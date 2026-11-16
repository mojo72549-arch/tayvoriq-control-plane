import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "followup", Path(__file__).resolve().parents[1] / "tools/tayvoriq_rejected_review_followup.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


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

    def test_repair_is_prepared_without_requesting_trends(self):
        self.write(self.decision_path, {**self.decision, "followup_action": "repair",
                                        "rejection_reason_code": "visuals"})
        plan = module.followup(self.root)
        self.assertEqual(plan["replacement_state"], "PREFLIGHT_REQUIRED")
        self.assertEqual(plan["repair_stage"], "VISUALS")
        self.assertFalse(plan["replacement_dispatch_allowed"])
        self.assertFalse(plan["new_trends_requested"])

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
