from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExactRequestGenerationTests(unittest.TestCase):
    def test_pinned_zero_does_not_inherit_another_requests_generation(self) -> None:
        workflow = (ROOT / ".github/workflows/tayvoriq-deliver-video-now.yml").read_text()
        resolver = workflow.split("      - name: Resolve approved X request", 1)[1]
        resolver = textwrap.dedent(resolver.split("          python - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github/run-now").mkdir(parents=True)
            (root / "requests").mkdir()
            (root / ".github/run-now/tayvoriq-x-request.json").write_text(json.dumps({
                "source_request_id": "old-request", "topic": "Old", "trend_id": "1",
                "recovery_generation": 2,
            }))
            durable = root / "requests/current-request.json"
            durable.write_text(json.dumps({"request_id": "current-request", "recovery_generation": 0}))
            env = dict(os.environ, EVENT_TOPIC="Current", EVENT_TREND_ID="5",
                       EVENT_SOURCE_REQUEST_ID="current-request", EVENT_RECOVERY_GENERATION="0",
                       GITHUB_ENV=str(root / "env"), GITHUB_OUTPUT=str(root / "out"))
            result = subprocess.run([sys.executable, "-c", resolver], cwd=root, env=env,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)["recovery_generation"], 0)
            self.assertIn("TAYVORIQ_RECOVERY_GENERATION=0", (root / "env").read_text())

            durable.write_text(json.dumps({"request_id": "current-request", "recovery_generation": 1}))
            env["EVENT_RECOVERY_GENERATION"] = ""
            result = subprocess.run([sys.executable, "-c", resolver], cwd=root, env=env,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)["recovery_generation"], 1)


if __name__ == "__main__":
    unittest.main()
