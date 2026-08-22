#!/usr/bin/env python3
"""Send verified Telegram production status without inventing progress."""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path

from tayvoriq_telegram_progress_notification_policy_v2 import HEARTBEAT_STAGES, heartbeat_due


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
        60,
        "Recovery übernommen",
        "Der fehlgeschlagene Lauf wurde erkannt und derselbe freigegebene Auftrag ist an einen neuen Recovery-Lauf gebunden.",
        "Der gespeicherte Produktionsstand wird übernommen und nur der noch offene Pfad weiterbearbeitet.",
    ),
    "sources_locked": Milestone(
        20,
        "Fakten gesichert",
        "Thema, Fakten und mindestens zwei Quellen sind verbindlich geprüft.",
        "Technischer Preflight und Produktionsvorbereitung.",
    ),
    "environment_active": Milestone(
        35,
        "Produktionsumgebung wird vorbereitet",
        "Quellen, Dublettenprüfung, Implementierung und vorhandene Recovery-Artefakte sind gebunden.",
        "Abhängigkeiten und Produktions-Preflight werden fertig vorbereitet.",
    ),
    "production_active": Milestone(
        45,
        "Produktion läuft",
        "Preflight und Produktionsvertrag sind bestanden.",
        "Skript, natürliche Sprecherstimme, Visuals, Untertitel und 9:16-Render werden erstellt beziehungsweise aus dem Checkpoint fortgesetzt.",
    ),
    "master_ready": Milestone(
        85,
        "Finaler Videomaster verifiziert",
        "Der lokal reparierte YouTube-/TikTok-Master ist vollständig erzeugt und als publishbarer Kandidat verifiziert.",
        "Finale Sprach-, Bild-, Fakten- und Plattform-Gates.",
    ),
    "quality_passed": Milestone(
        95,
        "Qualitätsprüfung bestanden",
        "Stimme, Bild, Fakten und beide Plattformpakete haben die Pflicht-Gates bestanden.",
        "Review-Seite und Telegram-Videofreigabe.",
    ),
    "review_ready": Milestone(
        100,
        "Review bereit",
        "Produktion, Render und alle verpflichtenden Quality-Gates sind abgeschlossen.",
        "Das Review-Video wird jetzt mit Freigeben/Ablehnen bereitgestellt.",
    ),
    "render_heartbeat": Milestone(
        45,
        "Produktion arbeitet weiter",
        "Der Produktionsprozess ist weiterhin aktiv; seit dem letzten verifizierten Meilenstein wurde kein neuer Fehler erkannt.",
        "Die laufende Produktionsphase wird fortgesetzt und der nächste echte Gate-Wechsel wird sofort gemeldet.",
    ),
    "checkpoint_repair": Milestone(
        75,
        "Render-Zwischenstand gesichert · Qualitätsreparatur",
        "Ein wiederverwendbarer Render-Zwischenstand ist gesichert. Er ist noch nicht freigabefähig und wurde nicht veröffentlicht.",
        "Nur fehlgeschlagene lokale Sprach-, Bild- oder Audit-Prüfpunkte werden repariert; erst danach wird der finale Master bestätigt.",
    ),
    "checkpoint_heartbeat": Milestone(
        75,
        "Qualitätsreparatur läuft intern weiter",
        "Render-Zwischenstand und Quellen bleiben gesichert; ein finaler Master ist noch nicht bestätigt.",
        "Die verbliebenen lokalen Prüfpunkte werden intern repariert und erneut gemessen; Telegram meldet erst den nächsten echten Meilenstein.",
    ),
    "audio_recovery": Milestone(
        None,
        "Audio-Gate hat sicher gestoppt",
        "Fakten, Thema und Dublettenprüfung bleiben gültig; es wurde nichts veröffentlicht.",
        "Nur der Pfad für die natürliche tiefe Sprecherstimme wird rückgekoppelt repariert und erneut geprüft.",
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
        "Der aktuelle Lauf wurde fail-closed beendet; Trendfreigabe und Quellen bleiben erhalten und es wurde nichts veröffentlicht.",
        "Der Orchestrator übernimmt denselben freigegebenen Auftrag automatisch nach der Recovery-Policy.",
    ),
}


REPLAY_SUPPRESSED_STAGES = {
    "sources_locked",
}

RECOVERY_REPLAY_SUPPRESSED_STAGES: set[str] = set()

RECOVERY_MILESTONES = {
    "sources_locked": Milestone(
        62,
        "Recovery-Bindung bestätigt",
        "Der gleiche Telegram-Auftrag, seine geprüften Quellen und die Dublettenprüfung sind für diesen Recovery-Lauf bestätigt.",
        "Produktionsumgebung und technischer Preflight werden abgeschlossen.",
    ),
    "environment_active": Milestone(
        62,
        "Recovery-Umgebung übernommen",
        "Quellen, Dublettenprüfung und vorhandener Produktions-Checkpoint sind für diesen Recovery-Lauf gebunden.",
        "Abhängigkeiten und der technische Preflight werden abgeschlossen.",
    ),
    "production_active": Milestone(
        65,
        "Recovery-Produktion läuft",
        "Produktions-Preflight und Vertragsprüfungen sind bestanden; der bestehende Auftrag wird gezielt fortgesetzt.",
        "Skript, Voice, Visuals und Renderpfad werden erstellt oder aus dem gesicherten Stand weitergeführt.",
    ),
    "render_heartbeat": Milestone(
        65,
        "Recovery arbeitet weiter",
        "Der aktuelle Produktionslauf ist weiterhin aktiv; seit dem letzten verifizierten Gate wurde kein neuer Fehler erkannt.",
        "Die aktive Produktionsphase läuft weiter; der nächste echte Meilenstein wird sofort gemeldet.",
    ),
    "checkpoint_repair": MILESTONES["checkpoint_repair"],
    "checkpoint_heartbeat": MILESTONES["checkpoint_heartbeat"],
    "master_ready": MILESTONES["master_ready"],
    "quality_passed": MILESTONES["quality_passed"],
    "review_ready": MILESTONES["review_ready"],
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


def immediate_failure_enabled(path: Path = DEFAULT_POLICY) -> bool:
    value = read_policy(path).get("immediate_failure_notification_enabled")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in TRUE_VALUES


def recovery_generation() -> int:
    """Resolve durable recovery ownership from the repository root, never cwd."""
    request_id = str(os.getenv("SOURCE_REQUEST_ID_PIN") or "").strip()
    if (
        not request_id
        or any(char in request_id for char in "/\\\r\n")
        or request_id in {".", ".."}
    ):
        return 0

    workspace_raw = str(os.getenv("GITHUB_WORKSPACE") or "").strip()
    if workspace_raw:
        repository_root = Path(workspace_raw)
    else:
        repository_root = Path(__file__).resolve().parents[1]
    path = repository_root / "requests" / f"{request_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if str(data.get("request_id") or "").strip() != request_id:
            return 0
        return max(0, int(data.get("recovery_generation") or 0))
    except Exception:
        return 0


def effective_milestone(stage: str, generation: int) -> Milestone:
    milestone = MILESTONES[stage]
    if generation <= 0:
        return milestone
    if stage == "recovery_started":
        return MILESTONES["recovery_started"]
    override = RECOVERY_MILESTONES.get(stage)
    if override is not None:
        return override
    if milestone.percent is not None and milestone.percent < 60:
        return replace(milestone, percent=60)
    return milestone


def should_send(
    path: Path,
    run_attempt: int,
    stage: str = "",
    elapsed_minutes: int = 0,
) -> bool:
    if not progress_enabled(path):
        return False
    if stage in {"technical_stop", "audio_recovery"} and not immediate_failure_enabled(path):
        return False
    if int(run_attempt) > 1 and stage in REPLAY_SUPPRESSED_STAGES:
        return False
    if stage in HEARTBEAT_STAGES and not heartbeat_due(stage, elapsed_minutes):
        return False
    return True


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
    generation: int = 0,
) -> dict:
    milestone = effective_milestone(stage, generation)
    heading = f"TAYVORIQ {milestone.percent} %" if milestone.percent is not None else "TAYVORIQ"
    icon = "🔄" if stage == "render_heartbeat" else ("🟠" if stage in {"audio_recovery", "technical_stop"} else "🟣")
    if stage in {"recovery_started", "checkpoint_repair", "checkpoint_heartbeat"} or generation > 0:
        icon = "🔧"
    if stage == "review_ready":
        icon = "🟢"
    if stage == "duplicate_blocked":
        icon = "🛑"

    title = milestone.title
    completed = milestone.completed
    next_step = milestone.next_step
    elapsed = int(elapsed_minutes or 0)
    if stage == "render_heartbeat" and elapsed >= 45:
        icon = "🟠"
        title = "Produktion ungewöhnlich lange aktiv · Watchdog überwacht"
        completed = "Der Lauf ist weiterhin aktiv; der letzte verifizierte Produktionsstand bleibt erhalten."
        next_step = "Der Watchdog prüft weiter intern; Telegram meldet erst wieder einen echten Zustandswechsel oder einen Fehler."
    elif stage == "render_heartbeat" and elapsed >= 18:
        icon = "🟠"
        title = "Produktion dauert länger · einmaliger Watchdog-Hinweis"
        completed = "Der Lauf ist weiterhin aktiv; der letzte verifizierte Produktionsstand bleibt erhalten."
        next_step = "Der Watchdog prüft intern weiter; Telegram bleibt bis zum nächsten echten Meilenstein ruhig."
    elif stage == "checkpoint_heartbeat" and elapsed >= 45:
        icon = "🟠"
        title = "Qualitätsreparatur ungewöhnlich lange aktiv · Watchdog überwacht"
        completed = "Render-Zwischenstand und Quellen sind gesichert; ein finaler Master ist noch nicht bestätigt."
        next_step = "Der Watchdog prüft weiter intern; Telegram meldet erst wieder einen echten Zustandswechsel oder einen Fehler."
    elif stage == "checkpoint_heartbeat" and elapsed >= 18:
        icon = "🟠"
        title = "Qualitätsreparatur dauert länger · einmaliger Watchdog-Hinweis"
        completed = "Render-Zwischenstand und Quellen sind gesichert; ein finaler Master ist noch nicht bestätigt."
        next_step = "Der Watchdog prüft intern weiter; Telegram bleibt bis zum nächsten echten Meilenstein ruhig."

    if stage == "technical_stop":
        detail = (
            "Automatische Recovery ist request-gebunden und folgt der getesteten Recovery-Policy; "
            "es wird nicht blind eine neue Generation gestartet."
        )

    lines = [
        f"{icon} {heading} · {title}",
        "",
        f"Thema: {clean_topic(topic)}",
        f"Run: {str(run_id or 'unbekannt').strip()}",
    ]
    if generation > 0:
        lines.append(f"Recovery: Generation {generation}")
    if stage in HEARTBEAT_STAGES:
        phase = "Produktionsphase" if stage == "render_heartbeat" else "Qualitätsreparatur"
        lines.extend(["", f"⏱️ {phase} aktiv seit: {max(1, elapsed)} Minuten"])
    if failure_state:
        lines.extend(["", f"Status: {clean_topic(failure_state)}"])
    if detail:
        lines.extend(["", f"Hinweis: {clean_topic(detail)}"])
    lines.extend([
        "",
        f"✅ Erledigt: {completed}",
        f"➡️ Als Nächstes: {next_step}",
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
    generation = recovery_generation()
    if not progress_enabled(args.policy):
        print(json.dumps({"status": "disabled", "stage": args.stage}))
        return 0
    if generation > 0 and args.stage in RECOVERY_REPLAY_SUPPRESSED_STAGES:
        print(json.dumps({
            "status": "suppressed_recovery_replay",
            "stage": args.stage,
            "run_attempt": attempt,
            "recovery_generation": generation,
        }))
        return 0
    if not should_send(args.policy, attempt, args.stage, args.elapsed_minutes):
        reason = (
            "suppressed_internal_recovery"
            if args.stage in {"technical_stop", "audio_recovery"} and not immediate_failure_enabled(args.policy)
            else ("suppressed_heartbeat" if args.stage in HEARTBEAT_STAGES else "suppressed_rerun")
        )
        print(json.dumps({
            "status": reason,
            "stage": args.stage,
            "run_attempt": attempt,
            "elapsed_minutes": int(args.elapsed_minutes or 0),
            "recovery_generation": generation,
        }))
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_PROGRESS_SECRETS_MISSING")

    milestone = effective_milestone(args.stage, generation)
    payload = build_payload(
        args.stage,
        args.topic,
        args.run_id,
        chat_id,
        elapsed_minutes=args.elapsed_minutes,
        failure_state=args.failure_state,
        detail=args.detail,
        generation=generation,
    )
    message_id = telegram_send(token, payload)
    receipt = {
        "status": "sent",
        "stage": args.stage,
        "percent": milestone.percent,
        "run_id": str(args.run_id),
        "run_attempt": attempt,
        "recovery_generation": generation,
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
