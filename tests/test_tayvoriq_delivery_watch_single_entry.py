from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeliveryWatchSingleEntryContractTests(unittest.TestCase):
    def test_request_pin_does_not_dispatch_a_duplicate_delivery_watch(self):
        workflow = (ROOT / ".github/workflows/tayvoriq-request-pin-autorepair.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("gh workflow run tayvoriq-delivery-watch.yml", workflow)
        self.assertIn("PIN_AUTOREPAIR_OWNER_BOUND_FOR_CANONICAL_DELIVERY_WATCH", workflow)

    def test_canonical_delivery_watch_waits_for_exact_owner_binding(self):
        workflow = (ROOT / ".github/workflows/tayvoriq-delivery-watch.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("for poll in $(seq 1 20)", workflow)
        self.assertIn("previous_golden_path_run_ids", workflow)
        self.assertIn("Give the binder a bounded window", workflow)


if __name__ == "__main__":
    unittest.main()
