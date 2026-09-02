const STUDIO_REPO='mojo72549-arch/shorts-agent-studio';
const PILOT_BRANCH='lab/cinematic-control-center';
const PILOT_MEDIA='cinematic-control-center/media/latest-pilot.mp4';
const API='https://api.github.com';

function ghHeaders(){
  const token=String(process.env.TAYVORIQ_GITHUB_TOKEN||process.env.GITHUB_TOKEN||'').trim();
  const headers={Accept:'application/vnd.github+json','User-Agent':'tayvoriq-control-center-pilot-media','X-GitHub-Api-Version':'2022-11-28'};
  if(token) headers.Authorization=`Bearer ${token}`;
  return {headers,authenticated:Boolean(token)};
}

function contentPath(path){
  return String(path).split('/').map(encodeURIComponent).join('/');
}

export default async function handler(req,res){
  res.setHeader('Cache-Control','private, no-store, max-age=0, must-revalidate');
  res.setHeader('X-Content-Type-Options','nosniff');
  if(req.method&& !['GET','HEAD'].includes(req.method)) return res.status(405).json({ok:false,error:'method_not_allowed'});

  const gh=ghHeaders();
  if(!gh.authenticated) return res.status(503).json({ok:false,error:'server_token_not_configured'});

  try{
    const url=`${API}/repos/${STUDIO_REPO}/contents/${contentPath(PILOT_MEDIA)}?ref=${encodeURIComponent(PILOT_BRANCH)}`;
    const response=await fetch(url,{headers:gh.headers,cache:'no-store'});
    if(!response.ok) return res.status(response.status).json({ok:false,error:`pilot_media_unavailable_${response.status}`});
    const payload=await response.json();
    if(!payload?.download_url) return res.status(502).json({ok:false,error:'pilot_media_download_url_missing'});
    res.setHeader('Content-Disposition','inline; filename="tayvoriq-0217-pilot.mp4"');
    return res.redirect(307,payload.download_url);
  }catch(error){
    return res.status(502).json({ok:false,error:'pilot_media_proxy_failed',detail:String(error?.message||error)});
  }
}
