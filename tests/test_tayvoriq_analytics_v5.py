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


def test_growth_review_uses_only_observed_per_video_conversion(tmp_path):
    analytics.store_observation({
        "platform": "youtube_shorts",
        "video_id": "pflege-1",
        "metric_scope": "video",
        "metrics": {
            "views": 1200,
            "engaged_views": 800,
            "follow_subscriber_signal": 6,
            "average_percentage_viewed": 74.2,
        },
        "content_contract": {
            "topic": "Pflegedeckel",
            "primary_hook": "Ein Deckel für Pflegekosten?",
            "follow_reason": "Wir verfolgen die nächsten Entscheidungen.",
            "cta_type": "IDENTITY",
        },
    }, tmp_path)
    analytics.store_observation({
        "platform": "tiktok",
        "video_id": "pflege-2",
        "metrics": {"views": 2000},
    }, tmp_path)

    report = analytics.growth_review(tmp_path)
    youtube = next(row for row in report["videos"] if row["platform"] == "youtube_shorts")
    tiktok = next(row for row in report["videos"] if row["platform"] == "tiktok")
    assert youtube["follows_per_1000_views"] == 5
    assert youtube["follows_per_1000_engaged_views"] == 7.5
    assert youtube["primary_hook"] == "Ein Deckel für Pflegekosten?"
    assert tiktok["follows_per_1000_views"] is None
    assert report["conversion_data_available_count"] == 1
    assert report["automatic_topic_ranking_performed"] is False


def test_growth_review_does_not_treat_account_growth_as_video_conversion(tmp_path):
    analytics.store_observation({
        "platform": "tiktok",
        "video_id": "pflege",
        "metric_scope": "account",
        "metrics": {"views": 1000, "follow_subscriber_signal": 10},
    }, tmp_path)
    row = analytics.growth_review(tmp_path)["videos"][0]
    assert row["follow_subscriber_signal"] == 10
    assert row["follows_per_1000_views"] is None
    assert row["conversion_data_available"] is False
