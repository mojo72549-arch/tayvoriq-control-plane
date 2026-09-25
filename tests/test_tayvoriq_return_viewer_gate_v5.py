from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_return_viewer_gate_v5 as gate


def request_contract() -> dict:
    story = {
        "schema": "tayvoriq-story-retention-contract-v5",
        "primary_hook": "Europa erweitert seine KI-Rechenleistung.",
        "viewer_question": "Warum das strategisch wichtig wird",
        "explanation_core": "Mehr Rechenleistung beeinflusst Abhängigkeiten.",
        "surprise_or_reframe": "Entscheidend ist auch der Zugang.",
        "practical_relevance": "Neue europäische Dienste können schneller entstehen.",
        "follow_reason": "TAYVORIQ liefert weitere verifizierte KI-Entwicklungen mit verständlicher Einordnung statt leerem Hype.",
        "open_loop": "Wir beobachten, welcher verifizierte nächste Schritt diese Entwicklung tatsächlich verändert.",
        "open_loop_status": "SOFT",
        "queue_status": None,
        "cta_type": "EXPERTISE",
        "cta_text": {
            "youtube_shorts": "Abonniere TAYVORIQ für verifizierte KI-Entwicklungen mit verständlicher Einordnung statt Hype.",
            "tiktok": "Folge TAYVORIQ für verifizierte KI-Entwicklungen mit verständlicher Einordnung statt Hype.",
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
    return {
        "request_id": "test-return-viewer",
        "retention_contract": {
            "schema": "tayvoriq-retention-v5",
            "return_viewer_score": 90,
        },
        "story_retention_contract": story,
    }


def job_for(request: dict) -> dict:
    story = request["story_retention_contract"]
    variants = {}
    for platform in ("youtube_shorts", "tiktok"):
        variants[platform] = {
            "text_package": {
                "cta": story["cta_text"][platform],
                "platform_cta_contract": {
                    "source_bound_viewer_value": True,
                    "viewer_value": story["follow_reason"],
                    "next_video_bridge": story["open_loop"],
                    "quality_gates_weakened": False,
                    "visible_script_audio_overlay_same_source": True,
                },
            }
        }
    return {"quality_report": {"passed": True}, "variants": variants}


def test_return_viewer_gate_passes_only_final_source_bound_platform_output() -> None:
    request = request_contract()
    report = gate.evaluate(request, job_for(request))
    assert report["status"] == "PASS"
    assert report["platforms"]["youtube_shorts"]["passed"] is True
    assert report["platforms"]["tiktok"]["passed"] is True
    assert report["quality_gates_weakened"] is False


def test_return_viewer_gate_detects_final_cta_drift() -> None:
    request = request_contract()
    job = job_for(request)
    job["variants"]["tiktok"]["text_package"]["cta"] = "Folge diesem Kanal für mehr."

    report = gate.evaluate(request, job)
    assert report["status"] == "IMPROVE"
    assert "tiktok:cta_exact_match" in report["issues"]


def test_return_viewer_gate_requires_quality_first() -> None:
    request = request_contract()
    job = job_for(request)
    job["quality_report"]["passed"] = False

    with pytest.raises(ValueError, match="RETURN_VIEWER_REQUIRES_PASSED_PUBLICATION_QUALITY"):
        gate.evaluate(request, job)


def test_no_publish_before_human_review() -> None:
    golden = Path(".github/workflows/tayvoriq-deliver-video-now.yml").read_text(encoding="utf-8")
    approved = Path(".github/workflows/tayvoriq-auto-publish-approved.yml").read_text(encoding="utf-8")

    assert "GP-70 Return Viewer Gate" in golden
    assert "Send Telegram review" in golden
    assert "youtube_publish_approved.py" not in golden
    assert "platform_upload_performed" not in golden
    assert "str(data.get('status') or '') == 'APPROVED'" in approved
    assert "Upload approved YouTube master publicly" in approved
