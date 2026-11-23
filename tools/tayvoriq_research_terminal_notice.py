"""Reconcile one routine research terminal status with a verified Telegram receipt."""
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from tayvoriq_provider_health_v1 import read, write
from tayvoriq_research_retry_v1 import ZONE, configured_path


def persist(path, value):
    write(path, value)
    subprocess.run(["git", "add", "--", str(path)], check=True)
    subprocess.run(["git", "-c", "user.name=github-actions[bot]", "-c",
                    "user.email=github-actions[bot]@users.noreply.github.com",
                    "commit", "-m", "Record terminal research notification " + value["state"], "--", str(path)],
                   check=True)
    for attempt in range(3):
        subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], check=True)
        if subprocess.run(["git", "push", "origin", "HEAD:main"]).returncode == 0:
            return
        time.sleep(1 + attempt)
    raise RuntimeError("Unable to persist terminal notification state")


def main():
    queue = read(configured_path())
    day = datetime.now(ZONE).date().isoformat()
    slot = queue.get("slot")
    state = queue.get("state")
    if (queue.get("schema") != "tayvoriq-research-retry-v1" or queue.get("berlin_date") != day
            or slot not in ("morning", "evening") or state not in ("EXHAUSTED", "EXTERNAL_BLOCKER")):
        return
    run = re.fullmatch(r"([1-9]\d*)\.[1-9]\d*", str(queue.get("last_research_attempt", "")))
    if not run:
        return
    path = Path(".automation/tayvoriq-agent-v2/research-notices") / f"{day}-{slot}-{state}.json"
    if path.exists():
        return
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat = os.environ["TELEGRAM_CHAT_ID"]
    if not token or not chat:
        raise RuntimeError("Telegram configuration unavailable for terminal notice")
    detail = queue.get("status_detail") or "Die Recherche konnte keine geprüfte Auswahl zustellen."
    label = "Morgenrecherche" if slot == "morning" else "Abendrecherche"
    message = (f"TAYVORIQ · {label} beendet ({day})\n\n{detail}\n"
               f"Versuche: {queue.get('attempts')} von {queue.get('max_attempts')}. "
               "Für diesen Slot ist keine Themenfreigabe offen.\n"
               f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run[1]}")
    evidence = {"slot": slot, "berlin_date": day, "research_state": state, "run_id": int(run[1]),
                "state": "SENDING", "telegram_delivery_verified": False}
    # All orchestrator jobs share a concurrency group. Commit the claim before sending:
    # an ambiguous network outcome must never lead to a duplicate notification.
    persist(path, evidence)
    request = urllib.request.Request("https://api.telegram.org/bot" + token + "/sendMessage",
                                     data=json.dumps({"chat_id": chat, "text": message,
                                                      "disable_web_page_preview": True}).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.load(response)
        result = data.get("result") or {}
        mid = result.get("message_id")
        if (data.get("ok") is not True or type(mid) is not int or mid <= 0
                or str((result.get("chat") or {}).get("id")) != chat):
            raise ValueError("missing matching Telegram receipt")
    except Exception as exc:
        persist(path, {**evidence, "state": "UNCONFIRMED", "error_type": type(exc).__name__})
        raise RuntimeError("Telegram delivery of terminal notice remains unconfirmed") from None
    persist(path, {**evidence, "state": "DELIVERED", "telegram_message_id": mid,
                   "telegram_delivery_verified": True, "delivered_at": datetime.now(ZONE).isoformat()})
    print(json.dumps({"event": "terminal_research_notice_delivered", "telegram_message_id": mid}))


if __name__ == "__main__":
    main()
