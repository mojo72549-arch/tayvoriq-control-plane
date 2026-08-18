#!/usr/bin/env python3
"""Request-bound recovery state for the TAYVORIQ Golden Path.

The delivery watcher must never recover from a mutable global request pointer.
It resolves the canonical request by the completed Golden Path run id and keeps
all fresh recovery generations attached to that same request.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_by_run(requests_dir: Path, run_id: int) -> tuple[Path, dict[str, Any]] | None:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(requests_dir.glob("*.json")):
        try:
            data = _read(path)
        except Exception:
            continue
        if int(data.get("golden_path_run_id") or 0) == run_id:
            matches.append((path, data))
    if len(matches) > 1:
        raise RuntimeError(
            f"RECOVERY_BINDING_AMBIGUOUS: run={run_id} "
            f"matches={[str(path) for path, _ in matches]}"
        )
    return matches[0] if matches else None


def find_by_request_id(requests_dir: Path, request_id: str) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(requests_dir.glob("*.json")):
        try:
            data = _read(path)
        except Exception:
            continue
        if str(data.get("request_id") or "").strip() == request_id:
            matches.append((path, data))
    if len(matches) != 1:
        raise RuntimeError(
            f"RECOVERY_REQUEST_ID_RESOLUTION_FAILED: request_id={request_id} matches={len(matches)}"
        )
    return matches[0]


def resolve(requests_dir: Path, run_id: int) -> dict[str, str]:
    match = find_by_run(requests_dir, run_id)
    if match is None:
        return {
            "bound": "false",
            "request_id": "",
            "request_path": "",
            "topic": "",
            "trend_id": "",
            "recovery_generation": "0",
            "retry_allowed": "false",
        }
    path, data = match
    request_id = str(data.get("request_id") or path.stem).strip()
    topic = str(data.get("topic") or "").strip()
    trend_id = str(data.get("trend_id") or "").strip()
    if not request_id or not topic or not trend_id:
        raise RuntimeError(f"RECOVERY_BINDING_INCOMPLETE: {path}")
    return {
        "bound": "true",
        "request_id": request_id,
        "request_path": path.as_posix(),
        "topic": topic,
        "trend_id": trend_id,
        "recovery_generation": str(int(data.get("recovery_generation") or 0)),
        "retry_allowed": str(data.get("retry_allowed") is not False).lower(),
    }


def prepare(requests_dir: Path, run_id: int, maximum: int) -> dict[str, str]:
    match = find_by_run(requests_dir, run_id)
    if match is None:
        raise RuntimeError(f"RECOVERY_BINDING_MISSING: run={run_id}")
    path, data = match
    if data.get("retry_allowed") is False:
        raise RuntimeError(f"RECOVERY_RETRY_NOT_ALLOWED: {path}")
    current = int(data.get("recovery_generation") or 0)
    if current >= maximum:
        raise RuntimeError(f"RECOVERY_BUDGET_EXHAUSTED: generation={current} maximum={maximum}")

    generation = current + 1
    now = _now()
    history = data.setdefault("golden_path_run_history", [])
    if run_id not in history:
        history.append(run_id)
    data["recovery_generation"] = generation
    data["retry_of_run_id"] = run_id
    data["recovery_state"] = "FRESH_RECOVERY_GENERATION_PREPARED"
    data["recovery_updated_at"] = now
    data.setdefault("state_history", []).append(
        {
            "state": "FRESH_RECOVERY_GENERATION_PREPARED",
            "at": now,
            "actor": f"delivery-watch:{run_id}",
        }
    )
    _write(path, data)
    result = resolve(requests_dir, run_id)
    result["generation"] = str(generation)
    return result


def bind_new(requests_dir: Path, request_id: str, old_run_id: int, new_run_id: int) -> dict[str, str]:
    path, data = find_by_request_id(requests_dir, request_id)
    current = int(data.get("golden_path_run_id") or 0)
    history = data.setdefault("golden_path_run_history", [])
    if current != old_run_id and old_run_id not in history:
        raise RuntimeError(
            f"RECOVERY_OLD_RUN_NOT_BOUND: request_id={request_id} old={old_run_id} current={current}"
        )
    if old_run_id not in history:
        history.append(old_run_id)
    now = _now()
    data["golden_path_run_id"] = new_run_id
    data["recovery_run_id"] = new_run_id
    data["recovery_state"] = "FRESH_RECOVERY_GENERATION_RUNNING"
    data["recovery_updated_at"] = now
    data.setdefault("state_history", []).append(
        {
            "state": "FRESH_RECOVERY_GENERATION_RUNNING",
            "at": now,
            "actor": f"delivery-watch:{old_run_id}",
            "run_id": new_run_id,
        }
    )
    _write(path, data)
    return {"request_path": path.as_posix(), "request_id": request_id, "new_run_id": str(new_run_id)}


def emit(values: dict[str, str], github_output: str | None) -> None:
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as handle:
            for key, value in values.items():
                if "\n" in value or "\r" in value:
                    raise RuntimeError(f"RECOVERY_OUTPUT_MULTILINE_FORBIDDEN: {key}")
                handle.write(f"{key}={value}\n")
    print(json.dumps(values, ensure_ascii=False, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("resolve", "prepare", "bind-new"))
    parser.add_argument("--requests-dir", default="requests")
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--old-run-id", type=int)
    parser.add_argument("--new-run-id", type=int)
    parser.add_argument("--request-id")
    parser.add_argument("--maximum", type=int, default=4)
    parser.add_argument("--github-output")
    args = parser.parse_args()
    requests_dir = Path(args.requests_dir)

    if args.command == "resolve":
        if args.run_id is None:
            parser.error("resolve requires --run-id")
        values = resolve(requests_dir, args.run_id)
    elif args.command == "prepare":
        if args.run_id is None:
            parser.error("prepare requires --run-id")
        values = prepare(requests_dir, args.run_id, args.maximum)
    else:
        if args.old_run_id is None or args.new_run_id is None or not args.request_id:
            parser.error("bind-new requires --old-run-id, --new-run-id and --request-id")
        values = bind_new(requests_dir, args.request_id, args.old_run_id, args.new_run_id)

    emit(values, args.github_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
