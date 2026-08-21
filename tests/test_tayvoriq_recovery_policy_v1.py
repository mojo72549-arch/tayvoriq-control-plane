from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from tayvoriq_recovery_policy_v1 import classify_failure


def test_preflight_test_failure_never_starts_new_generation():
    logs = """
    state: PREFLIGHT_FAILED
    FAILED tests/test_tayvoriq_checkpoint_resume_policy.py::test_lean_recovery_checkpoint_hydrates_only_matching_trend_and_source
    1 failed, 303 passed
    Production blocked before render: preflight outcome=failure
    """
    decision = classify_failure(logs, recovery_generation=30, max_generations=4)
    assert decision.mode == "deterministic"
    assert decision.state == "DETERMINISTIC_PREFLIGHT_FAILURE"
    assert decision.retry_allowed is False
    assert decision.next_generation is None


def test_transient_failure_uses_same_run_before_fresh_generation():
    decision = classify_failure(
        "HTTP 503 temporarily unavailable while synthesizing voice",
        run_attempt=1,
        recovery_generation=2,
        max_generations=4,
    )
    assert decision.mode == "rerun"
    assert decision.retry_kind == "same-run"
    assert decision.next_generation == 2


def test_transient_failure_stops_same_run_retry_after_two_attempts():
    decision = classify_failure(
        "HTTP 503 temporarily unavailable",
        run_attempt=3,
        recovery_generation=4,
        max_generations=4,
    )
    assert decision.mode == "exhausted"
    assert decision.state == "RECOVERY_CIRCUIT_OPEN"
    assert decision.retry_allowed is False


def test_fresh_internal_recovery_is_bounded():
    decision = classify_failure(
        "internal render checkpoint failed",
        recovery_generation=3,
        max_generations=4,
    )
    assert decision.mode == "fresh"
    assert decision.next_generation == 4

    stopped = classify_failure(
        "internal render checkpoint failed",
        recovery_generation=4,
        max_generations=4,
    )
    assert stopped.mode == "exhausted"
    assert stopped.next_generation is None


def test_exact_request_duplicate_during_recovery_is_contract_failure_not_new_angle():
    decision = classify_failure(
        "DUPLICATE_CONTENT_BLOCKED",
        recovery_generation=1,
        max_generations=4,
        exact_request_retry=True,
    )
    assert decision.mode == "deterministic"
    assert decision.state == "DUPLICATE_RETRY_CONTRACT_BROKEN"
    assert decision.retry_allowed is False


def test_new_approved_content_can_still_be_blocked_as_real_duplicate():
    decision = classify_failure("DUPLICATE_CONTENT_BLOCKED", exact_request_retry=False)
    assert decision.mode == "duplicate"
    assert decision.state == "DUPLICATE_CONTENT_BLOCKED"


def test_external_blocker_never_consumes_recovery_generation():
    decision = classify_failure(
        "Missing secret: GEMINI_API_KEY",
        recovery_generation=2,
        max_generations=4,
    )
    assert decision.mode == "external"
    assert decision.current_generation == 2
    assert decision.next_generation is None


def test_failure_signature_is_stable_for_same_failed_test_across_runs():
    a = classify_failure(
        "FAILED tests/test_a.py::test_contract run=111\n1 failed",
        recovery_generation=1,
    )
    b = classify_failure(
        "FAILED tests/test_a.py::test_contract run=999\n1 failed",
        recovery_generation=3,
    )
    assert a.failure_signature == b.failure_signature
