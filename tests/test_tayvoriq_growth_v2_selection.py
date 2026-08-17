from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_agent_trend_radar_v4 as growth


def _candidate(name: str, priority: int, growth_score: int, *, series: bool = False, scope: str = "science_future") -> dict:
    source_context = {"fallback_editorial_answers": {"what_happened": "x", "why_happening": "x", "who_is_affected": "x", "personal_impact": "x", "action_now": "x"}}
    if series:
        source_context["series_context"] = {"series_id": "world-forces", "episode": 3}
    return {"title": name, "trend_scope": scope, "score": 90, "growth_v2": {"growth_score": growth_score, "binding_score": 80, "priority_score": priority, "series_candidate": series}, "source_context": source_context}


def test_runtime_contract_is_two_runs_every_day_and_series_has_no_reserved_slot() -> None:
    cfg = json.loads((ROOT / "config/tayvoriq_growth_runtime_v2.json").read_text(encoding="utf-8"))
    assert cfg["daily_editorial_runs"] == 2
    assert cfg["selection"]["always_run_fresh_trend_scan"] is True
    assert cfg["selection"]["series_reserved_slots"] == 0
    assert cfg["selection"]["series_competes_with_trends"] is True
    assert cfg["selection"]["telegram_candidates_min"] == 1
    assert cfg["selection"]["telegram_candidates_max"] == 5
    assert cfg["selection"]["weak_fill_allowed"] is False
    assert cfg["selection"]["rescan_only_when_zero_eligible"] is True
    assert cfg["platform_native"]["tiktok"]["hard_final_floor_seconds"] == 61


def test_one_strong_candidate_is_surfaced_without_weak_fill() -> None:
    items = [_candidate("strong", 95, 91, scope="world_society"), _candidate("weak-a", 70, 79, scope="technology_ai"), _candidate("weak-b", 69, 72, scope="business_economy")]
    selected = growth.diversify(items, "evening")
    assert [item["title"] for item in selected] == ["strong"]


def test_series_is_not_forced_when_five_stronger_fresh_candidates_exist() -> None:
    items = [_candidate("series", 81, 80, series=True), _candidate("a", 96, 94, scope="world_society"), _candidate("b", 95, 93, scope="technology_ai"), _candidate("c", 94, 92, scope="business_economy"), _candidate("d", 93, 91, scope="mobility_energy"), _candidate("e", 92, 90, scope="sports")]
    selected = growth.diversify(items, "evening")
    assert len(selected) == 5
    assert all(item["title"] != "series" for item in selected)


def test_series_can_win_when_it_is_competitive() -> None:
    items = [_candidate("series", 99, 96, series=True), _candidate("a", 95, 93, scope="world_society"), _candidate("b", 94, 92, scope="technology_ai"), _candidate("c", 93, 91, scope="business_economy"), _candidate("d", 92, 90, scope="mobility_energy"), _candidate("e", 91, 89, scope="sports")]
    selected = growth.diversify(items, "evening")
    assert selected[0]["title"] == "series"
