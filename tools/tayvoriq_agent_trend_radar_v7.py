#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import tayvoriq_agent_trend_radar_v6 as growth_v6

base = growth_v6.base
CONFIG_PATH = Path("config/tayvoriq_growth_runtime_v2.json")
_original_normalized_candidate = base.normalized_candidate
_original_prompt = base.prompt_for

_CONTINUATION_MARKERS = (
    "ki", "ai", "technologie", "technik", "robot", "industrie", "wirtschaft", "auto",
    "mobilität", "energie", "klima", "deutschland", "europa", "raumfahrt", "chip",
    "infrastruktur", "bahn", "cyber", "digital",
)
_HOOK_MARKERS = (
    "warum", "wieso", "plötzlich", "ploetzlich", "was passiert", "was bedeutet", "rekord",
    "warn", "krise", "erstmals", "extrem", "überrasch", "ueberrasch", "gefahr", "riesig",
)


def _config() -> dict[str, Any]:
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _clamp(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _answers(candidate: dict[str, Any]) -> dict[str, str]:
    ctx = candidate.get("source_context") if isinstance(candidate.get("source_context"), dict) else {}
    raw = ctx.get("fallback_editorial_answers") if isinstance(ctx.get("fallback_editorial_answers"), dict) else {}
    return {key: " ".join(str(value or "").split()).strip() for key, value in raw.items()}


def _marker_score(blob: str, markers: tuple[str, ...], *, floor: int = 55, step: int = 8) -> int:
    lowered = str(blob or "").casefold()
    return min(100, floor + step * sum(1 for marker in markers if marker in lowered))


def _audience_report(candidate: dict[str, Any]) -> dict[str, Any]:
    growth = candidate.get("growth_v2") if isinstance(candidate.get("growth_v2"), dict) else {}
    criteria = candidate.get("criteria") if isinstance(candidate.get("criteria"), dict) else {}
    answers = _answers(candidate)
    title = str(candidate.get("title") or "")
    blob = " ".join([title, *answers.values()])

    base_priority = int(growth.get("priority_score") or 0)
    base_binding = int(growth.get("binding_score") or 0)
    growth_score = int(growth.get("growth_score") or 0)
    fit = int(criteria.get("tayvoriq_passung") or 0)
    viral = int(criteria.get("viralitaet") or 0)

    hook_strength = _marker_score(blob, _HOOK_MARKERS)
    continuation = _marker_score(blob, _CONTINUATION_MARKERS, floor=62, step=6)
    if isinstance((candidate.get("source_context") or {}).get("series_context"), dict):
        continuation = max(continuation, 96)

    has_complete_payoff = all(
        answers.get(key)
        for key in ("what_happened", "why_happening", "personal_impact", "action_now")
    )
    payoff = 94 if has_complete_payoff else 68

    subscriber_conversion = _clamp(
        base_binding * .32
        + fit * .20
        + viral * .14
        + hook_strength * .14
        + continuation * .20
    )
    returning_viewer = _clamp(
        base_binding * .34
        + continuation * .31
        + payoff * .20
        + fit * .15
    )

    audience_cfg = _config().get("audience_growth") or {}
    weights = audience_cfg.get("selection_weights") or {}
    base_weight = float(weights.get("base_priority") or .60)
    subscriber_weight = float(weights.get("subscriber_conversion") or .25)
    returning_weight = float(weights.get("returning_viewer") or .15)
    selection_priority = _clamp(
        base_priority * base_weight
        + subscriber_conversion * subscriber_weight
        + returning_viewer * returning_weight
    )

    promotion_cfg = audience_cfg.get("promotion_test") or {}
    min_growth = int(promotion_cfg.get("minimum_growth_score") or 85)
    min_subscriber = int(promotion_cfg.get("minimum_subscriber_conversion_score") or 80)
    predicted_candidate = growth_score >= min_growth and subscriber_conversion >= min_subscriber

    return {
        "subscriber_conversion_score": subscriber_conversion,
        "returning_viewer_score": returning_viewer,
        "continuation_score": continuation,
        "hook_strength_score": hook_strength,
        "standalone_payoff_score": payoff,
        "selection_priority_score": selection_priority,
        "promotion_test_candidate": predicted_candidate,
        "promotion_requires_observed_performance": True,
        "paid_boost_auto_enabled": False,
        "optimization_goal": "turn qualified viewers into returning viewers and followers without weakening quality gates",
    }


def normalized_candidate(raw: dict[str, Any], verified_at: str) -> dict[str, Any] | None:
    candidate = _original_normalized_candidate(raw, verified_at)
    if not candidate:
        return None
    report = _audience_report(candidate)
    candidate["audience_growth_v3"] = report
    ctx = candidate.get("source_context") if isinstance(candidate.get("source_context"), dict) else {}
    ctx["audience_growth_v3"] = report
    candidate["source_context"] = ctx
    return candidate


def diversify(candidates: list[dict[str, Any]], slot: str) -> list[dict[str, Any]]:
    semantically_grounded = [candidate for candidate in candidates if growth_v6._editorial_semantics_strong(candidate)]
    rejected = len(candidates) - len(semantically_grounded)
    if rejected:
        print({
            "event": "semantic_source_prefilter",
            "rejected": rejected,
            "kept": len(semantically_grounded),
            "reason": "fallback_not_downstream_contract_safe_or_semantically_weak",
        })
    if candidates and not semantically_grounded:
        growth_v6._mark_research_deferred(len(candidates), rejected)

    deduped = growth_v6._dedupe_story_clusters(semantically_grounded)
    enriched: list[dict[str, Any]] = []
    for candidate in deduped:
        if not isinstance(candidate.get("audience_growth_v3"), dict):
            report = _audience_report(candidate)
            candidate["audience_growth_v3"] = report
            ctx = candidate.get("source_context") if isinstance(candidate.get("source_context"), dict) else {}
            ctx["audience_growth_v3"] = report
            candidate["source_context"] = ctx
        enriched.append(candidate)

    eligible = [
        candidate
        for candidate in enriched
        if int((candidate.get("growth_v2") or {}).get("growth_score") or 0) >= 80
    ]
    ordered = sorted(
        eligible,
        key=lambda candidate: (
            int((candidate.get("audience_growth_v3") or {}).get("selection_priority_score") or 0),
            int((candidate.get("audience_growth_v3") or {}).get("subscriber_conversion_score") or 0),
            int((candidate.get("growth_v2") or {}).get("priority_score") or 0),
            int(candidate.get("score") or 0),
        ),
        reverse=True,
    )

    cfg = _config().get("selection") or {}
    selected: list[dict[str, Any]] = []
    scopes: dict[str, int] = {}
    for candidate in ordered:
        scope = str(candidate.get("trend_scope") or "")
        if scopes.get(scope, 0) >= 2:
            continue
        if any(str(item.get("title") or "").casefold() == str(candidate.get("title") or "").casefold() for item in selected):
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
    return _original_prompt(slot, now) + """

AUDIENCE GROWTH / FOLLOW CONVERSION:
- Optimize for qualified watch time AND a real reason to follow TAYVORIQ, not raw clicks alone.
- Prefer stories that deliver a complete standalone payoff but naturally support a specific next-video bridge within the same audience interest.
- Prefer repeatable audience pillars such as Germany in transformation, technology changing daily life, industry/mobility, AI and infrastructure when the current facts genuinely fit.
- Reject empty cliffhangers, generic 'follow for more' bait and forced series continuations.
- A candidate should make the viewer understand why this channel is worth returning to tomorrow.
- Paid promotion is NEVER triggered from prediction alone; only post-publish observed performance may qualify a small promotion test.
""".strip()


base.normalized_candidate = normalized_candidate
base.diversify = diversify
base.prompt_for = prompt_for

if __name__ == "__main__":
    raise SystemExit(base.main())
