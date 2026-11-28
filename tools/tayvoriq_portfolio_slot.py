"""Use an explicitly reserved portfolio review when its Berlin slot opens."""
import json
import re
from datetime import datetime
from pathlib import Path

from tayvoriq_scheduled_render import ZONE, window


def read(path):
    if path.exists():
        return json.loads(path.read_text())
    return {}


def reserved(root, now):
    return reserved_for_slot(root, now.astimezone(ZONE).date(), window(now))


def reserved_for_slot(root, day, slot):
    key = f"{day.isoformat()}-{slot}"
    item = read(root / "state/tayvoriq-portfolio-slots.json").get("slots", {}).get(key)
    if not slot or not item or item.get("day") != day.isoformat() or item.get("slot") != slot:
        return None
    rid, run = item.get("request_id"), item.get("run_id")
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}", str(rid)) or type(run) is not int or run <= 0:
        return None
    request = read(root / "requests" / f"{rid}.json")
    receipt = request.get("production_completion") or {}
    decision = read(root / ".automation/tayvoriq-artifact-decisions" / f"{run}.json")
    if (request.get("request_id") != rid or decision.get("request_id") != rid or str(decision.get("review_id")) != str(run)
            or decision.get("state") not in {"PENDING", "APPROVED"} or receipt.get("state") != "REVIEW_READY"
            or receipt.get("reference_only") or receipt.get("quality_gates_weakened") is not False
            or run != request.get("golden_path_run_id") or run != receipt.get("golden_path_run_id")):
        return None
    if (not re.fullmatch(r"[a-f0-9]{64}", str(item.get("review_sha") or ""))
            or item["review_sha"] != (decision.get("files_sha256") or {}).get("short_youtube.mp4")
            or not item.get("source_context_sha256")
            or not (item["source_context_sha256"] == request.get("source_context_sha256") == decision.get("source_context_sha256"))
            or not (type(item.get("telegram_message_id")) is int and item["telegram_message_id"] > 0
                    and item["telegram_message_id"] == receipt.get("telegram_message_id") == decision.get("telegram_message_id"))):
        return None
    return {**item, "key": key, "topic": request.get("topic", ""), "state": decision["state"]}


def notify():
    from tayvoriq_research_terminal_notice import deliver
    root = Path(".")
    plan = reserved(root, datetime.now(ZONE))
    if not plan or plan["state"] != "PENDING":
        return
    run = plan["run_id"]
    if read(root / ".automation/tayvoriq-publications" / f"{run}.json"):
        return
    path = root / ".automation/portfolio-slot-notices" / f"{plan['key']}-{run}.json"
    if path.exists():
        return
    label = "Morgenslot" if plan["slot"] == "morning" else "Abendslot"
    message = (f"TAYVORIQ · Dein {label} ist vorproduziert\n\n{plan['topic']}\n"
               f"Vorschau: https://mojo72549-arch.github.io/mind-reset-daily/tayvoriq/runs/{run}/\n"
               "Freigeben kannst du das fertige Video in deinem Portfolio oder in der ursprünglichen Telegram-Nachricht.\n"
               "https://tayvoriq-control-center-mo61.vercel.app/#portfolios")
    deliver(path, {"state":"SENDING", "request_id":plan["request_id"], "run_id":run, "slot":plan["key"]}, message)


if __name__ == "__main__":
    notify()
