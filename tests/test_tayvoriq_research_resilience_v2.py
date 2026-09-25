from __future__ import annotations

import json
import sys
import urllib.error
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_agent_research_http_v2 as http
import tayvoriq_agent_research_resilience_v2 as resilience
import tayvoriq_agent_hf_v2 as hf


def _http_error(code: int, **headers: str) -> urllib.error.HTTPError:
    msg = Message()
    for key, value in headers.items():
        msg[key.replace("_", "-")] = value
    return urllib.error.HTTPError("https://example.invalid", code, "test", msg, None)


def test_429_is_transient_and_rate_headers_are_preserved() -> None:
    exc = _http_error(
        429,
        Retry_After="17",
        X_Ratelimit_Remaining_Requests="0",
        X_Ratelimit_Reset_Requests="17s",
    )
    assert http.is_transient(exc) is True
    headers = http.rate_headers(exc)
    assert headers["retry-after"] == "17"
    assert headers["x-ratelimit-remaining-requests"] == "0"
    assert headers["x-ratelimit-reset-requests"] == "17s"


def test_hf_requires_two_exact_independent_source_urls(monkeypatch) -> None:
    records = [
        {"title": "A", "context": "same current event", "url": "https://a.example/x", "domain": "a.example"},
        {"title": "B", "context": "same current event", "url": "https://b.example/y", "domain": "b.example"},
    ] * 4

    fake = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "candidates": [{
                        "title": "Test",
                        "category": "science_future",
                        "trend_scope": "science_future",
                        "regional_relevance": "europe",
                        "criteria": {"aktualitaet": 90, "viralitaet": 90, "tayvoriq_passung": 90, "quellenqualitaet": 90, "visuell": 90},
                        "sources": [
                            {"source_id": "S001", "supports": "x"},
                            {"source_id": "S003", "supports": "x"},
                        ],
                        "fallback_editorial_answers": {"what_happened": "x", "why_happening": "x", "who_is_affected": "x", "personal_impact": "x", "action_now": "x"},
                    }]
                })
            }
        }]
    }
    monkeypatch.setattr(http, "post_json", lambda *args, **kwargs: (fake, {}))
    monkeypatch.setattr(http, "retry", lambda label, call, attempts: call())
    try:
        hf.structure("editorial", "token", records)
    except RuntimeError as exc:
        assert "HF source contract insufficient" in str(exc)
    else:
        raise AssertionError("same-domain HF evidence must force the next source pool")


def test_hf_fallback_prompt_is_v5_native_and_keeps_cross_domain_candidates(monkeypatch) -> None:
    records = [
        {"title": "A1", "context": "same current event alpha", "url": "https://a.example/1", "domain": "a.example"},
        {"title": "B1", "context": "same current event alpha", "url": "https://b.example/1", "domain": "b.example"},
        {"title": "A2", "context": "same current event beta", "url": "https://a.example/2", "domain": "a.example"},
        {"title": "B2", "context": "same current event beta", "url": "https://b.example/2", "domain": "b.example"},
    ] * 2
    captured = {}

    def candidate(title: str, first: str, second: str) -> dict:
        return {
            "title": title,
            "content_angle": "Warum dieses Ereignis jetzt wichtig wird",
            "category": "technology_ai",
            "trend_scope": "technology_ai",
            "regional_relevance": "global",
            "criteria": {"aktualitaet": 90, "viralitaet": 90, "tayvoriq_passung": 90, "quellenqualitaet": 90, "visuell": 90},
            "viral_potential": 90,
            "tayvoriq_fit": 90,
            "novelty_score": 88,
            "series_fit_score": 70,
            "return_viewer_score": 84,
            "follow_conversion_potential": 82,
            "open_loop_potential": 70,
            "proposed_series_id": "",
            "proposed_series_name": "",
            "next_episode_candidate": "",
            "recommended_cta_type": "CURIOSITY",
            "primary_hook": "Das verändert gerade mehr als es zuerst aussieht.",
            "viewer_question": "Was bedeutet das konkret für Nutzer?",
            "explanation_core": "Zwei unabhängige Quellen beschreiben denselben aktuellen Vorgang.",
            "surprise_or_reframe": "Entscheidend ist weniger die Schlagzeile als die direkte Folge.",
            "practical_relevance": "Für Nutzer entsteht daraus ein klarer praktischer Effekt.",
            "follow_reason": "TAYVORIQ ordnet die nächsten bestätigten Entwicklungen verständlich ein.",
            "open_loop": "Die nächste bestätigte Entwicklung bleibt relevant.",
            "open_loop_status": "SOFT",
            "next_episode_queue_status": "",
            "cta_type": "CURIOSITY",
            "cta_text": "Folge TAYVORIQ für die nächste bestätigte Entwicklung zu diesem Thema.",
            "sources": [
                {"source_id": first, "supports": "supported fact"},
                {"source_id": second, "supports": "supported fact"},
            ],
            "fallback_editorial_answers": {
                "what_happened": "Zwei Quellen bestätigen heute denselben neuen technischen Entwicklungsschritt.",
                "why_happening": "Das passiert, weil Anbieter ihre Systeme jetzt breiter verfügbar machen.",
                "who_is_affected": "Betroffen sind vor allem Nutzer digitaler Dienste und Plattformen.",
                "personal_impact": "Für dich kann sich die tägliche Nutzung dadurch spürbar verändern.",
                "action_now": "Prüfe jetzt, ob die neue Funktion bei dir verfügbar ist.",
            },
        }

    fake = {"choices": [{"message": {"content": json.dumps({"candidates": [
        candidate("Alpha", "S001", "S002"),
        candidate("Beta", "S003", "S004"),
    ]})}}]}

    def post_json(url, payload, headers, timeout):
        captured["payload"] = payload
        return fake, {}

    monkeypatch.setattr(http, "post_json", post_json)
    monkeypatch.setattr(http, "retry", lambda label, call, attempts: call())
    data, chunks, _ = hf.structure("editorial", "token", records)
    prompt = captured["payload"]["messages"][1]["content"]
    assert '"content_angle"' in prompt
    assert '"viral_potential"' in prompt
    assert '"follow_conversion_potential"' in prompt
    assert '"cta_text"' in prompt
    assert "naturally mention TAYVORIQ" in prompt
    assert len(data["candidates"]) == 2
    assert len(chunks) == 4
    assert all(len(item["sources"]) == 2 for item in data["candidates"])


def test_all_provider_failure_creates_deferred_marker(monkeypatch, tmp_path) -> None:
    marker = tmp_path / "deferred.json"
    monkeypatch.setattr(resilience, "MARKER", marker)
    monkeypatch.setattr(http, "retry", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("HTTP 429")))
    monkeypatch.setattr(resilience.provider, "groq_browser_then_structure", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("HTTP 429")))
    monkeypatch.setattr(resilience.rss, "source_pool", lambda: [])
    monkeypatch.setattr(resilience.gdelt, "source_pool", lambda: [])
    try:
        resilience.grounded("prompt", "gemini", "groq")
    except RuntimeError as exc:
        assert "RESEARCH_DEFERRED" in str(exc)
    else:
        raise AssertionError("expected deferred failure")
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["status"] == "RESEARCH_DEFERRED"
