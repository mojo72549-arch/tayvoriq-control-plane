from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_retention_v5 as v5


def base_contract():
    return {
        "request_id": "telegram-999-trend-1",
        "topic": "Europa baut einen neuen KI-Supercomputer",
        "source_context_sha256": "abc123",
        "content_angle": "Warum neue Rechenleistung Europas KI-Forschung verändert",
        "series_id": None,
        "series_name": None,
        "episode_id": None,
        "episode_number": None,
        "continuity_hook": None,
        "next_episode_candidate": None,
        "primary_hook": "Europa plant deutlich mehr KI-Rechenleistung.",
        "viewer_question": "Warum ist das für Europas KI-Entwicklung wichtig?",
        "explanation_core": "Mehr Rechenleistung verkürzt Training und Forschungsschleifen.",
        "surprise_or_reframe": "Entscheidend ist nicht nur der Chip, sondern wer Zugriff erhält.",
        "practical_relevance": "Das beeinflusst Forschung, Unternehmen und neue KI-Dienste.",
        "follow_reason": "Wenn du Europas KI-Infrastruktur verständlich verfolgt haben willst, folge TAYVORIQ.",
        "open_loop": "Der nächste entscheidende Punkt ist, wer die Kapazität tatsächlich nutzen darf.",
        "open_loop_status": "SOFT",
        "cta_type": "EXPERTISE",
        "cta_text": "Wenn du Europas KI-Infrastruktur verständlich verfolgt haben willst, folge TAYVORIQ.",
    }


def base_trend():
    c = base_contract()
    return {
        "title": c["topic"],
        "content_angle": c["content_angle"],
        "criteria": {"viralitaet": 90, "tayvoriq_passung": 95},
        "viral_potential": 90,
        "tayvoriq_fit": 95,
        "novelty_score": 88,
        "series_fit_score": 70,
        "return_viewer_score": 84,
        "follow_conversion_potential": 82,
        "open_loop_potential": 80,
        "proposed_series_id": "",
        "proposed_series_name": "",
        "next_episode_candidate": "",
        "recommended_cta_type": c["cta_type"],
        "primary_hook": c["primary_hook"],
        "viewer_question": c["viewer_question"],
        "explanation_core": c["explanation_core"],
        "surprise_or_reframe": c["surprise_or_reframe"],
        "practical_relevance": c["practical_relevance"],
        "follow_reason": c["follow_reason"],
        "open_loop": c["open_loop"],
        "open_loop_status": c["open_loop_status"],
        "cta_type": c["cta_type"],
        "cta_text": c["cta_text"],
        "source_context": {
            "independent_news_count": 2,
            "sources": [{"publisher": "A", "url": "https://a.example", "supports": "x"}, {"publisher": "B", "url": "https://b.example", "supports": "y"}],
        },
    }


def test_trend_selection_score_exact_weights():
    trend = base_trend()
    enriched = v5.apply_trend_contract(trend, strict=True)
    expected = round(.30*90 + .20*95 + .15*88 + .15*84 + .10*70 + .10*82)
    assert enriched["trend_selection_score"] == expected


def test_generic_cta_is_rejected():
    c = base_contract()
    c["cta_text"] = "Bitte abonnieren."
    result = v5.evaluate_follow_conversion(c)
    assert result["result"] == "REWRITE_REQUIRED"
    assert result["repair"] == "CTA_REWRITE_REQUIRED"


def test_false_hard_open_loop_is_rejected():
    c = base_contract()
    c["open_loop_status"] = "HARD"
    c["open_loop"] = "Morgen zeigen wir den nächsten Teil."
    c["next_episode_candidate"] = None
    result = v5.evaluate_follow_conversion(c)
    assert result["result"] == "REWRITE_REQUIRED"
    assert result["repair"] == "OPEN_LOOP_REWRITE_REQUIRED"


def test_topic_specific_follow_reason_passes():
    result = v5.evaluate_follow_conversion(base_contract())
    assert result["result"] == "PASS"


def test_recovery_keeps_sources_and_angle():
    before = base_contract()
    after = copy.deepcopy(before)
    after["cta_text"] = "Für verständliche KI-Infrastruktur-Updates: folge TAYVORIQ."
    v5.assert_repair_preserves(before, after)
    broken = copy.deepcopy(after)
    broken["content_angle"] = "anderer Winkel"
    with pytest.raises(ValueError, match="content_angle"):
        v5.assert_repair_preserves(before, broken)


def test_series_number_requires_real_series():
    trend = base_trend()
    trend["episode_number"] = 12
    trend["series_history_exists"] = False
    with pytest.raises(ValueError, match="episode_number_requires_real_series"):
        v5.apply_trend_contract(trend, strict=True)


def test_repeated_cta_wording_is_rotated():
    c = base_contract()
    result = v5.evaluate_follow_conversion(c, previous_cta=c["cta_text"])
    assert result["result"] == "REWRITE_REQUIRED"
    assert result["repair"] == "CTA_REWRITE_REQUIRED"
    assert "repeated_cta_wording" in result["issues"]


def test_sensitive_story_can_skip_cta():
    c = base_contract()
    c["cta_text"] = ""
    result = v5.evaluate_follow_conversion(c, sensitive_story=True)
    assert result["result"] == "NOT_APPLICABLE"


def test_no_publish_before_review():
    request = {"approval_required_before_youtube_publish": True}
    assert v5.publish_allowed(request, review_approved=False) is False
    assert v5.publish_allowed(request, review_approved=True) is True
