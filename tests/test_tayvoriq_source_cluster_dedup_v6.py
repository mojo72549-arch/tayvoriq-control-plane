from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_agent_trend_radar_v6 as radar


def _candidate(title: str, scope: str, priority: int, growth: int, sources: list[str]) -> dict:
    return {
        "title": title,
        "trend_scope": scope,
        "score": 90,
        "sources": sources,
        "growth_v2": {
            "growth_score": growth,
            "binding_score": 85,
            "priority_score": priority,
        },
        "source_context": {"fallback_editorial_answers": {}},
    }


def test_same_two_sources_are_one_story_even_with_different_titles() -> None:
    shared = ["https://guardian.example/ebola", "https://dw.example/ebola"]
    items = [
        _candidate("Ebola-Ausbruch im Kongo erreicht Rekordtodeszahl", "world_society", 90, 88, shared),
        _candidate("Todesreichster Ebola-Ausbruch in der Demokratischen Republik Kongo", "world_society", 89, 87, shared),
        _candidate("Apple Datenschutz", "technology_ai", 88, 86, ["https://a.example/apple", "https://b.example/apple"]),
        _candidate("Tsunami erklärt", "science_future", 87, 86, ["https://a.example/tsunami", "https://b.example/tsunami"]),
        _candidate("Energiepreis-Thema", "business_economy", 86, 85, ["https://a.example/energy", "https://b.example/energy"]),
    ]
    deduped = radar._dedupe_story_clusters(items)
    titles = [item["title"] for item in deduped]
    assert len([title for title in titles if "Ebola" in title]) == 1
    assert len(deduped) == 4


def test_duplicate_cluster_forces_rescan_when_only_three_unique_strong_stories_remain() -> None:
    shared = ["https://guardian.example/ebola", "https://dw.example/ebola"]
    items = [
        _candidate("Ebola A", "world_society", 90, 88, shared),
        _candidate("Ebola B", "world_society", 89, 87, shared),
        _candidate("Apple", "technology_ai", 88, 86, ["https://a.example/apple", "https://b.example/apple"]),
        _candidate("Tsunami", "science_future", 87, 86, ["https://a.example/tsunami", "https://b.example/tsunami"]),
    ]
    with pytest.raises(SystemExit, match="GROWTH_RESCAN_REQUIRED"):
        radar.diversify(items, "evening")
