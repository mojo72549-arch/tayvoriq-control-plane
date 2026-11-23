"""Evaluate the documented DE_LOCAL_RELEVANCE_V2 rubric using retrieved RSS evidence."""
from __future__ import annotations

import re


WEIGHTS = {
    "consequence": 25, "proximity": 20, "recognition": 15, "timeliness": 15,
    "explanation": 10, "resolution": 10, "continuity": 5,
}


def evidence_options(sid, title, context):
    """Source-local references select unmodified title or complete publisher sentences."""
    options = {}
    if 4 <= len(title.split()) <= 30:
        options[sid + ":title"] = title
    for sentence in re.split(r"(?<=[.!?])\s+", context):
        if (sentence.endswith((".", "!", "?")) and 4 <= len(sentence.split()) <= 30
                and sentence not in options.values()):
            options[sid + ":sentence" + str(1 + len(options))] = sentence
            if len(options) >= 3:
                break
    return options


def evaluate(card, sources):
    """The two source records are reconstructed by the RSS verifier, never supplied by the model."""
    if not isinstance(card, dict):
        return {"passed": False, "reason": "regional_scorecard_missing"}
    quotes = card.get("evidence")
    if not isinstance(quotes, dict) or len(sources) != 2:
        return {"passed": False, "reason": "both_original_excerpts_required"}
    matched = {}
    for source in sources:
        sid = source["source_id"]
        quote = quotes.get(sid)
        if isinstance(quote, str):
            quote = source.get("evidence_options", {}).get(quote, quote)
        if not isinstance(quote, str) or not 4 <= len(quote.split()) <= 30:
            return {"passed": False, "reason": "invalid_evidence_quote:" + sid}
        excerpt = " ".join(source["supports"].split()).casefold()
        if " ".join(quote.split()).casefold() not in excerpt:
            return {"passed": False, "reason": "quote_absent_from_retrieved_record:" + sid}
        matched[source["url"]] = quote
    ratings = card.get("ratings")
    fit = card.get("platform_fit")
    if not isinstance(ratings, dict) or not isinstance(fit, dict):
        return {"passed": False, "reason": "regional_ratings_or_platform_fit_missing"}
    scores = {"youtube": 0, "tiktok": 0}
    issues = []
    for platform in scores:
        if not isinstance(fit.get(platform), str) or len(fit[platform].split()) < 4:
            issues.append("platform_fit_missing:" + platform)
    for key, weight in WEIGHTS.items():
        row = ratings.get(key)
        if (not isinstance(row, list) or len(row) != 3
                or any(type(v) is not int or not 0 <= v <= 5 for v in row[:2])
                or not isinstance(row[2], str) or len(row[2].split()) < 4):
            issues.append("invalid_or_unexplained_rating:" + key)
            continue
        for index, platform in enumerate(scores):
            grade = row[index]
            if key in {"consequence", "explanation"} and grade < 3:
                issues.append(platform + ":" + key + "_below_3")
            scores[platform] += grade * weight // 5
    issues.extend(platform + ":regional_score_below_75" for platform, score in scores.items() if score < 75)
    return {"policy": "DE_LOCAL_RELEVANCE_V2", "passed": not issues, "issues": issues,
            "scores": scores, "ratings": {key: ratings.get(key) for key in WEIGHTS},
            "platform_fit": {key: fit.get(key) for key in scores},
            "evidence": matched}



def _mapping(value):
    return value if isinstance(value, dict) else {}


def _valid_grade(value):
    return type(value) is int and 0 <= value <= 5


def _valid_reason(value):
    return isinstance(value, str) and len(value.split()) >= 4


def complete_scorecards(candidates, options, generate):
    """Repair missing fields once per provider batch. Existing grades are immutable."""
    if sum(c.get("_retrieved_regional_assessment", {}).get("passed") is True for c in candidates) >= 2:
        return
    pending = {}
    requests = {}
    for candidate in candidates[:5]:
        if not candidate.get("fallback_editorial_answers"):
            continue
        sources = [{**row, "evidence_options": options.get(row["source_id"], {})}
                   for row in candidate["sources"]]
        key = "+".join(sorted(row["source_id"] for row in sources))
        card = _mapping(candidate.get("regional_scorecard"))
        missing = {}
        for source in sources:
            sid = source["source_id"]
            ref = _mapping(card.get("evidence")).get(sid)
            quote = source["evidence_options"].get(ref, ref) if isinstance(ref, str) else ""
            if not (4 <= len(quote.split()) <= 30 and
                    " ".join(quote.split()).casefold() in " ".join(source["supports"].split()).casefold()):
                missing["evidence." + sid] = "Copy a listed reference ID for this source or quote 4-18 original words."
        for field in WEIGHTS:
            row = _mapping(card.get("ratings")).get(field)
            row = row if isinstance(row, list) else []
            for i, name in enumerate(("youtube", "tiktok", "reason")):
                value = row[i] if i < len(row) else None
                if not (_valid_reason(value) if i == 2 else _valid_grade(value)):
                    missing[field + "." + name] = ("German reason of 4-12 words" if i == 2 else "integer 0-5")
        for platform in ("youtube", "tiktok"):
            if not _valid_reason(_mapping(card.get("platform_fit")).get(platform)):
                missing["fit." + platform] = "Specific German reason of 4-12 words"
        if missing:
            pending[key] = candidate, sources, card, missing
            requests[key] = {"headline": candidate["title"], "angle": candidate.get("content_angle"),
                             "sources": [{"id": s["source_id"], "text": s["supports"],
                                          "choices": s["evidence_options"]} for s in sources],
                             "existing": card, "missing": missing}
    if not requests:
        return
    try:
        replies = _mapping(generate(requests))
    except (OSError, ValueError, RuntimeError) as exc:
        # A failed optional completion must preserve the independent original assessments.
        print({"event": "scorecard_completion_unavailable", "error_type": type(exc).__name__})
        return
    for key, (candidate, sources, card, missing) in pending.items():
        fields = _mapping(replies.get(key))
        if not fields or not missing.keys() <= fields.keys():
            continue
        evidence = dict(_mapping(card.get("evidence")))
        fit = dict(_mapping(card.get("platform_fit")))
        ratings = {}
        for name in WEIGHTS:
            old = _mapping(card.get("ratings")).get(name)
            old = old if isinstance(old, list) else []
            ratings[name] = [fields[name + "." + col] if name + "." + col in missing else old[i]
                             for i, col in enumerate(("youtube", "tiktok", "reason"))]
        for source in sources:
            sid = source["source_id"]
            if "evidence." + sid in missing:
                evidence[sid] = fields["evidence." + sid]
        for platform in ("youtube", "tiktok"):
            if "fit." + platform in missing:
                fit[platform] = fields["fit." + platform]
        assessment = evaluate({"ratings": ratings, "evidence": evidence, "platform_fit": fit}, sources)
        candidate["_retrieved_regional_assessment"] = assessment
        print({"event": "source_bound_scorecard_completion", "headline": candidate["title"],
               "completed_fields": len(missing), "passed": assessment["passed"]})
