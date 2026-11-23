"""Evaluate the documented DE_LOCAL_RELEVANCE_V2 rubric using retrieved RSS evidence."""
from __future__ import annotations

WEIGHTS = {
    "consequence": 25, "proximity": 20, "recognition": 15, "timeliness": 15,
    "explanation": 10, "resolution": 10, "continuity": 5,
}


def evaluate(card, sources):
    """The two source records are reconstructed by the RSS verifier, never supplied by the model."""
    if not isinstance(card, dict):
        return {"passed": False, "reason": "regional_scorecard_missing"}
    quotes = card.get("evidence")
    if not isinstance(quotes, dict) or len(sources) != 2:
        return {"passed": False, "reason": "both_original_excerpts_required"}
    for source in sources:
        sid = source["source_id"]
        quote = quotes.get(sid)
        if not isinstance(quote, str) or not 4 <= len(quote.split()) <= 30:
            return {"passed": False, "reason": "invalid_evidence_quote:" + sid}
        excerpt = " ".join(source["supports"].split()).casefold()
        if " ".join(quote.split()).casefold() not in excerpt:
            return {"passed": False, "reason": "quote_absent_from_retrieved_record:" + sid}
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
            "evidence": {source["url"]: quotes[source["source_id"]] for source in sources}}
