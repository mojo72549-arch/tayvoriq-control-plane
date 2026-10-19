"""Regression tests for safe stale-news retirement (never publication)."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tayvoriq_stale_news_reconcile_v1 import quarantine

NOW = datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)
APPROVED = (NOW - timedelta(days=15)).isoformat()
COMPLETED = (NOW - timedelta(days=7)).isoformat()


class StaleNewsSafetyTests(unittest.TestCase):
    def setUp(self):
        self.pointer = {
            "schema": "tayvoriq-active-production-request-v1", "state": "ACTIVE",
            "request_id": "telegram-3401-trend-1", "golden_path_run_id": 42,
            "approval_key": "telegram:valid:3401:trend:1",
            "source_context_sha256": "source-hash", "contract_sha256": "contract-hash",
            "telegram_message_id": 3401, "recovery_generation": 1,
            "allow_recovery": True, "allow_publish": False,
        }
        self.request = {
            "request_id": "telegram-3401-trend-1", "status": "DISPATCHED",
            "golden_path_run_id": 42, "approved_at": APPROVED,
            "source": "telegram_trend_approval", "recovery_generation": 1,
            "approval_key": self.pointer["approval_key"],
            "source_context_sha256": "source-hash", "contract_sha256": "contract-hash",
            "telegram_message_id": 3401,
            "topic": "VW-Cariad", "source_context": {"immutable": True},
            "state_history": [{"state": "APPROVED"}],
        }
        self.run = {"id": 42, "name": "TAYVORIQ-X Golden Path",
                    "status": "completed", "conclusion": "failure",
                    "updated_at": COMPLETED}

    def retire(self, pointer=None, request=None, run=None, executors=0):
        return quarantine(
            pointer if pointer is not None else self.pointer,
            request if request is not None else self.request,
            run if run is not None else self.run,
            active_executors=executors, now=NOW,
        )

    def test_expired_failed_run_releases_slot_with_immutable_sources(self):
        original_request = copy.deepcopy(self.request)
        pair = self.retire()
        self.assertIsNotNone(pair)
        new_request, new_pointer = pair
        self.assertEqual(new_pointer["state"], "EXPIRED")
        self.assertFalse(new_pointer["allow_recovery"])
        self.assertFalse(new_pointer["allow_publish"])
        self.assertEqual(new_request["status"], "EXPIRED")
        self.assertEqual(new_request["source_context"], self.request["source_context"])
        self.assertEqual(new_request["approval_key"], self.request["approval_key"])
        self.assertFalse(new_request["stale_quarantine"]["upload_permitted"])
        self.assertEqual(new_request["state_history"][-1]["state"], "EXPIRED")
        self.assertEqual(self.request, original_request)
        self.assertIsNone(self.retire(pointer=new_pointer, request=new_request))

    def test_never_expire_live_executor_or_recent_approval(self):
        self.assertIsNone(self.retire(executors=1))
        newer = self.request | {"approved_at": (NOW - timedelta(hours=1)).isoformat()}
        self.assertIsNone(self.retire(request=newer))
        recent_failure = self.run | {"updated_at": (NOW - timedelta(minutes=5)).isoformat()}
        self.assertIsNone(self.retire(run=recent_failure))

    def test_never_expire_success_review_or_publication(self):
        for state, conclusion in (("queued", None), ("in_progress", None),
                                  ("completed", "success"), ("completed", "cancelled")):
            with self.subTest(state=state):
                self.assertIsNone(self.retire(run=self.run | {"status": state, "conclusion": conclusion}))
        for key, value in (("production_completion", {"state": "REVIEW_READY"}),
                           ("youtube_video_id", "abc123"),
                           ("review_url", "https://example.invalid/review"),
                           ("delivery_receipt", {"sent": True}),
                           ("state_history", [{"state": "REVIEW_READY"}])):
            with self.subTest(key=key):
                self.assertIsNone(self.retire(request=self.request | {key: value}))

    def test_wrong_request_source_hash_message_generation_are_rejected(self):
        for key, value in (
            ("request_id", "different"), ("source_context_sha256", "other"),
            ("contract_sha256", "other"), ("telegram_message_id", 999),
            ("recovery_generation", 0), ("golden_path_run_id", 7),
            ("source", "manual"), ("status", "APPROVED"),
        ):
            with self.subTest(field=key):
                self.assertIsNone(self.retire(request=self.request | {key: value}))
        self.assertIsNone(self.retire(pointer=self.pointer | {"allow_publish": True}))
        self.assertIsNone(self.retire(pointer=self.pointer | {"allow_recovery": False}))
        self.assertIsNone(self.retire(pointer=self.pointer | {"state": "EXPIRED"}))


if __name__ == "__main__":
    unittest.main()
