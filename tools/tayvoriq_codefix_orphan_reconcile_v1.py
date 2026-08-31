from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REQUESTS = ROOT / "requests"
POLICY = ROOT / "tools" / "tayvoriq_recovery_policy_v1.py"


def _run(args: list[str], *, check: bool = True, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


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


def _candidate_requests() -> list[tuple[int, Path]]:
    candidates: list[tuple[int, Path]] = []
    for path in sorted(REQUESTS.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(data.get("status") or "") != "DISPATCHED":
            continue
        if not _telegram_bound(data) or not _auto_repair(data):
            continue
        codefix = data.get("codefix_recovery") if isinstance(data.get("codefix_recovery"), dict) else {}
        if str(codefix.get("status") or "") in {"ARMED", "REPLAY_DISPATCHED"}:
            continue
        try:
            run_id = int(data.get("golden_path_run_id") or 0)
        except (TypeError, ValueError):
            run_id = 0
        if run_id > 0:
            candidates.append((run_id, path))
    return sorted(candidates, reverse=True)


def _run_metadata(repo: str, run_id: int) -> dict[str, Any] | None:
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
        if str(data.get("status") or "") != "DISPATCHED":
            return False, "", "", 0
        if int(data.get("golden_path_run_id") or 0) != run_id:
            return False, "", "", 0
        existing = data.get("codefix_recovery") if isinstance(data.get("codefix_recovery"), dict) else {}
        if str(existing.get("status") or "") in {"ARMED", "REPLAY_DISPATCHED"}:
            return False, "", "", 0

        request_id = str(data.get("request_id") or "").strip()
        topic = str(data.get("topic") or "").strip()
        generation = max(0, int(data.get("recovery_generation") or 0))
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        data["codefix_recovery"] = {
            "status": "ARMED",
            "request_substate": "AWAITING_CODEFIX",
            "failed_run_id": run_id,
            "failure_signature": signature,
            "failure_state": state,
            "failed_control_plane_sha": failed_control,
            "failed_implementation_sha": failed_impl,
            "recovery_generation": generation,
            "armed_at": now,
            "same_generation_replay_required": True,
            "exact_source_request_required": True,
            "quality_gates_weakened": False,
            "orphan_reconciled": True,
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
                    "failed_control_plane_sha": failed_control,
                    "failed_implementation_sha": failed_impl,
                    "recovery_generation": generation,
                    "reason": "orphaned-deterministic-failure-reconciled",
                    "quality_gates_weakened": False,
                },
            }
        ]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _run(["git", "add", "--", str(relative_path)])
        diff = _run(["git", "diff", "--cached", "--quiet"], check=False)
        if diff.returncode == 0:
            return False, "", "", 0
        _run(["git", "commit", "-m", f"ops: reconcile deterministic codefix orphan {request_id} run {run_id}"])
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
        "✅ Der verwaiste Fehlerlauf wurde automatisch wieder aufgenommen.\n"
        "✅ Auftrag, Trendfreigabe und geprüfte Quellen bleiben gebunden.\n"
        "✅ Es wird NICHT blind erneut produziert.\n"
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

    for run_id, path in _candidate_requests():
        run_meta = _run_metadata(repo, run_id)
        if run_meta is None:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        generation = max(0, int(data.get("recovery_generation") or 0))
        with tempfile.TemporaryDirectory(prefix="tayvoriq-codefix-orphan-") as raw_temp:
            temp = Path(raw_temp)
            logs = temp / "failed.log"
            if not _failed_logs(run_id, logs):
                print(f"CODEFIX_ORPHAN_NO_FAILED_LOGS:{run_id}")
                continue
            policy_path = temp / "policy.json"
            policy = _policy(logs, int(run_meta.get("run_attempt") or 1), generation, policy_path)
            if not policy or str(policy.get("mode") or "") != "deterministic":
                continue
            failed_control, failed_impl = _diagnostic_shas(
                run_id, int(run_meta.get("run_attempt") or 1), run_meta, temp
            )
            relative = path.relative_to(ROOT)
            armed, request_id, topic, armed_generation = _arm_request(
                relative,
                run_id,
                str(policy.get("failure_signature") or ""),
                str(policy.get("state") or "CODE_REPAIR_REQUIRED"),
                failed_control,
                failed_impl,
            )
            if armed:
                print(
                    json.dumps(
                        {
                            "state": "ORPHAN_CODEFIX_ARMED",
                            "request_id": request_id,
                            "run_id": run_id,
                            "recovery_generation": armed_generation,
                            "failed_implementation_sha": failed_impl,
                            "quality_gates_weakened": False,
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
