from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import tayvoriq_agent_trend_radar_v3 as radar


def _candidate() -> dict:
    return {
        "title": "Warum dieses Ereignis jetzt wichtig wird",
        "category": "science_future",
        "trend_scope": "science_future",
        "regional_relevance": "germany",
        "criteria": {
            "aktualitaet": 80,
            "viralitaet": 80,
            "tayvoriq_passung": 80,
            "quellenqualitaet": 80,
            "visuell": 80,
        },
        "growth_criteria": {
            "hook_strength": 100,
            "retention_potential": 100,
            "follow_conversion_potential": 100,
            "series_fit": 100,
            "share_comment_potential": 100,
            "search_discoverability": 100,
        },
        "sources": [
            {"publisher": "Quelle A", "url": "https://example.com/a", "supports": "Fakt A"},
            {"publisher": "Quelle B", "url": "https://example.org/b", "supports": "Fakt B"},
        ],
        "fallback_editorial_answers": {
            "what_happened": "Etwas ist passiert.",
            "why_happening": "Es gibt einen belegten Grund.",
            "who_is_affected": "Menschen sind betroffen.",
            "personal_impact": "Das kann den Alltag beeinflussen.",
            "action_now": "Beobachte die bestätigte Entwicklung.",
        },
    }


def test_growth_score_changes_final_ranking_without_weakening_editorial_gate() -> None:
    normalized = radar.growth_normalized_candidate(_candidate(), "2026-08-17T00:00:00Z")
    assert normalized is not None
    assert normalized["editorial_score"] == 80
    assert normalized["growth_score"] == 100
    assert normalized["score"] == 88
    assert normalized["score_model"] == "editorial60_growth40_v1"


def test_legacy_series_candidate_keeps_old_score_when_growth_fields_are_absent() -> None:
    raw = _candidate()
    raw.pop("growth_criteria")
    normalized = radar.growth_normalized_candidate(raw, "2026-08-17T00:00:00Z")
    assert normalized is not None
    assert normalized["score"] == 80
    assert normalized["score_model"] == "legacy-editorial-compatible"


def test_growth_candidate_fails_closed_on_extremely_weak_factor() -> None:
    raw = _candidate()
    raw["growth_criteria"]["retention_potential"] = 10
    assert radar.growth_normalized_candidate(raw, "2026-08-17T00:00:00Z") is None
