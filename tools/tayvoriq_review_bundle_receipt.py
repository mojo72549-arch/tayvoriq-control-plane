"""Bind the reviewed platform files to the media that passed final QA."""
import argparse
import hashlib
import json
from pathlib import Path

from tayvoriq_artifact_approval import FILES

PLATFORMS = {"youtube_shorts": "short_youtube.mp4", "tiktok": "short_tiktok.mp4"}


def digest(path):
    if path.is_symlink() or not path.is_file() or not path.stat().st_size:
        raise ValueError("REVIEW_FILE_MISSING:" + path.name)
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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
        source = job_dir / (job["variants"][platform].get("video_path") or filename)
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
