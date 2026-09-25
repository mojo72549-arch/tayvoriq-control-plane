from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_orchestration_contract as contract


def retention_v5(**overrides) -> dict:
    value = {
        "schema": "tayvoriq-retention-v5",
        "category": "AI",
        "content_angle": "Warum Europas KI-Infrastruktur strategisch relevant wird",
        "why_now": "Die neue Infrastruktur wurde aktuell angekündigt.",
        "evidence_strength": 98,
        "viral_potential": 92,
        "novelty_score": 90,
        "tayvoriq_fit": 94,
        "series_fit_score": 86,
        "return_viewer_score": 90,
        "follow_conversion_potential": 88,
        "open_loop_potential": 85,
        "next_episode_candidate": None,
        "proposed_series_id": None,
        "proposed_series_name": None,
        "recommended_cta_type": "IDENTITY",
        "risk_flags": [],
        "trend_selection_score": 91,
        "quality_gates_weakened": False,
    }
    value.update(overrides)
    return value


def source_context() -> dict:
    return {
        "independent_news_count": 2,
        "quality_gates_weakened": False,
        "sources": [
            {"publisher": "Source A", "url": "https://example.com/a", "supports": "Fact A"},
            {"publisher": "Source B", "url": "https://example.com/b", "supports": "Fact B"},
        ],
        "fallback_editorial_answers": {
            "what_happened": "Eine neue KI-Infrastruktur wurde in Europa angekündigt.",
            "why_happening": "Weil Europa mehr eigene Rechenleistung für KI benötigt.",
            "who_is_affected": "Betroffen sind Entwickler, Unternehmen und Forschungseinrichtungen.",
            "personal_impact": "Für dich können dadurch neue europäische KI-Dienste entstehen.",
            "action_now": "Beobachte, welche Anbieter die Infrastruktur zuerst nutzen.",
        },
    }


def test_create_from_telegram_binds_retention_contract(tmp_path: Path, capsys) -> None:
    selection = {
        "selection_id": "selection-v5",
        "selected_trend_id": None,
        "trends": [{
            "id": "1",
            "title": "Europa baut neue KI-Infrastruktur",
            "trend_scope": "technology_ai",
            "source_context": source_context(),
            "retention_v5": retention_v5(),
        }],
    }
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(selection), encoding="utf-8")
    out_dir = tmp_path / "requests"

    args = argparse.Namespace(
        trend_request=str(selection_path),
        trend_id="1",
        selection_id="selection-v5",
        message_id="1234",
        payload_topic="Europa baut neue KI-Infrastruktur",
        approved_at="2026-09-25T10:00:00+00:00",
        out_dir=str(out_dir),
    )
    contract.create_from_telegram(args)
    capsys.readouterr()

    request = json.loads((out_dir / "telegram-1234-trend-1.json").read_text(encoding="utf-8"))
    assert request["retention_contract"]["schema"] == "tayvoriq-retention-v5"
    assert request["retention_contract"]["follow_conversion_potential"] == 88
    assert request["retention_contract_sha256"]
    contract.validate(request, require_claimable=True)


def test_retention_tamper_breaks_immutable_request_hash(tmp_path: Path) -> None:
    now = contract.utc_now()
    retention = retention_v5()
    raw = json.dumps(retention, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = {
        "request_id": "test-v5-1",
        "status": "APPROVED",
        "trend_id": "1",
        "topic": "Topic",
        "trend_scope": "technology_ai",
        "language": "Deutsch",
        "platform": "youtube_tiktok",
        "target_duration": 35,
        "approval_required_before_youtube_publish": True,
        "approval_key": "test:v5",
        "mode": "full",
        "approved_at": now,
        "retention_contract": retention,
        "retention_contract_sha256": hashlib.sha256(raw).hexdigest(),
        "state_history": [{"state": "APPROVED", "at": now, "actor": "test"}],
    }
    request["contract_sha256"] = contract.contract_hash(request)
    contract.validate(request)

    request["retention_contract"]["follow_conversion_potential"] = 1
    with pytest.raises(SystemExit, match="retention_contract_sha256 mismatch"):
        contract.validate(request)


def test_series_cta_requires_real_next_episode() -> None:
    now = contract.utc_now()
    retention = retention_v5(
        recommended_cta_type="SERIES",
        proposed_series_id="ki-60",
        proposed_series_name="KI in 60 Sekunden",
        next_episode_candidate=None,
    )
    raw = json.dumps(retention, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = {
        "request_id": "test-v5-2",
        "status": "APPROVED",
        "trend_id": "1",
        "topic": "Topic",
        "trend_scope": "technology_ai",
        "language": "Deutsch",
        "platform": "youtube_tiktok",
        "target_duration": 35,
        "approval_required_before_youtube_publish": True,
        "approval_key": "test:v5:2",
        "mode": "full",
        "approved_at": now,
        "retention_contract": retention,
        "retention_contract_sha256": hashlib.sha256(raw).hexdigest(),
        "state_history": [{"state": "APPROVED", "at": now, "actor": "test"}],
    }
    request["contract_sha256"] = contract.contract_hash(request)

    with pytest.raises(SystemExit, match="SERIES CTA requires real series"):
        contract.validate(request)


def test_recovery_keeps_sources_and_angle(tmp_path: Path) -> None:
    now = contract.utc_now()
    source = source_context()
    source_raw = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    retention = retention_v5()
    retention_raw = json.dumps(retention, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    story = {
        "schema": "tayvoriq-story-retention-contract-v5",
        "primary_hook": "Europa erweitert seine KI-Rechenleistung.",
        "viewer_question": retention["content_angle"],
        "explanation_core": "Mehr Rechenleistung beeinflusst strategische Abhängigkeiten.",
        "surprise_or_reframe": "Entscheidend ist auch, wer Zugriff erhält.",
        "practical_relevance": "Neue europäische KI-Dienste können schneller entstehen.",
        "follow_reason": "TAYVORIQ liefert weitere verifizierte KI-Entwicklungen mit verständlicher Einordnung statt leerem Hype.",
        "open_loop": "",
        "open_loop_status": "NONE",
        "queue_status": None,
        "cta_type": "IDENTITY",
        "cta_text": {
            "youtube_shorts": "Abonniere TAYVORIQ, wenn du verifizierte KI-Entwicklungen verständlich und ohne Hype verfolgen willst.",
            "tiktok": "Folge TAYVORIQ, wenn du verifizierte KI-Entwicklungen verständlich und ohne Hype verfolgen willst.",
        },
        "cta_variant": {"youtube_shorts": 0, "tiktok": 0},
        "series_id": None,
        "series_name": None,
        "episode_number": None,
        "next_episode_candidate": None,
        "continuity_hook": None,
        "follow_conversion_gate": "PASS",
        "quality_gates_weakened": False,
    }
    story_raw = json.dumps(story, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = {
        "request_id": "test-v5-recovery",
        "status": "APPROVED",
        "trend_id": "1",
        "topic": "Europa baut neue KI-Infrastruktur",
        "trend_scope": "technology_ai",
        "language": "Deutsch",
        "platform": "youtube_tiktok",
        "target_duration": 35,
        "approval_required_before_youtube_publish": True,
        "approval_key": "test:v5:recovery",
        "mode": "full",
        "approved_at": now,
        "source_context": source,
        "source_context_sha256": hashlib.sha256(source_raw).hexdigest(),
        "retention_contract": retention,
        "retention_contract_sha256": hashlib.sha256(retention_raw).hexdigest(),
        "story_retention_contract": story,
        "story_retention_contract_sha256": hashlib.sha256(story_raw).hexdigest(),
        "state_history": [{"state": "APPROVED", "at": now, "actor": "test"}],
    }
    request["contract_sha256"] = contract.contract_hash(request)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")

    args = argparse.Namespace(
        path=str(path),
        to="DISPATCHING",
        actor="recovery-test",
        meta=["recovery_generation=1"],
    )
    contract.transition(args)

    recovered = json.loads(path.read_text(encoding="utf-8"))
    assert recovered["source_context_sha256"] == request["source_context_sha256"]
    assert recovered["retention_contract"]["content_angle"] == retention["content_angle"]
    assert recovered["retention_contract_sha256"] == request["retention_contract_sha256"]
    assert recovered["story_retention_contract_sha256"] == request["story_retention_contract_sha256"]
    assert recovered["contract_sha256"] == request["contract_sha256"]
