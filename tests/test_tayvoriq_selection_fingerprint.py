from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_agent_series_request_v2 as series_request


def _trend(title: str, suffix: str) -> dict:
    return {
        "title": title,
        "sources": [
            f"https://publisher-a.example/{suffix}",
            f"https://publisher-b.example/{suffix}",
        ],
    }


def test_fingerprint_is_stable_for_same_ranked_set() -> None:
    trends = [_trend("Tsunami erklärt", "a"), _trend("Zweiter Trend", "b")]
    assert series_request._fingerprint(trends) == series_request._fingerprint(trends)
    assert len(series_request._fingerprint(trends)) == 6


def test_fingerprint_changes_when_ranked_selection_changes() -> None:
    first = [_trend("Tsunami erklärt", "a"), _trend("Zweiter Trend", "b")]
    second = [_trend("Tsunami erklärt", "a"), _trend("Neuer Trend", "c")]
    assert series_request._fingerprint(first) != series_request._fingerprint(second)


def test_fingerprint_changes_when_source_evidence_changes() -> None:
    first = [_trend("Tsunami erklärt", "a")]
    second = [_trend("Tsunami erklärt", "new")]
    assert series_request._fingerprint(first) != series_request._fingerprint(second)
