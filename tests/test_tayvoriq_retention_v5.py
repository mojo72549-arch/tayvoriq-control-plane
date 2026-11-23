from __future__ import annotations

import copy
import json
import sys
from argparse import Namespace
from datetime import datetime
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
    trend.update(
        primary_hook='Europa plant deutlich mehr KI-Rechenleistung für Forschende und Unternehmen.',
        explanation_core='Mehr Rechenkapazität verkürzt Forschungsschleifen, weil KI-Modelle parallel trainiert werden können und Teams weniger lange auf verfügbare Systeme warten.',
        practical_relevance='Das beeinflusst, wie schnell Forschende und Unternehmen neue KI-Dienste entwickeln können.',
    )
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


def test_v5_state_machine_allows_local_repair_but_not_publish_jump():
    assert v5.advance_lifecycle("PREFLIGHT_PASSED", "RETENTION_CONTRACT_LOCKED") == "RETENTION_CONTRACT_LOCKED"
    assert v5.advance_lifecycle("RENDER_AVAILABLE", "LOCAL_REPAIR_RUNNING") == "LOCAL_REPAIR_RUNNING"
    assert v5.advance_lifecycle("LOCAL_REPAIR_RUNNING", "RENDER_AVAILABLE") == "RENDER_AVAILABLE"
    with pytest.raises(ValueError, match="ILLEGAL_V5_STATE_TRANSITION"):
        v5.advance_lifecycle("APPROVED", "COMPLETED")


@pytest.fixture
def raw_trend():
    return {
        "title": "Goldmedaillen entscheiden die Rangfolge bei der Leichtathletik-EM",
        "trend_scope": "sports",
        "regional_relevance": "germany",
        "criteria": dict.fromkeys(("aktualitaet", "viralitaet", "tayvoriq_passung", "quellenqualitaet", "visuell"), 95),
        "content_angle": "Wie die Medaillentabelle die Teams sortiert",
        "primary_hook": "Wie kann ein Team mit weniger Medaillen trotzdem vorne liegen?",
        "viewer_question": "Warum reicht die Medaillensumme für Rang eins nicht aus?",
        "explanation_core": "Die Medaillentabelle sortiert zunächst nach Gold, danach bei gleicher Goldzahl nach Silber und schließlich Bronze.",
        "surprise_or_reframe": "Ein Team mit vielen Podestplätzen kann deshalb trotzdem unter einer kleineren Delegation landen.",
        "practical_relevance": "So kannst du Platzierungen im Fernsehen auch bei widersprüchlich wirkenden Summen einordnen.",
        "follow_reason": "TAYVORIQ erklärt, wie Regeln die Ergebnisse deutscher Sportteams prägen.",
        "cta_type": "EXPERTISE",
        "cta_text": "Bei TAYVORIQ erfährst du, welche Regeln hinter den Ergebnissen deutscher Sportteams stehen.",
        "open_loop_status": "NONE",
        "sources": [
            {"publisher": "A", "url": "https://a.example/em", "supports": "In der Rangliste zählen Goldmedaillen zuerst."},
            {"publisher": "B", "url": "https://b.example/tabelle", "supports": "Die Rangliste wird bei gleicher Goldzahl nach Silber sortiert."},
        ],
        "fallback_editorial_answers": {
            "what_happened": "Deutschland gewinnt bei der EM 21 Medaillen und belegt Rang drei.",
            "why_happening": "Die Briten liegen vorn, weil Goldmedaillen in der Rangliste Vorrang haben.",
            "who_is_affected": "Das deutsche Leichtathletik-Team und seine Fans.",
            "personal_impact": "Für dich ändert die Rangfolge, wie du den direkten Vergleich bewertest.",
            "action_now": "Prüfe bei der Medaillentabelle zuerst die Goldmedaillen.",
        },
        "cinematic_brief": {
            "story_structure": "MECHANISM",
            "hook_answer": "Die Tabelle sortiert zuerst nach Goldmedaillen.",
            "opening_visual": {"type": "DATA_GRAPHIC", "subject": "Zwei Zeilen der Medaillentabelle", "purpose": "Der Goldvorsprung erklärt die Rangfolge."},
        },
    }


def test_live_radar_prompt_requests_cinematic_brief():
    import tayvoriq_agent_trend_radar_v8 as radar

    assert radar.base.CINEMATIC_BRIEF_INSTRUCTIONS in radar.prompt_for("morning", datetime(2026, 11, 23))


@pytest.mark.parametrize("invalid_brief", [None, {"opening_visual": []}, {"story_structure": "MECHANISM", "opening_visual": {"type": "FAKE_EVENT"}}])
def test_invalid_or_absent_brief_keeps_existing_candidate_contract(raw_trend, invalid_brief):
    import tayvoriq_agent_trend_radar_v8 as radar

    raw_trend["cinematic_brief"] = invalid_brief
    candidate = radar.base.normalized_candidate(raw_trend, "2026-11-23T06:00:00Z")
    assert candidate is not None
    assert "cinematic_brief" not in candidate["source_context"]


def test_brief_does_not_compensate_for_missing_source(raw_trend):
    import tayvoriq_agent_trend_radar_v8 as radar

    raw_trend["sources"].pop()
    assert radar.base.normalized_candidate(raw_trend, "2026-11-23T06:00:00Z") is None


def test_cinematic_brief_is_bound_to_the_approved_request(raw_trend, tmp_path):
    import tayvoriq_agent_trend_radar_v8 as radar
    import tayvoriq_orchestration_contract as contract

    now = "2026-11-23T06:00:00Z"
    raw_trend["cinematic_brief"]["opening_visual"]["license_verified"] = True
    candidate = radar.base.normalized_candidate(raw_trend, now)
    candidate["id"] = "1"
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({"selection_id": "test-selection", "trends": [candidate]}), encoding="utf-8")
    contract.create_from_telegram(Namespace(
        trend_id="1", selection_id="test-selection", message_id="999", trend_request=str(selection),
        payload_topic="", approved_at=now, out_dir=str(tmp_path),
    ))
    request = contract.read_json(tmp_path / "telegram-999-trend-1.json")
    brief = request["source_context"]["cinematic_brief"]
    assert brief["hook_answer"] == raw_trend["cinematic_brief"]["hook_answer"]
    assert brief["opening_visual"] == {"type": "DATA_GRAPHIC", "subject": "Zwei Zeilen der Medaillentabelle", "purpose": "Der Goldvorsprung erklärt die Rangfolge."}
    brief["opening_visual"]["subject"] = "Ausgetauschte Einstellung"
    with pytest.raises(SystemExit, match="source_context_sha256 mismatch"):
        contract.validate(request)
