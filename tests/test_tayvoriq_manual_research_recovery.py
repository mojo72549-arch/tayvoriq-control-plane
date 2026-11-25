"""Explicit research uses durable cooldowns and retries only its own bounded request."""
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import tayvoriq_research_observer as observer
from tayvoriq_source_evidence_v1 import _events, validate_pair

SID = '20261125-evening-agentv2-c28654554'


class ManualResearchRecoveryTests(unittest.TestCase):
    def test_explicit_context_shares_provider_health_and_isolates_other_requests(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as temporary:
            root, temporary = Path(root), Path(temporary)
            health = root / '.automation/tayvoriq-agent-v2/provider-health.json'
            health.parent.mkdir(parents=True)
            health.write_text(json.dumps({'schema':'tayvoriq-provider-health-v1','providers':{'gemini':{'state':'COOLDOWN'}}}))
            with patch.dict(os.environ, {'TAYVORIQ_RESEARCH_SLOT':'morning', 'TAYVORIQ_RESEARCH_RUN_KEY':'42.1'}):
                state = observer.context(SID, 'evening', root, temporary, now=1000)
            self.assertEqual(state['env']['TAYVORIQ_RESEARCH_SELECTION_ID'], SID)
            self.assertEqual(state['env']['TAYVORIQ_RESEARCH_SLOT'], 'evening')
            self.assertNotIn('TAYVORIQ_RESEARCH_RUN_KEY', state['env'])
            self.assertIn('gemini', observer.load_json(state['files']['health'])['providers'])
            self.assertIn(SID, state['paths']['drafts'])
            self.assertIn(SID, state['paths']['retry'])
            self.assertNotEqual(state['paths']['retry'], '.automation/tayvoriq-agent-v2/research-retry.json')
            self.assertEqual(state['deadline'], 1600)

    def test_retry_preserves_command_and_identity_and_waits_for_the_actual_deadline(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as temporary:
            state = observer.context(SID, 'evening', Path(root), Path(temporary), now=1000)
            observation = observer.Observation(SID, 'evening', 42, 2)
            now, calls, statuses = [1000.0], [], []
            def run(command, env, deadline, observed, save):
                calls.append((command, env['TAYVORIQ_RESEARCH_SELECTION_ID']))
                if len(calls) == 1:
                    state['files']['retry'].write_text(json.dumps({'state':'WAITING','retry_at_epoch':1010,'attempts':1}))
                    return 1
                return 0
            def pause(seconds):
                self.assertLessEqual(seconds, 5)
                now[0] += seconds
            result = observer.execute(['original-research-command'], state, observation,
                lambda *a: statuses.append(observation.data['state']), lambda: None,
                clock=lambda:now[0], pause=pause, run=run)
            self.assertEqual(result, 0)
            self.assertEqual(calls, [(['original-research-command'], SID)] * 2)
            self.assertIn('WAITING', statuses)
            self.assertEqual(now[0], 1010)
            self.assertEqual(observation.data['state'], 'GENERATED')

    def test_no_blind_retry_for_a_deterministic_failure_or_a_cooldown_outside_the_window(self):
        for retry in [{}, {'state':'WAITING','retry_at_epoch':1800,'attempts':1}]:
            with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as temporary:
                state = observer.context(SID, 'evening', Path(root), Path(temporary), now=1000)
                calls = []
                def run(*args):
                    calls.append(1)
                    state['files']['retry'].write_text(json.dumps(retry))
                    return 1
                result = observer.execute(['research'], state, observer.Observation(SID,'evening',42,1),
                    lambda *a:None,lambda:None,clock=lambda:1000,pause=lambda s:self.fail('must not wait'),run=run)
                self.assertEqual(result, 1)
                self.assertEqual(len(calls), 1)

    def test_a_terminal_request_budget_is_never_reopened_automatically(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as temporary:
            state = observer.context(SID, 'evening', Path(root), Path(temporary), now=1000)
            state['files']['retry'].write_text(json.dumps({'state':'EXHAUSTED','attempts':3}))
            code = observer.execute(['research'],state,observer.Observation(SID,'evening',42,1),lambda *a:None,lambda:None,
                clock=lambda:1000,run=lambda *a:self.fail('exhausted request must not call a provider'))
            self.assertEqual(code,124)

    def test_health_merge_does_not_erase_a_newer_parallel_cooldown(self):
        old={'state':'COOLDOWN','observed_at_epoch':10}
        newer={'state':'COOLDOWN','observed_at_epoch':20}
        original={'providers':{'gemini':old}}
        updated={'providers':{}}
        self.assertEqual(observer.merge_health(original,updated,{'providers':{'gemini':newer}})['providers']['gemini'],newer)
        self.assertNotIn('gemini',observer.merge_health(original,updated,original)['providers'])

    def test_real_child_exit_code_and_structured_progress_are_preserved_without_external_calls(self):
        o=observer.Observation(SID,'evening',42,1)
        command=[sys.executable,'-c','import json; print(json.dumps({"event":"source_records_loaded","total_records":17})); raise SystemExit(7)']
        code=observer.run_child(command,dict(os.environ),time.time()+10,o,lambda *a:None)
        self.assertEqual(code,7)
        self.assertEqual(o.data['sources_seen'],17)


class SourceEventDiscoveryTests(unittest.TestCase):
    def pair(self,title,other=None,context=''):
        return [{'title':title,'context':context or title+' Ein Bericht der Redaktion.','url':'https://a.example/story'},
                {'title':other or title,'context':context or (other or title)+' Ein zweiter eigenständiger Bericht.','url':'https://b.example/story'}]

    def test_work_money_and_transport_event_families_are_recognized_without_removing_source_checks(self):
        for title,event in [('USA planen neue Zölle gegen EU','trade_tariffs'),
                            ('Fahrkarten bald bei der Bahn buchbar','ticket_distribution'),
                            ('Deutsche Wirtschaft wächst im Quartal','economic_growth'),
                            ('Deutsche Wirtschaft schrumpft im Quartal','economic_contraction'),
                            ('Kerzen werden teurer','price_rise'),
                            ('Tarifrunde bei einem Autobauer beginnt','wage_negotiation')]:
            self.assertIn(event,_events(title))
            self.assertEqual(validate_pair({'title':title},self.pair(title)),[])

    def test_new_families_still_reject_plan_outcome_mismatches_and_opposite_economic_directions(self):
        planned='USA planen neue Zölle gegen EU'
        self.assertTrue(validate_pair({'title':planned},self.pair(planned,'USA verhängen neue Zölle gegen EU')))
        self.assertTrue(validate_pair({'title':'Kerzen werden teurer'},self.pair('Kerzen werden teurer','Kerzen dürften teurer werden')))
        self.assertTrue(validate_pair({'title':'Bahn verkauft Tickets jetzt'},self.pair('Bahn verkauft Tickets jetzt','Bahn verkauft Tickets künftig')))
        growth='Deutsche Wirtschaft wächst im Quartal'
        self.assertIn('shared_headline_event_anchor_required',validate_pair({'title':growth},self.pair(growth,'Deutsche Wirtschaft schrumpft im Quartal')))

    def test_new_families_still_reject_changed_numbers_missing_claims_same_publishers_and_wire_mirrors(self):
        title='USA planen 15 Prozent neue Zölle gegen EU'
        self.assertTrue(validate_pair({'title':title},self.pair(title,title.replace('15','10'))))
        self.assertTrue(validate_pair({'title':'USA planen neue Zölle gegen EU'},self.pair('USA planen neue Zölle gegen EU','USA planen neue Zölle gegen UK')))
        mirror=self.pair('Fahrkarten bald bei der Bahn buchbar')
        for row in mirror:row['origin']='dpa'
        self.assertIn('same_declared_reporting_origin',validate_pair({'title':mirror[0]['title']},mirror))
        same=self.pair('Kerzen werden teurer');same[1]['url']='https://a.example/other'
        self.assertIn('requires_two_independent_publishers',validate_pair({'title':same[0]['title']},same))

class ExplicitRetryAccountingTests(unittest.TestCase):
    def test_duplicate_gate_notices_count_one_process_and_the_next_local_process_counts_once(self):
        import tayvoriq_research_retry_v1 as retry
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                'TAYVORIQ_RESEARCH_SELECTION_ID':SID,'TAYVORIQ_RESEARCH_RUN_KEY':'42.2',
                'TAYVORIQ_RESEARCH_LOCAL_ATTEMPT':'1'}):
            path=Path(tmp)/'retry.json'
            for _ in range(3):
                state=retry.defer('evening',1100,path=path,now=1000)
            self.assertEqual(state['attempts'],1)
            self.assertEqual(state['state'],'WAITING')
            with patch.dict(os.environ,{'TAYVORIQ_RESEARCH_LOCAL_ATTEMPT':'2'}):
                state=retry.defer('evening',1200,path=path,now=1100)
                state=retry.defer('evening',1200,path=path,now=1100)
            self.assertEqual(state['attempts'],2)
            self.assertEqual(state['last_local_attempt'],2)

    def test_platform_identity_is_real_and_the_explicit_context_does_not_replace_it(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'GITHUB_RUN_ID':'42','GITHUB_RUN_ATTEMPT':'3'}):
            state=observer.context(SID,'evening',Path(root),Path(tmp),now=1000)
            self.assertEqual(state['env']['TAYVORIQ_RESEARCH_RUN_KEY'],'42.3')

    def test_measured_editorial_failure_is_distinct_from_a_provider_limit(self):
        o=observer.Observation(SID,'evening',42,3)
        o.event({'event':'provider_attempt_failed','provider':'gemini','error':'HTTP 429'})
        o.event({'event':'candidate_editorial_rejection','reason':'regional_scorecard','details':['tiktok:regional_score_below_75']})
        self.assertIn({'code':'TIKTOK_FIT','provider':None},o.data['issues'])
        o.event({'event':'candidate_editorial_rejection','reason':'claim_coherence','details':['why_happening_not_supported_by_source_claims']})
        self.assertIn({'code':'CLAIM_SUPPORT','provider':None},o.data['issues'])
