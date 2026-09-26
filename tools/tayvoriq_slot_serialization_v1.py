#!/usr/bin/env python3
"""Strict FIFO gate for TAYVORIQ morning/evening production requests."""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SELECTION_RE = re.compile(r"^(?P<date>\d{8})-(?P<slot>morning|evening|m|e)-.+$")
REQUIRED_FINAL_STEPS = (
    "Assert publishable production output",
    "Validate publication quality",
    "Publish review page",
    "Send Telegram review",
)
SERIALIZABLE_APPROVAL_SOURCES = {
    "telegram_trend_approval",
    "user_preapproved_preparation",
}
HELD_STATE = "HELD_WAITING_FOR_MORNING_REVIEW"
RELEASED_STATE = "RELEASED_AFTER_MORNING_REVIEW"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def selection_parts(data: dict) -> tuple[str, str] | None:
    match = SELECTION_RE.fullmatch(str(data.get("selection_id") or "").strip())
    if not match:
        return None
    return match.group("date"), match.group("slot")[0]


def _approved_stamp(data: dict) -> float:
    try:
        return datetime.fromisoformat(str(data.get("approved_at") or "").replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def find_same_day_morning(request: dict, requests_dir: Path) -> tuple[Path, dict] | None:
    parts = selection_parts(request)
    if not parts or parts[1] != "e":
        return None
    target_date = parts[0]
    candidates: list[tuple[float, Path, dict]] = []
    for path in requests_dir.glob("*.json"):
        try:
            data = read_json(path)
        except Exception:
            continue
        candidate_parts = selection_parts(data)
        if candidate_parts != (target_date, "m"):
            continue
        if str(data.get("source") or "") not in SERIALIZABLE_APPROVAL_SOURCES:
            continue
        candidates.append((_approved_stamp(data), path, data))
    if not candidates:
        return None
    _, path, data = max(candidates, key=lambda item: item[0])
    return path, data


def is_verified_editorial_source_repair(request: dict, owner: dict, owner_id: str) -> bool:
    """Allow a new immutable packet only for corrected editorial fallback text."""
    if request.get("source") != "telegram_trend_approval_source_repair":
        return False
    if request.get("repair_of_request_id") != owner_id or owner.get("request_id") != owner_id:
        return False
    if owner.get("status") != "DISPATCHED":
        return False
    if request.get("request_id") != f"{owner_id}-source-repair-v1":
        return False
    if request.get("approval_key") != f'{owner.get("approval_key")}:source-repair-v1':
        return False
    for key in (
        "selection_id", "trend_id", "topic", "trend_scope", "telegram_message_id",
        "approved_at", "content_angle", "primary_hook", "viewer_question",
        "explanation_core", "surprise_or_reframe", "practical_relevance",
        "follow_reason", "open_loop", "cta_text", "retention_contract_sha256",
    ):
        if request.get(key) != owner.get(key):
            return False
    original = owner.get("source_context")
    corrected = request.get("source_context")
    if not isinstance(original, dict) or not isinstance(corrected, dict):
        return False
    if original.get("fallback_editorial_answers") == corrected.get("fallback_editorial_answers"):
        return False
    common_original = {k: v for k, v in original.items() if k != "fallback_editorial_answers"}
    common_corrected = {k: v for k, v in corrected.items() if k != "fallback_editorial_answers"}
    return common_original == common_corrected


def is_verified_cta_content_repair(request: dict, owner: dict, owner_id: str) -> bool:
    """Keep the evidence and story fixed while repairing an incomplete CTA."""
    if request.get("source") != "telegram_trend_approval_content_repair":
        return False
    if request.get("repair_of_request_id") != owner_id or owner.get("request_id") != owner_id:
        return False
    if owner.get("status") != "DISPATCHED":
        return False
    if request.get("request_id") != f"{owner_id}-content-repair-v1":
        return False
    if request.get("approval_key") != f'{owner.get("approval_key")}:content-repair-v1':
        return False
    for key in (
        "selection_id", "trend_id", "topic", "trend_scope", "telegram_message_id",
        "approved_at", "content_angle", "primary_hook", "viewer_question",
        "explanation_core", "surprise_or_reframe", "practical_relevance",
        "follow_reason", "open_loop", "source_context", "source_context_sha256",
    ):
        if request.get(key) != owner.get(key):
            return False
    old_cta = str(owner.get("cta_text") or "").casefold()
    new_cta = str(request.get("cta_text") or "").casefold()
    return bool(
        old_cta and "tayvoriq" in old_cta
        and not any(marker in old_cta for marker in ("folg", "abonn"))
        and "tayvoriq" in new_cta
        and any(marker in new_cta for marker in ("folg", "abonn"))
    )


def evaluate_live_state(run: dict, jobs_payload: dict) -> tuple[bool, str, dict[str, str]]:
    status = str(run.get("status") or "")
    conclusion = str(run.get("conclusion") or "")
    if status != "completed":
        return False, "MORNING_RUN_NOT_COMPLETED", {}
    if conclusion != "success":
        return False, f"MORNING_RUN_{conclusion.upper() or 'NOT_SUCCESSFUL'}", {}
    steps: dict[str, str] = {}
    for job in jobs_payload.get("jobs") or []:
        if str(job.get("name") or "") != "orchestrate":
            continue
        for step in job.get("steps") or []:
            name = str(step.get("name") or "")
            if name in REQUIRED_FINAL_STEPS:
                steps[name] = str(step.get("conclusion") or "")
    if any(steps.get(name) != "success" for name in REQUIRED_FINAL_STEPS):
        return False, "MORNING_FINAL_REVIEW_NOT_VERIFIED", steps
    return True, "MORNING_FINAL_REVIEW_VERIFIED", steps


def github_json(url: str, token: str) -> dict:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "tayvoriq-slot-serialization-v1",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def check_request(request_path: Path, requests_dir: Path, repo: str, token: str) -> dict:
    request = read_json(request_path)
    parts = selection_parts(request)
    result = {
        "request_id": str(request.get("request_id") or request_path.stem),
        "selection_id": str(request.get("selection_id") or ""),
        "requires_serialization": False,
        "released": True,
        "reason": "NOT_AN_EVENING_SLOT",
        "predecessor_request_id": "",
        "predecessor_run_id": 0,
    }
    # Admission happens before claiming or dispatching a new production. A
    # failed/unfinished owner remains authoritative even across dates and slots.
    pointer_path = requests_dir.parent / ".github/state/tayvoriq-active-production-request.json"
    completed_owner_verified = False
    if pointer_path.is_file():
        result["requires_serialization"] = True
        result["released"] = False
        try:
            pointer = read_json(pointer_path)
            if pointer.get("schema") != "tayvoriq-active-production-request-v1":
                raise ValueError("invalid pointer schema")
            if pointer.get("state") not in {"ACTIVE", "COMPLETED"}:
                raise ValueError("invalid pointer state")
            if pointer.get("state") in {"ACTIVE", "COMPLETED"}:
                owner = str(pointer.get("request_id") or "")
                run_id = int(pointer.get("golden_path_run_id") or 0)
                if not owner or run_id <= 0:
                    raise ValueError("unbound active owner")
                if owner == result["request_id"]:
                    result["released"] = True
                    result["reason"] = "SAME_REQUEST_ACTIVE_OWNER"
                    return result
                if owner != result["request_id"]:
                    result["predecessor_request_id"] = owner
                    result["predecessor_run_id"] = run_id
                    if not repo or not token:
                        result["reason"] = "ACTIVE_OWNER_LIVE_STATE_UNAVAILABLE"
                        return result
                    try:
                        run = github_json(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}", token)
                        jobs = github_json(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token)
                        released, reason, steps = evaluate_live_state(run, jobs)
                    except Exception:
                        result["reason"] = "ACTIVE_OWNER_LIVE_STATE_UNAVAILABLE"
                        return result
                    result["verified_final_steps"] = steps
                    result["reason"] = reason.replace("MORNING_", "ACTIVE_OWNER_", 1)
                    if not released:
                        owner_path = requests_dir / f"{owner}.json"
                        if owner_path.is_file() and str(run.get("status")) == "completed" and str(run.get("conclusion")) == "failure":
                            failed_preflight = any(
                                step.get("name") == "Lightweight contract preflight" and step.get("conclusion") == "failure"
                                for job in jobs.get("jobs") or [] for step in job.get("steps") or []
                            )
                            if failed_preflight and is_verified_editorial_source_repair(request, read_json(owner_path), owner):
                                result["released"] = True
                                result["reason"] = "VERIFIED_EDITORIAL_SOURCE_REPAIR_AFTER_FAILED_PREFLIGHT"
                                return result
                            failed_publishability = any(
                                step.get("name") == "Assert publishable production output" and step.get("conclusion") == "failure"
                                for job in jobs.get("jobs") or [] for step in job.get("steps") or []
                            )
                            if failed_publishability and is_verified_cta_content_repair(request, read_json(owner_path), owner):
                                result["released"] = True
                                result["reason"] = "VERIFIED_CTA_CONTENT_REPAIR_AFTER_FAILED_PUBLISHABILITY"
                                return result
                        return result
                    completed_owner_verified = pointer.get("state") == "COMPLETED"
            result["released"] = True
        except (ValueError, TypeError, AttributeError, OSError):
            result["reason"] = "ACTIVE_OWNER_POINTER_INVALID"
            return result
    if not parts or parts[1] != "e":
        return result
    result["requires_serialization"] = True
    result["released"] = False
    predecessor = find_same_day_morning(request, requests_dir)
    if predecessor is None:
        # A direct Telegram approval may target the evening when no morning
        # request was ever approved. Preserve the active-owner and final-review
        # gates; never apply this to a prepared or automatically queued request.
        if completed_owner_verified and request.get("source") == "telegram_trend_approval":
            result["released"] = True
            result["reason"] = "EXPLICIT_EVENING_APPROVAL_AFTER_COMPLETED_OWNER"
            return result
        result["reason"] = "MORNING_REQUEST_MISSING"
        return result
    _, morning = predecessor
    result["predecessor_request_id"] = str(morning.get("request_id") or "")
    try:
        run_id = int(morning.get("golden_path_run_id") or 0)
    except (TypeError, ValueError):
        run_id = 0
    result["predecessor_run_id"] = run_id
    if run_id <= 0:
        result["reason"] = "MORNING_GOLDEN_PATH_NOT_BOUND"
        return result
    if not repo or not token:
        result["reason"] = "GITHUB_LIVE_STATE_UNAVAILABLE"
        return result
    run = github_json(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}", token)
    jobs = github_json(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token)
    released, reason, step_state = evaluate_live_state(run, jobs)
    result["released"] = released
    result["reason"] = reason
    result["verified_final_steps"] = step_state
    return result


def append_same_state_history(data: dict, actor: str, meta: dict) -> None:
    state = str(data.get("status") or "APPROVED").upper()
    data.setdefault("state_history", []).append({"state": state, "at": now_utc(), "actor": actor, "meta": meta})


def mark_held(path: Path, result: dict) -> bool:
    data = read_json(path)
    desired = {
        "slot_serialization_state": HELD_STATE,
        "slot_serialization_predecessor_request_id": result.get("predecessor_request_id") or "",
        "slot_serialization_predecessor_run_id": int(result.get("predecessor_run_id") or 0),
        "slot_serialization_reason": result.get("reason") or "UNKNOWN",
    }
    if all(data.get(k) == v for k, v in desired.items()):
        return False
    data.update(desired)
    append_same_state_history(data, "tayvoriq-slot-serialization-gate", dict(desired))
    write_json(path, data)
    return True


def mark_released(path: Path, result: dict) -> bool:
    data = read_json(path)
    if data.get("slot_serialization_state") == RELEASED_STATE:
        return False
    data["slot_serialization_state"] = RELEASED_STATE
    data["slot_serialization_released_at"] = now_utc()
    data["slot_serialization_predecessor_request_id"] = result.get("predecessor_request_id") or ""
    data["slot_serialization_predecessor_run_id"] = int(result.get("predecessor_run_id") or 0)
    data["slot_serialization_reason"] = result.get("reason") or "MORNING_FINAL_REVIEW_VERIFIED"
    append_same_state_history(data, "tayvoriq-slot-serialization-releaser", {
        "slot_serialization_state": RELEASED_STATE,
        "predecessor_request_id": data["slot_serialization_predecessor_request_id"],
        "predecessor_run_id": data["slot_serialization_predecessor_run_id"],
    })
    write_json(path, data)
    return True


def held_candidates(requests_dir: Path) -> list[Path]:
    candidates: list[tuple[float, Path]] = []
    for path in requests_dir.glob("*.json"):
        try:
            data = read_json(path)
        except Exception:
            continue
        if str(data.get("status") or "").upper() not in {"APPROVED", "TREND_APPROVED", "READY_FOR_PRODUCTION"}:
            continue
        if data.get("slot_serialization_state") != HELD_STATE:
            continue
        # Holds may now be caused by any active predecessor, including a prior
        # day's recovery. Resume every held approved request in approval order.
        candidates.append((_approved_stamp(data), path))
    return [path for _, path in sorted(candidates, key=lambda item: item[0])]


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--request", required=True)
    check.add_argument("--requests-dir", default="requests")
    check.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    check.add_argument("--token", default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "")
    mark_h = sub.add_parser("mark-held")
    mark_h.add_argument("--request", required=True)
    mark_h.add_argument("--result", required=True)
    mark_r = sub.add_parser("mark-released")
    mark_r.add_argument("--request", required=True)
    mark_r.add_argument("--result", required=True)
    scan = sub.add_parser("scan-held")
    scan.add_argument("--requests-dir", default="requests")
    args = parser.parse_args()
    if args.command == "check":
        print(json.dumps(check_request(Path(args.request), Path(args.requests_dir), args.repo, args.token), ensure_ascii=False))
    elif args.command in {"mark-held", "mark-released"}:
        result = read_json(Path(args.result))
        changed = mark_held(Path(args.request), result) if args.command == "mark-held" else mark_released(Path(args.request), result)
        print(json.dumps({"changed": changed, "request": args.request}))
    else:
        print(json.dumps([str(p) for p in held_candidates(Path(args.requests_dir))]))


if __name__ == "__main__":
    main()
