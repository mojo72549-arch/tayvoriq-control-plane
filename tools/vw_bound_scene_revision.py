"""Run the normal Studio recovery loop and all release guards, without delivery."""
from pathlib import Path
import json
import subprocess
import sys
from time import monotonic

from tayvoriq_scene_revision_v1 import read_json, sha256, write_json, PLATFORMS, video_timeline


def check(job_dir):
    job = read_json(job_dir / "job.json")
    source = sha256(job_dir / "source_context.resume.json")
    voices = {p: sha256(job_dir / p / "voice.mp3") for p in PLATFORMS}
    original = {p: sha256(job_dir / f) for p, f in PLATFORMS.items()}
    clocks = {p: video_timeline(job_dir / f) for p, f in PLATFORMS.items()}

    # The diagnostic candidate was just rendered from the bound historical
    # master. Do not reuse the historical verdict for the new export.
    (job_dir / "preapproval_ai_audit.json").unlink(missing_ok=True)
    outputs = job_dir / "verification-outputs"
    outputs.mkdir(exist_ok=True)
    report_out = outputs / "resume.json"
    started = monotonic()
    process = subprocess.run(
        [sys.executable, "tools/tayvoriq_resume_existing_render_v2.py",
         "--outdir", str(job_dir.parent), "--run-id", "45510042088",
         "--site-root", str(outputs / "site"),
         "--state-out", str(outputs / "review-state.json"),
         "--report-out", str(report_out)],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        timeout=800,
    )
    result = {"starting_export_sha256": original, "source_context_sha256": source,
              "elapsed_seconds": monotonic() - started, "canonical_exit": process.returncode}
    for line in process.stdout.splitlines():
        if line.startswith("SCENE_REVISION_FALLBACK:"):
            print(line)
        if 'checkpoint_repair_converged' in line or 'checkpoint_repair_round_failed_audit' in line:
            print(line)
    if report_out.is_file():
        receipt = read_json(report_out)
        result["state"] = receipt.get("state")
        result["repair_history"] = receipt.get("repair_history")
        result["repair_targets"] = receipt.get("repair_target_stages")
        result["gate_detail"] = receipt.get("reason")
    result["export_sha256"] = {p: sha256(job_dir / f) for p, f in PLATFORMS.items()}
    result["checkpoint_preserved"] = sha256(job_dir / "source_context.resume.json") == source
    result["voice_files_preserved"] = {p: sha256(job_dir / p / "voice.mp3") == voices[p] for p in PLATFORMS}
    result["frame_times_preserved"] = {p: video_timeline(job_dir / f) == clocks[p] for p, f in PLATFORMS.items()}
    verification = read_json(job_dir / "job.json")
    result["script_preserved"] = {
        p: verification["variants"][p]["text_package"]["script"] == job["variants"][p]["text_package"]["script"]
        for p in PLATFORMS
    }
    write_json(job_dir / "scene-revision-verification.json", result)
    print("Canonical checkpoint verification:", {k: v for k, v in result.items() if k not in ("repair_history", "gate_detail")}, flush=True)
    assert result["checkpoint_preserved"] and all(result["voice_files_preserved"].values())
    assert all(result["frame_times_preserved"].values()) and all(result["script_preserved"].values())
    assert result["export_sha256"]["tiktok"] == original["tiktok"]
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve())
