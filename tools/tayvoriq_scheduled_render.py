"""Reserve one review-only render per Berlin slot from a verified local research result."""
import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Berlin")
SOURCE = "scheduled_slot_research"


def window(now):
    local = now.astimezone(ZONE)
    minute = local.hour * 60 + local.minute
    if 330 <= minute < 720:
        return "morning"
    if minute >= 1140:
        return "evening"
    return ""


def scheduled_authority(request):
    proof = request.get("scheduled_research")
    if request.get("source") != SOURCE or not isinstance(proof, dict):
        return False
    sid = request.get("selection_id") or ""
    slot = request.get("slot")
    return bool(
        slot in {"morning", "evening"} and re.fullmatch(rf"\d{{8}}-{slot}-agentv2", sid)
        and request.get("request_id") == "slot-" + sid.removesuffix("-agentv2")
        and request.get("trend_id") == "1" and request.get("approval_key") == f"schedule:{sid}:trend:1"
        and request.get("approved_via") == "berlin_slot_scheduler"
        and request.get("telegram_message_id") is None
        and request.get("approval_required_before_youtube_publish") is True
        and request.get("tiktok_delivery") == "telegram_manual"
        and proof.get("origin") == "scheduled" and proof.get("selection") == sid
        and proof.get("slot") == slot and proof.get("topic") == ""
        and re.fullmatch(r"[0-9a-f]{40}", str(proof.get("revision") or ""))
        and all(re.fullmatch(r"[1-9]\d*", str(proof.get(key) or "")) for key in ("controller", "attempt", "worker_run_id"))
        and all(re.fullmatch(r"[0-9a-f]{64}", str(proof.get(key) or "")) for key in ("selection_sha256", "audit_sha256"))
    )


def owners(directory, sid):
    for path in sorted(directory.glob("*.json")):
        request = json.loads(path.read_text())
        selected = request.get("selection_id") or ""
        if (selected == sid or selected.startswith(sid + "-")) and request.get("status") not in {"EXPIRED", "REJECTED", "CANCELLED"}:
            if request.get("request_id") == path.stem and request.get("approval_key"):
                yield request


def pending(directory, now):
    slot = window(now)
    if not slot:
        return ""
    sid = f"{now.astimezone(ZONE):%Y%m%d}-{slot}-agentv2"
    rows = list(owners(directory, sid))
    if any(r.get("source") != SOURCE for r in rows):
        return ""
    for row in rows:
        if (scheduled_authority(row) and row["status"] == "APPROVED"
                and row.get("slot_serialization_state") != "HELD_WAITING_FOR_MORNING_REVIEW"):
            return row["request_id"]
    return ""


def stage(selection, audit, proof_path, directory, now):
    import tayvoriq_orchestration_contract as contract
    slot = window(now)
    sid = f"{now.astimezone(ZONE):%Y%m%d}-{slot}-agentv2"
    proof = json.loads(proof_path.read_text())
    packet = json.loads(selection.read_text())
    evidence = json.loads(audit.read_text())
    if not slot or not (sid == packet.get("selection_id") == evidence.get("selection_id") == proof.get("selection")
                        and slot == packet.get("slot") == evidence.get("slot") == proof.get("slot")
                        and proof["selection_sha256"] == hashlib.sha256(selection.read_bytes()).hexdigest()
                        and proof["audit_sha256"] == hashlib.sha256(audit.read_bytes()).hexdigest()
                        and evidence.get("quality_gates_weakened") is False
                        and evidence.get("selected_count") == len(packet["trends"])
                        and set(evidence["provider"].split("+")) <= {"ollama_rss", "ollama_gdelt"}):
        raise ValueError("SCHEDULED_RESULT_BINDING_INVALID")
    if list(owners(directory, sid)):
        return
    trend = packet["trends"][0]
    context = trend["source_context"]
    if (trend["id"] != "1" or (context.get("regional_assessment") or {}).get("passed") is not True
            or (context.get("duplicate_check") or {}).get("state") != "PASSED"):
        raise ValueError("SCHEDULED_EDITORIAL_REVIEW_MISSING")
    args = argparse.Namespace(trend_id="1", selection_id=sid, trend_request=selection,
                              message_id=None, payload_topic="", approved_at=now.isoformat(),
                              text_approval="", out_dir=directory)
    contract.create_review_request(args, scheduled_research=proof)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["stage", "pending", "manual-owner"])
    parser.add_argument("--request", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--proof", type=Path)
    args = parser.parse_args()
    now = datetime.now(ZONE)
    directory = Path("requests")
    if args.action == "stage":
        stage(args.selection, args.audit, args.proof, directory, now)
    elif args.action == "pending":
        print(pending(directory, now))
    else:
        row = json.loads(args.request.read_text())
        if row.get("source") == SOURCE:
            bound = f"{now:%Y%m%d}-{window(now)}-agentv2" == row.get("selection_id")
            if not bound or any(r.get("source") != SOURCE for r in owners(directory, row["selection_id"])):
                print("held")


if __name__ == "__main__":
    main()
