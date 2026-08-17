from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


WIDTH = 1080
HEIGHT = 1920
FPS = 30

SCENES = (
    {
        "spoken_youtube": "An Bruchzonen sitzen Gesteinsblöcke lange fest und rutschen dann plötzlich gegeneinander.",
        "spoken_tiktok": "An Bruchzonen sitzen Gesteinsblöcke lange fest und rutschen dann plötzlich gegeneinander.",
        "queries": (
            "geologist fault line rock outcrop documentary",
            "geologist mountain rocks field work",
            "rock fault mountain geology",
        ),
    },
    {
        "spoken_youtube": "Die Erdplatten drücken weiter.",
        "spoken_tiktok": "Die Erdplatten drücken weiter.",
        "queries": (
            "mountain rock layers aerial geology documentary",
            "rock strata mountain cliff aerial",
            "geological rock layers landscape",
        ),
    },
    {
        "spoken_youtube": "Spannung baut sich auf, bis der Widerstand plötzlich nachgibt.",
        "spoken_tiktok": "Spannung baut sich auf, bis der Widerstand plötzlich nachgibt.",
        "queries": (
            "earthquake cracked road damaged city real footage",
            "cracked road damaged building disaster",
            "earthquake damage street documentary",
        ),
    },
    {
        "spoken_youtube": "Besonders gefährdet sind Menschen in Regionen mit aktiven Bruchzonen.",
        "spoken_tiktok": "Besonders gefährdet sind Menschen in Regionen mit aktiven Bruchzonen.",
        "queries": (
            "earthquake emergency response people city documentary",
            "emergency response rescue city disaster",
            "people emergency evacuation city",
        ),
    },
    {
        "spoken_youtube": "Für dich: Stärke und Schaden hängen auch von Tiefe, Untergrund und Bauweise ab.",
        "spoken_tiktok": "Für dich: Stärke und Schaden hängen auch von Tiefe, Untergrund und Bauweise ab.",
        "queries": (
            "structural engineer building inspection construction documentary",
            "civil engineer inspecting building structure",
            "building engineering safety inspection",
        ),
    },
    {
        "spoken_youtube": "Nutze Warnungen und Vorsorgehinweise offizieller Erdbebendienste statt Vorhersagegerüchten.",
        "spoken_tiktok": "Nutze Warnungen und Vorsorgehinweise offizieller Erdbebendienste statt Vorhersagegerüchten.",
        "queries": (
            "smartphone emergency alert safety preparedness close up",
            "emergency notification smartphone close up",
            "emergency preparedness phone alert",
        ),
    },
    {
        "spoken_youtube": "Abonniere TAYVORIQ für verifizierte Einordnung und konkrete Schritte.",
        "spoken_tiktok": "Folge TAYVORIQ für verifizierte Einordnung und konkrete Schritte.",
        "queries": (
            "ocean waves aerial cinematic dramatic documentary",
            "underwater ocean surface light cinematic",
            "ocean coastline aerial waves documentary",
        ),
    },
)


def _run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            "COMMAND_FAILED: " + " ".join(command[:8]) + "\n" + str(completed.stdout or "")[-4000:]
        )
    return completed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ffprobe(path: Path) -> dict[str, Any]:
    completed = _run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ]
    )
    return json.loads(completed.stdout or "{}")


def _duration(path: Path) -> float:
    data = _ffprobe(path)
    try:
        return float((data.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _silence_candidates(path: Path) -> list[float]:
    completed = _run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
            "-af", "silencedetect=noise=-34dB:d=0.14", "-f", "null", "-",
        ],
        check=False,
    )
    values: list[float] = []
    for match in re.finditer(r"silence_end:\s*([0-9.]+)", completed.stdout or ""):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if value > 0.35:
            values.append(value)
    return sorted(set(round(item, 3) for item in values))


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\wÄÖÜäöüß'-]+\b", text, flags=re.UNICODE))


def _scene_boundaries(reference: Path, duration: float) -> list[float]:
    weights = [_word_count(str(scene["spoken_youtube"])) for scene in SCENES]
    total = max(1, sum(weights))
    targets: list[float] = []
    cumulative = 0
    for weight in weights[:-1]:
        cumulative += weight
        targets.append(duration * cumulative / total)

    candidates = _silence_candidates(reference)
    boundaries = [0.0]
    for index, target in enumerate(targets):
        minimum = boundaries[-1] + 0.9
        remaining = len(targets) - index
        maximum = duration - remaining * 0.9
        eligible = [item for item in candidates if minimum <= item <= maximum]
        nearest = min(eligible, key=lambda item: abs(item - target)) if eligible else target
        if eligible and abs(nearest - target) > 1.25:
            nearest = target
        boundaries.append(max(minimum, min(maximum, nearest)))
    boundaries.append(duration)
    return [round(item, 3) for item in boundaries]


def _request_json(url: str, api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": api_key,
            "User-Agent": "TAYVORIQ-Visual-Hotfix/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "TAYVORIQ-Visual-Hotfix/1.0"})
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=90) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    if not target.is_file() or target.stat().st_size < 30_000:
        raise RuntimeError(f"ASSET_DOWNLOAD_INVALID:{target.name}")


def _select_video(data: dict[str, Any], used_ids: set[str]) -> tuple[str, str] | None:
    choices: list[tuple[tuple[int, int, int], str, str]] = []
    for video in data.get("videos") or []:
        if not isinstance(video, dict):
            continue
        video_id = str(video.get("id") or "")
        if not video_id or video_id in used_ids:
            continue
        for file in video.get("video_files") or []:
            if not isinstance(file, dict) or str(file.get("file_type") or "") != "video/mp4":
                continue
            link = str(file.get("link") or "")
            width = int(file.get("width") or 0)
            height = int(file.get("height") or 0)
            if not link or width < 480 or height < 720:
                continue
            portrait = 1 if height > width else 0
            enough = 1 if height >= 1280 else 0
            closeness = -abs(width - WIDTH) - abs(height - HEIGHT)
            choices.append(((portrait, enough, closeness), video_id, link))
    if not choices:
        return None
    choices.sort(key=lambda item: item[0], reverse=True)
    _, video_id, link = choices[0]
    return video_id, link


def _select_photo(data: dict[str, Any], used_ids: set[str]) -> tuple[str, str] | None:
    for photo in data.get("photos") or []:
        if not isinstance(photo, dict):
            continue
        photo_id = str(photo.get("id") or "")
        if not photo_id or photo_id in used_ids:
            continue
        src = photo.get("src") if isinstance(photo.get("src"), dict) else {}
        link = str(src.get("portrait") or src.get("large2x") or src.get("original") or "")
        if link:
            return photo_id, link
    return None


def _find_asset(scene_index: int, queries: tuple[str, ...], api_key: str, used_ids: set[str], asset_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    for query in queries:
        encoded = urllib.parse.quote_plus(query)
        try:
            video_data = _request_json(
                f"https://api.pexels.com/videos/search?query={encoded}&per_page=20&orientation=portrait",
                api_key,
            )
            selected = _select_video(video_data, used_ids)
            if selected:
                asset_id, url = selected
                target = asset_dir / f"scene_{scene_index:02d}_pexels_{asset_id}.mp4"
                _download(url, target)
                used_ids.add(asset_id)
                return {
                    "scene": scene_index,
                    "source": "pexels_video",
                    "provider_id": asset_id,
                    "query": query,
                    "path": str(target),
                    "sha256": _sha256(target),
                }
        except Exception as exc:
            errors.append(f"video:{query}:{type(exc).__name__}")

        try:
            photo_data = _request_json(
                f"https://api.pexels.com/v1/search?query={encoded}&per_page=20&orientation=portrait",
                api_key,
            )
            selected_photo = _select_photo(photo_data, used_ids)
            if selected_photo:
                asset_id, url = selected_photo
                target = asset_dir / f"scene_{scene_index:02d}_pexels_{asset_id}.jpg"
                _download(url, target)
                used_ids.add(asset_id)
                return {
                    "scene": scene_index,
                    "source": "pexels_photo_kenburns",
                    "provider_id": asset_id,
                    "query": query,
                    "path": str(target),
                    "sha256": _sha256(target),
                }
        except Exception as exc:
            errors.append(f"photo:{query}:{type(exc).__name__}")

    raise RuntimeError(
        f"NO_QUALITY_ASSET_FOR_SCENE:{scene_index}:" + ";".join(errors[-6:])
    )


def _render_scene(asset: dict[str, Any], duration: float, target: Path) -> None:
    source_path = Path(str(asset["path"]))
    if asset["source"] == "pexels_video":
        command = [
            "ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(source_path),
            "-t", f"{duration:.3f}",
            "-vf", (
                f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},fps={FPS},setsar=1"
            ),
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target),
        ]
    else:
        command = [
            "ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(source_path),
            "-t", f"{duration:.3f}",
            "-vf", (
                "scale=1260:2240:force_original_aspect_ratio=increase,"
                "crop=1260:2240,"
                f"zoompan=z='min(zoom+0.0009,1.12)':x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':d=1:s={WIDTH}x{HEIGHT}:fps={FPS},setsar=1"
            ),
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target),
        ]
    _run(command)
    if not target.is_file() or target.stat().st_size < 100_000:
        raise RuntimeError(f"RENDERED_SCENE_INVALID:{target.name}")


def _srt_time(value: float) -> str:
    milliseconds = int(round(max(0.0, value) * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _write_srt(path: Path, boundaries: list[float], platform: str, platform_duration: float, reference_duration: float) -> None:
    scale = platform_duration / max(reference_duration, 0.001)
    lines: list[str] = []
    for index, scene in enumerate(SCENES, start=1):
        start = min(platform_duration, boundaries[index - 1] * scale)
        end = min(platform_duration, boundaries[index] * scale)
        text = str(scene["spoken_youtube" if platform == "youtube" else "spoken_tiktok"])
        lines.extend([str(index), f"{_srt_time(start)} --> {_srt_time(end)}", text, ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _concat_segments(segments: list[Path], target: Path) -> None:
    list_file = target.with_suffix(".txt")
    list_file.write_text(
        "\n".join(f"file '{path.resolve().as_posix()}'" for path in segments) + "\n",
        encoding="utf-8",
    )
    _run([
        "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(target),
    ])


def _finalize_video(silent_timeline: Path, source_with_audio: Path, srt: Path, target: Path, duration: float) -> None:
    subtitle_name = srt.name.replace("'", "\\'")
    filter_chain = (
        f"subtitles='{subtitle_name}':force_style='FontName=DejaVu Sans,FontSize=24,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,BorderStyle=3,"
        "Outline=1,Shadow=0,Alignment=2,MarginV=235',"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "text='TAYVORIQ · ERDBEBEN · TEIL 2':fontcolor=white:fontsize=38:"
        "x=(w-text_w)/2:y=105:box=1:boxcolor=black@0.42:boxborderw=18"
    )
    command = [
        "ffmpeg", "-y", "-v", "error", "-i", str(silent_timeline.resolve()),
        "-i", str(source_with_audio.resolve()), "-t", f"{duration:.3f}",
        "-vf", filter_chain,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(target.resolve()),
    ]
    completed = _run(command, cwd=srt.parent, check=False)
    if completed.returncode != 0:
        # Some hosted ffmpeg builds omit drawtext. Keep subtitles mandatory and retry
        # without the decorative top brand rather than losing the real-motion master.
        subtitle_only = (
            f"subtitles='{subtitle_name}':force_style='FontName=DejaVu Sans,FontSize=24,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,BorderStyle=3,"
            "Outline=1,Shadow=0,Alignment=2,MarginV=235'"
        )
        _run([
            "ffmpeg", "-y", "-v", "error", "-i", str(silent_timeline.resolve()),
            "-i", str(source_with_audio.resolve()), "-t", f"{duration:.3f}",
            "-vf", subtitle_only, "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target.resolve()),
        ], cwd=srt.parent)


def _validate_video(path: Path, old_sha: str, expected_duration: float) -> dict[str, Any]:
    data = _ffprobe(path)
    streams = data.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    actual_duration = _duration(path)
    sha = _sha256(path)
    checks = {
        "fresh_sha": sha != old_sha,
        "width": int(video.get("width") or 0) == WIDTH,
        "height": int(video.get("height") or 0) == HEIGHT,
        "audio_present": bool(audio),
        "duration_close": abs(actual_duration - expected_duration) <= 0.75,
        "minimum_bytes": path.stat().st_size >= 1_000_000,
    }
    if not all(checks.values()):
        raise RuntimeError(f"FINAL_VIDEO_GATE_FAILED:{path.name}:{checks}")
    return {
        "path": path.name,
        "sha256": sha,
        "bytes": path.stat().st_size,
        "duration_seconds": round(actual_duration, 3),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "audio_codec": str(audio.get("codec_name") or ""),
        "checks": checks,
    }


def _rewrite_job(job_path: Path, old_review: str, new_review: str, manifest: dict[str, Any]) -> None:
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except Exception:
        job = {}
    if not isinstance(job, dict):
        job = {}
    job["render_reused"] = False
    job["visual_hotfix"] = manifest
    job["operator_visual_review_required"] = True
    job["quality_gates_weakened"] = False
    job["review_id"] = new_review
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(pages_root: Path, old_review: str, new_review: str, api_key: str) -> dict[str, Any]:
    old_dir = pages_root / "tayvoriq" / "runs" / old_review
    if not old_dir.is_dir():
        raise RuntimeError(f"OLD_REVIEW_MISSING:{old_dir}")
    old_youtube = old_dir / "short_youtube.mp4"
    old_tiktok = old_dir / "short_tiktok.mp4"
    if not old_youtube.is_file() or not old_tiktok.is_file():
        raise RuntimeError("OLD_REVIEW_MASTER_MISSING")

    work = Path("out") / f"episode2-real-motion-{new_review}"
    if work.exists():
        shutil.rmtree(work)
    asset_dir = work / "assets"
    scene_dir = work / "scenes"
    asset_dir.mkdir(parents=True, exist_ok=True)
    scene_dir.mkdir(parents=True, exist_ok=True)

    yt_duration = _duration(old_youtube)
    tt_duration = _duration(old_tiktok)
    if not 20.0 <= yt_duration <= 40.0 or not 20.0 <= tt_duration <= 40.0:
        raise RuntimeError(f"SOURCE_AUDIO_DURATION_INVALID:{yt_duration}:{tt_duration}")
    reference_duration = max(yt_duration, tt_duration)
    base_boundaries = _scene_boundaries(old_youtube, yt_duration)
    normalized = [value / yt_duration for value in base_boundaries]
    boundaries = [round(value * reference_duration, 3) for value in normalized]
    boundaries[-1] = round(reference_duration, 3)

    used_ids: set[str] = set()
    assets: list[dict[str, Any]] = []
    for index, scene in enumerate(SCENES, start=1):
        asset = _find_asset(index, tuple(scene["queries"]), api_key, used_ids, asset_dir)
        assets.append(asset)

    unique_ids = {str(item.get("provider_id") or "") for item in assets}
    moving_or_animated = [item for item in assets if item.get("source") in {"pexels_video", "pexels_photo_kenburns"}]
    if len(assets) != len(SCENES) or len(unique_ids) != len(SCENES) or len(moving_or_animated) != len(SCENES):
        raise RuntimeError("VISUAL_DIVERSITY_GATE_FAILED")
    if any(item.get("source") == "generated_geology_animation" for item in assets):
        raise RuntimeError("REJECTED_GEOLOGY_PACK_REAPPEARED")

    segments: list[Path] = []
    for index, asset in enumerate(assets, start=1):
        duration = max(1.0, boundaries[index] - boundaries[index - 1])
        target = scene_dir / f"scene_{index:02d}.mp4"
        _render_scene(asset, duration, target)
        segments.append(target)

    silent_timeline = work / "real_motion_timeline.mp4"
    _concat_segments(segments, silent_timeline)

    output_dir = work / "final"
    output_dir.mkdir(parents=True, exist_ok=True)
    yt_srt = output_dir / "youtube.srt"
    tt_srt = output_dir / "tiktok.srt"
    _write_srt(yt_srt, boundaries, "youtube", yt_duration, reference_duration)
    _write_srt(tt_srt, boundaries, "tiktok", tt_duration, reference_duration)

    youtube_final = output_dir / "short_youtube.mp4"
    tiktok_final = output_dir / "short_tiktok.mp4"
    _finalize_video(silent_timeline, old_youtube, yt_srt, youtube_final, yt_duration)
    _finalize_video(silent_timeline, old_tiktok, tt_srt, tiktok_final, tt_duration)

    youtube_gate = _validate_video(youtube_final, _sha256(old_youtube), yt_duration)
    tiktok_gate = _validate_video(tiktok_final, _sha256(old_tiktok), tt_duration)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "repair_type": "operator-rejected-visual-full-replacement",
        "source_review_id": old_review,
        "review_id": new_review,
        "visual_contract": "world-forces-v1-episode-2-real-motion-hotfix-v1",
        "facts_reused": True,
        "voice_reused": True,
        "old_render_reused": False,
        "old_visual_assets_reused": False,
        "generated_geology_animation": False,
        "scene_count": len(SCENES),
        "unique_provider_assets": len(unique_ids),
        "assets": [
            {
                "scene": item["scene"],
                "source": item["source"],
                "provider_id": item["provider_id"],
                "query": item["query"],
                "sha256": item["sha256"],
            }
            for item in assets
        ],
        "scene_boundaries_seconds": boundaries,
        "youtube": youtube_gate,
        "tiktok": tiktok_gate,
        "human_visual_review_required": True,
        "youtube_upload_allowed_before_human_approval": False,
        "quality_gates_weakened": False,
    }

    new_dir = pages_root / "tayvoriq" / "runs" / new_review
    if new_dir.exists():
        shutil.rmtree(new_dir)
    shutil.copytree(old_dir, new_dir)
    shutil.copy2(youtube_final, new_dir / "short_youtube.mp4")
    shutil.copy2(tiktok_final, new_dir / "short_tiktok.mp4")
    (new_dir / "visual_hotfix_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    index_path = new_dir / "index.html"
    html = index_path.read_text(encoding="utf-8")
    html = html.replace(old_review, new_review)
    html = html.replace(
        "YouTube und TikTok getrennt geprüft",
        "Visual-Hotfix · alte abgelehnte Szenen vollständig ersetzt · YouTube und TikTok getrennt",
    )
    index_path.write_text(html, encoding="utf-8")

    _rewrite_job(new_dir / "job.json", old_review, new_review, manifest)
    publication_gate = {
        "passed": True,
        "gate": "episode2-real-motion-hotfix-technical-publication-gate-v1",
        "checks": {
            "fresh_visual_stream": True,
            "rejected_old_master_sha_blocked": True,
            "generated_geology_animation_absent": True,
            "unique_visual_assets": len(unique_ids),
            "scene_count": len(SCENES),
            "youtube_video_contract": youtube_gate["checks"],
            "tiktok_video_contract": tiktok_gate["checks"],
        },
        "human_visual_review_required": True,
        "youtube_upload_allowed_before_human_approval": False,
        "quality_gates_weakened": False,
    }
    (new_dir / "publication_quality_gate.json").write_text(
        json.dumps(publication_gate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Replace rejected episode-two visuals with unique Pexels real-motion assets")
    parser.add_argument("--pages-root", required=True)
    parser.add_argument("--old-review", required=True)
    parser.add_argument("--new-review", required=True)
    args = parser.parse_args()

    api_key = str(os.environ.get("PEXELS_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY_MISSING")
    for command in ("ffmpeg", "ffprobe"):
        if not shutil.which(command):
            raise RuntimeError(f"MISSING_RUNTIME:{command}")

    build(Path(args.pages_root), str(args.old_review), str(args.new_review), api_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
