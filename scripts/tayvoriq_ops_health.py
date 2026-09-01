#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "mojo72549-arch/tayvoriq-control-plane")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
OUT = Path(os.environ.get("TAYVORIQ_OPS_STATE_PATH", "run-status/ops-health.json"))

TERMINAL_STATES = {"PUBLISHED", "REJECTED", "CANCELLED", "CANCELED", "ARCHIVED"}
USER_ACTION_TOKENS = ("EXTERNAL", "SECRET", "AUTH", "QUOTA", "MANUAL", "ACCOUNT", "BILLING")


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_ts(value):
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def api_get(path):
    url = path if path.startswith("http") else f"{API}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "tayvoriq-ops-health/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code}: {body[:500]}") from exc


def request_timestamp(data):
    candidates = [
        parse_ts(data.get("approved_at")),
        parse_ts(data.get("requested_at")),
    ]
    for entry in data.get("state_history") or []:
        if isinstance(entry, dict):
            candidates.append(parse_ts(entry.get("at")))
    recovery = data.get("codefix_recovery") or {}
    if isinstance(recovery, dict):
        for key in ("armed_at", "replayed_at", "updated_at"):
            candidates.append(parse_ts(recovery.get(key)))
    return max(candidates or [0.0])


def latest_state(data):
    history = [x for x in (data.get("state_history") or []) if isinstance(x, dict)]
    if history:
        return str(history[-1].get("state") or data.get("status") or "UNKNOWN").upper()
    return str(data.get("status") or "UNKNOWN").upper()


def load_current_request():
    candidates = []
    for path in Path("requests").glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(data.get("mode") or "").strip().lower() != "full":
            continue
        ts = request_timestamp(data)
        candidates.append((ts, path, data))
    if not candidates:
        return None, None
    active = [item for item in candidates if latest_state(item[2]) not in TERMINAL_STATES]
    chosen = max(active or candidates, key=lambda item: item[0])
    return chosen[1], chosen[2]


def resolve_run_id(data):
    if not data:
        return None
    recovery = data.get("codefix_recovery") or {}
    if isinstance(recovery, dict):
        for key in ("replay_run_id", "golden_path_run_id"):
            value = recovery.get(key)
            if str(value or "").isdigit():
                return int(value)
    value = data.get("golden_path_run_id")
    if str(value or "").isdigit():
        return int(value)
    history = [x for x in (data.get("state_history") or []) if isinstance(x, dict)]
    for entry in reversed(history):
        meta = entry.get("meta") or {}
        if not isinstance(meta, dict):
            continue
        for key in ("golden_path_run_id", "failed_run_id", "retry_of_run_id"):
            value = meta.get(key)
            if str(value or "").isdigit():
                return int(value)
    return None


def phase(step, names):
    if not step:
        return "pending"
    conclusion = str(step.get("conclusion") or "").lower()
    status = str(step.get("status") or "").lower()
    if conclusion == "failure":
        return "error"
    if status == "in_progress":
        return "running"
    if conclusion == "success":
        return "success"
    if conclusion == "skipped":
        return "skipped"
    return "pending"


def find_step(steps, *patterns):
    pats = [p.casefold() for p in patterns]
    for step in steps:
        name = str(step.get("name") or "").casefold()
        if any(p in name for p in pats):
            return step
    return None


def build_stages(steps):
    defs = [
        ("Freigabe gebunden", ("resolve approved x request",)),
        ("Quellen gesperrt", ("materialize immutable verified source context",)),
        ("Dublettenprüfung", ("block global duplicate content",)),
        ("Light Preflight", ("lightweight contract preflight",)),
        ("Dependencies", ("install production dependencies",)),
        ("Full Preflight", ("preflight",)),
        ("Produktion / Master", ("produce approved master",)),
        ("Publishable Output", ("assert publishable production output",)),
        ("Quality Audit", ("validate publication quality",)),
        ("Review-Seite", ("publish review page",)),
        ("Telegram Review", ("send telegram review",)),
    ]
    result = []
    for label, pats in defs:
        step = find_step(steps, *pats)
        result.append({
            "label": label,
            "status": phase(step, pats),
            "step_number": step.get("number") if step else None,
            "step_name": step.get("name") if step else None,
        })
    return result


def progress_from_stages(stages, run_status, conclusion):
    if conclusion == "success":
        return 100
    weights = [8, 16, 22, 30, 38, 45, 65, 72, 82, 92, 96]
    progress = 0
    for idx, stage in enumerate(stages):
        if stage["status"] in {"success", "skipped"}:
            progress = max(progress, weights[idx])
        elif stage["status"] in {"running", "error"}:
            progress = max(progress, weights[idx])
            break
        else:
            break
    if run_status in {"queued", "requested", "waiting"}:
        return max(progress, 3)
    return progress


def health_color(run_status, conclusion, run_id):
    if not run_id:
        return "unknown"
    if run_status in {"queued", "requested", "waiting", "in_progress"}:
        return "yellow"
    if conclusion == "success":
        return "green"
    if conclusion in {"failure", "timed_out", "cancelled", "canceled", "action_required"}:
        return "red"
    return "unknown"


def load_json(path):
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def incident_signature(run_id, failed_step, failure_state):
    return f"{run_id or 'none'}:{(failed_step or {}).get('number') or 'none'}:{failure_state or 'none'}"


def main():
    previous = load_json(OUT) or {}
    request_path, request_data = load_current_request()
    run_id = resolve_run_id(request_data)
    run = {}
    jobs = []
    api_error = None
    if run_id:
        try:
            run = api_get(f"/repos/{REPO}/actions/runs/{run_id}")
            jobs_payload = api_get(f"/repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100")
            jobs = jobs_payload.get("jobs") or []
        except Exception as exc:
            api_error = str(exc)

    orchestrate = next((j for j in jobs if str(j.get("name") or "").lower() == "orchestrate"), jobs[0] if jobs else {})
    steps = orchestrate.get("steps") or []
    failed_step = next((s for s in steps if str(s.get("conclusion") or "").lower() == "failure"), None)
    running_step = next((s for s in steps if str(s.get("status") or "").lower() == "in_progress"), None)
    stages = build_stages(steps)

    run_status = str(run.get("status") or ("unknown" if api_error else "missing")).lower()
    conclusion = str(run.get("conclusion") or "").lower() or None
    overall = health_color(run_status, conclusion, run_id)
    if api_error:
        overall = "unknown"

    recovery = (request_data or {}).get("codefix_recovery") or {}
    if not isinstance(recovery, dict):
        recovery = {}
    failure_state = str(recovery.get("failure_state") or "") or None
    user_action_required = bool(failure_state and any(token in failure_state.upper() for token in USER_ACTION_TOKENS))
    self_heal_status = str(recovery.get("status") or "IDLE")

    telegram_steps = [s for s in steps if "telegram" in str(s.get("name") or "").casefold()]
    telegram_failed = next((s for s in telegram_steps if str(s.get("conclusion") or "").lower() == "failure"), None)
    telegram_success = next((s for s in reversed(telegram_steps) if str(s.get("conclusion") or "").lower() == "success"), None)
    if telegram_failed:
        telegram_status = "red"
        telegram_detail = f"Fehler bei: {telegram_failed.get('name')}"
    elif telegram_success:
        telegram_status = "green"
        telegram_detail = f"Zuletzt erfolgreich: {telegram_success.get('name')}"
    else:
        telegram_status = "yellow" if run_id else "unknown"
        telegram_detail = "Noch kein bestätigter Telegram-Schritt im aktuellen Run"

    green_pointer = load_json(".github/state/tayvoriq-production-green.json") or {}
    green_ok = bool(green_pointer.get("full_preflight_passed") is True and green_pointer.get("quality_gates_weakened") is False)
    green_sha = str(green_pointer.get("implementation_sha") or "")

    last_completed = None
    for s in reversed(steps):
        if str(s.get("conclusion") or "").lower() == "success":
            last_completed = s
            break

    incident = None
    if overall == "red" or failure_state:
        incident = {
            "signature": incident_signature(run_id, failed_step, failure_state),
            "severity": "critical" if overall == "red" else "warning",
            "failure_state": failure_state,
            "failed_step": failed_step.get("name") if failed_step else None,
            "failed_step_number": failed_step.get("number") if failed_step else None,
            "self_heal_status": self_heal_status,
            "same_generation_replay_required": bool(recovery.get("same_generation_replay_required")),
            "quality_gates_weakened": bool(recovery.get("quality_gates_weakened", False)),
            "user_action_required": user_action_required,
        }

    events = []
    for entry in reversed((request_data or {}).get("state_history") or []):
        if not isinstance(entry, dict):
            continue
        meta = entry.get("meta") or {}
        events.append({
            "at": entry.get("at"),
            "title": str(entry.get("state") or "Status"),
            "detail": str(meta.get("failure_state") or meta.get("reason") or entry.get("actor") or ""),
        })
        if len(events) >= 6:
            break
    if failed_step:
        events.insert(0, {
            "at": run.get("updated_at"),
            "title": "Workflow-Fehler",
            "detail": str(failed_step.get("name") or "Unbekannter Schritt"),
        })

    state = {
        "schema": "tayvoriq-ops-health-v1",
        "generated_at": now_iso(),
        "overall": overall,
        "intervention_count": 1 if user_action_required else 0,
        "user_action_required": user_action_required,
        "api_error": api_error,
        "request": {
            "request_id": (request_data or {}).get("request_id"),
            "topic": (request_data or {}).get("topic"),
            "trend_id": (request_data or {}).get("trend_id"),
            "slot": (request_data or {}).get("slot"),
            "state": latest_state(request_data or {}),
            "recovery_generation": int(recovery.get("recovery_generation") or 0),
            "source_count": len(((request_data or {}).get("source_context") or {}).get("sources") or []),
            "quality_gates_weakened": bool(((request_data or {}).get("source_context") or {}).get("quality_gates_weakened", False)),
            "path": str(request_path) if request_path else None,
        },
        "run": {
            "id": run_id,
            "status": run_status,
            "conclusion": conclusion,
            "html_url": run.get("html_url") if run else (f"https://github.com/{REPO}/actions/runs/{run_id}" if run_id else None),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "attempt": run.get("run_attempt"),
            "progress": progress_from_stages(stages, run_status, conclusion),
            "current_step": running_step.get("name") if running_step else None,
            "last_successful_step": last_completed.get("name") if last_completed else None,
            "failed_step": failed_step.get("name") if failed_step else None,
            "failed_step_number": failed_step.get("number") if failed_step else None,
            "stages": stages,
        },
        "healthchecks": [
            {
                "name": "Golden Path",
                "status": overall,
                "detail": (failed_step.get("name") if failed_step else (running_step.get("name") if running_step else (conclusion or run_status))),
            },
            {
                "name": "Production Green",
                "status": "green" if green_ok else "red",
                "detail": (green_sha[:12] + "…") if green_sha else "Pointer fehlt",
            },
            {
                "name": "Self-Heal",
                "status": "yellow" if self_heal_status not in {"", "IDLE", "NONE"} and overall != "green" else "green",
                "detail": self_heal_status,
            },
            {
                "name": "Telegram",
                "status": telegram_status,
                "detail": telegram_detail,
            },
            {
                "name": "Quality Gates",
                "status": "red" if bool(recovery.get("quality_gates_weakened")) else "green",
                "detail": "Nicht gelockert" if not bool(recovery.get("quality_gates_weakened")) else "WARNUNG: gelockert",
            },
        ],
        "incident": incident,
        "telegram": {
            "status": telegram_status,
            "detail": telegram_detail,
            "last_step": telegram_success.get("name") if telegram_success else None,
        },
        "recovery": {
            "status": self_heal_status,
            "failure_state": failure_state,
            "failed_run_id": recovery.get("failed_run_id"),
            "replay_run_id": recovery.get("replay_run_id"),
            "recovery_generation": int(recovery.get("recovery_generation") or 0),
            "same_generation_replay_required": bool(recovery.get("same_generation_replay_required")),
            "quality_gates_weakened": bool(recovery.get("quality_gates_weakened", False)),
        },
        "events": events[:8],
    }

    previous_overall = str(previous.get("overall") or "unknown")
    previous_incident = ((previous.get("incident") or {}).get("signature") if isinstance(previous.get("incident"), dict) else None)
    previous_recovery = str(((previous.get("recovery") or {}).get("status") if isinstance(previous.get("recovery"), dict) else "") or "")
    current_incident = incident.get("signature") if incident else None
    notify = (
        previous_overall != overall
        or previous_incident != current_incident
        or previous_recovery != self_heal_status
    ) and (overall in {"red", "yellow", "green"})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as handle:
            handle.write(f"notify={'true' if notify else 'false'}\n")
            handle.write(f"overall={overall}\n")
            handle.write(f"run_id={run_id or ''}\n")
            handle.write(f"user_action_required={'true' if user_action_required else 'false'}\n")
            handle.write(f"incident_signature={current_incident or ''}\n")
    print(json.dumps({"overall": overall, "run_id": run_id, "notify": notify, "api_error": api_error}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
