from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github/workflows/tayvoriq-request-continuity-watchdog.yml"
ORCHESTRATOR = ROOT / ".github/workflows/tayvoriq-agent-orchestrator-v2.yml"


def test_watchdog_is_observer_only() -> None:
    text = WATCHDOG.read_text(encoding="utf-8")

    assert "actions: read" in text
    assert "contents: read" in text
    assert "decision_owner':'tayvoriq-agent-orchestrator-v2'" in text
    assert "action':'OBSERVE_ONLY'" in text
    assert "gh workflow run" not in text
    assert "/cancel" not in text
    assert "actions: write" not in text
    assert "contents: write" not in text


def test_orchestrator_is_single_lifecycle_decision_owner() -> None:
    text = ORCHESTRATOR.read_text(encoding="utf-8")

    assert "lifecycle-controller:" in text
    assert "TAYVORIQ-X Golden Path" in text
    assert "TAYVORIQ Production Green Promoter" in text
    assert "TAYVORIQ Deterministic Codefix Continuity" in text
    assert "TAYVORIQ Delivery Watch" in text
    assert "TAYVORIQ Request Continuity Watchdog" in text
    assert "decision_owner':'tayvoriq-agent-orchestrator-v2'" in text
    assert "Enforce single active executor" in text
    assert "queued" in text and "in_progress" in text


def test_orchestrator_dispatches_only_bound_recovery_executors() -> None:
    text = ORCHESTRATOR.read_text(encoding="utf-8")

    assert "source_request_id=\"$REQUEST_ID\"" in text
    assert "failed_run_id=\"$RUN_ID\"" in text
    assert "run_id=\"$RUN_ID\"" in text
    assert "STALE_GOLDEN_PATH_EVENT" in text
    assert "EXTERNAL_BLOCKER_FAIL_CLOSED" in text
    assert "PRODUCTION_GREEN_READY" in text


def test_watchdog_no_longer_rebinds_or_owns_recovery() -> None:
    text = WATCHDOG.read_text(encoding="utf-8")

    legacy_mutation_markers = (
        "REQUEST_NOT_TELEGRAM_BOUND_AUTO_REPAIR",
        "BOUNDED_ACTIVE_REVIEW_CONTINUITY_RECOVERY",
        "REQUEST_ALREADY_REBOUND_BY_OTHER_RECOVERY_OWNER",
        "Path('requests').glob('*.json')",
    )
    for marker in legacy_mutation_markers:
        assert marker not in text
