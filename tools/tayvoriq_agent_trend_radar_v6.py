#!/usr/bin/env python3
from __future__ import annotations

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
                # Same two or more independent URLs means the radar is looking at
                # the same underlying event/claim cluster under another title.
                if len(signature & existing) >= 2:
                    duplicate = True
                    break
        if duplicate:
            continue
        kept.append(candidate)
        signatures.append(signature)
    return kept


def diversify(candidates: list[dict[str, Any]], slot: str) -> list[dict[str, Any]]:
    return _original_diversify(_dedupe_story_clusters(candidates), slot)


base.diversify = diversify

if __name__ == "__main__":
    raise SystemExit(base.main())
