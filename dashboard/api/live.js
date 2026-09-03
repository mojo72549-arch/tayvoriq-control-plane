const CONTROL_REPO='mojo72549-arch/tayvoriq-control-plane';
const STUDIO_REPO='mojo72549-arch/shorts-agent-studio';
const RAW_HEALTH='https://raw.githubusercontent.com/mojo72549-arch/tayvoriq-control-plane/main/run-status/ops-health.json';
const ACTIVE_POINTER='.github/state/tayvoriq-active-production-request.json';
const PILOT_BRANCH='lab/cinematic-control-center';
const PILOT_STATE='cinematic-control-center/run-state.json';
const API='https://api.github.com';
const ACTIVE_STATUSES=new Set(['in_progress','queued','requested','waiting','pending']);

function ghHeaders(){
  const token=String(process.env.TAYVORIQ_GITHUB_TOKEN||process.env.PRIVATE_REPO_TOKEN||process.env.GITHUB_TOKEN||'').trim();
  const h={Accept:'application/vnd.github+json','User-Agent':'tayvoriq-control-center-live','X-GitHub-Api-Version':'2022-11-28'};
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

function contentPath(path){
  return String(path).split('/').map(encodeURIComponent).join('/');
}

async function repoJson(repo,path,headers,ref='main'){
  const p=await jsonFetch(`${API}/repos/${repo}/contents/${contentPath(path)}?ref=${encodeURIComponent(ref)}`,headers);
  const text=Buffer.from(String(p.content||'').replace(/\n/g,''),'base64').toString('utf8');
  return JSON.parse(text);
}

function humanKind(name=''){
  const n=String(name).toLowerCase();
  if(n.includes('cinematic pilot')) return {kind:'pilot',label:'Cinematic Pilot',owner:'Cinematic Lab → Thunder A6000'};
  if(n.includes('golden path')) return {kind:'production',label:'Golden Path',owner:'Orchestrator → Golden Path'};
  if(n.includes('orchestrator')) return {kind:'recovery',label:'Orchestrator',owner:'TAYVORIQ Orchestrator'};
  if(n.includes('delivery watch')) return {kind:'recovery',label:'Delivery Recovery',owner:'Orchestrator → Delivery Watch'};
  if(n.includes('codefix')) return {kind:'recovery',label:'Codefix Recovery',owner:'Orchestrator → Codefix'};
  if(n.includes('production green')) return {kind:'quality',label:'Production Green',owner:'Orchestrator → Production Green'};
  if(n.includes('self-heal')||n.includes('self heal')||n.includes('recovery')) return {kind:'recovery',label:'Self-Heal / Recovery',owner:'Recovery Executor'};
  if(n.includes('quality')) return {kind:'quality',label:'Qualitätsprüfung',owner:'Quality Gate'};
  if(n.includes('publish')) return {kind:'publish',label:'Publish / Review',owner:'Publish Gate'};
  if(n.includes('telegram')) return {kind:'system',label:'Telegram-Dienst',owner:'Telegram'};
  if(n.includes('health')) return {kind:'system',label:'Health-Dienst',owner:'Health Monitor'};
  return {kind:'system',label:'Hintergrunddienst',owner:'System'};
}

function isNoise(name=''){
  const raw=String(name);
  const n=raw.toLowerCase();
  return raw.startsWith('.github/workflows/')||n.includes('artifact cleanup')||n.includes('legacy schedule guard')||n.includes('public preview')||n.includes('project lumen');
}

function stateFor(status,conclusion){
  status=String(status||'unknown');
  conclusion=String(conclusion||'');
  if(status==='in_progress') return 'läuft';
  if(['queued','requested','waiting','pending'].includes(status)) return 'startet';
  if(conclusion==='success') return 'erledigt';
  if(conclusion==='failure') return 'fehlgeschlagen';
  if(conclusion==='skipped') return 'übersprungen';
  if(['cancelled','canceled'].includes(conclusion)) return 'abgebrochen';
  if(status==='completed') return 'beendet';
  return 'wartet';
}

function runKey(repo,id){return `${repo}:${id}`}

async function listRuns(repo,headers){
  const p=await jsonFetch(`${API}/repos/${repo}/actions/runs?per_page=24`,headers);
  return (Array.isArray(p.workflow_runs)?p.workflow_runs:[]).map(r=>({...r,_repo:repo}));
}

async function getRun(repo,id,headers){
  const r=await jsonFetch(`${API}/repos/${repo}/actions/runs/${id}`,headers);
  return {...r,_repo:repo};
}

async function getJobs(repo,id,headers){
  const p=await jsonFetch(`${API}/repos/${repo}/actions/runs/${id}/jobs?filter=latest&per_page=100`,headers);
  return Array.isArray(p.jobs)?p.jobs:[];
}

function selectJob(jobs=[]){
  return jobs.find(j=>String(j.status)==='in_progress')
    ||jobs.find(j=>String(j.conclusion)==='failure')
    ||jobs.find(j=>ACTIVE_STATUSES.has(String(j.status)))
    ||jobs[0]
    ||null;
}

function selectStep(job){
  const steps=Array.isArray(job?.steps)?job.steps:[];
  return steps.find(s=>String(s.status)==='in_progress')
    ||steps.find(s=>String(s.conclusion)==='failure')
    ||[...steps].reverse().find(s=>String(s.status)==='completed'&&String(s.conclusion)!=='skipped')
    ||steps.find(s=>ACTIVE_STATUSES.has(String(s.status)))
    ||null;
}

function toActivity(run,jobs=[]){
  const workflow=run.name||run.display_title||'GitHub Action';
  const meta=humanKind(workflow);
  const job=selectJob(jobs);
  const step=selectStep(job);
  const detail=[workflow,job?.name,step?.name].filter(Boolean).join(' › ');
  return {
    id:run.id,
    repo:run._repo||CONTROL_REPO,
    name:detail||workflow,
    workflow,
    job:job?.name||null,
    job_status:job?.status||null,
    job_conclusion:job?.conclusion||null,
    step:step?.name||null,
    step_number:step?.number??null,
    step_status:step?.status||null,
    step_conclusion:step?.conclusion||null,
    label:meta.label,
    owner:meta.owner,
    kind:meta.kind,
    state:stateFor(run.status,run.conclusion),
    status:String(run.status||'unknown'),
    conclusion:run.conclusion||null,
    started_at:job?.started_at||run.run_started_at||run.created_at||null,
    updated_at:run.updated_at||run.created_at||null,
    url:run.html_url||null,
    attempt:run.run_attempt||1
  };
}

function phase(step){
  if(!step) return 'pending';
  const conclusion=String(step.conclusion||'').toLowerCase();
  const status=String(step.status||'').toLowerCase();
  if(conclusion==='failure') return 'error';
  if(status==='in_progress') return 'running';
  if(conclusion==='success') return 'success';
  if(conclusion==='skipped') return 'skipped';
  return 'pending';
}

function findStep(steps,...patterns){
  const pats=patterns.map(p=>String(p).toLowerCase());
  return steps.find(step=>pats.some(p=>String(step.name||'').toLowerCase().includes(p)))||null;
}

function buildStages(jobs=[]){
  const job=jobs.find(j=>String(j.name||'').toLowerCase()==='orchestrate')||jobs[0]||{};
  const steps=Array.isArray(job.steps)?job.steps:[];
  const defs=[
    ['Freigabe gebunden',['resolve approved x request']],
    ['Quellen gesperrt',['materialize immutable verified source context']],
    ['Dublettenprüfung',['block global duplicate content']],
    ['Light Preflight',['lightweight contract preflight']],
    ['Dependencies',['install production dependencies']],
    ['Full Preflight',['preflight']],
    ['Produktion / Master',['produce approved master']],
    ['Publishable Output',['assert publishable production output']],
    ['Quality Audit',['validate publication quality']],
    ['Review-Seite',['publish review page']],
    ['Telegram Review',['send telegram review']]
  ];
  return defs.map(([label,pats])=>{
    const step=findStep(steps,...pats);
    return {label,status:phase(step),step_number:step?.number??null,step_name:step?.name||null};
  });
}

function progressFromStages(stages=[],status,conclusion){
  if(conclusion==='success') return 100;
  const weights=[8,16,22,30,38,45,65,72,82,92,96];
  let progress=0;
  for(let i=0;i<stages.length;i++){
    const s=stages[i]?.status;
    if(['success','skipped'].includes(s)) progress=Math.max(progress,weights[i]);
    else if(['running','error'].includes(s)){progress=Math.max(progress,weights[i]);break}
    else break;
  }
  if(['queued','requested','waiting'].includes(String(status))) return Math.max(progress,3);
  return progress;
}

function requestState(data){
  const history=(Array.isArray(data?.state_history)?data.state_history:[]).filter(x=>x&&typeof x==='object');
  return String(history.at(-1)?.state||data?.codefix_recovery?.request_substate||data?.status||'UNKNOWN').toUpperCase();
}

function userActionRequired(failureState){
  return /(EXTERNAL|SECRET|AUTH|PAYMENT|BILLING|PERMISSION|QUOTA|ACCOUNT)/i.test(String(failureState||''));
}

function pilotFailureClass(stage='',step='',message=''){
  const value=`${stage} ${step} ${message}`.toUpperCase();
  if(/SECRET|TOKEN|AUTH|PAYMENT|BILLING|QUOTA|ACCOUNT|PERMISSION/.test(value)) return 'EXTERNAL_BLOCKER';
  if(/DELETE|CLEANUP|BILLING STOP/.test(value)) return 'GPU_CLEANUP_WARNING';
  if(/GPU|THUNDER|INSTANCE|SSH|PREFLIGHT/.test(value)) return 'GPU_PROVISION_FAILED';
  if(/MODEL|WAN|DIFFUSERS/.test(value)) return 'MODEL_LOAD_FAILED';
  if(/RENDER|SHOT/.test(value)) return 'SHOT_RENDER_FAILED';
  if(/DOWNLOAD|TRANSFER|SCP|ARTIFACT/.test(value)) return 'ARTIFACT_TRANSFER_FAILED';
  if(/PUBLISH|MEDIA|CONTROL CENTER/.test(value)) return 'PILOT_PUBLISH_FAILED';
  return 'PILOT_RUN_FAILED';
}

function buildPilot(state,run,jobs=[]){
  if(!state) return {available:false,reason:'pilot_state_unavailable'};
  const job=selectJob(jobs);
  const steps=Array.isArray(job?.steps)?job.steps:[];
  const failedStep=steps.find(s=>String(s.conclusion)==='failure')||null;
  const activeStep=steps.find(s=>String(s.status)==='in_progress')||null;
  const lastSuccess=[...steps].reverse().find(s=>String(s.conclusion)==='success')||null;
  const cleanupStep=findStep(steps,'delete thunder gpu');
  const failed=String(state.status).toUpperCase()==='FAILED'||String(run?.conclusion)==='failure';
  const failureClass=failed?pilotFailureClass(state.stage,failedStep?.name,state.last_error):null;
  const ready=Boolean(state?.video?.ready)&&(['COMPLETE','VISUAL_REVIEW_READY'].includes(String(state.status).toUpperCase())||failureClass==='GPU_CLEANUP_WARNING');
  return {
    available:true,
    project:state.project||'TAYVORIQ ORIGINALS · 02:17',
    environment:state.environment||'LAB',
    status:String(state.status||run?.status||'UNKNOWN').toUpperCase(),
    stage:String(state.stage||'UNKNOWN').toUpperCase(),
    progress:Number(state.progress||0),
    provider:state.provider||'Thunder Compute',
    gpu:state.gpu||'RTX A6000 48 GB',
    model:state.model||'Wan 2.2 TI2V-5B',
    updated_at:state.updated_at||run?.updated_at||null,
    cost_estimate_usd:state.cost_estimate_usd??null,
    shots:Array.isArray(state.shots)?state.shots:[],
    audio:state.audio||{},
    visual_review_ready:ready,
    media_url:ready?'/api/pilot-media':null,
    run:{
      id:Number(state.run_id||run?.id||0)||null,
      url:state.run_url||run?.html_url||null,
      status:run?.status||null,
      conclusion:run?.conclusion||null,
      attempt:run?.run_attempt||1,
      current_step:activeStep?.name||null,
      failed_step:failedStep?.name||null,
      failed_step_number:failedStep?.number??null,
      last_successful_step:lastSuccess?.name||null
    },
    gpu_cleanup:{
      status:phase(cleanupStep),
      detail:cleanupStep?.conclusion==='success'?'Thunder-Instanz entfernt · Abrechnung gestoppt':cleanupStep?.name||'Cleanup noch nicht erreicht'
    },
    error:failed?{
      class:failureClass,
      message:state.last_error||`Pilot-Run ist bei ${failedStep?.name||state.stage||'unbekanntem Schritt'} fehlgeschlagen.`,
      failed_step:failedStep?.name||null,
      failed_step_number:failedStep?.number??null,
      user_action_required:failureClass==='GPU_CLEANUP_WARNING'||userActionRequired(`${failureClass} ${state.last_error||''}`)
    }:null
  };
}

function buildOperatorFeed(state,pilot,jobs=[]){
  const job=selectJob(jobs);
  const steps=Array.isArray(job?.steps)?job.steps:[];
  const shots=Array.isArray(pilot?.shots)?pilot.shots:[];
  const runId=pilot?.run?.id||state?.run_id||null;
  const items=[];
  const seen=new Set();
  const add=(severity,title,detail,at=null,id=null)=>{
    const key=id||`${runId||'pilot'}:${title}:${detail}`;
    if(seen.has(key)) return;
    seen.add(key);
    items.push({id:key,severity,title,detail,at:at||pilot?.updated_at||null,run_id:runId});
  };

  if(!pilot?.available){
    add('error','Pilot-Livefeed nicht erreichbar','Die private Run-Telemetrie ist noch nicht verbunden. Kein Status wird erfunden.',null,'pilot:unavailable');
    return items;
  }

  const completed=shots.filter(s=>['DONE','SUCCESS','COMPLETE','READY'].includes(String(s.status||'').toUpperCase())).length;
  const total=Number(state?.total_shots||shots.length||5);
  const currentShot=shots.find(s=>['RENDERING','RUNNING'].includes(String(s.status||'').toUpperCase()))||null;
  const stage=String(pilot.stage||'UNKNOWN').toUpperCase();
  const active=ACTIVE_STATUSES.has(String(pilot?.run?.status))||['RUNNING','RENDERING'].includes(String(pilot.status));
  const cleanup=pilot.gpu_cleanup||{};

  if(pilot.error){
    const cleanupText=cleanup.status==='success'?' Die Thunder-GPU wurde entfernt; die Abrechnung ist gestoppt.':'';
    add(
      pilot.error.user_action_required?'error':'warning',
      `Technischer Stopp: ${pilot.error.failed_step||stage.replaceAll('_',' ')}`,
      `${pilot.error.message||'Der Run wurde an einem klaren Gate gestoppt.'}${cleanupText} ${pilot.error.user_action_required?'Eine externe Aktion ist nötig.':'Keine Nutzeraktion nötig; lokal reparieren und geprüft fortsetzen.'}`,
      pilot.updated_at,
      `pilot:${runId}:error:${pilot.error.failed_step_number||stage}`
    );
  }else if(pilot.visual_review_ready){
    add('success','Visual-Review-Paket ist bereit',`${completed} von ${total} Shots sind technisch geprüft. Das Video kann direkt hier angesehen werden. Nächster Schritt: deine visuelle Freigabe; erst danach folgen Voice, Musik und SFX.`,pilot.updated_at,`pilot:${runId}:ready`);
  }else if(stage==='RENDERING'&&currentShot){
    add('working',`Shot ${currentShot.id} rendert jetzt: „${currentShot.title}“`,`${completed} von ${total} Shots sind fertig. A6000 und Renderer sind aktiv; kein Retry und kein neuer Fehler. Kein Eingriff nötig.`,pilot.updated_at,`pilot:${runId}:shot:${currentShot.id}:rendering`);
  }else{
    const narration={
      STARTING:['Der neue Pilot-Run ist gestartet',`Run ${runId||'–'} ist eindeutig gebunden. Preflight und Schutzgates werden geprüft.`],
      GPU_STARTING:['Thunder-Preflight läuft','Token, vorhandene Instanzen und lokales Prüftool werden kontrolliert, bevor GPU-Kosten entstehen.'],
      GPU_READY:['A6000 und SSH sind bereit','Genau eine Thunder-Instanz läuft. Der Modellschritt ist als Nächstes dran.'],
      MODEL_LOADING:['Wan 2.2 wird vorbereitet','GPU und SSH sind bereit. Der visuelle 5-Shot-Pilot wird ohne Audio vorbereitet; kein Fehler gemeldet.'],
      DOWNLOADING:['Alle fünf Shots sind erzeugt','Die Einzelshots, der 25-Sekunden-Cut, das Storyboard und das Manifest werden von der GPU geladen.'],
      VISUAL_VALIDATION:['Der Review-Cut wird technisch geprüft','Auflösung, Dauer, Dateigröße und die bewusste Audiofreiheit werden jetzt verifiziert.'],
      PUBLISHING:['Das geprüfte Video wird eingebaut','Der validierte Review-Cut wird in den Control-Center-Player veröffentlicht.'],
      COMPLETE:['Visual-Review-Paket ist bereit',`${completed} von ${total} Shots sind technisch geprüft. Deine visuelle Freigabe ist offen.`],
      VISUAL_REVIEW_READY:['Visual-Review-Paket ist bereit',`${completed} von ${total} Shots sind technisch geprüft. Deine visuelle Freigabe ist offen; Audio bleibt zurückgestellt.`]
    };
    const [title,detail]=narration[stage]||[active?'Pilot-Run arbeitet weiter':'Pilot wartet',pilot?.run?.current_step?`Aktueller Schritt: ${pilot.run.current_step}`:`Status: ${stage.replaceAll('_',' ')}`];
    add(active?'working':['COMPLETE','VISUAL_REVIEW_READY'].includes(stage)?'success':'info',title,detail,pilot.updated_at,`pilot:${runId}:stage:${stage}`);
  }

  [...shots].reverse().forEach(shot=>{
    if(['DONE','SUCCESS','COMPLETE','READY'].includes(String(shot.status||'').toUpperCase())){
      add('success',`Shot ${shot.id} ist fertig und validiert`,shot.title||'Shot-Datei wurde technisch geprüft.',null,`pilot:${runId}:shot:${shot.id}:done`);
    }
  });

  const facts=[
    ['Guardrails and Thunder preflight','success','Preflight bestanden','Validator, Token und Ein-Instanz-Schutz sind bestätigt.'],
    ['Create one RTX A6000','success','Genau eine A6000 wurde gestartet','Keine zweite bezahlte GPU-Instanz wurde angelegt.'],
    ['Prepare Wan 2.2 renderer','success','Wan 2.2 ist bereit','Renderer und Abhängigkeiten wurden auf der A6000 vorbereitet.'],
    ['Preserve downloaded pilot artifact','success','Pilot-Dateien sind gesichert','Der komplette Download wurde vor der Endprüfung als Artefakt konserviert.'],
    ['Delete Thunder GPU even after failure','success','GPU entfernt · Abrechnung gestoppt','Thunder bestätigt, dass die Instanz nicht mehr aktiv ist.']
  ];
  facts.forEach(([needle,want,title,detail])=>{
    const step=findStep(steps,needle);
    if(step?.conclusion===want) add('success',title,detail,step.completed_at,`pilot:${runId}:step:${step.number}:success`);
  });

  const persisted=Array.isArray(state?.operator_events)?state.operator_events:[];
  persisted.slice().reverse().forEach((event,index)=>{
    if(!event||!event.title) return;
    add(event.severity||'info',String(event.title),String(event.detail||''),event.at||null,event.id||`pilot:${runId}:stored:${index}`);
  });
  return items.slice(0,12);
}

function colorForRun(run){
  if(!run) return 'unknown';
  if(ACTIVE_STATUSES.has(String(run.status))) return 'yellow';
  if(run.conclusion==='success') return 'green';
  if(['failure','timed_out','cancelled','canceled','action_required'].includes(String(run.conclusion))) return 'red';
  return 'unknown';
}

function liveHealthchecks(snapshot,canonicalRun,stages,recovery,activity){
  const existing=new Map((snapshot?.healthchecks||[]).map(x=>[String(x.name||''),x]));
  const qa=stages.find(x=>x.label==='Quality Audit');
  const pub=stages.find(x=>x.label==='Publishable Output');
  const orchestrator=activity.find(x=>/orchestrator/i.test(x.workflow||''));
  const result=[];
  result.push({name:'Orchestrator',status:orchestrator?(ACTIVE_STATUSES.has(orchestrator.status)?'yellow':orchestrator.conclusion==='failure'?'red':'green'):'unknown',detail:orchestrator?`${orchestrator.state} · ${orchestrator.step||orchestrator.job||'Workflow'}`:'Kein aktueller Orchestrator-Lauf in der Live-Abfrage'});
  result.push({name:'Golden Path',status:colorForRun(canonicalRun),detail:canonicalRun?`Run ${canonicalRun.id} · ${stateFor(canonicalRun.status,canonicalRun.conclusion)}`:'Kein kanonischer Run auflösbar'});
  const pg=existing.get('Production Green'); if(pg) result.push(pg);
  const recoveryActive=activity.find(x=>x.kind==='recovery'&&ACTIVE_STATUSES.has(x.status));
  result.push({name:'Self-Heal',status:recoveryActive?'yellow':String(recovery?.status||'').toUpperCase().includes('DISPATCHED')?'yellow':existing.get('Self-Heal')?.status||'unknown',detail:recoveryActive?`${recoveryActive.label}: ${recoveryActive.step||recoveryActive.job||recoveryActive.state}`:`${recovery?.status||'–'} · Gen ${recovery?.recovery_generation??0}`});
  result.push({name:'Publishability',status:pub?.status==='success'?'green':pub?.status==='error'?'red':pub?.status==='running'?'yellow':'unknown',detail:pub?.step_name||'Noch nicht erreicht'});
  result.push({name:'Quality Gates',status:qa?.status==='success'?'green':qa?.status==='error'?'red':qa?.status==='running'?'yellow':pub?.status==='error'?'yellow':'unknown',detail:qa?.status==='success'?'Quality Audit bestanden':pub?.status==='error'?'Wartet auf reparierten Publishable Output':qa?.status==='skipped'?'Noch nicht ausgeführt':'Noch nicht erreicht'});
  const telegram=existing.get('Telegram'); if(telegram) result.push(telegram);
  return result;
}

async function legacyState(headers,authenticated){
  if(!authenticated) return {available:false,reason:'server_token_not_configured'};
  try{
    const data=await repoJson(STUDIO_REPO,'.automation/tayvoriq-progress/latest.json',headers);
    return {available:true,data};
  }catch(error){
    return {available:false,reason:String(error?.message||error)};
  }
}

export default async function handler(req,res){
  const checkedAt=new Date().toISOString();
  const gh=ghHeaders();
  const errors=[];
  let snapshot=null;
  let pointer=null;
  let requestData=null;
  let controlRuns=[];
  let studioRuns=[];
  let canonicalRun=null;
  let pilotState=null;
  let pilotRun=null;
  let pilotUnavailable=null;

  try{snapshot=await health()}catch(error){errors.push(`health:${error?.message||error}`)}
  try{
    pointer=await repoJson(CONTROL_REPO,ACTIVE_POINTER,gh.headers);
    if(pointer?.request_id) requestData=await repoJson(CONTROL_REPO,`requests/${pointer.request_id}.json`,gh.headers);
  }catch(error){errors.push(`canonical:${error?.message||error}`)}
  if(gh.authenticated){
    try{pilotState=await repoJson(STUDIO_REPO,PILOT_STATE,gh.headers,PILOT_BRANCH)}catch(error){pilotUnavailable=String(error?.message||error)}
  }else pilotUnavailable='server_token_not_configured';

  const canonicalRunId=Number(pointer?.golden_path_run_id||requestData?.golden_path_run_id||0)||null;
  try{controlRuns=await listRuns(CONTROL_REPO,gh.headers)}catch(error){errors.push(`control-actions:${error?.message||error}`)}
  try{studioRuns=await listRuns(STUDIO_REPO,gh.headers)}catch(error){errors.push(`studio-actions:${error?.message||error}`)}

  if(canonicalRunId){
    canonicalRun=controlRuns.find(r=>Number(r.id)===canonicalRunId)||null;
    if(!canonicalRun){try{canonicalRun=await getRun(CONTROL_REPO,canonicalRunId,gh.headers)}catch(error){errors.push(`canonical-run:${error?.message||error}`)}}
  }

  const pilotRunId=Number(pilotState?.run_id||0)||null;
  if(pilotRunId){
    pilotRun=studioRuns.find(r=>Number(r.id)===pilotRunId)||null;
    if(!pilotRun){try{pilotRun=await getRun(STUDIO_REPO,pilotRunId,gh.headers)}catch(error){pilotUnavailable=`run:${error?.message||error}`}}
  }

  const candidates=[...controlRuns,...studioRuns].filter(r=>!isNoise(r.name||r.display_title));
  const targetMap=new Map();
  if(canonicalRun) targetMap.set(runKey(canonicalRun._repo,canonicalRun.id),canonicalRun);
  if(pilotRun) targetMap.set(runKey(pilotRun._repo,pilotRun.id),pilotRun);
  for(const run of candidates.filter(r=>ACTIVE_STATUSES.has(String(r.status))).slice(0,8)) targetMap.set(runKey(run._repo,run.id),run);
  for(const run of candidates.slice(0,4)) if(targetMap.size<10) targetMap.set(runKey(run._repo,run.id),run);

  const telemetry=[];
  const jobsByKey=new Map();
  await Promise.all([...targetMap.values()].map(async run=>{
    let jobs=[];
    try{jobs=await getJobs(run._repo,run.id,gh.headers)}catch(error){errors.push(`jobs:${run._repo}:${run.id}:${error?.message||error}`)}
    jobsByKey.set(runKey(run._repo,run.id),jobs);
    telemetry.push(toActivity(run,jobs));
  }));
  telemetry.sort((a,b)=>Date.parse(b.updated_at||0)-Date.parse(a.updated_at||0));

  const canonicalJobs=canonicalRun?jobsByKey.get(runKey(canonicalRun._repo,canonicalRun.id))||[]:[];
  const pilotJobs=pilotRun?jobsByKey.get(runKey(pilotRun._repo,pilotRun.id))||[]:[];
  const canonicalActivity=canonicalRun?toActivity(canonicalRun,canonicalJobs):null;
  const stages=canonicalRun?buildStages(canonicalJobs):(snapshot?.run?.stages||[]);
  const failedStage=stages.find(x=>x.status==='error')||null;
  const activeStage=stages.find(x=>x.status==='running')||null;
  const lastSuccess=[...stages].reverse().find(x=>x.status==='success')||null;
  const recoveryData=(requestData?.codefix_recovery&&typeof requestData.codefix_recovery==='object')?requestData.codefix_recovery:{};
  const recovery={
    ...(snapshot?.recovery||{}),
    ...recoveryData,
    status:recoveryData.status||snapshot?.recovery?.status||'UNKNOWN',
    recovery_generation:Number(requestData?.recovery_generation??recoveryData.fresh_recovery_generation??recoveryData.recovery_generation??snapshot?.recovery?.recovery_generation??0),
    owner:requestData?.recovery_owner||snapshot?.recovery?.owner||'tayvoriq-agent-orchestrator-v2'
  };

  const canonicalRequest=requestData?{
    ...(snapshot?.request||{}),
    request_id:pointer?.request_id||requestData.request_id,
    topic:requestData.topic||snapshot?.request?.topic||null,
    state:requestState(requestData),
    trend_id:requestData.trend_id||pointer?.trend_id||null,
    recovery_generation:Number(requestData.recovery_generation??0),
    recovery_owner:requestData.recovery_owner||recovery.owner,
    updated_at:pointer?.updated_at||requestData.recovery_dispatched_at||null
  }:(snapshot?.request||{});

  const liveRun=canonicalRun?{
    ...(snapshot?.run||{}),
    id:canonicalRun.id,
    name:canonicalRun.name||canonicalRun.display_title||'TAYVORIQ-X Golden Path',
    status:canonicalRun.status||'unknown',
    conclusion:canonicalRun.conclusion||null,
    attempt:canonicalRun.run_attempt||1,
    html_url:canonicalRun.html_url||null,
    created_at:canonicalRun.created_at||null,
    updated_at:canonicalRun.updated_at||null,
    current_step:activeStage?.step_name||null,
    failed_step:failedStage?.step_name||null,
    failed_step_number:failedStage?.step_number??null,
    last_successful_step:lastSuccess?.step_name||null,
    progress:progressFromStages(stages,canonicalRun.status,canonicalRun.conclusion),
    stages
  }:(snapshot?.run||{});

  const failureState=recoveryData.failure_state||snapshot?.incident?.failure_state||null;
  const incident=failedStage?{
    ...(snapshot?.incident||{}),
    failure_state:failureState||'WORKFLOW_FAILURE',
    failed_step:failedStage.step_name,
    failed_step_number:failedStage.step_number,
    self_heal_status:recovery.status,
    user_action_required:userActionRequired(failureState)
  }:(snapshot?.incident||null);

  const active=telemetry.filter(x=>ACTIVE_STATUSES.has(x.status));
  const current=active[0]||canonicalActivity||telemetry[0]||null;
  const latestAt=current?.updated_at||telemetry[0]?.updated_at||pointer?.updated_at||snapshot?.generated_at||null;
  const latestAge=latestAt?Math.max(0,Math.round((Date.now()-Date.parse(latestAt))/1000)):null;
  const snapshotAt=snapshot?.generated_at||null;
  const snapshotAge=snapshotAt?Math.max(0,Math.round((Date.now()-Date.parse(snapshotAt))/1000)):null;
  const overall=active.length?'yellow':canonicalRun?colorForRun(canonicalRun):(snapshot?.overall||'unknown');
  const healthchecks=liveHealthchecks(snapshot,canonicalRun,stages,recovery,telemetry);

  const liveEvents=[];
  for(const item of telemetry.slice(0,6)) liveEvents.push({at:item.updated_at,title:`LIVE · ${item.label} · ${item.state}`,detail:`${item.repo.split('/').at(-1)} · Run ${item.id}${item.job?` · ${item.job}`:''}${item.step?` · Step ${item.step_number??'–'}: ${item.step}`:''}`});
  if(pointer?.updated_at) liveEvents.push({at:pointer.updated_at,title:'Kanonischer Auftrag gebunden',detail:`${pointer.request_id} → Golden Path Run ${canonicalRunId||'–'}`});

  const legacy=await legacyState(gh.headers,gh.authenticated);
  const pilot=pilotState?buildPilot(pilotState,pilotRun,pilotJobs):{available:false,reason:pilotUnavailable||'pilot_state_unavailable'};
  const operatorFeed=buildOperatorFeed(pilotState,pilot,pilotJobs);
  const payload={
    ...(snapshot||{schema:'tayvoriq-live-v2'}),
    schema:'tayvoriq-live-v2',
    generated_at:checkedAt,
    overall,
    user_action_required:Boolean(incident?.user_action_required),
    request:canonicalRequest,
    run:liveRun,
    recovery,
    incident,
    healthchecks,
    events:[...liveEvents,...(snapshot?.events||[])].slice(0,20),
    pilot,
    operator_feed:operatorFeed,
    live:{
      checked_at:checkedAt,
      authenticated:gh.authenticated,
      canonical_pointer:ACTIVE_POINTER,
      canonical_request_id:pointer?.request_id||null,
      canonical_run_id:canonicalRunId,
      canonical_pointer_updated_at:pointer?.updated_at||null,
      snapshot_at:snapshotAt,
      snapshot_age_seconds:snapshotAge,
      latest_activity_at:latestAt,
      latest_activity_age_seconds:latestAge,
      active_count:active.length,
      active_activity:active,
      current,
      telemetry_count:telemetry.length,
      source:errors.length?'github-realtime+canonical-pointer+partial':'github-realtime+canonical-pointer',
      errors
    },
    activity:telemetry,
    legacy
  };

  res.setHeader('Content-Type','application/json; charset=utf-8');
  res.setHeader('Access-Control-Allow-Origin','*');
  res.setHeader('Cache-Control','no-store, max-age=0, must-revalidate');
  res.setHeader('Pragma','no-cache');
  res.status(snapshot||telemetry.length||pointer?200:502).json(payload);
}
