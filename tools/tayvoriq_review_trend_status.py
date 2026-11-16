"""Publish the operator-facing status of one rejected-review trend request."""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(".automation/tayvoriq-agent-v2")
STATES = {
    "SEARCHING": "TAYVORIQ · Neue Trendauswahl angefordert. Die Recherche läuft. Du musst nichts tun.",
    "WAITING": "TAYVORIQ · Noch keine belastbare Trendauswahl. Der Orchestrator versucht es innerhalb von fünf Minuten erneut.",
    "BLOCKED": "TAYVORIQ · Die 10-Minuten-Grenze ist erreicht. Eine belastbare neue Trendauswahl konnte nicht erstellt werden. Der konkrete Blocker steht im Control Center.",
}


def load(path):
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def status_for(selection, phase, retry, deferred, now):
    if phase == "start":
        return "SEARCHING", None
    slot = selection.split("-")[1]
    retry_at = retry.get("retry_at_epoch")
    if (deferred and retry.get("state") == "WAITING" and retry.get("slot") == slot
            and type(retry_at) in (int, float)
            and now < retry.get("valid_until_epoch", 0) and retry_at > 0):
        return "WAITING", datetime.fromtimestamp(retry_at, timezone.utc).isoformat()
    return "BLOCKED", None


def send_notice(state, retry_at):
    text = STATES[state]
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
    selection, phase = sys.argv[1:]
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
    deferred = Path("/tmp/tayvoriq-research-deferred.json").is_file()
    now = datetime.now(timezone.utc)
    state, retry_at = status_for(selection, phase, retry, deferred, now.timestamp())
    if state not in notices:
        try:
            notices[state] = send_notice(state, retry_at)
        except Exception as exc:
            print(f"Telegram status notice unavailable: {type(exc).__name__}", file=sys.stderr)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "tayvoriq-review-trend-status-v1",
        "selection_id": selection, "state": state, "retry_at": retry_at,
        "attempts": int(retry.get("attempts") or 0),
        "max_attempts": int(retry.get("max_attempts") or 0),
        "reason": retry.get("reason"),
        "sla_seconds": int(retry.get("sla_seconds") or 600),
        "updated_at": now.isoformat(), "telegram_notices": notices}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
