import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_resolve_production_green_v1 as resolver


class ProductionGreenBindingTests(unittest.TestCase):
    def resolve_fixture(self, current_run, bound_run, weakened=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pointer = root / "green.json"
            pointer.write_text(json.dumps({"schema": resolver.EXPECTED_SCHEMA,
                "implementation_repository": resolver.EXPECTED_REPOSITORY,
                "implementation_sha": "b" * 40, "full_preflight_passed": True,
                "quality_gates_weakened": False}))
            (root / "exact.json").write_text(json.dumps({"request_id": "exact",
                "golden_path_run_id": bound_run, "codefix_recovery": {
                    "status": "REPLAY_DISPATCHED", "replay_run_id": bound_run,
                    "replay_implementation_sha": "a" * 40,
                    "active_pointer_verified": True, "quality_gates_weakened": weakened}}))
            with patch.object(resolver, "POINTER_PATH", pointer), patch.object(resolver, "REQUESTS_DIR", root), patch.dict(os.environ, {"SOURCE_REQUEST_ID_PIN": "exact", "GITHUB_RUN_ID": current_run}):
                return resolver.resolve()

    def test_dispatch_race_never_inherits_predecessor_code(self):
        result = self.resolve_fixture("124", 123)
        self.assertEqual(result["implementation_sha"], "b" * 40)
        self.assertEqual(result["binding_source"], "current-production-green")

    def test_exact_same_run_preserves_historical_verified_pin(self):
        self.assertEqual(self.resolve_fixture("123", 123)["implementation_sha"], "a" * 40)

    def test_exact_replay_still_rejects_weakened_integrity(self):
        with self.assertRaises(SystemExit):
            self.resolve_fixture("123", 123, weakened=True)

    def test_missing_run_identity_cannot_inherit_previous_pin(self):
        self.assertEqual(self.resolve_fixture("", 123)["implementation_sha"], "b" * 40)


if __name__ == "__main__":
    unittest.main()
