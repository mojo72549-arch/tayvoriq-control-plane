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
- Put the useful detail into the EXISTING schema: source_context.fallback_editorial_answers.facts; the what_happened, why_happening, personal_impact and action_now answers; source_context.factual_guardrails; and source_context.research_notes.
- Explicitly distinguish current or confirmed facts from announced or planned items and from rumor or speculation. Never elevate rumor or expectation to confirmed fact.
- Include at least ONE contextualizing number, comparison or date where credible and relevant.
- Explain why the concrete detail matters to the viewer and what happens next when known.
- Research must be rich enough to support a useful 45–60 second TAYVORIQ script without filler. If the evidence cannot support that depth, lower the candidate or reject it rather than padding the story.
- Never invent details merely to satisfy these counts. Evidence beats count.

TAYVORIQ SCRIPT HANDOFF — HARD REQUIREMENT:
- source_context.factual_guardrails.must_include should carry the 3–6 highest-value concrete details into production whenever the schema permits.
- source_context.factual_guardrails.must_not_claim should explicitly capture unsupported, rumored or ambiguous claims that a script writer might otherwise overstate.
- source_context.factual_guardrails.uncertainty_note should make timing or confirmation status explicit where necessary.
- source_context.research_notes should identify the strongest story spine and useful examples, not merely repeat source titles or the headline.
- The candidate should give production enough material to answer: What exactly happened? Which concrete examples prove it? Why is it relevant? What happens next?

TAYVORIQ HASHTAG HANDOFF — HARD REQUIREMENT:
- End source_context.research_notes with a compact line starting exactly with "HASHTAG_SEEDS:" followed by 5–8 topic-specific hashtag suggestions for production metadata.
- Prefer a deliberate mix: 1 exact event/topic tag, 1–3 concrete entity/product/person/place tags, 1 relevant category/community tag, and #TAYVORIQ when appropriate.
- Hashtags must be semantically tied to the actual story and its strongest searchable entities.
- Do NOT pad with generic reach-bait such as #fyp, #viral, #trending, #explorepage or #fuerdich. Do not use #news merely because the item is a news story.
- Avoid duplicate synonyms and overbroad tags that do not help discovery. Strong specificity beats hashtag volume.
- Never put an unverified claim, rumor or speculative release detail into a hashtag.
""".strip() + (("\n\n" + editorial_hints) if editorial_hints else "")


base.prompt_for = prompt_for

if __name__ == "__main__":
    raise SystemExit(base.main())
