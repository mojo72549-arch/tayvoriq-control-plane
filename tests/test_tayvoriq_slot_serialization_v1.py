from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tayvoriq_slot_serialization_v1 as gate


def request(selection_id: str, request_id: str, approved_at: str, run_id: int = 0, source: str = "telegram_trend_approval") -> dict:
    data = {
        "request_id": request_id,
        "status": "APPROVED",
        "source": source,
        "selection_id": selection_id,
        "approved_at": approved_at,
        "state_history": [{"state": "APPROVED", "at": approved_at, "actor": "test"}],
    }
    if run_id:
        data["golden_path_run_id"] = run_id
    return data


class SlotSerializationTests(unittest.TestCase):
    def test_morning_request_never_waits_on_evening_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "morning.json"
            p.write_text(json.dumps(request("20260822-m-topic", "m1", "2026-08-22T06:00:00Z")), encoding="utf-8")
            result = gate.check_request(p, root, "", "")
            self.assertTrue(result["released"])
            self.assertFalse(result["requires_serialization"])

    def test_evening_is_fail_closed_without_morning_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "evening.json"
            p.write_text(json.dumps(request("20260822-e-topic", "e1", "2026-08-22T17:00:00Z")), encoding="utf-8")
            result = gate.check_request(p, root, "repo", "token")
            self.assertFalse(result["released"])
            self.assertEqual(result["reason"], "MORNING_REQUEST_MISSING")

    def test_preapproved_preparation_is_valid_same_day_morning_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = root / "morning.json"
            evening = root / "evening.json"
            morning.write_text(json.dumps(request(
                "20260824-m-ai-courts", "m1", "2026-08-23T20:28:00Z", 123,
                source="user_preapproved_preparation",
            )), encoding="utf-8")
            evening.write_text(json.dumps(request(
                "20260824-e-vw-crisis", "e1", "2026-08-23T20:29:00Z",
                source="user_preapproved_preparation",
            )), encoding="utf-8")
            predecessor = gate.find_same_day_morning(json.loads(evening.read_text(encoding="utf-8")), root)
            self.assertIsNotNone(predecessor)
            self.assertEqual(predecessor[1]["request_id"], "m1")

    def test_unapproved_source_is_not_accepted_as_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            morning = root / "morning.json"
            evening = root / "evening.json"
            morning.write_text(json.dumps(request(
                "20260824-m-ai-courts", "m1", "2026-08-23T20:28:00Z", 123,
                source="draft_only",
            )), encoding="utf-8")
            evening.write_text(json.dumps(request(
                "20260824-e-vw-crisis", "e1", "2026-08-23T20:29:00Z",
                source="user_preapproved_preparation",
            )), encoding="utf-8")
            predecessor = gate.find_same_day_morning(json.loads(evening.read_text(encoding="utf-8")), root)
            self.assertIsNone(predecessor)

    def test_evening_is_held_while_morning_run_is_not_completed(self) -> None:
        run = {"status": "in_progress", "conclusion": None}
        released, reason, _ = gate.evaluate_live_state(run, {"jobs": []})
        self.assertFalse(released)
        self.assertEqual(reason, "MORNING_RUN_NOT_COMPLETED")

    def test_evening_is_held_after_failed_morning(self) -> None:
        run = {"status": "completed", "conclusion": "failure"}
        released, reason, _ = gate.evaluate_live_state(run, {"jobs": []})
        self.assertFalse(released)
        self.assertEqual(reason, "MORNING_RUN_FAILURE")

    def test_successful_run_without_final_review_is_still_held(self) -> None:
        run = {"status": "completed", "conclusion": "success"}
        jobs = {"jobs": [{"name": "orchestrate", "steps": [
            {"name": "Assert publishable production output", "conclusion": "success"},
            {"name": "Validate publication quality", "conclusion": "success"},
            {"name": "Publish review page", "conclusion": "success"},
            {"name": "Send Telegram review", "conclusion": "failure"},
        ]}]}
        released, reason, _ = gate.evaluate_live_state(run, jobs)
        self.assertFalse(released)
        self.assertEqual(reason, "MORNING_FINAL_REVIEW_NOT_VERIFIED")

    def test_evening_releases_only_after_all_final_steps_succeed(self) -> None:
        run = {"status": "completed", "conclusion": "success"}
        jobs = {"jobs": [{"name": "orchestrate", "steps": [
            {"name": name, "conclusion": "success"} for name in gate.REQUIRED_FINAL_STEPS
        ]}]}
        released, reason, steps = gate.evaluate_live_state(run, jobs)
        self.assertTrue(released)
        self.assertEqual(reason, "MORNING_FINAL_REVIEW_VERIFIED")
        self.assertEqual(set(steps), set(gate.REQUIRED_FINAL_STEPS))

    def test_hold_and_release_preserve_request_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "request.json"
            p.write_text(json.dumps(request("20260822-e-topic", "e1", "2026-08-22T17:00:00Z")), encoding="utf-8")
            held = {"predecessor_request_id": "m1", "predecessor_run_id": 123, "reason": "MORNING_RUN_NOT_COMPLETED"}
            self.assertTrue(gate.mark_held(p, held))
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "APPROVED")
            self.assertEqual(data["slot_serialization_state"], gate.HELD_STATE)
            released = {"predecessor_request_id": "m1", "predecessor_run_id": 124, "reason": "MORNING_FINAL_REVIEW_VERIFIED"}
            self.assertTrue(gate.mark_released(p, released))
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "APPROVED")
            self.assertEqual(data["slot_serialization_state"], gate.RELEASED_STATE)


if __name__ == "__main__":
    unittest.main()
