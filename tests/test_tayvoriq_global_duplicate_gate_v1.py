from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_global_duplicate_gate_v1 as duplicate_gate


def request(request_id: str, topic: str, context: dict, *, status: str = "DISPATCHED") -> dict:
    return {
        "request_id": request_id,
        "status": status,
        "topic": topic,
        "source_context": context,
    }


class GlobalDuplicateGateTests(unittest.TestCase):
    def test_live_world_forces_episode_two_is_distinct_from_published_episode_one(self) -> None:
        prior = json.loads((ROOT / "requests/telegram-902-trend-1.json").read_text(encoding="utf-8"))
        current = json.loads((ROOT / "requests/telegram-1004-trend-1.json").read_text(encoding="utf-8"))
        metrics = duplicate_gate.compare(
            topic=current["topic"],
            source_context=current["source_context"],
            prior_topic=prior["topic"],
            prior_context=prior["source_context"],
        )
        self.assertFalse(metrics["blocked"], metrics)
        self.assertFalse(metrics["same_series_episode"])
        self.assertLess(metrics["content_cosine"], 0.82)

    def test_same_series_episode_under_new_request_id_is_always_blocked(self) -> None:
        prior = json.loads((ROOT / "requests/telegram-902-trend-1.json").read_text(encoding="utf-8"))
        metrics = duplicate_gate.compare(
            topic="Die Erde bewegt sich ständig unter unseren Füßen",
            source_context=prior["source_context"],
            prior_topic=prior["topic"],
            prior_context=prior["source_context"],
        )
        self.assertTrue(metrics["blocked"])
        self.assertIn("same_series_episode", metrics["duplicate_reasons"])

    def test_differently_worded_same_verified_story_is_blocked(self) -> None:
        context = {
            "fallback_editorial_answers": {
                "what_happened": "Verhakte Gesteinsblöcke rutschen plötzlich an einer Störung gegeneinander.",
                "why_happening": "Plattenbewegung speichert Spannung, bis sie stärker als die Reibung wird.",
                "who_is_affected": "Gefährdet sind Menschen nahe aktiver Störungen und Plattengrenzen.",
                "personal_impact": "Schäden hängen von Tiefe, Untergrund und Bauweise ab.",
                "action_now": "Nutze offizielle Erdbebendienste statt Vorhersagegerüchten.",
            },
            "sources": [
                {"url": "https://www.usgs.gov/faqs/what-earthquake-and-what-causes-them-happen"},
                {"url": "https://www.gfz.de/en/earthquakes"},
            ],
        }
        rewritten = json.loads(json.dumps(context))
        rewritten["fallback_editorial_answers"]["what_happened"] = (
            "An einer Störung gleiten festgehakte Gesteinsblöcke auf einmal gegeneinander."
        )
        metrics = duplicate_gate.compare(
            topic="Wieso ein Erdbeben ohne Vorwarnung losbricht",
            source_context=rewritten,
            prior_topic="Warum Erdbeben plötzlich auftreten",
            prior_context=context,
        )
        self.assertTrue(metrics["blocked"], metrics)
        self.assertTrue(
            {"same_verified_story", "same_sources_and_story"} & set(metrics["duplicate_reasons"]),
            metrics,
        )

    def test_retry_of_exact_same_request_id_is_allowed(self) -> None:
        current = json.loads((ROOT / "requests/telegram-1004-trend-1.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "same.json").write_text(json.dumps(current), encoding="utf-8")
            report = duplicate_gate.run_gate(
                requests_dir=directory,
                source_request_id=current["request_id"],
                topic=current["topic"],
                source_context=current["source_context"],
            )
        self.assertTrue(report["passed"])
        self.assertEqual(report["history_candidates_checked"], 0)
        self.assertTrue(report["retry_of_same_request_allowed"])

    def test_inactive_draft_does_not_block_production(self) -> None:
        context = {"fallback_editorial_answers": {key: f"Antwort {key}" for key in duplicate_gate.ANSWER_KEYS}}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            prior = request("draft-1", "Gleiches Thema", context, status="DRAFT")
            (directory / "draft.json").write_text(json.dumps(prior), encoding="utf-8")
            report = duplicate_gate.run_gate(
                requests_dir=directory,
                source_request_id="approved-2",
                topic="Gleiches Thema",
                source_context=context,
            )
        self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()
