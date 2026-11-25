import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('observer', Path(__file__).parents[1] / 'tools/tayvoriq_research_observer.py')
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class ResearchObserverTests(unittest.TestCase):
    def observation(self):
        return observer.Observation('20261125-evening-agentv2-c1234abcd', 'evening', 123, 2)

    def test_only_observed_counters_are_reported_and_drafts_are_distinct(self):
        o = self.observation()
        self.assertIsNone(o.data['sources_seen'])
        o.event({'event': 'source_records_loaded', 'total_records': 27})
        o.event({'event': 'research_draft_saved', 'title': 'Bosch'})
        o.event({'event': 'research_draft_saved', 'title': 'Bosch'})
        o.event({'event': 'candidate_editorial_rejection', 'title': 'Other'})
        self.assertEqual((o.data['sources_seen'], o.data['drafts_saved'], o.data['quality_rejections']), (27, 1, 1))
        o.finish(1)
        self.assertEqual(o.data['state'], 'FAILED')

    def test_provider_fallback_warnings_never_become_false_terminal_states(self):
        o = self.observation()
        o.event({'event': 'provider_attempt_failed', 'provider': 'gemini', 'error': 'HTTP 429 api_key=secret-value https://private.example'})
        o.event({'event': 'provider_attempt_started', 'provider': 'groq:model'})
        self.assertEqual(o.data['provider'], 'groq')
        self.assertEqual(o.data['state'], 'SEARCHING')
        self.assertEqual(o.data['issues'], [{'code': 'QUOTA', 'provider': 'gemini'}])
        self.assertNotIn('secret-value', json.dumps(o.data))
        self.assertNotIn('private.example', json.dumps(o.data))

    def test_binding_and_unknown_events_cannot_pollute_public_telemetry(self):
        with self.assertRaises(ValueError):
            observer.Observation('../private', 'evening', 123, 1)
        with self.assertRaises(ValueError):
            observer.Observation('20261125-evening-agentv2', 'morning', 123, 1)
        o = self.observation()
        self.assertFalse(o.event({'event': 'arbitrary', 'token': 'secret'}))
        self.assertNotIn('secret', json.dumps(o.data))
        self.assertEqual(observer.issue_code('HTTP 402 payment'), 'PAYMENT')
        self.assertEqual(observer.issue_code('source contract insufficient'), 'SOURCES')

    def test_an_old_attempt_or_different_run_cannot_overwrite_a_newer_binding(self):
        import base64
        for old in [{'run_id': 124, 'run_attempt': 1}, {'run_id': 123, 'run_attempt': 3}]:
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = json.dumps({'sha': 'version', 'content': base64.b64encode(json.dumps(old).encode()).decode()}).encode()
            request = Mock(return_value=response)
            self.assertFalse(observer.publish(self.observation().data, 'test-token', request=request))
            self.assertEqual(request.call_count, 1)

    def test_wrapper_is_in_the_explicit_research_path_and_preserves_command_result(self):
        root = Path(__file__).parents[1]
        workflow = (root / '.github/workflows/tayvoriq-telegram-trends-now.yml').read_text()
        self.assertIn('python tools/tayvoriq_research_observer.py --selection-id "$SELECTION_ID"', workflow)
        self.assertIn('python tools/tayvoriq_agent_trend_radar_v8.py', workflow)
        self.assertIn('return code', (root / 'tools/tayvoriq_research_observer.py').read_text())
