from pathlib import Path
import importlib.util
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "tayvoriq_telegram_progress_v1.py"
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
    assert values == [60, 62, 62, 65, 65, 84, 84, 84, 90, 100]


def test_fresh_recovery_confirms_sources_instead_of_hiding_them():
    assert "sources_locked" not in progress.RECOVERY_REPLAY_SUPPRESSED_STAGES
    milestone = progress.effective_milestone("sources_locked", 1)
    assert milestone.percent == 62
    assert "Recovery-Bindung" in milestone.title


def test_active_golden_path_heartbeat_is_due_every_three_minutes():
    assert progress.heartbeat_due("render_heartbeat", 3)
    assert progress.heartbeat_due("render_heartbeat", 6)
    assert progress.heartbeat_due("render_heartbeat", 15)
    assert not progress.heartbeat_due("render_heartbeat", 1)
    assert not progress.heartbeat_due("render_heartbeat", 4)
    assert progress.heartbeat_due("checkpoint_heartbeat", 18)


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


def test_master_and_quality_are_real_gate_percentages():
    assert progress.effective_milestone("master_ready", 0).percent == 84
    assert progress.effective_milestone("quality_passed", 0).percent == 90
    assert progress.effective_milestone("review_ready", 0).percent == 100
