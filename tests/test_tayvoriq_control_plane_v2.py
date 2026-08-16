from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_agent_series_state_v2 as series_state


ROOT = Path(__file__).resolve().parents[1]


class WorkflowContractTests(unittest.TestCase):
    def test_only_agent_v2_owns_twice_daily_schedule(self) -> None:
        scheduler = (ROOT / ".github/workflows/tayvoriq-agent-orchestrator-v2.yml").read_text(encoding="utf-8")
        bridge = (ROOT / ".github/workflows/tayvoriq-daily-orchestrator.yml").read_text(encoding="utf-8")
        dispatcher = (ROOT / ".github/workflows/tayvoriq-request-dispatch.yml").read_text(encoding="utf-8")
        for cron in ('30 4 * * *', '30 5 * * *', '30 15 * * *', '30 16 * * *'):
            self.assertIn(cron, scheduler)
        self.assertNotIn("afternoon", scheduler.lower())
        self.assertNotIn("\n  schedule:", bridge)
        self.assertNotIn("tayvoriq-deliver-video-now.yml", bridge)
        self.assertNotIn("*/5 * * * *", dispatcher)

    def test_selection_snapshot_contract_is_wired_end_to_end(self) -> None:
        scheduler = (ROOT / ".github/workflows/tayvoriq-agent-orchestrator-v2.yml").read_text(encoding="utf-8")
        dispatcher = (ROOT / ".github/workflows/tayvoriq-request-dispatch.yml").read_text(encoding="utf-8")
        worker = (ROOT / "infra/telegram-approval-worker-v2.js").read_text(encoding="utf-8")
        self.assertIn(".automation/tayvoriq-agent-v2/selections/", scheduler)
        self.assertIn("SELECTION_SNAPSHOT_MISSING", dispatcher)
        self.assertIn("loadTrendRequest(env, selectionId)", worker)
        self.assertIn("reject_trend:${selectionId}:${trendId}", worker)
        self.assertIn("trend_reason:newtrend:${selectionId}:${trendId}", worker)

    def test_series_selection_ids_remain_owned_by_agent_v2(self) -> None:
        builder = (ROOT / "tools/tayvoriq_agent_series_request_v2.py").read_text(encoding="utf-8")
        self.assertIn('-agentv2-', builder)
        self.assertIn('[:10]', builder)


class SeriesLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ("requests", "reviews", "maps"):
            (self.root / name).mkdir()
        self.state = {
            "series_id": "series-1",
            "status": "ready_for_selection",
            "episode": 1,
            "episodes": [{
                "episode": 2,
                "episode_title": "Episode 2",
                "cover_text": "TWO",
                "hook": "Hook",
                "bridge_out": "Bridge",
                "visual_continuity": "Continuity",
                "trend": {"title": "Next"},
            }],
        }
        request = {
            "request_id": "request-1",
            "selection_id": "selection-agentv2",
            "golden_path_run_id": 123,
            "source_context": {"series_context": {"series_id": "series-1", "episode": 1}},
        }
        (self.root / "requests/request-1.json").write_text(json.dumps(request), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def reconcile(self) -> tuple[dict, bool, str]:
        return series_state.reconcile(
            dict(self.state),
            self.root / "requests",
            self.root / "reviews",
            self.root / "maps",
        )

    def test_unpublished_episode_remains_in_flight(self) -> None:
        state, changed, reason = self.reconcile()
        self.assertFalse(changed)
        self.assertEqual(reason, "current_episode_not_published")
        self.assertEqual(state["episode"], 1)

    def test_verified_root_run_advances_exactly_one_episode(self) -> None:
        review = {"review_id": "123", "platform_upload_performed": True}
        (self.root / "reviews/123.json").write_text(json.dumps(review), encoding="utf-8")
        state, changed, reason = self.reconcile()
        self.assertTrue(changed)
        self.assertEqual(reason, "advanced_to_next_episode")
        self.assertEqual(state["episode"], 2)
        self.assertEqual(state["trend"]["title"], "Next")

    def test_verified_recovery_run_advances_source_request(self) -> None:
        mapping = {
            "run_id": 456,
            "source_request_id": "request-1",
            "selection_id": "selection-agentv2",
        }
        review = {"review_id": "456", "platform_upload_performed": True}
        (self.root / "maps/456.json").write_text(json.dumps(mapping), encoding="utf-8")
        (self.root / "reviews/456.json").write_text(json.dumps(review), encoding="utf-8")
        state, changed, _ = self.reconcile()
        self.assertTrue(changed)
        self.assertEqual(state["episode"], 2)


if __name__ == "__main__":
    unittest.main()
