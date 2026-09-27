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

    def test_inherited_gates_still_run(self):
        with patch.object(radar.retention_v5, 'apply_trend_contract', side_effect=lambda c, strict: copy.deepcopy(c)), \
             patch.object(radar, '_original_diversify', side_effect=SystemExit('GROWTH_RESCAN_REQUIRED')), \
             self.assertRaisesRegex(SystemExit, 'GROWTH_RESCAN_REQUIRED'):
            radar.diversify(self.candidates(), 'morning')

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
