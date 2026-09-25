from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_retention_contract_v5 as retention


def base_retention(**overrides) -> dict:
    value = {
        "schema": "tayvoriq-retention-v5",
        "category": "AI",
        "content_angle": "Warum Europas neue KI-Rechenleistung strategisch wichtig wird",
        "why_now": "Die Infrastruktur wurde aktuell angekündigt.",
        "evidence_strength": 98,
        "viral_potential": 92,
        "novelty_score": 91,
        "tayvoriq_fit": 94,
        "series_fit_score": 86,
        "return_viewer_score": 90,
        "follow_conversion_potential": 88,
        "open_loop_potential": 84,
        "next_episode_candidate": None,
        "proposed_series_id": None,
        "proposed_series_name": None,
        "recommended_cta_type": "EXPERTISE",
        "risk_flags": [],
        "trend_selection_score": 91,
        "quality_gates_weakened": False,
    }
    value.update(overrides)
    return value


def source_context(**overrides) -> dict:
    value = {
        "fallback_editorial_answers": {
            "what_happened": "Europa erweitert seine Recheninfrastruktur für neue KI-Systeme deutlich.",
            "why_happening": "Weil mehr Rechenleistung strategische Abhängigkeiten und Entwicklungstempo beeinflusst.",
            "who_is_affected": "Betroffen sind Entwickler, Unternehmen und europäische Forschungsstandorte.",
            "personal_impact": "Für dich können europäische KI-Dienste dadurch schneller verfügbar werden.",
            "action_now": "Beobachte, welche Anbieter die neue Infrastruktur tatsächlich nutzen.",
        },
        "story_first_script_body": (
            "Europa baut seine KI-Rechenleistung deutlich aus. "
            "Entscheidend ist nicht nur die Maschine, sondern wer sie nutzen darf. "
            "Damit verändert sich Europas technologische Abhängigkeit."
        ),
        "factual_guardrails": {
            "uncertainty_note": "Unabhängige Leistungsdaten stehen teilweise noch aus."
        },
    }
    value.update(overrides)
    return value


def test_topic_specific_follow_reason_passes() -> None:
    contract = retention.build_story_contract(base_retention(), source_context())
    retention.validate_story_contract(contract)

    assert "KI-Entwicklungen" in contract["follow_reason"]
    assert contract["follow_conversion_gate"] == "PASS"
    assert "verifizierte" in contract["cta_text"]["youtube_shorts"]
    assert "verifizierte" in contract["cta_text"]["tiktok"]


def test_generic_cta_is_rejected() -> None:
    contract = retention.build_story_contract(base_retention(), source_context())
    broken = copy.deepcopy(contract)
    broken["cta_text"]["youtube_shorts"] = "Abonniere TAYVORIQ."

    with pytest.raises(ValueError, match="STORY_RETENTION_PLATFORM_CTA_WORDS"):
        retention.validate_story_contract(broken)


def test_false_hard_open_loop_is_rejected() -> None:
    contract = retention.build_story_contract(base_retention(), source_context())
    broken = copy.deepcopy(contract)
    broken["open_loop_status"] = "HARD"
    broken["open_loop"] = "Morgen zeigen wir den nächsten Teil."
    broken["queue_status"] = None
    broken["series_id"] = "ki-60"
    broken["series_name"] = "KI in 60 Sekunden"
    broken["next_episode_candidate"] = "Wer erhält zuerst Zugriff?"

    with pytest.raises(ValueError, match="STORY_RETENTION_FALSE_HARD_OPEN_LOOP"):
        retention.validate_story_contract(broken)


def test_series_number_requires_real_series() -> None:
    contract = retention.build_story_contract(base_retention(), source_context())
    broken = copy.deepcopy(contract)
    broken["episode_number"] = 3
    broken["series_id"] = None
    broken["series_name"] = None

    with pytest.raises(ValueError, match="STORY_RETENTION_EPISODE_WITHOUT_SERIES"):
        retention.validate_story_contract(broken)


def test_repeated_cta_wording_is_rotated() -> None:
    first = retention.build_story_contract(base_retention(), source_context())
    recent = list(first["cta_text"].values())
    second = retention.build_story_contract(
        base_retention(),
        source_context(),
        recent_ctas=recent,
    )

    assert second["cta_text"]["youtube_shorts"] != first["cta_text"]["youtube_shorts"]
    assert second["cta_text"]["tiktok"] != first["cta_text"]["tiktok"]
    retention.validate_story_contract(second)


def test_hard_open_loop_requires_real_queued_series() -> None:
    series_source = source_context(
        series_context={
            "series_id": "ki-60",
            "series_name": "KI in 60 Sekunden",
            "episode": 2,
            "queue_status": "QUEUED",
            "next_episode_candidate": "Welche Unternehmen erhalten zuerst Zugriff?",
            "continuity_hook": "Wer die Infrastruktur tatsächlich nutzen darf.",
        }
    )
    contract = retention.build_story_contract(
        base_retention(
            proposed_series_id="ki-60",
            proposed_series_name="KI in 60 Sekunden",
            next_episode_candidate="Welche Unternehmen erhalten zuerst Zugriff?",
            recommended_cta_type="SERIES",
        ),
        series_source,
    )

    assert contract["open_loop_status"] == "HARD"
    assert contract["cta_type"] == "SERIES"
    assert contract["episode_number"] == 2
    assert contract["queue_status"] == "QUEUED"
    retention.validate_story_contract(contract)


def test_unqueued_series_proposal_is_soft_not_fake_hard() -> None:
    contract = retention.build_story_contract(
        base_retention(
            proposed_series_id="ki-60",
            proposed_series_name="KI in 60 Sekunden",
            next_episode_candidate="Welche Unternehmen erhalten zuerst Zugriff?",
            recommended_cta_type="SERIES",
        ),
        source_context(),
    )

    assert contract["open_loop_status"] == "SOFT"
    assert contract["cta_type"] != "SERIES"
    assert "Morgen zeigen wir" not in contract["open_loop"]
