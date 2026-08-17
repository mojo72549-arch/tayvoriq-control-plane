#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.request
from typing import Any

import tayvoriq_agent_trend_radar_v2 as base

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def post_groq(payload: dict[str, Any], api_key: str, timeout: int = 180) -> dict[str, Any]:
    req = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}", "User-Agent": "tayvoriq-agent-v3"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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
        "messages": [{"role": "system", "content": "You are a lossless research-data formatter. Return valid JSON only."}, {"role": "user", "content": structure_prompt}],
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


base.groq_call = groq_browser_then_structure
