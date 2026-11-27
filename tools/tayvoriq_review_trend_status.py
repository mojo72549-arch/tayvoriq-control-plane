"""Publish the operator-facing status of one rejected-review trend request."""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(".automation/tayvoriq-agent-v2")
STATES = {
    "SEARCHING": "TAYVORIQ · Neue Trendauswahl angefordert. Die Recherche läuft. Du musst nichts tun.",
    "WAITING": "TAYVORIQ · Noch keine belastbare Trendauswahl. Der Orchestrator versucht es innerhalb von fünf Minuten erneut.",
    "BLOCKED": "TAYVORIQ · Die Ersatzrecherche ist beendet.",
}
BLOCKERS = {
    "RESEARCH_RETRY_EXPIRED": "Das Zeitfenster ist abgelaufen. Die neue Auswahl wurde in Telegram nicht bestätigt.",
    "SOURCE_QUALITY": "Die gefundenen Themen bestanden die Quellen- oder redaktionelle Prüfung nicht.",
    "RESEARCH_TIMEOUT": "Die Recherche konnte innerhalb ihres Zeitlimits keine prüfbare Auswahl liefern.",
    "PROVIDER_LIMIT": "Die verfügbaren Recherche-Anbieter sind durch Kontingente oder Zahlungsstatus blockiert.",
    "TELEGRAM_DELIVERY_UNCONFIRMED": "Die Trendauswahl wurde geprüft, ihre Zustellung in Telegram konnte nicht bestätigt werden.",
    "RESEARCH_FAILED": "Der Recherche-Workflow ist vor einer bestätigten Trendauswahl abgebrochen.",
}
DEFERRED = Path("/tmp/tayvoriq-research-deferred.json")


def load(path):
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def deadline_for(previous, retry, requested_at, now):
    candidates = [float(retry["valid_until_epoch"])] if retry.get("valid_until_epoch") else []
    for stamp, offset in ((previous.get("deadline_at"), 0), (requested_at, 600)):
        if stamp:
            value = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
            candidates.append(value + offset)
    return min(candidates, default=now + 600)


def needs_expiry(plan, now):
    if not plan or not plan.get("new_trends_requested") or plan.get("selection_delivered"):
        return False
    selection = plan["selection_id"]
    if not re.fullmatch(r"review-(morning|evening)-[1-9][0-9]{0,19}", selection):
        return False
    state = load(ROOT / "review-trend-status" / f"{selection}.json")
    if state.get("state") == "BLOCKED":
        return not (state.get("telegram_notices") or {}).get("BLOCKED")
    retry = load(ROOT / "research-retries" / f"{selection}.json")
    return now >= deadline_for(state, retry, plan.get("research_requested_at"), now)


def research(command, deadline, *, clock=time.time, run=subprocess.run, pause=time.sleep):
    """Give interactive research bounded attempts within the same Orchestrator run."""
    if 'tools/tayvoriq_contabo_research.py' in command:
        remaining = int(deadline - clock() - 30)
        if remaining <= 0:
            return 124, 0
        try:
            result = run([*command, '--wait-seconds', str(min(remaining, 540))], timeout=remaining, check=False)
        except subprocess.TimeoutExpired:
            return 124, 1
        return result.returncode, 1
    for attempt in range(1, 4):
        remaining = deadline - clock() - 30
        if remaining <= 0:
            return 124, attempt - 1
        try:
            result = run(command, timeout=min(145, remaining), check=False)
        except subprocess.TimeoutExpired:
            return 124, attempt
        if result.returncode == 0:
            return 0, attempt
        failure = load(DEFERRED)
        errors = failure.get("errors") or []
        retryable = any("failed:" in line and any(word in line.lower() for word in
                        ("timed out", "temporarily unavailable", "connection reset", "http 5")) for line in errors)
        if not retryable or attempt == 3 or deadline - clock() < 55:
            return result.returncode, attempt
        pause(8)


def blocker_for(phase, retry, deferred, contract, telegram):
    if phase == "expire":
        return "RESEARCH_RETRY_EXPIRED"
    if contract == "success" and telegram != "success":
        return "TELEGRAM_DELIVERY_UNCONFIRMED"
    if contract == "failure":
        return "SOURCE_QUALITY"
    if deferred.get("result") == "TIMEOUT":
        return "RESEARCH_TIMEOUT"
    errors = " ".join(deferred.get("errors") or []).lower()
    if "source contract insufficient" in errors or "source pool too small" in errors or deferred.get("result") == "REJECTED":
        return "SOURCE_QUALITY"
    if retry.get("reason") == "PROVIDER_PAYMENT_OR_CONFIGURATION_BLOCKER" or "cooldown/payment" in errors:
        return "PROVIDER_LIMIT"
    return "RESEARCH_FAILED"


def send_notice(state, retry_at, detail=None):
    text = STATES[state]
    if detail:
        text += " " + detail
    if retry_at:
        local = datetime.fromisoformat(retry_at).astimezone(ZoneInfo("Europe/Berlin"))
        text += f" Nächster Versuch frühestens ab {local:%H:%M} Uhr."
    text += "\nhttps://tayvoriq-control-center.vercel.app/review"
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    data = json.dumps({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text,
                       "link_preview_options": {"is_disabled": True}}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=12) as response:
        payload = json.load(response)
    mid = payload.get("result", {}).get("message_id")
    if payload.get("ok") is not True or type(mid) is not int or mid <= 0:
        raise ValueError("Unconfirmed Telegram receipt")
    return mid


def main():
    selection, phase, *command = sys.argv[1:]
    if not re.fullmatch(r"review-(morning|evening)-[1-9][0-9]{0,19}", selection):
        raise SystemExit("Invalid review selection")
    delivery = load(ROOT / "deliveries" / (selection + ".json"))
    if (delivery.get("selection_id") == selection and delivery.get("telegram_delivery_verified") is True
            and type(delivery.get("telegram_message_id")) is int and delivery["telegram_message_id"] > 0):
        return
    path = ROOT / "review-trend-status" / (selection + ".json")
    previous = load(path)
    notices = previous.get("telegram_notices") or {}
    retry = load(Path(os.environ["TAYVORIQ_RESEARCH_RETRY_FILE"]))
    now = datetime.now(timezone.utc)
    deadline = deadline_for(previous, retry, os.getenv("TAYVORIQ_REVIEW_REQUESTED_AT"), now.timestamp())
    if phase == "require-time":
        raise SystemExit(0 if now.timestamp() + 12 < deadline else 1)
    if phase == "research":
        os.environ["TAYVORIQ_GDELT_BUDGET_SECONDS"] = "16"
        os.environ["TAYVORIQ_GDELT_TIMEOUT_SECONDS"] = "6"
        exit_code, attempts = research(command, deadline)
        payload = load(DEFERRED)
        if exit_code == 124:
            payload["result"] = "TIMEOUT"
        elif exit_code and not payload:
            payload["result"] = "REJECTED"
        payload["workflow_attempts"] = attempts
        DEFERRED.write_text(json.dumps(payload), encoding="utf-8")
        raise SystemExit(exit_code)
    if phase == "start" and previous.get("state") == "BLOCKED":
        return
    deferred = load(DEFERRED)
    state = "SEARCHING" if phase == "start" else "BLOCKED"
    retry_at = None
    reason = previous.get("reason") if previous.get("state") == "BLOCKED" else None
    if state == "BLOCKED" and not reason:
        reason = blocker_for(phase, retry, deferred, os.getenv("APPROVAL_CONTRACT"), os.getenv("TELEGRAM_OUTCOME"))
    detail = BLOCKERS.get(reason) if state == "BLOCKED" else None
    if type(notices.get(state)) is not int or notices[state] <= 0:
        try:
            notices[state] = send_notice(state, retry_at, detail)
        except Exception as exc:
            print(f"Telegram status notice unavailable: {type(exc).__name__}", file=sys.stderr)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "tayvoriq-review-trend-status-v1",
        "selection_id": selection, "state": state, "retry_at": retry_at,
        "attempts": int(deferred.get("workflow_attempts") or retry.get("attempts") or previous.get("attempts") or 0),
        "max_attempts": 3,
        "reason": reason,
        "detail": detail,
        "deadline_at": datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
        "sla_seconds": int(retry.get("sla_seconds") or 600),
        "updated_at": now.isoformat(), "telegram_notices": notices}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
