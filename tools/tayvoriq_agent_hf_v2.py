from __future__ import annotations
import json, os
from collections import defaultdict, deque
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

def _balanced_compact_records(records:list[dict[str,str]],max_chars:int=56000)->list[dict[str,str]]:
    groups:dict[str,deque[dict[str,str]]]=defaultdict(deque)
    for record in records:
        host=str(record.get('domain') or domain(str(record.get('url') or ''))).casefold()
        if host:
            groups[host].append(record)
    selected=[]; hosts=sorted(groups)
    while hosts:
        next_hosts=[]
        for host in hosts:
            if not groups[host]:
                continue
            rec=groups[host].popleft()
            compact={
                **rec,
                'title':base.clean(rec.get('title'),280),
                'context':base.clean(rec.get('context'),750),
                'domain':host,
            }
            selected.append(compact)
            next_hosts.append(host)
        hosts=next_hosts
        if len(selected)>=96:
            break
    bounded=[]
    for rec in selected:
        candidate=bounded+[rec]
        preview=[{
            'source_id':f'S{i+1:03d}',
            'domain':item.get('domain'),
            'title':item.get('title'),
            'context':item.get('context'),
            'seen_date':item.get('seen_date'),
            'feed':item.get('feed'),
        } for i,item in enumerate(candidate)]
        if len(json.dumps(preview,ensure_ascii=False))>max_chars:
            break
        bounded.append(rec)
    return bounded

def structure(prompt:str,token:str,records:list[dict[str,str]],source_label:str="independent-source-pool"):
    if not token: raise RuntimeError("HF_TOKEN/HUGGINGFACE_TOKEN missing")
    if len(records)<8 or len({r['domain'] for r in records})<2: raise RuntimeError("source pool too small for safe fallback")
    balanced=_balanced_compact_records(records)
    if len(balanced)<8 or len({r['domain'] for r in balanced})<2: raise RuntimeError("balanced source pool too small for safe fallback")
    model=base.clean(os.getenv("TAYVORIQ_HF_MODEL"),160) or "openai/gpt-oss-120b:cheapest"
    indexed=[]; by_id={}; by_url={}
    for idx,record in enumerate(balanced, start=1):
        sid=f"S{idx:03d}"
        original={**record,"source_id":sid}
        by_id[sid]=original
        by_url[str(record.get('url') or '')]=original
        indexed.append({
            "source_id":sid,
            "domain":record.get("domain"),
            "title":record.get("title"),
            "context":record.get("context"),
            "seen_date":record.get("seen_date"),
            "feed":record.get("feed"),
        })
    blob=json.dumps(indexed,ensure_ascii=False)
    print(json.dumps({"event":"hf_balanced_source_pool","records":len(indexed),"independent_domains":len({r['domain'] for r in indexed}),"chars":len(blob)},ensure_ascii=False))
    schema='''{"candidates":[{"title":"German headline","content_angle":"specific viewer angle","category":"...","trend_scope":"technology_ai|business_economy|world_society|sports|science_future|creator_media|mobility_energy","regional_relevance":"local|germany|europe|global","criteria":{"aktualitaet":0,"viralitaet":0,"tayvoriq_passung":0,"quellenqualitaet":0,"visuell":0},"viral_potential":0,"tayvoriq_fit":0,"novelty_score":0,"series_fit_score":0,"return_viewer_score":0,"follow_conversion_potential":0,"open_loop_potential":0,"proposed_series_id":"","proposed_series_name":"","next_episode_candidate":"","recommended_cta_type":"CURIOSITY|EXPERTISE|COMMUNITY|SERIES|DISCUSSION|IDENTITY","primary_hook":"...","viewer_question":"...","explanation_core":"...","surprise_or_reframe":"...","practical_relevance":"...","follow_reason":"...","open_loop":"","open_loop_status":"NONE|SOFT","next_episode_queue_status":"","cta_type":"CURIOSITY|EXPERTISE|COMMUNITY|SERIES|DISCUSSION|IDENTITY","cta_text":"...","sources":[{"source_id":"S001","supports":"supported fact"},{"source_id":"S002","supports":"supported fact"}],"fallback_editorial_answers":{"what_happened":"...","why_happening":"...","who_is_affected":"...","personal_impact":"...","action_now":"..."}}]}'''
    user=f'''Primary live browser providers are temporarily unavailable. Build TAYVORIQ candidates using ONLY the supplied current source records. Do not browse and do not infer facts beyond title + context. Search across ALL supplied publisher domains, not just the first records.

SOURCE CONTRACT:
- Each candidate must describe ONE coherent current story. Never combine two unrelated headlines, entities, warnings, discoveries or events into one candidate.
- A candidate is valid only with EXACTLY TWO source_id values from DIFFERENT domains that both clearly describe that same story.
- Return source_id values only; NEVER invent or copy URLs.
- Fewer candidates are better than a fabricated cross-source match. Drop a candidate when two independent domains do not support the same story.

V5 CONTRACT:
- Every candidate must include ALL V5 fields from the schema.
- All seven V5 scores are integers 0-100.
- content_angle, primary_hook, viewer_question, explanation_core, surprise_or_reframe, practical_relevance, follow_reason and cta_text must be non-empty.
- CTA type must be one of CURIOSITY, EXPERTISE, COMMUNITY, SERIES, DISCUSSION, IDENTITY.
- CTA text must be topic-specific, naturally mention TAYVORIQ and must not be generic "Bitte abonnieren".
- This fallback may use only NONE or SOFT open loops. Never invent a HARD open loop or queued next episode.

EDITORIAL FALLBACK CONTRACT:
- Provide all five fallback_editorial_answers.
- Each answer must be 5-15 words; together the five answers must total 38-49 words.
- why_happening must state a source-supported cause using wording such as weil, wegen, durch, Grund, Ursache, aufgrund, dadurch or deshalb.
- personal_impact must contain "für dich".
- action_now must start with a concrete verb such as Achte, Prüfe, Sichere, Vergleiche, Aktiviere, Reduziere, Kontaktiere, Beobachte, Exportiere, Wechsle, Plane, Kläre, Nutze, Begrenze or Speichere.

Aim for SIX distinct candidates across technology/AI, business/economy, world/society, science/nature, mobility/energy and sport when the records genuinely support them. Natural-event candidates must be dropped unless the available records support the WHY/HOW. Return up to SIX candidates in German as valid JSON only.\nSCHEMA:\n{schema}\nEditorial ranking context only, never factual source:\n{prompt[:2500]}\nSOURCE RECORDS ({source_label}):\n{blob}'''
    payload={"model":model,"messages":[{"role":"system","content":"Return valid JSON only. Source-bounded transformation; use only supplied source_id values and never invent facts."},{"role":"user","content":user}],"temperature":0,"max_tokens":8000,"stream":False}
    def call()->dict[str,Any]:
        raw,hs=http.post_json(HF_URL,payload,{"Content-Type":"application/json","Authorization":f"Bearer {token}","User-Agent":"tayvoriq-agent-v3-hf"},150)
        print(json.dumps({"event":"provider_success","provider":"huggingface","model":model,"source_label":source_label,"rate_limit":{k:hs[k] for k in http.RATE_HEADERS if k in hs}},ensure_ascii=False)); return raw
    raw=http.retry("huggingface",call,2); data=base.extract_json(provider.content_of(raw)); chunks=[]
    for c in data.get("candidates") or []:
        if not isinstance(c,dict): continue
        raw_sources=[s for s in (c.get("sources") or []) if isinstance(s,dict)]
        resolved=[]
        for s in raw_sources:
            sid=base.clean(s.get("source_id"),20)
            rec=by_id.get(sid)
            if rec is None:
                legacy_url=base.clean(s.get("url"),2000)
                rec=by_url.get(legacy_url)
                sid=str((rec or {}).get("source_id") or "")
            if rec is None: continue
            resolved.append((sid,rec,base.clean(s.get("supports"),600)))
        resolved_domains=[str(rec.get('domain') or domain(str(rec.get('url') or ''))).casefold() for _,rec,_ in resolved]
        if len(resolved)!=2 or len(set(resolved_domains))!=2:
            print(json.dumps({
                "event":"hf_candidate_source_rejected",
                "title":base.clean(c.get('title'),180),
                "source_ids":[base.clean(s.get('source_id'),20) for s in raw_sources],
                "resolved_count":len(resolved),
                "resolved_domains":resolved_domains,
                "reason":"requires_exactly_two_independent_domains",
            },ensure_ascii=False))
            c["sources"]=[]
            continue
        normalized=[]
        for sid,rec,supports in resolved:
            url=base.clean(rec.get("url"),2000); publisher=base.clean(rec.get("domain"),200) or domain(url)
            normalized.append({"source_id":sid,"publisher":publisher,"url":url,"supports":supports or base.clean(rec.get("context"),600)})
            chunks.append({"title":publisher,"uri":url})
        c["sources"]=normalized
    valid_candidates=[
        candidate for candidate in (data.get("candidates") or [])
        if isinstance(candidate,dict) and len(candidate.get("sources") or [])==2
    ]
    # One source-valid candidate produces only two grounding chunks and cannot
    # satisfy the radar's existing minimum grounding contract. Treat that as
    # provider insufficiency so resilience can continue to the next source pool
    # (notably GDELT) without weakening any evidence gate.
    if len(valid_candidates)<2 or len(chunks)<4:
        raise RuntimeError(
            f"HF source contract insufficient for {source_label}: "
            f"valid_candidates={len(valid_candidates)} grounding_chunks={len(chunks)}"
        )
    data["candidates"]=valid_candidates
    return data,chunks,f"huggingface/{model}+{source_label}"
