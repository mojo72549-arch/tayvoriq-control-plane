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
    assert decision.next_generation == 30


def test_bootstrap_import_failure_wins_over_incidental_timeout_text():
    logs = """
    request = urllib.request.urlopen(url, timeout=20)
    Traceback (most recent call last):
      File "tools/tayvoriq_lightweight_preflight.py", line 79, in _request_source_editorial_contract
        import tayvoriq_dual_platform_render_v11 as editorial
      File "tools/tayvoriq_dual_platform_render_v8.py", line 9, in <module>
        import requests
    ModuleNotFoundError: No module named 'requests'
    """
    decision = classify_failure(
        logs,
        run_attempt=1,
        recovery_generation=0,
        max_generations=4,
        exact_request_retry=True,
    )
    assert decision.mode == "deterministic"
    assert decision.state == "DETERMINISTIC_PREFLIGHT_FAILURE"
    assert decision.retry_kind == "verified-codefix-replay"
    assert decision.retry_allowed is False
    assert decision.next_generation == 0


def test_semantic_contract_failure_wins_over_publishable_retry_handoff():
    logs = """
    RuntimeError: CONTENT_REJECTED:v34-semantic-repair-missing:why_happening
    RuntimeError: Keiner der geprüften Trendkandidaten bestand Skript-, Sprach- und Render-Gates.
    Checkpoint handoff: state=PUBLISHABLE_OUTPUT_RETRY_REQUIRED process_exit=1
    recovery=PUBLISHABLE_OUTPUT_RETRY_REQUIRED/1
    """
    decision = classify_failure(
        logs,
        run_attempt=1,
        recovery_generation=0,
        max_generations=4,
        exact_request_retry=True,
    )
    assert decision.mode == "deterministic"
    assert decision.state == "SEMANTIC_CODEFIX_REQUIRED"
    assert decision.retry_kind == "verified-codefix-replay"
    assert decision.retry_allowed is False
    assert decision.next_generation == 0


def test_plain_publishability_failure_still_uses_bounded_fresh_recovery():
    decision = classify_failure(
        "Checkpoint handoff: state=PUBLISHABLE_OUTPUT_RETRY_REQUIRED process_exit=1",
        recovery_generation=1,
        max_generations=4,
        exact_request_retry=True,
    )
    assert decision.mode == "fresh"
    assert decision.state == "REQUEST_BOUND_RECOVERY_REQUIRED"
    assert decision.next_generation == 2


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


def test_terminal_code_repair_wins_over_provider_and_workflow_source_noise():
    logs = """
    test -n "${!name:-}" || { echo "Missing secret: $name"; exit 1; }
    gemini:RuntimeError:Gemini circuit already open for this workflow
    groq:RuntimeError:Groq circuit already open for this workflow
    TAYVORIQ_AUTONOMOUS_RECOVERY: no safe patch passed validation.
    Controller handoff: state=CODE_REPAIR_REQUIRED reusable_master=false process_exit=1
    Production is not publishable: controller=CODE_REPAIR_REQUIRED/1 recovery=/
    """
    decision = classify_failure(
        logs,
        run_attempt=1,
        recovery_generation=0,
        max_generations=4,
        exact_request_retry=True,
    )
    assert decision.mode == "deterministic"
    assert decision.state == "CODE_REPAIR_REQUIRED"
    assert decision.retry_kind == "verified-codefix-replay"
    assert decision.retry_allowed is False
    assert decision.next_generation == 0


def test_transient_failure_after_same_run_budget_enters_codefix_continuity_at_ceiling():
    decision = classify_failure(
        "HTTP 503 temporarily unavailable",
        run_attempt=3,
        recovery_generation=4,
        max_generations=4,
    )
    assert decision.mode == "deterministic"
    assert decision.state == "RECOVERY_CODEFIX_REQUIRED"
    assert decision.retry_kind == "verified-codefix-replay"
    assert decision.retry_allowed is False
    assert decision.next_generation == 4


def test_fresh_internal_recovery_is_bounded_then_preserved_for_codefix():
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
    assert stopped.mode == "deterministic"
    assert stopped.state == "RECOVERY_CODEFIX_REQUIRED"
    assert stopped.retry_kind == "verified-codefix-replay"
    assert stopped.next_generation == 4


def test_publishability_failure_at_ceiling_is_codefix_not_dead_circuit():
    decision = classify_failure(
        "Checkpoint handoff: state=PUBLISHABLE_OUTPUT_RETRY_REQUIRED process_exit=1",
        recovery_generation=4,
        max_generations=4,
    )
    assert decision.mode == "deterministic"
    assert decision.state == "PUBLISHABLE_CODEFIX_REQUIRED"
    assert decision.retry_kind == "verified-codefix-replay"
    assert decision.next_generation == 4


def test_exhausted_local_checkpoint_repair_is_armed_for_codefix_immediately():
    decision = classify_failure(
        "Bounded localized repair exhausted after 3 audit-driven rounds with residual blockers",
        recovery_generation=2,
        max_generations=4,
    )
    assert decision.mode == "deterministic"
    assert decision.state == "LOCAL_REPAIR_CODEFIX_REQUIRED"
    assert decision.retry_kind == "verified-codefix-replay"
    assert decision.next_generation == 2


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


def test_successful_provider_fallback_does_not_fake_external_blocker():
    logs = """
    provider_failures_before_success: Gemini HTTP 429: You exceeded your quota;
    please check your plan and billing details.
    selected_model: gemini-3.5-flash-lite
    Checkpoint handoff: state=PUBLISHABLE_OUTPUT_RETRY_REQUIRED process_exit=1
    Production is not publishable: controller=CONTROLLER_TIMEOUT/1
    recovery=PUBLISHABLE_OUTPUT_RETRY_REQUIRED/1
    """
    decision = classify_failure(
        logs,
        run_attempt=1,
        recovery_generation=0,
        max_generations=4,
    )
    assert decision.mode == "fresh"
    assert decision.state == "REQUEST_BOUND_RECOVERY_REQUIRED"
    assert decision.next_generation == 1


def test_terminal_publishability_wins_over_runner_source_echoes():
    decision = classify_failure(
        'test -n "${!name:-}" || { echo "Missing secret: $name"; exit 1; }\n'
        '"internal_recovery_expected": state != "EXTERNAL_ACTION_REQUIRED"\n'
        "Checkpoint handoff: state=PUBLISHABLE_OUTPUT_RETRY_REQUIRED process_exit=1\n"
        "recovery=PUBLISHABLE_OUTPUT_RETRY_REQUIRED/1",
        recovery_generation=1,
    )
    assert decision.mode == "fresh"
    assert decision.state == "REQUEST_BOUND_RECOVERY_REQUIRED"
    assert decision.next_generation == 2


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
