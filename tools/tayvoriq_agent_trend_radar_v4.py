#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import tayvoriq_agent_trend_provider_v3 as provider_v3

base = provider_v3.base
CONFIG_PATH = Path("config/tayvoriq_growth_runtime_v2.json")
_original_normalize = base.normalized_candidate
_original_prompt = base.prompt_for

_NUMBER_WORDS = {
    "null": "0", "eins": "1", "ein": "1", "eine": "1", "einen": "1",
    "zwei": "2", "drei": "3", "vier": "4", "fünf": "5", "fuenf": "5",
    "sechs": "6", "sieben": "7", "acht": "8", "neun": "9", "zehn": "10",
    "elf": "11", "zwölf": "12", "zwoelf": "12", "dreizehn": "13",
    "vierzehn": "14", "fünfzehn": "15", "fuenfzehn": "15", "sechzehn": "16",
    "siebzehn": "17", "achtzehn": "18", "neunzehn": "19", "zwanzig": "20",
}
_COUNTRY_MARKERS = {
    "germany": {"deutschland", "deutsch", "deutsche", "deutschen", "deutscher", "deutsches", "dlv"},
    "britain": {"großbritannien", "grossbritannien", "britannien", "britisch", "britische", "britischen", "britischer", "gb", "uk"},
    "italy": {"italien", "italienisch", "italienische", "italienischen"},
    "france": {"frankreich", "französisch", "franzoesisch", "französische", "franzoesische"},
    "spain": {"spanien", "spanisch", "spanische", "spanischen"},
    "austria": {"österreich", "oesterreich", "österreichisch", "oesterreichisch"},
    "switzerland": {"schweiz", "schweizer", "schweizerisch"},
    "belgium": {"belgien", "belgisch", "belgische", "belgischen"},
    "netherlands": {"niederlande", "niederländisch", "niederlaendisch", "niederländische", "niederlaendische"},
    "usa": {"usa", "us", "vereinigte", "amerikanisch", "amerikanische", "amerikanischen"},
}
_CAUSAL_MARKERS = ("weil", "wegen", "aufgrund", "durch", "dank", "führt", "fuehrt", "verursacht", "liegt an")
_STOPWORDS = {
    "diese", "dieser", "dieses", "einer", "einen", "einem", "eines", "eine", "einer",
    "führen", "fuehren", "führt", "fuehrt", "starke", "starken", "starker", "aktuell",
    "heute", "jetzt", "dadurch", "daher", "damit", "wurde", "werden", "haben", "hatte",
    "athleten", "athletinnen", "menschen", "deutsch", "deutsche", "deutschen", "deutscher",
    "ereignis", "erfolg", "erfolge", "spitzenleistungen", "leistung", "leistungen",
}


def _config() -> dict[str, Any]:
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _clamp(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-zäöüß0-9]+", str(text or "").casefold()))


def _numbers(text: str) -> set[str]:
    words = _words(text)
    values = {token for token in words if token.isdigit()}
    values.update(_NUMBER_WORDS[token] for token in words if token in _NUMBER_WORDS)
    return values


def _country_groups(text: str) -> set[str]:
    words = _words(text)
    return {group for group, markers in _COUNTRY_MARKERS.items() if words & markers}


def _meaningful_words(text: str) -> set[str]:
    return {word for word in _words(text) if len(word) >= 5 and not word.isdigit() and word not in _STOPWORDS}


def _source_claim_coherent(candidate: dict[str, Any]) -> tuple[bool, list[str]]:
    title = str(candidate.get("title") or "")
    ctx = candidate.get("source_context") if isinstance(candidate.get("source_context"), dict) else {}
    sources = ctx.get("sources") if isinstance(ctx.get("sources"), list) else []
    supports = [str(item.get("supports") or "") for item in sources if isinstance(item, dict)]
    answers = ctx.get("fallback_editorial_answers") if isinstance(ctx.get("fallback_editorial_answers"), dict) else {}
    reasons: list[str] = []

    title_numbers = _numbers(title)
    title_countries = _country_groups(title)
    critical_numeric = bool(title_numbers) and bool(title_countries)
    if critical_numeric:
        for index, support in enumerate(supports[:2], start=1):
            if not title_numbers.issubset(_numbers(support)):
                reasons.append(f"source_{index}_missing_title_number")
            if not title_countries.issubset(_country_groups(support)):
                reasons.append(f"source_{index}_missing_title_country")

    why = str(answers.get("why_happening") or "").strip()
    why_lower = why.casefold()
    if why and any(marker in why_lower for marker in _CAUSAL_MARKERS):
        why_terms = _meaningful_words(why)
        support_terms = _meaningful_words(" ".join(supports))
        if why_terms and not (why_terms & support_terms):
            reasons.append("why_happening_not_supported_by_source_claims")

    return not reasons, reasons


def _marker_score(text: str) -> int:
    blob = text.casefold()
    markers = (
        "warum", "wieso", "plötzlich", "ploetzlich", "was bedeutet", "was passiert",
        "rekord", "warn", "gefahr", "überrasch", "ueberrasch", "erstmals", "extrem",
        "ki", "ai", "beben", "tsunami", "vulkan", "brand", "sturm", "crash",
    )
    return min(100, 45 + 8 * sum(1 for marker in markers if marker in blob))


def _regional_score(value: str) -> int:
    return {"local": 100, "germany": 92, "europe": 78, "global": 64}.get(str(value).lower(), 60)


def _growth(candidate: dict[str, Any]) -> dict[str, Any]:
    criteria = candidate.get("criteria") if isinstance(candidate.get("criteria"), dict) else {}
    ctx = candidate.get("source_context") if isinstance(candidate.get("source_context"), dict) else {}
    answers = ctx.get("fallback_editorial_answers") if isinstance(ctx.get("fallback_editorial_answers"), dict) else {}
    title = str(candidate.get("title") or "")
    why = str(answers.get("why_happening") or "")
    impact = str(answers.get("personal_impact") or "")
    action = str(answers.get("action_now") or "")
    curiosity = _marker_score(f"{title} {why} {impact}")
    personal = _regional_score(str(candidate.get("regional_relevance") or ""))
    explainability = 92 if why and impact else 65
    follow_up = 90 if why and impact and action else 68
    if isinstance(ctx.get("series_context"), dict):
        follow_up = max(follow_up, 90)

    growth_score = _clamp(
        float(criteria.get("aktualitaet") or 0) * .22
        + float(criteria.get("viralitaet") or 0) * .28
        + float(criteria.get("tayvoriq_passung") or 0) * .16
        + float(criteria.get("visuell") or 0) * .14
        + personal * .12
        + curiosity * .08
    )
    binding_score = _clamp(
        float(criteria.get("tayvoriq_passung") or 0) * .30
        + personal * .25
        + explainability * .25
        + follow_up * .20
    )
    priority = _clamp(growth_score * .76 + binding_score * .24)
    tier = "breakout_preferred" if growth_score >= 90 else "primary" if growth_score >= 85 else "reserve" if growth_score >= 80 else "hold"
    return {
        "growth_score": growth_score,
        "binding_score": binding_score,
        "priority_score": priority,
        "tier": tier,
        "series_candidate": isinstance(ctx.get("series_context"), dict),
        "targets": "10k/20k/50k/100k are optimization targets, never guarantees",
    }


def normalized_candidate(raw: dict[str, Any], verified_at: str) -> dict[str, Any] | None:
    candidate = _original_normalize(raw, verified_at)
    if not candidate:
        return None
    coherent, reasons = _source_claim_coherent(candidate)
    if not coherent:
        return None
    cfg = _config().get("selection") or {}
    if int(candidate.get("score") or 0) < int(cfg.get("base_quality_min") or 75):
        return None
    report = _growth(candidate)
    candidate["growth_v2"] = report
    candidate["source_context"]["growth_v2"] = report
    candidate["source_context"]["claim_coherence"] = {"passed": True, "reasons": reasons}
    return candidate


def diversify(candidates: list[dict[str, Any]], slot: str) -> list[dict[str, Any]]:
    cfg = _config().get("selection") or {}
    eligible = [c for c in candidates if int((c.get("growth_v2") or {}).get("growth_score") or 0) >= 80]
    ordered = sorted(
        eligible,
        key=lambda c: (
            int((c.get("growth_v2") or {}).get("priority_score") or 0),
            int((c.get("growth_v2") or {}).get("growth_score") or 0),
            int(c.get("score") or 0),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    scopes: dict[str, int] = {}
    for candidate in ordered:
        scope = str(candidate.get("trend_scope") or "")
        if scopes.get(scope, 0) >= 2:
            continue
        if any(str(x.get("title") or "").casefold() == str(candidate.get("title") or "").casefold() for x in selected):
            continue
        selected.append(candidate)
        scopes[scope] = scopes.get(scope, 0) + 1
        if len(selected) >= int(cfg.get("telegram_candidates_max") or 5):
            break
    minimum = int(cfg.get("telegram_candidates_min") or 4)
    if len(selected) < minimum:
        raise SystemExit(f"GROWTH_RESCAN_REQUIRED: only {len(selected)} candidates reached reserve threshold")
    return selected


def prompt_for(slot, now):
    prompt = _original_prompt(slot, now)
    return prompt.replace(
        "Strong hook within 1.5 seconds; 35-60 second vertical short potential.",
        "Strong hook within 1.5 seconds. Evaluate breakout reach AND follower/subscriber conversion. The verified fact core must support a concise YouTube cut and a deeper TikTok cut over 61 seconds without padding."
    ) + "\n- An active series episode has NO reserved slot. Treat it as a candidate only if its current relevance and growth potential compete with fresh trends." \
      + "\n- CROSS-SOURCE CONSISTENCY IS MANDATORY: central numbers, countries/nationalities and causal WHY claims in the title/editorial answers must be supported by BOTH independent source summaries. Never combine a number from one story/person/country with another source."


base.normalized_candidate = normalized_candidate
base.diversify = diversify
base.prompt_for = prompt_for

if __name__ == "__main__":
    raise SystemExit(base.main())
