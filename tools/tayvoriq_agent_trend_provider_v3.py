#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Any, Callable

import tayvoriq_agent_trend_radar_v2 as base

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TRANSIENT_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524}


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return int(exc.code) in TRANSIENT_HTTP_CODES
    text = f"{type(exc).__name__}: {exc}".casefold()
    return any(token in text for token in (
        "429", "too many requests", "rate limit", "timeout", "timed out",
        " 500", " 502", " 503", " 504", " 520", " 522", " 524",
        "temporarily unavailable", "connection reset",
    ))


def _retry_delay(exc: Exception, attempt: int, *, floor: float = 6.0, cap: float = 45.0) -> float:
    if isinstance(exc, urllib.error.HTTPError):
        retry_after = (exc.headers or {}).get("Retry-After")
        if retry_after:
            try:
                return min(cap, max(floor, float(retry_after)))
            except Exception:
                pass
    return min(cap, floor * (2 ** attempt) + random.uniform(0.5, 2.0))


def _run_with_backoff(label: str, call: Callable[[], Any], attempts: int) -> Any:
    errors: list[str] = []
    for attempt in range(attempts):
        try:
            return call()
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt + 1 >= attempts or not _is_transient(exc):
                break
            time.sleep(_retry_delay(exc, attempt))
    raise RuntimeError(f"{label} failed after {len(errors)} attempt(s): " + " | ".join(errors))


def post_groq(payload: dict[str, Any], api_key: str, timeout: int = 180) -> dict[str, Any]:
    def _call() -> dict[str, Any]:
        req = urllib.request.Request(
            GROQ_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "tayvoriq-agent-v3",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    return _run_with_backoff("Groq HTTP request", _call, attempts=2)


def content_of(raw: dict[str, Any]) -> str:
    return str(((((raw.get("choices") or [{}])[0]).get("message") or {}).get("content")) or "").strip()


def groq_browser_then_structure(prompt: str, api_key: str):
    if not api_key:
        raise RuntimeError("GROQ_API_KEY missing")
    research_prompt = f"""
Research CURRENT TAYVORIQ short-video candidates for Germany now.
Use browser search. We need SIX different stories, normally from the last 24 hours (48 hours only if still unfolding).
Morning focus: Germany, Europe, major global stories. Evening focus: Stuttgart/Baden-Württemberg/South Germany plus strong Germany-wide stories.
Audience 16-44, sweet spot 18-34. Prioritize direct relevance, surprise, weather, transport, safety, prices, science, technology, business, mobility, major world developments and sports.
For earthquakes, volcanoes, eclipses, storms, wildfires, floods or similar natural events, include a concise WHY/HOW explanation.
Avoid political advocacy, gossip, rumors, graphic violence and duplicate angles.
For EACH story provide German title, category, one allowed trend scope, regional relevance, five 0-100 scores (aktualitaet, viralitaet, tayvoriq_passung, quellenqualitaet, visuell), EXACTLY TWO independent credible sources with publisher/direct URL/supported fact, and five concise answers: what_happened, why_happening, who_is_affected, personal_impact, action_now.
Do not invent URLs or facts. The next stage converts this to JSON.
Current editorial contract:
{prompt[:3500]}
""".strip()
    search_raw = post_groq({
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": research_prompt}],
        "temperature": 1,
        "max_completion_tokens": 6000,
        "top_p": 1,
        "tool_choice": "required",
        "tools": [{"type": "browser_search"}],
    }, api_key)
    dossier = content_of(search_raw)
    if len(dossier) < 500:
        raise RuntimeError("browser research dossier unexpectedly short")
    structure_prompt = f"""
Convert the dossier below into ONE valid JSON object. Use ONLY facts and URLs already present. Do not add or infer claims.
Schema: {{"candidates":[{{"title":"German headline","category":"...","trend_scope":"technology_ai|business_economy|world_society|sports|science_future|creator_media|mobility_energy","regional_relevance":"local|germany|europe|global","criteria":{{"aktualitaet":0,"viralitaet":0,"tayvoriq_passung":0,"quellenqualitaet":0,"visuell":0}},"sources":[{{"publisher":"...","url":"https://...","supports":"..."}},{{"publisher":"...","url":"https://...","supports":"..."}}],"fallback_editorial_answers":{{"what_happened":"...","why_happening":"...","who_is_affected":"...","personal_impact":"...","action_now":"..."}}}}]}}
Keep up to six complete candidates. Every candidate needs exactly two independent publishers and direct URLs. Return JSON only.
DOSSIER:
{dossier[:28000]}
""".strip()
    structured_raw = post_groq({
        "model": "openai/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": "You are a lossless research-data formatter. Return valid JSON only."},
            {"role": "user", "content": structure_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_completion_tokens": 9000,
    }, api_key, timeout=120)
    data = base.extract_json(content_of(structured_raw))
    chunks: list[dict[str, str]] = []
    for candidate in data.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        for source in candidate.get("sources") or []:
            if not isinstance(source, dict):
                continue
            url = base.clean(source.get("url"), 2000)
            if url.startswith(("https://", "http://")):
                chunks.append({"title": base.clean(source.get("publisher") or url, 500), "uri": url})
    return data, chunks, "openai/gpt-oss-20b+browser_search+json_object"


def resilient_grounded_call(prompt: str, gemini_key: str, groq_key: str):
    errors: list[str] = []

    if gemini_key:
        try:
            data, chunks, model = _run_with_backoff(
                "Gemini grounded trend scan",
                lambda: base.gemini_call(prompt, gemini_key),
                attempts=3,
            )
            return data, chunks, model, "gemini"
        except Exception as exc:
            errors.append(str(exc))

    if groq_key:
        try:
            data, chunks, model = _run_with_backoff(
                "Groq grounded trend scan",
                lambda: groq_browser_then_structure(prompt, groq_key),
                attempts=2,
            )
            return data, chunks, model, "groq"
        except Exception as exc:
            errors.append(str(exc))

    raise RuntimeError("All grounded trend providers failed after bounded retries: " + " | ".join(errors))


base.groq_call = groq_browser_then_structure
base.grounded_call = resilient_grounded_call
