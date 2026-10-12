from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import shutil
from pathlib import Path


def run_failure_handoff(tmp_path, report_data, console=''):
    workflow = Path(".github/workflows/tayvoriq-deliver-video-now.yml").read_text(
        encoding="utf-8"
    )
    section = workflow.split("- name: Record internal failure for Delivery Watch", 1)[1]
    match = re.search(r"python -S - <<'PY'\n(.*?)\n          PY", section, re.S)
    assert match, "Failure handoff Python block missing"
    script = "\n".join(
        line.removeprefix("          ") for line in match.group(1).splitlines()
    )
    # Reproduce the real checkout: implementation/tools is on PYTHONPATH and
    # owns a regular 'tools' package. The CP helper must use its explicit path.
    (tmp_path / 'tools').mkdir()
    for name in ('tayvoriq_current_failure_contract_v1.py', 'tayvoriq_recovery_policy_v1.py'):
        shutil.copy2(Path('tools') / name, tmp_path / 'tools' / name)
    shadow = tmp_path / 'implementation/tools'
    shadow.mkdir(parents=True)
    (shadow / '__init__.py').write_text('')

    report = tmp_path / "implementation/out/tayvoriq-self-heal/report.json"
    report.parent.mkdir(parents=True)
    # The workflow creates this directory immediately before the extracted Python.
    (tmp_path / "implementation/out/control-plane").mkdir(parents=True)
    report.write_text(json.dumps(report_data), encoding="utf-8")
    (report.parent / 'controller-console.log').write_text(console, encoding='utf-8')
    env = {
        **os.environ,
        "PYTHONPATH": str(tmp_path / 'implementation'),
        "GITHUB_RUN_ID": "42",
        "GITHUB_RUN_ATTEMPT": "3",
        "SOURCE_REQUEST_ID_PIN": "telegram-42-trend-1",
        "PRODUCTION_OUTCOME": "failure",
        "RECOVERY_STATE": "PUBLISHABLE_OUTPUT_RETRY_REQUIRED",
        "CONTROLLER_STATE": "PUBLISHABLE_OUTPUT_RETRY_REQUIRED",
        "REUSABLE_MASTER": "true",
    }
    result = subprocess.run(
        [sys.executable, "-S", "-c", script], cwd=tmp_path, env=env,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    policy = json.loads(
        (tmp_path / "implementation/out/control-plane/failure-notification-policy.json")
        .read_text(encoding="utf-8")
    )
    assert policy['run_id'] == 42
    assert policy['run_attempt'] == 3
    assert policy['request_id'] == 'telegram-42-trend-1'
    assert policy['quality_gates_weakened'] is False
    return policy


def test_failure_handoff_prefers_failed_recovery_over_stale_preflight(tmp_path):
    policy = run_failure_handoff(tmp_path, {"state": "PREFLIGHT_PASSED"})
    assert policy["state"] == "PUBLISHABLE_OUTPUT_RETRY_REQUIRED"
    assert policy["failure_class"] == "PUBLISHABLE_CHECKPOINT"
    assert policy["master_reusable"] is True
    assert policy["full_regeneration_allowed"] is False


def test_current_editorial_failure_overrides_earlier_visual_checkpoint(tmp_path):
    policy = run_failure_handoff(tmp_path, {
        'state': 'PUBLISHABLE_OUTPUT_RETRY_REQUIRED', 'repair_target_stages': ['VISUALS']
    }, 'RuntimeError: CONTENT_REJECTED:verified-editorial-postcondition-drift:fields=action_now:body_words=46')
    assert policy['state'] == 'EDITORIAL_VALIDATOR_CODEFIX_REQUIRED'
    assert policy['failure_class'] == 'DETERMINISTIC_CODE'
    assert policy['repair_target_stages'] == []
    assert policy['master_reusable'] is False


def test_native_final_length_failure_is_written_in_real_checkout_environment(tmp_path):
    policy = run_failure_handoff(tmp_path, {'state': 'PREFLIGHT_PASSED'},
        'RuntimeError: TAYVORIQ V20 Quality-Gate blockiert das Video: script_too_short:47:min=51')
    assert policy['state'] == 'EDITORIAL_VALIDATOR_CODEFIX_REQUIRED'
    assert policy['failure_class'] == 'DETERMINISTIC_CODE'
    assert policy['master_reusable'] is False


def test_pre_render_voice_proof_is_archived_without_a_completed_master(tmp_path):
    workflow = Path('.github/workflows/tayvoriq-deliver-video-now.yml').read_text()
    section = workflow.split('- name: Build lean diagnostics bundle', 1)[1]
    match = re.search(r"python - <<'PY'\n(.*?)\n          PY", section, re.S)
    assert match
    program = '\n'.join(line.removeprefix('          ') for line in match.group(1).splitlines())
    voice = tmp_path/'out/tayvoriq-youtube-tiktok/current/youtube_shorts'
    voice.mkdir(parents=True)
    (voice/'voice.mp3').write_bytes(b'failed-audio'*200)
    (tmp_path/'outside.mp3').write_bytes(b'outside-audio')
    for voice_path in ('voice.mp3', '../../../../outside.mp3'):
        (voice/'pre-render-voice-diagnostics.json').write_text(json.dumps({
            'quality_gates_weakened': False, 'attempts': [{'voice_path': voice_path}]}))
        shutil.rmtree(tmp_path/'out/diagnostics-bundle', ignore_errors=True)
        result = subprocess.run([sys.executable, '-S', '-c', program], cwd=tmp_path,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        archive = tmp_path/'out/diagnostics-bundle/pre-render-voice/current/youtube_shorts'
        assert (archive/'pre-render-voice-diagnostics.json').is_file()
        assert (archive/'voice.mp3').is_file() is (voice_path == 'voice.mp3')
        assert not list((tmp_path/'out/diagnostics-bundle').rglob('outside.mp3'))

