"""Read the private terminal evidence and admit one exact Contabo quality repair."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tayvoriq_contabo_handoff import STUDIO, identity, verify

ARTIFACT_LIMIT = 5 * 1024 * 1024
FILES = ("control-plane/production-manifest.json", "recovery-checkpoint-meta.json",
         "self-heal/report.json", "job/preapproval_ai_audit.json")
STUDIO_WORKFLOW = ".github/workflows/tayvoriq-contabo-produce.yml"
CONTROLLER_WORKFLOWS = {".github/workflows/tayvoriq-contabo-controller.yml",
                        ".github/workflows/tayvoriq-golden-path.yml"}


def private_diagnostics(worker, token):
    def api(path, limit=ARTIFACT_LIMIT):
        content = subprocess.check_output(["gh", "api", "repos/" + STUDIO + path],
                                          env={**os.environ, "GH_TOKEN": token}, timeout=20, stderr=subprocess.DEVNULL)
        if len(content) > limit:
            raise ValueError("Contabo diagnostic response exceeds its limit")
        return content

    run = json.loads(api(f"/actions/runs/{worker}"))
    if (run.get("id") != worker or run.get("head_branch") != "main" or run.get("status") != "completed"
            or run.get("conclusion") != "failure" or str(run.get("path", "")).split("@")[0] != STUDIO_WORKFLOW):
        raise ValueError("Contabo worker identity is unverified")
    expected = f"tayvoriq-x-diagnostics-{worker}-attempt-{int(run['run_attempt'])}"
    artifacts = json.loads(api(f"/actions/runs/{worker}/artifacts?name={expected}"))["artifacts"]
    matches = [a for a in artifacts if a.get("name") == expected and a.get("expired") is False
               and (a.get("workflow_run") or {}).get("id") == worker and 0 < a.get("size_in_bytes", 0) <= ARTIFACT_LIMIT]
    if len(matches) != 1:
        raise ValueError("Contabo diagnostic artifact is missing or ambiguous")
    artifact = matches[0]
    payload = api(f"/actions/artifacts/{int(artifact['id'])}/zip")
    return int(artifact["id"]), run.get("updated_at"), unpack(payload, artifact.get("digest"))


def unpack(payload, digest):
    if digest != "sha256:" + hashlib.sha256(payload).hexdigest():
        raise ValueError("Contabo diagnostic digest mismatch")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if any(archive.getinfo(name).file_size > ARTIFACT_LIMIT for name in FILES):
            raise ValueError("Contabo diagnostic file exceeds its limit")
        return [json.loads(archive.read(name)) for name in FILES]


def contabo_decision(pointer, request, run, green, receipt, *, diagnostics, now=None):
    if pointer.get("execution_backend") != "contabo_private_runner" or pointer.get("state") != "ACTIVE":
        return None
    if run.get("id") != pointer.get("golden_path_run_id") or run.get("status") != "completed" or run.get("conclusion") != "failure":
        return None
    if run.get("head_branch") != "main" or str(run.get("path", "")).split("@")[0] not in CONTROLLER_WORKFLOWS:
        return None
    controller, worker = run["id"], pointer.get("execution_run_id")
    identity(request, pointer)
    if type(worker) is not int or worker <= 0:
        return None
    verify(request, pointer, controller, worker)
    if (receipt.get("schema") != "tayvoriq-contabo-worker-v1" or receipt.get("status") != "FAILED"
            or receipt.get("controller_run_id") != controller or receipt.get("worker_run_id") != worker
            or receipt.get("request_id") != request["request_id"]
            or receipt.get("source_context_sha256") != request["source_context_sha256"]):
        return None
    checked = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    due = checked.replace(second=0, microsecond=0) + timedelta(minutes=5 - checked.minute % 5)
    decision = {
        "schema": "tayvoriq-contabo-quality-decision-v1", "request_id": request["request_id"],
        "source_context_sha256": request["source_context_sha256"], "controller_run_id": controller,
        "worker_run_id": worker, "state": "DIAGNOSTICS_REQUIRED", "checked_at": checked.isoformat(),
        "next_check_at": due.isoformat(), "controller_ended_at": run.get("updated_at"), "failed_step": receipt.get("failed_step"),
        "user_action_required": False, "quality_gates_weakened": False,
    }
    if receipt.get("failed_step") != "Assert publishable production output":
        decision["state"] = "TECHNICAL_REPAIR_REQUIRED"
        return decision
    if request.get("quality_recovery", {}).get("controller_run_id") == controller:
        decision["state"] = "RECOVERY_EXHAUSTED"
    try:
        artifact, worker_ended_at, (manifest, checkpoint, report, audit) = diagnostics(worker)
        implementation = manifest["implementation_sha"]
        if (not re.fullmatch(r"[a-f0-9]{40}", implementation)
                or str(manifest.get("run_id")) != str(controller)
                or str(manifest.get("execution_run_id")) != str(worker)
                or str(checkpoint.get("run_id")) != str(controller)
                or checkpoint.get("implementation_sha") != implementation
                or any(x.get("source_request_id") != request["request_id"]
                       or x.get("source_context_sha256") != request["source_context_sha256"]
                       for x in (manifest, checkpoint))
                or any(x.get("quality_gates_weakened") is not False for x in (manifest, checkpoint, report, audit))):
            return decision
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile):
        return decision
    blockers = [v for v in audit.get("blockers") or [] if isinstance(v, str)]
    scenes = sorted(set(re.findall(r"^visual_agent:scene_off_topic:(tiktok|youtube_shorts):([1-9][0-9]?)$",
                                    "\n".join(blockers), re.MULTILINE)))
    voice = any(v.startswith("pronunciation_interpretation:") for v in blockers)
    budget = report.get("runtime_budget_seconds")
    decision.update(artifact_id=artifact, implementation_sha=implementation, stopped_at=worker_ended_at,
                    budget_seconds=budget if type(budget) is int and 60 <= budget <= 3600 else None,
                    deadline_exceeded=report.get("deadline_exceeded") is True,
                    voice_blocked=voice, scenes=[{"platform": p, "scene": int(n)} for p, n in scenes])
    if decision["state"] == "RECOVERY_EXHAUSTED":
        return decision
    decision["state"] = "QUALITY_REPAIR_REQUIRED"
    if (audit.get("passed") is False and report.get("state") == "PUBLISHABLE_OUTPUT_RETRY_REQUIRED"
            and decision["deadline_exceeded"] and 0 < len(scenes) <= 2 and voice):
        decision["state"] = "AWAITING_VERIFIED_REPAIR"
        if (green.get("schema") == "tayvoriq-production-green-v1" and green.get("implementation_repository") == STUDIO
                and green.get("full_preflight_passed") is True and green.get("quality_gates_weakened") is False
                and green.get("mixed_checkpoint_recovery_verified") is True
                and re.fullmatch(r"[a-f0-9]{40}", (candidate := green.get("implementation_sha") or ""))
                and candidate != implementation):
            decision.update(state="RETRY_ELIGIBLE", next_implementation_sha=candidate, planned_attempts=1)
            stable = [decision[k] for k in ("request_id", "controller_run_id", "worker_run_id", "artifact_id", "next_implementation_sha")]
            decision["decision_key"] = hashlib.sha256(json.dumps(stable).encode()).hexdigest()
    return decision
