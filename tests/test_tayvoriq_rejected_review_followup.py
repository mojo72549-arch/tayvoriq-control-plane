import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "followup", Path(__file__).resolve().parents[1] / "tools/tayvoriq_rejected_review_followup.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_rejected_review_repair as repair


class RejectedReviewFollowupTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.write(module.POINTER, {
            "schema": "tayvoriq-active-production-request-v1", "state": "COMPLETED",
            "request_id": "request-1", "golden_path_run_id": 123, "selection_id": "week-evening-a",
            "source_context_sha256": "fixture",
        })
        self.write("requests/request-1.json", {
            "request_id": "request-1", "golden_path_run_id": 123, "source_context_sha256": "fixture",
            "production_completion": {"state": "REVIEW_READY", "golden_path_run_id": 123,
                                      "telegram_message_id": 44, "quality_gates_weakened": False},
        })
        self.decision = {
            "schema": "tayvoriq-artifact-approval", "state": "REJECTED", "request_id": "request-1",
            "review_id": "123", "telegram_message_id": 44, "source_context_sha256": "fixture",
            "rejection_reason": "Genuine footage required",
        }
        self.decision_path = f"{module.DECISIONS}/123.json"

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_auto_and_legacy_repair_start_new_trends_without_a_verified_repair(self):
        for action in ("auto", "repair"):
            self.write(self.decision_path, {**self.decision, "followup_action": action,
                                            "rejection_reason_code": "visuals"})
            plan = module.followup(self.root)
            self.assertEqual(plan["requested_action"], action)
            self.assertEqual(plan["route_reason"], "NO_VERIFIED_REPAIR")
            self.assertFalse(plan["replacement_dispatch_allowed"])
            self.assertTrue(plan["new_trends_requested"])

    def test_new_trends_require_an_explicit_choice_and_a_reason(self):
        self.write(self.decision_path, self.decision)
        self.assertFalse(module.followup(self.root)["new_trends_requested"])
        self.write(self.decision_path, {**self.decision, "followup_action": "new_trends", "rejection_reason": ""})
        self.assertFalse(module.followup(self.root)["new_trends_requested"])
        self.write(self.decision_path, {**self.decision, "followup_action": "new_trends"})
        plan = module.followup(self.root)
        self.assertTrue(plan["new_trends_requested"])
        self.assertFalse(plan["selection_delivered"])
        selection = plan["selection_id"]
        self.write(f"{module.DELIVERIES}/{selection}.json", {
            "selection_id": selection, "telegram_delivery_verified": True, "telegram_message_id": 55,
        })
        self.assertTrue(module.followup(self.root)["selection_delivered"])

    def test_other_review_or_approval_cannot_trigger_followup(self):
        self.assertIsNone(module.followup(self.root))
        for overrides in ({"state": "APPROVED"}, {"telegram_message_id": 45},
                          {"source_context_sha256": "another"}, {"request_id": "request-2"}):
            self.write(self.decision_path, {**self.decision, **overrides})
            self.assertIsNone(module.followup(self.root))

    def test_scoped_repair_requires_checkpoint_and_falls_back_on_failed_run(self):
        request_path = self.root / "requests/request-1.json"
        request = json.loads(request_path.read_text())
        receipt = request["production_completion"]
        receipt["review_repair_checkpoint"] = "tayvoriq-review-v1-fixture-123-2"
        self.write("requests/request-1.json", request)
        self.write(self.decision_path, {**self.decision, "followup_action": "auto",
                                        "rejection_reason_code": "voice"})
        plan = module.followup(self.root)
        self.assertEqual(plan["repair_stage"], "VOICE")
        self.assertEqual(plan["replacement_state"], "PREFLIGHT_REQUIRED")
        self.assertTrue(plan["replacement_dispatch_allowed"])
        self.assertFalse(plan["new_trends_requested"])
        execution = {"request_id": "request-1", "rejected_run_id": 123,
                     "source_context_sha256": "fixture", "run_id": 124, "state": "RUNNING"}
        path = f"{module.REPAIRS}/123.json"
        self.write(path, execution)
        self.assertEqual(module.followup(self.root)["replacement_state"], "REPAIR_RUNNING")
        self.write(path, {**execution, "state": "FAILED"})
        plan = module.followup(self.root)
        self.assertTrue(plan["new_trends_requested"])
        self.assertEqual(plan["route_reason"], "REPAIR_FAILED")
        self.assertFalse(plan["replacement_dispatch_allowed"])

    def test_repaired_review_does_not_loop_and_editorial_rejection_does_not_render(self):
        request_path = self.root / "requests/request-1.json"
        request = json.loads(request_path.read_text())
        request["production_completion"]["review_repair_checkpoint"] = "tayvoriq-review-v1-fixture-123-1"
        for repaired, reason in ((34, "visuals"), (None, "content")):
            self.write("requests/request-1.json", {**request, "repaired_review_run_id": repaired})
            self.write(self.decision_path, {**self.decision, "followup_action": "auto",
                                            "rejection_reason_code": reason})
            self.assertTrue(module.followup(self.root)["new_trends_requested"])

    def test_orchestrator_dispatches_once_and_releases_slot_on_missing_review(self):
        request = json.loads((self.root / "requests/request-1.json").read_text())
        request["trend_id"] = "1"
        request["production_completion"]["review_repair_checkpoint"] = "tayvoriq-review-v1-fixture-123-1"
        self.write("requests/request-1.json", request)
        self.write(self.decision_path, {**self.decision, "followup_action": "auto",
                                        "rejection_reason_code": "visuals"})
        run = {"id": 124, "display_title": "TAYVORIQ review correction 123", "event": "workflow_dispatch",
               "head_branch": "main", "status": "in_progress"}
        dispatches = []

        def checked(*args):
            if args[:2] == ("gh", "workflow"):
                dispatches.append(args)
            if args[:2] == ("gh", "api"):
                return json.dumps({"workflow_runs": [run] if dispatches else []})
            return ""

        output = self.root / "workflow-output"
        old_cwd = Path.cwd()
        self.addCleanup(os.chdir, old_cwd)
        os.chdir(self.root)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "fixture/repo", "GITHUB_OUTPUT": str(output)}), \
                patch.object(repair, "publish", side_effect=lambda path, value: self.write(path, value)), \
                patch.object(repair, "checked", side_effect=checked):
            repair.reconcile()
            self.assertEqual(repair.guard(123, 124, "request-1")["repair_stage"], "VISUALS")
            with self.assertRaises(ValueError):
                repair.guard(123, 125, "request-1")
            repair.reconcile()
            self.assertEqual(len(dispatches), 1)
            run["status"] = "completed"
            repair.reconcile()
        self.assertEqual(output.read_text(), "failed_review=123\n")
        self.assertTrue(module.followup(self.root)["new_trends_requested"])
