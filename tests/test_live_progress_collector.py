import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('collector',Path(__file__).parents[1]/'tools/tayvoriq_live_progress_collector.py')
collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
ID={'request_id':'r1','source_context_sha256':'a'*64,'run_id':123,'run_attempt':2}
def event(**kwargs): return {**ID,'phase':'voice','status':'started','at':'2026-11-26T08:00:00Z','call_id':'one',**kwargs}
class CollectorTests(unittest.TestCase):
 def test_bindings_and_secret_fields_are_filtered(self):
  state=collector.Observation(ID);state.accept(event(token='private',text='private'))
  self.assertNotIn('private',str(state.payload()))
  state.accept(event(run_attempt=1,call_id='other'))
  self.assertEqual(len(state.events),1)
 def test_nested_calls_restore_parent_and_keep_leaf_failure(self):
  state=collector.Observation(ID);state.accept(event(phase='render',call_id='parent'))
  state.accept(event(call_id='child',scene=2,total=6));self.assertEqual(state.payload()['current']['phase'],'voice')
  state.accept(event(call_id='child',status='failed'));state.accept(event(phase='render',call_id='parent',status='failed'))
  self.assertEqual(state.payload()['current']['phase'],'voice')
 def test_completion_requires_both_platforms(self):
  state=collector.Observation(ID);state.accept(event(status='completed',platform='youtube_shorts'))
  self.assertEqual(state.payload()['completed_phases'],[])
  state.accept(event(status='completed',platform='tiktok',call_id='two'))
  self.assertEqual(state.payload()['completed_phases'],['voice'])
 def test_checkpoint_round_and_failed_gate_are_retained(self):
  state=collector.Observation(ID)
  state.checkpoint('{"checkpoint_stage":"VISUAL_REPAIR_TOPIC_AWARE_V3_R2","status":"started","timeout_seconds":900}')
  self.assertEqual(state.payload()['current']['round'],2)
  self.assertEqual(state.payload()['current']['target'],'visuals')
  state.checkpoint('{"checkpoint_stage":"QUALITY_AUDIT_1","status":"completed","returncode":20}')
  self.assertEqual(state.payload()['current']['status'],'failed')
  self.assertEqual(state.payload()['current']['phase'],'quality')
 def test_log_json_primitives_do_not_terminate_the_observer(self):
  state=collector.Observation(ID)
  for line in ['[]','0','"provider log"','null','not json']: state.checkpoint(line)
  self.assertEqual(state.events,[])
 def test_audit_findings_use_only_fresh_failed_scene_evidence(self):
  import json,tempfile,os
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);old=root/'old';fresh=root/'fresh';passed=root/'passed'
   for p in (old,fresh,passed):p.mkdir()
   (old/'preapproval_ai_audit.json').write_text(json.dumps({'passed':False,'blockers':['historical']}))
   os.utime(old/'preapproval_ai_audit.json',(1,1))
   (fresh/'preapproval_ai_audit.json').write_text(json.dumps({'passed':False,'api_key':'private',
    'visual_review':{'scene_checks':[{'platform':'youtube_shorts','scene':3,'relevant':False},{'platform':'tiktok','scene':2,'distinct':False}]}}))
   (passed/'preapproval_ai_audit.json').write_text(json.dumps({'passed':True,'blockers':['obsolete']}))
   findings=collector.audit_findings(root,2)
   self.assertEqual(findings,['YouTube · Szene 3: Motiv passt nicht zur Aussage','TikTok · Szene 2: Motiv wiederholt sich'])
if __name__=='__main__': unittest.main()
