from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_paid_boost_policy_v1 as boost


def _config() -> dict:
    return json.loads((ROOT / "config/tayvoriq_growth_runtime_v2.json").read_text(encoding="utf-8"))


def _metrics(**overrides) -> dict:
    value = {
        "platform": "youtube_shorts",
        "hours_since_publish": 2.5,
        "observed": {
            "engaged_or_qualified_views": 1200,
            "retention_or_completion": 0.74,
            "subscriber_conversion_per_1000": 4.0,
        },
        "rolling_baseline": {
            "engaged_or_qualified_views": 1000,
            "retention_or_completion": 0.68,
            "subscriber_conversion_per_1000": 3.0,
        },
        "policy_restriction": False,
        "publishable": True,
        "tests_started_this_week": 0,
        "spend_eur_this_week": 0.0,
        "spend_eur_this_month": 0.0,
        "ads_credentials_present": False,
    }
    value.update(overrides)
    return value


def test_budget_is_exactly_five_with_absolute_five_euro_cap() -> None:
    result = boost.evaluate(_metrics(), _config())
    assert result["requested_total_budget_eur"] == 5.0
    assert result["hard_max_total_budget_eur"] == 5.0
    assert result["must_never_exceed_hard_cap"] is True


def test_good_video_without_credentials_never_spends() -> None:
    result = boost.evaluate(_metrics(), _config())
    assert result["eligible"] is True
    assert result["action"] == "BOOST_CANDIDATE_NO_CREDENTIALS"


def test_underperforming_video_is_not_boosted() -> None:
    metrics = _metrics()
    metrics["observed"]["retention_or_completion"] = 0.40
    result = boost.evaluate(metrics, _config())
    assert result["eligible"] is False
    assert result["action"] == "NO_BOOST"
    assert "below_baseline_retention_or_completion" in result["reasons"]


def test_weekly_cap_blocks_third_five_euro_test() -> None:
    result = boost.evaluate(_metrics(tests_started_this_week=2, spend_eur_this_week=10.0), _config())
    assert result["eligible"] is False
    assert "weekly_test_limit" in result["reasons"]
    assert "weekly_spend_cap" in result["reasons"]
