"""Hand a verified Studio implementation to the existing production preflight."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

WORKFLOW = "tayvoriq-production-green-promoter.yml"
STUDIO_STATUS = ("repos/mojo72549-arch/shorts-agent-studio/contents/.automation/"
                 "tayvoriq-quality-status.json?ref=feature/multi-platform-distribution-package")


def verified_candidate(status, green):
    if (status.get("state") != "TAYVORIQ_QUALITY_GATES_PASSED"
            or not all(status.get(key) is True for key in (
                "compile_passed", "editorial_selftests_passed", "all_tayvoriq_tests_passed", "diff_gate_passed"))
            or not re.fullmatch(r"[0-9a-f]{40}", str(status.get("tested_sha") or ""))
            or not re.fullmatch(r"[1-9][0-9]*", str(status.get("run_id") or ""))):
        raise ValueError("No verified Studio quality receipt")
    return status["tested_sha"] if status["tested_sha"] != green["implementation_sha"] else None


def handoff(candidate, list_runs, dispatch, pause=time.sleep):
    title = "Verify Studio " + candidate
    runs = list_runs()
    existing = next((r for r in runs if r.get("display_title") == title), None)
    if existing:
        return "Studio-Prüflauf bereits erfasst", existing["html_url"]
    active = next((r for r in runs if r.get("status") != "completed" and r.get("event") != "pull_request"), None)
    if active:
        return "Produktionsprüfung läuft", active["html_url"]
    # A timed-out dispatch can still start the verifier. Check its exact title before reporting the outcome.
    error = None
    try:
        dispatch(candidate)
    except subprocess.SubprocessError as exc:
        error = exc
    for attempt in range(5):
        if attempt:
            pause(2)
        try:
            runs = list_runs()
        except subprocess.SubprocessError:
            continue
        receipt = next((r for r in runs if r.get("display_title") == title), None)
        if receipt:
            return "Studio-Prüflauf bestätigt", receipt["html_url"]
    raise RuntimeError("GitHub hat den Prüflauf noch nicht bestätigt") from error


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    green = json.loads(Path(".github/state/tayvoriq-production-green.json").read_text())
    studio_env = dict(os.environ, GH_TOKEN=os.environ["STUDIO_READ_TOKEN"])
    status = json.loads(subprocess.check_output(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw+json", STUDIO_STATUS], env=studio_env, text=True))
    candidate = verified_candidate(status, green)
    if candidate:
        def list_runs():
            path = f"repos/{repo}/actions/workflows/{WORKFLOW}/runs?branch=main&per_page=50"
            return json.loads(subprocess.check_output(["gh", "api", path], text=True))["workflow_runs"]

        def dispatch(sha):
            subprocess.run(["gh", "workflow", "run", WORKFLOW, "--ref", "main", "-f", "candidate_sha=" + sha], check=True)

        message, url = handoff(candidate, list_runs, dispatch)
        summary = f"[{message}]({url}) · Studio `{candidate}`"
    else:
        summary = f"Geprüfter Studio-Stand ist produktiv · `{green['implementation_sha']}`"
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        print("### Studio-Freigabe\n\n" + summary, file=stream)


if __name__ == "__main__":
    main()
