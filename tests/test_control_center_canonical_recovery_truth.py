"""Control Center must show the active canonical replay, never yesterday's failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _node(source):
    result = subprocess.run(["node", "-e", source], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_live_recovery_does_not_inherit_previous_failed_run_incident():
    for path in ("api/live.js", "dashboard/api/live.js"):
        script = r"""
const fs=require('fs');
const src=fs.readFileSync(process.argv[1],'utf8');
const a=src.indexOf('function recoveryTruth('), b=src.indexOf('function pilotFailureClass',a);
if(a<0||b<0)throw Error('recovery functions missing');
const logic=src.slice(a,b);
const recovered=new Function('ACTIVE_STATUSES','userActionRequired',logic+'\nreturn {recoveryTruth,canonicalIncident}')(new Set(['in_progress','queued','requested','waiting','pending']),s=>/EXTERNAL|AUTH|SECRET/.test(s));
const run={id:43754016472,status:'in_progress',conclusion:null};
const previous={run:{id:43732348851,conclusion:'failure'},incident:{failure_state:'LOCAL_VISUAL_RECOVERY_EXHAUSTED'}};
const request={codefix_recovery:{status:'REPLAY_DISPATCHED',replay_run_id:43754016472,last_failure_state:'LOCAL_VISUAL_RECOVERY_EXHAUSTED',failure_state:''}};
const recovery=recovered.recoveryTruth(request,run,{...previous,recovery:{status:'REPLAY_DISPATCHED'}});
if(recovery.status!=='LOCAL_VISUAL_RETRY_RUNNING'||recovery.failure_state!==null)throw Error('stale failure carried to running replay');
if(recovered.canonicalIncident(previous,run,null,recovery)!==null)throw Error('stale incident survived running replay');
const bad={id:43754016472,status:'completed',conclusion:'failure'};
const current={...previous,run:{id:43754016472,conclusion:'failure'}};
const inc=recovered.canonicalIncident(current,bad,{step_name:'Render failed',step_number:33},{status:'RECOVERY_CLASSIFICATION_PENDING',failure_state:'CURRENT_RENDER_FAILURE'});
if(inc?.failure_state!=='CURRENT_RENDER_FAILURE'||inc?.failed_step_number!==33)throw Error('real current failure hidden');
console.log(JSON.stringify({ok:true}));
"""
        assert _node(script.replace("process.argv[1]", json.dumps(path)))["ok"]


def test_live_ui_does_not_call_running_canonical_replay_a_continuity_gap():
    src = Path("dashboard/live.html").read_text(encoding="utf-8")
    assert "function continuityGap" in src
    script = r"""
const fs=require('fs');
const source=fs.readFileSync('dashboard/live.html','utf8');
const a=source.indexOf('function continuityGap('),b=source.indexOf('function render(',a);
if(a<0||b<0)throw Error('continuityGap missing');
const continuityGap=new Function('ACTIVE',source.slice(a,b)+'\nreturn continuityGap')(new Set(['in_progress','queued','requested','waiting','pending']));
const running={run:{status:'in_progress'},live:{canonical_run_id:43754016472,canonical_active:true,active_count:0},recovery:{status:'REPLAY_DISPATCHED'}};
if(continuityGap(running))throw Error('canonical RUNNING mistaken for continuity gap');
const broken={run:{status:'completed'},live:{canonical_run_id:43754016472,canonical_active:false,active_count:0},recovery:{status:'REPLAY_DISPATCHED'}};
if(!continuityGap(broken))throw Error('real dispatch gap invisible');
console.log(JSON.stringify({ok:true}));
"""
    assert _node(script)["ok"]


def test_health_postprocess_removes_previous_incident_only_for_current_running_replay(tmp_path):
    root = Path("scripts/tayvoriq_ops_health_postprocess.py")
    path = tmp_path / "state.json"
    def run_case(status, conclusion, replay_run_id):
        state = {
            "run": {"id":43754016472, "status":status, "conclusion":conclusion},
            "recovery": {"source_status":"REPLAY_DISPATCHED",
                         "replay_run_id":replay_run_id,
                         "failure_state":"LOCAL_VISUAL_RECOVERY_EXHAUSTED"},
            "incident":{"failure_state":"LOCAL_VISUAL_RECOVERY_EXHAUSTED"},
            "healthchecks":[{"name":"Self-Heal","status":"red"}],
            "overall":"yellow",
            "user_action_required":True,
            "intervention_count":1,
            "events":[{"title":"Historischer Fehler","detail":"Alter Run"}],
        }
        path.write_text(json.dumps(state))
        env={**os.environ,"TAYVORIQ_OPS_STATE_PATH":str(path)}
        result=subprocess.run([sys.executable,str(root)],env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        return json.loads(path.read_text())
    active=run_case("in_progress",None,43754016472)
    assert active["recovery"]["status"]=="REPLAY_RUNNING"
    assert active["recovery"]["failure_state"] is None
    assert active["incident"] is None
    assert not active["user_action_required"]
    assert active["intervention_count"]==0
    assert active["events"][0]["title"]=="Historischer Fehler"
    failed=run_case("completed","failure",43754016472)
    assert failed["recovery"]["status"]=="RECOVERY_CLASSIFICATION_PENDING"
    assert failed["incident"]["failure_state"]=="LOCAL_VISUAL_RECOVERY_EXHAUSTED"
    unrelated=run_case("in_progress",None,9)
    assert unrelated["incident"] is not None


def test_runtime_snapshot_build_checks_active_canonical_before_old_failure():
    code=Path("scripts/tayvoriq_ops_health.py").read_text(encoding="utf8")
    assert "canonical_running = (" in code
    assert "if canonical_running:" in code
    assert "failure_state = None" in code
    assert "user_action_required = False" in code
    assert code.index("if canonical_running:") < code.index("incident = None")
