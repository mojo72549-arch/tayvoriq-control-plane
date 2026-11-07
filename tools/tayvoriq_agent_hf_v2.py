from __future__ import annotations
import json, os
from collections import defaultdict, deque
from typing import Any
from urllib.parse import urlparse
import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http
from tayvoriq_source_evidence_v1 import validate_pair, source_support, _words, _events, _status, _publisher
base=provider.base
HF_URL="https://router.huggingface.co/v1/chat/completions"

class InsufficientSourceEvidence(RuntimeError):
    """The provider responded successfully but did not return enough corroborated stories."""


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


def _source_pair_score(a: dict, b: dict) -> int:
    """Rank evidence leads, not verified claims. Final validate_pair stays mandatory."""
    domain_a = a.get('domain') or domain(str(a.get('url') or ''))
    domain_b = b.get('domain') or domain(str(b.get('url') or ''))
    if domain_a == domain_b or _publisher(a) == _publisher(b):
        return 0
    ta, tb = str(a.get('title') or ''), str(b.get('title') or '')
    shared_events = _events(ta) & _events(tb)
    if not shared_events or _status(ta) != _status(tb):
        return 0
    shared_title = _words(ta) & _words(tb)
    if not shared_title:
        return 0
    shared_text = _words(ta + ' ' + str(a.get('context') or '')) & _words(tb + ' ' + str(b.get('context') or ''))
    if len(shared_text) < 3:
        return 0
    # Shared headline event + meaningful terms beat globally popular actors
    # with unrelated stories. German audience terms are only a ranking hint.
    local = {'deutschland', 'stuttgart', 'baden', 'württemberg', 'berlin',
             'bundesregierung', 'bosch', 'mercedes', 'porsche', 'volkswagen', 'vw',
             'bahn', 'ig', 'metall', 'industrie'}
    return 12 + len(shared_title) * 4 + min(8, len(shared_text)) + 2 * len(local & shared_text)


def _groq_source_records(records):
    """Keep likely same-story TWO-publisher pairs inside the compact token budget.

    The previous publisher-round-robin picked 21 unrelated stories from a
    240-item pool, making the required two-source verification impossible.
    Every record still carries its own original provenance; validate_pair
    and downstream quality gates remain completely unchanged.
    """
    # Preserve historical source-ID ordering on small pools (including the
    # existing grounded mock contracts); pair-first only fixes large pools.
    if len(json.dumps(records, ensure_ascii=False)) <= 9000:
        return _balanced_compact_records(records, max_chars=9000)
    candidates = list(records)
    pairs = []
    scores = [0] * len(candidates)
    for i, a in enumerate(candidates):
        for j in range(i + 1, len(candidates)):
            score = _source_pair_score(a, candidates[j])
            if score:
                pairs.append((score, i, j))
                scores[i] = max(scores[i], score)
                scores[j] = max(scores[j], score)
    pairs.sort(reverse=True)
    indices = []
    used = set()
    # Prioritize distinct pairs (avoid filling the prompt with one headline).
    for _, i, j in pairs:
        if i in used or j in used:
            continue
        indices.extend((i, j))
        used.update((i, j))
        if len(indices) >= 18:
            break
    # Keep independent discoveries available even if pair candidates are few.
    title_words = [_words(str(row.get('title') or '')) for row in candidates]
    domain_lists = [str(row.get('domain') or domain(str(row.get('url') or ''))) for row in candidates]
    remainder = sorted((i for i in range(len(candidates)) if i not in used),
                       key=lambda i: (-scores[i], -len(title_words[i]), i))
    indices.extend(remainder)
    compact = []
    for idx in indices:
        row = candidates[idx]
        entry = {
            **row,
            'title': base.clean(row.get('title'), 225),
            'context': base.clean(row.get('context'), 260),
            'domain': domain_lists[idx],
        }
        preview = [{
            'source_id': f'S{n + 1:03d}',
            'domain': rec.get('domain'), 'title': rec.get('title'),
            'context': rec.get('context'), 'seen_date': rec.get('seen_date'),
            'feed': rec.get('feed'),
        } for n, rec in enumerate(compact + [entry])]
        if len(json.dumps(preview, ensure_ascii=False)) > 9000:
            break
        compact.append(entry)
        if len(compact) >= 96:
            break
    print(json.dumps({
        'event': 'groq_pair_first_source_selection',
        'matched_independent_pairs': len(pairs),
        'prioritized_pair_records': min(len(used), len(compact)),
        'selected_records': len(compact),
        'selected_domains': len({r.get('domain') for r in compact}),
    }, ensure_ascii=False))
    return compact

def structure(prompt:str,token:str,records:list[dict[str,str]],source_label:str="independent-source-pool",*,provider_kind:str="huggingface",model_override:str=""):
    if provider_kind not in {"huggingface", "groq"}: raise ValueError("UNSUPPORTED_SOURCE_STRUCTURE_PROVIDER")
    if not token: raise RuntimeError(f"{provider_kind.upper()}_API_KEY_MISSING")
    if len(records)<8 or len({r['domain'] for r in records})<2: raise RuntimeError("source pool too small for safe fallback")
    balanced=(_groq_source_records(records) if provider_kind=='groq'
              else _balanced_compact_records(records))
    if len(balanced)<8 or len({r['domain'] for r in balanced})<2: raise RuntimeError("balanced source pool too small for safe fallback")
    model=(base.clean(model_override or os.getenv("TAYVORIQ_GROQ_RSS_MODEL"),160) or "openai/gpt-oss-20b") if provider_kind=="groq" else (base.clean(os.getenv("TAYVORIQ_HF_MODEL"),160) or "openai/gpt-oss-120b:cheapest")
    indexed=[]; by_id={}; by_url={}
    originals = {str(record.get("url") or ""): record for record in records}
    for idx,record in enumerate(balanced, start=1):
        sid=f"S{idx:03d}"
        original={**originals[str(record.get("url") or "")], "source_id":sid}
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
    context_limit=800 if provider_kind=='groq' else 2500
    goal=('Return TWO or THREE complete candidates about current events in Stuttgart, Baden-Württemberg or Germany. '
          'Exclude Europe-only/global events and abstract laboratory research. A German brand alone does not establish German relevance.'
          if provider_kind=='groq' else
          'Aim for SIX distinct candidates across technology/AI, business/economy, world/society, science/nature, mobility/energy and sport when the records genuinely support them.')
    pair_hints = []
    if provider_kind == 'groq':
        for i, a in enumerate(balanced):
            for j in range(i + 1, len(balanced)):
                b = balanced[j]
                score = _source_pair_score(a, b)
                if score and len(pair_hints) < 14:
                    pair_hints.append((score, f'S{i + 1:03d}+S{j + 1:03d}'))
        pair_hints = sorted(pair_hints, reverse=True)[:12]
    pair_note = ('POTENTIAL SAME-EVENT CROSS-PUBLISHER LEADS (not evidence by themselves): ' +
                 ', '.join(x[1] for x in pair_hints) + '. Select only if full original SOURCE CONTRACT passes.'
                 if pair_hints else '')
    user=f'''Primary live browser providers are temporarily unavailable. Build TAYVORIQ candidates using ONLY the supplied current source records. Do not browse and do not infer facts beyond title + context. Search across ALL supplied publisher domains, not just the first records.

SOURCE CONTRACT:
- Each candidate must describe ONE coherent current story. Never combine two unrelated headlines, entities, warnings, discoveries or events into one candidate.
- A candidate is valid only with EXACTLY TWO source_id values from DIFFERENT domains that both clearly describe that same story.
- Return source_id values only; NEVER invent or copy URLs.
- Use a conservative headline whose substantive words and numbers occur in BOTH original records. Unsupported paraphrases are rejected. Source supports will be reconstructed from the original records, not your output.
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

{goal} Natural-event candidates must be dropped unless the available records support the WHY/HOW. Return complete candidates in German as valid JSON only.\nSCHEMA:\n{schema}\nEditorial ranking context only, never factual source:\n{prompt[:context_limit]}\n{pair_note}\nSOURCE RECORDS ({source_label}):\n{blob}'''
    payload={"model":model,"messages":[{"role":"system","content":"Return valid JSON only. Source-bounded transformation; use only supplied source_id values and never invent facts."},{"role":"user","content":user}],"temperature":0,"stream":False}
    if provider_kind=="groq":
        payload.update({"max_completion_tokens":4000,"reasoning_effort":"low",
                        "response_format":{"type":"json_object"}})
    else:
        payload["max_tokens"]=8000
    def call()->dict[str,Any]:
        if provider_kind=="groq":
            raw=provider.post_groq(payload,token,timeout=150)
            print(json.dumps({"event":"provider_success","provider":"groq_rss","model":model,"source_label":source_label},ensure_ascii=False)); return raw
        raw,hs=http.post_json(HF_URL,payload,{"Content-Type":"application/json","Authorization":f"Bearer {token}","User-Agent":"tayvoriq-agent-v3-hf"},150)
        print(json.dumps({"event":"provider_success","provider":"huggingface","model":model,"source_label":source_label,"rate_limit":{k:hs[k] for k in http.RATE_HEADERS if k in hs}},ensure_ascii=False)); return raw
    raw=(call() if provider_kind=="groq" else http.retry("huggingface",call,2)); data=base.extract_json(provider.content_of(raw)); chunks=[]
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
        reasons = validate_pair(c, [rec for _,rec,_ in resolved])
        if reasons:
            print(json.dumps({
                "event":"hf_candidate_source_rejected",
                "title":base.clean(c.get('title'),180),
                "source_ids":[base.clean(s.get('source_id'),20) for s in raw_sources],
                "resolved_count":len(resolved),
                "resolved_domains":resolved_domains,
                "reason": reasons,
            },ensure_ascii=False))
            c["sources"]=[]
            continue
        normalized=[]
        for sid,rec,supports in resolved:
            url=base.clean(rec.get("url"),2000); publisher=base.clean(rec.get("domain"),200) or domain(url)
            original_support, digest = source_support(rec)
            normalized.append({"source_id":sid,"publisher":publisher,"url":url,
                               "supports":original_support,"source_record_sha256":digest,
                               "support_origin":"retrieved_source_title_and_context"})
            chunks.append({"title":publisher,"uri":url})
        c["sources"]=normalized
    valid_candidates=[]
    seen_pairs, seen_titles = set(), set()
    for candidate in data.get('candidates') or []:
        if not isinstance(candidate, dict) or len(candidate.get('sources') or []) != 2:
            continue
        pair = tuple(sorted(source['url'] for source in candidate['sources']))
        title = ' '.join(str(candidate.get('title') or '').casefold().split())
        if pair in seen_pairs or title in seen_titles:
            continue
        seen_pairs.add(pair)
        seen_titles.add(title)
        valid_candidates.append(candidate)
    unique_chunks = {}
    for candidate in valid_candidates:
        for source in candidate['sources']:
            unique_chunks[source['url']] = {'title': source['publisher'], 'uri': source['url']}
    chunks = list(unique_chunks.values())
    # One source-valid candidate produces only two grounding chunks and cannot
    # satisfy the radar's existing minimum grounding contract. Treat that as
    # provider insufficiency so resilience can continue to the next source pool
    # (notably GDELT) without weakening any evidence gate.
    if len(valid_candidates)<2 or len(chunks)<4:
        raise InsufficientSourceEvidence(
            f"HF source contract insufficient for {source_label}: "
            f"valid_candidates={len(valid_candidates)} grounding_chunks={len(chunks)}"
        )
    data["candidates"]=valid_candidates
    return data,chunks,f"{provider_kind}/{model}+{source_label}"
