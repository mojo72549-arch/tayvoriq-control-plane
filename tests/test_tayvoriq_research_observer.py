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
        self.assertIn('python tools/tayvoriq_contabo_research.py', workflow)
        self.assertNotIn('secrets.GEMINI_API_KEY', workflow)
        self.assertIn('return code', (root / 'tools/tayvoriq_research_observer.py').read_text())

    def test_stopping_while_waiting_prevents_the_next_provider_attempt(self):
        import tempfile
        o = self.observation()
        with tempfile.TemporaryDirectory() as directory:
            retry = Path(directory) / 'retry.json'
            state = {'files': {'retry': retry}, 'env': {}, 'deadline': 600}
            def persist():
                retry.write_text(json.dumps({'state': 'WAITING', 'retry_at_epoch': 50}))

            run = Mock(return_value=1)
            stop = Mock(side_effect=[False, False, True])
            result = observer.execute(['test'], state, o, Mock(), persist, clock=lambda: 0,
                                      pause=Mock(), run=run, stopped=stop)
        self.assertEqual(result, observer.STOPPED)
        self.assertEqual(o.data['state'], 'STOPPED')
        self.assertIsNone(o.data['next_retry_at'])
        run.assert_called_once()


class ResearchFailureDiagnosticsTests(unittest.TestCase):
    observation = ResearchObserverTests.observation

    def test_worker_handoff_records_real_recheck_and_terminal_owner_without_invented_rejections(self):
        for started, expected in [(False, 'WORKER_START_TIMEOUT'), (True, 'WORKER_RESULT_TIMEOUT')]:
            o = self.observation()
            o.event({'event': 'contabo_worker_wakeup', 'wake_attempt': 1, 'next_check_epoch': 1090})
            self.assertEqual(o.data['handoff']['next_check_at'], '1970-01-01T00:18:10+00:00')
            if started:
                o.event({'event': 'contabo_worker_started', 'worker_run_id': 99})
            o.finish(124)
            self.assertIn({'code': expected, 'provider': None}, o.data['issues'])
            self.assertEqual(o.data['handoff']['state'], 'BLOCKED')
            self.assertEqual(o.data['handoff']['owner'], 'production_engineering')
            self.assertIsNone(o.data['handoff']['next_check_at'])
            self.assertEqual(o.data['quality_rejections'], 0)
            self.assertIsNone(o.data['sources_seen'])

    def test_wakeup_error_is_explicit_and_raw_errors_are_not_persisted(self):
        o = self.observation()
        o.event({'event': 'contabo_worker_failure', 'code': 'WORKER_WAKEUP_FAILED', 'error': 'secret-value'})
        o.finish(1)
        self.assertEqual(o.data['issues'], [{'code': 'WORKER_WAKEUP_FAILED', 'provider': None}])
        self.assertNotIn('secret-value', json.dumps(o.data))
        self.assertEqual(o.data['handoff']['action_required'], 'CHECK_RESEARCH_WAKEUP_ACCESS')

    def test_confirmed_worker_and_source_failure_replace_the_superseded_start_warning(self):
        o = self.observation()
        o.event({'event': 'contabo_worker_failure', 'code': 'WORKER_WAKEUP_FAILED', 'terminal': False, 'cause': 'ACCESS'})
        o.event({'event': 'contabo_worker_started', 'worker_run_id': 99})
        o.event({'event': 'contabo_worker_finished', 'status': 'FAILED', 'worker_run_id': 99})
        o.event({'event': 'insufficient_corroborated_stories', 'corroborated_titles': []})
        o.finish(1)
        self.assertEqual(o.data['issues'], [{'code': 'SOURCES', 'provider': None}])
        self.assertEqual(o.data['wakeup_failure_cause'], 'ACCESS')
        self.assertEqual(o.data['corroborated_headlines'], 0)
        self.assertEqual(o.data['handoff']['state'], 'BLOCKED')
        self.assertEqual(o.data['handoff']['owner'], 'research_controller')
        self.assertIsNone(o.data['handoff']['next_check_at'])

    def test_successful_article_evidence_clears_the_earlier_feed_warning(self):
        o = self.observation()
        o.event({'event': 'insufficient_corroborated_stories', 'corroborated_titles': []})
        o.event({'event': 'source_headline_preflight', 'corroborated_headlines': 2})
        self.assertEqual(o.data['issues'], [])

    def test_incomplete_scorecards_are_not_labeled_as_weak_tiktok_fit(self):
        o = self.observation()
        o.event({"event": "candidate_editorial_rejection", "reason": "regional_scorecard",
                 "details": ["invalid_or_unexplained_rating:consequence", "tiktok:regional_score_below_75"]})
        self.assertIn({"code": "EDITORIAL_FIELDS", "provider": None}, o.data["issues"])
        self.assertNotIn({"code": "TIKTOK_FIT", "provider": None}, o.data["issues"])

    def test_a_regional_summary_does_not_count_as_another_rejected_candidate(self):
        o = self.observation()
        for _ in range(2):
            o.event({"event": "candidate_editorial_rejection", "reason": "regional_scorecard",
                     "details": ["tiktok:regional_score_below_75"]})
        o.event({"event": "regional_editorial_validation", "required": 2, "eligible": 0})
        self.assertEqual(o.data["quality_rejections"], 2)

    def test_terminal_states_remove_an_old_retry_deadline(self):
        for code in (0, 1, 124):
            o = self.observation()
            o.waiting(1000, 2)
            o.finish(code)
            self.assertIsNone(o.data.get("next_retry_at"))

    def test_corroborated_stories_are_counted_separately_from_feed_records(self):
        o = self.observation()
        o.event({"event": "source_records_loaded", "total_records": 660})
        o.event({"event": "source_headline_preflight", "considered_records": 660,
                 "eligible_headlines": 6, "corroborated_headlines": 3})
        self.assertEqual(o.data["sources_seen"], 660)
        self.assertEqual(o.data["corroborated_headlines"], 3)
        self.assertEqual(o.data["drafts_saved"], 0)
