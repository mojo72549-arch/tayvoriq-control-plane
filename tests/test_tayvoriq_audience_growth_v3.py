from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_agent_trend_radar_v7 as growth


def _candidate(title: str, *, growth_score: int = 90, priority: int = 88, binding: int = 80, fit: int = 90, viral: int = 88) -> dict:
    return {
        "title": title,
        "trend_scope": "technology_ai",
        "score": 90,
        "criteria": {"tayvoriq_passung": fit, "viralitaet": viral},
        "growth_v2": {"growth_score": growth_score, "priority_score": priority, "binding_score": binding},
        "source_context": {
            "fallback_editorial_answers": {
                "what_happened": "Deutsche Gerichte erhalten immer mehr lange Schriftsätze aus KI-Werkzeugen.",
                "why_happening": "Weil KI Texte schnell erzeugt, reichen Menschen deutlich mehr Material ein.",
                "who_is_affected": "Richter, Kläger und Verwaltungen müssen zusätzliche Dokumente prüfen und einordnen.",
                "personal_impact": "Für dich können Verfahren dadurch langsamer und öffentliche Abläufe teurer werden.",
                "action_now": "Beobachte, wie Gerichte Regeln für KI-generierte Schriftsätze künftig verschärfen.",
            }
        },
    }


def test_audience_report_rewards_followable_repeatable_topic() -> None:
    candidate = _candidate("Warum KI deutsche Gerichte plötzlich mit tausenden Seiten überfordert")
    report = growth._audience_report(candidate)
    assert report["subscriber_conversion_score"] >= 80
    assert report["returning_viewer_score"] >= 80
    assert report["continuation_score"] >= 68
    assert report["selection_priority_score"] >= 80


def test_prediction_never_enables_paid_spend() -> None:
    candidate = _candidate("KI verändert Deutschlands Gerichte")
    report = growth._audience_report(candidate)
    assert report["promotion_requires_observed_performance"] is True
    assert report["paid_boost_auto_enabled"] is False


def test_low_growth_never_becomes_promotion_candidate() -> None:
    candidate = _candidate("KI verändert Deutschlands Gerichte", growth_score=79)
    report = growth._audience_report(candidate)
    assert report["promotion_test_candidate"] is False
