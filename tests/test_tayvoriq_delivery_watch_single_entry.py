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

        self.assertIn("for poll in $(seq 1 30)", workflow)
        self.assertIn("previous_golden_path_run_ids", workflow)
        self.assertIn("Give the binder a bounded window", workflow)


    def test_late_voice_failure_is_owned_only_by_delivery_watch(self):
        workflow = (ROOT / ".github/workflows/tayvoriq-deliver-video-now.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('state = "TRANSIENT_AUDIO_FAILURE"', workflow)
        self.assertIn("CODEFIX_FINALIZER_SKIPPED_LOCAL_VOICE_FAILURE", workflow)
        self.assertIn(
            "Delivery Watch exclusively owns bounded same-run voice/postmux retry.",
            workflow,
        )


    def test_local_checkpoint_retry_uses_new_green_when_verified_implementation_advanced(self):
        workflow = (ROOT / ".github/workflows/tayvoriq-delivery-watch.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Detect advanced Production Green for local checkpoint retry", workflow)
        self.assertIn("steps.local_green.outputs.advanced != 'true'", workflow)
        self.assertIn("Replay local checkpoint request on advanced Production Green", workflow)
        self.assertIn("SAME_GENERATION_VERIFIED_GREEN_LOCAL_REPLAY", workflow)
        self.assertIn("quality_gates_weakened':False", workflow)

    def test_delivery_watch_prefers_structured_failure_contract(self):
        workflow = (ROOT / ".github/workflows/tayvoriq-delivery-watch.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("failure-notification-policy.json", workflow)
        self.assertIn("/tmp/tayvoriq-structured-failure.json", workflow)
        self.assertIn("--structured-evidence /tmp/tayvoriq-structured-failure.json", workflow)
        self.assertIn("Raw Actions", workflow)

    def test_visual_failure_is_owned_by_delivery_watch_without_full_regeneration(self):
        workflow = (ROOT / ".github/workflows/tayvoriq-deliver-video-now.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('state = "LOCAL_VISUAL_REPAIR_REQUIRED"', workflow)
        self.assertIn("CODEFIX_FINALIZER_SKIPPED_LOCAL_VISUAL_FAILURE", workflow)
        self.assertIn('"full_regeneration_allowed": False if local_checkpoint else None', workflow)
        self.assertIn('"schema": "tayvoriq-failure-contract-v2"', workflow)


if __name__ == "__main__":
    unittest.main()
