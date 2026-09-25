from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_agent_trend_radar_v8 as growth


def candidate() -> dict:
    return {
        "title": "Europa baut neue KI-Infrastruktur",
        "trend_scope": "technology_ai",
        "criteria": {
            "aktualitaet": 96,
            "viralitaet": 92,
            "tayvoriq_passung": 94,
            "quellenqualitaet": 98,
            "visuell": 90,
        },
        "audience_growth_v3": {
            "subscriber_conversion_score": 88,
            "returning_viewer_score": 90,
            "continuation_score": 86,
            "hook_strength_score": 84,
        },
        "source_context": {
            "fallback_editorial_answers": {
                "what_happened": "Europa erweitert seine Recheninfrastruktur für neue KI-Systeme deutlich.",
                "why_happening": "Weil mehr Rechenleistung strategische Abhängigkeiten und Entwicklungstempo beeinflusst.",
                "who_is_affected": "Betroffen sind Entwickler, Unternehmen und europäische Forschungsstandorte.",
                "personal_impact": "Für dich können europäische KI-Dienste dadurch schneller verfügbar werden.",
                "action_now": "Beobachte, welche Anbieter die neue Infrastruktur tatsächlich nutzen.",
            }
        },
    }


def test_v5_score_uses_existing_audience_signals_without_weakening_quality() -> None:
    report = growth._retention_v5(
        candidate(),
        {
            "content_angle": "Warum Europas neue KI-Rechenleistung strategisch wichtig wird",
            "why_now": "Die Infrastruktur wurde jetzt angekündigt.",
            "novelty_score": 91,
            "recommended_cta_type": "EXPERTISE",
            "risk_flags": [],
        },
    )

    expected = round(
        .30 * 92
        + .20 * 94
        + .15 * 91
        + .15 * 90
        + .10 * 86
        + .10 * 88
    )
    assert report["trend_selection_score"] == expected
    assert report["return_viewer_score"] == 90
    assert report["follow_conversion_potential"] == 88
    assert report["evidence_strength"] == 98
    assert report["quality_gates_weakened"] is False


def test_series_cta_without_real_continuation_is_rejected() -> None:
    report = growth._retention_v5(
        candidate(),
        {
            "novelty_score": 90,
            "recommended_cta_type": "SERIES",
            "proposed_series_id": "ki-60",
            "proposed_series_name": "KI in 60 Sekunden",
            "next_episode_candidate": "",
        },
    )

    assert report["recommended_cta_type"] == "IDENTITY"
    assert "SERIES_CTA_WITHOUT_REAL_CONTINUATION_REJECTED" in report["risk_flags"]


def test_real_series_proposal_can_keep_series_cta() -> None:
    report = growth._retention_v5(
        candidate(),
        {
            "novelty_score": 93,
            "recommended_cta_type": "SERIES",
            "proposed_series_id": "ki-60",
            "proposed_series_name": "KI in 60 Sekunden",
            "next_episode_candidate": "Welche europäischen Firmen bekommen zuerst Zugriff?",
        },
    )

    assert report["recommended_cta_type"] == "SERIES"
    assert report["proposed_series_id"] == "ki-60"
    assert report["next_episode_candidate"]


def test_missing_novelty_signal_is_neutral_not_rewarded() -> None:
    report = growth._retention_v5(candidate(), {})
    assert report["novelty_score"] == 50
    assert report["novelty_score_source"] == "neutral_default"
    assert "NOVELTY_SIGNAL_MISSING" in report["risk_flags"]
