"""Fail-closed real-location photo/footage gate for TAYVORIQ news Shorts.

This gate checks evidence supplied by the renderer; it does not obtain images or
establish a copyright license on its own. Until the Studio writes a complete,
verified manifest, the review cannot be delivered. No quality score can override
a missing real-media source.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PLATFORMS = ("youtube_shorts", "tiktok")
SCHEMA = "tayvoriq-real-media-provenance-v1"
REAL_SOURCES = {
    "official_press_photo", "official_press_video",
    "licensed_location_photo", "licensed_location_video",
    "first_party_location_photo", "first_party_location_video",
    "licensed_archive_location_photo", "licensed_archive_location_video",
}
FORBIDDEN = ("sketch", "skizz", "schemat", "diagram", "illustrat",
             "generated", "ai_generated", "synthetic", "placeholder",
             "explainer_card", "generic_stock", "stock_market")
RIGHTS = {"licensed", "owned", "cc_licensed", "permission_granted"}


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value or ""))
        return parsed.scheme == "https" and bool(parsed.netloc) and bool(parsed.hostname)
    except ValueError:
        return False


def _bad_visual_description(value: Any) -> bool:
    normalized = str(value or "").casefold()
    return any(token in normalized for token in FORBIDDEN)


def validate(job_dir: Path, request_id: str, platforms: tuple[str, ...] = PLATFORMS) -> dict[str, Any]:
    job_dir = Path(job_dir)
    bundle = _load(job_dir / "content_bundle.json")
    manifest = _load(job_dir / "real_media_provenance.json")
    issues: list[str] = []

    if manifest.get("schema") != SCHEMA:
        issues.append("REAL_MEDIA_PROVENANCE_MISSING_OR_INVALID")
    if not request_id or manifest.get("source_request_id") != request_id:
        issues.append("REAL_MEDIA_REQUEST_BINDING_INVALID")

    audit = bundle.get("preapproval_ai_audit") or {}
    visual_review = audit.get("visual_review") if isinstance(audit, dict) else {}
    if isinstance(visual_review, dict):
        # An AI audit can score 85/100 while explicitly recognizing a sketch.
        # A passing score must never erase this positive evidence of fake visuals.
        observations = [
            *(visual_review.get("findings") or []),
            *(visual_review.get("blockers") or []),
        ]
        if any(_bad_visual_description(item) for item in observations):
            issues.append("REAL_MEDIA_AUDIT_DETECTED_ILLUSTRATION")

    proof_by_platform = manifest.get("platforms")
    proof_by_platform = proof_by_platform if isinstance(proof_by_platform, dict) else {}
    checked = {}
    for platform in platforms:
        render = _load(job_dir / platform / "render_report.json")
        rendered = render.get("asset_report")
        proofs = proof_by_platform.get(platform)
        if not isinstance(rendered, list) or not rendered:
            issues.append(f"REAL_MEDIA_RENDER_ASSETS_MISSING:{platform}")
            continue
        if not isinstance(proofs, list) or len(proofs) != len(rendered):
            issues.append(f"REAL_MEDIA_PROOF_INCOMPLETE:{platform}")
            continue
        for index, (asset, proof) in enumerate(zip(rendered, proofs), 1):
            prefix = f"{platform}:scene_{index}"
            if not isinstance(asset, dict) or not isinstance(proof, dict):
                issues.append(f"REAL_MEDIA_ASSET_INVALID:{prefix}")
                continue
            source = str(asset.get("source") or "")
            mode = str(asset.get("render_mode") or "")
            if _bad_visual_description(source) or _bad_visual_description(mode):
                issues.append(f"REAL_MEDIA_GENERATED_ASSET_FORBIDDEN:{prefix}")
            if source not in REAL_SOURCES or proof.get("source") != source:
                issues.append(f"REAL_MEDIA_SOURCE_UNVERIFIED:{prefix}")
            if str(asset.get("asset") or "") != str(proof.get("asset") or "") or not str(proof.get("asset") or ""):
                issues.append(f"REAL_MEDIA_ASSET_BINDING_INVALID:{prefix}")
            if proof.get("scene") != index:
                issues.append(f"REAL_MEDIA_SCENE_BINDING_INVALID:{prefix}")
            if proof.get("actual_location_media") is not True or proof.get("subject_match_verified") is not True:
                issues.append(f"REAL_MEDIA_TOPIC_MATCH_UNVERIFIED:{prefix}")
            if proof.get("rights_status") not in RIGHTS or proof.get("rights_verified") is not True:
                issues.append(f"REAL_MEDIA_RIGHTS_UNVERIFIED:{prefix}")
            if not _url(proof.get("provenance_url")) or not _url(proof.get("rights_evidence_url")):
                issues.append(f"REAL_MEDIA_ORIGIN_OR_RIGHTS_URL_MISSING:{prefix}")
        checked[platform] = len(rendered)

    return {
        "schema": SCHEMA,
        "passed": not issues,
        "source_request_id": request_id,
        "checked_scenes": checked,
        "issues": list(dict.fromkeys(issues)),
        "quality_gates_weakened": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--report-out", default="implementation/out/control-plane/real-media-provenance-gate.json")
    args = parser.parse_args()
    result = validate(Path(args.job_dir), args.request_id)
    report = Path(args.report_out)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 43


if __name__ == "__main__":
    raise SystemExit(main())
