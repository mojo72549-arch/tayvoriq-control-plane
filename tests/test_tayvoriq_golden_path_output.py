import json
import os
from pathlib import Path
import subprocess
import textwrap

import pytest


WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/tayvoriq-deliver-video-now.yml'


def run_step(name, directory, **variables):
    section = WORKFLOW.read_text(encoding='utf-8').split(f'- name: {name}', 1)[1]
    command = section.split('run: |\n', 1)[1].split('\n      - name:', 1)[0]
    return subprocess.run(['bash', '-c', textwrap.dedent(command)], cwd=directory,
                          env={**os.environ, **variables}, capture_output=True, text=True)


@pytest.mark.parametrize(('result', 'accepted'), [('0', False), ('-1', False), ('"42"', False), ('42', True)])
def test_telegram_review_records_only_confirmed_numeric_message_id(tmp_path, result, accepted):
    (tmp_path / 'tayvoriq_send_telegram.py').write_text(
        f'def send_status(**kwargs):\n    assert kwargs["state"] == "SUCCESS"\n    return {result}\n', encoding='utf-8')
    output = tmp_path / 'step-output'
    response = run_step('Send Telegram review', tmp_path, GITHUB_RUN_ID='100', GITHUB_OUTPUT=str(output))
    assert (response.returncode == 0) is accepted, response.stderr
    assert (output.read_text(encoding='utf-8') if output.exists() else '') == ('message_id=42\n' if accepted else '')


@pytest.mark.parametrize(('master', 'accepted'), [('missing', False), ('corrupt', False),
                                                ('landscape', False), ('no-audio', False), ('vertical', True)])
def test_publishability_requires_both_valid_vertical_masters(tmp_path, master, accepted):
    implementation = tmp_path / 'implementation'
    job = implementation / 'out/tayvoriq-youtube-tiktok/job'
    job.mkdir(parents=True)
    (job.parent.parent / 'tayvoriq-review-state.json').write_text(json.dumps({'job_dir': str(job)}))
    (job / 'job.json').write_text(json.dumps({'render_status': 'DONE', 'variants': {'youtube_shorts': {}, 'tiktok': {}}}))
    media = {'format_name': 'mov,mp4', 'duration_seconds': 35,
             'audio': {'present': master != 'no-audio'},
             'video': {'effective_width': 1920 if master == 'landscape' else 1080, 'effective_height': 1920}}
    module = implementation / 'src/core/media_probe.py'
    module.parent.mkdir(parents=True)
    module.write_text(f'''class MediaProbeError(RuntimeError):
    code = 'ffprobe_failed'

def probe_media(path):
    if path.read_bytes() == b'corrupt':
        raise MediaProbeError()
    return {media!r}
''', encoding='utf-8')
    (job / 'short_youtube.mp4').write_bytes(b'video')
    if master != 'missing':
        (job / 'short_tiktok.mp4').write_bytes(b'corrupt' if master == 'corrupt' else b'video')
    response = run_step('Assert publishable production output', tmp_path, PREFLIGHT_OUTCOME='success',
                        REPLAY_READINESS_OUTCOME='success', CONTROLLER_STATE='SUCCESS', CONTROLLER_EXIT='0',
                        RECOVERY_STATE='', RECOVERY_EXIT='')
    assert (response.returncode == 0) is accepted, response.stderr
