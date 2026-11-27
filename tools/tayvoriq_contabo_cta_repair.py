"""Stage one validated CTA-only retry for a proven private worker failure."""

import os
import re
from pathlib import Path

import tayvoriq_orchestration_contract as contract
import tayvoriq_retention_v5 as retention
from tayvoriq_slot_serialization_v1 import (
    CONTABO_WORKFLOWS,
    contabo_publishability_failed,
    github_json,
    is_verified_cta_content_repair,
)


def stage(root: Path, repo: str, token: str, signal: str = "") -> Path | None:
    pointer_path = root / ".github/state/tayvoriq-active-production-request.json"
    if not pointer_path.is_file():
        return None
    pointer = contract.read_json(pointer_path)
    owner_id = str(pointer.get("request_id") or "")
    run_id = pointer.get("golden_path_run_id")
    if (pointer.get("state") != "ACTIVE" or pointer.get("execution_backend") != "contabo_private_runner"
            or type(run_id) is not int or run_id <= 0 or (signal and str(run_id) != signal)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", owner_id)):
        return None
    owner = contract.read_json(root / "requests" / f"{owner_id}.json")
    if (owner.get("source") not in {"telegram_trend_approval", "telegram_trend_approval_source_repair"}
            or owner.get("retention_contract_version") != "v5"
            or (owner.get("production_completion") or {}).get("telegram_message_id")
            or not contabo_publishability_failed(root, pointer, owner)):
        return None
    receipt = contract.read_json(root / "run-status/contabo" / f"{run_id}.json")
    if receipt.get("failure_code") != "SHARED_CTA_INCOMPLETE":
        return None
    run = github_json(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}", token)
    if (run.get("id") != run_id or run.get("status") != "completed" or run.get("conclusion") != "failure"
            or run.get("head_branch") != "main" or run.get("path", "").split("@", 1)[0] not in CONTABO_WORKFLOWS):
        return None

    path = root / "requests" / f"{owner_id}-content-repair-v1.json"
    if path.is_file():
        existing = contract.read_json(path)
        if existing.get("status") in contract.CLAIMABLE and is_verified_cta_content_repair(existing, owner, owner_id):
            contract.validate(existing, require_claimable=True)
            return path
        return None

    original = str(owner.get("cta_text") or "").strip()
    cta = re.sub(r"^Entdecke mit TAYVORIQ,?\s+", "Folge TAYVORIQ und erfahre, ", original, flags=re.I)
    if cta == original:
        cta = f"{original.rstrip('.!?')}. Folge TAYVORIQ."
    if len(cta.split()) > 13:
        return None

    keys = (*contract.IMMUTABLE_FIELDS, *contract.V5_IMMUTABLE_FIELDS, "approved_via", "approved_at",
            "selection_id", "telegram_message_id", "tiktok_delivery", "source_context", "source_context_sha256")
    repair = {key: owner[key] for key in keys if key in owner}
    repair.update(request_id=path.stem, source="telegram_trend_approval_content_repair", status="APPROVED",
                  repair_of_request_id=owner_id, approval_key=f"{owner['approval_key']}:content-repair-v1",
                  cta_text=cta, golden_path_v5_state="APPROVED", golden_path_v5_history=owner["golden_path_v5_history"])
    repair["state_history"] = [{"state": "APPROVED", "at": contract.utc_now(), "actor": "contabo-cta-recovery",
                               "meta": {"repair_of_run_id": run_id, "worker_run_id": receipt["worker_run_id"],
                                        "repair_target": "cta_text", "failure_code": receipt["failure_code"]}}]
    if not is_verified_cta_content_repair(repair, owner, owner_id):
        return None
    fields = {key: repair.get(key) for key in (*retention.REQUEST_FIELDS, "next_episode_queue_status")}
    repair["follow_conversion_gate"] = retention.evaluate_follow_conversion(fields)
    repair["return_viewer_gate"] = retention.evaluate_return_viewer(fields)
    if any(repair[key]["result"] != "PASS" for key in ("follow_conversion_gate", "return_viewer_gate")):
        return None
    repair["retention_contract_sha256"] = retention.json_sha256(fields)
    repair["contract_sha256"] = contract.contract_hash(repair)
    contract.validate(repair, require_claimable=True)
    contract.write_json(path, repair)
    return path


if __name__ == "__main__":
    path = stage(Path("."), os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"], os.getenv("SIGNAL_RUN_ID", ""))
    if path is not None:
        print(path)
