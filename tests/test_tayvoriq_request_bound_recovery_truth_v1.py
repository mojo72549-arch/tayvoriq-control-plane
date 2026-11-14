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
    assert "Automatische Recovery ist request-gebunden" in text
    assert "automatisch untersucht" not in text
    assert "Recovery Dispatcher startet" not in text


def test_delivery_watch_persists_binding_before_dispatching_exact_retry() -> None:
    workflow = (ROOT / ".github/workflows/tayvoriq-delivery-watch.yml").read_text()
    retry = workflow.split("- name: Same-run retry for local or transient failure", 1)[1]
    retry = retry.split("- name: Replay local checkpoint", 1)[0]
    assert retry.index("tayvoriq_recovery_rebind_v1.py") < retry.index("git push")
    assert retry.index("git push") < retry.index("tayvoriq_recovery_attempt_ack_v1.py")


def test_armed_codefix_cannot_authorize_a_same_run_retry() -> None:
    workflow = (ROOT / ".github/workflows/tayvoriq-deliver-video-now.yml").read_text()
    for name in ("Early recovery binding gate", "Exact-request replay readiness gate"):
        step = workflow.split(f"- name: {name}", 1)[1].split("- name:", 1)[0]
        assert "codefix.get('status')=='LOCAL_RETRY_DISPATCHED'" in step
        assert "int(codefix.get('local_retry_run_id') or 0)==run_id" in step
        assert "int(codefix.get('local_retry_run_attempt') or 0)==run_attempt" in step
        assert "request_bound and (deterministic_bound or fresh_bound or local_retry_bound)" in step
