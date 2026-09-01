const RAW='https://raw.githubusercontent.com/mojo72549-arch/tayvoriq-control-plane/main/run-status/ops-health.json';
const API='https://api.github.com/repos/mojo72549-arch/tayvoriq-control-plane/contents/run-status/ops-health.json?ref=main';

async function fromRaw(){
  const r=await fetch(`${RAW}?v=${Date.now()}`,{headers:{Accept:'application/json'},cache:'no-store'});
  if(!r.ok) throw new Error(`raw:${r.status}`);
  return r.json();
}

async function fromApi(){
  const r=await fetch(API,{headers:{Accept:'application/vnd.github+json','User-Agent':'tayvoriq-control-center'},cache:'no-store'});
  if(!r.ok) throw new Error(`api:${r.status}`);
  const p=await r.json();
  if(!p.content) throw new Error('api:no-content');
  return JSON.parse(Buffer.from(String(p.content).replace(/\n/g,''),'base64').toString('utf8'));
}

export default async function handler(req,res){
  res.setHeader('Cache-Control','no-store, max-age=0');
  res.setHeader('Access-Control-Allow-Origin','*');
  try{
    let data;
    try{data=await fromRaw()}catch{data=await fromApi()}
    res.status(200).json(data);
  }catch(error){
    res.status(502).json({schema:'tayvoriq-ops-health-error-v1',overall:'unknown',api_error:String(error?.message||error)});
  }
}
