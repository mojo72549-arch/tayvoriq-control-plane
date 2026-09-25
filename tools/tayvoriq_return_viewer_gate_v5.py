#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import tayvoriq_retention_contract_v5 as retention_v5


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def evaluate(request: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    story = request.get("story_retention_contract")
    trend = request.get("retention_contract")
    if not isinstance(story, dict):
        raise ValueError("RETURN_VIEWER_STORY_CONTRACT_MISSING")
    if not isinstance(trend, dict) or trend.get("schema") != "tayvoriq-retention-v5":
        raise ValueError("RETURN_VIEWER_TREND_CONTRACT_MISSING")
    retention_v5.validate_story_contract(story)

    quality = job.get("quality_report")
    if not isinstance(quality, dict) or quality.get("passed") is not True:
        raise ValueError("RETURN_VIEWER_REQUIRES_PASSED_PUBLICATION_QUALITY")

    follow_gate = clean(story.get("follow_conversion_gate")).upper()
    if follow_gate not in {"PASS", "NOT_APPLICABLE"}:
        raise ValueError(f"RETURN_VIEWER_FOLLOW_GATE_NOT_PASSED:{follow_gate}")

    expected_ctas = story.get("cta_text") if isinstance(story.get("cta_text"), dict) else {}
    variants = job.get("variants") if isinstance(job.get("variants"), dict) else {}
    platform_results: dict[str, Any] = {}
    issues: list[str] = []

    for platform in ("youtube_shorts", "tiktok"):
        variant = variants.get(platform) if isinstance(variants.get(platform), dict) else {}
        package = variant.get("text_package") if isinstance(variant.get("text_package"), dict) else {}
        actual_cta = clean(package.get("cta"))
        expected_cta = clean(expected_ctas.get(platform))
        cta_contract = package.get("platform_cta_contract")
        cta_contract = cta_contract if isinstance(cta_contract, dict) else {}

        checks = {
            "variant_present": bool(variant),
            "expected_cta_present": bool(expected_cta),
            "cta_exact_match": actual_cta.rstrip(".!? ") == expected_cta.rstrip(".!? "),
            "source_bound_viewer_value": cta_contract.get("source_bound_viewer_value") is True,
            "viewer_value_match": clean(cta_contract.get("viewer_value")) == clean(story.get("follow_reason")),
            "next_video_bridge_match": clean(cta_contract.get("next_video_bridge")) == clean(story.get("open_loop")),
            "quality_gates_weakened": cta_contract.get("quality_gates_weakened") is False,
            "visible_audio_same_source": cta_contract.get("visible_script_audio_overlay_same_source") is True,
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            issues.extend(f"{platform}:{name}" for name in failed)
        platform_results[platform] = {
            "checks": checks,
            "cta": actual_cta,
            "passed": not failed,
        }

    score = int(trend.get("return_viewer_score") or 0)
    follow_reason = clean(story.get("follow_reason"))
    open_loop_status = clean(story.get("open_loop_status")).upper()
    series_name = clean(story.get("series_name")) or None

    if not follow_reason:
        issues.append("follow_reason_missing")
    if not 0 <= score <= 100:
        issues.append("return_viewer_score_invalid")
    if open_loop_status == "HARD":
        if not clean(story.get("next_episode_candidate")):
            issues.append("hard_open_loop_next_episode_missing")
        if not series_name:
            issues.append("hard_open_loop_series_missing")

    if follow_gate == "NOT_APPLICABLE":
        status = "NOT_APPLICABLE" if not issues else "IMPROVE"
    else:
        status = "PASS" if not issues else "IMPROVE"

    return {
        "schema": "tayvoriq-return-viewer-gate-v5",
        "status": status,
        "request_id": request.get("request_id"),
        "series_name": series_name,
        "episode_number": story.get("episode_number"),
        "cta_type": story.get("cta_type"),
        "follow_reason": follow_reason,
        "open_loop_status": open_loop_status,
        "next_episode_candidate": story.get("next_episode_candidate"),
        "follow_conversion_gate": follow_gate,
        "return_viewer_score": score,
        "platforms": platform_results,
        "issues": issues,
        "quality_gates_weakened": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--report-out", required=True)
    args = parser.parse_args()

    request = load(Path(args.request))
    job_dir = Path(args.job_dir)
    job = load(job_dir / "job.json")
    report = evaluate(request, job)

    target = Path(args.report_out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

    if report["status"] == "IMPROVE":
        raise SystemExit("RETURN_VIEWER_IMPROVE:" + ",".join(report["issues"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
