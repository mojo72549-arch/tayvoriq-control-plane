from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_analytics_v5 as analytics


def test_available_platform_metrics_are_stored_without_inventing_missing_values(tmp_path):
    payload = {
        "platform": "youtube_shorts",
        "video_id": "abc123",
        "request_id": "telegram-1-trend-1",
        "metrics": {
            "views": 1200,
            "average_view_duration_seconds": 31.4,
            "average_percentage_viewed": 78.5,
            "likes": 44,
            "comments": 5,
            "shares": 8,
        },
        "content_contract": {
            "cta_type": "EXPERTISE",
            "series_id": "ki-60",
            "open_loop_status": "SOFT",
        },
    }
    target = analytics.store_observation(payload, tmp_path)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["metrics"]["views"] == 1200
    assert data["metrics"]["completion_rate"] is None
    assert "completion_rate" not in data["available_metrics"]
    assert data["content_contract"]["cta_type"] == "EXPERTISE"
    assert data["content_contract"]["series_id"] == "ki-60"
    assert data["content_contract"]["open_loop_status"] == "SOFT"
    assert data["data_policy"]["small_sample_auto_optimization_enabled"] is False
    assert data["data_policy"]["missing_metrics_are_null_not_estimated"] is True


def test_analytics_history_collects_observations_but_never_auto_optimizes(tmp_path):
    base = {
        "platform": "tiktok",
        "video_id": "v1",
        "metrics": {"views": 100},
        "content_contract": {"cta_type": "IDENTITY", "open_loop_status": "NONE"},
    }
    target = analytics.store_observation(base, tmp_path)
    second = dict(base)
    second["metrics"] = {"views": 200, "follow_subscriber_signal": 3}
    analytics.store_observation(second, tmp_path)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert len(data["history"]) == 2
    assert data["metrics"]["views"] == 200
    assert data["data_policy"]["small_sample_auto_optimization_enabled"] is False
