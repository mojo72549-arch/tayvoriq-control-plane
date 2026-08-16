#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

STATE_PATH = Path("state/tayvoriq-active-series.json")


def clean(value, limit=2000):
    return " ".join(str(value or "").split()).strip()[:limit]


def clamp(value):
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", choices=["morning", "evening"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    if not STATE_PATH.is_file():
        raise SystemExit("ACTIVE_SERIES_MISSING")
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    status = clean(state.get("status"), 50).lower()
    if status not in {"active", "ready_for_selection"}:
        raise SystemExit(f"ACTIVE_SERIES_NOT_READY: {status}")

    episode = int(state.get("episode") or 0)
    episodes = state.get("episodes") if isinstance(state.get("episodes"), list) else []
    episode_state = next(
        (item for item in episodes if int(item.get("episode") or 0) == episode),
        state,
    )
    raw = episode_state.get("trend")
    if not isinstance(raw, dict):
        raise SystemExit("ACTIVE_SERIES_INVALID: missing trend")

    criteria_raw = raw.get("criteria") if isinstance(raw.get("criteria"), dict) else {}
    criteria = {
        key: clamp(criteria_raw.get(key))
        for key in ("aktualitaet", "viralitaet", "tayvoriq_passung", "quellenqualitaet", "visuell")
    }
    score = round(
        criteria["aktualitaet"] * .25
        + criteria["viralitaet"] * .25
        + criteria["tayvoriq_passung"] * .20
        + criteria["quellenqualitaet"] * .15
        + criteria["visuell"] * .15
    )

    sources = []
    for item in raw.get("sources") or []:
        if not isinstance(item, dict):
            continue
        publisher = clean(item.get("publisher"), 120)
        url = clean(item.get("url"), 2000)
        supports = clean(item.get("supports"), 800)
        if publisher and url.startswith(("https://", "http://")) and supports:
            sources.append({"publisher": publisher, "url": url, "supports": supports})
    if len(sources) < 2:
        raise SystemExit("ACTIVE_SERIES_INVALID: at least two sources required")

    answers_raw = raw.get("fallback_editorial_answers") if isinstance(raw.get("fallback_editorial_answers"), dict) else {}
    answer_keys = ("what_happened", "why_happening", "who_is_affected", "personal_impact", "action_now")
    answers = {key: clean(answers_raw.get(key), 1200) for key in answer_keys}
    if not all(answers.values()):
        raise SystemExit("ACTIVE_SERIES_INVALID: editorial answers incomplete")

    now = datetime.now(ZoneInfo("Europe/Berlin"))
    verified_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    series_id = clean(state.get("series_id"), 120)
    if not series_id or episode < 1:
        raise SystemExit("ACTIVE_SERIES_INVALID: series id/episode")

    trend = {
        "id": "1",
        "category": clean(raw.get("category"), 100) or "Wissenschaft/Erklärserie",
        "trend_scope": clean(raw.get("trend_scope"), 60) or "science_future",
        "title": clean(raw.get("title"), 180),
        "score": clamp(score),
        "criteria": criteria,
        "regional_relevance": clean(raw.get("regional_relevance"), 30) or "global",
        "sources": [s["url"] for s in sources[:3]],
        "source_context": {
            "verified_at": verified_at,
            "independent_news_count": len(sources[:3]),
            "sources": sources[:3],
            "fallback_editorial_answers": answers,
            "series_context": {
                "series_id": series_id,
                "series_title": clean(state.get("series_title"), 180),
                "episode": episode,
                "episode_title": clean(episode_state.get("episode_title"), 180),
                "cover_text": clean(episode_state.get("cover_text"), 120),
                "hook": clean(episode_state.get("hook"), 700),
                "bridge_out": clean(episode_state.get("bridge_out"), 700),
                "visual_continuity": clean(episode_state.get("visual_continuity"), 1600),
                "red_thread": clean(state.get("red_thread"), 1600),
                "approval_required": True,
            },
        },
    }
    if not trend["title"]:
        raise SystemExit("ACTIVE_SERIES_INVALID: missing title")

    series_token = re.sub(r"[^A-Za-z0-9_-]", "", series_id)[:10] or "series"
    selection_id = f"{now:%Y%m%d}-{args.slot[0]}-agentv2-{series_token}-e{episode}"
    request = {
        "date": now.strftime("%Y-%m-%d"),
        "slot": args.slot,
        "created_at": verified_at,
        "selection_id": selection_id,
        "selected_trend_id": None,
        "agent_orchestrator": "v2",
        "mode": "active_series",
        "series_id": series_id,
        "episode": episode,
        "trends": [trend],
    }

    audit = {
        "selection_id": selection_id,
        "slot": args.slot,
        "provider": "active_series_state",
        "model": None,
        "grounding_chunks": [{"title": s["publisher"], "uri": s["url"]} for s in sources[:3]],
        "candidate_count": 1,
        "valid_count": 1,
        "selected_count": 1,
        "series_candidate_injected": True,
        "series_bypassed_trend_radar": True,
        "quality_gates_weakened": False,
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.audit_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.audit_output).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "selection_id": selection_id,
        "slot": args.slot,
        "mode": "active_series",
        "series_id": series_id,
        "episode": episode,
        "title": trend["title"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
