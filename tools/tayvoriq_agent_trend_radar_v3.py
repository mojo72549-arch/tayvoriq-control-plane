#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.request
from typing import Any

import tayvoriq_agent_trend_radar_v2 as base

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROWTH_KEYS = (
    "hook_strength",
    "retention_potential",
    "follow_conversion_potential",
    "series_fit",
    "share_comment_potential",
    "search_discoverability",
)
GROWTH_WEIGHTS = {
    "hook_strength": 0.20,
    "retention_potential": 0.25,
    "follow_conversion_potential": 0.20,
    "series_fit": 0.15,
    "share_comment_potential": 0.10,
    "search_discoverability": 0.10,
}


def post_groq(payload: dict[str, Any], api_key: str, timeout: int = 180) -> dict[str, Any]:
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

TAYVORIQ growth model:
- Morning is normally the REACH slot: current/searchable/shareable with immediate visual payoff.
- Evening is normally the RETURN slot: series/recurring explainer potential that gives viewers a reason to follow and return.
- One researched story may later become separate YouTube and TikTok platform variants. Do not create cosmetic duplicate topics.
- Every story needs a hook before any series label.
- Prefer topics that can produce a factual second payoff rather than filler.

For EACH story provide:
- German title
- category and one scope from: technology_ai, business_economy, world_society, sports, science_future, creator_media, mobility_energy
- regional relevance: local, germany, europe or global
- five 0-100 editorial scores: aktualitaet, viralitaet, tayvoriq_passung, quellenqualitaet, visuell
- six 0-100 growth scores: hook_strength, retention_potential, follow_conversion_potential, series_fit, share_comment_potential, search_discoverability
- EXACTLY TWO independent credible sources, each with publisher, FULL DIRECT http(s) URL, and one supported fact
- five one-sentence answers: what_happened, why_happening, who_is_affected, personal_impact, action_now

Score growth potential conservatively. A topic is not 90+ merely because it is breaking. Follow conversion requires a credible reason to want more from TAYVORIQ; series fit requires multiple distinct factual angles; search discoverability requires likely explicit query intent.
Do not invent URLs or facts. Keep the dossier concise. The next system stage will convert it to JSON.
Current editorial contract for context:
{prompt[:3500]}
""".strip()

    search_raw = post_groq({
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": research_prompt}],
        "temperature": 1,
        "max_completion_tokens": 7000,
        "top_p": 1,
        "tool_choice": "required",
        "tools": [{"type": "browser_search"}],
    }, api_key)
    dossier = content_of(search_raw)
    if len(dossier) < 500:
        raise RuntimeError("browser research dossier unexpectedly short")

    structure_prompt = f"""
Convert the research dossier below into ONE valid JSON object. Use ONLY facts and URLs already present in the dossier; do not add or infer new factual claims.

Exact schema:
{{
  "candidates": [
    {{
      "title": "German headline",
      "category": "...",
      "trend_scope": "technology_ai|business_economy|world_society|sports|science_future|creator_media|mobility_energy",
      "regional_relevance": "local|germany|europe|global",
      "criteria": {{"aktualitaet":0,"viralitaet":0,"tayvoriq_passung":0,"quellenqualitaet":0,"visuell":0}},
      "growth_criteria": {{"hook_strength":0,"retention_potential":0,"follow_conversion_potential":0,"series_fit":0,"share_comment_potential":0,"search_discoverability":0}},
      "sources": [
        {{"publisher":"...","url":"https://...","supports":"..."}},
        {{"publisher":"...","url":"https://...","supports":"..."}}
      ],
      "fallback_editorial_answers": {{
        "what_happened":"...",
        "why_happening":"...",
        "who_is_affected":"...",
        "personal_impact":"...",
        "action_now":"..."
      }}
    }}
  ]
}}

Rules: keep up to six contract-complete candidates; every candidate must have exactly two independent source publishers and full direct URLs. Preserve the six growth scores from the dossier. If a candidate lacks two direct URLs in the dossier, omit it. Return JSON only.

DOSSIER:
{dossier[:30000]}
""".strip()

    structured_raw = post_groq({
        "model": "openai/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": "You are a lossless research-data formatter. Return valid JSON only."},
            {"role": "user", "content": structure_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_completion_tokens": 10000,
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
                chunks.append({
                    "title": base.clean(source.get("publisher") or url, 500),
                    "uri": url,
                })
    return data, chunks, "openai/gpt-oss-20b+browser_search+json_object+growth-v1"


_original_normalized_candidate = base.normalized_candidate
_original_grounded_call = base.grounded_call


def growth_normalized_candidate(raw: dict[str, Any], verified_at: str) -> dict[str, Any] | None:
    candidate = _original_normalized_candidate(raw, verified_at)
    if not candidate:
        return None

    editorial_score = base.clamp(candidate.get("score"))
    growth_raw = raw.get("growth_criteria") if isinstance(raw.get("growth_criteria"), dict) else None

    # Backwards compatibility: active series/state created before growth-v1 keeps
    # its editorial score instead of being penalized for missing new fields.
    if not growth_raw:
        candidate["editorial_score"] = editorial_score
        candidate["growth_score"] = editorial_score
        candidate["growth_criteria"] = {}
        candidate["score"] = editorial_score
        candidate["score_model"] = "legacy-editorial-compatible"
        return candidate

    growth = {key: base.clamp(growth_raw.get(key)) for key in GROWTH_KEYS}
    if min(growth.values()) < 25:
        return None

    growth_score = round(sum(growth[key] * GROWTH_WEIGHTS[key] for key in GROWTH_KEYS))
    combined = round(editorial_score * 0.60 + growth_score * 0.40)

    candidate["editorial_score"] = editorial_score
    candidate["growth_score"] = base.clamp(growth_score)
    candidate["growth_criteria"] = growth
    candidate["score"] = base.clamp(combined)
    candidate["score_model"] = "editorial60_growth40_v1"
    return candidate


def growth_grounded_call(prompt: str, gemini_key: str, groq_key: str):
    """Prefer the provider path that returns the complete growth-v1 dossier.

    Gemini stays as a source-grounded fallback so production does not lose provider
    redundancy. A fallback candidate without growth fields is scored with the legacy
    editorial model instead of fabricating growth values.
    """
    if groq_key:
        try:
            data, chunks, model = groq_browser_then_structure(prompt, groq_key)
            return data, chunks, model, "groq"
        except Exception:
            if not gemini_key:
                raise
    return _original_grounded_call(prompt, gemini_key, groq_key)


# Growth-v1 is authoritative for the v3 radar. Source validation, active-series
# injection, diversity and all existing hard quality gates remain in force.
base.groq_call = groq_browser_then_structure
base.grounded_call = growth_grounded_call
base.normalized_candidate = growth_normalized_candidate

if __name__ == "__main__":
    raise SystemExit(base.main())
