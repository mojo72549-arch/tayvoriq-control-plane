"""Render one durable Contabo lifecycle decision for both operator surfaces."""
import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tayvoriq_contabo_observation import CONTROL, api, mirror

OWNER = "TAYVORIQ-Produktionstechnik"


def build_event(result, dispatch_outcome=None):
    repair = result.get("contabo_repair")
    if not repair:
        return None
    state = repair["state"]
    event = {key: repair[key] for key in ("request_id", "source_context_sha256", "controller_run_id", "worker_run_id")}
    event.update(schema="tayvoriq-contabo-operator-event-v1", state=state, owner=OWNER,
                 user_action_required=False, happened_at=repair.get("stopped_at") or repair.get("controller_ended_at"))
    timeout = repair.get("timeout")
    if timeout:
        event["happened_at"] = timeout["at"]
        event["cause"] = f"Die Reparatur wurde nach {timeout['seconds'] // 60} Minuten vom Gesamtlimit gestoppt."
        if timeout.get("repair_round"):
            event["cause"] += f" Zu diesem Zeitpunkt lief Bildkorrektur {timeout['repair_round']}."
    else:
        event["cause"] = "Die Produktion ist bei der Prüfung des Video-Zwischenstands stehen geblieben."
        if repair.get("voice_timeout_seconds"):
            event["cause"] = f"Die Sprachkorrektur wurde nach {repair['voice_timeout_seconds'] // 60} Minuten gestoppt."
    event["done"] = ("Der Zwischenstand ist für diesen Auftrag gesichert und die Prüfung hat offene Mängel gefunden."
                     if repair.get("artifact_id") else "Der Orchestrator hat den Stopp dem freigegebenen Auftrag zugeordnet.")
    if repair.get("attempt_used"):
        event["done"] += " Der einmal zugelassene Wiederanlauf wurde ausgeführt."
    if repair.get("voice_platforms_passed"):
        event["done"] += " Die Sprecherfassungen für YouTube und TikTok haben die Sprachprüfung bestanden."
    event["decision_required"] = "Die Produktionstechnik muss den Fehlernachweis prüfen und eine gezielte Korrektur bestätigen."
    if state == "DIAGNOSTICS_REQUIRED":
        event["decision_required"] = "Die Produktionstechnik muss das Diagnoseartefakt des gestoppten Versuchs verifizieren."
    elif state == "AWAITING_VERIFIED_SCENE_FIX":
        scenes = ", ".join(f"{'TikTok' if row['platform'] == 'tiktok' else 'YouTube'}-Szene {row['scene']}"
                           for row in repair["scenes"])
        event["decision_required"] = (f"Die Produktionstechnik muss eine Reparatur für {scenes} "
                                      "ab dem gesicherten Zwischenstand prüfen und bestätigen.")
    elif state == "AWAITING_VERIFIED_PADDING_FIX":
        platform = "YouTube" if repair["platform"] == "youtube_shorts" else "TikTok"
        event["cause"] = f"Das Bildaudit ist bestanden. Die finale Mixprüfung beanstandet einen stummen Abschnitt bei {platform}."
        event["decision_required"] = f"Die Produktionstechnik prüft einen begrenzten Schnitt am stummen Ende von {platform}."
    if result.get("dispatch_verified") or result.get("reason") == "CONTABO_REPAIR_RUN_DISPATCHED":
        executor = result.get("executor_run_id") or (result.get("last_dispatch") or {}).get("executor_run_id")
        if executor:
            event.update(state="RECOVERY_DISPATCHED", executor_run_id=int(executor),
                         next=f"Ein gezielter Reparaturlauf ist eingeplant (Run {executor}).")
            event.pop("decision_required")
    if "next" not in event:
        event["next"] = "Es ist kein Reparaturjob eingeplant. " + event["decision_required"]
        if state == "RETRY_ELIGIBLE" and dispatch_outcome == "failure":
            event["next"] = ("Die Einplanung ließ sich nicht bestätigen. "
                             "Die Produktionstechnik muss den vorgesehenen Reparaturlauf abgleichen.")
            event["decision_required"] = "Abgleichen, ob GitHub den vorgesehenen Reparaturlauf angenommen hat."
        if result.get("reason") == "CONTABO_REPAIR_HANDOFF_TIMEOUT":
            event["decision_required"] = "Prüfen, warum der bestätigte Reparaturlauf den Auftrag nicht übernommen hat."
            event["next"] = ("GitHub hat den Reparaturlauf angenommen. Die Übernahme wurde innerhalb von zehn Minuten "
                             "nicht bestätigt. " + event["decision_required"])
    identity = json.dumps(event, sort_keys=True, ensure_ascii=False).encode()
    event["id"] = hashlib.sha256(identity).hexdigest()
    event["text"] = "\n".join((event["cause"], event["done"], event["next"], "Für dich ist keine Aktion nötig."))
    return event


def notify(event, token, bot, chat, *, fetch=api, save=mirror, open_response=urlopen):
    """Update the already confirmed Telegram stop message from the saved event."""
    run = event["controller_run_id"]
    path = f"run-status/contabo/notifications/{run}.json"
    try:
        current = json.loads(base64.b64decode(fetch(CONTROL, path, token)["content"]))
    except HTTPError as error:
        if error.code == 404:
            return False
        raise
    if (any(current.get(key) != event[key] for key in ("request_id", "source_context_sha256", "controller_run_id"))
            or current.get("phase_key") != "terminal:FAILED"
            or type(current.get("telegram_message_id")) is not int):
        return False
    if current.get("operator_event_id") == event["id"]:
        return True
    body = {"chat_id": chat, "message_id": current["telegram_message_id"],
            "text": f"TAYVORIQ · Update zur Reparatur\nAuftrag: {event['request_id']}\n\n{event['text']}\n"
                    "Live-Stand: https://tayvoriq-control-center-mo61.vercel.app",
            "disable_web_page_preview": True}
    request = Request(f"https://api.telegram.org/bot{bot}/editMessageText", data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
    try:
        with open_response(request, timeout=15) as response:
            result = json.load(response)
        if not result.get("ok") or result.get("result", {}).get("message_id") != body["message_id"]:
            raise RuntimeError("Telegram did not confirm the repair update")
    except HTTPError as error:
        # A previous process can have updated Telegram before saving the receipt.
        if error.code != 400 or "message is not modified" not in json.load(error).get("description", ""):
            raise
    save(path, {**current, "operator_event_id": event["id"]}, token)
    return True


if __name__ == "__main__":
    lifecycle = json.loads(Path(".github/state/tayvoriq-lifecycle-decision.json").read_text())
    event = lifecycle.get("operator_event")
    if event:
        notify(event, os.environ["GH_TOKEN"], os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"])
