from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/tayvoriq-request-continuity-watchdog.yml"


def test_watchdog_selects_newest_bound_request_not_stale_global_pointer() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "Path('.github/run-now/tayvoriq-x-request.json')" not in text
    assert "Path('requests').glob('*.json')" in text
    assert "max(candidates, key=lambda item: item[0])" in text
    assert "telegram_only_user_path" in text
    assert "communication_channel" in text
    assert "auto_repair_until_review" in text


def test_preapproved_telegram_bound_request_can_be_rebound_safely() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "REQUEST_NOT_TELEGRAM_BOUND_AUTO_REPAIR" in text
    assert "NON_TELEGRAM_REQUEST_NOT_RECOVERABLE" not in text
    assert "BOUNDED_ACTIVE_REVIEW_CONTINUITY_RECOVERY" in text
    assert "REQUEST_ALREADY_REBOUND_BY_OTHER_RECOVERY_OWNER" in text
