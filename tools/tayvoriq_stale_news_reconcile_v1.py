"""Quarantine stale failed Telegram news without silently publishing or retrying.

Only exact, review-less, unpublished, completed failed runs can be retired.
The full request and its immutable approved sources remain in Git history.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

POINTER = Path(".github/state/tayvoriq-active-production-request.json")
EXECUTOR_WORKFLOWS = (
    "tayvoriq-deliver-video-now.yml",
    "tayvoriq-delivery-watch.yml",
    "tayvoriq-deterministic-codefix-continuity.yml",
    "tayvoriq-autonomous-codefix-builder.yml",
    "tayvoriq-production-green-promoter.yml",
)
ACTIVE_RUN_STATES = {"queued", "in_progress", "waiting", "requested", "pending"}


def _utc(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timezone missing")
    return stamp.astimezone(timezone.utc)


def quarantine(
    pointer: dict, request: dict, run: dict, *,
    active_executors: int,
    now: datetime,
    minimum_age_hours: int = 72,
) -> tuple[dict, dict] | None:
    """Pure, fail-closed retirement decision; None means preserve the owner."""
    if now.tzinfo is None or minimum_age_hours < 48 or active_executors != 0:
        return None
    if (
        pointer.get("schema") != "tayvoriq-active-production-request-v1"
        or pointer.get("state") != "ACTIVE"
        or pointer.get("allow_publish") is not False
        or pointer.get("allow_recovery") is not True
        or request.get("status") != "DISPATCHED"
        or request.get("source") != "telegram_trend_approval"
    ):
        return None
    rid = str(pointer.get("request_id") or "").strip()
    if not rid or rid != request.get("request_id"):
        return None
    if not str(pointer.get("approval_key") or "").startswith("telegram:"):
        return None
    if not str(request.get("approved_at") or "") or str(request.get("approval_key") or "") != pointer.get("approval_key"):
        return None
    for key in ("source_context_sha256", "contract_sha256", "telegram_message_id"):
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
    if (
        run.get("name") != "TAYVORIQ-X Golden Path"
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or (now - approved_at) < timedelta(hours=minimum_age_hours)
        or (now - completed_at) < timedelta(hours=1)
    ):
        return None

    completion = request.get("production_completion")
    if completion:
        return None
    if any(request.get(key) for key in (
        "youtube_video_id", "youtube_url", "review_url",
        "telegram_review_message_id", "published_at", "uploaded_at",
        "publication", "upload_receipt", "delivery_receipt",
    )):
        return None
    if any(str(item.get("state") or "").upper() in {"REVIEW_READY", "PUBLISHED", "UPLOADED"}
           for item in request.get("state_history", []) if isinstance(item, dict)):
        return None

    timestamp = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    reason = "STALE_NEWS_QUARANTINED_AFTER_FAILED_PRODUCTION_NO_REVIEW"
    new_request, new_pointer = dict(request), dict(pointer)
    new_request["status"] = "EXPIRED"
    new_request["recovery_owner"] = "none"
    new_request["stale_quarantine"] = {
        "schema": "tayvoriq-stale-news-quarantine-v1", "at": timestamp,
        "reason": reason, "prior_status": "DISPATCHED", "prior_run_id": run_id,
        "review_delivered": False, "upload_permitted": False,
        "quality_gates_weakened": False,
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


def reconcile() -> bool:
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
        if datetime.now(timezone.utc) - _utc(str(approved)) < timedelta(hours=72):
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
        now=datetime.now(timezone.utc),
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
    subprocess.run(["git", "commit", "-m", f"ops(tayvoriq): quarantine stale failed news {rid}"], check=True)
    # A racing new request makes this non-fast-forward push fail closed; hourly
    # retry will first reread fresh main, never forcibly overwrite newer data.
    subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
    print(f"STALE_RECONCILE_EXPIRED_AND_FRESH_TRENDS_UNLOCKED:{rid}:{run_id}")
    return True


if __name__ == "__main__":
    try:
        reconcile()
    except Exception as error:
        print(f"STALE_RECONCILE_FAIL_CLOSED:{type(error).__name__}:{error}", file=sys.stderr)
        raise SystemExit(1)
