"""Read the private terminal evidence and admit one exact Contabo quality repair."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from tayvoriq_contabo_handoff import STUDIO, identity, verify

ARTIFACT_LIMIT = 5 * 1024 * 1024
FILES = ("control-plane/production-manifest.json", "recovery-checkpoint-meta.json",
         "self-heal/report.json", "job/preapproval_ai_audit.json")
STUDIO_WORKFLOW = ".github/workflows/tayvoriq-contabo-produce.yml"
VOICE_RECOVERY = "VOICE_CHECKPOINT_ISOLATION"
SCENE_RECOVERY = "SINGLE_SCENE_CHECKPOINT_REPAIR"
VOICE_PLAN = "ISOLATE_PLATFORM_VOICE_CHECKPOINTS"
CONTROLLER_WORKFLOWS = {".github/workflows/tayvoriq-contabo-controller.yml",
                        ".github/workflows/tayvoriq-golden-path.yml"}


def private_diagnostics(worker, token, *, controller=None):
    def api(path, limit=ARTIFACT_LIMIT):
        content = subprocess.check_output(["gh", "api", "repos/" + STUDIO + path],
                                          env={**os.environ, "GH_TOKEN": token}, timeout=20, stderr=subprocess.DEVNULL)
        if len(content) > limit:
            raise ValueError("Contabo diagnostic response exceeds its limit")
        return content

    if type(controller) is int and controller > 0:
        try:
            file = json.loads(api(f"/contents/run-status/contabo/stop-proof/{controller}.json?ref=main"))
            proof = json.loads(base64.b64decode(file["content"]))
            if (proof.get("schema") == "tayvoriq-contabo-stop-proof-v1" and proof.get("controller_run_id") == controller
                    and proof.get("worker_run_id") == worker and type(proof.get("artifact_id")) is int
                    and re.fullmatch(r"sha256:[a-f0-9]{64}", proof.get("artifact_digest", ""))
                    and isinstance(proof.get("evidence"), list) and len(proof["evidence"]) == 4):
                return proof["artifact_id"], proof.get("stopped_at"), proof["evidence"]
        except (ValueError, KeyError, TypeError, subprocess.SubprocessError):
            pass

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


def private_technical_case(controller, token):
    try:
        response = subprocess.check_output(
            ["gh", "api", f"repos/{STUDIO}/contents/run-status/contabo/technical-cases/{controller}.json?ref=main"],
            env={**os.environ, "GH_TOKEN": token}, timeout=12, stderr=subprocess.DEVNULL)
        return json.loads(base64.b64decode(json.loads(response)["content"]))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return {}


def private_scene_worker_ready(token, control_repo):
    """Check the executable private workflow's immutable reusable-workflow pin."""
    def content(repo, path, ref):
        payload = subprocess.check_output(
            ["gh", "api", f"repos/{repo}/contents/{path}?ref={ref}"],
            env={**os.environ, "GH_TOKEN": token}, timeout=15, stderr=subprocess.DEVNULL,
        )
        return base64.b64decode(json.loads(payload)["content"]).decode()

    reusable = ".github/workflows/tayvoriq-deliver-video-now.yml"
    try:
        worker = content(STUDIO, STUDIO_WORKFLOW, "main")
        pins = re.findall(r"^\s*uses:\s*" + re.escape(f"{control_repo}/{reusable}") + r"@([a-f0-9]{40})\s*$",
                          worker, re.MULTILINE)
        if len(pins) != 1:
            return False
        called = content(control_repo, reusable, pins[0])
        return all(marker in called for marker in ("SINGLE_SCENE_CHECKPOINT_REQUIRED", "--single-scene-parent-run", "--single-scene"))
    except (KeyError, OSError, ValueError, subprocess.SubprocessError):
        return False


def contabo_decision(pointer, request, run, green, receipt, *, diagnostics, technical_lookup=None,
                     scoped_worker_ready=None, now=None):
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
    decision = {
        "schema": "tayvoriq-contabo-quality-decision-v1", "request_id": request["request_id"],
        "source_context_sha256": request["source_context_sha256"], "controller_run_id": controller,
        "worker_run_id": worker, "state": "DIAGNOSTICS_REQUIRED", "checked_at": checked.isoformat(),
        "controller_ended_at": run.get("updated_at"), "failed_step": receipt.get("failed_step"),
        "user_action_required": False, "quality_gates_weakened": False,
    }
    if receipt.get("failed_step") != "Assert publishable production output":
        decision["state"] = "TECHNICAL_REPAIR_REQUIRED"
        return decision
    previous = request.get("quality_recovery") or {}
    attempt_used = previous.get("controller_run_id") == controller
    decision["attempt_used"] = attempt_used
    if attempt_used and previous.get("repair_kind") == SCENE_RECOVERY:
        decision["state"] = "RECOVERY_EXHAUSTED"
        return decision
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
    timeout = report.get("timeout")
    if (isinstance(timeout, dict) and timeout.get("kind") == "LOCAL_REPAIR_WALL"
            and timeout.get("seconds") == decision["budget_seconds"] and decision["deadline_exceeded"]
            and type(timeout.get("job_id")) is int and timeout["job_id"] > 0
            and isinstance(timeout.get("at"), str)):
        voice_passed = report.get("voice_platforms_passed") == ["tiktok", "youtube_shorts"] and not voice
        decision.update(timeout=timeout, voice_platforms_passed=voice_passed,
                        state="AWAITING_VERIFIED_SCENE_FIX" if scenes and voice_passed
                        and report.get("repair_target_stages") == ["VISUALS"] else "TECHNICAL_REPAIR_REQUIRED")
        candidate = green.get("implementation_sha") or ""
        if (decision["state"] == "AWAITING_VERIFIED_SCENE_FIX" and len(scenes) == 1
                and audit.get("passed") is False and report.get("state") == "PUBLISHABLE_OUTPUT_RETRY_REQUIRED"
                and green.get("schema") == "tayvoriq-production-green-v1"
                and green.get("implementation_repository") == STUDIO
                and green.get("full_preflight_passed") is True and green.get("quality_gates_weakened") is False
                and green.get("single_scene_checkpoint_repair_verified") is True
                and isinstance(candidate, str) and re.fullmatch(r"[a-f0-9]{40}", candidate) and candidate != implementation
                and scoped_worker_ready and scoped_worker_ready()):
            key = [request["request_id"], controller, worker, artifact, SCENE_RECOVERY, *scenes[0]]
            decision.update(state="RETRY_ELIGIBLE", next_implementation_sha=candidate, planned_attempts=1,
                            repair_kind=SCENE_RECOVERY, decision_key=hashlib.sha256(json.dumps(key).encode()).hexdigest())
        return decision
    if attempt_used:
        decision["state"] = "RECOVERY_EXHAUSTED"
        timeout = report.get("voice_timeout_seconds")
        if (type(timeout) is int and 60 <= timeout <= 1800 and voice
                and report.get("state") == "PUBLISHABLE_OUTPUT_RETRY_REQUIRED"
                and request["quality_recovery"].get("repair_kind") != VOICE_RECOVERY):
            decision.update(state="TECHNICAL_ANALYSIS_REQUIRED", voice_timeout_seconds=timeout)
            case = technical_lookup(controller) if technical_lookup else {}
            if (case.get("schema") == "tayvoriq-contabo-technical-case-v1"
                    and all(case.get(k) == decision[k] for k in
                            ("request_id", "source_context_sha256", "controller_run_id", "worker_run_id", "artifact_id"))
                    and case.get("failed_implementation_sha") == implementation
                    and case.get("voice_timeout_seconds") == timeout and case.get("quality_gates_weakened") is False):
                decision["technical_case_state"] = case.get("state")
                if case.get("state") == "PLAN_VERIFIED" and case.get("plan") == VOICE_PLAN and case.get("shared_checkpoint_proved") is True:
                    decision["state"] = "AWAITING_VERIFIED_TECHNICAL_FIX"
                    candidate = green.get("implementation_sha") or ""
                    if (green.get("schema") == "tayvoriq-production-green-v1"
                            and green.get("implementation_repository") == STUDIO
                            and green.get("full_preflight_passed") is True and green.get("quality_gates_weakened") is False
                            and green.get("voice_checkpoint_isolation_verified") is True
                            and isinstance(candidate, str) and re.fullmatch(r"[a-f0-9]{40}", candidate) and candidate != implementation):
                        key = [request["request_id"], controller, worker, artifact, candidate, VOICE_RECOVERY]
                        decision.update(state="RETRY_ELIGIBLE", next_implementation_sha=candidate, planned_attempts=1,
                                        repair_kind=VOICE_RECOVERY,
                                        decision_key=hashlib.sha256(json.dumps(key).encode()).hexdigest())
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
