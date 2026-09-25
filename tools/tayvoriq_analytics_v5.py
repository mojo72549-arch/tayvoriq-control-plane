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
    "average_view_duration_seconds",
    "average_percentage_viewed",
    "completion_rate",
    "likes",
    "comments",
    "shares",
    "saves_favorites",
    "follow_subscriber_signal",
    "returning_viewer_signal",
)

CONTRACT_FIELDS = (
    "cta_type",
    "series_id",
    "open_loop_status",
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
    }
    if contract["open_loop_status"] not in {None, "NONE", "SOFT", "HARD"}:
        raise ValueError("ANALYTICS_INVALID_OPEN_LOOP_STATUS")

    observed_at = clean(payload.get("observed_at"), 80) or datetime.now(timezone.utc).isoformat()
    return {
        "schema": "tayvoriq-analytics-v5",
        "platform": platform,
        "video_id": video_id,
        "request_id": clean(payload.get("request_id"), 240) or None,
        "published_at": clean(payload.get("published_at"), 80) or None,
        "observed_at": observed_at,
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

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", default="analytics/tayvoriq-v5")
    args = parser.parse_args()
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
