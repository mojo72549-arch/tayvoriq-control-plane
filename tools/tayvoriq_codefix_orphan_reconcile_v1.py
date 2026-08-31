from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REQUESTS = ROOT / "requests"
POLICY = ROOT / "tools" / "tayvoriq_recovery_policy_v1.py"
ACTIVE_POINTER = ROOT / ".github" / "state" / "tayvoriq-active-production-request.json"
ACTIVE_POINTER_SCHEMA = "tayvoriq-active-production-request-v1"


def _run(args: list[str], *, check: bool = True, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _telegram_bound(data: dict[str, Any]) -> bool:
    source = data.get("source_context") if isinstance(data.get("source_context"), dict) else {}
    return (
        str(data.get("source") or "").strip() == "telegram_trend_approval"
        or data.get("telegram_only_user_path") is True
        or source.get("telegram_only_user_path") is True
        or str(data.get("communication_channel") or "").strip() == "telegram"
    )


def _auto_repair(data: dict[str, Any]) -> bool:
    source = data.get("source_context") if isinstance(data.get("source_context"), dict) else {}
    return (
        data.get("auto_repair_until_review") is True
        or source.get("auto_repair_until_review") is True
        or str(data.get("source") or "").strip() == "telegram_trend_approval"
    )


def _active_pointer() -> dict[str, Any] | None:
    """Return the single canonical production owner or fail closed."""
    if not ACTIVE_POINTER.is_file():
        print("CODEFIX_ACTIVE_POINTER_MISSING")
        return None
    try:
        data = json.loads(ACTIVE_POINTER.read_text(encoding="utf-8"))
    except Exception:
        print("CODEFIX_ACTIVE_POINTER_INVALID_JSON")
        return None
    if str(data.get("schema") or "") != ACTIVE_POINTER_SCHEMA:
        print("CODEFIX_ACTIVE_POINTER_SCHEMA_INVALID")
        return None
    if str(data.get("state") or "") != "ACTIVE":
        print("CODEFIX_ACTIVE_POINTER_NOT_ACTIVE")
        return None
    request_id = str(data.get("request_id") or "").strip()
    if not request_id or any(char in request_id for char in "/\\\r\n"):
        print("CODEFIX_ACTIVE_POINTER_REQUEST_ID_INVALID")
        return None
    if _int(data.get("golden_path_run_id")) <= 0:
        print("CODEFIX_ACTIVE_POINTER_RUN_ID_INVALID")
        return None
    return data


def _replay_status_allows_rearm(codefix: dict[str, Any], run_id: int) -> bool:
    """Allow a completed failed replay to become the next codefix owner.

    ARMED already owns its failed run and must never be duplicated. A
    REPLAY_DISPATCHED record is different: if its replay_run_id is exactly the
    canonical active run that has now failed, the replay itself needs a new
    deterministic codefix handoff. Any other binding is treated as stale and is
    rejected fail-closed.
    """
    status = str(codefix.get("status") or "").strip()
    if not status:
        return True
    if status == "ARMED":
        return False
    if status == "REPLAY_DISPATCHED":
        replay_run = _int(codefix.get("replay_run_id"))
        if replay_run == run_id:
            return True
        print(f"CODEFIX_REPLAY_BINDING_MISMATCH:replay={replay_run}:active={run_id}")
        return False
    return True


def _candidate_requests() -> list[tuple[datetime, int, Path]]:
    """Return exactly the active production request; never scan history."""
    pointer = _active_pointer()
    if pointer is None:
        return []

    active_request_id = str(pointer["request_id"]).strip()
    explicit_target = str(os.environ.get("TAYVORIQ_RECOVERY_TARGET_REQUEST_ID") or "").strip()
    if explicit_target:
        if any(char in explicit_target for char in "/\\\r\n"):
            raise RuntimeError("CODEFIX_ORPHAN_TARGET_REQUEST_ID_INVALID")
        if explicit_target != active_request_id:
            print(f"CODEFIX_TARGET_NOT_ACTIVE:target={explicit_target}:active={active_request_id}")
            return []

    path = REQUESTS / f"{active_request_id}.json"
    if not path.is_file():
        print(f"CODEFIX_ACTIVE_REQUEST_FILE_MISSING:{active_request_id}")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        print(f"CODEFIX_ACTIVE_REQUEST_INVALID_JSON:{active_request_id}")
        return []

    if str(data.get("request_id") or "").strip() != active_request_id:
        print("CODEFIX_ACTIVE_REQUEST_ID_MISMATCH")
        return []
    if str(data.get("status") or "") != "DISPATCHED":
        return []
    if not _telegram_bound(data) or not _auto_repair(data):
        return []

    approved_at = _parse_time(data.get("approved_at"))
    if approved_at is None:
        print("CODEFIX_ACTIVE_REQUEST_APPROVAL_TIME_INVALID")
        return []
    run_id = _int(data.get("golden_path_run_id"))
    pointer_run_id = _int(pointer.get("golden_path_run_id"))
    if run_id <= 0 or run_id != pointer_run_id:
        print(f"CODEFIX_ACTIVE_RUN_MISMATCH:request={run_id}:pointer={pointer_run_id}")
        return []

    codefix = data.get("codefix_recovery") if isinstance(data.get("codefix_recovery"), dict) else {}
    if not _replay_status_allows_rearm(codefix, run_id):
        return []

    for field in ("approval_key", "source_context_sha256", "contract_sha256"):
        pointer_value = str(pointer.get(field) or "").strip()
        request_value = str(data.get(field) or "").strip()
        if pointer_value and pointer_value != request_value:
            print(f"CODEFIX_ACTIVE_POINTER_{field.upper()}_MISMATCH")
            return []

    return [(approved_at, run_id, path)]


def _run_metadata(repo: str, run_id: int, approved_at: datetime) -> dict[str, Any] | None:
    try:
        result = _run(["gh", "api", f"repos/{repo}/actions/runs/{run_id}"])
        data = json.loads(result.stdout)
    except Exception as exc:
        print(f"CODEFIX_ORPHAN_RUN_LOOKUP_FAILED:{run_id}:{type(exc).__name__}")
        return None
    if str(data.get("name") or "") != "TAYVORIQ-X Golden Path":
        return None
    if str(data.get("status") or "") != "completed":
        return None
    if str(data.get("conclusion") or "") == "success":
        return None
    run_created = _parse_time(data.get("created_at"))
    if run_created is None or run_created < approved_at - timedelta(minutes=5):
        print(f"CODEFIX_ORPHAN_RUN_PRECEDES_APPROVAL:{run_id}")
        return None
    return data


def _failed_logs(run_id: int, target: Path) -> bool:
    result = _run(["gh", "run", "view", str(run_id), "--log-failed"], check=False)
    target.write_text(result.stdout or "", encoding="utf-8")
    return target.is_file() and bool(target.read_text(encoding="utf-8", errors="replace").strip())


def _policy(logs: Path, run_attempt: int, generation: int, target: Path) -> dict[str, Any] | None:
    result = _run(
        [
            sys.executable,
            str(POLICY),
            "--logs-file",
            str(logs),
            "--run-attempt",
            str(max(1, run_attempt)),
            "--recovery-generation",
            str(max(0, generation)),
            "--max-generations",
            "4",
            "--owner-found",
            "true",
            "--owner-current",
            "true",
            "--exact-request-retry",
            "true",
            "--output-json",
            str(target),
        ],
        check=False,
    )
    if result.returncode != 0 or not target.is_file():
        print(f"CODEFIX_ORPHAN_POLICY_FAILED:{result.stdout[-500:]}")
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None


def _diagnostic_shas(run_id: int, run_attempt: int, run_meta: dict[str, Any], temp: Path) -> tuple[str, str]:
    failed_control = str(run_meta.get("head_sha") or "").strip()
    failed_impl = ""
    diag = temp / "diagnostics"
    diag.mkdir(parents=True, exist_ok=True)
    artifact = f"tayvoriq-x-diagnostics-{run_id}-attempt-{max(1, run_attempt)}"
    _run(["gh", "run", "download", str(run_id), "-n", artifact, "-D", str(diag)], check=False)
    manifests = list(diag.rglob("production-manifest.json"))
    if manifests:
        try:
            data = json.loads(manifests[0].read_text(encoding="utf-8"))
            failed_control = str(data.get("control_plane_sha") or failed_control).strip()
            failed_impl = str(data.get("implementation_sha") or "").strip()
        except Exception:
            pass
    return failed_control, failed_impl


def _still_active(request_id: str, run_id: int) -> bool:
    pointer = _active_pointer()
    if pointer is None:
        return False
    return (
        str(pointer.get("request_id") or "").strip() == request_id
        and _int(pointer.get("golden_path_run_id")) == run_id
    )


def _arm_request(
    relative_path: Path,
    run_id: int,
    signature: str,
    state: str,
    failed_control: str,
    failed_impl: str,
) -> tuple[bool, str, str, int]:
    _run(["git", "config", "user.name", "github-actions[bot]"])
    _run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])

    for attempt in range(1, 6):
        _run(["git", "fetch", "origin", "main", "--quiet"])
        _run(["git", "reset", "--hard", "origin/main"])
        path = ROOT / relative_path
        if not path.is_file():
            return False, "", "", 0
        data = json.loads(path.read_text(encoding="utf-8"))
        request_id = str(data.get("request_id") or "").strip()
        if not _still_active(request_id, run_id):
            print(f"CODEFIX_ARM_ABORTED_NOT_ACTIVE:{request_id}:{run_id}")
            return False, "", "", 0
        if str(data.get("status") or "") != "DISPATCHED":
            return False, "", "", 0
        if _int(data.get("golden_path_run_id")) != run_id:
            return False, "", "", 0

        existing = data.get("codefix_recovery") if isinstance(data.get("codefix_recovery"), dict) else {}
        if not _replay_status_allows_rearm(existing, run_id):
            return False, "", "", 0

        replay_rearm = str(existing.get("status") or "") == "REPLAY_DISPATCHED" and _int(existing.get("replay_run_id")) == run_id
        effective_failed_control = str(failed_control or "").strip()
        effective_failed_impl = str(failed_impl or "").strip()
        if replay_rearm:
            effective_failed_control = effective_failed_control or str(existing.get("replay_control_plane_sha") or "").strip()
            effective_failed_impl = effective_failed_impl or str(existing.get("replay_implementation_sha") or "").strip()

        topic = str(data.get("topic") or "").strip()
        generation = max(0, _int(data.get("recovery_generation")))
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        data["codefix_recovery"] = {
            "status": "ARMED",
            "request_substate": "AWAITING_CODEFIX",
            "failed_run_id": run_id,
            "failure_signature": signature,
            "failure_state": state,
            "failed_control_plane_sha": effective_failed_control,
            "failed_implementation_sha": effective_failed_impl,
            "recovery_generation": generation,
            "armed_at": now,
            "same_generation_replay_required": True,
            "exact_source_request_required": True,
            "quality_gates_weakened": False,
            "orphan_reconciled": True,
            "active_pointer_verified": True,
            "rearmed_after_failed_replay": replay_rearm,
            "previous_codefix_failed_run_id": _int(existing.get("failed_run_id")) if replay_rearm else 0,
            "previous_codefix_failure_signature": str(existing.get("failure_signature") or "") if replay_rearm else "",
        }
        data["state_history"] = list(data.get("state_history") or []) + [
            {
                "state": "AWAITING_CODEFIX",
                "at": now,
                "actor": "tayvoriq-codefix-orphan-reconcile-v1",
                "meta": {
                    "failed_run_id": run_id,
                    "failure_signature": signature,
                    "failure_state": state,
                    "failed_control_plane_sha": effective_failed_control,
                    "failed_implementation_sha": effective_failed_impl,
                    "recovery_generation": generation,
                    "reason": "failed-codefix-replay-rearmed" if replay_rearm else "active-request-deterministic-failure-reconciled",
                    "quality_gates_weakened": False,
                    "active_pointer_verified": True,
                },
            }
        ]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _run(["git", "add", "--", str(relative_path)])
        diff = _run(["git", "diff", "--cached", "--quiet"], check=False)
        if diff.returncode == 0:
            return False, "", "", 0
        _run(["git", "commit", "-m", f"ops: reconcile active deterministic codefix {request_id} run {run_id}"])
        pushed = _run(["git", "push", "origin", "HEAD:main"], check=False)
        if pushed.returncode == 0:
            return True, request_id, topic, generation
        time.sleep(attempt * 2)
    raise RuntimeError("CODEFIX_ORPHAN_ARM_PUSH_FAILED")


def _send_telegram(topic: str, run_id: int, generation: int) -> None:
    token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        print("CODEFIX_ORPHAN_TELEGRAM_SKIPPED_NO_SECRETS")
        return
    text = (
        "🧰 TAYVORIQ · Codefix-Recovery ist aktiv\n\n"
        f"Thema: {topic[:180]}\n"
        f"Fehlgeschlagener Run: {run_id}\n"
        f"Recovery: Generation {generation}\n\n"
        "✅ Ausschließlich der aktuell freigegebene Telegram-Auftrag wurde übernommen.\n"
        "✅ Auftrag, Trendfreigabe und geprüfte Quellen bleiben gebunden.\n"
        "✅ Historische Requests werden nicht automatisch reaktiviert.\n"
        "➡️ Derselbe Auftrag läuft weiter, sobald ein passender Production-Green-Codefix bestätigt ist."
    )
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("ok") is not True:
        raise RuntimeError("CODEFIX_ORPHAN_TELEGRAM_UNVERIFIED")


def main() -> int:
    repo = str(os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not repo:
        raise RuntimeError("CODEFIX_ORPHAN_GITHUB_REPOSITORY_MISSING")

    for approved_at, run_id, path in _candidate_requests():
        run_meta = _run_metadata(repo, run_id, approved_at)
        if run_meta is None:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        generation = max(0, _int(data.get("recovery_generation")))
        with tempfile.TemporaryDirectory(prefix="tayvoriq-codefix-orphan-") as raw_temp:
            temp = Path(raw_temp)
            logs = temp / "failed.log"
            if not _failed_logs(run_id, logs):
                print(f"CODEFIX_ORPHAN_NO_FAILED_LOGS:{run_id}")
                continue
            policy_path = temp / "policy.json"
            policy = _policy(logs, _int(run_meta.get("run_attempt")) or 1, generation, policy_path)
            if not policy:
                print(f"CODEFIX_ORPHAN_POLICY_UNAVAILABLE:{run_id}")
                continue
            mode = str(policy.get("mode") or "")
            state = str(policy.get("state") or "")
            print(f"CODEFIX_ORPHAN_POLICY_DECISION:{run_id}:mode={mode}:state={state}")
            if mode != "deterministic":
                continue
            failed_control, failed_impl = _diagnostic_shas(run_id, _int(run_meta.get("run_attempt")) or 1, run_meta, temp)
            relative = path.relative_to(ROOT)
            armed, request_id, topic, armed_generation = _arm_request(
                relative,
                run_id,
                str(policy.get("failure_signature") or ""),
                state or "CODE_REPAIR_REQUIRED",
                failed_control,
                failed_impl,
            )
            if armed:
                refreshed = json.loads((ROOT / relative).read_text(encoding="utf-8"))
                codefix = refreshed.get("codefix_recovery") if isinstance(refreshed.get("codefix_recovery"), dict) else {}
                print(
                    json.dumps(
                        {
                            "state": "ACTIVE_CODEFIX_ARMED",
                            "request_id": request_id,
                            "run_id": run_id,
                            "recovery_generation": armed_generation,
                            "failed_implementation_sha": str(codefix.get("failed_implementation_sha") or failed_impl),
                            "rearmed_after_failed_replay": codefix.get("rearmed_after_failed_replay") is True,
                            "quality_gates_weakened": False,
                            "active_pointer_verified": True,
                        },
                        ensure_ascii=False,
                    )
                )
                _send_telegram(topic, run_id, armed_generation)
                return 0

    print("CODEFIX_ORPHAN_RECONCILE_NOOP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
