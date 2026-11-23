"""Change the rejected media on both variants before their normal strict audit."""
import os
import subprocess
from pathlib import Path

import tayvoriq_resume_existing_render as resume
from tayvoriq_resume_existing_render_v2 import repair_visuals_v2, repair_voice_v2


def media_hashes(job_dir, job, stream):
    hashes = {}
    for platform in ("youtube_shorts", "tiktok"):
        variant = job["variants"][platform]
        default = "short_youtube.mp4" if platform == "youtube_shorts" else "short_tiktok.mp4"
        path = (job_dir / (variant.get("video_path") or default)).resolve(strict=True)
        if not path.is_relative_to(job_dir.resolve()):
            raise ValueError("Video variant is outside the verified checkpoint")
        hashes[platform] = subprocess.check_output(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", f"0:{stream}:0",
             "-f", "hash", "-hash", "sha256", "-"], text=True, timeout=90).strip()
    return hashes


def main():
    stage = os.environ["REVIEW_REPAIR_STAGE"]
    stream = {"VOICE": "a", "VISUALS": "v"}[stage]
    candidates = resume.rendered_candidates(Path("out/tayvoriq-youtube-tiktok"))
    if len(candidates) != 1:
        raise ValueError("A correction needs exactly one verified review master")
    job_dir, job = candidates[0]
    previous = media_hashes(job_dir, job, stream)
    if stage == "VOICE":
        repair_voice_v2(job_dir)
    else:
        result = repair_visuals_v2(job_dir, repair_round=2)
        if result.get("script_changed"):
            repair_voice_v2(job_dir)
    renewed = resume._load(job_dir / "job.json")
    current = media_hashes(job_dir, renewed, stream)
    if any(previous[platform] == current[platform] for platform in previous):
        raise ValueError("The correction left the rejected media unchanged")
    (job_dir / "preapproval_ai_audit.json").unlink(missing_ok=True)
    (job_dir / "publication_quality_gate.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
