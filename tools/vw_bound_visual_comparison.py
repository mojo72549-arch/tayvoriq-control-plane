"""Render one immutable Studio revision with a shared Pexels recording."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import requests


REQUEST = "telegram-3696-trend-1"
SOURCE_HASH = "91d55e03500a804d6a08f56215d5ee3e3ad2c3606c648e0f8d18cf74c6367cd2"
COMMITS = {
    "old": "5f9baa36075467dbea868a3066870645e2e4835a",
    "fixed": "e4452fcf2784ae83c310117e330e1c1f9b645fa6",
}
PLATFORMS = {"youtube_shorts": "short_youtube.mp4", "tiktok": "short_tiktok.mp4"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_bytes())


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class MediaTape:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.index = directory / "recordings.json"
        self.entries = read_json(self.index) if self.index.exists() else {}
        self.used = {}
        self.live_gets = 0
        self.fetch = requests.sessions.Session.request

    def request(self, session, method, url, **options):
        url = requests.Request(method, url, params=options.get("params")).prepare().url
        parsed = urlsplit(url)
        if (method.upper() != "GET" or parsed.scheme != "https"
                or parsed.hostname not in {"api.pexels.com", "videos.pexels.com", "images.pexels.com", "www.pexels.com"}):
            raise RuntimeError("Only Pexels GET requests are allowed in this render comparison")

        key = hashlib.sha256(url.encode()).hexdigest()
        body_path = self.directory / (key + ".body")
        item = self.entries.get(key)
        if item is None:
            if self.live_gets >= 90:
                raise RuntimeError("Pexels recording exceeded its request budget")
            self.live_gets += 1
            with self.fetch(session, "GET", url, headers=options.get("headers"), timeout=(20, 60)) as live:
                body = live.content
                item = {"url": url, "response_url": live.url, "status": live.status_code,
                        "content_type": live.headers.get("Content-Type", ""),
                        "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
            body_path.write_bytes(body)
            self.entries[key] = item
            write_json(self.index, self.entries)
        else:
            body = body_path.read_bytes()
            if hashlib.sha256(body).hexdigest() != item["sha256"]:
                raise RuntimeError("Pexels recording hash mismatch")
        self.used[key] = item["sha256"]
        response = requests.Response()
        response.status_code = item["status"]
        response.url = item["response_url"]
        response.headers["Content-Type"] = item["content_type"]
        response._content = body
        response._content_consumed = True
        return response


def run(phase: str, checkpoint: Path, output: Path) -> None:
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if revision != COMMITS[phase]:
        raise RuntimeError("Studio checkout differs from the selected SHA")
    meta = read_json(checkpoint / "meta.json")
    if (int(meta["run_id"]), int(meta["run_attempt"]), meta["source_request_id"],
            meta["source_context_sha256"], meta["implementation_sha"], meta["quality_gates_weakened"]) != (
                45510042088, 1, REQUEST, SOURCE_HASH, COMMITS["old"], False):
        raise RuntimeError("Recovery checkpoint identity mismatch")
    source = checkpoint / "job"
    hashes = meta["files_sha256"]
    for name, expected in hashes.items():
        if digest(source / name) != expected:
            raise RuntimeError(f"Recovery checkpoint file changed: {name}")

    job_dir = output / phase
    shutil.copytree(source, job_dir)
    original = read_json(job_dir / "job.json")
    tape = MediaTape(output / "pexels")
    try:
        requests.sessions.Session.request = lambda session, method, url, **options: tape.request(session, method, url, **options)
        import tayvoriq_visual_only_repair_v1 as visual
        repairs = visual.repair(job_dir)
    finally:
        requests.sessions.Session.request = tape.fetch

    actual = read_json(job_dir / "job.json")
    if digest(job_dir / "source_context.resume.json") != hashes["source_context.resume.json"]:
        raise RuntimeError("The source-context file changed during visual repair")
    proof = {"source_request_id": REQUEST, "source_context_sha256": SOURCE_HASH,
             "input_job_sha256": hashes["job.json"], "implementation_sha": revision,
             "profile": repairs["profile"], "pexels_records": tape.used, "platforms": {}}
    for platform, export in PLATFORMS.items():
        before = original["variants"][platform]["text_package"]
        variant = actual["variants"][platform]
        after = variant["text_package"]
        if any(before[k] != after[k] for k in ("script", "source_context")):
            raise RuntimeError(f"Script or bound sources changed: {platform}")
        voice = f"{platform}/voice.mp3"
        if digest(job_dir / voice) != hashes[voice]:
            raise RuntimeError(f"Narrator track changed: {platform}")
        scenes = variant["render"]["asset_report"]
        elapsed = 0.0
        for row, text in zip(scenes, after["scenes"], strict=True):
            selected = tape.entries.get(row["pexels_source_sha256"])
            if selected is None or selected["status"] != 200 or not selected["bytes"]:
                raise RuntimeError("Selected Pexels clip is missing from the recording")
            row.update(start_seconds=round(elapsed, 3), clip_file_sha256=selected["sha256"],
                       spoken_chunk=text["spoken_chunk"])
            elapsed += row["duration"]
        proof["platforms"][platform] = {"mp4_sha256": digest(job_dir / export),
                                        "voice_sha256": hashes[voice], "scenes": scenes}
    write_json(job_dir / "comparison.json", proof)
    print(json.dumps({"phase": phase, "profile": proof["profile"],
                      "recorded_Pexels_GETs": tape.live_gets, "requested_media": len(tape.used)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=COMMITS)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.phase, args.checkpoint.resolve(), args.output.resolve())
