"""Archived news must not be misreported as a live incident."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "scripts" / "tayvoriq_ops_health.py"
spec = importlib.util.spec_from_file_location("tayvoriq_health_archived_test", FILE)
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)

POSTPROCESS_FILE = Path(__file__).resolve().parents[1] / "scripts" / "tayvoriq_ops_health_postprocess.py"
postprocess_spec = importlib.util.spec_from_file_location("tayvoriq_health_postprocess_test", POSTPROCESS_FILE)
postprocess = importlib.util.module_from_spec(postprocess_spec)
postprocess_spec.loader.exec_module(postprocess)


class ArchivedNewsHealthTests(unittest.TestCase):
    def setUp(self):
        from datetime import datetime, timezone
        from tayvoriq_stale_news_reconcile_v1 import quarantine
        self.run = {'id': 38249921806, 'name': 'TAYVORIQ-X Golden Path',
                    'status': 'completed', 'conclusion': 'failure',
                    'updated_at': '2026-10-12T00:00:00Z'}
        pointer = {'schema': 'tayvoriq-active-production-request-v1', 'state': 'ACTIVE',
                   'request_id': 'telegram-3401-trend-1', 'golden_path_run_id': 38249921806,
                   'allow_publish': False, 'allow_recovery': True, 'approval_key': 'telegram:valid',
                   'source_context_sha256': 'sources', 'contract_sha256': 'contract',
                   'telegram_message_id': 3401}
        request = {**pointer, 'status': 'DISPATCHED', 'source': 'telegram_trend_approval',
                   'approved_at': '2026-10-04T00:00:00Z'}
        self.req, self.ptr = quarantine(pointer, request, self.run, active_executors=0,
                                        now=datetime(2026, 10, 20, tzinfo=timezone.utc))

    def test_exact_expired_unpublished_request_is_history(self):
        self.assertTrue(health.is_retired_unpublished(self.ptr, self.req, 38249921806, self.run))

    def test_live_or_different_owner_keeps_incident(self):
        for name, value in (("state", "ACTIVE"), ("allow_publish", True),
                            ("allow_recovery", True), ("request_id", "other"),
                            ("golden_path_run_id", 9)):
            with self.subTest(name=name):
                self.assertFalse(health.is_retired_unpublished(
                    {**self.ptr, name: value}, self.req, 38249921806, self.run))
        self.assertFalse(health.is_retired_unpublished(self.ptr, self.req, 99, self.run))

    def test_review_upload_or_unverified_quarantine_never_suppressed(self):
        for key, value in (("production_completion", {"state": "REVIEW_READY"}),
                           ("stale_quarantine", {"reason": "other",
                                "review_delivered": False, "upload_permitted": False}),
                           ("status", "DISPATCHED"), ("youtube_video_id", "unexpected"),
                           ("review_url", "unexpected"), ("state_history", [{"state": "PUBLISHED"}])):
            with self.subTest(key=key):
                self.assertFalse(health.is_retired_unpublished(
                    self.ptr, {**self.req, key: value}, 38249921806, self.run))
        self.assertFalse(health.is_retired_unpublished(self.ptr, {
            **self.req, "stale_quarantine": {
                "reason": "STALE_NEWS_QUARANTINED_AFTER_FAILED_PRODUCTION_NO_REVIEW",
                "review_delivered": True, "upload_permitted": False,
            }}, 38249921806, self.run))

    def test_malformed_owner_id_returns_false_without_raising(self):
        self.assertFalse(health.is_retired_unpublished(
            {**self.ptr, "golden_path_run_id": "bad"},
            self.req, 38249921806, self.run))
        self.assertFalse(health.is_retired_unpublished(
            self.ptr, {**self.req, "golden_path_run_id": "bad"}, 38249921806, self.run))

    def test_internal_research_exhaustion_never_revives_archived_incident_or_telegram(self):
        for state in ('WAITING', 'EXHAUSTED'):
            with self.subTest(state=state):
                result = health.research_only_projection({
                    'state': state,
                    'reason': 'RESEARCH_RETRY_BUDGET_EXHAUSTED',
                }, retired=True, run_id=38249921806)
                self.assertEqual(result['overall'], 'yellow')
                self.assertEqual(result['self_heal_status'], state)
                self.assertIsNone(result['failure_state'])
                self.assertFalse(result['user_action_required'])
                self.assertFalse(result['telegram_notify_allowed'])

    def test_true_external_research_blocker_remains_user_visible(self):
        result = health.research_only_projection({
            'state': 'EXTERNAL_BLOCKER',
            'reason': 'PROVIDER_PAYMENT_OR_CONFIGURATION_BLOCKER',
        }, retired=True, run_id=38249921806)
        self.assertEqual(result['overall'], 'red')
        self.assertTrue(result['user_action_required'])
        self.assertTrue(result['telegram_notify_allowed'])

    def test_research_projection_does_not_override_active_production(self):
        self.assertIsNone(health.research_only_projection(
            {'state': 'EXHAUSTED'}, retired=False, run_id=38249921806))

    def test_postprocess_respects_no_telegram_policy(self):
        self.assertFalse(postprocess.telegram_notification_allowed({
            'notification_policy': {'telegram_notify_allowed': False}
        }))
        self.assertTrue(postprocess.telegram_notification_allowed({}))

    def test_workflow_has_last_line_defense_against_internal_telegram_noise(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/tayvoriq-ops-health.yml').read_text())
        step = next(s for s in workflow['jobs']['health']['steps']
                    if s.get('name') == 'Telegram health transition')
        self.assertIn("policy.get('telegram_notify_allowed') is False", step['run'])
        self.assertIn('[ -f /tmp/tayvoriq-ops-telegram.json ] || exit 0', step['run'])

    def test_full_health_snapshot_keeps_exhausted_research_internal(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            out = folder / 'ops-health.json'
            pointer = folder / 'pointer.json'
            output = folder / 'github-output'
            pointer.write_text(json.dumps(self.ptr), encoding='utf-8')

            def api_get(path):
                if str(path).endswith('/jobs?filter=latest&per_page=100'):
                    return {'jobs': [{'name': 'orchestrate', 'steps': [{
                        'name': 'Assert publishable production output', 'number': 40,
                        'status': 'completed', 'conclusion': 'failure'}]}]}
                return self.run

            old_out, old_pointer = health.OUT, health.ACTIVE_POINTER
            old_post_path = postprocess.PATH
            health.OUT, health.ACTIVE_POINTER = out, pointer
            postprocess.PATH = out
            try:
                env = {'GITHUB_OUTPUT': str(output),
                       'TAYVORIQ_OPS_STATE_PATH': str(out)}
                with patch.dict(os.environ, env), \
                     patch.object(health, 'load_current_request',
                                  return_value=(Path('requests/archived.json'), self.req)), \
                     patch.object(health, 'api_get', side_effect=api_get), \
                     patch.object(health, 'is_retired_unpublished', return_value=True), \
                     patch.object(health, 'current_research_retry', return_value={
                         'state': 'EXHAUSTED', 'attempts': 8,
                         'reason': 'RESEARCH_RETRY_BUDGET_EXHAUSTED'}):
                    self.assertEqual(health.main(), 0)
                state = json.loads(out.read_text(encoding='utf-8'))
                self.assertEqual(state['overall'], 'yellow')
                self.assertIsNone(state['incident'])
                self.assertFalse(state['user_action_required'])
                self.assertFalse(state['notification_policy']['telegram_notify_allowed'])
                self.assertIn('notify=false', output.read_text(encoding='utf-8'))

                post_output = folder / 'post-output'
                with patch.dict(os.environ, {'GITHUB_OUTPUT': str(post_output)}):
                    postprocess.main()
                self.assertIn('notify=false', post_output.read_text(encoding='utf-8'))
            finally:
                health.OUT, health.ACTIVE_POINTER = old_out, old_pointer
                postprocess.PATH = old_post_path


if __name__ == "__main__":
    unittest.main()
