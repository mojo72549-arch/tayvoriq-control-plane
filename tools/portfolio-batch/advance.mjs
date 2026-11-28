import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import crypto from 'node:crypto';

const control='mojo72549-arch/tayvoriq-control-plane', studio='mojo72549-arch/shorts-agent-studio';
const statusPath='state/tayvoriq-portfolio-backlog.json';
const root='.automation/tayvoriq-agent-v2';
const done=new Set(['CUT_READY','REVIEW_READY','NO_SELECTION','DECLINED','EXPIRED','STOPPED','REPLACED','PRODUCTION_BLOCKED']);
const day=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Berlin'}).format(new Date());
const norm=s=>s.toLocaleLowerCase('de-DE').normalize('NFC').replace(/\s+/g,' ').trim();

export function topicsOf(input){
  if(!Array.isArray(input)||input.length<1||input.length>10)throw Error('One to ten subjects required');
  const result=[];
  for(const value of input){
    if(typeof value!=='string'||value.trim().length<3||value.trim().length>240||/[\x00-\x1f]/.test(value))throw Error('Invalid subject');
    if(!result.some(s=>norm(s)===norm(value)))result.push(value.trim());
  }
  return result;
}

async function api(repo,path,token,options={}){
  if(!token)throw Error('Missing workflow credential');
  const r=await fetch('https://api.github.com/repos/'+repo+'/'+path,{signal:AbortSignal.timeout(15000),...options,
    headers:{Accept:'application/vnd.github+json',Authorization:'Bearer '+token,'User-Agent':'TAYVORIQ-portfolio-backlog','Content-Type':'application/json'}});
  if(r.status===404 && !options.method)return null;
  if(!r.ok)throw Error('GitHub operation failed ('+r.status+')');
  return r.status===204?null:r.json();
}
async function get(repo,path,token){
  const r=await api(repo,'contents/'+path+'?ref=main',token);
  return r?{sha:r.sha,value:JSON.parse(Buffer.from(r.content,'base64'))}:null;
}
async function put(repo,path,token,data,sha){
  const r=await api(repo,'contents/'+path,token,{method:'PUT',body:JSON.stringify({branch:'main',message:'Update portfolio production queue',...(sha?{sha}:{}),content:Buffer.from(JSON.stringify(data,null,2)+'\n').toString('base64')})});
  return r.content.sha;
}

export function progress(row,{request,decision,delivery,observation,rejected,run,pointer,today}){
  if(request){
    const c=request.production_completion;
    if(c?.state==='REVIEW_READY'&&c.quality_gates_weakened===false&&c.reference_only!==true
       &&c.golden_path_run_id===request.golden_path_run_id&&Number.isSafeInteger(c.telegram_message_id)&&c.telegram_message_id>0
       &&decision?.request_id===request.request_id&&String(decision.review_id)===String(c.golden_path_run_id)
       &&decision.telegram_message_id===c.telegram_message_id&&decision.source_context_sha256===request.source_context_sha256){
      return {state:'REVIEW_READY',run_id:c.golden_path_run_id,request_id:request.request_id,source_context_sha256:request.source_context_sha256};
    }
    if(['EXHAUSTED','EXTERNAL_BLOCKER'].includes(request.recovery_outcome?.state))return {state:'PRODUCTION_BLOCKED',request_id:request.request_id};
    return {state:'PRODUCING',request_id:request.request_id};
  }
  if(rejected)return {state:'DECLINED'};
  if(delivery?.telegram_delivery_verified===true&&delivery.selection_id===row.selection_id){
    return {state:row.day===today?'AWAITING_TOPIC':'EXPIRED'};
  }
  if(observation?.state==='STOPPED'||(pointer?.selection_id===row.selection_id&&pointer.cancel_requested_at))return {state:'STOPPED'};
  if(run?.status==='completed'&&['failure','cancelled','timed_out'].includes(run.conclusion))return {state:'NO_SELECTION'};
  if(run?.status==='completed'&&run.conclusion==='success'&&!delivery)return {state:'NO_SELECTION'};
  if(pointer?.selection_id===row.selection_id&&pointer.dispatch_state==='FAILED')return {state:'NO_SELECTION'};
  if(pointer?.selection_id!==row.selection_id&&pointer?.requested_at>row.started&& !run)return {state:'REPLACED'};
  return {state:'RESEARCHING'};
}

async function existingCut(subject,token){
  const releases=await api(studio,'releases?per_page=100',token);
  for(const release of releases??[]){
    const tag=release.tag_name,match=/^portfolio-([a-z0-9-]+)-[a-f0-9]{16}$/.exec(tag);
    if(!match||release.draft||![match[1],release.name].some(v=>v&&norm(v)===norm(subject)))continue;
    const assets=release.assets??[];
    if(![match[1]+'.mp4',match[1]+'.json','SHA256SUMS'].every(n=>assets.some(a=>a.name===n&&a.size>0&&a.state==='uploaded')))continue;
    const brief=await api(studio,'contents/portfolio/briefs/'+match[1]+'.json?ref='+encodeURIComponent(tag),token);
    if(!brief)continue;
    const doc=JSON.parse(Buffer.from(brief.content,'base64'));
    const age=Date.parse(day())-Date.parse(doc.checked);
    if(doc.id===match[1]&&Number.isFinite(age)&&age>=0&&age<=30*86400000)
      return {state:'CUT_READY',cut_id:doc.id,archive:release.html_url};
  }
  return null;
}

async function main(){
  const pub=process.env.GITHUB_TOKEN,privateToken=process.env.STUDIO_TOKEN;
  const event=JSON.parse(await readFile(process.env.GITHUB_EVENT_PATH,'utf8'));
  const saved=await get(control,statusPath,pub);
  let version=saved?.sha;
  const data=saved?.value??{schema:'tayvoriq-portfolio-backlog-v1',batches:[]};
  const save=async()=>{version=await put(control,statusPath,pub,data,version);};
  if(['repository_dispatch','push'].includes(process.env.GITHUB_EVENT_NAME)){
    const input=process.env.GITHUB_EVENT_NAME==='push'?JSON.parse(await readFile('.github/run-now/tayvoriq-portfolio-shelf.json','utf8')):event.client_payload??{};
    const id=input.id;
    if(!/^[0-9a-f-]{36}$/.test(id)||!['morning','evening'].includes(input.slot))throw Error('Invalid batch identity');
    const topics=topicsOf(input.topics), path='.automation/portfolio-topic-batches/'+id+'.json';
    const original=await get(studio,path,privateToken);
    const contents={id,slot:input.slot,topics};
    if(original&&JSON.stringify(original.value)!==JSON.stringify(contents))throw Error('Batch identity conflict');
    if(!original)await put(studio,path,privateToken,contents);
    if(!data.batches.some(b=>b.id===id)){
      data.batches.push({id,slot:input.slot,created:new Date().toISOString(),items:topics.map(()=>({state:'QUEUED'}))});
      await save();
    }
  }
  const batch=data.batches.find(b=>b.items.some(row=>!done.has(row.state)));
  if(!batch)return;
  const index=batch.items.findIndex(row=>!done.has(row.state)),row=batch.items[index];
  const readPublic=async path=>(await get(control,path,pub))?.value;
  const pointer=await readPublic('state/tayvoriq-control-center-research.json');
  if(row.selection_id&&row.state!=='STARTING'){
    const sid=row.selection_id;
    const [delivery,observation,rejected,dir]=await Promise.all([readPublic(root+'/deliveries/'+sid+'.json'),
      readPublic('state/tayvoriq-research-progress/'+sid+'.json'),readPublic(root+'/rejections/'+sid+'.json'),
      api(control,'contents/requests?ref=main',pub)]);
    const active=await readPublic('.github/state/tayvoriq-active-production-request.json');
    let rid=row.request_id??(active?.selection_id===sid?active.request_id:null);
    if(!rid&&delivery?.telegram_message_id){
      const prefix='telegram-'+delivery.telegram_message_id+'-trend-';
      const entry=dir?.find(f=>f.name.startsWith(prefix)&&f.name.endsWith('.json')&&!f.name.includes('repair'));
      if(entry)rid=entry.name.slice(0,-5);
    }
    let request=rid?await readPublic('requests/'+rid+'.json'):null;
    if(request?.selection_id!==sid)request=null;
    const decision=request?.production_completion?.golden_path_run_id?await readPublic('.automation/tayvoriq-artifact-decisions/'+request.production_completion.golden_path_run_id+'.json'):null;
    let run=observation?.run_id?await api(control,'actions/runs/'+observation.run_id,pub):null;
    if(!run&&!request&&!delivery){
      const recent=await api(control,'actions/runs?event=repository_dispatch&per_page=80',pub);
      run=recent.workflow_runs.find(r=>r.display_title==='TAYVORIQ research '+sid);
    }
    const update=progress(row,{request,decision,delivery,observation,rejected,run,pointer,today:day()});
    if(Object.entries(update).some(([k,v])=>row[k]!==v)){Object.assign(row,update);await save();}
    if(!done.has(row.state))return;
  }
  const nextBatch=data.batches.find(b=>b.items.some(i=>!done.has(i.state)));
  if(!nextBatch)return;
  const i=nextBatch.items.findIndex(x=>!done.has(x.state)),next=nextBatch.items[i];
  if(!['QUEUED','STARTING'].includes(next.state))return;
  const subject=(await get(studio,'.automation/portfolio-topic-batches/'+nextBatch.id+'.json',privateToken)).value.topics[i];
  const action='portfolio-'+nextBatch.id+'-'+i;
  if(next.state==='QUEUED'){
    const cut=await existingCut(subject,process.env.STUDIO_READ_TOKEN||privateToken);
    if(cut){
      Object.assign(next,cut);
      await save();
      if(nextBatch.items.some(item=>!done.has(item.state)))await main();
      return;
    }
  }
  if(next.state==='STARTING'&&pointer?.action_id===action){
    Object.assign(next,{state:'RESEARCHING',selection_id:pointer.selection_id,day:next.day??day()});await save();return;
  }
  if(pointer?.selection_id&&pointer.action_id!==action&&!pointer.cancel_requested_at&&pointer.selection_id.startsWith(day().replaceAll('-',''))){
    const prev=await readPublic(root+'/deliveries/'+pointer.selection_id+'.json');
    if(prev?.telegram_delivery_verified){
      const choices=await api(control,'contents/requests?ref=main',pub);
      const taken=choices.some(f=>f.name.startsWith('telegram-'+prev.telegram_message_id+'-trend-'));
      const declined=await readPublic(root+'/rejections/'+pointer.selection_id+'.json');
      if(!taken&&!declined)return;
    }
  }
  const nowDay=day();
  const refresh='c'+crypto.createHash('sha256').update([action,nextBatch.slot,nowDay,subject,'portfolio'].join('|')).digest('hex').slice(0,8);
  Object.assign(next,{state:'STARTING',started:new Date().toISOString(),day:nowDay,selection_id:nowDay.replaceAll('-','')+'-'+nextBatch.slot+'-agentv2-'+refresh});await save();
  const {requestResearch}=await import(pathToFileURL(process.env.OPERATOR_RESEARCH_MODULE).href);
  let status,body;
  const res={status(code){status=code;return this;},json(obj){body=obj;return obj;}};
  await requestResearch({body:{slot:nextBatch.slot,topic:subject,action_id:action,purpose:'portfolio'}},res);
  if(status===409&&body?.error==='research_in_progress'){next.state='QUEUED';delete next.selection_id;await save();return;}
  if(status!==202||body?.selection_id!==next.selection_id)throw Error('Portfolio research submission requires reconciliation ('+status+')');
  next.state='RESEARCHING';await save();
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)await main();
