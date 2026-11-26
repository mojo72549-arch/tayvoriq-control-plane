#!/usr/bin/env python3
"""Check the VPS runtime without generating speech, video or a message."""
import argparse
from contextlib import redirect_stdout
import json
import platform
import shutil
import subprocess
import sys
from urllib.request import ProxyHandler, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warm-models', action='store_true', help='Download and load the production voice model without synthesizing audio')
    args = parser.parse_args()
    checks = {name: bool(shutil.which(name)) for name in ('ffmpeg', 'ffprobe', 'git', 'rsync')}
    checks['x86_64'] = platform.machine() == 'x86_64'
    checks['free_disk_20_gib'] = shutil.disk_usage('/var/cache/tayvoriq').free >= 20 * 1024**3
    with build_opener(ProxyHandler({})).open('http://127.0.0.1:11434/api/tags', timeout=10) as response:
        installed = {row['name']: row['digest'] for row in json.load(response)['models']}
    for model in ('qwen3.5:9b', 'gemma4:12b'):
        checks[model] = model in installed
    import torch
    import chatterbox.mtl_tts
    import moviepy.editor
    import tayvoriq_cloud_render

    checks['cpu_torch_2_6'] = torch.__version__.split('+')[0] == '2.6.0' and not torch.cuda.is_available()
    checks['studio_local_llm'] = callable(getattr(tayvoriq_cloud_render, 'call_ollama', None))
    if args.warm_models:
        from tayvoriq_chatterbox_worker import load_multilingual_model
        with redirect_stdout(sys.stderr):
            _, resolved, _ = load_multilingual_model(
                chatterbox.mtl_tts.ChatterboxMultilingualTTS, device='cpu', requested_version='v3',
            )
        checks['chatterbox_v3'] = resolved == 'v3'
    checks['ffmpeg_h264'] = 'libx264' in subprocess.check_output(['ffmpeg', '-hide_banner', '-encoders'], text=True)
    report = {'checks': checks, 'models': installed, 'passed': all(checks.values()), 'video_created': False}
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:
        print(json.dumps({'passed': False, 'error': f'{type(exc).__name__}: {exc}', 'video_created': False}))
        code = 1
    raise SystemExit(code)
