#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

VALID_SCOPES = {
    "technology_ai", "business_economy", "world_society", "sports",
    "science_future", "creator_media", "mobility_energy", "auto_scope",
}
BLOCKED_SOURCE_MARKERS = ("tiktok.com", "instagram.com", "facebook.com", "x.com", "twitter.com", "youtube.com")


def clamp(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return 0


def clean(value: Any, limit: int = 2000) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            value = json.loads(text[start:end+1])
            return value if isinstance(value, dict) else {}
        raise


def gemini_call(prompt: str, api_key: str) -> tuple[dict[str, Any], list[dict[str, str]], str]:
    configured = clean(os.getenv("TAYVORIQ_TREND_MODEL"), 100) or "gemini-3.5-flash"
    models = []
    for model in (configured, "gemini-2.5-flash"):
        if model not in models:
            models.append(model)
    last_error = ""
    for model in models:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"googleSearch": {}}],
            "generationConfig": {"temperature": 0.15, "maxOutputTokens": 12000},
        }
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key, "User-Agent": "tayvoriq-agent-v2"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                raw = json.loads(response.read().decode("utf-8"))
            candidate = (raw.get("candidates") or [{}])[0]
            parts = ((candidate.get("content") or {}).get("parts") or [])
            text = "\n".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()
            data = extract_json(text)
            chunks = []
            for chunk in ((candidate.get("groundingMetadata") or {}).get("groundingChunks") or []):
                web = chunk.get("web") if isinstance(chunk, dict) else None
                if isinstance(web, dict) and web.get("uri"):
                    chunks.append({"title": clean(web.get("title"), 500), "uri": clean(web.get("uri"), 2000)})
            return data, chunks, model
        except Exception as exc:
            last_error = f"{model}: {type(exc).__name__}: {exc}"
    raise RuntimeError(f"Gemini grounded trend scan failed: {last_error}")


def prompt_for(slot: str, now: datetime) -> str:
    slot_rules = (
        "MORNING: prioritize Germany + Europe + major global developments with strong visual/explainer potential."
        if slot == "morning" else
        "AFTERNOON: prioritize Stuttgart/Baden-Württemberg/South Germany and Germany-wide youth/creator/local-interest trends, while still allowing a major global breaking story if clearly stronger."
    )
    return f"""
You are the TrendSourceAgent for the German short-video brand TAYVORIQ.
Current local time: {now.isoformat()} (Europe/Berlin). Slot: {slot.upper()}.
{slot_rules}

Use Google Search grounding and identify 8 CURRENT candidate stories from roughly the last 24 hours (48 hours only if still actively unfolding). Return ONLY one JSON object with key \"candidates\".

Editorial goals:
- Audience: broad 16-39, especially 18-34, understandable without prior knowledge.
- Strong hook within 1.5 seconds; 35-60 second vertical short potential.
- Prefer technology/AI, world events, business/economy, science/future, mobility/energy, creator/media, sports, and useful local/regional developments.
- Natural events (earthquake, volcano, eclipse, storm, wildfire, flood etc.) should include the deeper WHY/HOW explanation, not only the event.
- Avoid party-political advocacy, celebrity gossip, graphic violence, rumors, clickbait without evidence, and duplicate versions of the same story.
- Every candidate MUST have at least two independent, credible sources. Prefer primary/official sources plus established news outlets. Do not use social media as a source.
- Do not invent URLs, publishers, dates, numbers, or quotes.

For each candidate return:
{{
  \"title\": \"short German headline\",
  \"category\": \"...\",
  \"trend_scope\": \"technology_ai|business_economy|world_society|sports|science_future|creator_media|mobility_energy\",
  \"regional_relevance\": \"local|germany|europe|global\",
  \"criteria\": {{\"aktualitaet\":0-100,\"viralitaet\":0-100,\"tayvoriq_passung\":0-100,\"quellenqualitaet\":0-100,\"visuell\":0-100}},
  \"sources\": [{{\"publisher\":\"...\",\"url\":\"https://...\",\"supports\":\"specific fact supported by this source\"}}, ...],
  \"fallback_editorial_answers\": {{
    \"what_happened\": \"...\",
    \"why_happening\": \"...\",
    \"who_is_affected\": \"...\",
    \"personal_impact\": \"...\",
    \"action_now\": \"...\"
  }}
}}
""".strip()


def normalized_candidate(raw: dict[str, Any], verified_at: str) -> dict[str, Any] | None:
    title = clean(raw.get("title"), 180)
    scope = clean(raw.get("trend_scope"), 60)
    if not title or scope not in VALID_SCOPES or scope == "auto_scope":
        return None
    crit_raw = raw.get("criteria") if isinstance(raw.get("criteria"), dict) else {}
    criteria = {k: clamp(crit_raw.get(k)) for k in ("aktualitaet","viralitaet","tayvoriq_passung","quellenqualitaet","visuell")}
    if min(criteria.values()) < 35:
        return None
    sources = []
    seen_publishers = set()
    for item in raw.get("sources") or []:
        if not isinstance(item, dict):
            continue
        publisher = clean(item.get("publisher"), 120)
        url = clean(item.get("url"), 2000)
        supports = clean(item.get("supports"), 600)
        lower_url = url.lower()
        if not publisher or not url.startswith(("https://", "http://")) or not supports:
            continue
        if any(marker in lower_url for marker in BLOCKED_SOURCE_MARKERS):
            continue
        key = publisher.casefold()
        if key in seen_publishers:
            continue
        seen_publishers.add(key)
        sources.append({"publisher": publisher, "url": url, "supports": supports})
    if len(sources) < 2:
        return None
    answers_raw = raw.get("fallback_editorial_answers") if isinstance(raw.get("fallback_editorial_answers"), dict) else {}
    answers = {k: clean(answers_raw.get(k), 900) for k in ("what_happened","why_happening","who_is_affected","personal_impact","action_now")}
    if not all(answers.values()):
        return None
    score = round(
        criteria["aktualitaet"] * .25 + criteria["viralitaet"] * .25 +
        criteria["tayvoriq_passung"] * .20 + criteria["quellenqualitaet"] * .15 + criteria["visuell"] * .15
    )
    return {
        "category": clean(raw.get("category"), 100) or scope,
        "trend_scope": scope,
        "title": title,
        "score": clamp(score),
        "criteria": criteria,
        "regional_relevance": clean(raw.get("regional_relevance"), 30) or "global",
        "sources": [s["url"] for s in sources[:3]],
        "source_context": {
            "verified_at": verified_at,
            "independent_news_count": len(sources[:3]),
            "sources": sources[:3],
            "fallback_editorial_answers": answers,
        },
    }


def diversify(candidates: list[dict[str, Any]], slot: str) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda x: x["score"], reverse=True)
    selected: list[dict[str, Any]] = []
    scope_counts: dict[str, int] = {}
    if slot == "afternoon":
        local = next((c for c in ordered if c.get("regional_relevance") == "local" and c["score"] >= 70), None)
        if local:
            selected.append(local)
            scope_counts[local["trend_scope"]] = 1
    for cand in ordered:
        if cand in selected:
            continue
        if scope_counts.get(cand["trend_scope"], 0) >= 2:
            continue
        if any(cand["title"].casefold() == x["title"].casefold() for x in selected):
            continue
        selected.append(cand)
        scope_counts[cand["trend_scope"]] = scope_counts.get(cand["trend_scope"], 0) + 1
        if len(selected) == 5:
            break
    if len(selected) < 5:
        for cand in ordered:
            if cand not in selected:
                selected.append(cand)
                if len(selected) == 5:
                    break
    return selected[:5]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", choices=["morning", "afternoon"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()
    api_key = clean(os.getenv("GEMINI_API_KEY"), 500)
    if not api_key:
        raise SystemExit("GEMINI_API_KEY missing")
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    data, chunks, model = gemini_call(prompt_for(args.slot, now), api_key)
    if len(chunks) < 4:
        raise SystemExit(f"Grounding evidence too weak: only {len(chunks)} web chunks")
    verified_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    raw_candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
    normalized = [c for raw in raw_candidates if isinstance(raw, dict) and (c := normalized_candidate(raw, verified_at))]
    chosen = diversify(normalized, args.slot)
    if len(chosen) != 5:
        raise SystemExit(f"Need 5 contract-valid grounded trends, got {len(chosen)} from {len(raw_candidates)} candidates")
    selection_id = f"{now:%Y%m%d}-{args.slot}-agentv2"
    for index, trend in enumerate(chosen, start=1):
        trend["id"] = str(index)
    request = {
        "date": now.strftime("%Y-%m-%d"),
        "slot": args.slot,
        "created_at": verified_at,
        "selection_id": selection_id,
        "selected_trend_id": None,
        "agent_orchestrator": "v2",
        "trends": chosen,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit = {"selection_id": selection_id, "slot": args.slot, "model": model, "grounding_chunks": chunks, "candidate_count": len(raw_candidates), "valid_count": len(normalized), "selected_count": 5, "quality_gates_weakened": False}
    Path(args.audit_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.audit_output).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selection_id": selection_id, "slot": args.slot, "model": model, "selected": [t["title"] for t in chosen]}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
