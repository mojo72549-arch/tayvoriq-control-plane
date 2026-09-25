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
Research CURRENT TAYVORIQ short-video candidates with broad reach potential now.
Use browser search. We need EIGHT genuinely different candidate stories, normally from the last 24 hours (48 hours only if still unfolding).
For BOTH morning and evening, search Germany-wide, Europe-wide and major global developments across AI, technology, science, business/economy, mobility/energy, sports and world/society. Do not prioritize Stuttgart, Baden-Württemberg, a city, a state or South Germany merely because the audience is German.
Audience 16-44, sweet spot 18-34. Prioritize verified momentum, broad audience relevance, surprise, consequence, strong 35-60 second hookability, visual potential and cross-publisher confirmation.
Purely local/city/state stories are normally ineligible. Include one only when the evidence shows a real national or international breakout, consequence or unusually strong cross-platform momentum.
"Recently reported somewhere" is not a trend signal. Prefer stories with clear why-now momentum and independent confirmation. Never pad the candidate set with weak/local filler.
Before choosing the final six, perform a strategic entity sweep for Microsoft, OpenAI, Google/Alphabet, Apple, Meta, Amazon/AWS and Nvidia. For Microsoft explicitly check Azure, Windows, Copilot, Microsoft 365, GitHub, Xbox and major AI/cloud/business developments. This is discovery coverage, not a quota: include a named-company story only when it is fresh, independently sourced and competitive on the normal TAYVORIQ criteria. Do not discard a strong Microsoft story merely because other AI/technology stories exist; deduplicate by the actual event and viewer takeaway, not by broad category.
For earthquakes, volcanoes, eclipses, storms, wildfires, floods or similar natural events, include a concise WHY/HOW explanation.
Avoid political advocacy, gossip, rumors, graphic violence and duplicate angles.
For EACH story provide German title, category, one allowed trend scope, regional relevance, five existing quality scores, PLUS V5 growth fields: viral_potential, tayvoriq_fit, novelty_score, series_fit_score, return_viewer_score, follow_conversion_potential and open_loop_potential (all 0-100); proposed_series_id/name only when genuinely appropriate; an honest next_episode_candidate or empty string; recommended_cta_type; primary_hook; viewer_question; explanation_core; surprise_or_reframe; practical_relevance; a topic-specific follow_reason; honest open_loop + open_loop_status NONE/SOFT/HARD; cta_type and topic-specific cta_text. HARD is allowed only when a real follow-up candidate is concretely planned by the returned series metadata. Never use generic 'Bitte abonnieren'. Also provide EXACTLY TWO independent credible sources with publisher/direct URL/supported fact, and five concise answers: what_happened, why_happening, who_is_affected, personal_impact, action_now.
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
Schema: {{"candidates":[{{"title":"German headline","category":"...","trend_scope":"technology_ai|business_economy|world_society|sports|science_future|creator_media|mobility_energy","regional_relevance":"local|germany|europe|global","criteria":{{"aktualitaet":0,"viralitaet":0,"tayvoriq_passung":0,"quellenqualitaet":0,"visuell":0}},"viral_potential":0,"tayvoriq_fit":0,"novelty_score":0,"series_fit_score":0,"return_viewer_score":0,"follow_conversion_potential":0,"open_loop_potential":0,"proposed_series_id":"","proposed_series_name":"","next_episode_candidate":"","recommended_cta_type":"CURIOSITY|EXPERTISE|COMMUNITY|SERIES|DISCUSSION|IDENTITY","primary_hook":"...","viewer_question":"...","explanation_core":"...","surprise_or_reframe":"...","practical_relevance":"...","follow_reason":"...","open_loop":"","open_loop_status":"NONE|SOFT|HARD","cta_type":"CURIOSITY|EXPERTISE|COMMUNITY|SERIES|DISCUSSION|IDENTITY","cta_text":"...","sources":[{{"publisher":"...","url":"https://...","supports":"..."}},{{"publisher":"...","url":"https://...","supports":"..."}}],"fallback_editorial_answers":{{"what_happened":"...","why_happening":"...","who_is_affected":"...","personal_impact":"...","action_now":"..."}}}}]}}
Keep up to eight complete candidates so the downstream reach gate can reject weak/local items without starving the final 3-5. Every candidate needs exactly two independent publishers and direct URLs. Return JSON only.
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
