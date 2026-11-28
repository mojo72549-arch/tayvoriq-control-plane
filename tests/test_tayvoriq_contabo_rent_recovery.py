import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import tayvoriq_contabo_visual_recovery as recovery


def test_unstarted_rent_scene_can_retry_once_only_after_its_own_verified_fix():
    root = Path('/unread-test-project')
    rid, run = 'telegram-3888-trend-2', 46139626379
    ptr = {'state':'ACTIVE', 'execution_backend':'contabo_private_runner', 'request_id':rid, 'golden_path_run_id':run}
    req = {'status':'DISPATCHED', 'topic':'Stuttgarts Vergleichsmiete steigt in zwei Jahren um 6,1 Prozent',
           'codefix_recovery':{'replay_implementation_sha':'a'*40}}
    green = {'schema':'tayvoriq-production-green-v1','implementation_sha':'b'*40,'full_preflight_passed':True,
             'quality_gates_weakened':False,'software_workplace_search_verified':True}
    docs = {root/recovery.POINTER:ptr, root/'requests'/f'{rid}.json':req,
            root/'run-status/contabo'/f'{run}.json':{'failure_detail':{'code':'REAL_VIDEO_SCENE_REQUIRED','scene':6}},
            root/'.github/state/tayvoriq-production-green.json':green}
    controller={'id':run,'head_branch':'main','path':'.github/workflows/tayvoriq-golden-path.yml',
                'status':'completed','conclusion':'failure'}
    with (patch.object(recovery, 'read', side_effect=docs.__getitem__), patch.object(recovery,'identity'),
         patch.object(recovery, 'contabo_publishability_failed',return_value=True),
         patch.object(recovery,'github_json',return_value=controller)):
        assert recovery.plan(root,'test/repo','') is None
        green['rental_footage_search_verified'] = True
        assert recovery.plan(root,'test/repo','')['scene'] == 6
        req['codefix_recovery']['replay_implementation_sha'] = green['implementation_sha']
        assert recovery.plan(root,'test/repo','') is None
        req['codefix_recovery']['replay_implementation_sha'] = 'a'*40
        req['visual_recovery'] = {'previous_run_id':run}
        assert recovery.plan(root,'test/repo','') is None
