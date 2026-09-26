from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def test_failure_handoff_prefers_failed_recovery_over_stale_preflight(tmp_path):
    workflow = Path(".github/workflows/tayvoriq-deliver-video-now.yml").read_text(
        encoding="utf-8"
    )
    section = workflow.split("- name: Record internal failure for Delivery Watch", 1)[1]
    match = re.search(r"python - <<'PY'\n(.*?)\n          PY", section, re.S)
    assert match, "Failure handoff Python block missing"
    script = "\n".join(
        line.removeprefix("          ") for line in match.group(1).splitlines()
    )

    report = tmp_path / "implementation/out/tayvoriq-self-heal/report.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"state": "PREFLIGHT_PASSED"}), encoding="utf-8")
    env = {
        **os.environ,
        "PRODUCTION_OUTCOME": "failure",
        "RECOVERY_STATE": "PUBLISHABLE_OUTPUT_RETRY_REQUIRED",
        "CONTROLLER_STATE": "PUBLISHABLE_OUTPUT_RETRY_REQUIRED",
        "REUSABLE_MASTER": "true",
    }
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    policy = json.loads(
        (tmp_path / "implementation/out/control-plane/failure-notification-policy.json")
        .read_text(encoding="utf-8")
    )
    assert policy["state"] == "PUBLISHABLE_OUTPUT_RETRY_REQUIRED"
    assert policy["failure_class"] == "PUBLISHABLE_CHECKPOINT"
    assert policy["master_reusable"] is True
    assert policy["full_regeneration_allowed"] is False
