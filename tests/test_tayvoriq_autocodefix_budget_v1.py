import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_autocodefix_budget_v1 as budget


class CodefixBudgetTests(unittest.TestCase):
    def test_same_evidence_is_admitted_once_despite_builder_restart(self):
        request = {"request_id": "telegram-2699-trend-1", "source_context_sha256": "source",
                   "contract_sha256": "contract", "codefix_recovery": {
                       "status": "ARMED", "failed_run_id": 123, "failure_signature": "voice"}}
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp)
            first = budget.reserve(request, "a" * 40, ledger, "1")
            self.assertTrue(first["admitted"])
            snapshot = Path(first["ledger_path"]).read_bytes()
            repeated = copy.deepcopy(request)
            repeated["state_history"] = ["status-only update"]
            self.assertFalse(budget.reserve(repeated, "a" * 40, ledger, "2")["admitted"])
            self.assertEqual(Path(first["ledger_path"]).read_bytes(), snapshot)
            self.assertTrue(budget.reserve(request, "b" * 40, ledger, "3")["admitted"])
            self.assertEqual(json.loads(snapshot)["max_provider_attempts"], 3)

    def test_incomplete_or_unarmed_identity_never_reserves(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                budget.reserve({}, "a" * 40, Path(tmp), "1")
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
