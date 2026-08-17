from __future__ import annotations

import json
from typing import Any

import tayvoriq_agent_hf_v2 as hf


def _candidate_key(candidate: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    title = " ".join(str(candidate.get("title") or "").casefold().split())
    urls = tuple(sorted(
        str(source.get("url") or "").strip()
        for source in (candidate.get("sources") or [])
        if isinstance(source, dict) and source.get("url")
    ))
    return title, urls


def _lane_records(records: list[dict[str, str]], index: int) -> list[dict[str, str]]:
    if index == 1:
        return records
    keywords = {
        2: (
            " ai ", "ki ", "tech", "cyber", "wirtschaft", "econom", "business", "energy", "energie",
            "auto", "car ", "mobil", "transport", "rail", "bahn", "germany", "deutschland", "stuttgart",
            "baden", "creator", "media", "internet", "software", "chip", "robot",
        ),
        3: (
            "world", "welt", "science", "wissenschaft", "nature", "natur", "space", "raumfahrt", "climate",
            "klima", "fire", "brand", "storm", "sturm", "flood", "flut", "earthquake", "erdbeben", "volcano",
            "vulkan", "tsunami", "sport", "football", "fußball", "fussball", "athlet", "ocean", "ozean",
        ),
    }[index]
    matched = []
    for record in records:
        blob = f" {record.get('title','')} {record.get('context','')} ".casefold()
        if any(keyword in blob for keyword in keywords):
            matched.append(record)
    domains = {str(record.get("domain") or "") for record in matched if record.get("domain")}
    if len(matched) < 12 or len(domains) < 2:
        return records
    return matched[:80]


def structure(prompt: str, token: str, records: list[dict[str, str]], source_label: str = "independent-source-pool"):
    passes = [
        "Build the strongest broad current-news pool. Prioritize breakout potential, Germany/Europe relevance and visual explainability.",
        "Build an ALTERNATIVE pool. Prefer technology/AI, business/economy, mobility/energy, Germany/local and creator/media stories not chosen in a generic first pass.",
        "Build another ALTERNATIVE pool. Prefer world/society, science/nature, sports and unusual explainable developments; avoid repeating obvious lead stories when other supported stories exist.",
    ]
    combined: list[dict[str, Any]] = []
    chunks: list[dict[str, str]] = []
    seen_candidates: set[tuple[str, tuple[str, ...]]] = set()
    seen_chunks: set[str] = set()
    models: list[str] = []
    pass_errors: list[str] = []

    for index, lane in enumerate(passes, start=1):
        scoped_records = _lane_records(records, index)
        print(json.dumps({
            "event": "hf_pool_scope",
            "pass": index,
            "records": len(scoped_records),
            "publishers": len({r.get('domain') for r in scoped_records if r.get('domain')}),
        }, ensure_ascii=False))
        try:
            data, pass_chunks, model = hf.structure(
                f"{lane}\n\n{prompt}", token, scoped_records, f"{source_label}-pass{index}"
            )
        except Exception as exc:
            pass_errors.append(f"pass{index}:{type(exc).__name__}:{exc}")
            print(json.dumps({
                "event": "hf_pool_pass_failed",
                "pass": index,
                "preserved_candidates": len(combined),
                "error": f"{type(exc).__name__}: {exc}",
            }, ensure_ascii=False))
            continue

        models.append(model)
        for candidate in data.get("candidates") or []:
            if not isinstance(candidate, dict) or len(candidate.get("sources") or []) != 2:
                continue
            key = _candidate_key(candidate)
            if not key[0] or key in seen_candidates:
                continue
            seen_candidates.add(key)
            combined.append(candidate)
        for chunk in pass_chunks:
            uri = str(chunk.get("uri") or "").strip()
            if not uri or uri in seen_chunks:
                continue
            seen_chunks.add(uri)
            chunks.append(chunk)
        print(json.dumps({
            "event": "hf_pool_pass",
            "pass": index,
            "unique_candidates": len(combined),
            "unique_grounding_chunks": len(chunks),
        }, ensure_ascii=False))
        if len(combined) >= 12:
            break

    if not combined:
        raise RuntimeError("all HF fallback passes failed: " + " | ".join(pass_errors))

    print(json.dumps({
        "event": "hf_pool_complete",
        "unique_candidates": len(combined),
        "unique_grounding_chunks": len(chunks),
        "failed_passes": len(pass_errors),
    }, ensure_ascii=False))
    return {"candidates": combined[:18]}, chunks, "+".join(models) or "hf-pool-partial"
