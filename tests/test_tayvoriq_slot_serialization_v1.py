from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
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
    def test_current_long_slot_names_cannot_bypass_gate(self) -> None:
        for slot, expected in (("morning", "m"), ("evening", "e"), ("m", "m"), ("e", "e")):
            self.assertEqual(gate.selection_parts({"selection_id": f"20260926-{slot}-agentv2-r3"}), ("20260926", expected))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "evening.json"
            p.write_text(json.dumps(request("20260926-evening-agentv2-r3", "e1", "2026-09-26T17:00:00Z")))
            self.assertFalse(gate.check_request(p, root, "repo", "token")["released"])

    def test_active_owner_blocks_every_new_slot_before_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "requests"
            root.mkdir()
            pointer = Path(tmp) / ".github/state/tayvoriq-active-production-request.json"
            pointer.parent.mkdir(parents=True)
            pointer.write_text(json.dumps({"schema": "tayvoriq-active-production-request-v1", "state": "ACTIVE", "request_id": "old", "golden_path_run_id": 123}))
            p = root / "next.json"
            p.write_text(json.dumps(request("20260926-morning-agentv2-r3", "next", "2026-09-26T06:00:00Z")))
            jobs = {"jobs": [{"name": "orchestrate", "steps": [{"name": n, "conclusion": "success"} for n in gate.REQUIRED_FINAL_STEPS]}]}
            for owner_state in ("ACTIVE", "COMPLETED"):
                pointer.write_text(json.dumps({"schema": "tayvoriq-active-production-request-v1", "state": owner_state, "request_id": "old", "golden_path_run_id": 123}))
                for status, conclusion, expected in (("in_progress", None, False), ("completed", "failure", False), ("completed", "success", True)):
                    with patch.object(gate, "github_json", side_effect=[{"status": status, "conclusion": conclusion}, jobs]):
                        self.assertEqual(gate.check_request(p, root, "repo", "token")["released"], expected)
            with patch.object(gate, "github_json", side_effect=[{"status": "completed", "conclusion": "success"}, {"jobs": []}]):
                self.assertFalse(gate.check_request(p, root, "repo", "token")["released"])
            with patch.object(gate, "github_json", side_effect=RuntimeError("unavailable")):
                result = gate.check_request(p, root, "repo", "token")
                self.assertFalse(result["released"])
            gate.mark_held(p, result)
            self.assertEqual(gate.held_candidates(root), [p])
            self.assertEqual(json.loads(p.read_text())["status"], "APPROVED")
            pointer.write_text(json.dumps({"schema": "tayvoriq-active-production-request-v1", "state": "UNKNOWN"}))
            self.assertEqual(gate.check_request(p, root, "repo", "token")["reason"], "ACTIVE_OWNER_POINTER_INVALID")
            pointer.write_text("broken json")
            self.assertEqual(gate.check_request(p, root, "repo", "token")["reason"], "ACTIVE_OWNER_POINTER_INVALID")

    def test_same_request_recovery_does_not_query_other_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "requests"
            root.mkdir()
            pointer = Path(tmp) / ".github/state/tayvoriq-active-production-request.json"
            pointer.parent.mkdir(parents=True)
            pointer.write_text(json.dumps({"schema": "tayvoriq-active-production-request-v1", "state": "ACTIVE", "request_id": "same", "golden_path_run_id": 123}))
            p = root / "same.json"
            p.write_text(json.dumps(request("20260926-evening-agentv2-r3", "same", "2026-09-26T06:00:00Z")))
            with patch.object(gate, "github_json") as api:
                self.assertTrue(gate.check_request(p, root, "repo", "token")["released"])
                api.assert_not_called()

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

    def test_explicit_evening_without_morning_requires_verified_completed_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "requests"
            root.mkdir()
            pointer = Path(tmp) / ".github/state/tayvoriq-active-production-request.json"
            pointer.parent.mkdir(parents=True)
            evening = root / "evening.json"
            evening.write_text(json.dumps(request(
                "20260926-evening-agentv2-r1", "telegram-2867-trend-5", "2026-09-26T15:09:05Z"
            )), encoding="utf-8")
            jobs = {"jobs": [{"name": "orchestrate", "steps": [
                {"name": name, "conclusion": "success"} for name in gate.REQUIRED_FINAL_STEPS
            ]}]}
            for owner_state, expected in (("ACTIVE", False), ("COMPLETED", True)):
                pointer.write_text(json.dumps({
                    "schema": "tayvoriq-active-production-request-v1", "state": owner_state,
                    "request_id": "telegram-2699-trend-1", "golden_path_run_id": 36243464769,
                }))
                with patch.object(gate, "github_json", side_effect=[
                    {"status": "completed", "conclusion": "success"}, jobs,
                ]):
                    result = gate.check_request(evening, root, "repo", "token")
                self.assertEqual(result["released"], expected)
            self.assertEqual(result["reason"], "EXPLICIT_EVENING_APPROVAL_AFTER_COMPLETED_OWNER")
            self.assertEqual(result["predecessor_run_id"], 36243464769)
            self.assertEqual(set(result["verified_final_steps"]), set(gate.REQUIRED_FINAL_STEPS))
            data = json.loads(evening.read_text(encoding="utf-8"))
            data["source"] = "user_preapproved_preparation"
            evening.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(gate, "github_json", side_effect=[
                {"status": "completed", "conclusion": "success"}, jobs,
            ]):
                self.assertEqual(gate.check_request(evening, root, "repo", "token")["reason"], "MORNING_REQUEST_MISSING")

    def test_failed_preflight_admits_only_exact_editorial_source_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "requests"
            root.mkdir()
            pointer = Path(tmp) / ".github/state/tayvoriq-active-production-request.json"
            pointer.parent.mkdir(parents=True)
            original = request("20260926-evening-agentv2-r1", "old", "2026-09-26T15:09:05Z", 123)
            original.update(status="DISPATCHED", approval_key="telegram:selection:2867:trend:5",
                            trend_id="5", topic="Brain study", telegram_message_id=2867,
                            source_context={"sources": ["one", "two"], "fallback_editorial_answers": {"what_happened": "long"}})
            (root / "old.json").write_text(json.dumps(original))
            repaired = dict(original)
            repaired.update(request_id="old-source-repair-v1", status="APPROVED",
                            source="telegram_trend_approval_source_repair",
                            repair_of_request_id="old",
                            approval_key="telegram:selection:2867:trend:5:source-repair-v1",
                            source_context={"sources": ["one", "two"], "fallback_editorial_answers": {"what_happened": "precise"}})
            path = root / "repaired.json"
            path.write_text(json.dumps(repaired))
            pointer.write_text(json.dumps({"schema": "tayvoriq-active-production-request-v1",
                                           "state": "ACTIVE", "request_id": "old", "golden_path_run_id": 123}))
            jobs = {"jobs": [{"name": "orchestrate", "steps": [
                {"name": "Lightweight contract preflight", "conclusion": "failure"}]}]}
            def check(run_status="completed", conclusion="failure"):
                with patch.object(gate, "github_json", side_effect=[
                    {"status": run_status, "conclusion": conclusion}, jobs,
                ]):
                    return gate.check_request(path, root, "repo", "token")
            self.assertEqual(check()["reason"], "VERIFIED_EDITORIAL_SOURCE_REPAIR_AFTER_FAILED_PREFLIGHT")
            self.assertTrue(check()["released"])
            self.assertFalse(check("in_progress", None)["released"])
            tampered = dict(repaired)
            tampered["source_context"] = {"sources": ["different"], "fallback_editorial_answers": {"what_happened": "precise"}}
            path.write_text(json.dumps(tampered))
            self.assertFalse(check()["released"])

    def test_failed_publishability_admits_cta_repair_with_unchanged_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "requests"
            root.mkdir()
            pointer = Path(tmp) / ".github/state/tayvoriq-active-production-request.json"
            pointer.parent.mkdir(parents=True)
            old = request("20260926-evening-agentv2-r1", "source-repair", "2026-09-26T15:09:05Z", 124)
            old.update(status="DISPATCHED", approval_key="telegram:selection:2867:trend:5:source-repair-v1",
                       trend_id="5", topic="Brain study", telegram_message_id=2867,
                       cta_text="TAYVORIQ prüft die nächsten Studien.",
                       source_context={"sources": ["same", "evidence"]}, source_context_sha256="original")
            (root / "source-repair.json").write_text(json.dumps(old))
            new = dict(old)
            new.update(request_id="source-repair-content-repair-v1", status="APPROVED",
                       source="telegram_trend_approval_content_repair", repair_of_request_id="source-repair",
                       approval_key=old["approval_key"] + ":content-repair-v1",
                       cta_text="Folge TAYVORIQ: Wir prüfen die nächsten Studien.")
            path = root / "cta-repair.json"
            path.write_text(json.dumps(new))
            pointer.write_text(json.dumps({"schema": "tayvoriq-active-production-request-v1",
                                           "state": "ACTIVE", "request_id": "source-repair", "golden_path_run_id": 124}))
            jobs = {"jobs": [{"name": "orchestrate", "steps": [
                {"name": "Assert publishable production output", "conclusion": "failure"}]}]}
            def check():
                with patch.object(gate, "github_json", side_effect=[
                    {"status": "completed", "conclusion": "failure"}, jobs,
                ]):
                    return gate.check_request(path, root, "repo", "token")
            self.assertEqual(check()["reason"], "VERIFIED_CTA_CONTENT_REPAIR_AFTER_FAILED_PUBLISHABILITY")
            new["source_context"] = {"sources": ["changed"]}
            path.write_text(json.dumps(new))
            self.assertFalse(check()["released"])

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
