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
            browser.assert_not_called()  # Scheduled research checks the source pool before browsing.
            self.assertEqual(rss.call_count, 1)
            self.assertEqual(structure.call_count, 4)  # Each Groq model and HF are tried once.
            self.assertEqual(structure.call_args.kwargs['provider_kind'], 'huggingface')
            self.assertEqual(read(self.queue)['state'], 'EXHAUSTED')

    def test_payment_only_cannot_create_automatic_retry(self):
        health = ProviderHealth(self.health, clock=lambda: NOW)
        health.failure('huggingface', 'key', error(402))
        self.assertIsNone(health.next_retry({'huggingface': 'key'}))
        state = retry.defer('morning', None, path=self.queue, now=NOW)
        self.assertEqual(state['state'], 'EXTERNAL_BLOCKER')
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 1000), '')

    def test_due_slot_is_bounded_by_attempt_count_and_age(self):
        retry.defer('morning', NOW + 120, path=self.queue, now=NOW)
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 119), '')
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 120), 'morning')
        self.assertEqual(retry.regular_process_seconds('morning', path=self.queue, now=NOW + 300), 240)
        retry.defer('morning', NOW + 240, path=self.queue, now=NOW + 120)
        state = retry.defer('morning', NOW + 360, path=self.queue, now=NOW + 240)
        self.assertEqual(state['attempts'], retry.MAX_ATTEMPTS)
        self.assertEqual(state['state'], 'EXHAUSTED')
        self.assertEqual(state['valid_until_epoch'], NOW + 600)
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 24 * 3600), '')

    def test_pending_research_visible_and_cannot_override_active_production(self):
        retry.defer('morning', NOW + 120, path=self.queue, now=NOW)
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

    def test_editorial_rejection_ends_slot_if_next_retry_is_too_late(self):
        import tayvoriq_agent_trend_radar_v8 as radar
        env = {'TAYVORIQ_RESEARCH_RETRY_FILE': str(self.queue), 'TAYVORIQ_RESEARCH_SLOT': 'morning',
               'TAYVORIQ_RESEARCH_STARTED_AT_EPOCH': str(int(NOW))}
        with patch.dict(os.environ, env), patch.object(retry.time, 'time', return_value=NOW + 500):
            for _ in range(retry.MAX_ATTEMPTS):
                radar._mark_research_deferred('REGIONAL_RESCAN_REQUIRED')
        self.assertEqual(read(self.queue)['state'], 'EXHAUSTED')
        self.assertEqual(read(self.queue)['attempts'], 1)

    def test_legacy_exhaustion_keeps_attempts_without_reopening_the_slot(self):
        import json
        legacy = {'schema': 'tayvoriq-research-retry-v1', 'state': 'EXHAUSTED',
                  'slot': 'morning', 'berlin_date': '2026-10-20', 'attempts': 8,
                  'first_deferred_at_epoch': NOW, 'retry_at_epoch': NOW + 7200,
                  'valid_until_epoch': NOW + 21600,
                  'reason': 'RESEARCH_RETRY_BUDGET_EXHAUSTED'}
        self.queue.write_text(json.dumps(legacy))
        state = retry.current(self.queue, now=NOW + 8000)
        self.assertEqual(state['state'], 'EXHAUSTED')
        self.assertEqual(state['attempts'], 8)
        self.assertEqual(state['retry_at_epoch'], NOW + 7200)
        self.assertEqual(state['valid_until_epoch'], NOW + 21600)
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 10799), '')
        self.assertEqual(retry.due_slot(self.queue, now=NOW + 10800), '')
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

    def test_two_groq_cooldowns_route_to_third_source_bound_model(self):
        env = {'TAYVORIQ_PROVIDER_HEALTH_FILE': str(self.health),
               'TAYVORIQ_RESEARCH_RETRY_FILE': str(self.queue), 'TAYVORIQ_RESEARCH_SLOT': 'morning'}
        expected = ({'candidates': ['source-bound']}, ['chunks'], 'qwen/qwen3.8-27b')
        with patch.dict(os.environ, env), \
             patch.object(resilience.rss, 'source_pool', return_value=[{'url': 'https://source.example/story'}]), \
             patch.object(resilience.hf, 'structure', side_effect=[error(429, '35'), error(429, '60'), expected]) as structure:
            result = resilience.grounded('prompt', '', 'existing-groq-key')
        self.assertEqual([call.kwargs.get('model_override') for call in structure.call_args_list],
                         [None, 'openai/gpt-oss-120b', 'qwen/qwen3.8-27b'])
        self.assertEqual(result, (*expected, 'groq_rss'))
        self.assertEqual(set(read(self.health)['providers']), {'groq', 'groq:openai/gpt-oss-120b'})

    def test_editorial_rescan_prefers_an_alternate_groq_model(self):
        with patch.dict(os.environ, {'TAYVORIQ_PROVIDER_HEALTH_FILE': str(self.health),
                                    'TAYVORIQ_RESEARCH_SLOT': 'evening'}), \
             patch.object(resilience.rss, 'source_pool', return_value=[{'url': 'https://source.example/story'}]), \
             patch.object(resilience.hf, 'structure', return_value=({'candidates': []}, [], 'model')) as structure:
            resilience.grounded('Editorial context' + resilience.hf.EDITORIAL_RESCAN, '', 'existing-groq-key')
        self.assertEqual(structure.call_args.kwargs['model_override'], 'openai/gpt-oss-120b')

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
            ('2026-11-23T16:08:19+01:00', '30 4 * * *', 'evening', ''),
            ('2026-11-24T08:15:00+01:00', '0 18 * * *', 'morning', ''),
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
                     patch.object(retry, 'confirmed_slot_delivery', return_value=False), \
                     patch('tayvoriq_rejected_review_followup.followup', return_value=None):
                    exec(code, {})
                results = dict(line.split('=', 1) for line in output.read_text().splitlines())
                self.assertEqual(results['slot'], expected)
                self.assertEqual(results['should_run'], 'true' if expected else 'false')

    def test_terminal_notice_requires_receipt_and_claims_before_sending(self):
        import io
        import json
        import tayvoriq_research_terminal_notice as notices
        from datetime import datetime
        from contextlib import chdir
        queue = {"schema": "tayvoriq-research-retry-v1", "state": "EXHAUSTED", "slot": "evening",
                 "berlin_date": datetime.now(notices.ZONE).date().isoformat(),
                 "last_research_attempt": "234.1", "attempts": 10, "max_attempts": 10}
        for chat, expected in [("-12", "DELIVERED"), ("-13", "UNCONFIRMED")]:
            with self.subTest(chat=chat), tempfile.TemporaryDirectory() as temp, chdir(temp):
                Path("queue.json").write_text(json.dumps(queue))
                env = {"TAYVORIQ_RESEARCH_RETRY_FILE":"queue.json", "TELEGRAM_BOT_TOKEN":"test",
                       "TELEGRAM_CHAT_ID":"-12", "GITHUB_REPOSITORY":"owner/repo"}
                reply = {"ok": True, "result": {"message_id": 91, "chat": {"id": int(chat)}}}
                def send(*args, **kwargs):
                    record = next(Path(".automation").rglob("*.json"))
                    self.assertEqual(json.loads(record.read_text())["state"], "SENDING")
                    return io.BytesIO(json.dumps(reply).encode())
                with patch.dict(os.environ, env), patch.object(notices, "persist", notices.write), \
                        patch.object(notices.urllib.request, "urlopen", side_effect=send) as sender:
                    if expected == "DELIVERED":
                        notices.main()
                    else:
                        with self.assertRaises(RuntimeError):
                            notices.main()
                    notices.main()
                    self.assertEqual(sender.call_count, 1)
                    record = json.loads(next(Path(".automation").rglob("*.json")).read_text())
                    self.assertEqual(record["state"], expected)
                    self.assertEqual(record["telegram_delivery_verified"], expected == "DELIVERED")

    def test_terminal_slot_is_scoped_to_berlin_day_and_slot(self):
        from datetime import datetime
        stamp = datetime.fromisoformat("2026-11-23T19:00:00+01:00")
        for state, day, slot, expected in [
            ("EXHAUSTED", "2026-11-23", "evening", True),
            ("EXTERNAL_BLOCKER", "2026-11-23", "evening", True),
            ("WAITING", "2026-11-23", "evening", False),
            ("EXHAUSTED", "2026-11-22", "evening", False),
            ("EXHAUSTED", "2026-11-23", "morning", False),
        ]:
            with self.subTest(state=state, day=day, slot=slot), patch.object(
                retry, "current", return_value={"state": state, "berlin_date": day, "slot": slot}
            ):
                self.assertEqual(retry.terminal_slot("evening", stamp), expected)

    def test_exhausted_slot_cannot_be_reopened_by_a_maintainer_marker(self):
        from datetime import datetime
        stamp = datetime.fromisoformat("2026-11-23T23:45:00+01:00")
        now = stamp.timestamp()
        state = {"schema": "tayvoriq-research-retry-v1", "state": "EXHAUSTED",
                 "slot": "evening", "berlin_date": "2026-11-23", "attempts": 10,
                 "valid_until_epoch": now - 60, "first_deferred_at_epoch": now - 21660,
                 "last_issue": "EDITORIAL_MINIMUM_NOT_MET", "last_research_attempt": "234.1"}
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        queue = Path(temp.name) / "research-retry.json"
        retry.write(queue, state)
        marker = "retry_terminal=2026-11-23:evening:234.1"
        with patch.dict("os.environ", {"TAYVORIQ_RESEARCH_RETRY_FILE": str(queue),
                                       "TAYVORIQ_RESEARCH_RUN_KEY": "235.1",
                                       "TAYVORIQ_RESEARCH_REPAIR_FROM": "234.1"}), \
             patch.object(retry, "confirmed_slot_delivery", return_value=False):
            self.assertEqual(retry.terminal_repair_attempt(marker, "evening", stamp), "")
            before = read(queue)
            result = retry.defer("evening", now + 900, now=now,
                                 issue="EDITORIAL_MINIMUM_NOT_MET")
            self.assertEqual(result, before)
            self.assertEqual(read(queue), before)
            self.assertEqual(result["attempts"], 10)
            self.assertEqual(result["last_research_attempt"], "234.1")

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

    def test_new_editorial_packet_can_be_delivered_after_feed_exhaustion_once(self):
        from datetime import datetime
        import yaml

        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        steps = workflow['jobs']['trend-gate']['steps']
        resolver = next(step['run'] for step in steps if step.get('id') == 'slot')
        ranking = next(step['run'] for step in steps if step.get('name') == 'Generate quality-driven 1-5 trend ranking')
        prepared_branch = ranking.split('elif [ "$PREPARED_ONLY" = true ]; then\n', 1)[1].split('\nelse\n', 1)[0]
        self.assertIn('timeout --kill-after=5s 420 "${command[@]}"', prepared_branch)
        self.assertNotIn('regular_process_seconds', prepared_branch)
        code = compile(resolver.split("<<'PY'\n", 1)[1].rsplit('\nPY\n', 1)[0], 'prepared research', 'exec')
        now = datetime.fromisoformat('2026-11-24T22:30:00+01:00')
        packet = 'state/tayvoriq-verified-research-evening.json'
        cases = [(packet, False, True), (packet, True, False),
                 ('.github/run-now/tayvoriq-agent-trigger.txt', False, False)]
        for changed, delivered, expected in cases:
            with self.subTest(changed=changed, delivered=delivered), tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / 'output'
                env = {'EVENT_NAME': 'push', 'GITHUB_OUTPUT': str(output),
                       'PUSH_BEFORE': 'a' * 40, 'GITHUB_SHA': 'b' * 40}
                with patch.dict(os.environ, env, clear=True), patch('datetime.datetime') as clock, \
                     patch('subprocess.check_output', return_value=changed + '\n'), \
                     patch.object(retry, 'due_slot', return_value=''), \
                     patch.object(retry, 'terminal_slot', return_value=True), \
                     patch.object(retry, 'confirmed_slot_delivery', return_value=delivered), \
                     patch('tayvoriq_rejected_review_followup.followup', return_value=None):
                    clock.now.side_effect = lambda tz: now.astimezone(tz)
                    exec(code, {})
                results = dict(line.split('=', 1) for line in output.read_text().splitlines())
                self.assertEqual(results['slot'], 'evening')
                self.assertEqual(results['should_run'], 'true' if expected else 'false')
                self.assertEqual(results['prepared_only'], 'true' if expected else 'false')

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

    def test_verified_exhaustion_from_an_earlier_day_releases_discovery_only(self):
        import json
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        import yaml

        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        source = next(step['run'] for step in workflow['jobs']['trend-gate']['steps']
                      if step.get('id') == 'active_request')
        program = compile(source.split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0], '<active-request>', 'exec')
        today_slot = datetime.now(ZoneInfo('Europe/Berlin')).date()
        yesterday_slot = today_slot - timedelta(days=1)
        request_id, run_id = 'telegram-3696-trend-1', 45510042088
        reason = 'LOCAL_VISUAL_RECOVERY_EXHAUSTED'
        receipt = dict(schema='tayvoriq-recovery-outcome-v1', state='EXHAUSTED', reason=reason,
                       request_id=request_id, run_id=run_id, recovery_generation=1,
                       publish_allowed=False, quality_gates_weakened=False)
        decision = dict(state='REPAIR_REQUIRED', action='NONE', reason=reason,
                        request_id=request_id, run_id=str(run_id), generation='1')

        with tempfile.TemporaryDirectory() as folder:
            before = Path.cwd()
            os.chdir(folder)
            try:
                pointer_path = Path('.github/state/tayvoriq-active-production-request.json')
                decision_path = pointer_path.with_name('tayvoriq-lifecycle-decision.json')
                request_path = Path('requests') / f'{request_id}.json'
                pointer_path.parent.mkdir(parents=True)
                request_path.parent.mkdir()
                for title, date, outcome, lifecycle, expected in (
                    ('previous day exhausted', yesterday_slot, receipt, decision, 'false'),
                    ('same day exhausted', today_slot, receipt, decision, 'true'),
                    ('missing outcome', yesterday_slot, {}, decision, 'true'),
                    ('wrong run', yesterday_slot, dict(receipt, run_id=run_id + 1), decision, 'true'),
                    ('new recovery dispatch', yesterday_slot, receipt, dict(decision, action='DELIVERY_WATCH'), 'true'),
                ):
                    with self.subTest(title=title):
                        selection = f'{date:%Y%m%d}-evening-agentv2'
                        pointer = dict(request_id=request_id, state='ACTIVE', selection_id=selection,
                                       golden_path_run_id=run_id, recovery_generation=1)
                        request = dict(request_id=request_id, status='DISPATCHED', selection_id=selection,
                                       golden_path_run_id=run_id, recovery_outcome=outcome)
                        inputs = {pointer_path: pointer, request_path: request, decision_path: lifecycle}
                        for path, data in inputs.items():
                            path.write_text(json.dumps(data), encoding='utf-8')
                        output = Path('outputs')
                        output.write_text('', encoding='utf-8')
                        with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
                            exec(program, {})
                        self.assertIn(f'active={expected}\n', output.read_text(encoding='utf-8'))
                        for path, data in inputs.items():
                            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), data)
            finally:
                os.chdir(before)

    def test_due_research_reuses_existing_approval_and_delivery_gates(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        steps = workflow['jobs']['trend-gate']['steps']
        resolver = next(s for s in steps if s.get('id') == 'slot')['run']
        self.assertIn("schedule == '*/5 * * * *'", resolver)
        self.assertIn('due_slot(now=now.timestamp())', resolver)
        push_resolver = resolver.split("if event == 'push' and should:", 1)[1].split("if event == 'schedule':", 1)[0]
        self.assertIn("slot = prepared_slot or due_slot(now=now.timestamp()) or ('morning' if now.hour < 12 else 'evening')", push_resolver)
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

    def test_external_clock_revalidates_retry_and_duplicate_delivery(self):
        from datetime import datetime
        now = datetime.fromisoformat("2026-11-23T13:35:00+01:00")
        tick = str(int(now.timestamp()) - 60)
        with patch.object(retry, "confirmed_slot_delivery", return_value=False), \
                patch.object(retry, "due_slot", return_value="morning"):
            self.assertEqual(retry.clock_slot("morning", "retry", "2026-11-23", tick, now=now), "morning")
            self.assertEqual(retry.clock_slot("evening", "retry", "2026-11-23", tick, now=now), "")
            self.assertEqual(retry.clock_slot("morning", "retry", "2026-11-22", tick, now=now), "")
        with patch.object(retry, "confirmed_slot_delivery", return_value=True):
            self.assertEqual(retry.clock_slot("morning", "retry", "2026-11-23", tick, now=now), "")

    def test_scheduled_rescans_share_one_attempt_and_keep_the_original_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            queue = Path(folder) / "research-retry.json"
            with patch.dict(os.environ, {"TAYVORIQ_RESEARCH_RUN_KEY": "1.1",
                                         "TAYVORIQ_RESEARCH_STARTED_AT_EPOCH": str(int(NOW))}):
                first = retry.defer("morning", NOW + 120, path=queue, now=NOW + 30)
                second = retry.defer("morning", NOW + 900, path=queue, now=NOW + 35)
            assert first["attempts"] == second["attempts"] == 1
            assert first["valid_until_epoch"] == second["valid_until_epoch"] == NOW + 600
            assert first["state"] == "WAITING"
            assert second["state"] == "EXHAUSTED"

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


def test_healthy_source_editor_can_retry_within_slot_but_real_quota_is_respected(tmp_path):
    health = ProviderHealth(tmp_path / "health.json", clock=lambda: NOW)
    queue = tmp_path / "retry.json"
    keys = {"groq":"live", "gemini":"limited"}
    health.failure("gemini", keys["gemini"], error(429))
    due = health.next_retry(keys, available_delay_seconds=90)
    assert due == NOW + 90
    result = retry.defer("morning",due,path=queue,now=NOW,issue="SOURCE_MINIMUM_NOT_MET")
    assert result["state"] == "WAITING"
    assert retry.due_slot(queue,now=NOW+90) == "morning"
    assert health.next_retry({"gemini":"limited"},available_delay_seconds=90) == NOW+1800


def test_editorial_and_regional_rescans_remain_within_the_original_slot(tmp_path, monkeypatch):
    import tayvoriq_agent_research_resilience_v2 as resilience
    import tayvoriq_agent_trend_radar_v8 as radar

    marker = tmp_path / "marker.json"
    monkeypatch.setattr(resilience, "MARKER", marker)
    monkeypatch.setattr(radar, "Path", lambda _: marker)
    monkeypatch.setenv("TAYVORIQ_RESEARCH_SLOT", "morning")
    monkeypatch.delenv("TAYVORIQ_RESEARCH_SELECTION_ID", raising=False)
    monkeypatch.setenv("TAYVORIQ_RESEARCH_STARTED_AT_EPOCH", str(int(NOW)))
    monkeypatch.setattr(retry.time, "time", lambda: NOW + 220)
    for issue, reject in (
        ("EDITORIAL_MINIMUM_NOT_MET", lambda: resilience.defer_editorial("morning")),
        ("REGIONAL_MINIMUM_NOT_MET", lambda: radar._mark_research_deferred("REGIONAL_RESCAN_REQUIRED")),
    ):
        queue = tmp_path / (issue + ".json")
        monkeypatch.setenv("TAYVORIQ_RESEARCH_RETRY_FILE", str(queue))
        reject()
        state = retry.current(queue)
        assert state["last_issue"] == issue
        assert state["state"] == "WAITING"
        assert state["valid_until_epoch"] == NOW + 600
        assert state["retry_at_epoch"] == NOW + 220 + retry.EDITORIAL_RETRY_SECONDS
        assert retry.due_slot(queue, now=state["retry_at_epoch"]) == "morning"
