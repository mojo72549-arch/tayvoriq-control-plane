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
    def test_due_research_reuses_existing_approval_and_delivery_gates(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-agent-orchestrator-v2.yml').read_text())
        steps = workflow['jobs']['trend-gate']['steps']
        resolver = next(s for s in steps if s.get('id') == 'slot')['run']
        self.assertIn("schedule == '*/5 * * * *'", resolver)
        self.assertIn('due_slot(now=now.timestamp())', resolver)
        self.assertIn("os.environ.get('RECONCILE_ONLY') == 'true'", resolver)
        persist = next(s for s in steps if s.get('name') == 'Persist provider cooldown and bounded research retry')
        self.assertIn('always()', persist['if'])
        self.assertIn('git pull --rebase origin main', persist['run'])
        delivered = next(s for s in steps if s.get('name') == 'Persist verified Telegram delivery evidence')
        self.assertEqual(delivered['if'], "steps.telegram.outcome == 'success'")
        self.assertIn("delivered(os.environ['TAYVORIQ_RESEARCH_SLOT'])", delivered['run'])
        names = [s.get('name') for s in steps]
        self.assertIn('Validate approval contract', names)
        self.assertIn('Detect active production or recovery request', names)

if __name__ == '__main__':
    unittest.main()
