const CONTROL_REPO='mojo72549-arch/tayvoriq-control-plane';
const LEGACY_REPO='mojo72549-arch/shorts-agent-studio';
const RAW_HEALTH='https://raw.githubusercontent.com/mojo72549-arch/tayvoriq-control-plane/main/run-status/ops-health.json';
const API='https://api.github.com';

function ghHeaders(){
  const token=String(process.env.TAYVORIQ_GITHUB_TOKEN||process.env.GITHUB_TOKEN||'').trim();
  const h={Accept:'application/vnd.github+json','User-Agent':'tayvoriq-control-center-live'};
  if(token) h.Authorization=`Bearer ${token}`;
  return {headers:h,authenticated:Boolean(token)};
}

async function jsonFetch(url,headers={}){
  const r=await fetch(url,{headers,cache:'no-store'});
  if(!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function health(){
  return jsonFetch(`${RAW_HEALTH}?v=${Date.now()}`,{Accept:'application/json'});
}

function humanKind(name=''){
  const n=String(name).toLowerCase();
  if(n.includes('golden path')) return {kind:'production',label:'Golden Path'};
  if(n.includes('orchestrator')) return {kind:'recovery',label:'Recovery-Orchestrator'};
  if(n.includes('self-heal')||n.includes('self heal')||n.includes('recovery')) return {kind:'recovery',label:'Self-Heal / Recovery'};
  if(n.includes('quality')) return {kind:'quality',label:'Qualitätsprüfung'};
  if(n.includes('publish')) return {kind:'publish',label:'Publish / Review'};
  if(n.includes('telegram')) return {kind:'system',label:'Telegram-Dienst'};
  if(n.includes('health')) return {kind:'system',label:'Health-Dienst'};
  return {kind:'system',label:'Hintergrunddienst'};
}

function isNoise(name=''){
  const raw=String(name);
  const n=raw.toLowerCase();
  return raw.startsWith('.github/workflows/')||n.includes('artifact cleanup')||n.includes('legacy schedule guard')||n.includes('public preview')||n.includes('project lumen');
}

function activityFromRuns(runs=[]){
  return runs.filter(r=>!isNoise(r.name||r.display_title)).slice(0,14).map(r=>{
    const meta=humanKind(r.name||r.display_title);
    const status=String(r.status||'unknown');
    const conclusion=String(r.conclusion||'');
    let state='wartet';
    if(status==='in_progress') state='läuft';
    else if(status==='queued'||status==='requested'||status==='waiting') state='startet';
    else if(conclusion==='success') state='erledigt';
    else if(conclusion==='failure') state='fehlgeschlagen';
    else if(conclusion==='skipped') state='übersprungen';
    else if(conclusion==='cancelled') state='abgebrochen';
    else if(status==='completed') state='beendet';
    return {
      id:r.id,
      name:r.name||r.display_title||'GitHub Action',
      label:meta.label,
      kind:meta.kind,
      state,
      status,
      conclusion:conclusion||null,
      updated_at:r.updated_at||r.created_at||null,
      url:r.html_url||null
    };
  });
}

async function legacyState(headers,authenticated){
  if(!authenticated) return {available:false,reason:'server_token_not_configured'};
  try{
    const p=await jsonFetch(`${API}/repos/${LEGACY_REPO}/contents/.automation/tayvoriq-progress/latest.json?ref=main`,headers);
    const text=Buffer.from(String(p.content||'').replace(/\n/g,''),'base64').toString('utf8');
    return {available:true,data:JSON.parse(text)};
  }catch(error){
    return {available:false,reason:String(error?.message||error)};
  }
}

export default async function handler(req,res){
  const checkedAt=new Date().toISOString();
  const gh=ghHeaders();
  const errors=[];
  let snapshot=null;
  let runs=[];
  let legacy={available:false,reason:'not_checked'};

  try{snapshot=await health();}catch(error){errors.push(`health:${error?.message||error}`)}
  try{
    const p=await jsonFetch(`${API}/repos/${CONTROL_REPO}/actions/runs?per_page=30`,gh.headers);
    runs=Array.isArray(p.workflow_runs)?p.workflow_runs:[];
  }catch(error){errors.push(`actions:${error?.message||error}`)}
  legacy=await legacyState(gh.headers,gh.authenticated);

  const activity=activityFromRuns(runs);
  const active=activity.filter(x=>['in_progress','queued','requested','waiting','pending'].includes(x.status));
  const snapshotAt=snapshot?.generated_at||null;
  const snapshotAge=snapshotAt?Math.max(0,Math.round((Date.now()-Date.parse(snapshotAt))/1000)):null;
  const latestAt=activity[0]?.updated_at||snapshot?.run?.updated_at||snapshotAt;
  const latestAge=latestAt?Math.max(0,Math.round((Date.now()-Date.parse(latestAt))/1000)):null;

  const payload={
    ...(snapshot||{schema:'tayvoriq-live-fallback-v1',overall:'unknown'}),
    live:{
      checked_at:checkedAt,
      authenticated:gh.authenticated,
      snapshot_at:snapshotAt,
      snapshot_age_seconds:snapshotAge,
      latest_activity_at:latestAt||null,
      latest_activity_age_seconds:latestAge,
      active_count:active.length,
      active_activity:active,
      source:errors.length?'partial':'github-actions+ops-health',
      errors
    },
    activity,
    legacy
  };

  res.setHeader('Content-Type','application/json; charset=utf-8');
  res.setHeader('Access-Control-Allow-Origin','*');
  res.setHeader('Cache-Control',gh.authenticated?'public, s-maxage=8, stale-while-revalidate=20':'public, s-maxage=60, stale-while-revalidate=120');
  res.status(snapshot||activity.length?200:502).json(payload);
}
