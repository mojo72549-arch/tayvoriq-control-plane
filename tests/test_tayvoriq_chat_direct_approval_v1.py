"""Regression: one-off user authorisation allows review, never publication."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from tayvoriq_chat_direct_approval_v1 import authorized_for_review
from tayvoriq_orchestration_contract import contract_hash, validate
from tayvoriq_request_state import start


def _approval():
    request = json.loads((ROOT / "requests/chatgpt-20261115-morning-mercedes.json").read_text())
    request.pop("production_completion", None)
    request.pop("golden_path_run_id", None)
    request["status"] = "APPROVED"
    request["state_history"] = [{"state": "APPROVED", "actor": "chat_direct_user_instruction"}]
    return request


def test_request_provenance_and_contract():
    item = _approval()
    assert authorized_for_review(item)
    assert contract_hash(item) == item["contract_sha256"]
    validate(item, require_claimable=True)
    record = start(item, cutoff=datetime(2026, 11, 14, tzinfo=timezone.utc))
    assert record["state"] == "APPROVED"


@pytest.mark.parametrize("change", [
    {"source": "telegram_trend_approval"},
    {"telegram_message_id": 123456},
    {"topic": "Other topic"},
    {"selection_id": "20261115-evening-direct"},
    {"allow_publish": True},
    {"approved_at": "2026-11-15T07:00:00Z"},
    {"approval_required_before_youtube_publish": False},
])
def test_unrelated_or_fabricated_approval_not_accepted(change):
    item = _approval()
    item.update(change)
    assert not authorized_for_review(item)
    with pytest.raises((ValueError, SystemExit)):
        start(item, cutoff=datetime(2026, 11, 14, tzinfo=timezone.utc))
