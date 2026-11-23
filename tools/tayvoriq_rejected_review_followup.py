"""Prepare follow-up work for the actively bound, rejected review."""
import json
import re
from pathlib import Path

POINTER = ".github/state/tayvoriq-active-production-request.json"
DECISIONS = ".automation/tayvoriq-artifact-decisions"
FOLLOWUPS = ".github/state/rejected-review-followups"
REPAIRS = ".github/state/rejected-review-repairs"
DELIVERIES = ".automation/tayvoriq-agent-v2/deliveries"


def read(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def followup(root=Path(".")):
    pointer = read(root / POINTER)
    run_id = pointer.get("golden_path_run_id")
    request_id = pointer.get("request_id", "")
    if (pointer.get("schema") != "tayvoriq-active-production-request-v1"
            or pointer.get("state") != "COMPLETED" or type(run_id) is not int or run_id <= 0
            or not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", request_id)):
        return None
    request = read(root / "requests" / (request_id + ".json"))
    decision_path = f"{DECISIONS}/{run_id}.json"
    decision = read(root / decision_path)
    receipt = request.get("production_completion")
    if not isinstance(receipt, dict):
        return None
    source_hash = pointer.get("source_context_sha256")
    message_id = receipt.get("telegram_message_id")
    if (request.get("request_id") != request_id or request.get("golden_path_run_id") != run_id
            or receipt.get("state") != "REVIEW_READY" or receipt.get("golden_path_run_id") != run_id
            or receipt.get("reference_only") is True or receipt.get("quality_gates_weakened") is not False
            or type(message_id) is not int or message_id <= 0
            or decision.get("schema") != "tayvoriq-artifact-approval" or decision.get("state") != "REJECTED"
            or str(decision.get("review_id")) != str(run_id) or decision.get("request_id") != request_id
            or decision.get("telegram_message_id") != message_id or not source_hash
            or request.get("source_context_sha256") != source_hash or decision.get("source_context_sha256") != source_hash):
        return None
    slot_match = re.search(r"(?:^|-)(morning|evening)(?:-|$)", str(pointer.get("selection_id") or ""))
    if not slot_match:
        return None
    reason = str(decision.get("rejection_reason") or "").strip()[:600]
    requested = decision.get("followup_action")
    requested = requested if requested in {"auto", "new_trends", "repair"} else None
    repair_stage = {"voice": "VOICE", "visuals": "VISUALS"}.get(decision.get("rejection_reason_code"))
    checkpoint = receipt.get("review_repair_checkpoint") or ""
    checkpoint_prefix = f"tayvoriq-review-v1-{source_hash}-{run_id}-"
    execution = read(root / REPAIRS / f"{run_id}.json")
    if execution and (
        execution.get("request_id"), execution.get("source_context_sha256"), execution.get("rejected_run_id")
    ) != (request_id, source_hash, run_id):
        execution = {}
    can_repair = (
        requested in {"auto", "repair"} and bool(repair_stage)
        and isinstance(checkpoint, str) and checkpoint.startswith(checkpoint_prefix)
        and bool(re.fullmatch(r"[1-9][0-9]*", checkpoint[len(checkpoint_prefix):]))
        and not request.get("repaired_review_run_id") and execution.get("state") != "FAILED"
    )
    action = ("repair" if can_repair else "new_trends") if reason and requested else None
    selection_id = f"review-{slot_match[1]}-{run_id}"
    delivery = read(root / DELIVERIES / (selection_id + ".json"))
    research = read(root / ".automation/tayvoriq-agent-v2/review-trend-status" / (selection_id + ".json"))
    return {
        "schema": "tayvoriq-rejected-review-followup-v1",
        "request_id": request_id,
        "rejected_run_id": run_id,
        "source_context_sha256": source_hash,
        "rejection_reason": reason or None,
        "requested_action": requested,
        "followup_action": action,
        "route_reason": ("REPAIR_FAILED" if execution.get("state") == "FAILED" else
                         "NO_VERIFIED_REPAIR" if action == "new_trends" and requested != "new_trends" else None),
        "new_trends_requested": action == "new_trends" and bool(reason),
        "research_requested_at": (decision.get("followup_requested_at")
                                   if execution.get("state") != "FAILED" else execution.get("failed_at")),
        "research_state": (research.get("state") if research.get("selection_id") == selection_id else None),
        "replacement_state": ("REASON_REQUIRED" if not reason else
                              "REPAIR_RUNNING" if action == "repair" and execution.get("run_id") else
                              "PREFLIGHT_REQUIRED" if action == "repair" else
                              "NOT_SELECTED" if not action else "NEW_TRENDS_SELECTED"),
        "replacement_dispatch_allowed": action == "repair",
        "repair_stage": repair_stage if action == "repair" else None,
        "repair_cache_key": checkpoint if action == "repair" else None,
        "repair_run_id": execution.get("run_id"),
        "selection_id": selection_id,
        "selection_delivered": (delivery.get("selection_id") == selection_id
                                and delivery.get("telegram_delivery_verified") is True
                                and type(delivery.get("telegram_message_id")) is int
                                and delivery["telegram_message_id"] > 0),
        "slot": slot_match[1],
        "decision_path": decision_path,
    }


if __name__ == "__main__":
    plan = followup()
    if plan:
        target = Path(FOLLOWUPS) / f"{plan['rejected_run_id']}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
