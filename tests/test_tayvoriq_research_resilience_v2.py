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
                            {"publisher": "x", "url": "https://a.example/x", "supports": "x"},
                            {"publisher": "x", "url": "https://a.example/x", "supports": "x"},
                        ],
                        "fallback_editorial_answers": {"what_happened": "x", "why_happening": "x", "who_is_affected": "x", "personal_impact": "x", "action_now": "x"},
                    }]
                })
            }
        }]
    }
    monkeypatch.setattr(http, "post_json", lambda *args, **kwargs: (fake, {}))
    monkeypatch.setattr(http, "retry", lambda label, call, attempts: call())
    data, chunks, _ = hf.structure("editorial", "token", records)
    assert data["candidates"][0]["sources"] == []
    assert chunks == []


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
