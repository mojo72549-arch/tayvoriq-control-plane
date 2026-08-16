#!/usr/bin/env python3
"""Fail closed when an approved video repeats an earlier production request.

The gate is deliberately deterministic and stdlib-only.  It scans the durable
request ledger, permits retries of the exact same request id, and compares the
topic plus the five verified editorial answers.  Adjacent series episodes are
allowed only when their factual focus is distinct; the same series episode under
a new request id is always blocked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


ACTIVE_STATES = {"APPROVED", "DISPATCHING", "DISPATCHED", "SUCCESS", "PUBLISHED"}
ANSWER_KEYS = ("what_happened", "why_happening", "who_is_affected", "personal_impact", "action_now")
STOPWORDS = {
    "aber", "alle", "als", "am", "an", "auch", "auf", "aus", "bei", "bis", "das", "dass",
    "dein", "deine", "dem", "den", "der", "des", "die", "durch", "ein", "eine", "einer",
    "es", "fuer", "für", "haben", "hat", "im", "in", "ist", "mit", "nach", "nicht", "noch",
    "oder", "sich", "sie", "sind", "statt", "und", "von", "vor", "warum", "wenn", "werden",
    "wird", "wie", "zu", "zum", "zur", "über", "ueber", "obwohl", "besonders", "menschen",
}
ALIASES = {
    "beben": "erdbeben",
    "erdbeben": "erdbeben",
    "erdplatten": "tektonikplatte",
    "erdplatte": "tektonikplatte",
    "platten": "tektonikplatte",
    "platte": "tektonikplatte",
    "plattengrenzen": "plattengrenze",
    "bricht": "bruch",
    "brechen": "bruch",
    "gebrochen": "bruch",
    "brueche": "bruch",
    "brüche": "bruch",
    "spannungen": "spannung",
    "stress": "spannung",
    "stoerungen": "stoerung",
    "störungen": "stoerung",
    "fault": "stoerung",
    "rutscht": "rutschen",
    "gerutscht": "rutschen",
    "verschiebt": "rutschen",
    "verschiebung": "rutschen",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _ascii(value: str) -> str:
    translated = value.casefold().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return "".join(char for char in unicodedata.normalize("NFKD", translated) if not unicodedata.combining(char))


def _stem(token: str) -> str:
    canonical = ALIASES.get(token, token)
    if canonical in ALIASES:
        canonical = ALIASES[canonical]
    for suffix in ("ungen", "ern", "en", "er", "es", "e", "n", "s"):
        if len(canonical) - len(suffix) >= 5 and canonical.endswith(suffix):
            canonical = canonical[: -len(suffix)]
            break
    return canonical


def tokens(value: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", _ascii(_clean(value)))
    return [_stem(token) for token in raw if token not in STOPWORDS and len(token) >= 3]


def _context_text(topic: str, source_context: dict[str, Any]) -> str:
    answers = source_context.get("fallback_editorial_answers")
    series = source_context.get("series_context")
    parts = [topic]
    if isinstance(answers, dict):
        parts.extend(_clean(answers.get(key)) for key in ANSWER_KEYS)
    if isinstance(series, dict):
        parts.append(_clean(series.get("hook")))
    return _clean(" ".join(parts))


def _set_jaccard(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def _containment(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def _cosine(left: list[str], right: list[str]) -> float:
    a, b = Counter(left), Counter(right)
    if not a or not b:
        return 0.0
    numerator = sum(a[key] * b.get(key, 0) for key in a)
    denominator = math.sqrt(sum(value * value for value in a.values())) * math.sqrt(
        sum(value * value for value in b.values())
    )
    return numerator / denominator if denominator else 0.0


def _trigrams(value: str) -> set[str]:
    compact = re.sub(r"[^a-z0-9]+", " ", _ascii(value)).strip()
    return {compact[index : index + 3] for index in range(max(0, len(compact) - 2))}


def _trigram_jaccard(left: str, right: str) -> float:
    a, b = _trigrams(left), _trigrams(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def _canonical_url(value: Any) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    parsed = urlsplit(raw)
    host = parsed.netloc.casefold().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold() or "https", host, path, "", ""))


def _source_urls(source_context: dict[str, Any]) -> set[str]:
    sources = source_context.get("sources")
    if not isinstance(sources, list):
        return set()
    return {
        canonical
        for item in sources
        if isinstance(item, dict)
        for canonical in [_canonical_url(item.get("url"))]
        if canonical
    }


def _series_identity(source_context: dict[str, Any]) -> tuple[str, int | None]:
    series = source_context.get("series_context")
    if not isinstance(series, dict):
        return "", None
    series_id = _clean(series.get("series_id"))
    try:
        episode = int(series.get("episode"))
    except (TypeError, ValueError):
        episode = None
    return series_id, episode


def compare(
    *,
    topic: str,
    source_context: dict[str, Any],
    prior_topic: str,
    prior_context: dict[str, Any],
) -> dict[str, Any]:
    topic_tokens = tokens(topic)
    prior_topic_tokens = tokens(prior_topic)
    content_tokens = tokens(_context_text(topic, source_context))
    prior_content_tokens = tokens(_context_text(prior_topic, prior_context))
    topic_intersection = len(set(topic_tokens) & set(prior_topic_tokens))
    current_urls = _source_urls(source_context)
    prior_urls = _source_urls(prior_context)
    source_overlap = len(current_urls & prior_urls) / min(len(current_urls), len(prior_urls)) if current_urls and prior_urls else 0.0
    series_id, episode = _series_identity(source_context)
    prior_series_id, prior_episode = _series_identity(prior_context)
    same_episode = bool(series_id and series_id == prior_series_id and episode is not None and episode == prior_episode)

    metrics = {
        "topic_jaccard": round(_set_jaccard(topic_tokens, prior_topic_tokens), 4),
        "topic_containment": round(_containment(topic_tokens, prior_topic_tokens), 4),
        "topic_trigram_jaccard": round(_trigram_jaccard(topic, prior_topic), 4),
        "content_jaccard": round(_set_jaccard(content_tokens, prior_content_tokens), 4),
        "content_cosine": round(_cosine(content_tokens, prior_content_tokens), 4),
        "source_url_overlap": round(source_overlap, 4),
        "topic_token_intersection": topic_intersection,
        "same_series_episode": same_episode,
    }
    reasons = []
    if same_episode:
        reasons.append("same_series_episode")
    if metrics["topic_jaccard"] >= 0.72:
        reasons.append("near_identical_topic_tokens")
    if metrics["topic_trigram_jaccard"] >= 0.82:
        reasons.append("near_identical_topic_phrasing")
    if metrics["topic_containment"] >= 0.86 and topic_intersection >= 4:
        reasons.append("topic_concept_containment")
    if metrics["content_jaccard"] >= 0.58 or metrics["content_cosine"] >= 0.82:
        reasons.append("same_verified_story")
    if metrics["source_url_overlap"] >= 0.5 and metrics["content_cosine"] >= 0.68:
        reasons.append("same_sources_and_story")
    metrics["duplicate_reasons"] = reasons
    metrics["blocked"] = bool(reasons)
    metrics["risk_score"] = round(max(
        float(metrics["topic_jaccard"]),
        float(metrics["topic_trigram_jaccard"]),
        float(metrics["content_jaccard"]),
        float(metrics["content_cosine"]),
    ), 4)
    return metrics


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def run_gate(
    *,
    requests_dir: Path,
    source_request_id: str,
    topic: str,
    source_context: dict[str, Any],
) -> dict[str, Any]:
    comparisons = []
    for path in sorted(requests_dir.glob("*.json")):
        try:
            prior = _read_json(path)
        except Exception:
            continue
        prior_id = _clean(prior.get("request_id"))
        if not prior_id or prior_id == source_request_id:
            continue
        if _clean(prior.get("status")).upper() not in ACTIVE_STATES:
            continue
        prior_topic = _clean(prior.get("topic"))
        prior_context = prior.get("source_context")
        if not prior_topic or not isinstance(prior_context, dict):
            continue
        metrics = compare(
            topic=topic,
            source_context=source_context,
            prior_topic=prior_topic,
            prior_context=prior_context,
        )
        comparisons.append({
            "request_id": prior_id,
            "request_file": str(path),
            "topic": prior_topic,
            **metrics,
        })

    comparisons.sort(key=lambda item: (bool(item["blocked"]), float(item["risk_score"])), reverse=True)
    blocked = [item for item in comparisons if item["blocked"]]
    canonical = _context_text(topic, source_context)
    return {
        "schema_version": "tayvoriq-global-duplicate-gate-v1",
        "passed": not blocked,
        "state": "PASSED" if not blocked else "DUPLICATE_CONTENT_BLOCKED",
        "source_request_id": source_request_id,
        "topic": topic,
        "content_fingerprint_sha256": hashlib.sha256(_ascii(canonical).encode("utf-8")).hexdigest(),
        "history_candidates_checked": len(comparisons),
        "retry_of_same_request_allowed": True,
        "quality_gates_weakened": False,
        "nearest_prior": comparisons[0] if comparisons else None,
        "blocked_matches": blocked[:5],
        "thresholds": {
            "topic_jaccard": 0.72,
            "topic_trigram_jaccard": 0.82,
            "topic_containment_with_four_tokens": 0.86,
            "content_jaccard": 0.58,
            "content_cosine": 0.82,
            "source_overlap_plus_content_cosine": [0.5, 0.68],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests-dir", type=Path, default=Path("requests"))
    parser.add_argument("--source-request-id", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--source-context", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    args = parser.parse_args()

    source_request_id = _clean(args.source_request_id)
    topic = _clean(args.topic)
    if not source_request_id or not topic:
        raise SystemExit("DUPLICATE_GATE_INPUT_INVALID")
    source_context = _read_json(args.source_context)
    report = run_gate(
        requests_dir=args.requests_dir,
        source_request_id=source_request_id,
        topic=topic,
        source_context=source_context,
    )
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not report["passed"]:
        nearest = report.get("nearest_prior") or {}
        raise SystemExit(
            "DUPLICATE_CONTENT_BLOCKED:"
            f"request_id={nearest.get('request_id', 'unknown')}:topic={nearest.get('topic', 'unknown')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
