import copy
import hashlib
import json
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_orchestration_contract as contract
from tayvoriq_contabo_handoff import identity
from tayvoriq_contabo_research import receipt_events, worker_failure_code, SOURCE_MINIMUM_NOT_MET
from tayvoriq_scheduled_render import ZONE, pending, scheduled_authority, stage, window
from tayvoriq_source_evidence_v1 import validate_pair


class ScheduledSlotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.requests = root / "requests"
        self.requests.mkdir()
        fixture = Path(__file__).resolve().parents[1] / ".automation/tayvoriq-agent-v2/selections/20261127-morning-agentv2.json"
        self.packet = json.loads(fixture.read_text())
        self.sid = self.packet["selection_id"]
        self.now = datetime(2026, 11, 27, 6, tzinfo=ZONE)
        self.selection, self.audit, self.proof = [root / n for n in ("selection.json", "audit.json", "proof.json")]
        self.selection.write_text(json.dumps(self.packet))
        self.audit.write_text(json.dumps(dict(selection_id=self.sid, slot="morning", provider="ollama_rss",
                                              quality_gates_weakened=False, selected_count=len(self.packet["trends"]))))
        self.proof.write_text(json.dumps(dict(selection=self.sid, slot="morning", topic="", origin="scheduled",
                                              revision="a" * 40, attempt="1", controller="123", worker_run_id=456,
                                              selection_sha256=hashlib.sha256(self.selection.read_bytes()).hexdigest(),
                                              audit_sha256=hashlib.sha256(self.audit.read_bytes()).hexdigest())))

    def reserve(self):
        with redirect_stdout(StringIO()):
            stage(self.selection, self.audit, self.proof, self.requests, self.now)

    def test_restart_reuses_one_render_and_only_a_human_can_release_video(self):
        self.reserve()
        self.reserve()
        files = list(self.requests.glob("*.json"))
        self.assertEqual(len(files), 1)
        row = json.loads(files[0].read_text())
        self.assertTrue(scheduled_authority(row))
        self.assertEqual(pending(self.requests, self.now), row["request_id"])
        self.assertIsNone(row["telegram_message_id"])
        self.assertTrue(row["approval_required_before_youtube_publish"])
        pointer = {k: row[k] for k in ("request_id", "contract_sha256", "source_context_sha256", "approval_key")}
        identity(row, pointer)
        contract.validate(row, require_claimable=True)
        corrupt = copy.deepcopy(row)
        corrupt["scheduled_research"]["worker_run_id"] += 1
        with self.assertRaises(SystemExit):
            contract.validate(corrupt)
        row["status"] = "DISPATCHED"
        files[0].write_text(json.dumps(row))
        self.assertEqual(pending(self.requests, self.now), "")

    def test_manual_preproduction_before_stage_or_before_claim_owns_only_its_slot(self):
        manual = dict(selection_id=self.sid + "-c00000001", source="telegram_trend_approval", status="DISPATCHED",
                      request_id="manual", approval_key="telegram:manual")
        file = self.requests / "manual.json"
        file.write_text(json.dumps(manual))
        self.reserve()
        self.assertEqual(list(self.requests.iterdir()), [file])
        manual["selection_id"] = self.sid.replace("morning", "evening")
        file.write_text(json.dumps(manual))
        self.reserve()
        self.assertTrue(pending(self.requests, self.now))
        file.write_text(json.dumps({**manual, "selection_id": self.sid}))
        self.assertEqual(pending(self.requests, self.now), "")

    def test_wrong_origin_changed_result_or_late_slot_cannot_start(self):
        proof = json.loads(self.proof.read_text())
        for change in ({"origin": "verification"}, {"selection_sha256": "f" * 64}, {"slot": "evening"}):
            self.proof.write_text(json.dumps({**proof, **change}))
            with self.assertRaises((SystemExit, ValueError)):
                self.reserve()
            self.assertFalse(list(self.requests.iterdir()))
        self.proof.write_text(json.dumps(proof))
        self.now = self.now.replace(hour=19)
        with self.assertRaises(ValueError):
            self.reserve()

    def test_scheduled_portfolio_reuses_only_the_matching_pending_video(self):
        from tayvoriq_portfolio_slot import reserved
        root = self.requests.parent
        plan = dict(day="2026-11-27", slot="morning", request_id="portfolio-video", run_id=111,
                    source_context_sha256="a"*64, review_sha="b"*64, telegram_message_id=999)
        state = root / "state/tayvoriq-portfolio-slots.json"
        state.parent.mkdir()
        state.write_text(json.dumps({"slots":{"2026-11-27-morning":plan}}))
        receipt = dict(state="REVIEW_READY", golden_path_run_id=111, quality_gates_weakened=False, telegram_message_id=999)
        (self.requests/"portfolio-video.json").write_text(json.dumps({
            **plan, "golden_path_run_id":111, "production_completion":receipt}))
        decision = root / ".automation/tayvoriq-artifact-decisions/111.json"
        decision.parent.mkdir(parents=True)
        review = {**plan, "state":"PENDING", "review_id":"111", "files_sha256":{"short_youtube.mp4":"b"*64}}
        decision.write_text(json.dumps(review))
        self.assertEqual(reserved(root,self.now)["run_id"],111)
        self.reserve()
        self.assertEqual(len(list(self.requests.glob("slot-*.json"))),0)
        for changed in ({"state":"REJECTED"}, {"telegram_message_id":998}, {"source_context_sha256":"c"*64}):
            decision.write_text(json.dumps({**review, **changed}))
            self.assertIsNone(reserved(root,self.now))

    def test_clock_uses_berlin_in_both_seasons(self):
        for month in (1, 7):
            for hour, minute, slot in ((5, 29, ""), (5, 30, "morning"), (12, 0, ""),
                                       (18, 59, ""), (19, 0, "evening")):
                self.assertEqual(window(datetime(2026, month, 10, hour, minute, tzinfo=ZONE)), slot)

    def test_interleaved_logs_preserve_specific_terminal_cause(self):
        events = list(receipt_events(['{"event":"gdelt_query_failed"}{"event":"gdelt_query_failed"}', 'partial {',
                                      '{"event":"local_research_failed","issue":"SOURCE_MINIMUM_NOT_MET"}']))
        self.assertEqual(len(events), 3)
        self.assertEqual(worker_failure_code(events), SOURCE_MINIMUM_NOT_MET)

    def test_same_application_volume_required_at_both_publishers(self):
        a = {"title":"Firma Berg zählt 50.000 Bewerbungen", "url":"https://a.de/1", "context":"Firma Berg zählt 50.000 Bewerbungen."}
        b = {"title":"Firma Berg zählt 40.000 Bewerbungen", "url":"https://b.de/1", "context":"50.000 Stellen bei Firma Berg."}
        self.assertIn("application_volume_not_independently_confirmed", validate_pair({"title":a["title"]}, [a, b]))
        b["title"] = a["title"]
        self.assertEqual(validate_pair({"title":a["title"]}, [a, b]), [])
