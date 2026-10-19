"""Regression tests for canonical same-run Delivery Watch rebinding."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tayvoriq_recovery_rebind_v1 import RetryBindingError, main, rebind_same_run


class RecoveryRebindTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pointer = {
            "schema": "tayvoriq-active-production-request-v1",
            "state": "ACTIVE", "request_id": "telegram-3401-trend-1",
            "golden_path_run_id": 38249921806, "allow_recovery": True,
            "recovery_generation": 1, "approval_key": "telegram:selection:3401:trend:1",
            "source_context_sha256": "source-hash", "contract_sha256": "contract-hash",
            "telegram_message_id": 3401,
        }
        self.request = {
            "request_id": "telegram-3401-trend-1", "status": "DISPATCHED",
            "golden_path_run_id": 38249921806, "recovery_generation": 1,
            "source": "telegram_trend_approval", "approval_key": self.pointer["approval_key"],
            "source_context_sha256": "source-hash", "contract_sha256": "contract-hash",
            "telegram_message_id": 3401, "topic": "Cariad", "source_context": {"immutable": True},
            "state_history": [{"state": "APPROVED"}],
            "codefix_recovery": {"status": "AWAITING_CODEFIX", "failure_state": "LOCAL_VOICE_RETRY_REQUIRED"},
        }
        self.kw = {
            "request_id": "telegram-3401-trend-1", "run_id": 38249921806,
            "run_attempt": 1, "failure_state": "LOCAL_VOICE_RETRY_REQUIRED",
            "failure_signature": "sig-001", "at": "2026-10-19T17:00:00Z",
        }

    def bind(self, request=None, pointer=None, **changes):
        return rebind_same_run(
            request if request is not None else self.request,
            pointer if pointer is not None else self.pointer,
            **(self.kw | changes),
        )

    def test_bound_request_preserves_identity_sources_and_quality(self):
        original = copy.deepcopy(self.request)
        updated, changed = self.bind()
        self.assertTrue(changed)
        self.assertEqual(updated["source_context"], original["source_context"])
        self.assertEqual(updated["approval_key"], original["approval_key"])
        self.assertEqual(updated["topic"], "Cariad")
        self.assertEqual(updated["status"], "DISPATCHED")
        self.assertEqual(updated["codefix_recovery"]["local_retry_run_attempt"], 2)
        self.assertFalse(updated["codefix_recovery"]["quality_gates_weakened"])
        self.assertEqual(updated["recovery_owner"], "tayvoriq-delivery-watch")
        self.assertEqual(len(updated["state_history"]), 2)
        self.assertEqual(self.request, original)

    def test_rebind_idempotent_does_not_duplicate_history(self):
        updated, _ = self.bind()
        unchanged, changed = self.bind(request=updated)
        self.assertFalse(changed)
        self.assertEqual(unchanged, updated)

    def test_stale_pointer_and_request_are_refused(self):
        for field, value in (("request_id", "different"), ("golden_path_run_id", 99), ("state", "COMPLETED"), ("allow_recovery", False)):
            pointer = self.pointer | {field: value}
            with self.subTest(pointer=field), self.assertRaises(RetryBindingError):
                self.bind(pointer=pointer)
        with self.assertRaises(RetryBindingError):
            self.bind(request=self.request | {"status": "APPROVED"})

    def test_immutable_approval_contract_mismatch_is_refused(self):
        for key in ("approval_key", "source_context_sha256", "contract_sha256", "telegram_message_id"):
            with self.subTest(key=key), self.assertRaises(RetryBindingError):
                self.bind(request=self.request | {key: "altered"})
        with self.assertRaises(RetryBindingError):
            self.bind(request=self.request | {"source": "manual"})

    def test_generation_mismatch_and_retry_conflict_are_refused(self):
        with self.assertRaises(RetryBindingError):
            self.bind(pointer=self.pointer | {"recovery_generation": 0})
        updated, _ = self.bind()
        with self.assertRaisesRegex(RetryBindingError, "CONFLICTING_ATTEMPT"):
            self.bind(request=updated, failure_signature="different")
        older = copy.deepcopy(updated)
        older["codefix_recovery"]["local_retry_run_attempt"] = 4
        with self.assertRaisesRegex(RetryBindingError, "STALE_ATTEMPT"):
            self.bind(request=older, run_attempt=1)

    def test_next_run_attempt_can_be_rebound(self):
        updated, _ = self.bind()
        again, changed = self.bind(request=updated, run_attempt=2, failure_signature="sig-002")
        self.assertTrue(changed)
        self.assertEqual(again["codefix_recovery"]["local_retry_run_attempt"], 3)

    def test_cli_atomic_write_and_idempotency(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            request_path, pointer_path = path / "request.json", path / "pointer.json"
            request_path.write_text(json.dumps(self.request), encoding="utf-8")
            pointer_path.write_text(json.dumps(self.pointer), encoding="utf-8")
            argv = [
                "--request-file", str(request_path), "--active-pointer", str(pointer_path),
                "--request-id", self.kw["request_id"], "--run-id", str(self.kw["run_id"]),
                "--run-attempt", "1", "--failure-state", self.kw["failure_state"],
                "--failure-signature", self.kw["failure_signature"],
            ]
            self.assertEqual(main(argv), 0)
            first = request_path.read_bytes()
            self.assertEqual(main(argv), 0)
            self.assertEqual(request_path.read_bytes(), first)
            self.assertEqual(json.loads(pointer_path.read_text()), self.pointer)


if __name__ == "__main__":
    unittest.main()
