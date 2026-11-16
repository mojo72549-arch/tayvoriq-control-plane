"""Regression tests: a drawn Stuttgart station map must never reach Telegram review."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "tayvoriq_real_media_provenance_gate_v1.py"
spec = importlib.util.spec_from_file_location("real_media_gate", MODULE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class RealMediaGateTests(unittest.TestCase):
    REQUEST_ID = "telegram-3636-trend-1"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.origin = {
            "source": "official_press_photo",
            "asset": "real_schalterhalle_1.jpg",
        }
        self.proof = {
            **self.origin,
            "scene": 1,
            "actual_location_media": True,
            "subject_match_verified": True,
            "rights_status": "permission_granted",
            "rights_verified": True,
            "provenance_url": "https://example.org/schalterhalle-photo",
            "rights_evidence_url": "https://example.org/permissions/tayvoriq",
        }
        for platform in gate.PLATFORMS:
            write(self.root / platform / "render_report.json",
                  {"asset_report": [dict(self.origin)]})
        write(self.root / "real_media_provenance.json", {
            "schema": gate.SCHEMA, "source_request_id": self.REQUEST_ID,
            "platforms": {platform: [dict(self.proof)] for platform in gate.PLATFORMS},
        })
        write(self.root / "content_bundle.json", {"preapproval_ai_audit": {
            "visual_review": {"passed": True, "score": 85, "findings": []},
        }})

    def check(self):
        return gate.validate(self.root, self.REQUEST_ID)

    def test_licensed_real_location_photo_passes(self):
        self.assertTrue(self.check()["passed"])

    def test_schematic_sketch_blocked_even_when_ai_scores_pass(self):
        write(self.root / "content_bundle.json", {"preapproval_ai_audit": {
            "visual_review": {"passed": True, "score": 85,
                "findings": ["Textüberschneidung in der schematischen Wegskizze"]},
        }})
        self.assertIn("REAL_MEDIA_AUDIT_DETECTED_ILLUSTRATION", self.check()["issues"])

    def test_generated_visuals_are_rejected(self):
        for platform in gate.PLATFORMS:
            write(self.root / platform / "render_report.json", {
                "asset_report": [{"source": "generated_verified_explainer",
                                  "asset": "explainer_01.png"}]})
        self.assertFalse(self.check()["passed"])

    def test_missing_or_unlicensed_evidence_blocks(self):
        (self.root / "real_media_provenance.json").unlink()
        self.assertFalse(self.check()["passed"])

    def test_unrelated_generic_stock_never_substitutes_location(self):
        write(self.root / "youtube_shorts" / "render_report.json", {
            "asset_report": [{"source": "generic_stock", "asset": "station.mp4"}]})
        self.assertFalse(self.check()["passed"])

    def test_mismatched_request_binding_blocks(self):
        self.assertIn("REAL_MEDIA_REQUEST_BINDING_INVALID",
                      gate.validate(self.root, "telegram-some-other-trend-1")["issues"])


if __name__ == "__main__":
    unittest.main()
