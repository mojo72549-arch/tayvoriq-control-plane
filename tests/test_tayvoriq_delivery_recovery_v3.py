import json
import tempfile
import unittest
from pathlib import Path

from tools import tayvoriq_delivery_recovery_v3 as recovery


class DeliveryRecoveryV3Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.requests = Path(self.tmp.name) / "requests"
        self.requests.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write_request(self, name, **overrides):
        data = {
            "request_id": name,
            "topic": f"Topic {name}",
            "trend_id": "2",
            "golden_path_run_id": 100,
            "retry_allowed": True,
            "recovery_generation": 0,
        }
        data.update(overrides)
        path = self.requests / f"{name}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_resolve_is_bound_to_exact_run_not_newest_other_run(self):
        self.write_request("approved-a", golden_path_run_id=100)
        self.write_request("unrelated-newer", golden_path_run_id=999)
        resolved = recovery.resolve(self.requests, 100)
        self.assertEqual(resolved["bound"], "true")
        self.assertEqual(resolved["request_id"], "approved-a")

    def test_prepare_increments_only_exact_bound_request(self):
        target = self.write_request("approved-a", golden_path_run_id=100, recovery_generation=1)
        other = self.write_request("unrelated-newer", golden_path_run_id=999, recovery_generation=3)
        prepared = recovery.prepare(self.requests, 100, 4)
        self.assertEqual(prepared["generation"], "2")
        self.assertEqual(self.read(target)["recovery_generation"], 2)
        self.assertEqual(self.read(other)["recovery_generation"], 3)
        self.assertIn(100, self.read(target)["golden_path_run_history"])

    def test_bind_new_moves_only_same_request_to_new_run(self):
        target = self.write_request("approved-a", golden_path_run_id=100)
        recovery.prepare(self.requests, 100, 4)
        recovery.bind_new(self.requests, "approved-a", 100, 101)
        data = self.read(target)
        self.assertEqual(data["golden_path_run_id"], 101)
        self.assertEqual(data["recovery_run_id"], 101)
        self.assertIn(100, data["golden_path_run_history"])
        self.assertEqual(recovery.resolve(self.requests, 101)["request_id"], "approved-a")

    def test_ambiguous_run_binding_fails_closed(self):
        self.write_request("a", golden_path_run_id=100)
        self.write_request("b", golden_path_run_id=100)
        with self.assertRaisesRegex(RuntimeError, "RECOVERY_BINDING_AMBIGUOUS"):
            recovery.resolve(self.requests, 100)

    def test_budget_exhaustion_fails_closed(self):
        self.write_request("approved-a", golden_path_run_id=100, recovery_generation=4)
        with self.assertRaisesRegex(RuntimeError, "RECOVERY_BUDGET_EXHAUSTED"):
            recovery.prepare(self.requests, 100, 4)


if __name__ == "__main__":
    unittest.main()
