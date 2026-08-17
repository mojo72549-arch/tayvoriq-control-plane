#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tayvoriq_agent_trend_radar_v3 as v3

base = v3.base
CONFIG_PATH = Path("config/tayvoriq_growth_runtime_v2.json")
_original_normalize = base.normalized_candidate
_original_prompt = base.prompt_for


def _config() -> dict[str, Any]:
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _clamp(value: float) -> int:
    return max(0, min(100, int(round(value))))


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
    cfg = _config().get("selection") or {}
    if int(candidate.get("score") or 0) < int(cfg.get("base_quality_min") or 75):
        return None
    report = _growth(candidate)
    candidate["growth_v2"] = report
    candidate["source_context"]["growth_v2"] = report
    return candidate


def diversify(candidates: list[dict[str, Any]], slot: str) -> list[dict[str, Any]]:
    cfg = _config().get("selection") or {}
    reserve_min = 80
    eligible = [c for c in candidates if int((c.get("growth_v2") or {}).get("growth_score") or 0) >= reserve_min]
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
    ) + "\n- An active series episode has NO reserved slot. Treat it as a candidate only if its current relevance and growth potential compete with fresh trends."


base.normalized_candidate = normalized_candidate
base.diversify = diversify
base.prompt_for = prompt_for

if __name__ == "__main__":
    raise SystemExit(base.main())
