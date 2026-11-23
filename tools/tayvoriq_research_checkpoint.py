"""Reuse one slot's qualified drafts only while both live source records still match."""
from datetime import datetime
from os import getenv
from pathlib import Path
from zoneinfo import ZoneInfo

from tayvoriq_provider_health_v1 import read, write
from tayvoriq_regional_relevance import evaluate
from tayvoriq_source_evidence_v1 import source_support, validate_pair


def _state():
    value = getenv("TAYVORIQ_RESEARCH_CHECKPOINT_FILE")
    slot = getenv("TAYVORIQ_RESEARCH_SLOT")
    if not value or slot not in {"morning", "evening"}:
        return None, {}
    path = Path(value)
    scope = [datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat(), slot,
             getenv("TAYVORIQ_RESEARCH_SELECTION_ID", "")]
    try:
        state = read(path)
    except (OSError, ValueError):
        state = {}
    if state.get("scope") != scope or not isinstance(state.get("drafts"), list):
        state = {"scope": scope, "drafts": []}
    state["drafts"] = [entry for entry in state["drafts"] if isinstance(entry, dict)
                       and isinstance(entry.get("candidate"), dict)
                       and isinstance(entry.get("assessment"), dict)
                       and isinstance(entry["assessment"].get("evidence"), dict)
                       and isinstance(entry.get("model"), str)
                       and isinstance(entry["candidate"].get("sources"), list)
                       and len(entry["candidate"]["sources"]) == 2
                       and all(isinstance(s, dict) and s.get("url") and s.get("source_id")
                               for s in entry["candidate"]["sources"])]
    return path, state


def remember(raw, assessment, model):
    path, state = _state()
    if not path or not assessment.get("passed"):
        return
    sources = raw.get("sources", [])
    if len(sources) != 2 or not all(s.get("source_record_sha256") for s in sources):
        return
    drafts = state["drafts"]
    pair = {s["url"] for s in sources}
    others = [d for d in drafts if {s["url"] for s in d["candidate"]["sources"]} != pair]
    entry = {"candidate": raw, "assessment": assessment, "model": model}
    if entry not in drafts:
        state["drafts"] = [entry, *others][:5]
        write(path, state)
        print({"event": "research_draft_saved", "title": raw["title"]})


def current(records):
    _, state = _state()
    by_url = {r["url"]: r for r in records}
    verified = []
    for entry in state.get("drafts", []):
        raw = entry["candidate"]
        sources = raw["sources"]
        fresh = [by_url.get(s["url"]) for s in sources]
        if not all(fresh) or validate_pair(raw, fresh):
            continue
        if any(source_support(record)[1] != s["source_record_sha256"] or
               record.get("seen_date") != s.get("source_date") or
               (record.get("origin") or "") != (s.get("declared_origin") or "")
               for record, s in zip(fresh, sources)):
            continue
        saved = entry["assessment"]
        card = {**saved, "evidence": {s["source_id"]: saved["evidence"].get(s["url"]) for s in sources}}
        assessment = evaluate(card, sources)
        if assessment.get("passed"):
            verified.append({**raw, "_retrieved_regional_assessment": assessment,
                             "_checkpoint_model": entry["model"]})
    return verified
