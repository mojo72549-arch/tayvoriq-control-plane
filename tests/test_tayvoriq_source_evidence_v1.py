import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tayvoriq_source_evidence_v1 import validate_pair, source_support


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {"title": "Mercedes investiert in Stuttgart in Werk"}
        self.records = [
            {"title": "Mercedes investiert in Stuttgart in Werk", "context": "Mercedes plant Investitionen in das Werk in Stuttgart.", "url": "https://tagesschau.de/wirtschaft/werk"},
            {"title": "Werk Stuttgart: Mercedes investiert", "context": "Das Werk Stuttgart bekommt Investitionen von Mercedes.", "url": "https://dw.com/werk"},
        ]

    def test_same_story_is_accepted_and_support_is_derived_from_original(self):
        self.assertEqual(validate_pair(self.candidate, self.records), [])
        text, digest = source_support(self.records[0])
        self.assertEqual(text, self.records[0]["title"] + " " + self.records[0]["context"])
        self.assertEqual(len(digest), 64)

    def test_mercedes_and_hamburg_flood_cannot_confirm_each_other(self):
        self.records[1].update(title="Hochwasser in Hamburg erwartet", context="Elbe steigt nach starkem Regen an.")
        reasons = validate_pair(self.candidate, self.records)
        self.assertIn("source_records_do_not_establish_same_story", reasons)
        self.assertIn("source_2_does_not_support_headline", reasons)

    def test_same_entity_alone_does_not_prove_same_event(self):
        self.records[1].update(title="Mercedes gewinnt Rennen in Monaco", context="Mercedes gewinnt mit neuem Fahrer.")
        self.assertTrue(validate_pair(self.candidate, self.records))

    def test_shared_company_and_location_cannot_hide_different_action(self):
        self.records[1].update(title="Mercedes schließt Werk in Stuttgart", context="Mercedes schließt das Werk in Stuttgart.")
        self.assertIn("source_2_does_not_support_headline", validate_pair(self.candidate, self.records))

    def test_invented_headline_number_is_rejected(self):
        self.candidate["title"] = "Mercedes investiert 1000 Millionen in Stuttgart Werk"
        self.assertIn("source_1_missing_headline_number", validate_pair(self.candidate, self.records))

    def test_bbc_aliases_and_declared_syndication_are_not_independent(self):
        self.records[0]["url"] = "https://bbc.com/news/1"
        self.records[1]["url"] = "https://feeds.bbc.co.uk/news/2"
        self.assertTrue(validate_pair(self.candidate, self.records))
        self.records[0]["url"] = "https://tagesschau.de/1"
        self.records[1]["url"] = "https://dw.com/2"
        for record in self.records:
            record["wire_agency"] = "Reuters"
        self.assertIn("same_declared_reporting_origin", validate_pair(self.candidate, self.records))

    def test_identical_long_context_is_not_independent_confirmation(self):
        for record in self.records:
            record["context"] = "Mercedes investiert in Stuttgart in sein Werk. " * 4
        self.assertIn("identical_source_context_is_not_independent_confirmation", validate_pair(self.candidate, self.records))


if __name__ == "__main__":
    unittest.main()
