"""Bounded retry of an unapproved trend slot; never produces or publishes."""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from tayvoriq_provider_health_v1 import read, write

ZONE = ZoneInfo("Europe/Berlin")


def configured_path() -> Path | None:
    value = os.getenv("TAYVORIQ_RESEARCH_RETRY_FILE")
    return Path(value) if value else None


def defer(slot: str, next_at: float | None, *, path: Path | None = None, now: float | None = None) -> dict:
    path = path or configured_path()
    if path is None or slot not in {"morning", "evening"}:
        return {}
    now = time.time() if now is None else now
    date = datetime.fromtimestamp(now, ZONE).date().isoformat()
    previous = read(path)
    same = previous.get("slot") == slot and previous.get("berlin_date") == date
    first = float(previous.get("first_deferred_at_epoch") or now) if same else now
    attempts = int(previous.get("attempts") or 0) + 1 if same else 1
    deadline = first + 6 * 3600
    status = "WAITING" if next_at is not None else "EXTERNAL_BLOCKER"
    if attempts >= 8 or now >= deadline or (next_at is not None and next_at >= deadline):
        status = "EXHAUSTED"
    result = {"schema": "tayvoriq-research-retry-v1", "state": status, "slot": slot,
              "berlin_date": date, "first_deferred_at_epoch": first,
              "attempts": attempts, "retry_at_epoch": next_at,
              "valid_until_epoch": deadline,
              "reason": "PROVIDER_PAYMENT_OR_CONFIGURATION_BLOCKER" if next_at is None else "RESEARCH_DEFERRED_AFTER_BOUNDED_ATTEMPT",
              "quality_gates_weakened": False, "production_started": False}
    if status == 'EXHAUSTED':
        result['reason'] = 'RESEARCH_RETRY_BUDGET_EXHAUSTED'
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


def delivered(slot: str) -> None:
    path = configured_path()
    state = current(path)
    if path and state and state.get("slot") == slot:
        write(path, {**state, "state": "DELIVERED", "delivered_at_epoch": time.time()})


def lifecycle(result: dict) -> dict:
    if result.get("state") != "IDLE":
        return result
    queue = current()
    if not queue:
        return result
    return {**result, "action": "NONE",
            "state": "WAITING" if queue.get("state") == "WAITING" else "BLOCKED",
            "reason": "RESEARCH_PROVIDER_COOLDOWN" if queue.get("state") == "WAITING" else queue.get("reason"),
            "research_slot": queue["slot"], "research_retry_state": queue["state"],
            "research_retry_at_epoch": queue.get("retry_at_epoch") or 0}
