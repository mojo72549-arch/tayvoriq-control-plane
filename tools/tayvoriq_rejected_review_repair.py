"""Dispatch one scoped Golden Path correction for a bound rejected review."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from tayvoriq_rejected_review_followup import REPAIRS, followup, read

WORKFLOW = "tayvoriq-deliver-video-now.yml"


def checked(*args):
    return subprocess.check_output(args, text=True)


def publish(path, execution):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
    checked("git", "add", "--", str(path))
    checked("git", "-c", "user.name=github-actions[bot]", "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", f"ops: record rejected review correction {execution['rejected_run_id']}", "--", str(path))
    for attempt in range(3):
        if subprocess.run(["git", "push", "origin", "HEAD:main"], check=False).returncode == 0:
            return
        checked("git", "pull", "--rebase", "origin", "main")
    raise RuntimeError("Review repair state could not be persisted")


def matching_run(runs, rejected_run):
    title = f"TAYVORIQ review correction {rejected_run}"
    exact = [run for run in runs if run.get("display_title") == title
             and run.get("event") == "workflow_dispatch" and run.get("head_branch") == "main"
             and type(run.get("id")) is int and run["id"] > 0]
    if len(exact) > 1:
        raise RuntimeError("Multiple Golden Path runs claimed one review correction")
    return exact[0] if exact else None


def reconcile():
    plan = followup()
    if not plan or not plan["replacement_dispatch_allowed"] or plan["selection_delivered"]:
        return
    old = plan["rejected_run_id"]
    path = Path(REPAIRS) / f"{old}.json"
    repo = os.environ["GITHUB_REPOSITORY"]
    request = read(Path("requests") / f"{plan['request_id']}.json")
    identity = {key: plan[key] for key in ("rejected_run_id", "request_id", "source_context_sha256")}
    execution = read(path)
    if execution and any(execution.get(key) != value for key, value in identity.items()):
        raise RuntimeError("Persisted review repair does not match its review")

    def lookup():
        query = f"repos/{repo}/actions/workflows/{WORKFLOW}/runs?branch=main&event=workflow_dispatch&per_page=100"
        return matching_run(json.loads(checked("gh", "api", query))["workflow_runs"], old)

    run = lookup()
    if not execution:
        if run:
            raise RuntimeError("Review correction run has no authorization record")
        execution = {**identity, "state": "REQUESTED", "requested_at_epoch": int(time.time())}
        publish(path, execution)
        try:
            checked("gh", "workflow", "run", WORKFLOW, "--ref", "main", "-f", f"review_repair_of={old}",
                    "-f", f"source_request_id={plan['request_id']}", "-f", f"trend_id={request['trend_id']}",
                    "-f", f"recovery_generation={request.get('recovery_generation') or 0}")
        except subprocess.CalledProcessError:
            # GitHub may have accepted the dispatch even if the response was lost.
            pass
        for _ in range(8):
            run = lookup()
            if run:
                break
            time.sleep(2)
    if not run and execution.get("run_id"):
        run = json.loads(checked("gh", "api", f"repos/{repo}/actions/runs/{int(execution['run_id'])}"))
        run = matching_run([run], old)
    if not run and time.time() - execution["requested_at_epoch"] < 120:
        return
    if run and execution.get("run_id") not in (None, run["id"]):
        raise RuntimeError("Review correction run identity changed")
    # A successful handoff replaces the canonical run. If this run ended and
    # the original review still owns the pointer, research a replacement.
    checked("git", "pull", "--ff-only", "origin", "main")
    latest = followup()
    if not latest or latest["rejected_run_id"] != old:
        return
    update = {**execution, "run_id": run["id"] if run else None,
              "state": "RUNNING" if run and run.get("status") != "completed" else "FAILED"}
    if update != execution:
        publish(path, update)
    if update["state"] == "FAILED":
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"failed_review={old}\n")


def guard(previous, new_run, request_id):
    plan = followup()
    if not (plan and plan["replacement_dispatch_allowed"] and plan["rejected_run_id"] == previous
            and plan["request_id"] == request_id and plan["repair_run_id"] == new_run):
        raise ValueError("Review correction authorization is missing or no longer current")
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--guard", nargs=3, metavar=("REJECTED_RUN", "NEW_RUN", "REQUEST"))
    args = parser.parse_args()
    if args.guard:
        old, run, request_id = args.guard
        print(json.dumps(guard(int(old), int(run), request_id)))
    else:
        reconcile()
