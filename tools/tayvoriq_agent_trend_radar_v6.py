#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import tayvoriq_agent_trend_radar_v5 as growth_v5

base = growth_v5.base
_original_diversify = base.diversify


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


def _editorial_semantics_strong(candidate: dict[str, Any]) -> bool:
    """Reject source packages whose WHY/IMPACT merely restate headline facts.

    The WHY vocabulary is intentionally aligned with the downstream production
    causality gate. A radar candidate must not pass on comparison words such as
    'aber', 'trotz' or 'entscheidend' alone and then fail later in production.
    """

    ctx = candidate.get("source_context") if isinstance(candidate.get("source_context"), dict) else {}
    answers = ctx.get("fallback_editorial_answers") if isinstance(ctx.get("fallback_editorial_answers"), dict) else {}
    what = str(answers.get("what_happened") or "").strip()
    why = str(answers.get("why_happening") or "").strip()
    affected = str(answers.get("who_is_affected") or "").strip()
    impact = str(answers.get("personal_impact") or "").strip()
    if not all((what, why, affected, impact)):
        return False

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
    consequence_markers = (
        "bedeutet", "heißt", "dadurch", "deshalb", "kann", "muss", "sollte",
        "wer ", "für zuschauer", "für verbraucher", "für reisende", "für fans",
        "einordnen", "erklärt", "relevant", "konkret", "automatisch",
    )
    why_lower = why.casefold()
    impact_lower = impact.casefold()

    if len(why_novel) < 4 or not any(marker in why_lower for marker in mechanism_markers):
        return False
    if len(impact_novel) < 4 or not any(marker in impact_lower for marker in consequence_markers):
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
            "reason": "why_or_personal_impact_was_tautological_or_underspecified",
        })
    if candidates and not semantically_grounded:
        _mark_research_deferred(len(candidates), rejected)
    return _original_diversify(_dedupe_story_clusters(semantically_grounded), slot)


base.diversify = diversify

if __name__ == "__main__":
    raise SystemExit(base.main())
