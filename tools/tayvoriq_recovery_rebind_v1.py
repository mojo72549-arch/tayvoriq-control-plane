"""Guard and persist a same-run Delivery Watch retry without changing its owner.

Pure rebind_same_run is independently testable. The CLI only updates the
canonical request JSON in the workflow checkout; Git commit and Actions rerun
remain the caller's responsibility.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class RetryBindingError(ValueError):
    """A fail-closed canonical request/active-owner contract violation."""


def _positive_int(value: object, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RetryBindingError(f"INVALID_{name}") from exc
    if result < 1:
        raise RetryBindingError(f"INVALID_{name}")
    return result


def rebind_same_run(
    request: dict,
    pointer: dict,
    *,
    request_id: str,
    run_id: int,
    run_attempt: int,
    failure_state: str,
    failure_signature: str,
    at: str | None = None,
) -> tuple[dict, bool]:
    """Return (new_request, changed), refusing to reassign a different owner.

    run_attempt is the failed Golden Path attempt (not the Delivery Watch
    attempt). Attempt N can be rebound only for a retry of attempt N+1.
    """
    run_id = _positive_int(run_id, "RUN_ID")
    run_attempt = _positive_int(run_attempt, "RUN_ATTEMPT")
    request_id = str(request_id or "").strip()
    failure_state = str(failure_state or "").strip()
    failure_signature = str(failure_signature or "").strip()
    if not request_id or not failure_state or not failure_signature:
        raise RetryBindingError("RETRY_BINDING_INPUT_MISSING")

    if (
        pointer.get("schema") != "tayvoriq-active-production-request-v1"
        or pointer.get("state") != "ACTIVE"
        or str(pointer.get("request_id") or "") != request_id
        or _positive_int(pointer.get("golden_path_run_id"), "POINTER_RUN_ID") != run_id
        or pointer.get("allow_recovery") is not True
    ):
        raise RetryBindingError("SAME_RUN_RETRY_ACTIVE_OWNER_CHANGED")
    if (
        str(request.get("request_id") or "") != request_id
        or request.get("status") != "DISPATCHED"
        or _positive_int(request.get("golden_path_run_id"), "REQUEST_RUN_ID") != run_id
    ):
        raise RetryBindingError("SAME_RUN_RETRY_REQUEST_OWNER_CHANGED")
    try:
        request_generation = int(request.get("recovery_generation") or 0)
        pointer_generation = int(pointer.get("recovery_generation") or 0)
    except (TypeError, ValueError) as exc:
        raise RetryBindingError("SAME_RUN_RETRY_INVALID_GENERATION") from exc
    if min(request_generation, pointer_generation) < 0 or request_generation != pointer_generation:
        raise RetryBindingError("SAME_RUN_RETRY_GENERATION_MISMATCH")
    if request.get("source") != "telegram_trend_approval":
        raise RetryBindingError("SAME_RUN_RETRY_TELEGRAM_APPROVAL_REQUIRED")
    for key in ("approval_key", "source_context_sha256", "contract_sha256"):
        if not pointer.get(key) or str(pointer[key]) != str(request.get(key) or ""):
            raise RetryBindingError(f"SAME_RUN_RETRY_IMMUTABLE_MISMATCH:{key}")
    if str(request.get("telegram_message_id") or "") != str(pointer.get("telegram_message_id") or ""):
        raise RetryBindingError("SAME_RUN_RETRY_TELEGRAM_MESSAGE_MISMATCH")

    codefix = request.get("codefix_recovery")
    codefix = dict(codefix) if isinstance(codefix, dict) else {}
    target_attempt = run_attempt + 1
    previous_attempt = int(codefix.get("local_retry_run_attempt") or 0)
    if previous_attempt > target_attempt:
        raise RetryBindingError("SAME_RUN_RETRY_STALE_ATTEMPT")
    if previous_attempt == target_attempt:
        if (
            codefix.get("status") == "LOCAL_RETRY_DISPATCHED"
            and codefix.get("local_retry_kind") == "same-run"
            and int(codefix.get("local_retry_run_id") or 0) == run_id
            and codefix.get("local_retry_failure_signature") == failure_signature
        ):
            return dict(request), False
        raise RetryBindingError("SAME_RUN_RETRY_CONFLICTING_ATTEMPT")

    timestamp = at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    prior = str(codefix.get("failure_state") or "").strip()
    if prior:
        codefix["last_failure_state"] = prior
    codefix.update({
        "status": "LOCAL_RETRY_DISPATCHED",
        "request_substate": "DISPATCHED",
        "failure_state": "",
        "local_retry_run_id": run_id,
        "local_retry_run_attempt": target_attempt,
        "local_retry_kind": "same-run",
        "local_retry_failure_state": failure_state,
        "local_retry_failure_signature": failure_signature,
        "local_retry_dispatched_at": timestamp,
        "quality_gates_weakened": False,
        "active_pointer_verified": True,
    })
    updated = dict(request)
    updated["codefix_recovery"] = codefix
    updated["recovery_owner"] = "tayvoriq-delivery-watch"
    updated["state_history"] = list(request.get("state_history") or []) + [{
        "state": "DISPATCHED",
        "at": timestamp,
        "actor": "tayvoriq-delivery-watch",
        "meta": {
            "golden_path_run_id": run_id,
            "reason": "same-run-local-retry",
            "failure_state": failure_state,
            "failure_signature": failure_signature,
            "quality_gates_weakened": False,
            "active_pointer_verified": True,
        },
    }]
    return updated, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-file", type=Path, required=True)
    parser.add_argument("--active-pointer", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--failure-state", required=True)
    parser.add_argument("--failure-signature", required=True)
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.request_file.read_text(encoding="utf-8"))
        pointer = json.loads(args.active_pointer.read_text(encoding="utf-8"))
        updated, changed = rebind_same_run(
            request, pointer,
            request_id=args.request_id, run_id=args.run_id,
            run_attempt=args.run_attempt, failure_state=args.failure_state,
            failure_signature=args.failure_signature,
        )
        if changed:
            payload = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=args.request_file.parent,
                prefix=".retry-", suffix=".tmp", delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
            try:
                os.replace(temp_path, args.request_file)
            finally:
                temp_path.unlink(missing_ok=True)
        print("SAME_RUN_RETRY_BOUND" if changed else "SAME_RUN_RETRY_ALREADY_BOUND")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"SAME_RUN_RETRY_BIND_FAILED:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
