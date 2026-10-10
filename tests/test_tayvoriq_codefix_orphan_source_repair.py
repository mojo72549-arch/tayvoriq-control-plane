from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE = Path("tools/tayvoriq_codefix_orphan_reconcile_v1.py")
SPEC = importlib.util.spec_from_file_location("tayvoriq_codefix_orphan_reconcile_v1", MODULE)
assert SPEC and SPEC.loader
orphan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(orphan)


def test_source_repair_requests_are_telegram_bound_and_auto_repairable() -> None:
    request = {
        "source": "telegram_trend_approval_source_repair",
        "source_context": {},
    }

    assert orphan._telegram_bound(request) is True
    assert orphan._auto_repair(request) is True


def test_nontelegram_source_is_not_implicitly_auto_repairable() -> None:
    request = {
        "source": "scheduled_research",
        "source_context": {},
    }

    assert orphan._telegram_bound(request) is False
    assert orphan._auto_repair(request) is False

def test_review_repair_request_keeps_telegram_binding_from_approval_identity() -> None:
    request = {
        "source": "review_rejection_real_video_visual_repair",
        "source_context": {},
        "telegram_message_id": 2991,
        "approval_key": "telegram:20260928-evening-agentv2:2991:trend:1:visual-repair-real-video-v1",
        "approved_at": "2026-09-28T19:05:30Z",
    }

    assert orphan._telegram_bound(request) is True
    assert orphan._auto_repair(request) is True


def test_review_repair_without_telegram_identity_is_not_auto_repairable() -> None:
    request = {
        "source": "review_rejection_real_video_visual_repair",
        "source_context": {},
    }

    assert orphan._telegram_bound(request) is False
    assert orphan._auto_repair(request) is False



def test_structured_local_voice_failure_can_never_be_rearmed_as_codefix(tmp_path: Path) -> None:
    evidence = tmp_path / "failure-notification-policy.json"
    evidence.write_text(
        """{
  "state": "TRANSIENT_AUDIO_FAILURE",
  "failure_class": "LOCAL_VOICE",
  "repair_target_stages": [],
  "quality_gates_weakened": false
}
""",
        encoding="utf-8",
    )

    assert orphan._structured_local_failure(evidence) is True


def test_structured_local_visual_failure_can_never_be_rearmed_as_codefix(tmp_path: Path) -> None:
    evidence = tmp_path / "failure-notification-policy.json"
    evidence.write_text(
        """{
  "state": "PUBLISHABLE_OUTPUT_RETRY_REQUIRED",
  "failure_class": "LOCAL_VISUAL",
  "repair_target_stages": ["VISUALS"],
  "quality_gates_weakened": false
}
""",
        encoding="utf-8",
    )

    assert orphan._structured_local_failure(evidence) is True


def test_deterministic_structured_failure_remains_eligible_for_codefix(tmp_path: Path) -> None:
    evidence = tmp_path / "failure-notification-policy.json"
    evidence.write_text(
        """{
  "state": "CODE_REPAIR_REQUIRED",
  "failure_class": "DETERMINISTIC_CODE",
  "repair_target_stages": [],
  "quality_gates_weakened": false
}
""",
        encoding="utf-8",
    )

    assert orphan._structured_local_failure(evidence) is False


def test_orphan_reconcile_passes_structured_failure_contract_to_recovery_policy() -> None:
    source = MODULE.read_text(encoding="utf-8")
    assert "--structured-evidence" in source
    assert "CODEFIX_ORPHAN_REPLAY_REARM_BLOCKED_NO_STRUCTURED_EVIDENCE" in source
    assert "CODEFIX_ORPHAN_LOCAL_FAILURE_NOT_CODEFIX" in source


def test_local_retry_dispatch_remains_owned_by_delivery_watch() -> None:
    codefix = {
        "status": "LOCAL_RETRY_DISPATCHED",
        "local_retry_run_id": 42,
        "request_substate": "DISPATCHED",
    }

    assert orphan._replay_status_allows_rearm(codefix, 42) is False


def test_local_retry_for_other_run_fails_closed() -> None:
    codefix = {
        "status": "LOCAL_RETRY_DISPATCHED",
        "local_retry_run_id": 41,
        "request_substate": "DISPATCHED",
    }

    assert orphan._replay_status_allows_rearm(codefix, 42) is False


def test_untrusted_artifact_cannot_be_replaced_by_console_fallback(tmp_path, monkeypatch):
    import json
    import pytest
    from types import SimpleNamespace
    folder = tmp_path / 'structured-diagnostics'
    folder.mkdir()
    evidence = folder / 'failure-notification-policy.json'
    monkeypatch.setattr(orphan, '_run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    for changes in ({'quality_gates_weakened': True}, {'run_id': 41}, {'run_attempt': 2}):
        evidence.write_text(json.dumps({'quality_gates_weakened': False, 'run_id': 42,
                                       'run_attempt': 3, **changes}))
        with pytest.raises(RuntimeError, match='STRUCTURED_EVIDENCE_'):
            orphan._structured_failure_evidence(42, 3, tmp_path)


def test_missing_diagnostics_never_labels_current_green_as_failed_code(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    green = tmp_path / 'green.json'
    green.write_text(json.dumps({'schema':'tayvoriq-production-green-v1',
        'implementation_sha':'d'*40,'full_preflight_passed':True,'quality_gates_weakened':False}))
    monkeypatch.setattr(orphan,'PRODUCTION_GREEN_POINTER',green)
    monkeypatch.setattr(orphan,'_run',lambda *args,**kwargs:SimpleNamespace(returncode=1))
    assert orphan._diagnostic_shas(42,3,{'head_sha':'c'*40},tmp_path) == ('c'*40,'')
    proof=dict(run_id=42,run_attempt=3,quality_gates_weakened=False,
               evidence_provenance='exact-run-attempt-console',
               failed_control_plane_sha='b'*40,failed_implementation_sha='a'*40)
    assert orphan._diagnostic_shas(42,3,{'head_sha':'c'*40},tmp_path,proof) == ('b'*40,'a'*40)

