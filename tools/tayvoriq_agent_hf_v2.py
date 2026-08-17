from __future__ import annotations
import json, os
from typing import Any
from urllib.parse import urlparse
import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http
base=provider.base
HF_URL="https://router.huggingface.co/v1/chat/completions"

def domain(url:str)->str:
    try:
        h=urlparse(url).netloc.casefold().split(":",1)[0]; return h[4:] if h.startswith("www.") else h
    except Exception: return ""

def structure(prompt:str,token:str,records:list[dict[str,str]],source_label:str="independent-source-pool"):
    if not token: raise RuntimeError("HF_TOKEN/HUGGINGFACE_TOKEN missing")
    if len(records)<8 or len({r['domain'] for r in records})<2: raise RuntimeError("source pool too small for safe fallback")
    model=base.clean(os.getenv("TAYVORIQ_HF_MODEL"),160) or "openai/gpt-oss-120b:cheapest"; blob=json.dumps(records,ensure_ascii=False)
    schema='''{"candidates":[{"title":"German headline","category":"...","trend_scope":"technology_ai|business_economy|world_society|sports|science_future|creator_media|mobility_energy","regional_relevance":"local|germany|europe|global","criteria":{"aktualitaet":0,"viralitaet":0,"tayvoriq_passung":0,"quellenqualitaet":0,"visuell":0},"sources":[{"publisher":"domain","url":"exact URL","supports":"supported fact"},{"publisher":"different domain","url":"exact URL","supports":"supported fact"}],"fallback_editorial_answers":{"what_happened":"...","why_happening":"...","who_is_affected":"...","personal_impact":"...","action_now":"..."}}]}'''
    user=f'''Primary live browser providers are temporarily unavailable. Build TAYVORIQ candidates using ONLY the supplied current source records. Do not browse and do not infer facts beyond title + context. Cluster only records clearly describing the same current story. A candidate is valid only with EXACTLY TWO different publisher domains. Copy URLs exactly. If any required editorial answer is unsupported, drop the candidate. Natural-event candidates must be dropped unless the available records support the WHY/HOW. Return up to SIX candidates in German as valid JSON only.\nSCHEMA:\n{schema}\nEditorial ranking context only, never factual source:\n{prompt[:2500]}\nSOURCE RECORDS ({source_label}):\n{blob[:60000]}'''
    payload={"model":model,"messages":[{"role":"system","content":"Return valid JSON only. Source-bounded transformation; never invent facts or URLs."},{"role":"user","content":user}],"temperature":0,"max_tokens":8000,"stream":False}
    def call()->dict[str,Any]:
        raw,hs=http.post_json(HF_URL,payload,{"Content-Type":"application/json","Authorization":f"Bearer {token}","User-Agent":"tayvoriq-agent-v3-hf"},150)
        print(json.dumps({"event":"provider_success","provider":"huggingface","model":model,"source_label":source_label,"rate_limit":{k:hs[k] for k in http.RATE_HEADERS if k in hs}},ensure_ascii=False)); return raw
    raw=http.retry("huggingface",call,2); data=base.extract_json(provider.content_of(raw)); allowed={r['url'] for r in records}; chunks=[]
    for c in data.get("candidates") or []:
        if not isinstance(c,dict): continue
        src=[s for s in (c.get("sources") or []) if isinstance(s,dict)]; urls=[base.clean(s.get("url"),2000) for s in src]
        if len(urls)!=2 or any(u not in allowed for u in urls) or len({domain(u) for u in urls})!=2: c["sources"]=[]; continue
        for s in src:
            s["publisher"]=domain(base.clean(s.get("url"),2000)); chunks.append({"title":s["publisher"],"uri":base.clean(s.get("url"),2000)})
    return data,chunks,f"huggingface/{model}+{source_label}"
