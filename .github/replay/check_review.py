import hashlib
import json
import os
from pathlib import Path
import sys

from src.core.media_probe import probe_media

workspace = Path(os.environ["GITHUB_WORKSPACE"])
request = json.loads((workspace / "replay/binding.json").read_text())
source = json.loads((workspace / "replay/source.json").read_text())
digest = hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode()).hexdigest()
if digest != request["source_context_sha256"]:
    raise SystemExit("REPLAY_SOURCE_CHANGED")
job_dir = Path(sys.argv[1]).resolve()
job = json.loads((job_dir / "job.json").read_text())
if job.get("render_status") != "DONE":
    raise SystemExit("REPLAY_RENDER_INCOMPLETE")
review = Path("site/tayvoriq/runs") / request["run_id"]
if not (review / "index.html").is_file():
    raise SystemExit("REPLAY_REVIEW_PAGE_MISSING")
for platform, name in (("youtube_shorts", "short_youtube.mp4"), ("tiktok", "short_tiktok.mp4")):
    master = (job_dir / (job["variants"][platform].get("video_path") or name)).resolve()
    if not master.is_relative_to(job_dir) or master.suffix.lower() != ".mp4":
        raise SystemExit(f"REPLAY_MASTER_PATH_INVALID:{platform}")
    media = probe_media(master)
    video = media["video"]
    if (not video.get("present") or not media["audio"]["present"] or
            "mp4" not in media["format_name"].split(",") or
            not 0 < media["duration_seconds"] < float("inf") or
            video["effective_width"] * 16 != video["effective_height"] * 9):
        raise SystemExit(f"REPLAY_MASTER_INVALID:{platform}")
    with master.open("rb") as f, (review / name).open("rb") as reviewed:
        if hashlib.file_digest(f, "sha256").digest() != hashlib.file_digest(reviewed, "sha256").digest():
            raise SystemExit(f"REPLAY_REVIEW_MASTER_MISMATCH:{platform}")
print("REPLAY_MASTER_AND_REVIEW_PAGE_VERIFIED")
