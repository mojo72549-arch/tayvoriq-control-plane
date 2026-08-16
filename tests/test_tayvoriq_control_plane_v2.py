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
        for cron in ('30 3 * * *', '30 4 * * *', '0 17 * * *', '0 18 * * *'):
            self.assertIn(cron, scheduler)
        for stale_cron in ('30 5 * * *', '30 15 * * *', '30 16 * * *'):
            self.assertNotIn(stale_cron, scheduler)
        self.assertIn("'evening': '0 17 * * *' if offset == 2 else '0 18 * * *'", scheduler)
        self.assertNotIn("afternoon", scheduler.lower())
        self.assertNotIn("\n  schedule:", bridge)
        self.assertNotIn("tayvoriq-deliver-video-now.yml", bridge)
        self.assertNotIn("*/5 * * * *", dispatcher)

    def test_local_repair_is_checkpointed_before_publishable_assert(self) -> None:
        golden = (
            ROOT / ".github/workflows/tayvoriq-deliver-video-now.yml"
        ).read_text(encoding="utf-8")
        repair = golden.index("- name: Repair only failed local checkpoints")
        refresh = golden.index(
            "- name: Refresh lean recovery checkpoint after local repair"
        )
        persist = golden.index("- name: Persist refreshed post-repair checkpoint")
        publishable = golden.index("- name: Assert publishable production output")

        self.assertLess(repair, refresh)
        self.assertLess(refresh, persist)
        self.assertLess(persist, publishable)
        self.assertIn("-post-local-repair", golden)
        self.assertIn("steps.checkpoint_recovery.outputs.state", golden)
        self.assertIn("quality_gates_weakened", golden)

    def test_in_flight_series_never_falls_back_to_loose_trends(self) -> None:
        scheduler = (ROOT / ".github/workflows/tayvoriq-agent-orchestrator-v2.yml").read_text(encoding="utf-8")
        self.assertIn(
            "Active series episode is still in flight; no duplicate episode or loose trend is proposed.",
            scheduler,
        )
        self.assertIn(
            "if: steps.slot.outputs.should_run == 'true' && steps.mode.outputs.active_series != 'true'",
            scheduler,
        )
        self.assertIn(
            "steps.mode.outputs.series_in_flight != 'true'",
            scheduler,
        )
        self.assertNotIn(
            "steps.mode.outputs.active_series != 'true' || steps.mode.outputs.series_in_flight == 'true'",
            scheduler,
        )

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
            "topic": "Episode One",
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

    def test_verified_youtube_title_recovers_missing_run_map(self) -> None:
        review = {
            "review_id": "999",
            "status": "APPROVED",
            "platform_upload_performed": True,
            "upload_status": "PUBLISHED_YOUTUBE",
            "youtube": {"video_id": "video-1", "privacy": "public"},
            "published_payload": {"title": "  Episode   One  "},
        }
        (self.root / "reviews/999.json").write_text(json.dumps(review), encoding="utf-8")
        state, changed, reason = self.reconcile()
        self.assertTrue(changed)
        self.assertEqual(reason, "advanced_to_next_episode")
        self.assertEqual(state["episode"], 2)

    def test_explicit_publication_run_id_is_accepted(self) -> None:
        path = self.root / "requests/request-1.json"
        request = json.loads(path.read_text(encoding="utf-8"))
        request["published_run_id"] = 777
        path.write_text(json.dumps(request), encoding="utf-8")
        review = {"review_id": "777", "platform_upload_performed": True}
        (self.root / "reviews/777.json").write_text(json.dumps(review), encoding="utf-8")
        state, changed, _ = self.reconcile()
        self.assertTrue(changed)
        self.assertEqual(state["episode"], 2)

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
