#!/usr/bin/env python3
"""Durable single admission per failed request and immutable Studio revision."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def reserve(request: dict, implementation_sha: str, ledger: Path, run_id: str) -> dict:
    codefix = request.get("codefix_recovery") or {}
    identity = {
        "schema": "tayvoriq-autocodefix-budget-v1",
        "request_id": request.get("request_id"),
        "failed_run_id": codefix.get("failed_run_id"),
        "failure_signature": codefix.get("failure_signature"),
        "source_context_sha256": request.get("source_context_sha256"),
        "contract_sha256": request.get("contract_sha256"),
        "implementation_sha": implementation_sha,
    }
    if codefix.get("status") != "ARMED" or not all(identity.values()):
        raise ValueError("AUTOCODEFIX_BUDGET_IDENTITY_INCOMPLETE")
    if not re.fullmatch(r"[0-9a-f]{40}", implementation_sha):
        raise ValueError("AUTOCODEFIX_BUDGET_IMPLEMENTATION_INVALID")
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    path = ledger / f"{key}.json"
    result = {"admitted": False, "fingerprint": key, "ledger_path": str(path),
              "implementation_sha": implementation_sha}
    ledger.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump({**identity, "builder_run_id": str(run_id), "state": "RESERVED",
                       "reserved_at": datetime.now(timezone.utc).isoformat(),
                       "max_provider_attempts": 3, "quality_gates_weakened": False},
                      handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError:
        return result
    return {**result, "admitted": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--implementation-sha", required=True)
    parser.add_argument("--builder-run-id", required=True)
    parser.add_argument("--ledger", default=".github/state/tayvoriq-codefix-attempts")
    args = parser.parse_args()
    result = reserve(json.loads(Path(args.request).read_text(encoding="utf-8")),
                     args.implementation_sha, Path(args.ledger), args.builder_run_id)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
