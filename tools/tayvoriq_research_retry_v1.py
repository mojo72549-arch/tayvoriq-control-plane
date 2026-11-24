"""Bounded retry of an unapproved trend slot; never produces or publishes."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from tayvoriq_provider_health_v1 import read, write

ZONE = ZoneInfo("Europe/Berlin")
MAX_ATTEMPTS = 3
REGULAR_DEADLINE_SECONDS = 10 * 60
REVIEW_RETRY_SECONDS = 5 * 60
REVIEW_DEADLINE_SECONDS = 10 * 60
REVIEW_MAX_ATTEMPTS = 3
REVIEW_RETRY_DIR = Path(".automation/tayvoriq-agent-v2/research-retries")
ISSUE_DETAILS = {
    "RESEARCH_TIME_BUDGET_EXHAUSTED": "Die Themenprüfung hat ihr Zeitlimit erreicht.",
    "EDITORIAL_MINIMUM_NOT_MET": "Zu wenige Themen haben die redaktionelle Prüfung bestanden.",
    "SOURCE_MINIMUM_NOT_MET": "Zu wenige Vorschläge haben die Quellenprüfung bestanden.",
    "RESEARCH_PROVIDER_UNAVAILABLE": "Die Rechercheanbieter konnten die Anfrage nicht abschließen.",
}


def review_path(selection_id: str) -> Path:
    if not selection_id.startswith("review-") or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in selection_id):
        raise ValueError("INVALID_REVIEW_SELECTION_ID")
    return REVIEW_RETRY_DIR / f"{selection_id}.json"


def _review_selection(path: Path) -> str:
    return path.stem if path.parent.name == REVIEW_RETRY_DIR.name and path.stem.startswith("review-") else ""


def configured_path() -> Path | None:
    value = os.getenv("TAYVORIQ_RESEARCH_RETRY_FILE")
    return Path(value) if value else None


def defer(slot: str, next_at: float | None, *, path: Path | None = None, now: float | None = None,
          issue: str = "") -> dict:
    path = path or configured_path()
    if path is None or slot not in {"morning", "evening"}:
        return {}
    now = time.time() if now is None else now
    date = datetime.fromtimestamp(now, ZONE).date().isoformat()
    previous = read(path)
    same = previous.get("slot") == slot and previous.get("berlin_date") == date
    review_selection = _review_selection(path)
    started = os.getenv("TAYVORIQ_RESEARCH_STARTED_AT_EPOCH", "")
    started_at = min(now, float(started)) if not review_selection and re.fullmatch(r"[0-9]{10}", started) else now
    first = float(previous.get("first_deferred_at_epoch") or now) if same else started_at
    run_key = os.getenv("TAYVORIQ_RESEARCH_RUN_KEY", "") if not review_selection else ""
    run_key = run_key if re.fullmatch(r"[1-9][0-9]*\.[1-9][0-9]*", run_key) else ""
    already_counted = bool(same and run_key and previous.get("last_research_attempt") == run_key)
    max_attempts = REVIEW_MAX_ATTEMPTS if review_selection else MAX_ATTEMPTS
    # A terminal regular slot is immutable. Technical repairs are validated in
    # CI and by a future scheduled slot; they never reopen the exhausted window.
    if not review_selection and same and previous.get("state") == "EXHAUSTED":
        return previous
    attempts = (int(previous.get("attempts") or 0) if same else 0) + (0 if already_counted else 1)
    sla = REVIEW_DEADLINE_SECONDS if review_selection else REGULAR_DEADLINE_SECONDS
    deadline = first + sla
    provider_next_at = next_at
    if review_selection and next_at is not None:
        # A user-requested replacement selection is a short interactive task.
        # Provider cooldowns may inform diagnostics, but never turn the UI into
        # an hours-long silent queue.
        next_at = min(next_at, now + REVIEW_RETRY_SECONDS)
    phase = 'REVIEW_FAST' if review_selection else 'NORMAL'
    status = "WAITING" if next_at is not None else "EXTERNAL_BLOCKER"
    last_retry = deadline if review_selection else deadline - 60
    if attempts >= max_attempts or now >= deadline or (next_at is not None and next_at > last_retry):
        status = "EXHAUSTED"
    result = {"schema": "tayvoriq-research-retry-v1", "state": status, "slot": slot,
              "berlin_date": date, "first_deferred_at_epoch": first,
              "attempts": attempts, "retry_at_epoch": next_at,
              "retry_phase": phase, "last_deferred_at_epoch": now,
              "provider_retry_at_epoch": provider_next_at,
              "max_attempts": max(attempts, max_attempts), "sla_seconds": sla,
              "valid_until_epoch": deadline,
              "reason": "PROVIDER_PAYMENT_OR_CONFIGURATION_BLOCKER" if next_at is None else "RESEARCH_DEFERRED_AFTER_BOUNDED_ATTEMPT",
              "quality_gates_weakened": False, "production_started": False}
    if review_selection:
        result["selection_id"] = review_selection
    if run_key:
        result["last_research_attempt"] = run_key
    if status == 'EXHAUSTED':
        result['reason'] = 'RESEARCH_RETRY_BUDGET_EXHAUSTED'
    if issue in ISSUE_DETAILS:
        result['last_issue'] = issue
        result['status_detail'] = ISSUE_DETAILS[issue]
    write(path, result)
    return result


def current(path: Path | None = None, *, now: float | None = None) -> dict:
    path = path or configured_path()
    state = read(path)
    now = time.time() if now is None else now
    if not state:
        return {}
    if state.get("schema") != "tayvoriq-research-retry-v1" or state.get("slot") not in {"morning", "evening"}:
        raise ValueError("RESEARCH_RETRY_STATE_INVALID")
    if state.get("state") == "DELIVERED":
        return {}
    if (state.get("berlin_date") != datetime.fromtimestamp(now, ZONE).date().isoformat()
            or now >= float(state.get("valid_until_epoch") or 0)):
        return {**state, "state": "EXHAUSTED", "reason": "RESEARCH_RETRY_EXPIRED"}
    return state


def due_slot(path: Path | None = None, *, now: float | None = None) -> str:
    now = time.time() if now is None else now
    state = current(path, now=now)
    if state.get("state") == "WAITING" and float(state.get("retry_at_epoch") or float("inf")) <= now:
        return state["slot"]
    return ""


def regular_process_seconds(slot: str, *, path: Path | None = None, now: float | None = None) -> int:
    """Keep time for persisting the result and delivering the Telegram card."""
    now = time.time() if now is None else now
    state = current(path, now=now)
    if (state.get("slot") == slot and state.get("sla_seconds") == REGULAR_DEADLINE_SECONDS
            and state.get("berlin_date") == datetime.fromtimestamp(now, ZONE).date().isoformat()):
        remaining = int(float(state["valid_until_epoch"]) - now) - 60
        return max(0, min(420, remaining))
    return 420


def terminal_slot(slot: str, now: datetime) -> bool:
    state = current(now=now.timestamp())
    return (state.get("berlin_date") == now.date().isoformat() and state.get("slot") == slot
            and state.get("state") in {"EXHAUSTED", "EXTERNAL_BLOCKER"})


def terminal_repair_attempt(marker: str, slot: str, now: datetime) -> str:
    """Never reopen a terminal regular slot after its bounded budget ended."""
    return ""


def confirmed_slot_delivery(slot: str, now: datetime, *, root: Path = Path(".")) -> bool:
    selection_id = f"{now:%Y%m%d}-{slot}-agentv2"
    receipt = read(root / ".automation/tayvoriq-agent-v2/deliveries" / f"{selection_id}.json")
    message_id = receipt.get("telegram_message_id")
    return (receipt.get("selection_id") == selection_id and receipt.get("telegram_delivery_verified") is True
            and type(message_id) is int and message_id > 0)


def valid_clock_tick(slot: str, day: str, scheduled: str, now: datetime) -> bool:
    return (slot in {"morning", "evening"} and day == now.date().isoformat()
            and scheduled.isascii() and scheduled.isdigit() and len(scheduled) == 10
            and 0 <= now.timestamp() - int(scheduled) < 20 * 60)


def clock_slot(slot: str, mode: str, day: str, scheduled: str, *, now: datetime) -> str:
    """A wakeup is a hint. The Orchestrator owns the current slot and receipt."""
    if not valid_clock_tick(slot, day, scheduled, now) or confirmed_slot_delivery(slot, now):
        return ""
    if mode == "retry":
        return slot if due_slot(now=now.timestamp()) == slot else ""
    start = 335 if slot == "morning" else 1145
    minute = now.hour * 60 + now.minute
    queue = current(now=now.timestamp())
    already_attempted = queue.get("berlin_date") == day and queue.get("slot") == slot
    return slot if mode == "catchup" and start <= minute < start + 30 and not already_attempted else ""


def review_due(selection_id: str, *, now: float | None = None) -> bool:
    path = review_path(selection_id)
    status = read(path.parent.parent / "review-trend-status" / path.name)
    if status.get("state") == "BLOCKED":
        return False
    if not path.is_file():
        return True
    state = current(path, now=now)
    due = (
        state.get("selection_id") == selection_id
        and state.get("state") == "WAITING"
        and float(state.get("retry_at_epoch") or float("inf")) <= (time.time() if now is None else now)
    )
    if due:
        return True
    return False


def delivered(slot: str) -> None:
    path = configured_path()
    if not path or slot not in {"morning", "evening"}:
        return
    now = time.time()
    day = datetime.fromtimestamp(now, ZONE).date().isoformat()
    state = read(path)
    if state.get('state') == 'DELIVERED' and state.get('slot') == slot and state.get('berlin_date') == day:
        return
    if state.get('berlin_date') == day and state.get('slot') != slot and state.get('state') == 'WAITING':
        return
    if state.get('slot') != slot or state.get('berlin_date') != day:
        if _review_selection(path):
            return
        state = {"schema": "tayvoriq-research-retry-v1", "slot": slot, "berlin_date": day}
    write(path, {**state, "state": "DELIVERED", "delivered_at_epoch": now})


def lifecycle(result: dict) -> dict:
    if result.get("state") != "IDLE":
        return result
    now = time.time()
    queue = current(now=now)
    # A missed or exhausted research slot from a previous Berlin day is
    # history. It must not turn today's otherwise idle lifecycle into BLOCKED.
    if not queue or queue.get("berlin_date") != datetime.fromtimestamp(now, ZONE).date().isoformat():
        return result
    return {**result, "action": "NONE",
            "state": "WAITING" if queue.get("state") == "WAITING" else "BLOCKED",
            "reason": "RESEARCH_PROVIDER_COOLDOWN" if queue.get("state") == "WAITING" else queue.get("reason"),
            "research_slot": queue["slot"], "research_retry_state": queue["state"],
            "research_retry_at_epoch": queue.get("retry_at_epoch") or 0,
            "research_retry_phase": queue.get("retry_phase") or "NORMAL",
            "research_attempts": int(queue.get("attempts") or 0),
            "research_max_attempts": int(queue.get("max_attempts") or MAX_ATTEMPTS),
            "next_system_step": ("AUTOMATIC_RESEARCH_RETRY" if queue.get("state") == "WAITING"
                                 else "RESEARCH_WINDOW_ENDED")}
