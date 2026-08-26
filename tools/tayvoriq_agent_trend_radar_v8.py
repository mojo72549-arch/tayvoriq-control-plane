#!/usr/bin/env python3
from __future__ import annotations

"""Brand-safe growth overlay for the TAYVORIQ trend radar.

Keeps the current Growth V7 scoring and quality gates unchanged while making the
channel's non-sexual growth boundary explicit at the research/prompt layer.
"""

import tayvoriq_agent_trend_radar_v7 as growth_v7

base = growth_v7.base
_original_prompt = base.prompt_for


def prompt_for(slot, now):
    return _original_prompt(slot, now) + """

TAYVORIQ BRAND SAFETY — HARD REQUIREMENT:
- Reject sexualized, erotic, sexually suggestive, fetishized or pornographic topics and angles.
- Reject sexual or body-focused shock bait even when it appears to have high click or viral potential.
- Never use sexual content, sexual thumbnails, suggestive wording or innuendo as a growth lever.
- Prefer broadly shareable curiosity, consequence, surprise, technology, business, world-event and everyday-impact hooks.
- This brand-safety rule must not be traded off against virality, trend score or predicted follower conversion.

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
- Explain why the concrete detail matters to the viewer and what happens next (next date, release, decision, event step or practical consequence) when known.
- For event coverage such as Gamescom, name concrete confirmed games, publishers, exhibitors or features and state what is playable, announced, shown or merely expected when source-backed.
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
- Hashtags must be semantically tied to the actual story and its strongest searchable entities. For Gamescom coverage, for example, use the confirmed event/game/publisher names that are genuinely central to that candidate rather than generic gaming bait.
- Do NOT pad with generic reach-bait such as #fyp, #viral, #trending, #explorepage or #fürdich. Do not use #news merely because the item is a news story.
- Avoid duplicate synonyms and overbroad tags that do not help discovery. Strong specificity beats hashtag volume.
- Never put an unverified claim, rumor or speculative release detail into a hashtag.
""".strip()


base.prompt_for = prompt_for

if __name__ == "__main__":
    raise SystemExit(base.main())
