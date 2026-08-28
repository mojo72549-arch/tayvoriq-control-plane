import glob
import os
import shutil
import subprocess
from pathlib import Path

PROMPT = (
    "A single continuous photorealistic cinematic shot at night on a rain-soaked rooftop in a modern European city. "
    "A 30-year-old man with short dark wet hair, light stubble, black waterproof jacket, dark trousers and dark shoes "
    "walks toward camera through heavy wind-driven rain, his jacket and hair physically moving. He suddenly looks up. "
    "A violent white-blue lightning bolt strikes the wet rooftop several meters beside him, throwing bright sparks and rain spray. "
    "The man visibly flinches with his whole body, jerks his shoulders and arms, loses his balance and stumbles backward trying to stay upright. "
    "Real human body motion and realistic physics, natural facial reaction, handheld cinema camera follows him, dramatic reflected city lights, "
    "no cuts, no montage, no still image, no freeze frame, no text, no subtitles, no logo, no gore."
)

root = Path('/kaggle/working')
repo = root / 'SkyReels-V2'
out = root / 'tayvoriq_output'
out.mkdir(parents=True, exist_ok=True)

print('TAYVORIQ_KAGGLE_GPU_START')
subprocess.run(['nvidia-smi'], check=False)

if not repo.exists():
    subprocess.run([
        'git', 'clone', '--depth', '1',
        'https://huggingface.co/spaces/fffiloni/SkyReels-V2',
        str(repo)
    ], check=True)

subprocess.run([
    'python', '-m', 'pip', 'install', '-q', '-r', str(repo / 'requirements.txt')
], check=True)

cmd = [
    'python', 'generate_video_df.py',
    '--outdir', 'tayvoriq_blitz',
    '--model_id', 'Skywork/SkyReels-V2-DF-1.3B-540P',
    '--resolution', '540P',
    '--num_frames', '97',
    '--base_num_frames', '97',
    '--guidance_scale', '6.0',
    '--shift', '8.0',
    '--inference_steps', '24',
    '--offload',
    '--fps', '24',
    '--seed', '614273',
    '--teacache',
    '--teacache_thresh', '0.2',
    '--use_ret_steps',
    '--prompt', PROMPT,
]
subprocess.run(cmd, cwd=repo, check=True)

candidates = sorted(
    glob.glob(str(repo / 'result' / 'tayvoriq_blitz' / '*.mp4')),
    key=os.path.getmtime,
    reverse=True,
)
if not candidates:
    raise RuntimeError('KAGGLE_SKYREELS_OUTPUT_NOT_FOUND')

final = out / 'TAYVORIQ_Blitz_SkyReels_Kaggle_Raw.mp4'
shutil.copy2(candidates[0], final)
if final.stat().st_size < 100_000:
    raise RuntimeError('KAGGLE_SKYREELS_OUTPUT_TOO_SMALL')
print('TAYVORIQ_KAGGLE_GPU_SUCCESS', final, final.stat().st_size)
