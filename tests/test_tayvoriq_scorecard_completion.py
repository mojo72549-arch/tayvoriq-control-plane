import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tayvoriq_regional_relevance import WEIGHTS, complete_scorecards, evaluate


class CompletionTest(unittest.TestCase):
    def setUp(self):
        self.sources = [{"source_id": sid, "url": url, "supports": title} for sid, url, title in
                        [("S003", "https://a.de/1", "Ab Montag fährt die neue Bahn."),
                         ("S008", "https://b.de/2", "Die Bahn verbindet beide Stadtteile.")]]
        self.choices = {s["source_id"]: {s["source_id"] + ":title": s["supports"]} for s in self.sources}
        self.card = {"ratings": {k: [4, 4, "Die Verbindung verkürzt den Arbeitsweg."] for k in WEIGHTS},
                     "platform_fit": {"youtube": "Die neue Strecke im Vergleich.", "tiktok": "Der Weg zum Bahnhof wird kürzer."},
                     "evidence": {s["source_id"]: s["supports"] for s in self.sources}}
        self.candidate = {"title": "Die neue Bahn", "fallback_editorial_answers": {"what_happened": "Neue Bahn"},
                          "sources": self.sources, "regional_scorecard": self.card}

    def complete(self, reply):
        self.candidate["_retrieved_regional_assessment"] = evaluate(self.card, self.sources)
        call = Mock(return_value={"S003+S008": reply})
        complete_scorecards([self.candidate], self.choices, call)
        return self.candidate["_retrieved_regional_assessment"], call

    def test_repairs_reason_and_preserves_both_grades(self):
        self.card["ratings"]["consequence"] = [4, 2, ""]
        assessment, call = self.complete({"consequence.reason": "Der Anschluss verkürzt den Arbeitsweg.",
                                          "consequence.tiktok": 5})
        self.assertFalse(assessment["passed"])
        self.assertEqual(assessment["ratings"]["consequence"][:2], [4, 2])
        self.assertEqual(set(call.call_args.args[0]["S003+S008"]["missing"]), {"consequence.reason"})

    def test_quote_must_belong_to_correct_source(self):
        self.card["evidence"].pop("S003")
        self.assertFalse(self.complete({"evidence.S003": "S008:title"})[0]["passed"])
        self.assertTrue(self.complete({"evidence.S003": "S003:title"})[0]["passed"])

    def test_valid_or_weak_complete_card_never_triggers_rescoring(self):
        self.complete({})[1].assert_not_called()
        self.card["ratings"]["explanation"][0] = 1
        self.complete({})[1].assert_not_called()
