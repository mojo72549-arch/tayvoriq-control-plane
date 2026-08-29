#!/usr/bin/env python3
"""Pure notification cadence rules for TAYVORIQ Telegram progress.

The watchdog may poll every three minutes. Polling itself is not a user-visible
state change, so Telegram only receives rare long-running thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass


HEARTBEAT_STAGES = {"render_heartbeat", "checkpoint_heartbeat"}
# Keep internal polling quiet. One 45-minute threshold reports a genuinely long
# production without turning regular liveness checks into operator noise.
HEARTBEAT_NOTIFY_MINUTES = (45,)


@dataclass(frozen=True)
class NotificationDecision:
    send: bool
    reason: str


def heartbeat_due(stage: str, elapsed_minutes: int) -> bool:
    if stage not in HEARTBEAT_STAGES:
        return True
    elapsed = max(0, int(elapsed_minutes or 0))
    return elapsed in HEARTBEAT_NOTIFY_MINUTES


def decision(stage: str, elapsed_minutes: int) -> NotificationDecision:
    if stage not in HEARTBEAT_STAGES:
        return NotificationDecision(True, "real_state_change")
    if heartbeat_due(stage, elapsed_minutes):
        return NotificationDecision(True, "long_running_threshold_crossed")
    return NotificationDecision(False, "silent_liveness_poll")
