"""Archived news must not be misreported as a live incident."""
import importlib.util
import unittest
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "scripts" / "tayvoriq_ops_health.py"
spec = importlib.util.spec_from_file_location("tayvoriq_health_archived_test", FILE)
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


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


if __name__ == "__main__":
    unittest.main()
