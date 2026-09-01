from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from tayvoriq_recovery_policy_v1 import classify_failure


def test_lumi_validator_failure_is_internal_codefix_even_with_secret_source_echo():
    logs = r'''
    test -n "${!name:-}" || { echo "Missing secret: $name"; exit 1; }
    RuntimeError: CONTENT_REJECTED:v34-legacy-validator:editorial_answer_too_long:what_happened,editorial_body_too_long:56:max=49
    RuntimeError: CONTENT_REJECTED:v48-bounded-overflow-outside-range
    '''
    decision = classify_failure(
        logs,
        run_attempt=1,
        recovery_generation=0,
        max_generations=4,
        exact_request_retry=True,
    )
    assert decision.mode == "deterministic"
    assert decision.state == "EDITORIAL_VALIDATOR_CODEFIX_REQUIRED"
    assert decision.retry_kind == "verified-codefix-replay"
    assert decision.retry_allowed is False
    assert decision.next_generation == 0
    assert "not an external" in decision.reason


def test_workflow_source_echo_of_missing_secret_does_not_trigger_external_help():
    logs = r'''
    test -n "${!name:-}" || { echo "Missing secret: $name"; exit 1; }
    if [ -z "${TOKEN:-}" ]; then echo "Missing required secret: TOKEN"; fi
    internal render checkpoint failed
    '''
    decision = classify_failure(logs, recovery_generation=1, max_generations=4)
    assert decision.mode == "fresh"
    assert decision.state == "REQUEST_BOUND_RECOVERY_REQUIRED"
    assert decision.next_generation == 2


def test_real_named_missing_secret_still_requires_external_action():
    decision = classify_failure(
        "Missing secret: GEMINI_API_KEY",
        recovery_generation=2,
        max_generations=4,
    )
    assert decision.mode == "external"
    assert decision.state == "EXTERNAL_ACTION_REQUIRED"
    assert decision.next_generation is None


def test_explicit_external_auth_marker_still_requires_external_action():
    decision = classify_failure("EXTERNAL_AUTH_BLOCKER: provider credentials expired")
    assert decision.mode == "external"
    assert decision.state == "EXTERNAL_ACTION_REQUIRED"
