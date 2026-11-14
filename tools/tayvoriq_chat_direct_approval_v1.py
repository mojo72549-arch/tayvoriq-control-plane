"""Single-use direct editorial-production approval; final publish stays Telegram-only.

This is an explicitly scoped compatibility path for the 2026-11-15 morning
review, not a global exemption from authenticated Telegram topic approvals.
"""
from __future__ import annotations

from datetime import datetime, timezone

REQUEST_ID = "chatgpt-20261115-morning-mercedes"
TOPIC = "Mercedes stoppt Investitionen und prüft Werksschließungen"
APPROVAL_KEY = "chatgpt:20261115-morning-mercedes:direct-user-request"


def authorized_for_review(request: dict) -> bool:
    if not isinstance(request, dict):
        return False
    if request.get("source") != "chat_direct_user_authorization":
        return False
    expected = {
        "request_id": REQUEST_ID,
        "topic": TOPIC,
        "trend_id": "1",
        "approval_key": APPROVAL_KEY,
        "mode": "full",
        "selection_id": "20261115-morning-direct",
        "slot": "morning",
    }
    if any(request.get(k) != v for k, v in expected.items()):
        return False
    if request.get("approval_required_before_youtube_publish") is not True:
        return False
    if request.get("tiktok_delivery") != "telegram_manual":
        return False
    if request.get("allow_publish") is True or request.get("published_at"):
        return False
    try:
        stamp = datetime.fromisoformat(str(request["approved_at"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return False
        stamp_utc = stamp.astimezone(timezone.utc)
    except (ValueError, TypeError, KeyError):
        return False
    if stamp_utc.date().isoformat() != "2026-11-14":
        return False
    # Never invent a Telegram trend-selection receipt for a chat approval.
    return request.get("telegram_message_id") is None
