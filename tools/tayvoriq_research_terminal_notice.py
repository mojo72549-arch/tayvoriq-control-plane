"""Reconcile routine or explicit research terminal status with a verified Telegram receipt."""
import argparse
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from tayvoriq_provider_health_v1 import write
from tayvoriq_research_retry_v1 import ZONE, current


GIT_BOT = ["git", "-c", "user.name=github-actions[bot]", "-c",
           "user.email=github-actions[bot]@users.noreply.github.com"]


def persist(path, value):
    write(path, value)
    subprocess.run(["git", "add", "--", str(path)], check=True)
    subprocess.run([*GIT_BOT, "commit", "-m", "Record terminal research notification " + value["state"], "--", str(path)],
                   check=True)
    for attempt in range(3):
        # The observer commits checkpoints while this job runs. Rebasing the
        # notice creates a new commit and needs the same identity as commit.
        subprocess.run([*GIT_BOT, "pull", "--rebase", "--autostash", "origin", "main"], check=True)
        if subprocess.run(["git", "push", "origin", "HEAD:main"]).returncode == 0:
            return
        time.sleep(1 + attempt)
    raise RuntimeError("Unable to persist terminal notification state")


def main(selection_id=""):
    if selection_id:
        return explicit_notice(selection_id)
    queue = current()
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
    detail = queue.get("status_detail") or "Die Recherche konnte keine geprüfte Auswahl zustellen."
    label = "Morgenrecherche" if slot == "morning" else "Abendrecherche"
    message = (f"TAYVORIQ · {label} beendet ({day})\n\n{detail}\n"
               f"Versuche: {queue.get('attempts')} von {queue.get('max_attempts')}. "
               "Für diesen Slot ist keine Themenfreigabe offen.\n"
               f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run[1]}")
    evidence = {"slot": slot, "berlin_date": day, "research_state": state, "run_id": int(run[1]),
                "state": "SENDING", "telegram_delivery_verified": False}
    deliver(path, evidence, message)


def explicit_notice(selection_id):
    if not re.fullmatch(r"\d{8}-(morning|evening)-agentv2(?:-(?:r[1-9]\d?|c[a-f0-9]{8}))?", selection_id):
        raise ValueError("Invalid explicit research selection")
    scope = Path(".automation/tayvoriq-agent-v2")
    receipt_path = scope / "deliveries" / (selection_id + ".json")
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get("selection_id") == selection_id and receipt.get("telegram_delivery_verified") is True
                and type(receipt.get("telegram_message_id")) is int and receipt["telegram_message_id"] > 0):
            return
    pointer_path = Path("state/tayvoriq-control-center-research.json")
    if "-agentv2-c" in selection_id and pointer_path.is_file():
        pointer = json.loads(pointer_path.read_text())
        if pointer.get("schema") == "tayvoriq-control-center-research-v1" and (
                pointer.get("selection_id") != selection_id or pointer.get("cancel_requested_at")):
            return
    path = scope / "research-notices" / (selection_id + "-FAILED.json")
    if path.exists():
        return
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[1-9]\d*", run_id):
        raise ValueError("Invalid research run binding")
    evidence = {"selection_id": selection_id, "run_id": int(run_id), "research_state": "FAILED",
                "state": "SENDING", "telegram_delivery_verified": False}
    message = ("🔴 TAYVORIQ · Recherche angehalten\n\n"
               "Für diese Anfrage steht noch keine geprüfte Themenauswahl bereit.\n"
               f"Recherche: {selection_id}\n"
               "Details und weitere Schritte findest du im Control Center.")
    deliver(path, evidence, message)


def deliver(path, evidence, message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat = os.environ["TELEGRAM_CHAT_ID"]
    if not token or not chat:
        raise RuntimeError("Telegram configuration unavailable for terminal notice")
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-id", default="")
    main(parser.parse_args().selection_id)
