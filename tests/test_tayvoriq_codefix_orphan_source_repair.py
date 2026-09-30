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
