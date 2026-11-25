"""Run the real Studio entry point on a replayed, bound VW renderer output."""
from pathlib import Path
import os
import subprocess
import sys
from time import monotonic

import tayvoriq_preapproval_ai_audit as audit
from tayvoriq_scene_revision_v1 import _bound_scene, read_json, sha256, write_json, PLATFORMS, PROFILE
from tayvoriq_visual_only_repair_v1 import repair


def check(job_dir):
    job = read_json(job_dir / "job.json")
    source = sha256(job_dir / "source_context.resume.json")
    original = {p: sha256(job_dir / name) for p, name in PLATFORMS.items()}
    voices = {p: sha256(job_dir / p / "voice.mp3") for p in PLATFORMS}
    output = job_dir / "scene-revision-verification.json"
    report = {"starting_export_sha256": original, "source_context_sha256": source}
    try:
        visual = audit.gemini_visual_audit(job, job_dir)
        report["starting_visual_review"] = visual
        failed = {"passed": False, "visual_review": visual, "blockers": [
            f"visual_agent:{blocker}" for blocker in visual.get("blockers", [])
        ]}
        if not _bound_scene(job_dir, job, failed):
            report["state"] = "review_did_not_isolate_one_repairable_scene"
            raise SystemExit(1)
        write_json(job_dir / "preapproval_ai_audit.json", failed)
        started = monotonic()
        result = repair(job_dir)
        report["repair_seconds"] = monotonic() - started
        report["repair"] = result
        assert result.get("profile") == PROFILE
        after = read_json(job_dir / "job.json")
        assert sha256(job_dir / "source_context.resume.json") == source
        for platform in PLATFORMS:
            assert sha256(job_dir / platform / "voice.mp3") == voices[platform]
            assert after["variants"][platform]["text_package"] == job["variants"][platform]["text_package"]
        other = result["donor_platform"]
        assert sha256(job_dir / PLATFORMS[other]) == original[other]
        verified = subprocess.run([sys.executable, "tools/tayvoriq_preapproval_ai_audit_v4.py",
                                   "--job-dir", str(job_dir)], check=False, timeout=480,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        report["quality_gate_exit"] = verified.returncode
        report["state"] = "strict_audit_passed" if verified.returncode == 0 else "strict_audit_blocked"
        if verified.returncode:
            raise SystemExit(verified.returncode)
    except Exception as exc:
        report["failure_type"] = type(exc).__name__
        # Provider exception messages can include request headers or URLs.
        raise SystemExit(1) from None
    finally:
        write_json(output, report)
        print("VW scene revision diagnostic:", report.get("state", report.get("failure_type")), flush=True)


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve())
