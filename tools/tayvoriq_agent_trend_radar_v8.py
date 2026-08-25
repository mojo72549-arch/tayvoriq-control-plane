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
""".strip()


base.prompt_for = prompt_for

if __name__ == "__main__":
    raise SystemExit(base.main())
