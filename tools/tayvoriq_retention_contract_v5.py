#!/usr/bin/env python3
from __future__ import annotations

import copy
import re
from typing import Any, Iterable

CTA_TYPES = {"CURIOSITY", "EXPERTISE", "COMMUNITY", "SERIES", "DISCUSSION", "IDENTITY"}
HARD_QUEUE_STATES = {"QUEUED", "PLANNED", "RESERVED", "COMMITTED"}
PLATFORM_PREFIX = {
    "youtube_shorts": "Abonniere ",
    "tiktok": "Folge ",
}
CATEGORY_PROMISE = {
    "AI": ("KI-Entwicklungen", "KI-Thema"),
    "TECH": ("Technik-Entwicklungen", "Technik-Thema"),
    "SPORTS": ("Geschichten hinter dem Sport", "Sport-Thema"),
    "WORLD": ("wichtige Weltentwicklungen", "Welt-Thema"),
}


def clean(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def words(value: str) -> int:
    return len(re.findall(r"[\wÄÖÜäöüß-]+", str(value or ""), flags=re.UNICODE))


def _series_context(source_context: dict[str, Any]) -> dict[str, Any]:
    value = source_context.get("series_context")
    return value if isinstance(value, dict) else {}


def _first_sentence(value: str) -> str:
    text = clean(value, 500)
    if not text:
        return ""
    match = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    return clean(match[0], 320)


def _cta_variants(cta_type: str, category: str, series_name: str | None) -> list[str]:
    promise, topic_label = CATEGORY_PROMISE.get(category, CATEGORY_PROMISE["TECH"])
    if cta_type == "SERIES" and series_name:
        body = [
            f"TAYVORIQ für den nächsten verifizierten Teil von {series_name}",
            f"TAYVORIQ für die verifizierte Fortsetzung von {series_name}",
            f"TAYVORIQ, damit du die nächste verifizierte Folge von {series_name} nicht verpasst",
        ]
    elif cta_type == "EXPERTISE":
        body = [
            f"TAYVORIQ für verifizierte {promise}, verständliche Einordnung und klare Folgen für dich",
            f"TAYVORIQ für verifizierte {promise} mit verständlicher Einordnung statt Hype",
            f"TAYVORIQ, wenn du verifizierte {promise} verständlich und sachlich eingeordnet haben willst",
        ]
    elif cta_type == "COMMUNITY":
        body = [
            f"TAYVORIQ und bleib bei verifizierten {promise} früh, verständlich und sachlich dabei",
            f"TAYVORIQ, wenn du verifizierte {promise} früh mit verständlicher Einordnung verfolgen willst",
            f"TAYVORIQ für verifizierte {promise} und eine Community, die Zusammenhänge verstehen will",
        ]
    elif cta_type == "CURIOSITY":
        body = [
            f"TAYVORIQ – wir ordnen die nächste verifizierte Entwicklung in diesem {topic_label} verständlich ein",
            f"TAYVORIQ, wenn du wissen willst, wie sich dieses {topic_label} verifiziert weiterentwickelt",
            f"TAYVORIQ für die nächste verifizierte Entwicklung und ihre verständliche Einordnung",
        ]
    elif cta_type == "DISCUSSION":
        body = [
            f"TAYVORIQ für weitere verifizierte Perspektiven und verständliche Einordnung zu diesem {topic_label}",
            f"TAYVORIQ, wenn du dieses {topic_label} mit verifizierten Fakten weiterverfolgen willst",
            f"TAYVORIQ für verifizierte Fakten, verständliche Einordnung und weitere Perspektiven zu diesem {topic_label}",
        ]
    else:
        body = [
            f"TAYVORIQ, wenn du verifizierte {promise} verstehen willst, bevor sie überall diskutiert werden",
            f"TAYVORIQ für verifizierte {promise}, die verständlich erklären, was sich wirklich verändert",
            f"TAYVORIQ, wenn du verifizierte {promise} ohne Hype und mit verständlicher Einordnung willst",
        ]
    return [clean(value.rstrip(".!? ") + ".", 260) for value in body]


def _platform_cta(
    platform: str,
    cta_type: str,
    category: str,
    series_name: str | None,
    recent_ctas: Iterable[str],
) -> tuple[str, int]:
    prefix = PLATFORM_PREFIX[platform]
    recent = {clean(value, 260).casefold() for value in recent_ctas if clean(value, 260)}
    candidates = _cta_variants(cta_type, category, series_name)
    for index, body in enumerate(candidates):
        candidate = prefix + body
        if not 8 <= words(candidate) <= 20:
            continue
        if candidate.casefold() not in recent:
            return candidate, index
    for index, body in enumerate(candidates):
        candidate = prefix + body
        if 8 <= words(candidate) <= 20:
            return candidate, index
    raise ValueError(f"CTA_TEMPLATE_OUTSIDE_WORD_GATE:{platform}:{cta_type}")


def validate_story_contract(value: dict[str, Any]) -> None:
    if value.get("schema") != "tayvoriq-story-retention-contract-v5":
        raise ValueError("STORY_RETENTION_SCHEMA_INVALID")
    if value.get("quality_gates_weakened") is not False:
        raise ValueError("STORY_RETENTION_QUALITY_GATE_INTEGRITY_FAILED")
    for field in (
        "primary_hook",
        "viewer_question",
        "explanation_core",
        "practical_relevance",
        "follow_reason",
    ):
        if not clean(value.get(field)):
            raise ValueError(f"STORY_RETENTION_REQUIRED_FIELD_MISSING:{field}")

    cta_type = clean(value.get("cta_type"), 40).upper()
    if cta_type not in CTA_TYPES:
        raise ValueError(f"STORY_RETENTION_CTA_TYPE_INVALID:{cta_type}")

    status = clean(value.get("open_loop_status"), 20).upper()
    if status not in {"NONE", "SOFT", "HARD"}:
        raise ValueError(f"STORY_RETENTION_OPEN_LOOP_STATUS_INVALID:{status}")
    open_loop = clean(value.get("open_loop"), 500)
    if status == "NONE" and open_loop:
        raise ValueError("STORY_RETENTION_NONE_WITH_OPEN_LOOP")
    if status != "NONE" and not open_loop:
        raise ValueError("STORY_RETENTION_OPEN_LOOP_MISSING")

    if status == "HARD":
        if clean(value.get("queue_status"), 30).upper() not in HARD_QUEUE_STATES:
            raise ValueError("STORY_RETENTION_FALSE_HARD_OPEN_LOOP")
        if not clean(value.get("next_episode_candidate")):
            raise ValueError("STORY_RETENTION_HARD_WITHOUT_NEXT_EPISODE")
        if not clean(value.get("series_id")) or not clean(value.get("series_name")):
            raise ValueError("STORY_RETENTION_HARD_WITHOUT_REAL_SERIES")

    if clean(value.get("episode_number")) and (
        not clean(value.get("series_id")) or not clean(value.get("series_name"))
    ):
        raise ValueError("STORY_RETENTION_EPISODE_WITHOUT_SERIES")

    ctas = value.get("cta_text")
    if not isinstance(ctas, dict):
        raise ValueError("STORY_RETENTION_CTA_TEXT_MISSING")
    for platform, prefix in PLATFORM_PREFIX.items():
        cta = clean(ctas.get(platform), 260)
        if not cta.startswith(prefix):
            raise ValueError(f"STORY_RETENTION_PLATFORM_CTA_INVALID:{platform}")
        if not 8 <= words(cta) <= 20:
            raise ValueError(f"STORY_RETENTION_PLATFORM_CTA_WORDS:{platform}:{words(cta)}")
        lowered = cta.casefold()
        if lowered in {"bitte abonnieren.", "folge uns.", "bitte abonnieren", "folge uns"}:
            raise ValueError("STORY_RETENTION_GENERIC_CTA")
        if any(marker in lowered for marker in ("du musst", "garantiert", "verpass nie wieder")):
            raise ValueError("STORY_RETENTION_MANIPULATIVE_CTA")
        if status != "HARD" and "morgen zeigen wir" in lowered:
            raise ValueError("STORY_RETENTION_FALSE_FUTURE_PROMISE")


def build_story_contract(
    retention: dict[str, Any],
    source_context: dict[str, Any],
    *,
    recent_ctas: Iterable[str] = (),
) -> dict[str, Any]:
    if retention.get("schema") != "tayvoriq-retention-v5":
        raise ValueError("RETENTION_V5_REQUIRED_FOR_GP35")
    if retention.get("quality_gates_weakened") is not False:
        raise ValueError("RETENTION_V5_QUALITY_GATE_INTEGRITY_FAILED")

    answers = source_context.get("fallback_editorial_answers")
    if not isinstance(answers, dict):
        raise ValueError("GP35_EDITORIAL_EVIDENCE_MISSING")

    story = clean(source_context.get("story_first_script_body"), 1200)
    guardrails = source_context.get("factual_guardrails")
    guardrails = guardrails if isinstance(guardrails, dict) else {}
    series = _series_context(source_context)

    series_id = clean(retention.get("proposed_series_id"), 80) or clean(series.get("series_id"), 80) or None
    series_name = clean(retention.get("proposed_series_name"), 120) or clean(series.get("series_name"), 120) or None
    episode_number = series.get("episode_number", series.get("episode"))
    if episode_number in (None, ""):
        episode_number = None
    else:
        episode_number = int(episode_number)

    next_episode = clean(retention.get("next_episode_candidate"), 320) or clean(series.get("next_episode_candidate"), 320) or None
    queue_status = clean(series.get("queue_status"), 30).upper() or None
    hard = bool(
        series_id
        and series_name
        and next_episode
        and queue_status in HARD_QUEUE_STATES
    )
    open_loop_potential = int(retention.get("open_loop_potential") or 0)
    if hard:
        open_loop_status = "HARD"
        open_loop = f"Im nächsten Teil: {next_episode}"
    elif open_loop_potential >= 70:
        open_loop_status = "SOFT"
        open_loop = (
            f"Der nächste entscheidende Punkt bleibt: {next_episode}"
            if next_episode
            else "Wir beobachten, welcher verifizierte nächste Schritt diese Entwicklung tatsächlich verändert."
        )
    else:
        open_loop_status = "NONE"
        open_loop = ""

    recommended = clean(retention.get("recommended_cta_type"), 40).upper()
    cta_type = recommended if recommended in CTA_TYPES else "IDENTITY"
    if cta_type == "SERIES" and not hard:
        cta_type = "CURIOSITY" if open_loop_status == "SOFT" else "IDENTITY"

    category = clean(retention.get("category"), 20).upper()
    if category not in CATEGORY_PROMISE:
        category = "TECH"
    promise, _ = CATEGORY_PROMISE[category]
    follow_reason = f"TAYVORIQ liefert weitere verifizierte {promise} mit verständlicher Einordnung statt leerem Hype."

    recent = list(recent_ctas)
    youtube_cta, youtube_variant = _platform_cta(
        "youtube_shorts", cta_type, category, series_name, recent
    )
    tiktok_cta, tiktok_variant = _platform_cta(
        "tiktok", cta_type, category, series_name, recent
    )

    what = clean(answers.get("what_happened"), 500)
    why = clean(answers.get("why_happening"), 500)
    impact = clean(answers.get("personal_impact"), 500)
    uncertainty = clean(guardrails.get("uncertainty_note"), 500)
    contract = {
        "schema": "tayvoriq-story-retention-contract-v5",
        "primary_hook": _first_sentence(story) or what,
        "viewer_question": clean(retention.get("content_angle"), 360),
        "explanation_core": why,
        "surprise_or_reframe": uncertainty or clean(retention.get("content_angle"), 360),
        "practical_relevance": impact,
        "follow_reason": follow_reason,
        "open_loop": open_loop,
        "open_loop_status": open_loop_status,
        "queue_status": queue_status,
        "cta_type": cta_type,
        "cta_text": {
            "youtube_shorts": youtube_cta,
            "tiktok": tiktok_cta,
        },
        "cta_variant": {
            "youtube_shorts": youtube_variant,
            "tiktok": tiktok_variant,
        },
        "series_id": series_id,
        "series_name": series_name,
        "episode_number": episode_number,
        "next_episode_candidate": next_episode,
        "continuity_hook": clean(series.get("continuity_hook"), 320) or None,
        "follow_conversion_gate": "PASS",
        "quality_gates_weakened": False,
    }
    validate_story_contract(contract)
    return contract


def bind_story_contract_to_source_context(
    source_context: dict[str, Any],
    story_contract: dict[str, Any],
) -> dict[str, Any]:
    validate_story_contract(story_contract)
    result = copy.deepcopy(source_context)
    result["story_retention_contract_v5"] = copy.deepcopy(story_contract)
    result["audience_cta_contract"] = {
        "version": "v5-source-bound-follow-conversion",
        "viewer_value": story_contract["follow_reason"],
        "next_video_bridge": story_contract["open_loop"],
        "cta_type": story_contract["cta_type"],
        "open_loop_status": story_contract["open_loop_status"],
        "series_id": story_contract.get("series_id"),
        "series_name": story_contract.get("series_name"),
        "ctas_by_platform": copy.deepcopy(story_contract["cta_text"]),
        "quality_gates_weakened": False,
    }
    return result
