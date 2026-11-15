"""Regression coverage for a real exhausted Stuttgart evening production."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from tayvoriq_lifecycle_controller_v1 import decide
from tayvoriq_recovery_outcome_v1 import record_exhaustion


def incident():
    pointer = {
        "schema": "tayvoriq-active-production-request-v1", "state": "ACTIVE",
        "request_id": "telegram-3636-trend-1", "golden_path_run_id": 43732348851,
        "recovery_generation": 1, "approval_key": "telegram:20261115-evening-agentv2:3636:trend:1",
        "source_context_sha256": "f" * 64, "contract_sha256": "a" * 64,
    }
    request = {
        **pointer, "source": "telegram_trend_approval", "status": "DISPATCHED",
        "topic": "Stuttgart Hauptbahnhof: Der kürzere Weg zur S-Bahn ist wieder offen",
        "codefix_recovery": {"status": "LOCAL_RETRY_DISPATCHED", "request_substate": "DISPATCHED",
                             "replay_implementation_sha": "e" * 40},
        "source_context": {"sources": [{"url": "https://example.invalid/source"}]},
    }
    run = {"id": 43732348851, "run_attempt": 3,
           "status": "completed", "conclusion": "failure"}
    policy = {
        "mode": "exhausted", "state": "LOCAL_VISUAL_RECOVERY_EXHAUSTED",
        "retry_allowed": False, "current_generation": 1,
        "failure_signature": "b" * 20,
    }
    return pointer, request, run, policy


def test_exhaustion_is_durable_idempotent_and_never_releases_publication():
    pointer, request, run, policy = incident()
    approved = copy.deepcopy(request["source_context"])
    assert record_exhaustion(pointer, request, policy, run_id=run["id"],
                            run_attempt=3, now="2026-11-15T16:13:00Z")
    outcome = request["recovery_outcome"]
    assert outcome["run_id"] == run["id"]
    assert outcome["reason"] == "LOCAL_VISUAL_RECOVERY_EXHAUSTED"
    assert outcome["implementation_sha"] == "e" * 40
    assert outcome["quality_gates_weakened"] is False
    assert outcome["publish_allowed"] is False
    assert request["status"] == "DISPATCHED"
    assert request["source_context"] == approved
    assert not record_exhaustion(pointer, request, policy, run_id=run["id"],
                                run_attempt=3, now="2026-11-15T16:14:00Z")
    assert request["recovery_outcome"]["recorded_at"] == "2026-11-15T16:13:00Z"


def test_verified_outcome_replaces_false_missing_executor_result():
    pointer, request, run, policy = incident()
    previous = {"decision_key": "old", "dispatch_verified": True,
                "action": "DELIVERY_WATCH", "executor_run_id": 43734194007}
    assert decide(pointer, request, run, previous=previous)["state"] == "RECOVERY_REQUIRED"
    record_exhaustion(pointer, request, policy, run_id=run["id"], run_attempt=3)
    decision = decide(pointer, request, run, previous=previous)
    assert decision["action"] == "NONE"
    assert decision["state"] == "REPAIR_REQUIRED"
    assert decision["reason"] == "LOCAL_VISUAL_RECOVERY_EXHAUSTED"
    assert decision["request_substate"] == "RECOVERY_EXHAUSTED"


@pytest.mark.parametrize("mutate", [
    lambda p, r, e: p.update(golden_path_run_id=41),
    lambda p, r, e: p.update(request_id="other"),
    lambda p, r, e: r.update(source_context_sha256="changed"),
    lambda p, r, e: r.update(status="PUBLISHED"),
    lambda p, r, e: r.update(recovery_generation=2),
    lambda p, r, e: e.update(mode="rerun"),
    lambda p, r, e: e.update(retry_allowed=True),
    lambda p, r, e: e.update(failure_signature="not-a-signature"),
])
def test_fail_closed_on_stale_owner_and_unverified_policy(mutate):
    pointer, request, run, policy = incident()
    mutate(pointer, request, policy)
    with pytest.raises(ValueError):
        record_exhaustion(pointer, request, policy, run_id=run["id"], run_attempt=3)
    assert "recovery_outcome" not in request


def test_forged_receipt_is_not_treated_as_success_or_recoverable():
    pointer, request, run, policy = incident()
    record_exhaustion(pointer, request, policy, run_id=run["id"], run_attempt=3)
    request["recovery_outcome"]["publish_allowed"] = True
    decision = decide(pointer, request, run)
    assert decision["state"] == "BLOCKED"
    assert decision["reason"] == "RECOVERY_OUTCOME_IDENTITY_INVALID"
    assert decision["action"] == "NONE"


def test_old_receipt_does_not_own_new_generation():
    pointer, request, run, policy = incident()
    record_exhaustion(pointer, request, policy, run_id=run["id"], run_attempt=3)
    pointer["golden_path_run_id"] = request["golden_path_run_id"] = 43740000000
    run["id"] = 43740000000
    result = decide(pointer, request, run)
    assert result["state"] == "RECOVERY_REQUIRED"
    assert result["action"] == "DELIVERY_WATCH"


def test_voice_exhaustion_uses_same_contract():
    pointer, request, run, policy = incident()
    policy["state"] = "LOCAL_VOICE_RECOVERY_EXHAUSTED"
    assert record_exhaustion(pointer, request, policy, run_id=run["id"], run_attempt=3)
    assert decide(pointer, request, run)["reason"] == "LOCAL_VOICE_RECOVERY_EXHAUSTED"


def test_verified_new_green_revives_exhausted_request_without_new_generation():
    pointer, request, run, policy = incident()
    record_exhaustion(pointer, request, policy, run_id=run["id"], run_attempt=3)
    previous = {"decision_key": "historic-dispatch", "dispatch_verified": True}
    unchanged = decide(pointer, request, run, green="e" * 40, previous=previous)
    assert unchanged["state"] == "REPAIR_REQUIRED"
    assert unchanged["action"] == "NONE"
    changed = decide(pointer, request, run, green="f" * 40, previous=previous)
    assert changed["state"] == "RECOVERY_REQUIRED"
    assert changed["reason"] == "VERIFIED_GREEN_ADVANCED_AFTER_EXHAUSTION"
    assert changed["action"] == "DELIVERY_WATCH"
    assert changed["run_id"] == str(run["id"])
    assert changed["generation"] == "1"
    assert len(changed["decision_key"]) == 64
    # The same verified codefix must NEVER dispatch multiple owners.
    dup = decide(pointer, request, run, green="f" * 40,
                 previous={**changed, "dispatch_verified": True})
    assert dup["action"] == "NONE"
    assert dup["state"] == "RECOVERY_FAILED"


def test_unverified_green_or_unknown_original_version_cannot_revive_exhaustion():
    pointer, request, run, policy = incident()
    record_exhaustion(pointer, request, policy, run_id=run["id"], run_attempt=3)
    for green in ("", "broken", "e" * 40):
        result = decide(pointer, request, run, green=green)
        assert result["state"] == "REPAIR_REQUIRED"
        assert result["action"] == "NONE"
    request["recovery_outcome"]["implementation_sha"] = ""
    result = decide(pointer, request, run, green="f" * 40)
    assert result["state"] == "REPAIR_REQUIRED"
