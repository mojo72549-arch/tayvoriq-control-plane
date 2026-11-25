"""Detect a repeated failed visual checkpoint using consecutive run artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PLATFORMS = {"youtube_shorts": "short_youtube.mp4", "tiktok": "short_tiktok.mp4"}
VISUAL_RETRY_STATES = {"LOCAL_VISUAL_REPAIR_REQUIRED", "PUBLISHABLE_OUTPUT_RETRY_REQUIRED"}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _visual_findings(audit: dict) -> tuple | None:
    review = audit["visual_review"]
    blockers = audit["blockers"]
    if (audit["passed"] is not False or audit["quality_gates_weakened"] is not False
            or review["passed"] is not False or not blockers or not review["reviewed_frames"]):
        return None

    findings = set()
    for blocker in blockers:
        if re.fullmatch(r"score_below_threshold:visual:\d+<\d+", blocker):
            findings.add(("visual-score-below-threshold", blocker.split("<", 1)[1]))
        elif blocker == "visual_agent_recommendation_block":
            findings.add((blocker,))
        elif blocker.startswith("visual_agent:scene_"):
            findings.add((blocker,))
        elif blocker.startswith("visual_agent:"):
            # Legacy audits use free text for the recommendation. Identical
            # exports and frame samples are required in addition to this gate.
            findings.add(("visual-agent-rejected-frames",))
        else:
            return None
    return tuple(sorted(findings)), tuple(review["reviewed_frames"])


def _snapshot(root: Path, run_id: int, attempt: int, request_id: str) -> dict | None:
    manifest = json.loads((root / "control-plane/production-manifest.json").read_bytes())
    meta = json.loads((root / "recovery-checkpoint-meta.json").read_bytes())
    for proof in (manifest, meta):
        if (int(proof["run_id"]) != run_id or int(proof["run_attempt"]) != attempt
                or proof["source_request_id"] != request_id or proof["quality_gates_weakened"] is not False):
            return None
    if (not _sha(meta["source_context_sha256"])
            or manifest["source_context_sha256"] != meta["source_context_sha256"]
            or not re.fullmatch(r"[0-9a-f]{40}", meta["implementation_sha"])
            or manifest["implementation_sha"] != meta["implementation_sha"]):
        return None

    hashes = meta["files_sha256"]
    reports = {}
    for name in ("job.json", "preapproval_ai_audit.json"):
        raw = (root / "job" / name).read_bytes()
        if _digest(raw) != hashes[name]:
            return None
        reports[name] = json.loads(raw)
    findings = _visual_findings(reports["preapproval_ai_audit.json"])
    if findings is None:
        return None

    variants = reports["job.json"]["variants"]
    media = {}
    for platform, export in PLATFORMS.items():
        if not _sha(hashes[export]):
            return None
        scenes = []
        for number, row in enumerate(variants[platform]["render"]["asset_report"], 1):
            requested, selected = row["requested_query"], row["query"]
            source = row["pexels_source_sha256"]
            if (row["scene"] != number or not isinstance(requested, str) or not requested.strip()
                    or not isinstance(selected, str) or not selected.strip() or not _sha(source)):
                return None
            scenes.append((requested, selected, source))
        if not scenes:
            return None
        media[platform] = (hashes[export], scenes)
    return {"source": meta["source_context_sha256"], "implementation": meta["implementation_sha"],
            "media": media, "findings": findings}


def record_visual_no_progress(evidence: dict, previous: Path, current: Path) -> dict:
    if (evidence.get("state") not in VISUAL_RETRY_STATES
            or evidence.get("quality_gates_weakened") is not False
            or evidence.get("master_reusable") is not True or not evidence.get("request_id")):
        return evidence
    try:
        run_id, attempt = int(evidence["run_id"]), int(evidence["run_attempt"])
        if attempt < 2:
            return evidence
        old = _snapshot(previous, run_id, attempt - 1, evidence["request_id"])
        new = _snapshot(current, run_id, attempt, evidence["request_id"])
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return evidence
    if old is None or old != new:
        return evidence
    fingerprint = _digest(json.dumps(new, sort_keys=True, ensure_ascii=False).encode())
    return {**evidence, "visual_no_progress_sha256": fingerprint}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("previous", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("contract", type=Path)
    args = parser.parse_args()
    evidence = json.loads(args.contract.read_bytes())
    updated = record_visual_no_progress(evidence, args.previous, args.current)
    if updated != evidence:
        args.contract.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("VISUAL_RECOVERY_NO_PROGRESS:" + updated["visual_no_progress_sha256"])


if __name__ == "__main__":
    main()
