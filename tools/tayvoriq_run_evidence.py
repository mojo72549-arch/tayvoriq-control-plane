"""Summarize the artifacts belonging to one Golden Path attempt. Read-only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


PLATFORMS = {"youtube_shorts": "YouTube", "tiktok": "TikTok"}
SCENE_PROFILES = {"vw-verified-sister-platform-scene-revision-v1", "verified-sister-platform-scene-revision-v1"}


def document(path: Path, digest: str | None = None) -> dict:
    try:
        data = path.read_bytes()
        if digest is not None and hashlib.sha256(data).hexdigest() != digest:
            return {}
        parsed = json.loads(data)
        return parsed if isinstance(parsed, dict) else {}
    except (OSError, ValueError):
        return {}


def collect(root: Path, run: str, attempt: str, request: str, source: str) -> dict:
    manifest = document(root / "control-plane/production-manifest.json")
    if not (re.fullmatch(r"[1-9]\d*", run) and re.fullmatch(r"[1-9]\d*", attempt)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", request)
            and re.fullmatch(r"[0-9a-f]{64}", source)):
        raise ValueError("Auftrag, Versuch oder Quellenbindung fehlt")
    binding = {"run_id": run, "run_attempt": attempt, "source_request_id": request,
               "source_context_sha256": source}

    def matches(record):
        return all(str(record.get(key, "")) == value for key, value in binding.items())

    if not matches(manifest):
        raise ValueError("Produktionsmanifest gehört nicht zu diesem Versuch")
    report = {"schema": 1, **binding, "studio_sha": manifest["implementation_sha"],
              "checkpoint_restored": manifest.get("restored_recovery_checkpoint") is True,
              "tools": [], "scores": [], "findings": []}
    meta = document(root / "recovery-checkpoint-meta.json")
    if not matches(meta) or meta.get("implementation_sha") != report["studio_sha"]:
        return report
    hashes = meta.get("files_sha256") or {}

    def proof(name):
        return document(root / "job" / name, hashes.get(name, ""))

    def record(tool, activity, evidence):
        report["tools"].append({"name": tool, "activity": activity, "evidence": evidence})

    audit = proof("preapproval_ai_audit.json")
    for key, platform in PLATFORMS.items():
        name = f"{key}/audio_report.json"
        if proof(name).get("voice_provider_used") == "chatterbox_multilingual_v3":
            action = "Stimme im geprüften Export" if report["checkpoint_restored"] else "Stimme erzeugt"
            record("Chatterbox", f"{platform} · {action}", "job/" + name)
        asr = (audit.get("audio_reports") or {}).get(key) or {}
        if (asr.get("transcription_model") or "").startswith("whisper") and type(asr.get("passed")) is bool:
            outcome = "bestanden" if asr["passed"] else "beanstandet"
            record("Whisper", f"{platform} · Transkriptprüfung {outcome}", "job/preapproval_ai_audit.json")

    revision = proof("job.json").get("visual_checkpoint_repair") or {}
    target = PLATFORMS.get(revision.get("target_platform"))
    replacements = revision.get("replacement_clips") or {}
    scenes = sorted(int(n) for n, row in replacements.items()
                    if str(n).isdigit() and isinstance(row, dict)
                    and re.fullmatch(r"[0-9a-f]{64}", str(row.get("new_source_clip_sha256") or ""))
                    and row.get("new_source_clip_sha256") != row.get("old_source_clip_sha256"))
    if (revision.get("profile") in SCENE_PROFILES and target and scenes
            and re.fullmatch(r"[0-9a-f]{64}", str(revision.get("revised_export_sha256") or ""))):
        activity = f"{target} · Szenen " + ", ".join(map(str, scenes)) + " ersetzt"
        seconds = revision.get("repair_wall_seconds")
        if type(seconds) in (int, float) and 0 < seconds < 86400:
            activity += f" ({seconds:.1f} s)"
        record("MoneyPrinterTurbo", activity, "job/job.json · visual_checkpoint_repair")
        if all(re.fullmatch(r"[0-9a-f]{64}", str((revision.get("audio_sha256") or {}).get(key) or ""))
               for key in ("copy", "pcm_s16le")):
            record("FFmpeg / ffprobe", f"{target} · Videospur zusammengesetzt, Originalton geprüft",
                   "job/job.json · visual_checkpoint_repair.audio_sha256")
    for key, label in (("factual_accuracy", "Fakten"), ("visual", "Bild"), ("overall", "Gesamt")):
        value, threshold = (audit.get("scores") or {}).get(key), (audit.get("thresholds") or {}).get(key)
        if all(type(n) in (int, float) and 0 <= n <= 100 for n in (value, threshold)):
            report["scores"].append({"name": label, "value": value, "threshold": threshold})
    for row in (audit.get("visual_review") or {}).get("scene_checks") or []:
        platform = PLATFORMS.get(row.get("platform"))
        if platform and type(row.get("scene")) is int and row["scene"] > 0:
            if row.get("relevant") is False or row.get("distinct") is False:
                reason = "Motiv unpassend" if row.get("relevant") is False else "Motiv wiederholt"
                report["findings"].append(f"{platform} · Szene {row['scene']} · {reason}")
    return report


def summary(report: dict) -> str:
    lines = ["## Produktion und Qualitätsprüfung", "",
             f"Auftrag `{report['source_request_id']}` · Lauf {report['run_id']} · Versuch {report['run_attempt']}", "",
             "| Werkzeug | Aufgabe im vorliegenden Export | Nachweis in der Diagnose |",
             "| --- | --- | --- |"]
    for row in report["tools"]:
        lines.append(f"| {row['name']} | {row['activity']} | {row['evidence']} |")
    if not report["tools"]:
        lines.append("| – | Kein gebundener Werkzeugnachweis für diesen Versuch | – |")
    lines.extend(["", *[f"- {s['name']}: {s['value']}/100 (Mindestwert {s['threshold']})" for s in report["scores"]],
                  *[f"- {finding}" for finding in report["findings"]]])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("diagnostics", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = collect(args.diagnostics, os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"],
                     os.environ["SOURCE_REQUEST_ID_PIN"], os.environ["SOURCE_CONTEXT_SHA256"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(summary(report), end="")


if __name__ == "__main__":
    main()
