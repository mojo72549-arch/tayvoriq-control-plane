#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, *, cwd=None):
    print('+', ' '.join(map(str, cmd)), flush=True)
    subprocess.run([str(x) for x in cmd], cwd=cwd, check=True)


def probe(path: Path):
    raw = subprocess.check_output([
        'ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','stream=width,height,r_frame_rate:format=duration,size',
        '-of','json',str(path)
    ], text=True)
    return json.loads(raw)


def quality_gate(path: Path, min_seconds: float = 4.0):
    if not path.exists() or path.stat().st_size < 200_000:
        raise RuntimeError(f'VIDEO_GATE_FILE_INVALID: {path}')
    info = probe(path)
    streams = info.get('streams') or []
    if not streams:
        raise RuntimeError(f'VIDEO_GATE_NO_STREAM: {path}')
    s = streams[0]
    width, height = int(s.get('width', 0)), int(s.get('height', 0))
    duration = float((info.get('format') or {}).get('duration') or 0)
    if height <= width:
        raise RuntimeError(f'VIDEO_GATE_NOT_VERTICAL: {width}x{height}')
    if duration < min_seconds:
        raise RuntimeError(f'VIDEO_GATE_TOO_SHORT: {duration:.2f}s')
    return {'width': width, 'height': height, 'duration': duration, 'bytes': path.stat().st_size}


def find_skyreels(root: Path):
    candidates = [
        root / 'generate_video.py',
        Path(os.environ.get('SKYREELS_V3_ROOT','')) / 'generate_video.py' if os.environ.get('SKYREELS_V3_ROOT') else None,
    ]
    for c in candidates:
        if c and c.exists():
            return c.parent
    return None


def skyreels_call(repo: Path, args):
    py = os.environ.get('SKYREELS_PYTHON', sys.executable)
    run([py, 'generate_video.py', *args], cwd=repo)


def newest_mp4(folder: Path, before=None):
    items = [p for p in folder.rglob('*.mp4') if p.is_file()]
    if before:
        items = [p for p in items if p.stat().st_mtime >= before]
    if not items:
        raise RuntimeError(f'No mp4 generated under {folder}')
    return max(items, key=lambda p: p.stat().st_mtime)


def generate_seed(repo: Path, reference: Path, prompt: str, out: Path):
    import time
    start = time.time() - 1
    skyreels_call(repo, [
        '--task_type','reference_to_video',
        '--ref_imgs',str(reference.resolve()),
        '--prompt',prompt,
        '--duration','5',
        '--resolution','720P',
        '--offload','--low_vram'
    ])
    src = newest_mp4(repo, before=start)
    shutil.copy2(src, out)
    return quality_gate(out)


def extend(repo: Path, source: Path, prompt: str, seconds: int, out: Path, shot_switch=False):
    import time
    start = time.time() - 1
    task = 'shot_switching_extension' if shot_switch else 'single_shot_extension'
    args = [
        '--task_type',task,
        '--input_video',str(source.resolve()),
        '--prompt',prompt,
        '--resolution','720P',
        '--offload','--low_vram'
    ]
    if not shot_switch:
        args += ['--duration',str(seconds)]
    skyreels_call(repo, args)
    src = newest_mp4(repo, before=start)
    shutil.copy2(src, out)
    return quality_gate(out)


def main():
    ap = argparse.ArgumentParser(description='TAYVORIQ SkyReels V3 coherent-film controller')
    ap.add_argument('--skyreels-root', default='vendor/SkyReels-V3')
    ap.add_argument('--reference', required=True)
    ap.add_argument('--outdir', default='lab/output/skyreels_v3')
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    reference = Path(args.reference)
    if not reference.exists():
        raise SystemExit(f'Missing reference image: {reference}')

    repo = find_skyreels(Path(args.skyreels_root))
    if not repo:
        raise SystemExit('SKYREELS_V3_NOT_INSTALLED: clone SkyworkAI/SkyReels-V3 and set --skyreels-root or SKYREELS_V3_ROOT')

    # One story, not independent B-roll. Each next generation receives the complete previous movie.
    story = [
        {
            'kind':'seed',
            'prompt':('Cinematic photorealistic vertical film at night on the same rain-soaked rooftop in a modern European city. '
                      'The referenced 30-year-old man wears a black waterproof rain jacket and dark trousers. Heavy rain and wind move his hair and jacket. '
                      'He walks slowly across the rooftop, looks up at the storm clouds, visibly uneasy. Natural body motion, realistic city lights, documentary cinema, no text, no logo.')
        },
        {
            'kind':'extend','seconds':8,
            'prompt':('Continue the exact same movie and same man without resetting the scene. A violent lightning bolt hits the wet rooftop several meters beside him. '
                      'The white-blue flash illuminates the same skyline. He flinches hard, loses balance, stumbles backward with both arms trying to recover, then falls onto the wet concrete. '
                      'Camera follows naturally; realistic physics, rain splashes, no gore, no cut to unrelated footage.')
        },
        {
            'kind':'extend','seconds':8,
            'prompt':('Continue immediately from the same fallen man on the same rooftop. A second adult man in a dark hooded rain jacket runs out of the rooftop access door, crosses the roof, kneels beside him, '
                      'speaks to him, checks response, takes out a smartphone and calls emergency services on speaker while checking breathing. Same weather, same lighting, same identities, natural hands and movement.')
        },
        {
            'kind':'extend','seconds':8,
            'prompt':('Continue the same uninterrupted incident. Blue emergency-light reflections spread across the wet rooftop. Two realistic European paramedics run through the access door with a medical bag, '
                      'kneel beside the same victim, take over the assessment, while the helper moves aside. Camera slowly pulls back, preserving the same skyline, rain and cinematic look. No text or logos.')
        },
    ]

    manifest = {'engine':'SkyReels-V3','mode':'coherent-video-extension','reference':str(reference),'segments':[]}
    current = outdir / '00_seed.mp4'
    q = generate_seed(repo, reference, story[0]['prompt'], current)
    manifest['segments'].append({'file':str(current),'gate':q,'kind':'reference_to_video'})

    for i, item in enumerate(story[1:], 1):
        target = outdir / f'{i:02d}_extended.mp4'
        q = extend(repo, current, item['prompt'], item['seconds'], target)
        current = target
        manifest['segments'].append({'file':str(target),'gate':q,'kind':'single_shot_extension'})

    final = outdir / 'TAYVORIQ_Blitz_SkyReelsV3_Master_Silent.mp4'
    shutil.copy2(current, final)
    quality_gate(final, min_seconds=20)
    manifest['final'] = str(final)
    (outdir/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'FINAL={final}')


if __name__ == '__main__':
    main()
