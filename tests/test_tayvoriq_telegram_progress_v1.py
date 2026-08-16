from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_telegram_progress_v1 as progress


class TelegramProgressUnitTests(unittest.TestCase):
    def test_milestones_are_strictly_increasing_and_meaningful(self) -> None:
        names = ("sources_locked", "production_active", "master_ready", "quality_passed")
        percentages = [progress.MILESTONES[name].percent for name in names]
        self.assertEqual(percentages, [20, 45, 75, 90])
        self.assertEqual(percentages, sorted(set(percentages)))

    def test_payload_is_clear_and_requires_no_action(self) -> None:
        payload = progress.build_payload(
            "master_ready",
            "Wenn die Erde plötzlich bricht",
            "31999999999",
            "12345",
        )
        text = payload["text"]
        self.assertIn("TAYVORIQ 75 %", text)
        self.assertIn("Wenn die Erde plötzlich bricht", text)
        self.assertIn("Videomaster", text)
        self.assertIn("Keine Aktion nötig", text)
        self.assertNotIn("fehlgeschlagen", text.casefold())

    def test_recovery_payload_explains_safe_stop_and_restart(self) -> None:
        payload = progress.build_payload(
            "recovery_started",
            "Wenn die Erde plötzlich bricht",
            "31966058297",
            "12345",
        )
        text = payload["text"]
        self.assertIn("Sichere Reparatur gestartet", text)
        self.assertIn("nichts veröffentlicht", text)
        self.assertIn("neu gestartet", text)
        self.assertIn("Keine Aktion nötig", text)

    def test_policy_controls_progress_and_same_run_reruns_are_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps({"production_progress_enabled": True}), encoding="utf-8")
            self.assertTrue(progress.should_send(path, 1))
            self.assertFalse(progress.should_send(path, 2))
            path.write_text(json.dumps({"production_progress_enabled": False}), encoding="utf-8")
            self.assertFalse(progress.should_send(path, 1))


class TelegramProgressWorkflowTests(unittest.TestCase):
    def test_golden_path_wires_each_verified_milestone_once(self) -> None:
        workflow = (ROOT / ".github/workflows/tayvoriq-deliver-video-now.yml").read_text(encoding="utf-8")
        for stage in ("sources_locked", "production_active", "master_ready", "quality_passed"):
            self.assertEqual(workflow.count(f"--stage {stage}"), 1)
        self.assertGreaterEqual(workflow.count("continue-on-error: true"), 4)
        self.assertIn(
            'if [ "${GITHUB_EVENT_NAME}" != "push" ]; then',
            workflow,
        )
        self.assertIn(
            "Verified production-start Telegram is owned by the request dispatcher.",
            workflow,
        )

    def test_dispatcher_promises_real_milestones_not_silence(self) -> None:
        workflow = (ROOT / ".github/workflows/tayvoriq-request-dispatch.yml").read_text(encoding="utf-8")
        self.assertIn("TAYVORIQ 10 % · Produktion gestartet", workflow)
        self.assertIn("Fakten gesichert", workflow)
        self.assertIn("Videomaster erstellt", workflow)
        self.assertIn("Quality-Gates bestanden", workflow)
        self.assertNotIn("Nächste Nachricht erst beim fertigen Video-Review", workflow)

    def test_on_demand_status_bridge_is_bound_to_one_trigger_file(self) -> None:
        workflow = (
            ROOT / ".github/workflows/tayvoriq-telegram-status-bridge-v1.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('.github/run-now/tayvoriq-progress-trigger.json', workflow)
        self.assertIn('STATUS_STAGE_INVALID', workflow)
        self.assertIn('Send and verify Telegram status', workflow)

    def test_checked_in_policy_is_enabled_until_user_opt_out(self) -> None:
        policy = json.loads(
            (ROOT / "state/tayvoriq-notification-policy.json").read_text(encoding="utf-8")
        )
        self.assertIs(policy["production_progress_enabled"], True)
        self.assertIs(policy["notify_only_on_real_state_change"], True)
        self.assertIs(policy["enabled_until_user_opt_out"], True)


if __name__ == "__main__":
    unittest.main()
