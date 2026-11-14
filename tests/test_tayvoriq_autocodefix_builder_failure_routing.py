import os
from pathlib import Path
import subprocess
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tayvoriq-autonomous-codefix-builder.yml"


def test_editorial_length_failures_take_priority_over_speech_noise():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "r'script_too_short'" in text
    assert "r'verified-editorial-postcondition-drift'" in text
    assert "editorial_length_failure=any(" in text
    assert "action='repair_bounded_v20_length_contract_then_resume_approved_request'" in text
    assert "'runtime_patches/tayvoriq_german_hyphen_guard.py'" in text
    assert "'runtime_patches/tayvoriq_v20_final_length_guard.py'" in text

    editorial_branch = text.index("elif editorial_length_failure:")
    number_branch = text.index("elif number_failure:")
    pronunciation_branch = text.index("elif pronunciation_failure:")
    assert editorial_branch < number_branch < pronunciation_branch


def test_number_and_pronunciation_routing_use_failure_focus_not_full_log():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "failure_focus=(quality_evidence + '\\n' + failed_log).casefold()" in text
    assert "'48.000'" not in text[text.index("number_failure=any("):text.index("if source_hash_failure:")]
    assert "'number-pronunciation-not-confirmed'" in text
    assert "'critical_pronunciation_missing'" in text


def test_meta_narration_failure_cannot_reach_unrelated_patch_generation(tmp_path):
    text = WORKFLOW.read_text(encoding="utf-8")
    step = text.split('- name: Build guarded repair request', 1)[1]
    source = textwrap.dedent(step.split("<<'PY'\n", 1)[1].split('\n          PY', 1)[0])
    source = source.replace('/tmp/tayvoriq-codefix-', str(tmp_path / 'codefix-'))
    (tmp_path / 'codefix-failed.log').write_text('Production is not publishable\n')
    (tmp_path / 'codefix-full.log').write_text(
        '2026-11-11T08:08:43.0639589Z RuntimeError: '
        'CONTENT_REJECTED:GOLDEN_QUALITY_REGRESSION:golden-floor-meta-narration\n')
    result = subprocess.run(['python', '-c', source], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'CODE_DEFECT_EDITORIAL_META_NARRATION_REQUIRES_REVIEWED_PR' in result.stderr
    assert not (tmp_path / 'codefix-request.json').exists()


@pytest.mark.parametrize(("dispatched", "run_id", "accepted"), [
    ("false", "", False),
    ("", "", False),
    ("true", "0", False),
    ("false", "42", False),
    ("true", "42", True),
])
def test_codefix_requires_request_bound_replay(dispatched, run_id, accepted):
    text = WORKFLOW.read_text(encoding="utf-8")
    replay, result_gate = text.split("- name: Assert exact replay binding exists", 1)
    mismatch = replay.split('if [ "$green_sha" != "$HANDOFF_BASE_SHA" ]; then', 1)[1]
    assert "exit 1" in mismatch.split("\n          fi", 1)[0]
    command = result_gate.split("run: |\n", 1)[1].split("\n      - name:", 1)[0]
    result = subprocess.run(["bash", "-c", textwrap.dedent(command)], capture_output=True,
                            env={**os.environ, "REPLAY_DISPATCHED": dispatched, "REPLAY_RUN_ID": run_id})
    assert (result.returncode == 0) is accepted
