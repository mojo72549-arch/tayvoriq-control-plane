"""Quarantine stale failed Telegram news without silently publishing or retrying.

Only exact, review-less, unpublished, completed failed runs can be retired.
The full request and its immutable approved sources remain in Git history.
"""
from __future__ import annotations

import json
import os
import re
from tayvoriq_scheduled_render import scheduled_authority

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__:
    from .tayvoriq_recovery_attempt_ack_v1 import is_golden_path_run
else:
    from tayvoriq_recovery_attempt_ack_v1 import is_golden_path_run

POINTER = Path(".github/state/tayvoriq-active-production-request.json")
STALE_NEWS = "STALE_NEWS_QUARANTINED_AFTER_FAILED_PRODUCTION_NO_REVIEW"
EXHAUSTED_MORNING = "MORNING_RECOVERY_EXHAUSTED_EVENING_RELEASE"
EXECUTOR_WORKFLOWS = (
    "tayvoriq-deliver-video-now.yml",
    "tayvoriq-delivery-watch.yml",
    "tayvoriq-deterministic-codefix-continuity.yml",
    "tayvoriq-autonomous-codefix-builder.yml",
    "tayvoriq-production-green-promoter.yml",
    "tayvoriq-contabo-controller.yml",
)
ACTIVE_RUN_STATES = {"queued", "in_progress", "waiting", "requested", "pending"}


def _utc(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timezone missing")
    return stamp.astimezone(timezone.utc)


def has_delivery_evidence(request: dict) -> bool:
    if any(request.get(key) for key in (
        "production_completion", "youtube_video_id", "youtube_url", "review_url",
        "telegram_review_message_id", "published_at", "uploaded_at",
        "publication", "upload_receipt", "delivery_receipt",
    )):
        return True
    history = request.get("state_history", [])
    if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
        return True  # malformed history cannot prove that nothing was delivered
    return any(str(item.get("state") or "").upper() in {"REVIEW_READY", "PUBLISHED", "UPLOADED"}
               for item in history)


def _failed_golden_path(run: dict) -> bool:
    # Older stored run snapshots may still have only the canonical name.
    correct_workflow = is_golden_path_run(run) if run.get("path") else run.get("name") == "TAYVORIQ-X Golden Path"
    controller = str(run.get("path") or "").split("@")[0] == ".github/workflows/tayvoriq-contabo-controller.yml"
    return (correct_workflow or controller) and run.get("status") == "completed" and run.get("conclusion") == "failure"


def _failed_contabo_worker(pointer: dict, request: dict, receipt: dict | None) -> bool:
    if not isinstance(receipt, dict) or pointer.get("execution_backend") != "contabo_private_runner":
        return False
    worker = pointer.get("execution_run_id")
    return (
        receipt.get("schema") == "tayvoriq-contabo-worker-v1" and receipt.get("status") == "FAILED"
        and not receipt.get("result_release") and type(worker) is int and worker > 0
        and worker == receipt.get("worker_run_id") == (request.get("contabo_handoff") or {}).get("worker_run_id")
        and receipt.get("request_id") == pointer.get("request_id") == request.get("request_id")
        and receipt.get("controller_run_id") == pointer.get("golden_path_run_id") == request.get("golden_path_run_id")
        and receipt.get("source_context_sha256") == pointer.get("source_context_sha256") == request.get("source_context_sha256")
    )


def _approved_source(request: dict, contabo_failed: bool) -> bool:
    return scheduled_authority(request) or request.get("source") == "telegram_trend_approval" or (contabo_failed and request.get("source") in {
        "telegram_trend_approval_content_repair", "telegram_trend_approval_source_repair",
    })


def _exhausted_morning(request: dict, run: dict, now: datetime) -> bool:
    zone = ZoneInfo("Europe/Berlin")
    today = now.astimezone(zone)
    outcome = request.get("recovery_outcome")
    if (today.hour < 19 or not isinstance(outcome, dict)
            or not re.fullmatch(rf"{today:%Y%m%d}-(morning|m)-.+", str(request.get("selection_id") or ""))):
        return False
    expected = {
        "schema": "tayvoriq-recovery-outcome-v1", "state": "EXHAUSTED",
        "request_id": request.get("request_id"), "run_id": run.get("id"),
        "run_attempt": run.get("run_attempt"), "recovery_generation": request.get("recovery_generation", 0),
        "quality_gates_weakened": False, "publish_allowed": False,
        "next_action": "AWAIT_VERIFIED_MEDIA_OR_CODE_REPAIR",
    }
    try:
        receipt_at = _utc(outcome["recorded_at"])
        approved = _utc(request["approved_at"])
        completed = _utc(run["updated_at"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        all(outcome.get(key) == value for key, value in expected.items())
        and outcome.get("quality_gates_weakened") is False and outcome.get("publish_allowed") is False
        and type(run.get("run_attempt")) is int and run["run_attempt"] > 0
        and outcome.get("reason") in {"LOCAL_VISUAL_RECOVERY_EXHAUSTED", "LOCAL_VOICE_RECOVERY_EXHAUSTED"}
        and bool(re.fullmatch(r"[a-f0-9]{20}", str(outcome.get("failure_signature") or "")))
        and approved.astimezone(zone).date() == today.date()
        and approved <= completed <= receipt_at <= now
    )


def verified_quarantine(pointer: dict, request: dict, run: dict) -> bool:
    """Revalidate the canonical producer's complete, mirrored retirement proof."""
    reason = pointer.get("reason")
    if reason not in (STALE_NEWS, EXHAUSTED_MORNING):
        return False
    q, p = request.get("stale_quarantine"), pointer.get("stale_quarantine")
    if not isinstance(q, dict) or not isinstance(p, dict) or has_delivery_evidence(request):
        return False
    contabo_failed = _failed_contabo_worker(pointer, request, q.get("contabo_worker_receipt"))
    if pointer.get("execution_backend") == "contabo_private_runner" and not contabo_failed:
        return False
    if (pointer.get("schema") != "tayvoriq-active-production-request-v1"
            or pointer.get("state") != "EXPIRED" or request.get("status") != "EXPIRED"
            or pointer.get("allow_publish") is not False or pointer.get("allow_recovery") is not False
            or not _approved_source(request, contabo_failed) or request.get("recovery_owner") != "none"
            or q.get("schema") != "tayvoriq-stale-news-quarantine-v1"
            or q.get("prior_status") != "DISPATCHED" or q.get("quality_gates_weakened") is not False
            or q.get("review_delivered") is not False or q.get("upload_permitted") is not False
            or q.get("reason") != reason or p.get("reason") != reason or pointer.get("reason") != reason):
        return False
    for key in ("request_id", "approval_key", "source_context_sha256", "contract_sha256") + (() if scheduled_authority(request) else ("telegram_message_id",)):
        if not pointer.get(key) or pointer[key] != request.get(key):
            return False
    if (not scheduled_authority(request) and not str(pointer["approval_key"]).startswith("telegram:")) or p.get("request_id") != request["request_id"]:
        return False
    try:
        rid = int(pointer.get("golden_path_run_id") or 0)
        if (rid < 1 or any(int(value or 0) != rid for value in (
                request.get("golden_path_run_id"), run.get("id"), q.get("prior_run_id"), p.get("run_id")))
                or int(pointer.get("recovery_generation") or 0) != int(request.get("recovery_generation") or 0)
                or _utc(q["at"]) < _utc(request["approved_at"])
                or q["at"] != p.get("at") or q["at"] != pointer.get("updated_at")):
            return False
    except (KeyError, ValueError, TypeError):
        return False
    return _failed_golden_path(run) and (
        reason == STALE_NEWS or _exhausted_morning(request, run, _utc(q["at"]))
    )


def quarantine(
    pointer: dict, request: dict, run: dict, *,
    active_executors: int,
    now: datetime,
    minimum_age_hours: int = 72,
    for_evening: bool = False,
    contabo_receipt: dict | None = None,
) -> tuple[dict, dict] | None:
    """Pure, fail-closed retirement decision; None means preserve the owner."""
    if now.tzinfo is None or minimum_age_hours < 48 or active_executors != 0:
        return None
    contabo_failed = _failed_contabo_worker(pointer, request, contabo_receipt)
    if (
        pointer.get("schema") != "tayvoriq-active-production-request-v1"
        or pointer.get("state") != "ACTIVE"
        or pointer.get("allow_publish") is not False
        or (pointer.get("allow_recovery") is not True and not contabo_failed)
        or (pointer.get("execution_backend") == "contabo_private_runner" and not contabo_failed)
        or request.get("status") != "DISPATCHED"
        or not _approved_source(request, contabo_failed)
    ):
        return None
    rid = str(pointer.get("request_id") or "").strip()
    if not rid or rid != request.get("request_id"):
        return None
    if not scheduled_authority(request) and not str(pointer.get("approval_key") or "").startswith("telegram:"):
        return None
    if not str(request.get("approved_at") or "") or str(request.get("approval_key") or "") != pointer.get("approval_key"):
        return None
    for key in ("source_context_sha256", "contract_sha256") + (() if scheduled_authority(request) else ("telegram_message_id",)):
        if not pointer.get(key) or pointer[key] != request.get(key):
            return None
    try:
        run_id = int(pointer.get("golden_path_run_id") or 0)
        request_run_id = int(request.get("golden_path_run_id") or 0)
        same_generation = int(pointer.get("recovery_generation") or 0) == int(request.get("recovery_generation") or 0)
        approved_at = _utc(request["approved_at"])
        completed_at = _utc(str(run.get("updated_at") or ""))
    except (ValueError, TypeError):
        return None
    if run_id < 1 or request_run_id != run_id or not same_generation or int(run.get("id") or 0) != run_id:
        return None
    if not _failed_golden_path(run):
        return None
    exhausted = for_evening and _exhausted_morning(request, run, now)
    if not exhausted and ((now - approved_at) < timedelta(hours=minimum_age_hours)
                          or (now - completed_at) < timedelta(hours=1)):
        return None

    if has_delivery_evidence(request):
        return None

    timestamp = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    reason = EXHAUSTED_MORNING if exhausted else STALE_NEWS
    new_request, new_pointer = dict(request), dict(pointer)
    new_request["status"] = "EXPIRED"
    new_request["recovery_owner"] = "none"
    new_request["stale_quarantine"] = {
        "schema": "tayvoriq-stale-news-quarantine-v1", "at": timestamp,
        "reason": reason, "prior_status": "DISPATCHED", "prior_run_id": run_id,
        "review_delivered": False, "upload_permitted": False,
        "quality_gates_weakened": False,
    }
    if contabo_failed:
        new_request['stale_quarantine']['contabo_worker_receipt'] = {
            key:contabo_receipt.get(key) for key in ('schema','status','worker_run_id','request_id',
                                                     'controller_run_id','source_context_sha256','result_release')
        }
    new_request["state_history"] = list(request.get("state_history") or []) + [{
        "state": "EXPIRED", "at": timestamp,
        "actor": "tayvoriq-stale-news-safety",
        "meta": {"reason": reason, "run_id": run_id,
                 "prior_status": "DISPATCHED", "review_delivered": False,
                 "quality_gates_weakened": False},
    }]
    new_pointer.update(
        state="EXPIRED", allow_recovery=False, allow_publish=False,
        updated_at=timestamp, reason=reason,
        stale_quarantine={
            "at": timestamp, "reason": reason,
            "request_id": rid, "run_id": run_id,
        },
    )
    return new_request, new_pointer


def _gh_api(repo: str, path: str) -> dict:
    return json.loads(subprocess.check_output(
        ["gh", "api", f"repos/{repo}/{path}"], text=True,
    ))


def reconcile(*, for_evening: bool = False) -> bool:
    repo = str(os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if repo.count("/") != 1:
        raise RuntimeError("STALE_RECONCILE_GITHUB_REPOSITORY_REQUIRED")

    # Resolve latest remote state and only ever write one atomic git commit.
    subprocess.run(["git", "pull", "--ff-only", "origin", "main"], check=True)
    if not POINTER.is_file():
        print("STALE_RECONCILE_NO_POINTER")
        return False
    pointer = json.loads(POINTER.read_text(encoding="utf-8"))
    if pointer.get("state") != "ACTIVE":
        print("STALE_RECONCILE_NO_ACTIVE_NEWS_OWNER")
        return False

    rid = str(pointer.get("request_id") or "")
    if not rid or rid in (".", "..") or "/" in rid or "\\" in rid:
        raise RuntimeError("STALE_RECONCILE_INVALID_REQUEST_ID")
    request_path = Path("requests") / f"{rid}.json"
    if not request_path.is_file():
        raise RuntimeError("STALE_RECONCILE_MISSING_REQUEST")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    approved = request.get("approved_at")
    try:
        if not for_evening and datetime.now(timezone.utc) - _utc(str(approved)) < timedelta(hours=72):
            print("STALE_RECONCILE_WITHIN_APPROVAL_WINDOW")
            return False
    except (TypeError, ValueError):
        return False

    run_id = int(pointer.get("golden_path_run_id") or 0)
    if run_id < 1:
        return False
    run = _gh_api(repo, f"actions/runs/{run_id}")
    active = 0
    for workflow in EXECUTOR_WORKFLOWS:
        runs = _gh_api(repo, f"actions/workflows/{workflow}/runs?branch=main&per_page=20")
        active += sum(x.get("status") in ACTIVE_RUN_STATES for x in runs.get("workflow_runs", []))
    decision = quarantine(
        pointer, request, run, active_executors=active,
        now=datetime.now(timezone.utc), for_evening=for_evening,
        contabo_receipt=_worker_receipt(run_id) if pointer.get('execution_backend')=='contabo_private_runner' else None,
    )
    if decision is None:
        print("STALE_RECONCILE_NOT_ELIGIBLE_OR_EXECUTOR_ACTIVE")
        return False
    retired_request, retired_pointer = decision
    request_path.write_text(
        json.dumps(retired_request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    POINTER.write_text(
        json.dumps(retired_pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", str(request_path), str(POINTER)], check=True)
    subprocess.run(["git", "commit", "-m", f"ops(tayvoriq): close failed production {rid}"], check=True)
    # A racing new request makes this non-fast-forward push fail closed; hourly
    # retry will first reread fresh main, never forcibly overwrite newer data.
    subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
    print(f"STALE_RECONCILE_EXPIRED_AND_FRESH_TRENDS_UNLOCKED:{rid}:{run_id}")
    return True


def _worker_receipt(run_id: int) -> dict | None:
    path = Path('run-status/contabo') / f'{run_id}.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


if __name__ == "__main__":
    try:
        reconcile(for_evening="--for-evening" in sys.argv[1:])
    except Exception as error:
        print(f"STALE_RECONCILE_FAIL_CLOSED:{type(error).__name__}:{error}", file=sys.stderr)
        raise SystemExit(1)
