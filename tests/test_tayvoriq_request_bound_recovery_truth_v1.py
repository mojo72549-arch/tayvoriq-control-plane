from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_telegram_progress_v1 as progress


def test_technical_stop_overrides_legacy_vague_detail_with_recovery_contract() -> None:
    payload = progress.build_payload(
        "technical_stop",
        "Deutschland holt 21 EM-Medaillen",
        "32240504048",
        "12345",
        failure_state="CODE_REPAIR_REQUIRED",
        detail="Der technische Teilpfad wird automatisch untersucht.",
    )
    text = payload["text"]
    assert "CODE_REPAIR_REQUIRED" in text
    assert "Delivery Watch übernimmt denselben freigegebenen Auftrag" in text
    assert "Recovery Dispatcher startet und bindet den nächsten Run automatisch" in text
    assert "altem und neuem Run" in text
    assert "automatisch untersucht" not in text


def test_request_bound_recovery_dispatcher_uses_direct_workflow_dispatch() -> None:
    workflow = (
        ROOT / ".github/workflows/tayvoriq-request-bound-recovery-dispatcher.yml"
    ).read_text(encoding="utf-8")
    assert "workflows:\n      - TAYVORIQ-X Golden Path" in workflow
    assert "recovery_owner') or '') != 'tayvoriq-delivery-watch'" in workflow
    assert "gh workflow run tayvoriq-deliver-video-now.yml" in workflow
    assert "status']='DISPATCHING'" in workflow
    assert "data['status']='DISPATCHED'" in workflow
    assert "data['golden_path_run_id']=new_run" in workflow
    assert "AUTONOMOUS_REQUEST_BOUND_RECOVERY_DISPATCH_PASSED" in workflow


def test_failed_golden_path_dispatches_immediate_owner_and_waits_for_terminal_source() -> None:
    golden = (ROOT / ".github/workflows/tayvoriq-deliver-video-now.yml").read_text(
        encoding="utf-8"
    )
    watch = (ROOT / ".github/workflows/tayvoriq-delivery-watch.yml").read_text(
        encoding="utf-8"
    )
    assert "Dispatch immediate request-bound recovery owner" in golden
    assert "if: failure()" in golden
    assert "gh workflow run tayvoriq-delivery-watch.yml" in golden
    assert '-f "run_id=$GITHUB_RUN_ID"' in golden
    assert "RECOVERY_SOURCE_RUN_NOT_TERMINAL" in watch
    assert "steps.owner.outputs.is_current == 'true'" in watch


def test_recovery_generation_is_passed_to_every_fresh_golden_path() -> None:
    golden = (ROOT / ".github/workflows/tayvoriq-deliver-video-now.yml").read_text(
        encoding="utf-8"
    )
    delivery = (ROOT / ".github/workflows/tayvoriq-delivery-watch.yml").read_text(
        encoding="utf-8"
    )
    continuity = (
        ROOT / ".github/workflows/tayvoriq-request-continuity-watchdog.yml"
    ).read_text(encoding="utf-8")
    dispatcher = (
        ROOT / ".github/workflows/tayvoriq-request-bound-recovery-dispatcher.yml"
    ).read_text(encoding="utf-8")
    assert "recovery_generation:" in golden
    assert "TAYVORIQ_RECOVERY_GENERATION" in golden
    assert '-f "recovery_generation=$NEXT_GENERATION"' in delivery
    assert '-f "recovery_generation=$NEXT_GENERATION"' in continuity
    assert '-f recovery_generation="${{ steps.candidate.outputs.recovery_generation }}"' in dispatcher


def test_explicit_recovery_generation_survives_dispatch_binding_race(monkeypatch) -> None:
    monkeypatch.setenv("TAYVORIQ_RECOVERY_GENERATION", "2")
    monkeypatch.setenv("SOURCE_REQUEST_ID_PIN", "request-not-yet-rebound")
    assert progress.recovery_generation() == 2

    monkeypatch.setenv("TAYVORIQ_RECOVERY_GENERATION", "9")
    assert progress.recovery_generation() == 0
