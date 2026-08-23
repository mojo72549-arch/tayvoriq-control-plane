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


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


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
    (request_dir / f"{request_id}.json").write_text(
        json.dumps({"request_id": request_id, "recovery_generation": 12}),
        encoding="utf-8",
    )
    implementation = workspace / "implementation"
    implementation.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("SOURCE_REQUEST_ID_PIN", request_id)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    monkeypatch.delenv("TAYVORIQ_RECOVERY_GENERATION_PIN", raising=False)
    monkeypatch.chdir(implementation)
    assert progress.recovery_generation() == 12


def test_live_durable_request_wins_over_stale_frozen_checkout(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    request_dir = workspace / "requests"
    request_dir.mkdir(parents=True)
    request_id = "telegram-1268-trend-1"
    current_run = "32451685401"
    # This models the real bug: the job checked out generation 30 before the
    # durable request was rebound to this current run as generation 31.
    (request_dir / f"{request_id}.json").write_text(
        json.dumps({
            "request_id": request_id,
            "recovery_generation": 30,
            "golden_path_run_id": 32449164670,
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("SOURCE_REQUEST_ID_PIN", request_id)
    monkeypatch.setenv("GITHUB_REPOSITORY", "mojo72549-arch/tayvoriq-control-plane")
    monkeypatch.setenv("GITHUB_RUN_ID", current_run)
    monkeypatch.delenv("TAYVORIQ_RECOVERY_GENERATION_PIN", raising=False)
    monkeypatch.setattr(
        progress.urllib.request,
        "urlopen",
        lambda request, timeout=5: _FakeResponse({
            "request_id": request_id,
            "recovery_generation": 31,
            "golden_path_run_id": int(current_run),
        }),
    )
    assert progress.recovery_generation() == 31


def test_stale_local_generation_is_never_reported_if_live_truth_is_unavailable(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    request_dir = workspace / "requests"
    request_dir.mkdir(parents=True)
    request_id = "telegram-1268-trend-1"
    (request_dir / f"{request_id}.json").write_text(
        json.dumps({
            "request_id": request_id,
            "recovery_generation": 30,
            "golden_path_run_id": 32449164670,
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("SOURCE_REQUEST_ID_PIN", request_id)
    monkeypatch.setenv("GITHUB_REPOSITORY", "mojo72549-arch/tayvoriq-control-plane")
    monkeypatch.setenv("GITHUB_RUN_ID", "32451685401")
    monkeypatch.delenv("TAYVORIQ_RECOVERY_GENERATION_PIN", raising=False)

    def _offline(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(progress.urllib.request, "urlopen", _offline)
    assert progress.recovery_generation() == 0


def test_explicit_generation_pin_has_highest_priority(monkeypatch):
    monkeypatch.setenv("TAYVORIQ_RECOVERY_GENERATION_PIN", "31")
    monkeypatch.setenv("SOURCE_REQUEST_ID_PIN", "telegram-1268-trend-1")
    assert progress.recovery_generation() == 31


def test_watchdog_polling_every_three_minutes_does_not_spam_telegram():
    assert progress.heartbeat_due("render_heartbeat", 18)
    assert not progress.heartbeat_due("render_heartbeat", 21)
    assert not progress.heartbeat_due("render_heartbeat", 24)
    assert not progress.heartbeat_due("render_heartbeat", 27)
    assert not progress.heartbeat_due("render_heartbeat", 30)
    assert progress.heartbeat_due("render_heartbeat", 45)


def test_checkpoint_watchdog_uses_same_quiet_threshold_policy():
    assert progress.heartbeat_due("checkpoint_heartbeat", 18)
    for minute in (3, 6, 9, 12, 15, 21, 24, 27, 30, 33, 42):
        assert not progress.heartbeat_due("checkpoint_heartbeat", minute)
    assert progress.heartbeat_due("checkpoint_heartbeat", 45)


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
        elapsed_minutes=18,
        generation=12,
    )
    text = payload["text"]
    assert "einmaliger Watchdog-Hinweis" in text
    assert "Telegram bleibt bis zum nächsten echten Meilenstein ruhig" in text


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
