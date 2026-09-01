#!/usr/bin/env python3
import json
import os
from pathlib import Path

PATH = Path(os.environ.get("TAYVORIQ_OPS_STATE_PATH", "run-status/ops-health.json"))
FAILURES = {"failure", "timed_out", "cancelled", "canceled", "action_required"}


def same_id(a, b):
    try:
        return int(a) == int(b)
    except Exception:
        return False


def main():
    state = json.loads(PATH.read_text(encoding="utf-8"))
    run = state.get("run") or {}
    recovery = state.get("recovery") or {}
    incident = state.get("incident") or {}

    source_status = str(recovery.get("status") or "IDLE").upper()
    run_status = str(run.get("status") or "").lower()
    conclusion = str(run.get("conclusion") or "").lower()
    replay_is_current = same_id(recovery.get("replay_run_id"), run.get("id"))

    effective = source_status
    inferred = False
    detail = source_status
    health = "green"

    if run_status in {"queued", "requested", "waiting", "in_progress"} and replay_is_current:
        effective = "REPLAY_RUNNING"
        detail = "Recovery-Replay läuft"
        health = "yellow"
    elif conclusion in FAILURES and replay_is_current and source_status in {
        "REPLAY_DISPATCHED", "DISPATCHED", "REPLAY_RUNNING"
    }:
        effective = "REPLAY_FAILED_CODEFIX_REQUIRED"
        detail = "Recovery-Replay fehlgeschlagen · Codefix erforderlich"
        health = "red"
        inferred = True
    elif source_status not in {"", "IDLE", "NONE"} and str(state.get("overall") or "") != "green":
        health = "yellow"

    recovery["source_status"] = source_status
    recovery["status"] = effective
    recovery["inferred_from_run_terminal_state"] = inferred
    recovery["needs_codefix"] = effective == "REPLAY_FAILED_CODEFIX_REQUIRED"
    state["recovery"] = recovery

    if incident:
        incident["self_heal_status"] = effective
        incident["recovery_replay_failed"] = effective == "REPLAY_FAILED_CODEFIX_REQUIRED"
        state["incident"] = incident

    for item in state.get("healthchecks") or []:
        if str(item.get("name") or "").casefold() == "self-heal":
            item["status"] = health
            item["detail"] = detail
            break

    if effective == "REPLAY_FAILED_CODEFIX_REQUIRED":
        events = state.get("events") or []
        marker = {
            "at": run.get("updated_at"),
            "title": "Recovery-Replay fehlgeschlagen",
            "detail": f"Run {run.get('id')} · interner Codefix erforderlich · kein Eingriff von dir",
        }
        if not events or events[0].get("title") != marker["title"] or events[0].get("at") != marker["at"]:
            state["events"] = [marker] + events[:7]

    PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    changed = effective != source_status
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as handle:
            handle.write(f"notify={'true' if changed else 'false'}\n")
            handle.write(f"effective_self_heal={effective}\n")

    print(json.dumps({
        "effective_self_heal": effective,
        "source_status": source_status,
        "changed": changed,
        "replay_is_current": replay_is_current,
        "run_conclusion": conclusion,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
