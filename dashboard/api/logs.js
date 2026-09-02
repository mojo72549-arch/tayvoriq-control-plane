const CONTROL_REPO='mojo72549-arch/tayvoriq-control-plane';
const STUDIO_REPO='mojo72549-arch/shorts-agent-studio';
const API='https://api.github.com';
const ALLOWED=new Set([CONTROL_REPO,STUDIO_REPO]);

function ghHeaders(){
  const token=String(process.env.TAYVORIQ_GITHUB_TOKEN||process.env.GITHUB_TOKEN||'').trim();
  const headers={Accept:'application/vnd.github+json','User-Agent':'tayvoriq-control-center-logs','X-GitHub-Api-Version':'2022-11-28'};
  if(token) headers.Authorization=`Bearer ${token}`;
  return {headers,authenticated:Boolean(token)};
}

function resolveRepo(value){
  const raw=String(value||'').trim();
  if(raw==='control') return CONTROL_REPO;
  if(raw==='studio') return STUDIO_REPO;
  return ALLOWED.has(raw)?raw:null;
}

async function jsonFetch(url,headers){
  const r=await fetch(url,{headers,cache:'no-store'});
  if(!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

function selectJob(jobs=[]){
  return jobs.find(j=>String(j.status)==='completed'&&String(j.conclusion)==='failure')
    ||[...jobs].reverse().find(j=>String(j.status)==='completed')
    ||jobs.find(j=>String(j.status)==='in_progress')
    ||jobs[0]
    ||null;
}

function redact(text){
  return String(text||'')
    .replace(/gh[pousr]_[A-Za-z0-9_]{20,}/g,'[REDACTED_GITHUB_TOKEN]')
    .replace(/Bearer\s+[^\s]+/gi,'Bearer [REDACTED]')
    .replace(/bot\d+:[A-Za-z0-9_-]{20,}/g,'bot[REDACTED]')
    .replace(/(TELEGRAM_BOT_TOKEN|GITHUB_TOKEN|TAYVORIQ_GITHUB_TOKEN)=([^\s]+)/gi,'$1=[REDACTED]');
}

export default async function handler(req,res){
  res.setHeader('Content-Type','application/json; charset=utf-8');
  res.setHeader('Cache-Control','no-store, max-age=0, must-revalidate');
  res.setHeader('Pragma','no-cache');
  if(req.method&&req.method!=='GET') return res.status(405).json({ok:false,error:'method_not_allowed'});

  const repo=resolveRepo(req.query?.repo);
  const runId=Number(req.query?.run||0);
  if(!repo||!Number.isSafeInteger(runId)||runId<=0) return res.status(400).json({ok:false,error:'invalid_repo_or_run'});

  const gh=ghHeaders();
  try{
    const jobPayload=await jsonFetch(`${API}/repos/${repo}/actions/runs/${runId}/jobs?filter=latest&per_page=100`,gh.headers);
    const jobs=Array.isArray(jobPayload.jobs)?jobPayload.jobs:[];
    const job=selectJob(jobs);
    if(!job) return res.status(200).json({ok:true,available:false,reason:'no_job',repo,run_id:runId,authenticated:gh.authenticated});
    if(String(job.status)!=='completed'){
      return res.status(200).json({ok:true,available:false,reason:'job_in_progress',repo,run_id:runId,job_id:job.id,job_name:job.name,status:job.status,authenticated:gh.authenticated});
    }

    const logResponse=await fetch(`${API}/repos/${repo}/actions/jobs/${job.id}/logs`,{headers:gh.headers,cache:'no-store',redirect:'follow'});
    if(!logResponse.ok){
      return res.status(200).json({ok:true,available:false,reason:`log_unavailable_${logResponse.status}`,repo,run_id:runId,job_id:job.id,job_name:job.name,authenticated:gh.authenticated});
    }
    const raw=redact(await logResponse.text());
    const lines=raw.split(/\r?\n/).filter(Boolean).slice(-140);
    let text=lines.join('\n');
    if(text.length>28000) text=text.slice(-28000);
    return res.status(200).json({ok:true,available:true,repo,run_id:runId,job_id:job.id,job_name:job.name,conclusion:job.conclusion,completed_at:job.completed_at||null,authenticated:gh.authenticated,line_count:lines.length,text});
  }catch(error){
    return res.status(200).json({ok:true,available:false,reason:String(error?.message||error),repo,run_id:runId,authenticated:gh.authenticated});
  }
}
