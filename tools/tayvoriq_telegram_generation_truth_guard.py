from __future__ import annotations

"""Truth guard for recovery-generation status reads.

A fresh Recovery Golden Path can start milliseconds before the recovery owner pushes
its new durable run binding to ``main``. In that window the job's checkout may hold
an older request snapshot (for example generation 3 bound to the failed run) while
the durable request is already generation 4 bound to the current run.

Telegram must never turn that stale snapshot into a confident generation number.
This module therefore suppresses only ``recovery_generation`` when the request
snapshot is not bound to the current Golden Path run. It never changes request
identity, sources, production state, recovery limits, or any quality gate.
"""

import json
from typing import Any


def _as_positive_int(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def sanitize_request_snapshot(text: str, current_run_id: Any) -> str:
    """Return JSON with stale recovery generation suppressed, never guessed."""

    try:
        data = json.loads(str(text or ""))
    except Exception:
        return text
    if not isinstance(data, dict):
        return text

    current = _as_positive_int(current_run_id)
    generation = _as_positive_int(data.get("recovery_generation"))
    if not current or not generation:
        return text

    bound = _as_positive_int(data.get("golden_path_run_id"))
    if bound == current:
        return text

    guarded = dict(data)
    guarded["recovery_generation"] = 0
    guarded["telegram_generation_truth_guard"] = {
        "status": "stale-snapshot-suppressed",
        "snapshot_golden_path_run_id": bound,
        "current_golden_path_run_id": current,
        "generation_was": generation,
        "generation_inferred": False,
        "quality_gates_changed": False,
    }
    return json.dumps(guarded, ensure_ascii=False, indent=2) + "\n"
