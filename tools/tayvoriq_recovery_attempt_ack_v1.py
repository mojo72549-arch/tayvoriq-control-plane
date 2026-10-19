"""Dispatch and acknowledge exactly one failed-job GitHub Golden Path retry.

The caller MUST have bound the same request/run/next attempt first.
Unverified API acceptance is never reported as a successful recovery.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Callable


class RetryDispatchError(RuntimeError):
    pass


def _verify(run: dict, run_id: int) -> None:
    if int(run.get("id") or 0) != run_id:
        raise RetryDispatchError("RETRY_ACK_WRONG_GITHUB_RUN")
    if (
        run.get("name") != "TAYVORIQ-X Golden Path"
        or str(run.get("path") or "").split("@", 1)[0]
        != ".github/workflows/tayvoriq-deliver-video-now.yml"
    ):
        raise RetryDispatchError("RETRY_ACK_WRONG_WORKFLOW")


def dispatch_acknowledged(
    run_id: int,
    failed_attempt: int,
    *,
    fetch: Callable[[int], dict],
    dispatch: Callable[[int], None],
    pause: Callable[[float], None],
    polls: int = 12,
) -> dict:
    """Return proof for exactly attempt N+1; never rerun an unrelated owner."""
    if run_id < 1 or failed_attempt < 1 or polls < 1:
        raise RetryDispatchError("RETRY_ACK_INVALID_ARGUMENTS")
    desired = failed_attempt + 1
    initial = fetch(run_id)
    _verify(initial, run_id)
    current = int(initial.get("run_attempt") or 0)
    if current == desired:
        return {"run_id": run_id, "acknowledged_attempt": desired,
                "mode": "already_dispatched"}
    if current != failed_attempt:
        raise RetryDispatchError(
            f"RETRY_ACK_STALE_ATTEMPT:expected={failed_attempt}:actual={current}"
        )
    if initial.get("status") != "completed" or initial.get("conclusion") not in (
        "failure", "cancelled", "timed_out"
    ):
        raise RetryDispatchError("RETRY_ACK_FAILED_RUN_NOT_TERMINAL")

    dispatch_error: str = ""
    try:
        dispatch(run_id)
    except (OSError, subprocess.CalledProcessError) as exc:
        # The transport can time out after GitHub accepted the rerun. Poll its
        # canonical run_attempt before declaring failure or attempting a repeat.
        dispatch_error = type(exc).__name__
    for index in range(polls):
        observed = fetch(run_id)
        _verify(observed, run_id)
        current = int(observed.get("run_attempt") or 0)
        if current == desired:
            return {"run_id": run_id, "acknowledged_attempt": desired,
                    "mode": "dispatched", "dispatch_transport_error": dispatch_error}
        if current > desired:
            raise RetryDispatchError("RETRY_ACK_UNEXPECTED_LATER_ATTEMPT")
        if index < polls - 1:
            pause(3)
    raise RetryDispatchError(
        f"RETRY_ACK_NOT_ACKNOWLEDGED:run={run_id}:attempt={desired}:"
        f"dispatch_error={dispatch_error or 'none'}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--failed-attempt", type=int, required=True)
    args = parser.parse_args(argv)
    repo = str(os.environ.get("GITHUB_REPOSITORY") or "")
    if not repo or not all(part for part in repo.split("/")) or repo.count("/") != 1:
        print("RETRY_ACK_GITHUB_REPOSITORY_MISSING", file=sys.stderr)
        return 1

    def fetch(rid: int) -> dict:
        result = subprocess.check_output(
            ["gh", "api", f"repos/{repo}/actions/runs/{rid}"], text=True,
        )
        return json.loads(result)

    def dispatch(rid: int) -> None:
        subprocess.run(["gh", "run", "rerun", str(rid), "--failed"], check=True)

    try:
        receipt = dispatch_acknowledged(
            args.run_id, args.failed_attempt,
            fetch=fetch, dispatch=dispatch, pause=time.sleep,
        )
    except (RetryDispatchError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"RETRY_DISPATCH_FAILED:{exc}", file=sys.stderr)
        return 1
    print("TRANSIENT_SAME_RUN_RETRY_ACKNOWLEDGED:" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
