#!/usr/bin/env python3
"""Advance an active editorial series only after verified YouTube publication."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def normalized_title(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def published_run_ids(review_dir: Path) -> set[str]:
    result: set[str] = set()
    for path in review_dir.glob("*.json") if review_dir.is_dir() else []:
        data = read_json(path)
        if data.get("platform_upload_performed") is True:
            result.add(str(data.get("review_id") or path.stem))
    return result


def published_youtube_titles(review_dir: Path) -> set[str]:
    """Return exact normalized titles backed by verified YouTube publication evidence."""
    result: set[str] = set()
    for path in review_dir.glob("*.json") if review_dir.is_dir() else []:
        data = read_json(path)
        youtube = data.get("youtube") if isinstance(data.get("youtube"), dict) else {}
        upload_status = str(data.get("upload_status") or "").strip().upper()
        verified_youtube = bool(str(youtube.get("video_id") or "").strip()) or upload_status == "PUBLISHED_YOUTUBE"
        payload = data.get("published_payload") if isinstance(data.get("published_payload"), dict) else {}
        title = normalized_title(payload.get("title"))
        if data.get("platform_upload_performed") is True and verified_youtube and title:
            result.add(title)
    return result


def request_run_ids(request: dict, run_map_dir: Path) -> set[str]:
    result: set[str] = set()
    for key in ("golden_path_run_id", "published_run_id", "publication_run_id"):
        run_id = str(request.get(key) or "")
        if run_id.isdigit():
            result.add(run_id)
    request_id = str(request.get("request_id") or "")
    selection_id = str(request.get("selection_id") or "")
    for path in run_map_dir.glob("*.json") if run_map_dir.is_dir() else []:
        mapping = read_json(path)
        if (
            str(mapping.get("source_request_id") or "") == request_id
            or str(mapping.get("selection_id") or "") == selection_id
        ):
            run_id = str(mapping.get("run_id") or path.stem)
            if run_id.isdigit():
                result.add(run_id)
    return result


def matching_requests(request_dir: Path, series_id: str, episode: int) -> list[dict]:
    matches: list[dict] = []
    for path in request_dir.glob("*.json") if request_dir.is_dir() else []:
        request = read_json(path)
        source = request.get("source_context") if isinstance(request.get("source_context"), dict) else {}
        series = source.get("series_context") if isinstance(source.get("series_context"), dict) else {}
        try:
            request_episode = int(series.get("episode") or 0)
        except Exception:
            request_episode = 0
        if str(series.get("series_id") or "") == series_id and request_episode == episode:
            request.setdefault("request_id", path.stem)
            matches.append(request)
    return matches


def apply_episode(state: dict, episode_data: dict) -> None:
    state["episode"] = int(episode_data["episode"])
    for key in ("episode_title", "cover_text", "hook", "bridge_out", "visual_continuity"):
        state[key] = episode_data[key]
    state["trend"] = episode_data["trend"]
    state["status"] = "ready_for_selection"


def reconcile(state: dict, request_dir: Path, review_dir: Path, run_map_dir: Path) -> tuple[dict, bool, str]:
    status = str(state.get("status") or "").lower()
    if status not in {"active", "ready_for_selection"}:
        return state, False, "series_not_active"
    series_id = str(state.get("series_id") or "").strip()
    episode = int(state.get("episode") or 0)
    episodes = state.get("episodes") if isinstance(state.get("episodes"), list) else []
    if not series_id or episode < 1:
        raise SystemExit("ACTIVE_SERIES_INVALID: missing series_id or episode")

    published = published_run_ids(review_dir)
    published_titles = published_youtube_titles(review_dir)
    finished = False
    for request in matching_requests(request_dir, series_id, episode):
        run_evidence = bool(request_run_ids(request, run_map_dir) & published)
        title_evidence = normalized_title(request.get("topic")) in published_titles
        if run_evidence or title_evidence:
            finished = True
            break
    if not finished:
        return state, False, "current_episode_not_published"

    next_episode = next((item for item in episodes if int(item.get("episode") or 0) == episode + 1), None)
    state["last_published_episode"] = episode
    if next_episode:
        apply_episode(state, next_episode)
        return state, True, "advanced_to_next_episode"
    state["status"] = "completed"
    state["completed_episode_count"] = episode
    return state, True, "series_completed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="state/tayvoriq-active-series.json")
    parser.add_argument("--requests", default="requests")
    parser.add_argument("--reviews", default=".automation/tayvoriq-reviews")
    parser.add_argument("--run-maps", default=".automation/tayvoriq-agent-v2/run-map")
    args = parser.parse_args()

    state_path = Path(args.state)
    state = read_json(state_path)
    updated, changed, reason = reconcile(
        state,
        Path(args.requests),
        Path(args.reviews),
        Path(args.run_maps),
    )
    if changed:
        state_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "changed": changed,
        "reason": reason,
        "status": updated.get("status"),
        "series_id": updated.get("series_id"),
        "episode": updated.get("episode"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
