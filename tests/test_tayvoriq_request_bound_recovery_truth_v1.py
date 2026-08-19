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
