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
        def structure(*args, **kwargs):
            raise error(429 if kwargs['provider_kind'] == 'groq' else 402)
        with patch.dict(os.environ, env), \
             patch.object(resilience, 'MARKER', Path(self.tmp.name) / 'marker.json'), \
             patch.object(provider, 'groq_browser_then_structure', side_effect=error(429)) as browser, \
             patch.object(resilience.rss, 'source_pool', return_value=[{'url': 'https://source.example/story'}]) as rss, \
             patch.object(resilience.gdelt, 'source_pool', side_effect=AssertionError('all structurers blocked')), \
             patch.object(resilience.hf, 'structure', side_effect=structure) as structure:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, 'RESEARCH_DEFERRED'):
                    resilience.grounded('prompt', '', 'groq-key')
            self.assertEqual(browser.call_count, 1)
            self.assertEqual(rss.call_count, 1)
            self.assertEqual(structure.call_count, 2)  # alternate model then HF, each once
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
        self.assertEqual(state['state'], 'WAITING')
        self.assertEqual(state['retry_phase'], 'SLOW_RECOVERY')
        self.assertEqual(state['retry_at_epoch'], NOW + 9900)
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 7200), '')
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 9900), 'morning')
        retry.defer('morning', NOW + 10000, path=self.queue, now=NOW + 9900)
        state = retry.defer('morning', NOW + 14000, path=self.queue, now=NOW + 13500)
        self.assertEqual(state['attempts'], 10)
        self.assertEqual(state['state'], 'EXHAUSTED')
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
            for _ in range(retry.MAX_ATTEMPTS):
                radar._mark_research_deferred('REGIONAL_RESCAN_REQUIRED')
        self.assertEqual(read(self.queue)['state'], 'EXHAUSTED')
        self.assertEqual(read(self.queue)['attempts'], retry.MAX_ATTEMPTS)

    def test_legacy_exhaustion_keeps_attempts_and_deadline_for_two_slow_reserves(self):
        import json
        legacy = {'schema': 'tayvoriq-research-retry-v1', 'state': 'EXHAUSTED',
                  'slot': 'morning', 'berlin_date': '2026-10-20', 'attempts': 8,
                  'first_deferred_at_epoch': NOW, 'retry_at_epoch': NOW + 7200,
                  'valid_until_epoch': NOW + 21600,
                  'reason': 'RESEARCH_RETRY_BUDGET_EXHAUSTED'}
        self.queue.write_text(json.dumps(legacy))
        state = retry.current(self.queue, now=NOW + 8000)
        self.assertEqual(state['state'], 'WAITING')
        self.assertEqual(state['attempts'], 8)
        self.assertEqual(state['retry_at_epoch'], NOW + 10800)
        self.assertEqual(state['valid_until_epoch'], NOW + 21600)
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 10799), '')
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 10800), 'morning')
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 21600), '')
        self.queue.write_text(json.dumps({**legacy, 'retry_at_epoch': None}))
        self.assertEqual(retry.current(self.queue, now=NOW + 8000)['state'], 'EXHAUSTED')

    def test_model_daily_limit_routes_once_to_existing_alternate_budget(self):
        env = {'TAYVORIQ_PROVIDER_HEALTH_FILE': str(self.health),
               'TAYVORIQ_RESEARCH_RETRY_FILE': str(self.queue)}
        with patch.dict(os.environ, env), \
             patch.object(provider, 'groq_browser_then_structure', side_effect=error(429, '3600')) as call, \
             patch.object(resilience.rss, 'source_pool', return_value=[{'url': 'https://source.example/story'}]), \
             patch.object(resilience.hf, 'structure', return_value=(
                 {'candidates': ['source-bound']}, ['chunks'], 'openai/gpt-oss-120b')) as structure:
            result = resilience.grounded('prompt', '', 'existing-groq-key')
        self.assertEqual(call.call_count, 1)
        self.assertEqual(structure.call_count, 1)
        self.assertEqual(structure.call_args.kwargs['model_override'], 'openai/gpt-oss-120b')
        self.assertEqual(result[2], 'openai/gpt-oss-120b')
        self.assertEqual(read(self.health)['providers']['groq']['http_status'], 429)
        self.assertNotIn('groq:openai/gpt-oss-120b', read(self.health)['providers'])

    def test_model_response_clears_expired_quota_even_when_sources_fail(self):
        health = ProviderHealth(self.health, clock=lambda: NOW)
        health.failure('groq', 'groq-key', error(429, '1'))
        env = {'TAYVORIQ_PROVIDER_HEALTH_FILE': str(self.health), 'HF_TOKEN': '', 'HUGGINGFACE_TOKEN': ''}
        with patch.dict(os.environ, env), \
             patch.object(resilience, 'MARKER', Path(self.tmp.name) / 'marker.json'), \
             patch.object(provider, 'groq_browser_then_structure') as browser, \
             patch.object(resilience.rss, 'source_pool', return_value=[{'url': 'https://source.example/story'}]), \
             patch.object(resilience.gdelt, 'source_pool', return_value=[]), \
             patch.object(resilience.hf, 'structure', side_effect=resilience.hf.InsufficientSourceEvidence('no safe pairs')):
            with self.assertRaisesRegex(RuntimeError, 'RESEARCH_DEFERRED'):
                resilience.grounded('prompt', '', 'groq-key')
            browser.assert_not_called()
            self.assertNotIn('groq', read(self.health)['providers'])

    def test_recovering_model_preserves_budget_for_source_structuring(self):
        state = ProviderHealth(self.health, clock=lambda: NOW)
        state.failure('groq', 'groq-key', error(429, '1'))
        env = {'TAYVORIQ_PROVIDER_HEALTH_FILE': str(self.health),
               'TAYVORIQ_RESEARCH_RETRY_FILE': str(self.queue)}
        with patch.dict(os.environ, env), \
             patch.object(provider, 'groq_browser_then_structure', side_effect=AssertionError('no browser after 429')), \
             patch.object(resilience.rss, 'source_pool', return_value=[{'url': 'https://source.example/story'}]), \
             patch.object(resilience.hf, 'structure', return_value=(
                 {'candidates': ['source-bound']}, ['chunks'], 'verified')) as structure:
            result = resilience.grounded('prompt', '', 'groq-key')
        self.assertEqual(result[3], 'groq_rss')
        self.assertEqual(structure.call_count, 1)
        self.assertNotIn('groq', read(self.health)['providers'])

    def test_payment_or_permission_failure_never_switches_groq_models(self):
        for code in (402, 403):
            with self.subTest(code=code), \
                 patch.dict(os.environ, {'TAYVORIQ_PROVIDER_HEALTH_FILE': str(self.health),
                                         'TAYVORIQ_RESEARCH_RETRY_FILE': str(self.queue),
                                         'HF_TOKEN': '', 'HUGGINGFACE_TOKEN': ''}), \
                 patch.object(provider, 'groq_browser_then_structure', side_effect=error(code)) as call:
                self.health.unlink(missing_ok=True)
                with self.assertRaises(RuntimeError):
                    resilience.grounded('prompt', '', 'groq-key')
                self.assertEqual(call.call_count, 1)

    def test_nested_groq_rate_limit_does_not_repeat_or_drop_reset_headers(self):
        with patch.object(provider.urllib.request, 'urlopen', side_effect=error(429, '7200')) as call, \
             patch.object(provider.time, 'sleep', side_effect=AssertionError('must defer')):
            with self.assertRaises(RuntimeError) as caught:
                provider._run_with_backoff('outer', lambda: provider.post_groq({}, 'key'), 3)
        self.assertEqual(call.call_count, 1)
        code, headers = http_failure(caught.exception)
        self.assertEqual(code, 429)
        self.assertEqual(headers['retry-after'], '7200')

    def test_previous_day_expired_research_cannot_block_fresh_lifecycle(self):
        retry.defer('morning', NOW + 900, path=self.queue, now=NOW)
        with patch.dict(os.environ, {'TAYVORIQ_RESEARCH_RETRY_FILE': str(self.queue)}), \
             patch.object(retry.time, 'time', return_value=NOW + 26 * 3600):
            result = retry.lifecycle({'state': 'IDLE', 'action': 'NONE'})
            self.assertEqual(result['state'], 'IDLE')
            self.assertEqual(result['action'], 'NONE')
            self.assertEqual(retry.due_slot(self.queue, now=NOW + 26 * 3600), '')


class SchedulerContractTests(unittest.TestCase):
    def test_berlin_slot_workflow_python_executes_for_regular_and_retry_ticks(self):
        from datetime import datetime
        from tempfile import TemporaryDirectory
        import yaml

        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        resolver = next(step['run'] for step in workflow['jobs']['trend-gate']['steps'] if step.get('id') == 'slot')
        source = resolver.split("<<'PY'\n", 1)[1].rsplit('\nPY\n', 1)[0]
        code = compile(source, 'Berlin slot in the deployed workflow', 'exec')

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return current.astimezone(tz)

        cases = [
            ('2026-11-23T05:30:00+01:00', '30 4 * * *', '', 'morning'),
            ('2026-11-23T19:00:00+01:00', '0 18 * * *', '', 'evening'),
            ('2026-09-01T05:30:00+02:00', '30 3 * * *', '', 'morning'),
            ('2026-09-01T19:00:00+02:00', '0 17 * * *', '', 'evening'),
            ('2026-11-23T04:30:00+01:00', '30 3 * * *', '', ''),
            ('2026-11-23T12:05:00+01:00', '*/5 * * * *', 'morning', 'morning'),
            ('2026-11-23T12:05:00+01:00', '*/5 * * * *', '', ''),
        ]
        for stamp, cron, retry_slot, expected in cases:
            current = datetime.fromisoformat(stamp)
            with self.subTest(cron=cron, stamp=stamp, retry=retry_slot), TemporaryDirectory() as temp:
                output = Path(temp) / 'output'
                env = {'EVENT_NAME': 'schedule', 'EVENT_SCHEDULE': cron, 'GITHUB_OUTPUT': str(output)}
                with patch.dict(os.environ, env, clear=True), patch('datetime.datetime', FrozenDateTime), \
                     patch.object(retry, 'due_slot', return_value=retry_slot), \
                     patch('tayvoriq_rejected_review_followup.followup', return_value=None):
                    exec(code, {})
                results = dict(line.split('=', 1) for line in output.read_text().splitlines())
                self.assertEqual(results['slot'], expected)
                self.assertEqual(results['should_run'], 'true' if expected else 'false')

    def test_scheduled_tick_uses_durable_retry_without_sleeping_or_dispatching_again(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        agent = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        triggers = agent.get('on') or agent.get(True)
        self.assertEqual({item['cron'] for item in triggers['schedule']}, {
            '*/5 * * * *', '30 3 * * *', '30 4 * * *', '0 17 * * *', '0 18 * * *',
        })
        steps = agent['jobs']['trend-gate']['steps']
        resolver = next(step['run'] for step in steps if step.get('id') == 'slot')
        self.assertIn("schedule == '*/5 * * * *'", resolver)
        self.assertIn("review_due(plan['selection_id']", resolver)
        self.assertIn('slot = due_slot(now=now.timestamp())', resolver)
        self.assertFalse((root / '.github/workflows/tayvoriq-research-retry-wakeup.yml').exists())
        self.assertNotIn('tayvoriq-research-retry-wakeup.yml/dispatches', str(steps))
        self.assertIn('research_retry_wakeup', triggers['workflow_dispatch']['inputs'])

    def test_push_slot_is_bound_to_event_commit_after_main_advances(self):
        from datetime import datetime
        from tempfile import TemporaryDirectory
        import yaml

        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        resolver = next(step['run'] for step in workflow['jobs']['trend-gate']['steps'] if step.get('id') == 'slot')
        code = compile(resolver.split("<<'PY'\n", 1)[1].rsplit('\nPY\n', 1)[0], 'Berlin push slot', 'exec')
        now = datetime.fromisoformat('2026-11-23T08:29:00+01:00')
        plan = {'decision_path': '.automation/tayvoriq-artifact-decisions/1234.json',
                'new_trends_requested': True, 'selection_delivered': False,
                'slot': 'evening', 'selection_id': 'review-evening-1234'}

        for changed, slot in (('.github/run-now/tayvoriq-agent-trigger.txt', 'morning'),
                              ('.github/workflows/tayvoriq-agent-orchestrator-v2.yml', ''),
                              (plan['decision_path'], 'evening')):
            with self.subTest(changed=changed), TemporaryDirectory() as temp:
                output = Path(temp) / 'output'
                env = {'EVENT_NAME': 'push', 'GITHUB_OUTPUT': str(output),
                       'PUSH_BEFORE': 'a' * 40, 'GITHUB_SHA': 'b' * 40}
                with patch.dict(os.environ, env, clear=True), patch('datetime.datetime') as clock, \
                     patch('subprocess.check_output', return_value=changed + '\n') as git, \
                     patch.object(retry, 'due_slot', return_value=''), \
                     patch('tayvoriq_rejected_review_followup.followup', return_value=plan):
                    clock.now.side_effect = lambda tz: now.astimezone(tz)
                    exec(code, {})
                git.assert_called_once_with(['git', 'diff', '--name-only', 'a' * 40, 'b' * 40], text=True)
                results = dict(line.split('=', 1) for line in output.read_text().splitlines())
                self.assertEqual(results['slot'], slot)
                self.assertEqual(results['should_run'], 'true' if slot else 'false')

    def test_model_cache_is_saved_before_a_failed_publishability_gate(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        producer = yaml.safe_load((root / '.github/workflows/tayvoriq-deliver-video-now.yml').read_text())
        steps = producer['jobs']['orchestrate']['steps']
        names = [step.get('name') for step in steps]
        restore = steps[names.index('Restore production model cache')]
        save_index = names.index('Persist downloaded production models before the output gate')
        save = steps[save_index]
        self.assertEqual(restore['uses'], 'actions/cache/restore@v4')
        self.assertEqual(save['uses'], 'actions/cache/save@v4')
        self.assertIn('steps.model_cache.outputs.cache-primary-key', save['with']['key'])
        self.assertIn("steps.model_cache.outputs.cache-hit != 'true'", save['if'])
        self.assertLess(names.index('Repair only failed local checkpoints'), save_index)
        self.assertLess(save_index, names.index('Assert publishable production output'))

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

    def test_rejected_review_gets_own_five_minute_queue_and_ten_minute_sla(self):
        selection = 'review-evening-43776528221'
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            queue = folder / 'research-retries' / f'{selection}.json'
            queue.parent.mkdir()
            first = retry.defer('evening', NOW + 900, path=queue, now=NOW)
            self.assertEqual(first['selection_id'], selection)
            self.assertEqual(first['retry_at_epoch'], NOW + 300)
            self.assertEqual(first['valid_until_epoch'], NOW + 600)
            self.assertEqual(first['sla_seconds'], 600)
            self.assertEqual(first['max_attempts'], 3)
            self.assertEqual(first['retry_phase'], 'REVIEW_FAST')
            with patch.object(retry, 'REVIEW_RETRY_DIR', queue.parent), \
                 patch.object(retry, 'read', wraps=read):
                self.assertFalse(retry.review_due(selection, now=NOW + 299))
                self.assertTrue(retry.review_due(selection, now=NOW + 300))
            second = retry.defer('evening', NOW + 1200, path=queue, now=NOW + 300)
            self.assertEqual(second['retry_at_epoch'], NOW + 600)
            final = retry.defer('evening', NOW + 1500, path=queue, now=NOW + 600)
            self.assertEqual(final['state'], 'EXHAUSTED')
            self.assertEqual(final['attempts'], 3)

        import yaml
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        steps = workflow['jobs']['trend-gate']['steps']
        bind = next(step for step in steps if step.get('name') == 'Bind replacement trend research state')
        self.assertIn('research-retries/${REVIEW_SELECTION}.json', bind['run'])
        generate = next(step for step in steps if step.get('name') == 'Generate quality-driven 1-5 trend ranking')
        self.assertEqual(generate['env']['TAYVORIQ_RESEARCH_SELECTION_ID'],
                         "${{ steps.slot.outputs.rejection_selection }}")

if __name__ == '__main__':
    unittest.main()
