import baseHandler from './live.js';

const STUDIO_REPO='mojo72549-arch/shorts-agent-studio';
const CONTROL_REPO='mojo72549-arch/tayvoriq-control-plane';
const SOCIAL_TRIGGER='.tayvoriq/commands/social-direct.trigger';
const ACTIVE=new Set(['in_progress','queued','requested','waiting','pending']);

function ghHeaders(){
  const token=String(process.env.TAYVORIQ_GITHUB_TOKEN||process.env.PRIVATE_REPO_TOKEN||process.env.GITHUB_TOKEN||'').trim();
  const headers={Accept:'application/vnd.github+json','User-Agent':'tayvoriq-control-center-live-v3','X-GitHub-Api-Version':'2022-11-28'};
  if(token) headers.Authorization=`Bearer ${token}`;
  return headers;
}

function contentPath(path){return String(path).split('/').map(encodeURIComponent).join('/')}

async function repoText(repo,path,ref='main'){
  const r=await fetch(`https://api.github.com/repos/${repo}/contents/${contentPath(path)}?ref=${encodeURIComponent(ref)}`,{headers:ghHeaders(),cache:'no-store'});
  if(!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  const p=await r.json();
  return Buffer.from(String(p.content||'').replace(/\n/g,''),'base64').toString('utf8');
}

async function latestSocialRequest(){
  try{
    const requestId=(await repoText(STUDIO_REPO,SOCIAL_TRIGGER)).trim();
    if(!/^[A-Za-z0-9_-]{4,80}$/.test(requestId)) return null;
    const raw=await repoText(CONTROL_REPO,`requests/${requestId}.json`);
    const data=JSON.parse(raw);
    if(data?.lane!=='social_media') return null;
    return data;
  }catch(_){
    return null;
  }
}

function isCanonicalProduction(a){
  const value=`${a?.workflow||''} ${a?.name||''} ${a?.label||''}`.toLowerCase();
  return a?.repo===STUDIO_REPO && (value.includes('canonical request')||value.includes('production — canonical'));
}

function isSocialBridge(a){
  const value=`${a?.workflow||''} ${a?.name||''} ${a?.label||''}`.toLowerCase();
  return a?.repo===STUDIO_REPO && value.includes('social') && value.includes('direct editorial bridge');
}

function socialRun(activity=[]){
  const all=(Array.isArray(activity)?activity:[]).filter(isCanonicalProduction);
  return all.find(a=>ACTIVE.has(String(a.status)))||all[0]||null;
}

const STAGE_DEFS=[
  {label:'Request gebunden',min:4,max:4,done:4,detail:'Kanonischer Social-Auftrag und Quellenkontext sind verifiziert.'},
  {label:'Runtime vorbereitet',min:5,max:9,done:9,detail:'Python, CPU-Budget, Speicher und Abhängigkeiten sind vorbereitet.'},
  {label:'Produktion / Master',min:10,max:10,done:10,detail:'Skript, Voice, Visuals und Render werden als gebundener Auftrag produziert.'},
  {label:'Publishable Gate',min:11,max:11,done:11,detail:'Der erzeugte Master wird auf Veröffentlichungsfähigkeit geprüft.'},
  {label:'Review-Artefakt',min:12,max:12,done:12,detail:'Der geprüfte Master wird als Review-Artefakt gesichert.'},
  {label:'Telegram Review',min:13,max:13,done:13,detail:'Das Review-Video wird mit Freigabe/Ablehnen an Telegram geliefert.'}
];

function stageStatus(def,run){
  const n=Number(run?.step_number||0);
  const status=String(run?.status||'');
  const conclusion=String(run?.conclusion||'');
  if(conclusion==='success') return 'success';
  if(['failure','timed_out','cancelled','canceled','action_required'].includes(conclusion)){
    if(n>=def.min&&n<=def.max) return 'error';
    if(n>def.max) return 'success';
    return 'pending';
  }
  if(ACTIVE.has(status)){
    if(n>def.max) return 'success';
    if(n>=def.min&&n<=def.max) return 'running';
    return 'pending';
  }
  return n>def.max?'success':'pending';
}

function buildStages(run){
  return STAGE_DEFS.map((def,index)=>({
    label:def.label,
    status:stageStatus(def,run),
    step_number:index===0?4:def.done,
    step_name:def.detail
  }));
}

function progress(run,stages){
  if(run?.conclusion==='success') return 100;
  const n=Number(run?.step_number||0);
  if(n>=13) return 97;
  if(n===12) return 90;
  if(n===11) return 80;
  if(n===10) return 68;
  if(n>=8) return 45;
  if(n>=5) return 28;
  if(n>=4) return 14;
  const done=stages.filter(s=>s.status==='success').length;
  return Math.round((done/Math.max(1,stages.length))*100);
}

function stepNarration(step=''){
  const s=String(step).toLowerCase();
  if(s.includes('resolve and verify canonical request')) return 'Auftrag und Quellen werden fest gebunden';
  if(s.includes('extend bounded cpu render budget')) return 'CPU-Renderbudget wird für den langen Masterlauf abgesichert';
  if(s.includes('reclaim runner disk')) return 'Runner-Speicher wird für den Medienrender freigeräumt';
  if(s.includes('install production dependencies')) return 'Produktionsmodule und CPU-Audio/Video-Abhängigkeiten werden geladen';
  if(s.includes('notify accepted production')) return 'Der gebundene Auftrag wurde akzeptiert und die Produktion startet';
  if(s.includes('produce approved request')) return 'Skript, Stimme, Visuals und Master werden gerade produziert';
  if(s.includes('assert publishable output')) return 'Der fertige Master wird auf Veröffentlichungsfähigkeit geprüft';
  if(s.includes('upload request-bound review artifact')) return 'Der geprüfte Master wird für die Review-Stufe gesichert';
  if(s.includes('deliver review video to telegram')) return 'Das fertige Review-Video wird an Telegram ausgeliefert';
  return step?`Aktueller GitHub-Schritt: ${step}`:'Der Social-Produktionslauf arbeitet weiter';
}

function nextStage(stages=[]){
  const idx=stages.findIndex(s=>s.status==='running'||s.status==='error');
  if(idx>=0&&idx+1<stages.length) return stages[idx+1].label;
  const pending=stages.find(s=>s.status==='pending');
  return pending?.label||'Review / Freigabe';
}

function socialOperatorFeed(request,run,stages){
  if(!run) return [{severity:'warning',title:'Social-Auftrag ist gebunden',detail:'Der Produktions-Executor ist noch nicht als aktiver GitHub-Run sichtbar. Der Auftrag bleibt unverändert gebunden.',at:request?.approved_at||null}];
  const failed=['failure','timed_out','cancelled','canceled','action_required'].includes(String(run.conclusion||''));
  const active=ACTIVE.has(String(run.status));
  const items=[];
  if(failed){
    items.push({severity:'error',title:`Technischer Stopp · Schritt ${run.step_number||'–'}`,detail:`${stepNarration(run.step)}. Der Auftrag bleibt gebunden; es wird kein anderes Thema gestartet.`,at:run.updated_at||null});
  }else if(active){
    items.push({severity:'working',title:`Social-Produktion läuft · Schritt ${run.step_number||'–'}`,detail:`${stepNarration(run.step)}. Danach: ${nextStage(stages)}. Run ${run.id}.`,at:run.updated_at||null});
  }else if(run.conclusion==='success'){
    items.push({severity:'success',title:'Social-Master ist durch den Produktionslauf',detail:`Run ${run.id} ist erfolgreich abgeschlossen. Der Review-/Freigabestatus wird jetzt angezeigt.`,at:run.updated_at||null});
  }else{
    items.push({severity:'info',title:'Social-Produktion wartet',detail:`Run ${run.id} · ${run.status||'Status unbekannt'}.`,at:run.updated_at||null});
  }
  [...stages].reverse().forEach(s=>{
    if(s.status==='success') items.push({severity:'success',title:`✓ ${s.label}`,detail:s.step_name,at:run.updated_at||null});
  });
  items.push({severity:'info',title:'Thema fest gebunden',detail:request?.topic||'Social-Media-Auftrag',at:request?.approved_at||null});
  return items.slice(0,10);
}

function enhance(base,request){
  if(!base||!request) return base;
  const activity=Array.isArray(base.activity)?base.activity:[];
  const run=socialRun(activity);
  const bridge=activity.find(isSocialBridge)||null;
  if(!run&&!bridge) return base;

  const stages=buildStages(run||bridge);
  const chosen=run||bridge;
  const failed=['failure','timed_out','cancelled','canceled','action_required'].includes(String(chosen?.conclusion||''));
  const active=ACTIVE.has(String(chosen?.status));
  const runProgress=progress(chosen,stages);

  base.request={
    ...(base.request||{}),
    request_id:request.request_id,
    topic:request.topic,
    state:String(request.status||'APPROVED').toUpperCase(),
    trend_id:request.trend_id||null,
    lane:'social_media',
    updated_at:request.approved_at||base.generated_at||null
  };

  base.run={
    ...(base.run||{}),
    id:chosen.id,
    name:chosen.workflow||'TAYVORIQ Social Production',
    status:chosen.status||'unknown',
    conclusion:chosen.conclusion||null,
    attempt:chosen.attempt||1,
    html_url:chosen.url||null,
    created_at:chosen.started_at||null,
    updated_at:chosen.updated_at||null,
    current_step:active?chosen.step||chosen.job||null:null,
    failed_step:failed?chosen.step||chosen.job||null:null,
    failed_step_number:failed?chosen.step_number??null:null,
    last_successful_step:stages.filter(s=>s.status==='success').at(-1)?.label||null,
    progress:runProgress,
    stages
  };

  base.recovery={
    status:failed?'TECHNICAL_RECOVERY_REQUIRED':active?'PRODUCTION_RUNNING':chosen.conclusion==='success'?'REVIEW_READY':'BOUND',
    recovery_generation:0,
    owner:'Social Golden Path'
  };
  base.incident=failed?{
    failure_state:String(chosen.conclusion||'WORKFLOW_FAILURE').toUpperCase(),
    failed_step:chosen.step||chosen.job||null,
    failed_step_number:chosen.step_number??null,
    self_heal_status:'TECHNICAL_RECOVERY_REQUIRED',
    user_action_required:false
  }:null;
  base.user_action_required=false;
  base.overall=failed?'red':active?'yellow':chosen.conclusion==='success'?'green':base.overall;
  base.operator_feed=socialOperatorFeed(request,chosen,stages);

  const socialHealth=[
    {name:'Social Pipeline',status:failed?'red':active?'yellow':chosen.conclusion==='success'?'green':'unknown',detail:`Run ${chosen.id} · ${active?'läuft':chosen.conclusion||chosen.status||'wartet'} · Schritt ${chosen.step_number??'–'}`},
    {name:'Publishability',status:stages.find(s=>s.label==='Publishable Gate')?.status==='success'?'green':stages.find(s=>s.label==='Publishable Gate')?.status==='error'?'red':stages.find(s=>s.label==='Publishable Gate')?.status==='running'?'yellow':'unknown',detail:stages.find(s=>s.label==='Publishable Gate')?.status==='success'?'Master publishable':'Noch nicht abgeschlossen'},
    {name:'Telegram Review',status:stages.find(s=>s.label==='Telegram Review')?.status==='success'?'green':stages.find(s=>s.label==='Telegram Review')?.status==='running'?'yellow':'unknown',detail:stages.find(s=>s.label==='Telegram Review')?.status==='success'?'Review ausgeliefert':'Wartet auf fertigen Master'}
  ];
  base.healthchecks=[...socialHealth,...(Array.isArray(base.healthchecks)?base.healthchecks.filter(h=>!['Golden Path','Publishability','Telegram Review'].includes(String(h?.name||''))):[])].slice(0,8);

  base.events=[{
    at:chosen.updated_at||base.generated_at,
    title:`SOCIAL LIVE · ${active?'Produktion läuft':failed?'Technischer Stopp':'Run aktualisiert'}`,
    detail:`Run ${chosen.id} · Schritt ${chosen.step_number??'–'}: ${chosen.step||chosen.job||'Workflow'} · ${runProgress}%`
  },...(Array.isArray(base.events)?base.events:[])].slice(0,20);

  base.live={
    ...(base.live||{}),
    canonical_request_id:request.request_id,
    canonical_run_id:chosen.id,
    current:chosen,
    social_lane_active:true,
    social_request_id:request.request_id,
    social_run_id:chosen.id,
    source:'github-realtime+social-direct-request'
  };
  return base;
}

export default async function handler(req,res){
  const request=await latestSocialRequest();
  const originalJson=res.json.bind(res);
  res.json=(payload)=>originalJson(enhance(payload,request));
  return baseHandler(req,res);
}
