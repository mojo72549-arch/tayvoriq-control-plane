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
from zoneinfo import ZoneInfo

from tayvoriq_stale_news_reconcile_v1 import EXHAUSTED_MORNING, verified_quarantine
from tayvoriq_review_receipt import REPLAY_PATH, REPLAY_BRANCH, REPLAY_STEPS
from tayvoriq_contabo_handoff import STUDIO, identity

SELECTION_RE = re.compile(r"^(?P<date>\d{8})-(?P<slot>morning|evening|m|e)-.+$")
REQUIRED_FINAL_STEPS = (
    "Assert publishable production output",
    "Validate publication quality",
    "Publish review page",
    "Send Telegram review",
)
CONTABO_FINAL_STEPS = (
    "Receive the request-bound Contabo review package",
    "Assert immutable result and final quality proof",
    "Publish review page",
    "Send Telegram review",
    "Finalize verified review delivery",
)
CONTABO_WORKFLOWS = {
    ".github/workflows/tayvoriq-contabo-controller.yml",
    ".github/workflows/tayvoriq-deliver-video-now.yml",
}
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
    # The morning approval retains its identity when a bounded editorial
    # repair takes over. The evening must check the production of that repair.
    for suffix, verify in (
        ("-source-repair-v1", is_verified_editorial_source_repair),
        ("-content-repair-v1", is_verified_cta_content_repair),
    ):
        parent_id = str(data.get("request_id") or "")
        if parent_id != path.stem:
            break
        repair_path = requests_dir / f"{parent_id}{suffix}.json"
        try:
            repair = read_json(repair_path)
        except (OSError, ValueError):
            continue
        if verify(repair, data, parent_id):
            path, data = repair_path, repair
    return path, data


def morning_research_exhausted(request: dict, root: Path, repo: str, token: str) -> bool:
    """Allow the first production of the evening when morning research ended empty."""
    if not repo or not token or request.get("source") != "telegram_trend_approval":
        return False
    zone = ZoneInfo("Europe/Berlin")
    today = datetime.now(zone)
    if (selection_parts(request) != (today.strftime("%Y%m%d"), "e")
            or datetime.fromtimestamp(_approved_stamp(request), zone).date() != today.date()):
        return False
    base = root / ".automation/tayvoriq-agent-v2"
    if (base / "deliveries" / f"{today:%Y%m%d}-morning-agentv2.json").exists():
        return False
    path = base / "research-notices" / f"{today:%Y-%m-%d}-morning-EXHAUSTED.json"
    try:
        receipt = read_json(path)
        run_id = receipt.get("run_id")
        if (receipt.get("slot") != "morning" or receipt.get("berlin_date") != today.date().isoformat()
                or receipt.get("research_state") != "EXHAUSTED"
                or receipt.get("state") not in {"SENDING", "UNCONFIRMED", "DELIVERED"}
                or type(run_id) is not int or run_id <= 0):
            return False
        run = github_json(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}", token)
    except (OSError, ValueError, TypeError, AttributeError, RuntimeError):
        return False
    return (isinstance(run, dict) and run.get("id") == run_id and run.get("status") == "completed"
            and str(run.get("path") or "").split("@", 1)[0] == ".github/workflows/tayvoriq-agent-orchestrator-v2.yml")


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


def reference_review_verified(request, run, jobs_payload):
    completion = request.get('production_completion') or {}
    message = completion.get('telegram_message_id')
    return (completion.get('reference_only') is True and completion.get('publishable_review') is False
            and completion.get('state') == 'REVIEW_READY' and completion.get('quality_gates_weakened') is False
            and type(message) is int and message > 0
            and completion.get('golden_path_run_id') == request.get('golden_path_run_id') == run.get('id')
            and run.get('head_branch') == REPLAY_BRANCH and str(run.get('path') or '').split('@', 1)[0] == REPLAY_PATH
            and run.get('status') == 'completed' and run.get('conclusion') == 'success'
            and any(job.get('name') == 'review' and job.get('conclusion') == 'success'
                    and set(REPLAY_STEPS) <= {step.get('name') for step in job.get('steps', [])
                                             if step.get('conclusion') == 'success'}
                    for job in jobs_payload.get('jobs', [])))


def github_json(url: str, token: str) -> dict:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "tayvoriq-slot-serialization-v1",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def evaluate_contabo_review(request, run, jobs_payload, repo, token, expected_run_id, pointer=None):
    completion = request.get("production_completion") or {}
    handoff = request.get("contabo_handoff") or {}
    message_id = completion.get("telegram_message_id")
    worker_id = handoff.get("worker_run_id")
    delivery_id = completion.get("delivery_run_id", expected_run_id)
    unverified = False, "MORNING_CONTABO_REVIEW_NOT_VERIFIED", {}
    if not (
        request.get("golden_path_run_id") == completion.get("golden_path_run_id")
        == handoff.get("controller_run_id") == expected_run_id
        and completion.get("state") == "REVIEW_READY"
        and completion.get("quality_gates_weakened") is False
        and type(message_id) is int and message_id > 0
        and type(delivery_id) is int and delivery_id > 0
        and type(worker_id) is int and worker_id > 0
        and handoff.get("schema") == "tayvoriq-contabo-handoff-v1"
        and handoff.get("execution_repository") == STUDIO
        and handoff.get("quality_gates_weakened") is False
        and all(request.get(key) and request[key] == handoff.get(key)
                for key in ("request_id", "source_context_sha256", "contract_sha256"))
    ):
        return unverified
    try:
        if pointer is not None:
            identity(request, pointer)
            if (pointer.get("state") != "COMPLETED"
                    or pointer.get("execution_backend") != "contabo_private_runner"
                    or pointer.get("execution_repository") != STUDIO
                    or pointer.get("execution_run_id") != worker_id):
                return unverified
    except (AssertionError, KeyError, TypeError):
        return unverified
    if delivery_id != expected_run_id:
        url = f"https://api.github.com/repos/{repo}/actions/runs/{delivery_id}"
        run = github_json(url, token)
        jobs_payload = github_json(f"{url}/jobs?per_page=100", token)
    if (run.get("id") != delivery_id or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or str(run.get("path") or "").split("@", 1)[0] not in CONTABO_WORKFLOWS):
        return unverified
    for job in jobs_payload.get("jobs") or []:
        if (job.get("name") not in {"orchestrate", "contabo-controller / orchestrate"}
                or job.get("conclusion") != "success"):
            continue
        steps = {step["name"]: step.get("conclusion") for step in job.get("steps", [])
                 if step.get("name") in CONTABO_FINAL_STEPS}
        if all(steps.get(name) == "success" for name in CONTABO_FINAL_STEPS):
            return True, "MORNING_CONTABO_REVIEW_VERIFIED", steps
    return unverified


def contabo_publishability_failed(root, pointer, owner):
    if pointer.get("state") != "ACTIVE" or pointer.get("execution_backend") != "contabo_private_runner":
        return False
    controller = pointer.get("golden_path_run_id")
    receipt_path = root / "run-status/contabo" / f"{controller}.json"
    if not receipt_path.is_file():
        return False
    receipt = read_json(receipt_path)
    handoff = owner.get("contabo_handoff") or {}
    worker = pointer.get("execution_run_id")
    return (
        type(worker) is int and worker > 0
        and receipt.get("schema") == "tayvoriq-contabo-worker-v1"
        and receipt.get("status") == "FAILED" and receipt.get("failed_step") == REQUIRED_FINAL_STEPS[0]
        and receipt.get("request_id") == pointer.get("request_id") == owner.get("request_id")
        and receipt.get("controller_run_id") == owner.get("golden_path_run_id") == controller
        and receipt.get("worker_run_id") == handoff.get("worker_run_id") == worker
        and receipt.get("source_context_sha256") == pointer.get("source_context_sha256")
        == owner.get("source_context_sha256")
    )


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
    expired_owner_verified = False
    if pointer_path.is_file():
        result["requires_serialization"] = True
        result["released"] = False
        try:
            pointer = read_json(pointer_path)
            if pointer.get("schema") != "tayvoriq-active-production-request-v1":
                raise ValueError("invalid pointer schema")
            if pointer.get("state") == "EXPIRED":
                owner = str(pointer.get("request_id") or "")
                run_id = int(pointer.get("golden_path_run_id") or 0)
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", owner) or run_id <= 0:
                    raise ValueError("invalid expired owner binding")
                result["predecessor_request_id"] = owner
                result["predecessor_run_id"] = run_id
                previous = read_json(requests_dir / f"{owner}.json")
                previous_parts = selection_parts(previous)
                berlin = ZoneInfo("Europe/Berlin")
                today = datetime.now(berlin).strftime("%Y%m%d")
                approved = datetime.fromtimestamp(_approved_stamp(request), berlin).strftime("%Y%m%d")
                same_day_evening = (
                    pointer.get("reason") == EXHAUSTED_MORNING
                    and previous_parts == (today, "m") and parts == (today, "e")
                )
                different_day = parts and previous_parts and previous_parts[0] < parts[0] == today
                if (not (same_day_evening or different_day) or approved != today
                        or request.get("source") != "telegram_trend_approval" or owner == result["request_id"]):
                    result["reason"] = "NEW_BERLIN_DAY_TELEGRAM_APPROVAL_REQUIRED"
                    return result
                try:
                    run = github_json(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}", token) if repo and token else {}
                except Exception:
                    run = {}
                if not verified_quarantine(pointer, previous, run):
                    result["reason"] = "EXPIRED_OWNER_QUARANTINE_NOT_VERIFIED"
                    return result
                if same_day_evening:
                    result.update(released=True, reason=EXHAUSTED_MORNING)
                    return result
                expired_owner_verified = True
                result["reason"] = "FRESH_REQUEST_AFTER_VERIFIED_OWNER_EXPIRY"
            elif pointer.get("state") in {"ACTIVE", "COMPLETED"}:
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
                        if pointer.get("execution_backend") == "contabo_private_runner":
                            previous = read_json(requests_dir / f"{owner}.json")
                            released, reason, steps = evaluate_contabo_review(previous, run, jobs, repo, token, run_id, pointer)
                        elif (not released and pointer.get('state') == 'COMPLETED'
                                and pointer.get('reference_only') is True and pointer.get('allow_publish') is False
                                and reference_review_verified(read_json(requests_dir / f'{owner}.json'), run, jobs)):
                            released, reason = True, 'MORNING_REFERENCE_REVIEW_VERIFIED'
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
                            original = read_json(owner_path)
                            if (is_verified_cta_content_repair(request, original, owner)
                                    and (failed_publishability or contabo_publishability_failed(requests_dir.parent, pointer, original))):
                                result["released"] = True
                                result["reason"] = "VERIFIED_CTA_CONTENT_REPAIR_AFTER_FAILED_PUBLISHABILITY"
                                return result
                        return result
                    completed_owner_verified = pointer.get("state") == "COMPLETED"
            else:
                raise ValueError("invalid pointer state")
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
        if expired_owner_verified:
            result["released"] = True
            result["reason"] = "FIRST_APPROVED_SLOT_AFTER_VERIFIED_OWNER_EXPIRY"
            return result
        # A direct Telegram approval may target the evening when no morning
        # request was ever approved. Preserve the active-owner and final-review
        # gates; never apply this to a prepared or automatically queued request.
        if completed_owner_verified and request.get("source") == "telegram_trend_approval":
            result["released"] = True
            result["reason"] = "EXPLICIT_EVENING_APPROVAL_AFTER_COMPLETED_OWNER"
            return result
        if morning_research_exhausted(request, requests_dir.parent, repo, token):
            result.update(released=True, reason="EVENING_APPROVED_AFTER_MORNING_RESEARCH_EXHAUSTION")
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
    if morning.get("execution_backend") == "contabo_private_runner":
        released, reason, step_state = evaluate_contabo_review(morning, run, jobs, repo, token, run_id)
    elif not released and reference_review_verified(morning, run, jobs):
        released, reason = True, 'MORNING_REFERENCE_REVIEW_VERIFIED'
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
