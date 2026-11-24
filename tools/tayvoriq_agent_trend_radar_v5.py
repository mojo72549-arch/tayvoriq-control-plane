#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import tayvoriq_agent_trend_radar_v4 as growth
import tayvoriq_agent_research_resilience_v2 as resilience
import tayvoriq_research_checkpoint as checkpoint
from tayvoriq_global_duplicate_gate_v1 import run_gate
from tayvoriq_retention_v5 import apply_trend_contract

base = growth.base
resilience.install()


def _identity(candidate: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    title = " ".join(str(candidate.get("title") or "").casefold().split())
    sources = tuple(sorted(str(url) for url in (candidate.get("sources") or []) if url))
    return title, sources


def _retention_ready(candidate) -> bool:
    try:
        apply_trend_contract(candidate, strict=True)
    except ValueError:
        return False
    return True


def _verified_editorial_repair(previous, candidate, *, ready=_retention_ready) -> bool:
    return _identity(previous) == _identity(candidate) and not ready(previous) and ready(candidate)

def _editorial_scan(slot: str, now: datetime):
    """Use short-lived, source-backed editorial input through the normal radar gates."""
    path = Path(f"state/tayvoriq-verified-research-{slot}.json")
    if not path.is_file():
        return None
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
        checked_at = datetime.fromisoformat(packet["checked_at"])
        if packet["slot"] != slot or packet["target_date"] != now.date().isoformat():
            return None
        if not timedelta(0) <= now - checked_at <= timedelta(hours=4):
            return None

        candidates = []
        chunks = {}
        for raw in packet["candidates"][:5]:
            sources = raw["sources"]
            if not 2 <= len(sources) <= 3:
                continue
            domains = set()
            origins = set()
            for source in sources:
                parsed = urlparse(source["url"])
                origin = source["reporting_origin"].strip().casefold()
                published = datetime.fromisoformat(source["published_at"])
                if (parsed.scheme != "https" or not parsed.hostname or not origin
                        or not source["supports"].strip()
                        or not timedelta(0) <= now - published <= timedelta(hours=72)):
                    break
                domains.add(parsed.hostname.removeprefix("www."))
                origins.add(origin)
            else:
                if len(domains) == len(origins) == len(sources):
                    candidates.append(raw)
                    chunks.update({s["url"]: {"uri": s["url"], "title": s["publisher"]} for s in sources})
        if len(candidates) >= 2 and len(chunks) >= 4:
            return {"candidates": candidates}, list(chunks.values()), "source-reviewed", "editorial"
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        print(json.dumps({"event": "editorial_packet_invalid", "path": str(path)}))
    return None


def main(*, repair_ready=_retention_ready) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", choices=["morning", "evening"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--prepared-only", action="store_true")
    args = parser.parse_args()

    now = datetime.now(ZoneInfo("Europe/Berlin"))
    editorial_scan = _editorial_scan(args.slot, now)
    if args.prepared_only and not editorial_scan:
        raise SystemExit("No fresh verified editorial packet for this slot")
    gemini_key = base.clean(os.getenv("GEMINI_API_KEY"), 500)
    groq_key = base.clean(os.getenv("GROQ_API_KEY"), 500)
    hf_token = base.clean(os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN"), 500)
    if not args.prepared_only and not gemini_key and not groq_key and not hf_token:
        raise SystemExit("No grounded trend provider configured")

    verified_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    selection_cfg = (growth._config().get("selection") or {})
    max_candidates = max(1, min(5, int(selection_cfg.get("telegram_candidates_max") or 5)))
    min_candidates = max(1, min(max_candidates, int(selection_cfg.get("telegram_candidates_min") or 4)))
    max_scans = max(1, min(3, int(selection_cfg.get("max_grounded_scans") or 2)))
    rescan_below_minimum = bool(selection_cfg.get("rescan_when_below_candidate_minimum", True))

    normalized: list[dict[str, Any]] = []
    seen: dict[tuple[str, tuple[str, ...]], int] = {}
    grounding_chunks: list[dict[str, str]] = []
    seen_chunks: set[str] = set()
    providers: list[str] = []
    models: list[str] = []
    previous_draft_titles = []
    base_rejections = []
    raw_count = 0
    chosen: list[dict[str, Any]] | None = None
    last_growth_error: BaseException | None = None

    series_candidate = base.load_active_series_candidate(verified_at)

    for scan_index in range(0 if editorial_scan else 1, 1 if args.prepared_only else max_scans + 1):
        prompt = base.prompt_for(args.slot, now)
        if scan_index > 1:
            prior_titles = [str(candidate.get("title") or "") for candidate in normalized]
            previous_error = str(last_growth_error or "")
            if "REGIONAL_RESCAN_REQUIRED" in previous_error or "REGIONAL_SELECTION_RESCAN_REQUIRED" in previous_error:
                prompt += (
                    "\n\nAUTOMATIC REGIONAL CONTRACT RESCAN: the previous scan did not yield enough contract-valid "
                    "local/Germany candidates. Run a FRESH, targeted Stuttgart/Baden-Wuerttemberg and Germany-only discovery pass. "
                    "Return distinct current stories that can survive every existing source, freshness, Growth, semantic, duplicate, "
                    "claim-coherence and brand-safety gate. Aim for at least 5 genuinely regional raw candidates so that at least 2 can "
                    "remain after validation. Do NOT relabel a global story as regional and do NOT weaken any threshold. "
                    "Use these verified stories only when correcting failed editorial fields without changing the evidence: "
                    + " | ".join(prior_titles[:12]) + "\nPrevious editorial checks: " + previous_error
                )
            else:
                prompt += (
                    f"\n\nAUTOMATIC BELOW-MINIMUM RESCAN: the previous scan left fewer than {min_candidates} candidates above the existing Growth reserve/source thresholds. "
                    "Find DISTINCT current stories/angles without weakening scores, source quality, novelty, claim coherence or duplicate rules. "
                    "A previously seen title and exact source pair may be repeated only to correct an editorially rejected draft. "
                    "Do not return another copy of a previously valid draft. Previous titles: "
                    + " | ".join(prior_titles[:12]) + "\nPrevious editorial checks: " + previous_error
                )

        if scan_index > 1 and base_rejections:
            prompt += "\nPrevious base-field findings for the source-bound drafts: " + json.dumps(
                base_rejections[:5], ensure_ascii=False)
        if scan_index > 1 and previous_draft_titles:
            prompt += "\nPreviously drafted source headlines: " + json.dumps(previous_draft_titles[:12], ensure_ascii=False)
        base_rejections.clear()
        data, chunks, model, provider_name = (
            editorial_scan if scan_index == 0 else base.grounded_call(prompt, gemini_key, groq_key)
        )
        providers.append(provider_name)
        models.append(model)
        rows = data.get("candidates") or []
        individual = (provider_name.endswith(("_rss", "_gdelt")) and len(rows) == 1
                      and rows[0].get("_retrieved_regional_assessment", {}).get("passed") is True
                      and len(chunks) == 2 and len(rows[0].get("sources", [])) == 2
                      and {s["url"] for s in rows[0]["sources"]} == {c["uri"] for c in chunks})
        if len(chunks) < 4 and not individual:
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
        draft_titles = [base.clean(item.get("title"), 180) for item in raw_candidates if isinstance(item, dict)]
        previous_draft_titles = list(dict.fromkeys(previous_draft_titles + [title for title in draft_titles if title]))
        raw_count += len(raw_candidates)
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            source_bound = provider_name.endswith(("_rss", "_gdelt"))
            assessment = raw.pop("_retrieved_regional_assessment", None)
            if source_bound and isinstance(assessment, dict) and not assessment.get("passed"):
                print(json.dumps({"event": "candidate_editorial_rejection", "title": raw.get("title"),
                                  "reason": assessment.get("reason") or "regional_scorecard",
                                  "details": assessment.get("issues"), "scores": assessment.get("scores")}, ensure_ascii=False))
                base_rejections.append({"title": base.clean(raw.get("title"), 180),
                                        "fields": assessment.get("issues") or [assessment.get("reason")]})
                continue
            candidate = base.normalized_candidate(raw, verified_at)
            if not candidate:
                title, _, _, _, _, issues = base.base_editorial_fields(raw)
                if issues:
                    base_rejections.append({"title": title, "fields": issues})
                continue
            if source_bound:
                if assessment:
                    candidate["source_context"]["regional_assessment"] = assessment
                # structure() rebuilt these fields from downloaded records after validate_pair().
                # Never accept model-authored provenance from a browser or prepared packet.
                original_sources = {source["url"]: source for source in raw["sources"]}
                for source in candidate["source_context"]["sources"]:
                    original = original_sources[source["url"]]
                    for field in ("publisher_headline", "source_date", "declared_origin",
                                  "source_record_sha256", "support_origin"):
                        if original.get(field):
                            source[field] = original[field]
            if scan_index == 0:
                context = candidate["source_context"]
                original_sources = {source["url"]: source for source in raw["sources"]}
                for source in context["sources"]:
                    original = original_sources[source["url"]]
                    source["published_at"] = original["published_at"]
                    source["reporting_origin"] = original["reporting_origin"]
            if scan_index == 0 or source_bound:
                duplicates = run_gate(requests_dir=Path("requests"), source_request_id="",
                                      topic=candidate["title"], source_context=candidate["source_context"])
                if not duplicates["passed"]:
                    print(json.dumps({"event": "candidate_editorial_rejection", "title": candidate["title"],
                                      "reason": "previous_request_duplicate",
                                      "prior_requests": [row["request_id"] for row in duplicates["blocked_matches"]]},
                                     ensure_ascii=False))
                    continue
                candidate["source_context"]["duplicate_check"] = {
                    key: duplicates[key] for key in ("state", "content_fingerprint_sha256", "history_candidates_checked")
                }
            if source_bound and assessment and assessment.get("passed") and repair_ready(candidate):
                original_model = raw.get("_checkpoint_model") or model
                candidate["source_context"]["editorial_model"] = original_model
                checkpoint.remember({k: v for k, v in raw.items() if k != "_checkpoint_model"},
                                    assessment, original_model)
            key = _identity(candidate)
            if key in seen:
                if scan_index > 1 and provider_name.endswith(("_rss", "_gdelt")):
                    position = seen[key]
                    if _verified_editorial_repair(normalized[position], candidate, ready=repair_ready):
                        normalized[position] = candidate
                        print(json.dumps({"event": "editorial_candidate_replaced", "title": candidate["title"],
                                          "same_source_urls": True}, ensure_ascii=False))
                continue
            seen[key] = len(normalized)
            normalized.append(candidate)

        candidate_pool = list(normalized)
        allow_single = individual and len(candidate_pool) == 1 and not os.getenv("TAYVORIQ_RESEARCH_SELECTION_ID")
        if series_candidate and _identity(series_candidate) not in {_identity(c) for c in candidate_pool}:
            candidate_pool.append(series_candidate)

        try:
            if allow_single and len(candidate_pool) == 1:
                selected = base.diversify(candidate_pool, args.slot, allow_single=True)
                if len(selected) == 1:
                    min_candidates = 1
            else:
                selected = base.diversify(candidate_pool, args.slot)
            if min_candidates <= len(selected) <= max_candidates:
                chosen = selected
                break
            raise SystemExit(
                f"GROWTH_RESCAN_REQUIRED: only {len(selected)} candidates reached the strong-candidate threshold; minimum is {min_candidates}"
            )
        except SystemExit as exc:
            last_growth_error = exc
            message = str(exc)
            rescan_signal = any(signal in message for signal in (
                "GROWTH_RESCAN_REQUIRED",
                "REGIONAL_RESCAN_REQUIRED",
                "REGIONAL_SELECTION_RESCAN_REQUIRED",
            ))
            if (
                rescan_signal
                and rescan_below_minimum
                and scan_index < max_scans
            ):
                regional_rescan = (
                    "REGIONAL_RESCAN_REQUIRED" in message
                    or "REGIONAL_SELECTION_RESCAN_REQUIRED" in message
                )
                print(json.dumps({
                    "event": "growth_rescan",
                    "reason": "regional_contract_below_minimum" if regional_rescan else "below_minimum_candidates",
                    "scan": scan_index,
                    "valid_pool": len(candidate_pool),
                    "minimum_required": min_candidates,
                    "error": message,
                    "quality_gates_weakened": False,
                }, ensure_ascii=False))
                continue
            if rescan_signal and not args.prepared_only:
                resilience.defer_editorial(args.slot)
            raise

    if chosen is None:
        if last_growth_error is not None:
            raise last_growth_error
        raise SystemExit(
            f"Need {min_candidates}-{max_candidates} contract-valid grounded trends after {max_scans} scan(s), got 0"
        )

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
    if len(chosen) == 1:
        request["mode"] = "single_verified_topic"
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
        "candidate_count_policy": f"quality_driven_{min_candidates}_to_{max_candidates}",
        "candidate_minimum": min_candidates,
        "candidate_maximum": max_candidates,
        "weak_fill_allowed": False,
    }
    Path(args.audit_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.audit_output).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "selection_id": selection_id,
        "slot": args.slot,
        "providers": providers,
        "scan_count": len(providers),
        "selected_count": len(chosen),
        "candidate_minimum": min_candidates,
        "selected": [trend["title"] for trend in chosen],
        "growth_scores": [int((trend.get("growth_v2") or {}).get("growth_score") or 0) for trend in chosen],
    }, ensure_ascii=False))
    return 0


base.main = main

if __name__ == "__main__":
    raise SystemExit(main())
