#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import tayvoriq_agent_trend_radar_v5 as growth_v5

base = growth_v5.base
_original_diversify = base.diversify
_original_prompt = base.prompt_for
_EDITORIAL_KEYS = (
    "what_happened",
    "why_happening",
    "who_is_affected",
    "personal_impact",
    "action_now",
)
_CAUSE_MARKERS = (
    "weil", "wegen", "durch", "treiber", "grund", "ursache", "auslöser", "führt", "infolge",
    "nachfrage", "kosten", "finanzierung", "strategie", "nutzung", "aufgrund", "dadurch", "deshalb",
)
_ACTION_MARKERS = (
    "achte", "prüfe", "sichere", "vergleiche", "aktiviere", "reduziere", "kontaktiere", "beobachte",
    "exportiere", "wechsle", "plane", "kläre", "nutze", "begrenze", "speichere",
)


def _source_signature(candidate: dict[str, Any]) -> frozenset[str]:
    urls = {
        str(url).strip().casefold()
        for url in (candidate.get("sources") or [])
        if str(url).strip()
    }
    if urls:
        return frozenset(urls)
    ctx = candidate.get("source_context") if isinstance(candidate.get("source_context"), dict) else {}
    sources = ctx.get("sources") if isinstance(ctx.get("sources"), list) else []
    return frozenset(
        str(item.get("url") or "").strip().casefold()
        for item in sources
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    )


def _dedupe_story_clusters(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        candidates,
        key=lambda c: (
            int((c.get("growth_v2") or {}).get("priority_score") or 0),
            int((c.get("growth_v2") or {}).get("growth_score") or 0),
            int(c.get("score") or 0),
        ),
        reverse=True,
    )
    kept: list[dict[str, Any]] = []
    signatures: list[frozenset[str]] = []
    for candidate in ordered:
        signature = _source_signature(candidate)
        duplicate = False
        if len(signature) >= 2:
            for existing in signatures:
                if len(signature & existing) >= 2:
                    duplicate = True
                    break
        if duplicate:
            continue
        kept.append(candidate)
        signatures.append(signature)
    return kept


def _words(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zäöüß0-9]+", str(value or "").casefold())
        if len(token) >= 3
        and token not in {
            "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer",
            "einem", "einen", "und", "oder", "mit", "für", "von", "auf", "aus",
            "ist", "sind", "war", "waren", "wird", "werden", "hat", "haben",
            "dass", "dies", "diese", "dieser", "als", "auch", "nur", "noch",
        }
    }


def _word_count(value: str) -> int:
    return len(re.findall(r"\S+", " ".join(str(value or "").split())))


def _downstream_editorial_contract_valid(answers: dict[str, Any]) -> bool:
    """Mirror the strict V11/V34 fallback contract before Telegram approval.

    Research prose may stay rich in source summaries, but the five immutable fallback
    answers must already be usable as a 35-second fail-closed production packet.
    This prevents a request from being green in research and deterministically red
    later at the renderer's semantic boundary.
    """

    normalized = {key: " ".join(str(answers.get(key) or "").split()).strip() for key in _EDITORIAL_KEYS}
    if any(not normalized[key] for key in _EDITORIAL_KEYS):
        return False
    if any(not 5 <= _word_count(value) <= 15 for value in normalized.values()):
        return False
    body_words = sum(_word_count(normalized[key]) for key in _EDITORIAL_KEYS)
    if not 38 <= body_words <= 49:
        return False
    why = normalized["why_happening"].casefold()
    if not any(marker in why for marker in _CAUSE_MARKERS):
        return False
    if "für dich" not in normalized["personal_impact"].casefold():
        return False
    action = normalized["action_now"].casefold()
    if not any(action.startswith(marker) for marker in _ACTION_MARKERS):
        return False
    return True


def _editorial_semantics_strong(candidate: dict[str, Any]) -> bool:
    """Reject source packages whose WHY/IMPACT merely restate headline facts.

    In addition to novelty checks, the immutable fallback must now satisfy the same
    compact semantic shape expected downstream. The quality threshold is not lowered.
    """

    ctx = candidate.get("source_context") if isinstance(candidate.get("source_context"), dict) else {}
    answers = ctx.get("fallback_editorial_answers") if isinstance(ctx.get("fallback_editorial_answers"), dict) else {}
    if not _downstream_editorial_contract_valid(answers):
        return False

    what = str(answers.get("what_happened") or "").strip()
    why = str(answers.get("why_happening") or "").strip()
    affected = str(answers.get("who_is_affected") or "").strip()
    impact = str(answers.get("personal_impact") or "").strip()

    what_words = _words(what)
    why_words = _words(why)
    affected_words = _words(affected)
    impact_words = _words(impact)
    why_novel = why_words - what_words
    impact_novel = impact_words - (what_words | affected_words)

    mechanism_markers = (
        "weil", "wegen", "dadurch", "deshalb", "aufgrund", "infolge", "durch ",
        "führt", "treiber", "ursache", "grund", "auslöser", " bis ",
    )
    why_lower = why.casefold()

    if len(why_novel) < 3 or not any(marker in why_lower for marker in mechanism_markers):
        return False
    if len(impact_novel) < 3:
        return False
    return True


def _mark_research_deferred(candidate_count: int, rejected_count: int) -> None:
    path = Path("/tmp/tayvoriq-research-deferred.json")
    payload = {
        "state": "RESEARCH_DEFERRED_NO_SAFE_CANDIDATES",
        "candidate_count": int(candidate_count),
        "semantic_rejected": int(rejected_count),
        "quality_gate_weakened": False,
        "production_started": False,
        "user_action_required": False,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"event": "research_deferred", **payload})


def diversify(candidates: list[dict[str, Any]], slot: str) -> list[dict[str, Any]]:
    semantically_grounded = [candidate for candidate in candidates if _editorial_semantics_strong(candidate)]
    rejected = len(candidates) - len(semantically_grounded)
    if rejected:
        print({
            "event": "semantic_source_prefilter",
            "rejected": rejected,
            "kept": len(semantically_grounded),
            "reason": "fallback_not_downstream_contract_safe_or_semantically_weak",
        })
    if candidates and not semantically_grounded:
        _mark_research_deferred(len(candidates), rejected)
    return _original_diversify(_dedupe_story_clusters(semantically_grounded), slot)


def prompt_for(slot, now):
    return _original_prompt(slot, now) + """

STRICT FALLBACK CONTRACT BEFORE TELEGRAM:
- Each of the five fallback_editorial_answers must be ONE natural German sentence with 5-15 words.
- All five sentences together must total 38-49 words.
- why_happening must contain an explicit causal mechanism such as weil, wegen, durch, aufgrund, dadurch, deshalb, Ursache, Grund or führt.
- personal_impact must explicitly contain 'Für dich' and state a concrete viewer consequence/relevance supported by the sources.
- action_now must begin with one of: Achte, Prüfe, Sichere, Vergleiche, Aktiviere, Reduziere, Kontaktiere, Beobachte, Exportiere, Wechsle, Plane, Kläre, Nutze, Begrenze, Speichere.
- Do not use the fallback fields for long research prose; keep detail in source supports instead.
""".strip()


base.diversify = diversify
base.prompt_for = prompt_for

if __name__ == "__main__":
    raise SystemExit(base.main())
