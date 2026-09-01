#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
POINTER_PATH = Path(".github/state/tayvoriq-production-green.json")
REQUESTS_DIR = Path("requests")
EXPECTED_SCHEMA = "tayvoriq-production-green-v1"
EXPECTED_REPOSITORY = "mojo72549-arch/shorts-agent-studio"


def _require_sha(value: object, label: str) -> str:
    sha = str(value or "").strip().lower()
    if SHA_RE.fullmatch(sha) is None:
        raise SystemExit(f"{label}_INVALID:{sha!r}")
    return sha


def resolve() -> dict[str, object]:
    if not POINTER_PATH.is_file():
        raise SystemExit("PRODUCTION_GREEN_POINTER_MISSING")
    pointer = json.loads(POINTER_PATH.read_text(encoding="utf-8"))
    if pointer.get("schema") != EXPECTED_SCHEMA:
        raise SystemExit("PRODUCTION_GREEN_SCHEMA_INVALID")
    if pointer.get("implementation_repository") != EXPECTED_REPOSITORY:
        raise SystemExit("PRODUCTION_GREEN_REPOSITORY_INVALID")
    if pointer.get("full_preflight_passed") is not True:
        raise SystemExit("PRODUCTION_GREEN_PREFLIGHT_NOT_VERIFIED")
    if pointer.get("quality_gates_weakened") is not False:
        raise SystemExit("PRODUCTION_GREEN_QUALITY_GATE_INTEGRITY_FAILED")

    green_sha = _require_sha(pointer.get("implementation_sha"), "PRODUCTION_GREEN_SHA")
    selected_sha = green_sha
    binding_source = "current-production-green"

    request_id = str(os.environ.get("SOURCE_REQUEST_ID_PIN") or "").strip()
    if request_id:
        if any(char in request_id for char in "\r\n/\\") or request_id in {".", ".."}:
            raise SystemExit("PRODUCTION_GREEN_REQUEST_ID_INVALID")
        request_path = REQUESTS_DIR / f"{request_id}.json"
        if not request_path.is_file():
            raise SystemExit("PRODUCTION_GREEN_REQUEST_MISSING")
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if str(request.get("request_id") or "").strip() != request_id:
            raise SystemExit("PRODUCTION_GREEN_REQUEST_IDENTITY_FAILED")
        recovery = request.get("codefix_recovery")
        if not isinstance(recovery, dict):
            recovery = {}
        replay_sha_raw = str(recovery.get("replay_implementation_sha") or "").strip().lower()
        if str(recovery.get("status") or "").upper() == "REPLAY_DISPATCHED" and replay_sha_raw:
            replay_sha = _require_sha(replay_sha_raw, "PRODUCTION_GREEN_REPLAY_SHA")
            if recovery.get("quality_gates_weakened") is not False:
                raise SystemExit("PRODUCTION_GREEN_REPLAY_QUALITY_GATE_INTEGRITY_FAILED")
            if recovery.get("active_pointer_verified") is not True:
                raise SystemExit("PRODUCTION_GREEN_REPLAY_POINTER_NOT_VERIFIED")
            selected_sha = replay_sha
            binding_source = "request-recorded-production-green"

    return {
        "implementation_sha": selected_sha,
        "binding_source": binding_source,
        "current_production_green_sha": green_sha,
        "quality_gates_weakened": False,
    }


def main() -> int:
    result = resolve()
    output_path = str(os.environ.get("GITHUB_OUTPUT") or "").strip()
    if not output_path:
        raise SystemExit("GITHUB_OUTPUT_MISSING")
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"implementation_sha={result['implementation_sha']}\n")
        handle.write(f"binding_source={result['binding_source']}\n")
        handle.write(f"current_production_green_sha={result['current_production_green_sha']}\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
