"""Persist the exact terminal recovery result, never only an executor exit code.

This is a request-bound, idempotent receipt. It does not authorize publication,
change approved sources, or silently create new retry generations.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


_ALLOWED = {"LOCAL_VISUAL_RECOVERY_EXHAUSTED", "LOCAL_VOICE_RECOVERY_EXHAUSTED"}


def record_exhaustion(pointer: dict, request: dict, policy: dict, *,
                      run_id: int, run_attempt: int, now: str | None = None) -> bool:
    """Bind a classifier's exhausted outcome to the single approved request.

    Returns False when the identical outcome was already recorded. All other
    mismatches fail closed, including stale attempts, active-run changes and
    any weakening of the immutable editorial approval.
    """
    rid = str(pointer.get("request_id") or "")
    if (pointer.get("schema") != "tayvoriq-active-production-request-v1"
            or pointer.get("state") != "ACTIVE"
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", rid)
            or request.get("request_id") != rid
            or request.get("status") != "DISPATCHED"
            or request.get("source") != "telegram_trend_approval"):
        raise ValueError("RECOVERY_OUTCOME_ACTIVE_APPROVAL_INVALID")
    generation = int(pointer.get("recovery_generation") or 0)
    if (int(pointer.get("golden_path_run_id") or 0) != run_id
            or int(request.get("golden_path_run_id") or 0) != run_id
            or int(request.get("recovery_generation") or 0) != generation
            or int(run_attempt) < 1):
        raise ValueError("RECOVERY_OUTCOME_RUN_MISMATCH")
    for field in ("approval_key", "contract_sha256", "source_context_sha256"):
        if not pointer.get(field) or pointer[field] != request.get(field):
            raise ValueError("RECOVERY_OUTCOME_IMMUTABLE_IDENTITY_MISMATCH")
    if (policy.get("mode") != "exhausted"
            or policy.get("state") not in _ALLOWED
            or policy.get("retry_allowed") is not False
            or not re.fullmatch(r"[a-f0-9]{20}", str(policy.get("failure_signature") or ""))
            or int(policy.get("current_generation") or -1) != generation):
        raise ValueError("RECOVERY_OUTCOME_UNVERIFIED_CLASSIFIER")
    codefix = request.get("codefix_recovery") or {}
    implementation_sha = str(codefix.get("replay_implementation_sha") or "")
    if not re.fullmatch(r"[a-f0-9]{40}", implementation_sha):
        implementation_sha = ""
    outcome = {
        "schema": "tayvoriq-recovery-outcome-v1",
        "state": "EXHAUSTED",
        "reason": policy["state"],
        "request_id": rid,
        "run_id": run_id,
        "run_attempt": int(run_attempt),
        "recovery_generation": generation,
        "failure_signature": policy["failure_signature"],
        "implementation_sha": implementation_sha,
        "quality_gates_weakened": False,
        "publish_allowed": False,
        "next_action": "AWAIT_VERIFIED_MEDIA_OR_CODE_REPAIR",
    }
    existing = request.get("recovery_outcome") or {}
    if isinstance(existing, dict) and all(existing.get(k) == v for k, v in outcome.items()):
        return False
    outcome["recorded_at"] = now or datetime.now(timezone.utc).isoformat()
    request["recovery_outcome"] = outcome
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--policy-file", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", args.request_id):
        raise ValueError("RECOVERY_OUTCOME_REQUEST_ID_INVALID")
    pointer = json.loads(Path(".github/state/tayvoriq-active-production-request.json").read_text())
    path = Path("requests") / (args.request_id + ".json")
    request = json.loads(path.read_text(encoding="utf-8"))
    policy = json.loads(args.policy_file.read_text(encoding="utf-8"))
    if args.request_id != pointer.get("request_id"):
        raise ValueError("RECOVERY_OUTCOME_NOT_ACTIVE_REQUEST")
    changed = record_exhaustion(pointer, request, policy,
                                run_id=args.run_id, run_attempt=args.run_attempt)
    if changed:
        path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({
        "request_id": args.request_id,
        "run_id": args.run_id,
        "state": request.get("recovery_outcome", {}).get("reason"),
        "written": changed,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
