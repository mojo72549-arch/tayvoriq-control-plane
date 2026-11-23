import ast
import copy
import io
import json
import os
import re
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import mock_open, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import tayvoriq_agent_trend_radar_v8 as radar


class RegionalPolicyTest(unittest.TestCase):
    def candidates(self):
        return [{'title': scope, 'regional_relevance': scope,
                 'trend_scope': 'business_economy', 'source_context': {}}
                for scope in ('local', 'germany', 'europe', 'global')]

    def select(self, candidates):
        with patch.object(radar.retention_v5, 'apply_trend_contract', side_effect=lambda c, strict: copy.deepcopy(c)), \
             patch.object(radar, '_original_diversify', side_effect=lambda c, slot: c):
            return radar.diversify(candidates, 'morning')

    def test_only_local_and_germany_pass_and_two_are_sufficient(self):
        selected = self.select(self.candidates())
        self.assertEqual({c['regional_relevance'] for c in selected}, {'local', 'germany'})
        self.assertTrue(all(c['source_context']['reach_gate']['policy'] == 'REGIONAL_GERMANY_CHANNEL_EVIDENCE_V2' for c in selected))

    def test_abstract_research_and_single_candidate_fail_closed(self):
        candidates = self.candidates()[:2]
        candidates[1]['trend_scope'] = 'science_future'
        with patch.object(radar, '_mark_research_deferred'), self.assertRaisesRegex(SystemExit, 'REGIONAL_RESCAN_REQUIRED'):
            self.select(candidates)

    def test_retention_failure_cannot_be_compensated_by_locality(self):
        with patch.object(radar.retention_v5, 'apply_trend_contract', side_effect=ValueError('bad evidence')), \
             patch.object(radar, '_mark_research_deferred'), \
             self.assertRaisesRegex(SystemExit, 'REGIONAL_RESCAN_REQUIRED'):
            radar.diversify(self.candidates(), 'morning')

    def test_a_thin_hook_reuses_the_supported_question_without_rewriting_facts(self):
        original = {
            "title":"Bahn stellt Fahrplan um", "primary_hook":"Deine Verbindung ändert sich",
            "viewer_question":"Warum ändert sich der Fahrplan für Pendler auf dieser Strecke?",
            "explanation_core":"Die Bahn verändert den Fahrplan wegen Bauarbeiten und stellt für betroffene Reisende auf einzelnen Abschnitten Ersatzbusse bereit.",
            "surprise_or_reframe":"Auch bei kurzen Wegen bleiben Umstiege, Fahrtzeiten und Haltestellen die wichtigsten Unterschiede.",
            "practical_relevance":"Für deine nächste Fahrt hilft die aktuelle Übersicht im Bahnhof.",
            "follow_reason":"Bei TAYVORIQ erfährst du, wie sich der Fahrplan für Pendler konkret ändert.",
            "source_context":{"sources":[{"url":"https://a.example/a"},{"url":"https://b.example/b"}]},
        }
        assert radar.retention_v5.evaluate_content_depth(original)["issues"] == ["hook_too_thin"]
        repaired = radar._repair_thin_hook(original)
        self.assertEqual(repaired["primary_hook"], original["viewer_question"])
        self.assertIs(repaired["source_context"], original["source_context"])
        self.assertEqual(radar.retention_v5.evaluate_content_depth(repaired)["result"], "PASS")
        incomplete = {**original, "explanation_core":""}
        self.assertIs(radar._repair_thin_hook(incomplete), incomplete)

    def test_inherited_gates_still_run(self):
        with patch.object(radar.retention_v5, 'apply_trend_contract', side_effect=lambda c, strict: copy.deepcopy(c)), \
             patch.object(radar, '_original_diversify', side_effect=SystemExit('GROWTH_RESCAN_REQUIRED')), \
             self.assertRaisesRegex(SystemExit, 'GROWTH_RESCAN_REQUIRED'):
            radar.diversify(self.candidates(), 'morning')

    def test_source_bound_rescan_replaces_a_semantically_weak_draft_with_a_valid_one(self):
        from tayvoriq_agent_trend_radar_v5 import _verified_editorial_repair

        answers = {
            'what_happened': 'Die Bahn stellt ab Montag ihren Fahrplan um.',
            'why_happening': 'Wegen maroder Gleise sperrt die Bahn mehrere Abschnitte.',
            'who_is_affected': 'Betroffen sind Pendler und Fahrgäste auf dieser Strecke.',
            'personal_impact': 'Für dich verlängern Umleitungen und zusätzliche Umstiege diese Fahrt.',
            'action_now': 'Prüfe vor der Abfahrt die aktuelle Verbindung online.',
        }
        corrected = {**self.candidates()[0], 'title': 'Bahn stellt Fahrplan um',
                     'growth_v2': {'growth_score': 80},
                     'sources': ['https://a.example/a', 'https://b.example/b'],
                     'source_context': {'fallback_editorial_answers': answers}}
        previous = {**corrected, 'source_context': {'fallback_editorial_answers': {
            **answers, 'personal_impact': 'Für dich sind Pendler und Fahrgäste betroffen.'}}}
        with patch.object(radar.retention_v5, 'apply_trend_contract', return_value={}):
            self.assertTrue(_verified_editorial_repair(previous, corrected, ready=radar._passes_candidate_gates))
            changed_sources = {**corrected, 'sources': ['https://a.example/a', 'https://c.example/c']}
            self.assertFalse(_verified_editorial_repair(previous, changed_sources, ready=radar._passes_candidate_gates))
            below_reserve = {**corrected, 'growth_v2': {'growth_score': 79}}
            self.assertFalse(_verified_editorial_repair(previous, below_reserve, ready=radar._passes_candidate_gates))

    def test_prompts_do_not_reject_local_or_invite_global(self):
        for slot in ('morning', 'evening'):
            prompt = radar.prompt_for(slot, datetime(2026, 9, 27, 10))
            self.assertIn('Germany ONLY', prompt[:3500])
            self.assertIn('two independent', prompt)
            self.assertNotIn('not locality-first', prompt)
            self.assertNotIn('Global AI/Tech/Science/Sports/World stories are fully eligible', prompt)
        provider = (ROOT / 'tools/tayvoriq_agent_trend_provider_v3.py').read_text()
        self.assertNotIn('Purely local/city/state stories are normally ineligible', provider)

    def test_workflow_embedded_python_compiles_and_message_handles_two(self):
        workflow = (ROOT / '.github/workflows/tayvoriq-telegram-trends-now.yml').read_text()
        blocks = []
        for block in re.findall(r"<<'PY'[^\n]*\n(.*?)\n          PY", workflow, re.S):
            block = '\n'.join(line[10:] if line.startswith('          ') else line for line in block.splitlines())
            ast.parse(block)
            blocks.append(block)
        self.assertGreater(len(blocks), 3)
        message = next(block for block in blocks if "labels={'1'" in block)
        data = {'trends': [{'id': str(i), 'title': 'Thema ' + str(i)} for i in (1, 2)]}
        output = io.StringIO()
        with patch('builtins.open', mock_open(read_data=json.dumps(data))), \
             patch.dict(os.environ, {'SELECTION_ID': 'test', 'TARGET_DATE': '2026-09-27', 'SLOT': 'morning', 'TELEGRAM_CHAT_ID': 'test'}), \
             redirect_stdout(output):
            exec(message, {})
        payload = json.loads(output.getvalue())
        self.assertIn('Alle 2 Trends', payload['text'])
        self.assertEqual(len(payload['reply_markup']['inline_keyboard'][0]), 2)


if __name__ == '__main__':
    unittest.main()
