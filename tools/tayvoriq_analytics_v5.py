#!/usr/bin/env python3
"""TAYVORIQ V5 post-publish analytics storage contract.

This module only normalizes and stores observations that a platform adapter
actually supplies. It intentionally does not infer missing metrics and contains
no automatic optimization/ranking logic.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

METRIC_FIELDS = (
    "views",
    "engaged_views",
    "average_view_duration_seconds",
    "average_percentage_viewed",
    "completion_rate",
    "likes",
    "comments",
    "shares",
    "saves_favorites",
    "follow_subscriber_signal",
    "profile_visits",
    "returning_viewer_signal",
)

CONTRACT_FIELDS = (
    "cta_type",
    "series_id",
    "open_loop_status",
    "topic",
    "content_angle",
    "primary_hook",
    "follow_reason",
)

def clean(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]

def _number_or_none(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return int(number) if number.is_integer() else number

def normalize_observation(payload: dict[str, Any]) -> dict[str, Any]:
    platform = clean(payload.get("platform"), 80)
    video_id = clean(payload.get("video_id"), 240)
    if not platform:
        raise ValueError("ANALYTICS_PLATFORM_REQUIRED")
    if not video_id:
        raise ValueError("ANALYTICS_VIDEO_ID_REQUIRED")

    metrics_in = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    contract_in = payload.get("content_contract") if isinstance(payload.get("content_contract"), dict) else {}

    metrics = {key: _number_or_none(metrics_in.get(key)) for key in METRIC_FIELDS}
    available = [key for key, value in metrics.items() if value is not None]

    contract = {
        "cta_type": clean(contract_in.get("cta_type"), 40).upper() or None,
        "series_id": clean(contract_in.get("series_id"), 160) or None,
        "open_loop_status": clean(contract_in.get("open_loop_status"), 20).upper() or None,
        "topic": clean(contract_in.get("topic"), 240) or None,
        "content_angle": clean(contract_in.get("content_angle"), 500) or None,
        "primary_hook": clean(contract_in.get("primary_hook"), 240) or None,
        "follow_reason": clean(contract_in.get("follow_reason"), 500) or None,
    }
    if contract["open_loop_status"] not in {None, "NONE", "SOFT", "HARD"}:
        raise ValueError("ANALYTICS_INVALID_OPEN_LOOP_STATUS")

    observed_at = clean(payload.get("observed_at"), 80) or datetime.now(timezone.utc).isoformat()
    metric_scope = clean(payload.get("metric_scope"), 40).lower() or "unspecified"
    if metric_scope not in {"video", "account", "unspecified"}:
        raise ValueError("ANALYTICS_INVALID_METRIC_SCOPE")
    return {
        "schema": "tayvoriq-analytics-v5",
        "platform": platform,
        "video_id": video_id,
        "request_id": clean(payload.get("request_id"), 240) or None,
        "published_at": clean(payload.get("published_at"), 80) or None,
        "observed_at": observed_at,
        "metric_scope": metric_scope,
        "metrics": metrics,
        "available_metrics": available,
        "content_contract": contract,
        "data_policy": {
            "missing_metrics_are_null_not_estimated": True,
            "small_sample_auto_optimization_enabled": False,
            "correlation_is_not_causation": True,
        },
    }

def store_observation(payload: dict[str, Any], out_dir: Path) -> Path:
    normalized = normalize_observation(payload)
    platform = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in normalized["platform"])[:80]
    video = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in normalized["video_id"])[:180]
    target = out_dir / platform / f"{video}.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    history: list[dict[str, Any]] = []
    if target.is_file():
        try:
            current = json.loads(target.read_text(encoding="utf-8"))
            history = current.get("history") if isinstance(current.get("history"), list) else []
        except Exception:
            history = []

    snapshot = dict(normalized)
    snapshot.pop("history", None)
    merged = dict(normalized)
    merged["history"] = (history + [snapshot])[-100:]
    target.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target

def growth_review(out_dir: Path) -> dict[str, Any]:
    """Report observed conversion with an explicit denominator and no ranking."""
    rows: list[dict[str, Any]] = []
    for path in sorted(out_dir.glob("*/*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if record.get("schema") != "tayvoriq-analytics-v5":
            continue
        metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        contract = record.get("content_contract") if isinstance(record.get("content_contract"), dict) else {}
        follows = _number_or_none(metrics.get("follow_subscriber_signal"))
        views = _number_or_none(metrics.get("views"))
        engaged = _number_or_none(metrics.get("engaged_views"))
        video_attributed = record.get("metric_scope") == "video"
        def rate(denominator: int | float | None) -> float | None:
            if not video_attributed or follows is None or denominator is None or denominator <= 0:
                return None
            return round(1000 * follows / denominator, 2)
        rows.append({
            "platform": record.get("platform"),
            "video_id": record.get("video_id"),
            "request_id": record.get("request_id"),
            "published_at": record.get("published_at"),
            "observed_at": record.get("observed_at"),
            "metric_scope": record.get("metric_scope") or "unspecified",
            "topic": contract.get("topic"),
            "primary_hook": contract.get("primary_hook"),
            "follow_reason": contract.get("follow_reason"),
            "cta_type": contract.get("cta_type"),
            "views": views,
            "engaged_views": engaged,
            "average_percentage_viewed": _number_or_none(metrics.get("average_percentage_viewed")),
            "completion_rate": _number_or_none(metrics.get("completion_rate")),
            "follow_subscriber_signal": follows,
            "follows_per_1000_views": rate(views),
            "follows_per_1000_engaged_views": rate(engaged),
            "conversion_data_available": video_attributed and follows is not None and views is not None and views > 0,
        })
    return {
        "schema": "tayvoriq-growth-review-v1",
        "videos": rows,
        "video_count": len(rows),
        "conversion_data_available_count": sum(row["conversion_data_available"] for row in rows),
        "automatic_topic_ranking_performed": False,
        "missing_metrics_estimated": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--input")
    mode.add_argument("--review-dir")
    parser.add_argument("--out-dir", default="analytics/tayvoriq-v5")
    args = parser.parse_args()
    if args.review_dir:
        print(json.dumps(growth_review(Path(args.review_dir)), ensure_ascii=False, indent=2))
        return 0
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    target = store_observation(payload, Path(args.out_dir))
    print(json.dumps({
        "analytics_recorded": True,
        "path": str(target),
        "auto_optimization_performed": False,
    }, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
