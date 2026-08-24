from pathlib import Path
import importlib.util
import json
import sys


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "tayvoriq_telegram_progress_v1.py"
spec = importlib.util.spec_from_file_location("tayvoriq_telegram_progress_v1", MODULE_PATH)
assert spec and spec.loader
progress = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = progress
spec.loader.exec_module(progress)


def test_recovery_progress_never_regresses_below_sixty():
    stages = (
        "recovery_started",
        "sources_locked",
        "environment_active",
        "production_active",
        "render_heartbeat",
        "checkpoint_repair",
        "checkpoint_heartbeat",
        "master_ready",
        "quality_passed",
        "review_ready",
    )
    values = [progress.effective_milestone(stage, 12).percent for stage in stages]
    assert all(value is not None and value >= 60 for value in values)
    assert values == [60, 62, 62, 65, 65, 75, 75, 85, 95, 100]


def test_fresh_recovery_confirms_sources_instead_of_hiding_them():
    assert "sources_locked" not in progress.RECOVERY_REPLAY_SUPPRESSED_STAGES
    milestone = progress.effective_milestone("sources_locked", 1)
    assert milestone.percent == 62
    assert "Recovery-Bindung" in milestone.title


def test_recovery_generation_is_resolved_from_workspace_not_current_directory(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    request_dir = workspace / "requests"
    request_dir.mkdir(parents=True)
    request_id = "telegram-1268-trend-1"
    run_id = 32649570583
    (request_dir / f"{request_id}.json").write_text(
        json.dumps({
            "request_id": request_id,
            "recovery_generation": 12,
            "golden_path_run_id": run_id,
        }),
        encoding="utf-8",
    )
    implementation = workspace / "implementation"
    implementation.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("SOURCE_REQUEST_ID_PIN", request_id)
    monkeypatch.setenv("GITHUB_RUN_ID", str(run_id))
    monkeypatch.chdir(implementation)
    assert progress.recovery_generation() == 12


def test_recovery_generation_suppresses_stale_workspace_snapshot(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    request_dir = workspace / "requests"
    request_dir.mkdir(parents=True)
    request_id = "telegram-1451-trend-1"
    (request_dir / f"{request_id}.json").write_text(
        json.dumps({
            "request_id": request_id,
            "recovery_generation": 4,
            "golden_path_run_id": 32649570583,
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("SOURCE_REQUEST_ID_PIN", request_id)
    monkeypatch.setenv("GITHUB_RUN_ID", "32643433479")
    assert progress.recovery_generation() == 0

    monkeypatch.setenv("GITHUB_RUN_ID", "32649570583")
    assert progress.recovery_generation() == 4


def test_watchdog_polling_every_three_minutes_does_not_spam_telegram():
    # Premium dual-voice/render work commonly exceeds 18 minutes. The internal
    # watchdog keeps polling, but Telegram remains silent until minute 45.
    for minute in (3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42):
        assert not progress.heartbeat_due("render_heartbeat", minute)
    assert progress.heartbeat_due("render_heartbeat", 45)


def test_checkpoint_watchdog_uses_same_quiet_threshold_policy():
    for minute in (3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 42):
        assert not progress.heartbeat_due("checkpoint_heartbeat", minute)
    assert progress.heartbeat_due("checkpoint_heartbeat", 45)


def test_recovery_generation_does_not_repeat_repair_noise():
    assert progress.RECOVERY_REPLAY_SUPPRESSED_STAGES == {
        "render_heartbeat",
        "checkpoint_repair",
        "checkpoint_heartbeat",
    }


def test_real_milestones_are_always_due_immediately():
    assert progress.heartbeat_due("production_active", 1)
    assert progress.heartbeat_due("master_ready", 24)
    assert progress.heartbeat_due("quality_passed", 1)


def test_recovery_payload_exposes_generation_and_no_user_action():
    payload = progress.build_payload(
        "production_active",
        "Testthema",
        "32389787423",
        "1234",
        generation=12,
    )
    assert "TAYVORIQ 65 %" in payload["text"]
    assert "Recovery: Generation 12" in payload["text"]
    assert "Für dich: ✅ Keine Aktion nötig." in payload["text"]


def test_long_running_notice_promises_silent_internal_polling_afterward():
    payload = progress.build_payload(
        "render_heartbeat",
        "Testthema",
        "32389787423",
        "1234",
        elapsed_minutes=45,
    )
    text = payload["text"]
    assert "ungewöhnlich lange aktiv" in text
    assert "Telegram meldet erst wieder einen echten Zustandswechsel oder einen Fehler" in text


def test_checkpoint_is_not_mislabeled_as_final_master():
    milestone = progress.effective_milestone("checkpoint_repair", 12)
    assert milestone.percent == 75
    assert "Render-Zwischenstand" in milestone.title
    assert "noch nicht freigabefähig" in milestone.completed
    assert "Master gesichert" not in milestone.title

    payload = progress.build_payload(
        "checkpoint_repair",
        "Testthema",
        "32389787423",
        "1234",
        generation=12,
    )
    assert "TAYVORIQ 75 %" in payload["text"]
    assert "noch nicht freigabefähig" in payload["text"]


def test_master_quality_and_review_are_distinct_real_gate_percentages():
    assert progress.effective_milestone("checkpoint_repair", 0).percent == 75
    assert progress.effective_milestone("master_ready", 0).percent == 85
    assert progress.effective_milestone("quality_passed", 0).percent == 95
    assert progress.effective_milestone("review_ready", 0).percent == 100
