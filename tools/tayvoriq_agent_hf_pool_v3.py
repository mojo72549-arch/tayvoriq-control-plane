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

    for index, lane in enumerate(passes, start=1):
        data, pass_chunks, model = hf.structure(
            f"{lane}\n\n{prompt}", token, records, f"{source_label}-pass{index}"
        )
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

    return {"candidates": combined[:18]}, chunks, "+".join(models)
