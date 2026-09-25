#!/usr/bin/env python3
"""TAYVORIQ Golden Path V5 retention/series contract.

Dependency-free control-plane policy. It does not publish, render or call providers.
The module binds growth metadata to the approved request and enforces the V5
retention/open-loop/follow-conversion invariants without weakening V4 evidence gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

CTA_TYPES = {"CURIOSITY", "EXPERTISE", "COMMUNITY", "SERIES", "DISCUSSION", "IDENTITY"}
OPEN_LOOP_STATUSES = {"NONE", "SOFT", "HARD"}
FOLLOW_RESULTS = {"PASS", "REWRITE_REQUIRED", "NOT_APPLICABLE"}
RETURN_RESULTS = {"PASS", "IMPROVE", "NOT_APPLICABLE"}
HARD_QUEUE_STATES = {"PLANNED", "QUEUED", "READY"}
REPAIR_STATES = {
    "SCRIPT_RETENTION_REWRITE",
    "CTA_REWRITE_REQUIRED",
    "OPEN_LOOP_REWRITE_REQUIRED",
    "SERIES_METADATA_REPAIR",
    "FOLLOW_CONVERSION_FAILED",
    "RETURN_VIEWER_IMPROVE",
}
LIFECYCLE_STATES = (
    "TREND_CANDIDATES_SCORED",
    "APPROVED",
    "REQUEST_LOCKED",
    "SOURCES_LOCKED",
    "PREFLIGHT_PASSED",
    "RETENTION_CONTRACT_LOCKED",
    "PRODUCTION_RUNNING",
    "FOLLOW_CONVERSION_PASSED",
    "RENDER_AVAILABLE",
    "MASTER_PUBLISHABLE",
    "QUALITY_PASSED",
    "REVIEW_READY",
    "COMPLETED",
)

REQUEST_FIELDS = (
    "series_id",
    "series_name",
    "episode_id",
    "episode_number",
    "continuity_hook",
    "next_episode_candidate",
    "primary_hook",
    "viewer_question",
    "explanation_core",
    "surprise_or_reframe",
    "practical_relevance",
    "follow_reason",
    "open_loop",
    "open_loop_status",
    "cta_type",
    "cta_text",
)

_SCORE_FIELDS = (
    "viral_potential",
    "tayvoriq_fit",
    "novelty_score",
    "return_viewer_score",
    "series_fit_score",
    "follow_conversion_potential",
    "open_loop_potential",
)

_GENERIC_CTA_PATTERNS = (
    r"^bitte\s+(?:jetzt\s+)?abonnier(?:e|t|en)?[.!]?$",
    r"^abonnier(?:e|t|en)?\s+(?:uns|den kanal)?[.!]?$",
    r"^folge\s+(?:uns|mir)?[.!]?$",
    r"^follow\s+(?:us|me)?[.!]?$",
)

def clean(value: Any, limit: int = 1200) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]

def clamp_score(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return 0

def json_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def trend_selection_score(candidate: dict[str, Any]) -> int:
    """Exact V5 default score. Evidence quality is intentionally not a compensating weight."""
    return clamp_score(
        0.30 * clamp_score(candidate.get("viral_potential"))
        + 0.20 * clamp_score(candidate.get("tayvoriq_fit"))
        + 0.15 * clamp_score(candidate.get("novelty_score"))
        + 0.15 * clamp_score(candidate.get("return_viewer_score"))
        + 0.10 * clamp_score(candidate.get("series_fit_score"))
        + 0.10 * clamp_score(candidate.get("follow_conversion_potential"))
    )

def _source_context(candidate: dict[str, Any]) -> dict[str, Any]:
    value = candidate.get("source_context")
    return value if isinstance(value, dict) else {}

def _series_context(candidate: dict[str, Any]) -> dict[str, Any]:
    value = _source_context(candidate).get("series_context")
    return value if isinstance(value, dict) else {}

def _retention_seed(candidate: dict[str, Any]) -> dict[str, Any]:
    value = _source_context(candidate).get("retention_v5")
    return value if isinstance(value, dict) else {}

def apply_trend_contract(candidate: dict[str, Any], *, strict: bool = True) -> dict[str, Any]:
    """Normalize and score one already evidence-valid candidate.

    In strict mode every V5 model-provided field must be present. Compatibility mode
    is only for legacy dry-runs and is explicitly marked so it cannot masquerade as
    a native V5 trend.
    """
    result = dict(candidate)
    criteria = result.get("criteria") if isinstance(result.get("criteria"), dict) else {}
    seed = _retention_seed(result)

    compatibility = False
    aliases = {
        "viral_potential": criteria.get("viralitaet"),
        "tayvoriq_fit": criteria.get("tayvoriq_passung"),
    }
    for key in _SCORE_FIELDS:
        raw = result.get(key)
        if raw is None and key in seed:
            raw = seed.get(key)
        if raw is None and key in aliases and aliases[key] is not None:
            raw = aliases[key]
        if raw is None:
            if strict:
                raise ValueError(f"V5_TREND_CONTRACT_MISSING:{key}")
            compatibility = True
            if key == "novelty_score":
                raw = criteria.get("aktualitaet")
            elif key == "return_viewer_score":
                raw = (result.get("audience_growth_v3") or {}).get("returning_viewer_score")
            elif key == "follow_conversion_potential":
                raw = (result.get("audience_growth_v3") or {}).get("subscriber_conversion_score")
            elif key == "series_fit_score":
                raw = 100 if _series_context(result) else 55
            elif key == "open_loop_potential":
                raw = 90 if _series_context(result) else 55
            else:
                raw = 0
        result[key] = clamp_score(raw)

    text_fields = (
        "proposed_series_id", "proposed_series_name", "next_episode_candidate",
        "recommended_cta_type", "primary_hook", "viewer_question",
        "explanation_core", "surprise_or_reframe", "practical_relevance",
        "follow_reason", "open_loop", "open_loop_status", "cta_type", "cta_text",
    )
    for key in text_fields:
        raw = result.get(key)
        if raw is None and key in seed:
            raw = seed.get(key)
        result[key] = clean(raw)

    series = _series_context(result)
    if series:
        result["proposed_series_id"] = clean(result.get("proposed_series_id") or series.get("series_id"), 120)
        result["proposed_series_name"] = clean(
            result.get("proposed_series_name") or series.get("series_title") or series.get("series_name"), 180
        )
        result["continuity_hook"] = clean(series.get("bridge_out") or series.get("continuity_hook"), 600)
        try:
            result["episode_number"] = int(series.get("episode") or 0) or None
        except Exception:
            result["episode_number"] = None
        result["episode_id"] = clean(series.get("episode_id"), 160) or (
            f"{result['proposed_series_id']}-e{result['episode_number']}"
            if result.get("proposed_series_id") and result.get("episode_number") else ""
        )
        result["series_history_exists"] = True

    if not result.get("recommended_cta_type"):
        result["recommended_cta_type"] = result.get("cta_type") or ("SERIES" if series else "IDENTITY")
    if not result.get("cta_type"):
        result["cta_type"] = result.get("recommended_cta_type")

    cta_type = clean(result.get("cta_type")).upper()
    if cta_type not in CTA_TYPES:
        if strict:
            raise ValueError(f"V5_TREND_CONTRACT_INVALID:cta_type={cta_type!r}")
        result["cta_type"] = "IDENTITY"
        result["recommended_cta_type"] = "IDENTITY"
        compatibility = True
    else:
        result["cta_type"] = cta_type
        result["recommended_cta_type"] = cta_type

    status = clean(result.get("open_loop_status")).upper()
    if not status:
        status = "HARD" if result.get("next_episode_candidate") and series else "SOFT" if result.get("open_loop") else "NONE"
        compatibility = compatibility or not strict
    if status not in OPEN_LOOP_STATUSES:
        raise ValueError(f"V5_TREND_CONTRACT_INVALID:open_loop_status={status!r}")
    result["open_loop_status"] = status

    result["trend_selection_score"] = trend_selection_score(result)
    result["retention_v5_native"] = not compatibility
    if compatibility:
        result["retention_v5_compatibility"] = "legacy_request_dry_run_only"

    validate_trend_contract(result, strict=strict)
    return result

def validate_trend_contract(candidate: dict[str, Any], *, strict: bool = True) -> None:
    if strict:
        required_text = (
            "content_angle", "primary_hook", "viewer_question", "explanation_core",
            "surprise_or_reframe", "practical_relevance", "follow_reason", "cta_text",
        )
        for key in required_text:
            if not clean(candidate.get(key)):
                raise ValueError(f"V5_TREND_CONTRACT_MISSING:{key}")
    for key in _SCORE_FIELDS:
        value = candidate.get(key)
        if value is None and strict:
            raise ValueError(f"V5_TREND_CONTRACT_MISSING:{key}")
        if value is not None and not 0 <= clamp_score(value) <= 100:
            raise ValueError(f"V5_TREND_CONTRACT_INVALID:{key}")
    if candidate.get("trend_selection_score") != trend_selection_score(candidate):
        raise ValueError("V5_TREND_SELECTION_SCORE_MISMATCH")
    status = clean(candidate.get("open_loop_status")).upper()
    if status not in OPEN_LOOP_STATUSES:
        raise ValueError("V5_TREND_CONTRACT_INVALID:open_loop_status")
    cta_type = clean(candidate.get("cta_type") or candidate.get("recommended_cta_type")).upper()
    if cta_type not in CTA_TYPES:
        raise ValueError("V5_TREND_CONTRACT_INVALID:cta_type")
    if status == "HARD":
        if not clean(candidate.get("next_episode_candidate")):
            raise ValueError("OPEN_LOOP_REWRITE_REQUIRED:false_hard_open_loop")
        queue_status = clean(candidate.get("next_episode_queue_status")).upper()
        if queue_status not in HARD_QUEUE_STATES:
            raise ValueError("OPEN_LOOP_REWRITE_REQUIRED:hard_open_loop_requires_planned_queue")
    episode = candidate.get("episode_number")
    if episode:
        if not clean(candidate.get("proposed_series_id")) or not bool(candidate.get("series_history_exists")):
            raise ValueError("SERIES_METADATA_REPAIR:episode_number_requires_real_series")

def request_fields_from_trend(trend: dict[str, Any]) -> dict[str, Any]:
    series = _series_context(trend)
    fields = {
        "series_id": clean(trend.get("proposed_series_id") or series.get("series_id"), 120) or None,
        "series_name": clean(
            trend.get("proposed_series_name") or series.get("series_title") or series.get("series_name"), 180
        ) or None,
        "episode_id": clean(trend.get("episode_id") or series.get("episode_id"), 160) or None,
        "episode_number": trend.get("episode_number") or series.get("episode") or None,
        "continuity_hook": clean(trend.get("continuity_hook") or series.get("bridge_out"), 600) or None,
        "next_episode_candidate": clean(trend.get("next_episode_candidate"), 600) or None,
        "primary_hook": clean(trend.get("primary_hook"), 600),
        "viewer_question": clean(trend.get("viewer_question"), 600),
        "explanation_core": clean(trend.get("explanation_core"), 900),
        "surprise_or_reframe": clean(trend.get("surprise_or_reframe"), 900),
        "practical_relevance": clean(trend.get("practical_relevance"), 900),
        "follow_reason": clean(trend.get("follow_reason"), 900),
        "open_loop": clean(trend.get("open_loop"), 900),
        "open_loop_status": clean(trend.get("open_loop_status")).upper(),
        "cta_type": clean(trend.get("cta_type") or trend.get("recommended_cta_type")).upper(),
        "cta_text": clean(trend.get("cta_text"), 900),
    }
    try:
        fields["episode_number"] = int(fields["episode_number"]) if fields["episode_number"] else None
    except Exception:
        fields["episode_number"] = None
    return fields

def is_generic_cta(text: Any) -> bool:
    value = clean(text).casefold()
    if not value:
        return True
    return any(re.fullmatch(pattern, value, flags=re.I) for pattern in _GENERIC_CTA_PATTERNS)

def _repeated_cta(text: str, previous_cta: str) -> bool:
    return bool(clean(previous_cta) and clean(text).casefold() == clean(previous_cta).casefold())

def evaluate_follow_conversion(
    contract: dict[str, Any],
    *,
    previous_cta: str = "",
    sensitive_story: bool = False,
) -> dict[str, Any]:
    if sensitive_story and not clean(contract.get("cta_text")):
        return {"result": "NOT_APPLICABLE", "repair": None, "issues": [], "reason": "sensitive_story_cta_skipped"}

    issues: list[str] = []
    cta = clean(contract.get("cta_text"))
    follow_reason = clean(contract.get("follow_reason"))
    status = clean(contract.get("open_loop_status")).upper() or "NONE"
    next_episode = clean(contract.get("next_episode_candidate"))
    queue_status = clean(contract.get("next_episode_queue_status")).upper()

    if is_generic_cta(cta):
        issues.append("generic_cta")
    if len(follow_reason.split()) < 5:
        issues.append("missing_or_generic_follow_reason")
    if _repeated_cta(cta, previous_cta):
        issues.append("repeated_cta_wording")
    if status == "HARD":
        if not next_episode:
            issues.append("hard_open_loop_without_next_episode")
        if queue_status and queue_status not in HARD_QUEUE_STATES:
            issues.append("hard_open_loop_without_planned_queue")
    if "morgen zeigen wir" in clean(contract.get("open_loop")).casefold() and status != "HARD":
        issues.append("false_tomorrow_promise")
    if status not in OPEN_LOOP_STATUSES:
        issues.append("invalid_open_loop_status")
    if clean(contract.get("cta_type")).upper() not in CTA_TYPES:
        issues.append("invalid_cta_type")

    if not issues:
        return {"result": "PASS", "repair": None, "issues": []}
    if any(issue.startswith("hard_open_loop") or issue == "false_tomorrow_promise" for issue in issues):
        repair = "OPEN_LOOP_REWRITE_REQUIRED"
    elif "generic_cta" in issues or "repeated_cta_wording" in issues:
        repair = "CTA_REWRITE_REQUIRED"
    else:
        repair = "FOLLOW_CONVERSION_FAILED"
    return {"result": "REWRITE_REQUIRED", "repair": repair, "issues": issues}

def evaluate_return_viewer(contract: dict[str, Any], *, sensitive_story: bool = False) -> dict[str, Any]:
    if sensitive_story and not clean(contract.get("cta_text")):
        return {"result": "NOT_APPLICABLE", "issues": []}
    issues: list[str] = []
    series = clean(contract.get("series_name"))
    follow_reason = clean(contract.get("follow_reason"))
    cta = clean(contract.get("cta_text"))
    if not series and len(follow_reason.split()) < 5:
        issues.append("missing_series_or_topic_promise")
    if cta and "tayvoriq" not in cta.casefold():
        issues.append("brand_identity_not_explicit")
    if clean(contract.get("open_loop_status")).upper() == "HARD" and not clean(contract.get("next_episode_candidate")):
        issues.append("false_hard_open_loop")
    return {"result": "PASS" if not issues else "IMPROVE", "issues": issues}

def lock_retention_contract(request: dict[str, Any]) -> dict[str, Any]:
    contract = {key: request.get(key) for key in REQUEST_FIELDS}
    contract["request_id"] = clean(request.get("request_id"))
    contract["topic"] = clean(request.get("topic"))
    contract["source_context_sha256"] = clean(request.get("source_context_sha256"))
    contract["content_angle"] = clean(request.get("content_angle")) or None
    contract["quality_gates_weakened"] = False
    contract["schema_version"] = "tayvoriq-retention-v5"
    contract["lifecycle_state"] = "RETENTION_CONTRACT_LOCKED"
    contract["contract_sha256"] = json_sha256({k: v for k, v in contract.items() if k != "contract_sha256"})
    return contract

def assert_repair_preserves(before: dict[str, Any], after: dict[str, Any]) -> None:
    for key in ("request_id", "topic", "source_context_sha256", "content_angle"):
        if before.get(key) != after.get(key):
            raise ValueError(f"RETENTION_REPAIR_MUTATED_IMMUTABLE:{key}")

def _legacy_request_to_contract(request: dict[str, Any]) -> dict[str, Any]:
    """Build an explicitly marked compatibility contract for dry-run verification only."""
    source = request.get("source_context") if isinstance(request.get("source_context"), dict) else {}
    answers = source.get("fallback_editorial_answers") if isinstance(source.get("fallback_editorial_answers"), dict) else {}
    topic = clean(request.get("topic"))
    scope = clean(request.get("trend_scope"))
    promise = {
        "technology_ai": "Wenn du verstehen willst, was neue KI-Funktionen im Alltag wirklich ändern, folge TAYVORIQ.",
        "science_future": "Wenn du Forschung und Technik ohne Hype verständlich eingeordnet haben willst, folge TAYVORIQ.",
        "sports": "Wenn du verstehen willst, was hinter solchen Sportentwicklungen steckt, folge TAYVORIQ.",
        "business_economy": "Wenn du verstehen willst, was solche Wirtschaftsänderungen für den Alltag bedeuten, folge TAYVORIQ.",
        "mobility_energy": "Wenn du Mobilität und Energie verständlich eingeordnet haben willst, folge TAYVORIQ.",
    }.get(scope, "Wenn du solche Entwicklungen verständlich eingeordnet haben willst, folge TAYVORIQ.")
    contract = {
        "request_id": request.get("request_id"),
        "topic": topic,
        "source_context_sha256": request.get("source_context_sha256"),
        "content_angle": request.get("content_angle"),
        "series_id": request.get("series_id"),
        "series_name": request.get("series_name"),
        "episode_id": request.get("episode_id"),
        "episode_number": request.get("episode_number"),
        "continuity_hook": request.get("continuity_hook"),
        "next_episode_candidate": request.get("next_episode_candidate"),
        "primary_hook": clean(request.get("primary_hook") or answers.get("what_happened")),
        "viewer_question": clean(request.get("viewer_question") or (f"Warum ist {topic} jetzt wichtig?" if topic else "")),
        "explanation_core": clean(request.get("explanation_core") or answers.get("why_happening")),
        "surprise_or_reframe": clean(request.get("surprise_or_reframe") or answers.get("what_happened")),
        "practical_relevance": clean(request.get("practical_relevance") or answers.get("personal_impact")),
        "follow_reason": clean(request.get("follow_reason") or promise),
        "open_loop": clean(request.get("open_loop")),
        "open_loop_status": clean(request.get("open_loop_status")).upper() or "NONE",
        "cta_type": clean(request.get("cta_type")).upper() or "IDENTITY",
        "cta_text": clean(request.get("cta_text") or promise),
        "quality_gates_weakened": False,
        "schema_version": "tayvoriq-retention-v5",
        "compatibility_mode": "legacy_request_dry_run_only",
        "lifecycle_state": "RETENTION_CONTRACT_LOCKED",
    }
    contract["contract_sha256"] = json_sha256({k: v for k, v in contract.items() if k != "contract_sha256"})
    return contract

def dry_run_request(request: dict[str, Any]) -> dict[str, Any]:
    native = all(key in request for key in ("primary_hook", "follow_reason", "cta_type", "cta_text", "open_loop_status"))
    contract = lock_retention_contract(request) if native else _legacy_request_to_contract(request)
    follow = evaluate_follow_conversion(contract)
    return_viewer = evaluate_return_viewer(contract)
    return {
        "dry_run": True,
        "platform_upload_performed": False,
        "request_id": request.get("request_id"),
        "topic": request.get("topic"),
        "source_context_sha256": request.get("source_context_sha256"),
        "retention_contract_sha256": contract.get("contract_sha256"),
        "contract_mode": "native_v5" if native else "legacy_compatibility",
        "follow_conversion_gate": follow,
        "return_viewer_gate": return_viewer,
        "review_required_before_publish": request.get("approval_required_before_youtube_publish") is True,
        "quality_gates_weakened": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dry-run")
    p.add_argument("--request", required=True)
    p.add_argument("--out", default="")
    args = parser.parse_args()
    if args.cmd == "dry-run":
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        report = dry_run_request(request)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
