#!/usr/bin/env python3
from __future__ import annotations

"""Brand-safe growth overlay for the TAYVORIQ trend radar.

Keeps the current Growth V7 scoring and quality gates unchanged while making the
channel's non-sexual growth boundary explicit at the research/prompt layer.
"""

import json
from pathlib import Path

import tayvoriq_agent_trend_radar_v7 as growth_v7

base = growth_v7.base
_original_prompt = base.prompt_for
_original_diversify = base.diversify

_BROAD_REACH = {"germany", "europe", "global"}
_SCOPE_BONUS = {"global": 18, "europe": 16, "germany": 13, "local": -45}


def _reach_gate(candidate):
    """Return a conservative audience-reach score without inventing signals."""
    relevance = str(candidate.get("regional_relevance") or "").strip().lower()
    audience = candidate.get("audience_growth_v3") if isinstance(candidate.get("audience_growth_v3"), dict) else {}
    growth = candidate.get("growth_v2") if isinstance(candidate.get("growth_v2"), dict) else {}
    source_context = candidate.get("source_context") if isinstance(candidate.get("source_context"), dict) else {}
    independent = int(source_context.get("independent_news_count") or 0)
    base_score = int(audience.get("selection_priority_score") or growth.get("priority_score") or candidate.get("score") or 0)
    viral = int((candidate.get("criteria") or {}).get("viralitaet") or 0)
    freshness = int((candidate.get("criteria") or {}).get("aktualitaet") or 0)
    cross_signal = int((source_context.get("reach_gate") or {}).get("cross_platform_signal_count") or 0) if isinstance(source_context.get("reach_gate"), dict) else 0
    return (
        base_score
        + _SCOPE_BONUS.get(relevance, -30)
        + min(8, independent * 2)
        + min(8, cross_signal * 2)
        + (viral // 20)
        + (freshness // 25)
    )


def _selection_key(candidate):
    audience = candidate.get("audience_growth_v3") if isinstance(candidate.get("audience_growth_v3"), dict) else {}
    growth = candidate.get("growth_v2") if isinstance(candidate.get("growth_v2"), dict) else {}
    return (
        _reach_gate(candidate),
        int(audience.get("subscriber_conversion_score") or 0),
        int(growth.get("growth_score") or 0),
        int(candidate.get("score") or 0),
    )


def _mark_research_deferred(reason: str, **meta):
    """Persist a machine-readable transient research defer marker.

    The orchestrator already treats this file as an internal saturation/defer
    signal and suppresses the misleading red user-facing failure notification.
    This never lowers ranking, source, regional or brand-safety gates.
    """

    payload = {
        "schema": "tayvoriq-research-deferred-v1",
        "reason": str(reason or "RESEARCH_TEMPORARILY_INCOMPLETE"),
        "quality_gates_weakened": False,
        **meta,
    }
    Path("/tmp/tayvoriq-research-deferred.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def diversify(candidates, slot):
    cfg = growth_v7._config().get("selection") or {}
    minimum = int(cfg.get("telegram_candidates_min") or 4)

    # Reach-first: local-only stories do not enter Telegram by default.
    broad = [
        candidate for candidate in candidates
        if str(candidate.get("regional_relevance") or "").strip().lower() in _BROAD_REACH
    ]
    if len(broad) < minimum:
        _mark_research_deferred(
            "REACH_RESCAN_REQUIRED",
            slot=str(slot),
            broad_reach_candidates=len(broad),
            required_broad_reach=minimum,
            total_candidates=len(candidates),
        )
        raise SystemExit(
            f"REACH_RESCAN_REQUIRED: only {len(broad)} Germany/Europe/global candidates passed all gates"
        )

    selected = _original_diversify(sorted(broad, key=_selection_key, reverse=True), slot)
    selected = [
        candidate for candidate in selected
        if str(candidate.get("regional_relevance") or "").strip().lower() in _BROAD_REACH
    ]
    if len(selected) < minimum:
        _mark_research_deferred(
            "REACH_SELECTION_RESCAN_REQUIRED",
            slot=str(slot),
            selected=len(selected),
            required=minimum,
        )
        raise SystemExit(
            f"REACH_RESCAN_REQUIRED: selected={len(selected)}; require at least {minimum} broad-reach candidates"
        )

    for candidate in selected:
        ctx = candidate.get("source_context") if isinstance(candidate.get("source_context"), dict) else {}
        gate = ctx.get("reach_gate") if isinstance(ctx.get("reach_gate"), dict) else {}
        gate.update({
            "policy": "NATIONAL_EU_GLOBAL_FIRST",
            "scope": str(candidate.get("regional_relevance") or "").strip().lower(),
            "local_only_rejected": False,
            "reach_score": _reach_gate(candidate),
        })
        ctx["reach_gate"] = gate
        candidate["source_context"] = ctx

    return sorted(selected, key=_selection_key, reverse=True)



def _editorial_hint_text(slot, now):
    """Load dated, source-backed candidate hints without bypassing live verification."""
    paths = [
        Path(f"state/tayvoriq-editorial-hints-{slot}.json"),
        Path("state/tayvoriq-editorial-hints.json"),
    ]
    data = None
    for path in paths:
        if not path.is_file():
            continue
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(candidate.get("slot") or "").strip() != str(slot):
            continue
        data = candidate
        break
    if not isinstance(data, dict):
        return ""
    target_date = str(data.get("target_date") or "").strip()
    current_date = now.date().isoformat() if hasattr(now, "date") else str(now)[:10]
    if target_date != current_date:
        return ""
    candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
    if not candidates:
        return ""
    lines = [
        "TAYVORIQ PRE-RESEARCHED EDITORIAL HINTS — VERIFY LIVE, NEVER FORCE:",
        "- These candidates were researched in advance for this exact date and slot.",
        "- Re-check freshness, source coherence, duplicate status, factual status and trend strength now.",
        "- Prefer candidates that still pass all normal gates; replace any item that is stale, superseded, weak or contradicted.",
        "- These hints NEVER weaken source, duplicate, brand-safety, quality or claim-verification gates.",
    ]
    for i, item in enumerate(candidates[:8], 1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        why = str(item.get("why_now") or "").strip()
        sources = [str(x).strip() for x in (item.get("sources") or []) if str(x).strip()]
        if not title:
            continue
        lines.append(f"{i}. {title}")
        if why:
            lines.append(f"   Why now: {why}")
        if sources:
            lines.append("   Pre-researched sources: " + " | ".join(sources[:4]))
    return "\n".join(lines)


def prompt_for(slot, now):
    editorial_hints = _editorial_hint_text(slot, now)
    return _original_prompt(slot, now) + """

TAYVORIQ REACH POTENTIAL GATE — HARD RANKING REQUIREMENT:
- The final Telegram ranking is reach-first, not locality-first.
- Default eligible scope is Germany-wide, Europe-wide or global. Purely local/city/state stories are rejected before Telegram unless they demonstrably break out to a national or international audience.
- Do NOT fill the list just because a story is recent. "Trending somewhere" is not enough.
- Prefer stories with verified momentum, broad audience relevance, strong short-form hookability, visual potential and at least two independent credible sources.
- A Germany-wide story can outrank a global story when its momentum and viewer relevance are stronger; geography is not a substitute for momentum.
- Global AI/Tech/Science/Sports/World stories are fully eligible without an artificial Germany angle when their audience potential is genuinely broad.
- For every candidate, set regional_relevance accurately to local|germany|europe|global.
- Put a source_context.reach_gate object on each candidate when possible with: scope, why_now, momentum_evidence, cross_platform_signal_count, and breakout_proof.
- Never invent cross-platform evidence. Use 0 when it is not verified.
- If fewer than 4 strong broad-reach candidates pass, fail closed and rescan instead of forcing weak/local filler.
- A rejected Telegram selection is part of duplicate history: do not immediately recycle the same underlying stories with rewritten headlines.

TAYVORIQ STRATEGIC ENTITY SWEEP — DISCOVERY REQUIREMENT:
- Before finalizing candidates, explicitly check current high-impact developments around Microsoft, OpenAI, Google/Alphabet, Apple, Meta, Amazon/AWS and Nvidia only when they have a verified Germany/Europe angle or direct audience consequence.
- For Microsoft, actively check Azure, Windows, Copilot, Microsoft 365, GitHub, Xbox and major AI/cloud/business moves instead of relying on generic AI or technology searches to surface them accidentally.
- This is a discovery-coverage rule, NOT a quota: never force Microsoft or any named company into the final five when its story is weaker, stale, duplicated or insufficiently sourced.
- Do not suppress a strong company story merely because another AI/technology candidate already exists. Deduplicate by the underlying event and viewer takeaway, not by the broad category or company size.
- A strategically watched entity that has a fresh, independently verified story competing on the normal scores must be allowed into the candidate pool and ranked normally.

TAYVORIQ BRAND SAFETY — HARD REQUIREMENT:
- Reject sexualized, erotic, sexually suggestive, fetishized or pornographic topics and angles.
- Reject sexual or body-focused shock bait even when it appears to have high click or viral potential.
- Never use sexual content, sexual thumbnails, suggestive wording or innuendo as a growth lever.
- Prefer broadly shareable curiosity, consequence, surprise, technology, business, world-event and everyday-impact hooks.
- This brand-safety rule must not be traded off against virality, trend score or predicted follower conversion.

TAYVORIQ DUPLICATE EXCLUSION — HARD REQUIREMENT:
- Do not propose any topic, event or core story that TAYVORIQ has already surfaced, selected, approved, produced or published, even if the headline or angle is rewritten.
- Compare the candidate semantically against prior requests, selections, series episodes and publication history; same underlying event or same viewer takeaway means duplicate.
- A follow-up is allowed only when a genuinely material new development changes the story itself, and the new development must be the hook and majority of the value.
- Hard-exclude known recently used/surfaced families unless such a material new development exists: earthquake/tsunami/volcano series, solar eclipse, Nvidia/AI-stock pressure, Stuttgart 21 game/demo, Bosch humanoid robots in Buehl, ChatGPT ads in Germany, VW mega-crisis/restructuring, courts/chatbots, DFB camp rule experiment, oil/Hormuz/sprit prices, MHP/Porsche-TCS sale, Helge Schneider Ellwangen, ESA/Uni-Stuttgart satellite re-entry, El Nino, humanoid robot sprint record and Gamescom 2026.
- Morning and evening on the same target date must also be semantically distinct from each other. Never recycle a morning candidate in the evening list with a different wording.
- If duplicate status is uncertain, reject the candidate and choose a fresh story.

TAYVORIQ VARIETY — VERIFIED PLAYFUL WILDCARD:
- When the live source pool supports it, try to include ONE surprising, playful, quirky or unusual but real candidate alongside harder news.
- Good wildcard families include games, unusual experiments, odd engineering, local curiosities, science oddities, creator phenomena and unexpected everyday stories.
- The wildcard must pass the SAME freshness, two-independent-source, claim-coherence, duplicate, visual and Growth thresholds as every other candidate.
- Never force a wildcard when the evidence or quality is weaker than the existing gates.
- The wildcard remains subject to the non-sexual brand-safety boundary above.

TAYVORIQ CONTENT DEPTH — HARD REQUIREMENT:
- Never submit a candidate whose source context only restates the headline.
- For every candidate, research and retain at least THREE concrete, source-backed facts whenever they are available.
- Where the topic naturally permits it, retain at least TWO specific named examples or entities: games, models, companies, products, places, people, dates, features or comparable concrete details.
- IMPORTANT CONTRACT SEPARATION: deep research belongs in source supports, factual_guardrails and research_notes. Do NOT stuff long-form research prose into the five fallback_editorial_answers.
- The five fallback_editorial_answers are a compact factual compatibility contract and MUST continue to obey the inherited STRICT FALLBACK CONTRACT: one natural sentence per field, 5–15 words each, 38–49 words total, explicit causal why, explicit 'Für dich' relevance and a viewer-facing concrete action verb.
- NEW STORY-FIRST V2: every newly generated candidate MUST also set source_context.editorial_story_contract_version = 2 and source_context.story_first_script_body.
- story_first_script_body is the spoken editorial mini-story, 38–49 words, at least 3 natural sentences, and MUST NOT simply concatenate the five fallback answers.
- Required narrative spine: surprising/consequential hook -> only the context needed to understand it -> cause/development -> verified tension/counterposition when supported -> meaning/outlook.
- Use connective narration such as aber, doch, denn, weil, gleichzeitig, brisant or entscheidend where natural. Do not manufacture conflict merely to satisfy the pattern.
- Avoid the form-like spoken sequence 'Betroffen sind ... Für dich ... Beobachte/Achte/Prüfe ...'. Those compatibility fields remain available for validation but are not the preferred spoken copy.
- Every claim in story_first_script_body must be supported by source_context.sources, factual_guardrails or other verified source material in the same candidate. Never add a dramatic claim not present in the evidence.
- Use source_context.research_notes and source support fields for extra examples, names, dates, numbers and context that production may draw on when building a richer story without invalidating the compatibility contract.
- Explicitly distinguish current or confirmed facts from announced or planned items and from rumor or speculation. Never elevate rumor or expectation to confirmed fact.
- Include at least ONE contextualizing number, comparison or date where credible and relevant in the research evidence; it does not need to be forced into the compact five-answer fallback if doing so breaks its contract.
- Explain why the concrete detail matters to the viewer and what happens next when known.
- Research must be rich enough to support a useful TAYVORIQ story, while the immutable fallback itself remains safely renderable at the configured 35-second target. If the evidence cannot support both, lower the candidate or reject it rather than padding the fallback.
- Never invent details merely to satisfy these counts. Evidence beats count.

TAYVORIQ SCRIPT HANDOFF — HARD REQUIREMENT:
- source_context.factual_guardrails.must_include should carry the 3–6 highest-value concrete details into production whenever the schema permits.
- source_context.factual_guardrails.must_not_claim should explicitly capture unsupported, rumored or ambiguous claims that a script writer might otherwise overstate.
- source_context.factual_guardrails.uncertainty_note should make timing or confirmation status explicit where necessary.
- source_context.research_notes should identify the strongest story spine and useful examples, not merely repeat source titles or the headline.
- fallback_editorial_answers must remain downstream-contract-safe; never place editor instructions such as 'Im Short ...' in action_now. action_now is always a concrete viewer action.
- The candidate should give production enough evidence to answer: What exactly happened? Which concrete examples prove it? Why is it relevant? What happens next?

TAYVORIQ HASHTAG HANDOFF — HARD REQUIREMENT:
- End source_context.research_notes with a compact line starting exactly with "HASHTAG_SEEDS:" followed by 5–8 topic-specific hashtag suggestions for production metadata.
- Prefer a deliberate mix: 1 exact event/topic tag, 1–3 concrete entity/product/person/place tags, 1 relevant category/community tag, and #TAYVORIQ when appropriate.
- Hashtags must be semantically tied to the actual story and its strongest searchable entities.
- Do NOT pad with generic reach-bait such as #fyp, #viral, #trending, #explorepage or #fuerdich. Do not use #news merely because the item is a news story.
- Avoid duplicate synonyms and overbroad tags that do not help discovery. Strong specificity beats hashtag volume.
- Never put an unverified claim, rumor or speculative release detail into a hashtag.
""".strip() + (("\n\n" + editorial_hints) if editorial_hints else "")


base.diversify = diversify
base.prompt_for = prompt_for

if __name__ == "__main__":
    raise SystemExit(base.main())
