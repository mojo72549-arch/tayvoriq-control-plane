import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_research_checkpoint as checkpoint
from tayvoriq_regional_relevance import WEIGHTS, evaluate
from tayvoriq_source_evidence_v1 import source_support


class RegionalCheckpointTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, TAYVORIQ_RESEARCH_CHECKPOINT_FILE=tmp.name + "/pool.json",
                         TAYVORIQ_RESEARCH_SLOT="evening", TAYVORIQ_RESEARCH_SELECTION_ID="")
        env.start()
        self.addCleanup(env.stop)
        title = "Mercedes investiert in Werk Stuttgart"
        self.records = [{"title": title, "context": context, "url": url, "seen_date": "now"} for url, context in
                        [("https://swr.de/werk", "Die Investition in das Werk ist beschlossen."),
                         ("https://handelsblatt.com/werk", "Mercedes investiert in das Werk in Stuttgart.")]]
        sources = []
        for i, r in enumerate(self.records):
            support, digest = source_support(r)
            sources.append({"source_id": str(i), "url": r["url"], "supports": support,
                            "source_record_sha256": digest, "source_date": "now"})
        self.raw = {"title": title, "sources": sources}
        card = {"evidence": {str(i): r["context"] for i, r in enumerate(self.records)},
                "ratings": {k: [4, 4, "Die Investition betrifft den Standort."] for k in WEIGHTS},
                "platform_fit": {k: "Konkrete Entwicklung am bekannten Standort." for k in ("youtube", "tiktok")}}
        self.assessment = evaluate(card, sources)
        self.assertTrue(self.assessment["passed"])
        checkpoint.remember(self.raw, self.assessment, "original-model")

    def test_both_current_records_required_and_original_model_retained(self):
        self.assertEqual(checkpoint.current(self.records)[0]["_checkpoint_model"], "original-model")
        self.assertEqual(checkpoint.current(self.records[:1]), [])

    def test_changed_fact_date_or_publisher_origin_invalidates_checkpoint(self):
        for change in ({"context": "Die Investition ist verschoben."}, {"seen_date": "later"}, {"origin": "dpa"}):
            self.assertEqual(checkpoint.current([self.records[0], {**self.records[1], **change}]), [])

    def test_other_slot_and_requested_replacement_have_separate_scope(self):
        for change in ({"TAYVORIQ_RESEARCH_SLOT": "morning"}, {"TAYVORIQ_RESEARCH_SELECTION_ID": "review-new"}):
            with patch.dict(os.environ, change):
                self.assertEqual(checkpoint.current(self.records), [])
