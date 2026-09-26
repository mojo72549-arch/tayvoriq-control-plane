from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tayvoriq_orchestration_contract as contract


class EditorialRequestPreflightTests(unittest.TestCase):
    def test_curated_list_cannot_dispatch_fallback_that_renderer_would_reject(self) -> None:
        selection = json.loads((ROOT / ".automation/tayvoriq-agent-v2/selections/20260926-evening-agentv2-r1.json").read_text())
        trend = next(item for item in selection["trends"] if item["id"] == "5")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "selection.json"
            output = Path(tmp) / "requests"
            path.write_text(json.dumps(selection))
            args = SimpleNamespace(trend_request=str(path), trend_id="5", selection_id=selection["selection_id"],
                                   message_id="2867", payload_topic=trend["title"],
                                   approved_at="2026-09-26T15:09:05Z", out_dir=str(output))
            with self.assertRaisesRegex(SystemExit, "SOURCE_CONTEXT_EDITORIAL_INVALID"):
                contract.create_from_telegram(args)
            self.assertEqual(list(output.glob("*.json")), [])

            repaired = json.loads((ROOT / "requests/telegram-2867-trend-5-source-repair-v1.json").read_text())
            trend["source_context"] = repaired["source_context"]
            path.write_text(json.dumps(selection))
            contract.create_from_telegram(args)
            generated = json.loads((output / "telegram-2867-trend-5.json").read_text())
            contract.validate(generated, require_claimable=True)
            self.assertEqual(generated["topic"], trend["title"])
            self.assertEqual(generated["source_context"]["sources"], repaired["source_context"]["sources"])


if __name__ == "__main__":
    unittest.main()
