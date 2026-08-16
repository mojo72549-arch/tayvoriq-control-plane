#!/usr/bin/env python3
"""Send concise Telegram production progress at verified workflow milestones."""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_POLICY = Path("state/tayvoriq-notification-policy.json")
TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Milestone:
    percent: int
    title: str
    completed: str
    next_step: str


MILESTONES = {
    "sources_locked": Milestone(
        20,
        "Fakten gesichert",
        "Serienfolge, Fakten und mindestens zwei Quellen sind verbindlich geprüft.",
        "Technischer Preflight und Produktionsvorbereitung.",
    ),
    "production_active": Milestone(
        45,
        "Produktion läuft",
        "Preflight und Produktionsvertrag sind bestanden.",
        "Skript, tiefe Sprecherstimme, Visuals, Untertitel und 9:16-Render werden erstellt und geprüft.",
    ),
    "master_ready": Milestone(
        75,
        "Videomaster erstellt",
        "Ein wiederverwendbarer YouTube-/TikTok-Master liegt vor.",
        "Finale Sprach-, Bild-, Fakten- und Plattform-Gates.",
    ),
    "quality_passed": Milestone(
        90,
        "Qualitätsprüfung bestanden",
        "Stimme, Bild, Fakten und beide Plattformpakete haben die Pflicht-Gates bestanden.",
        "Review-Seite und Telegram-Videofreigabe.",
    ),
}


def read_policy(path: Path = DEFAULT_POLICY) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def progress_enabled(path: Path = DEFAULT_POLICY) -> bool:
    value = read_policy(path).get("production_progress_enabled")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in TRUE_VALUES


def should_send(path: Path, run_attempt: int) -> bool:
    return progress_enabled(path) and int(run_attempt) <= 1


def clean_topic(value: str) -> str:
    return " ".join(str(value or "").split()).strip()[:180] or "Freigegebene TAYVORIQ-Folge"


def build_payload(stage: str, topic: str, run_id: str, chat_id: str) -> dict:
    milestone = MILESTONES[stage]
    lines = [
        f"🟣 TAYVORIQ {milestone.percent} % · {milestone.title}",
        "",
        f"Thema: {clean_topic(topic)}",
        f"Run: {str(run_id or 'unbekannt').strip()}",
        "",
        f"✅ Erledigt: {milestone.completed}",
        f"➡️ Als Nächstes: {milestone.next_step}",
        "",
        "Für dich: ✅ Keine Aktion nötig.",
    ]
    return {
        "chat_id": str(chat_id).strip(),
        "text": "\n".join(lines),
        "disable_web_page_preview": True,
    }


def telegram_send(token: str, payload: dict) -> int:
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token.strip()}/sendMessage",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    message_id = int((result.get("result") or {}).get("message_id") or 0)
    if result.get("ok") is not True or message_id <= 0:
        raise RuntimeError(f"Telegram progress delivery was not verified: {result}")
    return message_id


def parse_attempt(value: str) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=tuple(MILESTONES), required=True)
    parser.add_argument("--topic", default=os.getenv("TOPIC", ""))
    parser.add_argument("--run-id", default=os.getenv("GITHUB_RUN_ID", ""))
    parser.add_argument("--run-attempt", default=os.getenv("GITHUB_RUN_ATTEMPT", "1"))
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()

    attempt = parse_attempt(args.run_attempt)
    if not progress_enabled(args.policy):
        print(json.dumps({"status": "disabled", "stage": args.stage}))
        return 0
    if attempt > 1:
        print(json.dumps({"status": "suppressed_rerun", "stage": args.stage, "run_attempt": attempt}))
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_PROGRESS_SECRETS_MISSING")

    payload = build_payload(args.stage, args.topic, args.run_id, chat_id)
    message_id = telegram_send(token, payload)
    print(json.dumps({
        "status": "sent",
        "stage": args.stage,
        "percent": MILESTONES[args.stage].percent,
        "telegram_message_id": message_id,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
