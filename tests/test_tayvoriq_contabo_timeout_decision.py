import base64
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tayvoriq_contabo_operator_event import build_event, notify
from tayvoriq_contabo_recovery_decision import PADDING_RECOVERY, SCENE_RECOVERY, contabo_decision, private_diagnostics
from tayvoriq_lifecycle_dispatch_v1 import dispatch_verified

REQUEST = "telegram-3821-trend-1-content-repair-v1"
CONTROLLER = 45988482504
WORKER = 45988694096
ARTIFACT = 15194561067


def stopped_request():
    context = {}
    binding = {"request_id": REQUEST, "source_context_sha256": hashlib.sha256(b"{}").hexdigest(),
               "contract_sha256": "contract", "approval_key": "approved"}
    studio = "mojo72549-arch/shorts-agent-studio"
    receipt = {**binding, "schema": "tayvoriq-contabo-worker-v1", "status": "FAILED",
               "controller_run_id": CONTROLLER, "worker_run_id": WORKER,
               "failed_step": "Assert publishable production output"}
    request = {**binding, "source_context": context, "golden_path_run_id": CONTROLLER,
               "approved_at": "2026-11-27T06:09:04Z", "telegram_message_id": 3821,
               "quality_recovery": {"controller_run_id": CONTROLLER, "planned_attempts": 1},
               "contabo_handoff": {**receipt, "schema": "tayvoriq-contabo-handoff-v1",
                                   "execution_repository": studio, "quality_gates_weakened": False}}
    pointer = {**binding, "execution_backend": "contabo_private_runner", "state": "ACTIVE",
               "execution_repository": studio, "golden_path_run_id": CONTROLLER, "execution_run_id": WORKER}
    run = {"id": CONTROLLER, "head_branch": "main", "status": "completed", "conclusion": "failure",
           "path": ".github/workflows/tayvoriq-contabo-controller.yml", "updated_at": "2026-11-27T11:40:49Z"}
    return pointer, request, run, {}, receipt


def diagnostics(request, *, scenes=("visual_agent:scene_off_topic:tiktok:6",)):
    binding = {"run_id": str(CONTROLLER), "source_request_id": REQUEST,
               "source_context_sha256": request["source_context_sha256"],
               "implementation_sha": "76b8abdd650512400649ba48c015524f74435062",
               "quality_gates_weakened": False}
    report = {"state": "PUBLISHABLE_OUTPUT_RETRY_REQUIRED", "repair_target_stages": ["VISUALS"],
              "runtime_budget_seconds": 1500, "deadline_exceeded": True, "quality_gates_weakened": False,
              "voice_platforms_passed": ["tiktok", "youtube_shorts"],
              "timeout": {"kind": "LOCAL_REPAIR_WALL", "job_id": 140470803069, "seconds": 1500,
                          "at": "2026-11-27T11:39:40.0746435Z", "repair_round": 2}}
    audit = {"passed": False, "quality_gates_weakened": False, "blockers": list(scenes)}
    return ARTIFACT, "2026-11-27T11:40:26Z", ({**binding, "execution_run_id": WORKER}, binding, report, audit)


def test_sap_wall_timeout_has_stable_scene_repair_decision_and_no_unconfirmed_schedule():
    args = stopped_request()
    # A new process computes the same event from the same terminal facts.
    def classify(minute):
        proof = contabo_decision(*args, diagnostics=lambda _: diagnostics(args[1]),
                                 now=datetime(2026, 11, 27, 12, minute, tzinfo=timezone.utc))
        return proof, build_event({"contabo_repair": proof})

    proof, event = classify(30)
    assert proof["state"] == "AWAITING_VERIFIED_SCENE_FIX"
    assert proof["attempt_used"] is True
    assert event == classify(35)[1]
    assert "25 Minuten" in event["cause"] and "Bildkorrektur 2" in event["cause"]
    assert "Sprecherfassungen" in event["done"]
    assert "TikTok-Szene 6" in event["decision_required"]
    assert "kein Reparaturjob eingeplant" in event["next"]
    assert "next_check_at" not in event and not event["user_action_required"]


def test_missing_diagnostics_stays_concrete_and_never_dispatches():
    def unavailable(_):
        raise FileNotFoundError

    proof = contabo_decision(*stopped_request(), diagnostics=unavailable)
    event = build_event({"contabo_repair": proof})
    assert proof["state"] == "DIAGNOSTICS_REQUIRED"
    assert "Diagnoseartefakt" in event["decision_required"]
    assert "decision_key" not in proof


def test_single_scene_timeout_requires_promoted_fix_and_executable_worker_pin():
    pointer, request, run, _, receipt = stopped_request()
    green = {"schema": "tayvoriq-production-green-v1", "implementation_repository": "mojo72549-arch/shorts-agent-studio",
             "implementation_sha": "e" * 40, "full_preflight_passed": True,
             "quality_gates_weakened": False, "single_scene_checkpoint_repair_verified": True}

    def classify(worker_ready):
        return contabo_decision(pointer, request, run, green, receipt,
                                diagnostics=lambda _: diagnostics(request), scoped_worker_ready=lambda: worker_ready)

    assert classify(False)["state"] == "AWAITING_VERIFIED_SCENE_FIX"
    allowed = classify(True)
    assert allowed["state"] == "RETRY_ELIGIBLE"
    assert allowed["repair_kind"] == SCENE_RECOVERY and allowed["planned_attempts"] == 1
    assert allowed["scenes"] == [{"platform": "tiktok", "scene": 6}]
    green["implementation_sha"] = "f" * 40
    assert classify(True)["decision_key"] == allowed["decision_key"]
    request["quality_recovery"]["repair_kind"] = SCENE_RECOVERY
    assert classify(True)["state"] == "RECOVERY_EXHAUSTED"


def test_passing_scene_repair_can_authorize_only_the_later_terminal_mix_failure():
    pointer, request, run, _, receipt = stopped_request()
    request["quality_recovery"]["repair_kind"] = SCENE_RECOVERY
    green = {"schema": "tayvoriq-production-green-v1", "implementation_repository": "mojo72549-arch/shorts-agent-studio",
             "implementation_sha": "f" * 40, "full_preflight_passed": True,
             "quality_gates_weakened": False, "terminal_padding_checkpoint_verified": True}
    artifact, ts, (manifest, checkpoint, report, audit) = diagnostics(request)
    audit.update(passed=True, blockers=[])
    gate = {"top_level_issues": ["final-production-mix-gate-not-passed"], "quality_gates_weakened": False,
            "variants": {"youtube_shorts": {"passed": True}, "tiktok": {"passed": True}},
            "production_mix": {"passed": False, "quality_gates_weakened": False, "cross_variant_issues": [],
                               "variants": {"youtube_shorts": {"passed": False, "issues": ["production-mix-silent-interval"]},
                                            "tiktok": {"passed": True, "issues": []}}}}

    def classify():
        return contabo_decision(pointer, request, run, green, receipt, scoped_worker_ready=lambda: True,
                                diagnostics=lambda _: (artifact, ts, (manifest, checkpoint, report, audit, gate)))

    proof = classify()
    assert (proof["state"], proof["repair_kind"], proof["platform"]) == ("RETRY_ELIGIBLE", PADDING_RECOVERY, "youtube_shorts")
    request["quality_recovery"]["repair_kind"] = PADDING_RECOVERY
    assert classify()["state"] == "RECOVERY_EXHAUSTED"


def test_private_stop_proof_can_carry_the_bound_final_mix_report(monkeypatch):
    proof = {"schema": "tayvoriq-contabo-stop-proof-v1", "controller_run_id": CONTROLLER,
             "worker_run_id": WORKER, "artifact_id": ARTIFACT, "artifact_digest": "sha256:" + "f" * 64,
             "evidence": [{"report_index": i} for i in range(5)]}

    def api(command, **kwargs):
        assert f"/stop-proof/{CONTROLLER}.json?ref=main" in command[-1]
        return json.dumps({"content": base64.b64encode(json.dumps(proof).encode()).decode()}).encode()

    monkeypatch.setattr(subprocess, "check_output", api)
    assert private_diagnostics(WORKER, "test-token", controller=CONTROLLER, include_mix=True)[2] == proof["evidence"]
    assert private_diagnostics(WORKER, "test-token", controller=CONTROLLER)[2] == proof["evidence"][:4]


def test_lost_dispatch_response_and_restart_do_not_submit_a_second_repair(tmp_path):
    claim = tmp_path / "claim"
    calls = []
    visible = []
    key = "a" * 64

    def reserve(*_):
        try:
            with claim.open("x") as handle:
                handle.write(key)
        except FileExistsError:
            return False
        return True

    def dispatch(*args):
        calls.append(args)
        raise subprocess.CalledProcessError(1, "gh")

    def reconcile():
        return dispatch_verified("CONTABO_QUALITY_RECOVERY", REQUEST, CONTROLLER, key,
                                 list_runs=lambda _: visible, dispatch=dispatch, reserve=reserve, polls=1)

    with pytest.raises(RuntimeError, match="NOT_ACKNOWLEDGED"):
        reconcile()
    with pytest.raises(RuntimeError, match="NOT_ACKNOWLEDGED"):
        reconcile()
    visible.append({"id": 11, "display_title": f"TAYVORIQ lifecycle {key}",
                    "event": "workflow_dispatch", "head_branch": "main"})
    assert reconcile()["id"] == reconcile()["id"] == 11
    assert len(calls) == 1


def test_same_persisted_event_updates_one_existing_telegram_message():
    proof = contabo_decision(*stopped_request(), diagnostics=lambda _: diagnostics(stopped_request()[1]))
    event = build_event({"contabo_repair": proof})
    receipt = {key: event[key] for key in ("request_id", "controller_run_id", "source_context_sha256")}
    receipt.update(phase_key="terminal:FAILED", telegram_message_id=3860)
    edits = []

    def fetch(*_):
        return {"content": base64.b64encode(json.dumps(receipt).encode())}

    def send(request, **_):
        edits.append(json.loads(request.data))
        # Telegram already applied the edit before the process lost its local response.
        raise HTTPError(request.full_url, 400, "", {}, BytesIO(b'{"description":"Bad Request: message is not modified"}'))

    def save(_, data, __):
        receipt.update(data)

    assert notify(event, "control", "bot", "chat", fetch=fetch, save=save, open_response=send)
    assert notify(event, "control", "bot", "chat", fetch=fetch, save=save, open_response=send)
    assert len(edits) == 1
    assert event["text"] in edits[0]["text"]
    assert edits[0]["message_id"] == receipt["telegram_message_id"]
