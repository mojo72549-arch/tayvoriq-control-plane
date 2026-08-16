#!/usr/bin/env python3
"""Send verified Telegram production status without inventing progress."""
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
    percent: int | None
    title: str
    completed: str
    next_step: str


MILESTONES = {
    "recovery_started": Milestone(
        30,
        "Sichere Reparatur gestartet",
        "Der vorherige Lauf wurde sicher gestoppt; es wurde nichts veröffentlicht.",
        "Die erkannte Ursache wird repariert und derselbe freigegebene Auftrag neu gestartet.",
    ),
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
    "render_heartbeat": Milestone(
        45,
        "Produktion arbeitet weiter",
        "Der Workflow ist aktiv; seit dem letzten geprüften Meilenstein wurde kein neuer Fehler erkannt.",
        "Die rechenintensive Sprecher-, Visual-, Untertitel- und Renderphase läuft weiter.",
    ),
    "checkpoint_repair": Milestone(
        60,
        "Master gesichert · gezielte Reparatur",
        "Ein wiederverwendbarer Master ist dauerhaft gesichert; es wurde noch nichts veröffentlicht.",
        "Nur fehlgeschlagene lokale Sprach-, Bild- oder Audit-Prüfpunkte werden repariert.",
    ),
    "checkpoint_heartbeat": Milestone(
        60,
        "Checkpoint-Reparatur arbeitet weiter",
        "Master und Quellen bleiben gesichert; seit dem Reparaturstart wurde kein neuer Fehler erkannt.",
        "Die verbliebenen lokalen Prüfpunkte werden weiter repariert und erneut gemessen.",
    ),
    "audio_recovery": Milestone(
        None,
        "Audio-Gate hat sicher gestoppt",
        "Fakten, Serienfolge und Dublettenprüfung bleiben gültig; es wurde nichts veröffentlicht.",
        "Nur der Pfad für die tiefe Sprecherstimme wird rückgekoppelt repariert und erneut geprüft.",
    ),
    "duplicate_blocked": Milestone(
        None,
        "Dublette verhindert",
        "Der Auftrag wurde vor Render und Upload blockiert; es wurde nichts veröffentlicht.",
        "Ein klar unterscheidbarer Themenwinkel muss vor einer neuen Produktion freigegeben werden.",
    ),
    "technical_stop": Milestone(
        None,
        "Technischer Stopp erkannt",
        "Der Lauf wurde fail-closed beendet; es wurde nichts veröffentlicht.",
        "Die konkrete Ursache wird gesichert und nur der betroffene technische Pfad wird repariert.",
    ),
}


REPLAY_SUPPRESSED_STAGES = {"sources_locked", "production_active"}


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


def should_send(path: Path, run_attempt: int, stage: str = "") -> bool:
    if not progress_enabled(path):
        return False
    return int(run_attempt) <= 1 or stage not in REPLAY_SUPPRESSED_STAGES


def clean_topic(value: str) -> str:
    return " ".join(str(value or "").split()).strip()[:180] or "Freigegebene TAYVORIQ-Folge"


def build_payload(
    stage: str,
    topic: str,
    run_id: str,
    chat_id: str,
    *,
    elapsed_minutes: int = 0,
    failure_state: str = "",
    detail: str = "",
) -> dict:
    milestone = MILESTONES[stage]
    heading = f"TAYVORIQ {milestone.percent} %" if milestone.percent is not None else "TAYVORIQ"
    icon = "🔄" if stage == "render_heartbeat" else ("🟠" if stage in {"audio_recovery", "technical_stop"} else "🟣")
    if stage in {"checkpoint_repair", "checkpoint_heartbeat"}:
        icon = "🔧"
    if stage == "duplicate_blocked":
        icon = "🛑"
    lines = [
        f"{icon} {heading} · {milestone.title}",
        "",
        f"Thema: {clean_topic(topic)}",
        f"Run: {str(run_id or 'unbekannt').strip()}",
    ]
    if stage in {"render_heartbeat", "checkpoint_heartbeat"}:
        phase = "Renderphase" if stage == "render_heartbeat" else "Reparaturphase"
        lines.extend(["", f"⏱️ {phase} aktiv seit: {max(1, int(elapsed_minutes or 0))} Minuten"])
    if failure_state:
        lines.extend(["", f"Status: {clean_topic(failure_state)}"])
    if detail:
        lines.extend(["", f"Hinweis: {clean_topic(detail)}"])
    lines.extend([
        "",
        f"✅ Erledigt: {milestone.completed}",
        f"➡️ Als Nächstes: {milestone.next_step}",
        "",
        (
            "Für dich: ⚠️ Neuer Themenwinkel zur Freigabe nötig."
            if stage == "duplicate_blocked"
            else "Für dich: ✅ Keine Aktion nötig."
        ),
    ])
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
    parser.add_argument("--elapsed-minutes", type=int, default=0)
    parser.add_argument("--failure-state", default="")
    parser.add_argument("--detail", default="")
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()

    attempt = parse_attempt(args.run_attempt)
    if not progress_enabled(args.policy):
        print(json.dumps({"status": "disabled", "stage": args.stage}))
        return 0
    if not should_send(args.policy, attempt, args.stage):
        print(json.dumps({"status": "suppressed_rerun", "stage": args.stage, "run_attempt": attempt}))
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_PROGRESS_SECRETS_MISSING")

    payload = build_payload(
        args.stage,
        args.topic,
        args.run_id,
        chat_id,
        elapsed_minutes=args.elapsed_minutes,
        failure_state=args.failure_state,
        detail=args.detail,
    )
    message_id = telegram_send(token, payload)
    receipt = {
        "status": "sent",
        "stage": args.stage,
        "percent": MILESTONES[args.stage].percent,
        "run_id": str(args.run_id),
        "run_attempt": attempt,
        "failure_state": clean_topic(args.failure_state) if args.failure_state else "",
        "telegram_message_id": message_id,
    }
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
