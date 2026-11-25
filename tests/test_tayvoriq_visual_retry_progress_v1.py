from __future__ import annotations

import hashlib
import json

import pytest

from tools.tayvoriq_recovery_policy_v1 import classify_failure
from tools.tayvoriq_visual_retry_progress_v1 import record_visual_no_progress


REQUEST_ID = "telegram-3696-trend-1"
RUN_ID = 45510042088


def _write_checkpoint(root, attempt, *, query="original query", clip="a" * 64,
                      export="b" * 64, blocker=None, invalidate=False):
    (root / "control-plane").mkdir(parents=True)
    (root / "job").mkdir()
    manifest = {"run_id": str(RUN_ID), "run_attempt": str(attempt), "source_request_id": REQUEST_ID,
                "source_context_sha256": "c" * 64, "implementation_sha": "d" * 40,
                "quality_gates_weakened": False}
    hashes = {"short_youtube.mp4": export, "short_tiktok.mp4": "e" * 64}
    assets = [{"scene": 1, "requested_query": query, "query": query, "pexels_source_sha256": clip}]
    job = {"variants": {platform: {"render": {"asset_report": assets}} for platform in ("youtube_shorts", "tiktok")}}
    audit = {"passed": False, "quality_gates_weakened": False,
             "blockers": [blocker or f"score_below_threshold:visual:{45 if attempt == 1 else 20}<78",
                          "visual_agent:Irrelevant bird footage"],
             "visual_review": {"passed": False, "reviewed_frames": ["youtube_shorts-2.jpg"]}}
    for name, report in (("job.json", job), ("preapproval_ai_audit.json", audit)):
        raw = json.dumps(report).encode()
        (root / "job" / name).write_bytes(raw)
        hashes[name] = "f" * 64 if invalidate else hashlib.sha256(raw).hexdigest()
    (root / "control-plane/production-manifest.json").write_text(json.dumps(manifest))
    (root / "recovery-checkpoint-meta.json").write_text(json.dumps({**manifest, "files_sha256": hashes}))


@pytest.fixture
def local_failure():
    return {"state": "LOCAL_VISUAL_REPAIR_REQUIRED", "run_id": RUN_ID, "run_attempt": 2,
            "request_id": REQUEST_ID, "master_reusable": True, "quality_gates_weakened": False}


def test_unchanged_failed_exports_stop_before_the_next_attempt(tmp_path, local_failure):
    previous = tmp_path / "previous"
    current = tmp_path / "current"
    _write_checkpoint(previous, 1)
    _write_checkpoint(current, 2)
    evidence = record_visual_no_progress(local_failure, previous, current)
    assert len(evidence["visual_no_progress_sha256"]) == 64
    decision = classify_failure("", run_attempt=2, structured_evidence=evidence)
    assert decision.state == "LOCAL_VISUAL_RECOVERY_EXHAUSTED"
    assert decision.retry_allowed is False


@pytest.mark.parametrize("change", [{"query": "new query"}, {"clip": "1" * 64}, {"export": "2" * 64},
                                    {"blocker": "visual_agent:scene_off_topic:youtube_shorts:4"}, {"invalidate": True}])
def test_changed_or_unproven_evidence_keeps_the_bounded_retry(tmp_path, local_failure, change):
    previous = tmp_path / "previous"
    current = tmp_path / "current"
    _write_checkpoint(previous, 1)
    _write_checkpoint(current, 2, **change)
    evidence = record_visual_no_progress(local_failure, previous, current)
    assert evidence == local_failure
    assert classify_failure("", run_attempt=2, structured_evidence=evidence).retry_allowed is True
