"""Bind the reviewed platform files to the media that passed final QA."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from tayvoriq_artifact_approval import FILES

PLATFORMS = {"youtube_shorts": "short_youtube.mp4", "tiktok": "short_tiktok.mp4"}


def digest(path):
    if path.is_symlink() or not path.is_file() or not path.stat().st_size:
        raise ValueError("REVIEW_FILE_MISSING:" + path.name)
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_scene_coverage(variant, platform):
    planned = (variant.get("text_package") or {}).get("scenes")
    render = variant.get("render") or {}
    actual = render.get("asset_report")
    if (not isinstance(planned, list) or not planned or not isinstance(actual, list)
            or len(planned) != len(actual)):
        raise ValueError("REVIEW_SCENE_COUNT_INVALID:" + platform)
    elapsed = 0.0
    for number, (plan, scene) in enumerate(zip(planned, actual), start=1):
        if (not isinstance(plan, dict) or not isinstance(scene, dict)
                or type(scene.get("scene")) is not int or scene["scene"] != number):
            raise ValueError(f"REVIEW_SCENE_SEQUENCE_INVALID:{platform}:{number}")
        duration = scene.get("duration")
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"REVIEW_SCENE_DURATION_INVALID:{platform}:{number}")
        if str(plan.get("spoken_chunk") or "").strip() and scene.get("subtitle_present") is not True:
            raise ValueError(f"REVIEW_SCENE_CAPTION_MISSING:{platform}:{number}")
        elapsed += duration
    final = render.get("final_duration_seconds")
    if type(final) not in (float, int) or not math.isfinite(final) or abs(elapsed - final) > 0.35:
        raise ValueError("REVIEW_SCENE_TIMELINE_INCOMPLETE:" + platform)


def verify(job_dir, bundle, run_id):
    job = json.loads((job_dir / "job.json").read_text())
    review_job = json.loads((bundle / "job.json").read_text())
    gate = json.loads((job_dir / "publication_quality_gate.json").read_text())
    if (any(str(record.get("github_run_id")) != run_id for record in (job, review_job))
            or not job.get("job_id") or job["job_id"] != review_job.get("job_id")
            or gate.get("job_id") != job["job_id"] or gate.get("passed") is not True
            or gate.get("quality_gates_weakened") is not False
            or set(gate.get("targets") or []) != set(PLATFORMS)):
        raise ValueError("REVIEW_BUNDLE_JOB_OR_GATE_INVALID")
    hashes = {name: digest(bundle / name) for name in sorted(FILES)}
    for platform, filename in PLATFORMS.items():
        variant = job["variants"][platform]
        verify_scene_coverage(variant, platform)
        source = job_dir / (variant.get("video_path") or filename)
        if (not source.resolve().is_relative_to(job_dir.resolve())
                or hashes[filename] != digest(source)):
            raise ValueError("REVIEW_MASTER_DIFFERS_FROM_QA:" + platform)
    if hashes["publication_quality_gate.json"] != digest(job_dir / "publication_quality_gate.json"):
        raise ValueError("REVIEW_GATE_DIFFERS_FROM_FINAL_QA")
    return hashes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--implementation", type=Path, required=True)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    state = json.loads((args.implementation / "out/tayvoriq-review-state.json").read_text())
    if not state.get("job_dir"):
        raise ValueError("REVIEW_JOB_MISSING")
    hashes = verify(args.implementation / state["job_dir"], args.bundle, args.run)
    args.out.write_text(json.dumps(hashes, sort_keys=True))


if __name__ == "__main__":
    main()
