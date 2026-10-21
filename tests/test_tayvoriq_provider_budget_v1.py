import os
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import tayvoriq_agent_research_http_v2 as http
import tayvoriq_agent_research_resilience_v2 as resilience
import tayvoriq_agent_trend_provider_v3 as provider
from tayvoriq_provider_health_v1 import ProviderHealth, http_failure, retry_at, read
import tayvoriq_research_retry_v1 as retry

NOW = datetime(2026, 10, 20, 8, tzinfo=timezone.utc).timestamp()

def error(code, retry_after='1800'):
    headers = Message()
    headers['Retry-After'] = retry_after
    return urllib.error.HTTPError('https://example.invalid', code, 'test', headers, None)

class PersistentBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.health = Path(self.tmp.name) / 'health.json'
        self.queue = Path(self.tmp.name) / 'retry.json'

    def test_cooldown_and_payment_block_survive_reloading(self):
        first = ProviderHealth(self.health, clock=lambda: NOW)
        first.failure('groq', 'secret-not-for-storage', error(429))
        first.failure('huggingface', 'hf-secret', error(402))
        again = ProviderHealth(self.health, clock=lambda: NOW + 100)
        self.assertFalse(again.available('groq', 'secret-not-for-storage'))
        self.assertFalse(again.available('huggingface', 'hf-secret'))
        self.assertNotIn('secret-not-for-storage', self.health.read_text())
        self.assertEqual(again.next_retry({'groq': 'secret-not-for-storage', 'huggingface': 'hf-secret'}), NOW + 1800)
        later = ProviderHealth(self.health, clock=lambda: NOW + 1801)
        self.assertTrue(later.available('groq', 'secret-not-for-storage'))
        self.assertFalse(later.available('huggingface', 'hf-secret'))
        self.assertTrue(later.available('huggingface', 'rotated-credential'))

    def test_long_reset_and_http_date_are_not_capped(self):
        self.assertEqual(retry_at({'retry-after': '7200'}, NOW), NOW + 7200)
        self.assertEqual(retry_at({'retry-after': 'Tue, 20 Oct 2026 10:00:00 GMT'}, NOW), NOW + 7200)
        self.assertEqual(retry_at({'x-ratelimit-reset-tokens': '1h20m30s'}, NOW), NOW + 4830)

    def test_429_never_repeats_inline_and_preserves_original_headers(self):
        for run in (lambda call: http.retry('gemini', call, 3),
                    lambda call: provider._run_with_backoff('Groq', call, 3)):
            calls = []
            def call():
                calls.append(1)
                raise error(429, '7200')
            with patch.object(http.time, 'sleep', side_effect=AssertionError('must defer')):
                with self.assertRaises(RuntimeError) as caught:
                    run(call)
            self.assertEqual(calls, [1])
            code, headers = http_failure(caught.exception)
            self.assertEqual(code, 429)
            self.assertEqual(headers['retry-after'], '7200')

    def test_gemini_payment_block_does_not_repeat_across_models(self):
        with patch.object(http, 'post_json', side_effect=error(402)) as post:
            with self.assertRaises(urllib.error.HTTPError):
                http.gemini_grounded('prompt', 'key')
        self.assertEqual(post.call_count, 1)

    def test_depleted_groq_not_reused_for_rss_or_gdelt_hf_payment_is_blocked(self):
        env = {'TAYVORIQ_PROVIDER_HEALTH_FILE': str(self.health),
               'TAYVORIQ_RESEARCH_RETRY_FILE': str(self.queue),
               'TAYVORIQ_RESEARCH_SLOT': 'morning', 'HF_TOKEN': 'hf-key', 'HUGGINGFACE_TOKEN': ''}
        with patch.dict(os.environ, env), \
             patch.object(resilience, 'MARKER', Path(self.tmp.name) / 'marker.json'), \
             patch.object(provider, 'groq_browser_then_structure', side_effect=error(429)) as browser, \
             patch.object(resilience.rss, 'source_pool', return_value=[{'original': True}]) as rss, \
             patch.object(resilience.gdelt, 'source_pool', side_effect=AssertionError('all structurers blocked')), \
             patch.object(resilience.hf, 'structure', side_effect=error(402)) as structure:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, 'RESEARCH_DEFERRED'):
                    resilience.grounded('prompt', '', 'groq-key')
            self.assertEqual(browser.call_count, 1)
            self.assertEqual(rss.call_count, 1)
            self.assertEqual(structure.call_count, 1)
            self.assertEqual(structure.call_args.kwargs['provider_kind'], 'huggingface')
            self.assertEqual(read(self.queue)['state'], 'WAITING')

    def test_payment_only_cannot_create_automatic_retry(self):
        health = ProviderHealth(self.health, clock=lambda: NOW)
        health.failure('huggingface', 'key', error(402))
        self.assertIsNone(health.next_retry({'huggingface': 'key'}))
        state = retry.defer('morning', None, path=self.queue, now=NOW)
        self.assertEqual(state['state'], 'EXTERNAL_BLOCKER')
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 1000), '')

    def test_due_slot_is_bounded_by_attempt_count_and_age(self):
        retry.defer('morning', NOW + 900, path=self.queue, now=NOW)
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 899), '')
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 900), 'morning')
        for i in range(1, 8):
            state = retry.defer('morning', NOW + 900 * (i + 1), path=self.queue, now=NOW + i * 900)
        self.assertEqual(state['attempts'], 8)
        self.assertEqual(state['state'], 'EXHAUSTED')
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 7200), '')
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 24 * 3600), '')

    def test_pending_research_visible_and_cannot_override_active_production(self):
        retry.defer('morning', NOW + 900, path=self.queue, now=NOW)
        with patch.dict(os.environ, {'TAYVORIQ_RESEARCH_RETRY_FILE': str(self.queue)}), \
             patch.object(retry.time, 'time', return_value=NOW):
            result = retry.lifecycle({'state': 'IDLE', 'action': 'NONE'})
            self.assertEqual(result['state'], 'WAITING')
            self.assertEqual(result['reason'], 'RESEARCH_PROVIDER_COOLDOWN')
            active = {'state': 'RUNNING', 'action': 'NONE'}
            self.assertEqual(retry.lifecycle(active), active)
            retry.delivered('evening')
            self.assertEqual(read(self.queue)['state'], 'WAITING')
            retry.delivered('morning')
            self.assertEqual(read(self.queue)['state'], 'DELIVERED')
            self.assertEqual(retry.lifecycle({'state': 'IDLE'})['state'], 'IDLE')

    def test_malformed_state_never_reports_healthy(self):
        self.queue.write_text('{"schema":"other"}')
        with self.assertRaises(ValueError):
            retry.due_slot(self.queue, now=NOW)

    def test_editorial_rejection_counts_towards_same_bounded_retry_budget(self):
        import tayvoriq_agent_trend_radar_v8 as radar
        env = {'TAYVORIQ_RESEARCH_RETRY_FILE': str(self.queue), 'TAYVORIQ_RESEARCH_SLOT': 'morning'}
        with patch.dict(os.environ, env):
            for _ in range(8):
                radar._mark_research_deferred('REGIONAL_RESCAN_REQUIRED')
        self.assertEqual(read(self.queue)['state'], 'EXHAUSTED')
        self.assertEqual(read(self.queue)['attempts'], 8)

class SchedulerContractTests(unittest.TestCase):
    def test_retry_wakeup_waits_once_and_revalidates_due_slot_before_dispatch(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        wake = yaml.safe_load((root / '.github/workflows/tayvoriq-research-retry-wakeup.yml').read_text())
        triggers = wake.get('on') or wake.get(True)
        self.assertIn('.automation/tayvoriq-agent-v2/research-retry.json', triggers['push']['paths'])
        self.assertTrue(wake['concurrency']['cancel-in-progress'])
        self.assertEqual(wake['permissions']['contents'], 'read')
        self.assertEqual(wake['permissions']['actions'], 'write')
        job = wake['jobs']['wake']
        self.assertLessEqual(job['timeout-minutes'], 130)
        steps = {step['name']: step for step in job['steps'] if step.get('name')}
        self.assertIn('WAITING', steps['Plan bounded wakeup']['run'])
        self.assertIn('time.sleep', steps['Wait until provider retry is due']['run'])
        dispatch = steps['Revalidate and dispatch exact due slot']['run']
        self.assertIn('git show origin/main:', dispatch)
        self.assertIn('due_slot', dispatch)
        self.assertIn("'research_retry_wakeup': 'true'", dispatch)

        agent = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        agent_triggers = agent.get('on') or agent.get(True)
        self.assertIn('research_retry_wakeup', agent_triggers['workflow_dispatch']['inputs'])
        resolver = next(s for s in agent['jobs']['trend-gate']['steps'] if s.get('id') == 'slot')['run']
        self.assertIn("event == 'workflow_dispatch' and os.environ.get('RESEARCH_RETRY_WAKEUP') == 'true'", resolver)
        self.assertIn('slot = due_slot(now=now.timestamp())', resolver)
        agent_steps = {step['name']: step for step in agent['jobs']['trend-gate']['steps'] if step.get('name')}
        rearm = agent_steps['Arm next bounded research wakeup']
        self.assertIn('always()', rearm['if'])
        self.assertIn("state.get('state') != 'WAITING'", rearm['run'])
        self.assertIn('tayvoriq-research-retry-wakeup.yml/dispatches', rearm['run'])
        refresh = agent_steps['Refresh ops health after provider state persistence']
        self.assertIn('always()', refresh['if'])
        self.assertIn('tayvoriq-ops-health.yml/dispatches', refresh['run'])

    def test_retry_wakeup_programs_execute_for_due_queue_and_verified_dispatch(self):
        import json
        import time
        import urllib.request
        import yaml
        root = Path(__file__).resolve().parents[1]
        wake = yaml.safe_load((root / '.github/workflows/tayvoriq-research-retry-wakeup.yml').read_text())
        steps = {step['name']: step for step in wake['jobs']['wake']['steps'] if step.get('name')}
        extract = lambda run: run.split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        queue = Path(folder.name) / 'retry.json'
        outputs = Path(folder.name) / 'outputs'
        latest = Path(folder.name) / 'latest-retry.json'
        retry.defer('morning', NOW + 900, path=queue, now=NOW)
        with patch.dict(os.environ, {'GITHUB_OUTPUT': str(outputs),
                                     'TAYVORIQ_RESEARCH_RETRY_FILE': str(queue)}), \
             patch.object(time, 'time', return_value=NOW):
            exec(compile(extract(steps['Plan bounded wakeup']['run']), '<retry-wakeup-plan>', 'exec'), {})
        plan = dict(line.split('=', 1) for line in outputs.read_text().splitlines())
        self.assertEqual(plan, {'enabled': 'true', 'wait_seconds': '900', 'slot': 'morning'})

        latest.write_text(queue.read_text())
        requests = []
        class Response:
            status = 204
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        def open_request(request, timeout=0):
            requests.append((request, timeout))
            return Response()
        env = {'GH_TOKEN': 'test-token', 'EXPECTED_SLOT': 'morning',
               'LATEST_RETRY_FILE': str(latest), 'GITHUB_API_URL': 'https://api.github.test',
               'GITHUB_REPOSITORY': 'owner/repository'}
        dispatch_program = extract(steps['Revalidate and dispatch exact due slot']['run'])
        with patch.dict(os.environ, env), patch.object(time, 'time', return_value=NOW + 901), \
             patch.object(urllib.request, 'urlopen', side_effect=open_request):
            exec(compile(dispatch_program, '<retry-wakeup-dispatch>', 'exec'), {})
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        self.assertEqual(timeout, 30)
        self.assertTrue(request.full_url.endswith('/actions/workflows/tayvoriq-agent-orchestrator-v2.yml/dispatches'))
        self.assertEqual(json.loads(request.data), {
            'ref': 'main', 'inputs': {'slot': 'morning', 'research_retry_wakeup': 'true'}})

    def test_orchestrator_rearms_wakeup_after_persisting_waiting_retry(self):
        import json
        import time
        import urllib.request
        import yaml
        root = Path(__file__).resolve().parents[1]
        agent = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        step = next(s for s in agent['jobs']['trend-gate']['steps']
                    if s.get('name') == 'Arm next bounded research wakeup')
        program = step['run'].split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]

        with tempfile.TemporaryDirectory() as folder:
            queue = Path(folder) / 'retry.json'
            retry.defer('morning', NOW + 900, path=queue, now=NOW)
            requests = []
            class Response:
                status = 204
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
            def open_request(request, timeout=0):
                requests.append((request, timeout))
                return Response()
            env = {'GH_TOKEN': 'test-token', 'TAYVORIQ_RESEARCH_RETRY_FILE': str(queue),
                   'GITHUB_API_URL': 'https://api.github.test',
                   'GITHUB_REPOSITORY': 'owner/repository'}
            with patch.dict(os.environ, env), patch.object(time, 'time', return_value=NOW), \
                 patch.object(urllib.request, 'urlopen', side_effect=open_request):
                exec(compile(program, '<retry-wakeup-rearm>', 'exec'), {})
            self.assertEqual(len(requests), 1)
            request, timeout = requests[0]
            self.assertEqual(timeout, 30)
            self.assertTrue(request.full_url.endswith(
                '/actions/workflows/tayvoriq-research-retry-wakeup.yml/dispatches'))
            self.assertEqual(json.loads(request.data), {'ref': 'main'})

    def test_orchestrator_dispatches_ops_health_after_provider_state_persistence(self):
        import json
        import urllib.request
        import yaml
        root = Path(__file__).resolve().parents[1]
        agent = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        step = next(s for s in agent['jobs']['trend-gate']['steps']
                    if s.get('name') == 'Refresh ops health after provider state persistence')
        program = step['run'].split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]

        requests = []
        class Response:
            status = 204
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        def open_request(request, timeout=0):
            requests.append((request, timeout))
            return Response()
        env = {'GH_TOKEN': 'test-token', 'GITHUB_API_URL': 'https://api.github.test',
               'GITHUB_REPOSITORY': 'owner/repository'}
        with patch.dict(os.environ, env), \
             patch.object(urllib.request, 'urlopen', side_effect=open_request):
            exec(compile(program, '<ops-health-dispatch>', 'exec'), {})
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        self.assertEqual(timeout, 30)
        self.assertTrue(request.full_url.endswith(
            '/actions/workflows/tayvoriq-ops-health.yml/dispatches'))
        self.assertEqual(json.loads(request.data), {'ref': 'main'})

    def test_provider_state_push_refreshes_control_center_without_waiting_for_cron(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-ops-health.yml').read_text())
        triggers = workflow.get('on') or workflow.get(True)
        paths = set(triggers['push']['paths'])
        self.assertIn('.automation/tayvoriq-agent-v2/provider-health.json', paths)
        self.assertIn('.automation/tayvoriq-agent-v2/research-retry.json', paths)
        self.assertIn('.github/workflows/tayvoriq-agent-orchestrator-v2.yml', paths)

    def test_persistence_pushes_reconciled_series_and_preserves_other_worktree_changes(self):
        import subprocess
        import yaml
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        steps = workflow['jobs']['trend-gate']['steps']
        persist = next(s for s in steps if s.get('name') == 'Persist provider cooldown and bounded research retry')['run']
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            remote, work = folder / 'remote.git', folder / 'work'
            def run(args, cwd=None):
                return subprocess.run(args, cwd=cwd or work, check=True, capture_output=True, text=True).stdout
            run(['git', 'init', '--bare', str(remote)], folder)
            run(['git', 'clone', str(remote), str(work)], folder)
            run(['git', 'checkout', '-b', 'main'])
            run(['git', 'config', 'user.name', 'test'])
            run(['git', 'config', 'user.email', 'test@example.invalid'])
            series = work / 'state/tayvoriq-active-series.json'
            series.parent.mkdir()
            series.write_text('{"status":"active"}')
            (work / 'unrelated.txt').write_text('original')
            run(['git', 'add', '.'])
            run(['git', 'commit', '-m', 'base'])
            run(['git', 'push', '-u', 'origin', 'main'])
            series.write_text('{"status":"completed"}')
            (work / 'unrelated.txt').write_text('preserve unrelated local change')
            health, queue = work / 'health.json', work / 'retry.json'
            health.write_text('{"providers":{}}')
            queue.write_text('{"state":"WAITING"}')
            result = subprocess.run(['bash', '-c', persist], cwd=work, capture_output=True, text=True,
                                    env={**os.environ, 'TAYVORIQ_PROVIDER_HEALTH_FILE': 'health.json',
                                         'TAYVORIQ_RESEARCH_RETRY_FILE': 'retry.json'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(run(['git', '--git-dir', str(remote), 'show', 'main:state/tayvoriq-active-series.json']).strip(), '{"status":"completed"}')
            self.assertEqual(run(['git', '--git-dir', str(remote), 'show', 'main:retry.json']).strip(), '{"state":"WAITING"}')
            self.assertEqual((work / 'unrelated.txt').read_text(), 'preserve unrelated local change')
            self.assertIn('unrelated.txt', run(['git', 'status', '--short']))

    def test_existing_verified_delivery_clears_retry_without_sending_again(self):
        import json
        import yaml
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        steps = workflow['jobs']['trend-gate']['steps']
        resolver = next(s for s in steps if s.get('id') == 'delivery')['run']
        program = resolver.split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            selection = '20261020-morning-agentv2-r1'
            request = folder / 'request.json'
            request.write_text(json.dumps({'selection_id': selection, 'slot': 'morning'}))
            receipt = folder / '.automation/tayvoriq-agent-v2/deliveries' / (selection + '.json')
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({'selection_id': selection, 'telegram_delivery_verified': True,
                                           'telegram_message_id': 123}))
            queue = folder / 'retry.json'
            retry.defer('morning', NOW + 900, path=queue, now=NOW)
            program = program.replace('/tmp/tayvoriq-trend-request.json', str(request))
            before = Path.cwd()
            try:
                os.chdir(folder)
                with patch.dict(os.environ, {'GITHUB_OUTPUT': str(folder / 'outputs'),
                                             'TAYVORIQ_RESEARCH_RETRY_FILE': str(queue)}), \
                     patch.object(retry.time, 'time', return_value=NOW):
                    exec(compile(program, '<delivery-resolver>', 'exec'), {})
            finally:
                os.chdir(before)
            self.assertEqual(read(queue)['state'], 'DELIVERED')
            self.assertIn('needs_delivery=false', (folder / 'outputs').read_text())
        names = [step.get('name') for step in steps]
        self.assertGreater(names.index('Persist provider cooldown and bounded research retry'),
                           names.index('Resolve idempotent selection delivery'))

    def test_due_research_reuses_existing_approval_and_delivery_gates(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        steps = workflow['jobs']['trend-gate']['steps']
        resolver = next(s for s in steps if s.get('id') == 'slot')['run']
        self.assertIn("schedule == '*/5 * * * *'", resolver)
        self.assertIn('due_slot(now=now.timestamp())', resolver)
        push_resolver = resolver.split("if event == 'push' and should:", 1)[1].split("if event == 'schedule':", 1)[0]
        self.assertIn("slot = due_slot(now=now.timestamp()) or ('morning' if now.hour < 12 else 'evening')", push_resolver)
        self.assertIn("os.environ.get('RECONCILE_ONLY') == 'true'", resolver)
        persist = next(s for s in steps if s.get('name') == 'Persist provider cooldown and bounded research retry')
        self.assertIn('always()', persist['if'])
        self.assertIn('git pull --rebase --autostash origin main', persist['run'])
        delivered = next(s for s in steps if s.get('name') == 'Persist verified Telegram delivery evidence')
        self.assertEqual(delivered['if'], "steps.telegram.outcome == 'success'")
        self.assertIn("delivered(os.environ['TAYVORIQ_RESEARCH_SLOT'])", delivered['run'])
        names = [s.get('name') for s in steps]
        self.assertIn('Validate approval contract', names)
        self.assertIn('Detect active production or recovery request', names)

if __name__ == '__main__':
    unittest.main()
