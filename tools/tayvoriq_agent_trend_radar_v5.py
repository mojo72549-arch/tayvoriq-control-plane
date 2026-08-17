#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import tayvoriq_agent_trend_radar_v4 as growth
import tayvoriq_agent_research_resilience_v2 as resilience

base = growth.base
resilience.install()


def _identity(candidate: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    title = " ".join(str(candidate.get("title") or "").casefold().split())
    sources = tuple(sorted(str(url) for url in (candidate.get("sources") or []) if url))
    return title, sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", choices=["morning", "evening"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    gemini_key = base.clean(os.getenv("GEMINI_API_KEY"), 500)
    groq_key = base.clean(os.getenv("GROQ_API_KEY"), 500)
    hf_token = base.clean(os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN"), 500)
    if not gemini_key and not groq_key and not hf_token:
        raise SystemExit("No grounded trend provider configured")

    now = datetime.now(ZoneInfo("Europe/Berlin"))
    verified_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    selection_cfg = (growth._config().get("selection") or {})
    max_scans = max(1, min(3, int(selection_cfg.get("max_grounded_scans") or 2)))

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    grounding_chunks: list[dict[str, str]] = []
    seen_chunks: set[str] = set()
    providers: list[str] = []
    models: list[str] = []
    raw_count = 0
    chosen: list[dict[str, Any]] | None = None
    last_growth_error: BaseException | None = None

    series_candidate = base.load_active_series_candidate(verified_at)

    for scan_index in range(1, max_scans + 1):
        prompt = base.prompt_for(args.slot, now)
        if scan_index > 1:
            prior_titles = [str(candidate.get("title") or "") for candidate in normalized]
            prompt += (
                "\n\nAUTOMATIC ZERO-RESULT RESCAN: the previous scan produced no candidate above the existing Growth reserve threshold. "
                "Find DISTINCT current stories/angles without weakening scores or source rules. Exclude already-seen titles or equivalent angles: "
                + " | ".join(prior_titles[:12])
            )

        data, chunks, model, provider_name = base.grounded_call(prompt, gemini_key, groq_key)
        providers.append(provider_name)
        models.append(model)
        if len(chunks) < 4:
            if scan_index < max_scans:
                print(json.dumps({"event": "growth_rescan", "reason": "weak_grounding", "scan": scan_index, "chunks": len(chunks)}, ensure_ascii=False))
                continue
            raise SystemExit(f"Grounding evidence too weak after {scan_index} scan(s): only {len(chunks)} web chunks")

        for chunk in chunks:
            uri = str(chunk.get("uri") or "").strip()
            if uri and uri not in seen_chunks:
                seen_chunks.add(uri)
                grounding_chunks.append(chunk)

        raw_candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
        raw_count += len(raw_candidates)
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            candidate = base.normalized_candidate(raw, verified_at)
            if not candidate:
                continue
            key = _identity(candidate)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(candidate)

        candidate_pool = list(normalized)
        if series_candidate and _identity(series_candidate) not in {_identity(c) for c in candidate_pool}:
            candidate_pool.append(series_candidate)

        try:
            selected = base.diversify(candidate_pool, args.slot)
            if 1 <= len(selected) <= int(selection_cfg.get("telegram_candidates_max") or 5):
                chosen = selected
                break
        except SystemExit as exc:
            last_growth_error = exc
            message = str(exc)
            if "GROWTH_RESCAN_REQUIRED" in message and scan_index < max_scans:
                print(json.dumps({
                    "event": "growth_rescan",
                    "reason": "zero_reserve_candidates",
                    "scan": scan_index,
                    "valid_pool": len(candidate_pool),
                    "error": message,
                }, ensure_ascii=False))
                continue
            raise

    if chosen is None:
        if last_growth_error is not None:
            raise last_growth_error
        raise SystemExit(f"Need at least 1 contract-valid grounded trend after {max_scans} scan(s), got 0")

    selection_id = f"{now:%Y%m%d}-{args.slot}-agentv2"
    for index, trend in enumerate(chosen, start=1):
        trend["id"] = str(index)

    request = {
        "date": now.strftime("%Y-%m-%d"),
        "slot": args.slot,
        "created_at": verified_at,
        "selection_id": selection_id,
        "selected_trend_id": None,
        "agent_orchestrator": "v2",
        "trends": chosen,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    audit = {
        "selection_id": selection_id,
        "slot": args.slot,
        "provider": "+".join(providers),
        "model": "+".join(models),
        "grounding_chunks": grounding_chunks,
        "candidate_count": raw_count,
        "valid_count": len(normalized) + (1 if series_candidate else 0),
        "selected_count": len(chosen),
        "series_candidate_injected": bool(series_candidate),
        "quality_gates_weakened": False,
        "grounded_scan_count": len(providers),
        "growth_rescan_used": len(providers) > 1,
        "max_grounded_scans": max_scans,
        "candidate_count_policy": "quality_driven_1_to_5",
    }
    Path(args.audit_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.audit_output).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "selection_id": selection_id,
        "slot": args.slot,
        "providers": providers,
        "scan_count": len(providers),
        "selected_count": len(chosen),
        "selected": [trend["title"] for trend in chosen],
        "growth_scores": [int((trend.get("growth_v2") or {}).get("growth_score") or 0) for trend in chosen],
    }, ensure_ascii=False))
    return 0


base.main = main

if __name__ == "__main__":
    raise SystemExit(main())
