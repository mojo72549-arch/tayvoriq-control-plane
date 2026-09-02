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
        names = ("sources_locked", "production_active", "checkpoint_repair", "master_ready", "quality_passed", "review_ready")
        percentages = [progress.MILESTONES[name].percent for name in names]
        self.assertEqual(percentages, [20, 45, 75, 85, 95, 100])
        self.assertEqual(percentages, sorted(set(percentages)))

    def test_payload_is_clear_and_requires_no_action(self) -> None:
        payload = progress.build_payload(
            "master_ready",
            "Wenn die Erde plötzlich bricht",
            "31999999999",
            "12345",
        )
        text = payload["text"]
        self.assertIn("TAYVORIQ 85 %", text)
        self.assertIn("Wenn die Erde plötzlich bricht", text)
        self.assertIn("Finaler Videomaster verifiziert", text)
        self.assertIn("publishbarer Kandidat", text)
        self.assertIn("Keine Aktion nötig", text)
        self.assertNotIn("fehlgeschlagen", text.casefold())

    def test_recovery_payload_explains_durable_takeover(self) -> None:
        payload = progress.build_payload(
            "recovery_started",
            "Wenn die Erde plötzlich bricht",
            "31966058297",
            "12345",
        )
        text = payload["text"]
        self.assertIn("TAYVORIQ 60 %", text)
        self.assertIn("Recovery übernommen", text)
        self.assertIn("neuen Recovery-Lauf gebunden", text)
        self.assertIn("Keine Aktion nötig", text)

    def test_render_heartbeat_reports_elapsed_time_without_fake_advancement(self) -> None:
        payload = progress.build_payload(
            "render_heartbeat",
            "Wenn die Erde plötzlich bricht",
            "31968359576",
            "12345",
            elapsed_minutes=45,
        )
        text = payload["text"]
        self.assertIn("TAYVORIQ 45 %", text)
        self.assertIn("seit: 45 Minuten", text)
        self.assertIn("weiterhin aktiv", text)
        self.assertNotIn("85 %", text)

    def test_eighteen_minutes_is_normal_runtime_not_a_watchdog_warning(self) -> None:
        payload = progress.build_payload(
            "render_heartbeat",
            "Wenn die Erde plötzlich bricht",
            "31968359576",
            "12345",
            elapsed_minutes=18,
        )
        text = payload["text"]
        self.assertNotIn("dauert länger", text)
        self.assertNotIn("Watchdog", text)
        self.assertNotIn("85 %", text)

    def test_heartbeat_schedule_suppresses_three_minute_operator_spam(self) -> None:
        for minute in (3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42):
            self.assertFalse(progress.heartbeat_due("render_heartbeat", minute))
        self.assertTrue(progress.heartbeat_due("render_heartbeat", 45))
        self.assertTrue(progress.heartbeat_due("master_ready", 24))

    def test_audio_stop_is_immediate_truthful_and_says_nothing_was_published(self) -> None:
        payload = progress.build_payload(
            "audio_recovery",
            "Wenn die Erde plötzlich bricht",
            "31968359576",
            "12345",
            failure_state="TRANSIENT_AUDIO_FAILURE",
        )
        text = payload["text"]
        self.assertIn("Audio-Gate", text)
        self.assertIn("TRANSIENT_AUDIO_FAILURE", text)
        self.assertIn("nichts veröffentlicht", text)
        self.assertIn("Dublettenprüfung bleiben gültig", text)

    def test_checkpoint_repair_is_explicitly_not_a_final_master(self) -> None:
        payload = progress.build_payload(
            "checkpoint_heartbeat",
            "Wenn die Erde plötzlich bricht",
            "31970469274",
            "12345",
            elapsed_minutes=18,
        )
        text = payload["text"]
        self.assertIn("TAYVORIQ 75 %", text)
        self.assertIn("Render-Zwischenstand und Quellen bleiben gesichert", text)
        self.assertIn("finaler Master ist noch nicht bestätigt", text)
        self.assertIn("Qualitätsreparatur aktiv seit: 18 Minuten", text)
        self.assertNotIn("85 %", text)
        self.assertNotIn("Master gesichert", text)

    def test_duplicate_stop_requires_a_new_angle_and_never_claims_publication(self) -> None:
        payload = progress.build_payload(
            "duplicate_blocked",
            "Dasselbe Thema anders formuliert",
            "31968359999",
            "12345",
            detail="Ähnlich zu einer früheren Folge",
        )
        text = payload["text"]
        self.assertIn("Dublette verhindert", text)
        self.assertIn("vor Render und Upload blockiert", text)
        self.assertIn("Neuer Themenwinkel", text)

    def test_policy_suppresses_replays_and_intermediate_liveness_polls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps({"production_progress_enabled": True}), encoding="utf-8")
            self.assertTrue(progress.should_send(path, 1, "sources_locked"))
            self.assertFalse(progress.should_send(path, 2, "sources_locked"))
            self.assertFalse(progress.should_send(path, 3, "environment_active"))
            self.assertFalse(progress.should_send(path, 3, "production_active"))
            self.assertFalse(progress.should_send(path, 3, "render_heartbeat", 18))
            self.assertFalse(progress.should_send(path, 3, "checkpoint_repair"))
            self.assertFalse(progress.should_send(path, 3, "checkpoint_heartbeat", 18))
            self.assertFalse(progress.should_send(path, 3, "master_ready"))
            self.assertFalse(progress.should_send(path, 3, "quality_passed"))
            self.assertFalse(progress.should_send(path, 3, "review_ready"))
            self.assertFalse(progress.should_send(path, 3, "render_heartbeat", 6))
            self.assertFalse(progress.should_send(path, 1, "render_heartbeat", 18))
            self.assertFalse(progress.should_send(path, 1, "render_heartbeat", 21))
            self.assertFalse(progress.should_send(path, 1, "render_heartbeat", 24))
            self.assertFalse(progress.should_send(path, 1, "render_heartbeat", 27))
            self.assertTrue(progress.should_send(path, 1, "render_heartbeat", 45))
            self.assertFalse(progress.should_send(path, 1, "checkpoint_heartbeat", 3))
            self.assertFalse(progress.should_send(path, 1, "checkpoint_heartbeat", 18))
            self.assertTrue(progress.should_send(path, 1, "checkpoint_repair"))
            self.assertTrue(progress.should_send(path, 1, "master_ready"))
            self.assertTrue(progress.should_send(path, 1, "quality_passed"))
            self.assertTrue(progress.should_send(path, 1, "review_ready"))
            self.assertFalse(progress.should_send(path, 3, "audio_recovery"))
            path.write_text(json.dumps({"production_progress_enabled": False}), encoding="utf-8")
            self.assertFalse(progress.should_send(path, 1, "master_ready"))


class TelegramProgressWorkflowTests(unittest.TestCase):
    def test_golden_path_wires_each_verified_milestone_once(self) -> None:
        workflow = (ROOT / ".github/workflows/tayvoriq-deliver-video-now.yml").read_text(encoding="utf-8")
        for stage in ("sources_locked", "production_active", "master_ready", "quality_passed"):
            self.assertEqual(workflow.count(f"--stage {stage}"), 1)
        self.assertEqual(workflow.count("--stage render_heartbeat"), 1)
        self.assertEqual(workflow.count("--stage checkpoint_repair"), 1)
        self.assertEqual(workflow.count("--stage checkpoint_heartbeat"), 1)
        self.assertIn("Telegram progress - checkpoint repair", workflow)
        self.assertIn("sleep 180", workflow)
        self.assertIn("--policy ../state/tayvoriq-notification-policy.json", workflow)
        self.assertIn("Telegram immediate verified stop", workflow)
        self.assertIn("--stage \"$notification_stage\"", workflow)
        self.assertIn("telegram-failure-receipt.json", workflow)
        self.assertGreaterEqual(workflow.count("continue-on-error: true"), 4)
        self.assertIn(
            'if [ "${GITHUB_EVENT_NAME}" != "push" ]; then',
            workflow,
        )
        self.assertIn(
            "Verified production-start Telegram is owned by the request dispatcher.",
            workflow,
        )

    def test_supersede_guard_cancels_only_older_active_runs(self) -> None:
        workflow = (ROOT / ".github/workflows/tayvoriq-supersede-stale-runs.yml").read_text(encoding="utf-8")
        self.assertIn("tayvoriq-x-request.json", workflow)
        self.assertIn("actions: write", workflow)
        self.assertIn("head_sha", workflow)
        self.assertIn("keeper_run_id", workflow)
        self.assertIn("cancelled_older_runs", workflow)
        self.assertIn("/cancel", workflow)
        self.assertIn("fail-safe-no-cancellation", workflow)
        self.assertIn("publication_performed", workflow)

    def test_golden_path_promises_real_milestones_not_silence(self) -> None:
        workflow = (ROOT / ".github/workflows/tayvoriq-deliver-video-now.yml").read_text(encoding="utf-8")
        self.assertIn("TAYVORIQ Produktion gestartet", workflow)
        self.assertIn("--stage sources_locked", workflow)
        self.assertIn("--stage master_ready", workflow)
        self.assertIn("--stage quality_passed", workflow)
        self.assertNotIn("Nächste Nachricht erst beim fertigen Video-Review", workflow)

    def test_on_demand_status_bridge_is_bound_to_one_trigger_file(self) -> None:
        workflow = (
            ROOT / ".github/workflows/tayvoriq-telegram-status-bridge-v1.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('.github/run-now/tayvoriq-progress-trigger.json', workflow)
        self.assertIn('STATUS_STAGE_INVALID', workflow)
        self.assertIn('Send and verify Telegram status', workflow)
        self.assertIn('audio_recovery', workflow)
        self.assertIn('checkpoint_repair', workflow)
        self.assertIn('checkpoint_heartbeat', workflow)
        self.assertIn('elapsed_minutes', workflow)
        self.assertIn('STATUS_ELAPSED_MINUTES_INVALID', workflow)

    def test_checked_in_policy_matches_state_change_operator_feed(self) -> None:
        policy = json.loads(
            (ROOT / "state/tayvoriq-notification-policy.json").read_text(encoding="utf-8")
        )
        self.assertIs(policy["production_progress_enabled"], True)
        self.assertIs(policy["notify_only_on_real_state_change"], True)
        self.assertIs(policy["enabled_until_user_opt_out"], True)
        self.assertEqual(policy["watchdog_poll_interval_seconds"], 180)
        self.assertEqual(policy["operator_heartbeat_notify_minutes"], [45])
        self.assertIs(policy["suppress_intermediate_liveness_polls"], True)
        self.assertIs(policy["immediate_failure_notification_enabled"], False)
        self.assertIs(policy["internal_recovery_operator_noise_suppressed"], True)
        self.assertIs(policy["terminal_external_blocker_notification_enabled"], True)
        self.assertEqual(
            policy["recovery_replay_suppressed_stages"],
            ["render_heartbeat", "checkpoint_repair", "checkpoint_heartbeat"],
        )
        self.assertIn("checkpoint_repair", policy["milestones"])
        self.assertIn("checkpoint_heartbeat", policy["long_running_threshold_stages"])


if __name__ == "__main__":
    unittest.main()
