from __future__ import annotations
import json, os, re, unicodedata
from collections import defaultdict, deque
from typing import Any
from urllib.parse import urlparse
import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http
import tayvoriq_agent_rss_v2 as rss
from tayvoriq_regional_relevance import evaluate as evaluate_regional_relevance
from tayvoriq_source_evidence_v1 import validate_pair, source_support, claim_terms, _words, _events, _status, _publisher
base=provider.base
HF_URL="https://router.huggingface.co/v1/chat/completions"
EDITORIAL_RESCAN = "\n\nAUTOMATIC REGIONAL CONTRACT RESCAN:"
GROWTH_RESCAN = "\n\nAUTOMATIC BELOW-MINIMUM RESCAN:"
RESCAN_MARKERS = (EDITORIAL_RESCAN, GROWTH_RESCAN)

class InsufficientSourceEvidence(RuntimeError):
    """The provider responded successfully but did not return enough corroborated stories."""

class InsufficientFeedEvidence(InsufficientSourceEvidence):
    """No model was called because the discovery snippets could not establish two stories."""


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
    shared_title = claim_terms(ta) & claim_terms(tb)
    if not shared_title:
        return 0
    shared_text = claim_terms(ta + ' ' + str(a.get('context') or '')) & claim_terms(tb + ' ' + str(b.get('context') or ''))
    if len(shared_text) < 3:
        return 0
    # Shared headline event + meaningful terms beat globally popular actors
    # with unrelated stories. German audience terms are only a ranking hint.
    local = {'deutschland', 'stuttgart', 'baden', 'württemberg', 'berlin',
             'bundesregierung', 'bosch', 'mercedes', 'porsche', 'volkswagen', 'vw',
             'bahn', 'ig', 'metall', 'industrie'}
    return 12 + len(shared_title) * 4 + min(8, len(shared_text)) + 2 * len(local & shared_text)


def corroborated_headline(a: dict, b: dict) -> str:
    """Use a publisher's headline or standalone lead clause with joint support."""
    for record in (a, b):
        title = base.clean(record.get('title'))
        if 0 < len(title) <= 180 and not validate_pair({'title': title}, [a, b]):
            return title
    for record in (a, b):
        title = base.clean(record.get('title'))
        clauses = re.split(r":\s+|\s+[–—]\s+|;\s+", title)
        for clause in clauses:
            if (len(clauses) > 1 and 24 <= len(clause) <= 150 and len(_words(clause)) >= 3
                    and _status(clause) == _status(title) and _events(clause) == _events(title)
                    and not validate_pair({'title': clause}, [a, b])):
                return clause
    # Publisher summaries often contain a complete, mutually supported lead
    # while their display headlines add a quotation or unrelated context.
    for record in (a, b):
        headline = str(record.get('title') or '')
        context = base.clean(record.get('context'))
        for sentence in re.split(r'(?<=[.!?])\s+', context)[:2]:
            lead = sentence.rstrip('.')
            if (sentence.endswith('.') and 24 <= len(lead) <= 160 and len(_words(lead)) >= 4
                    and _events(lead) == _events(headline) and _status(lead) == _status(headline)
                    and not validate_pair({'title': lead}, [a, b])):
                return lead
    return ''


def distinct_headlines(left, right):
    left_terms, right_terms = claim_terms(left), claim_terms(right)
    shared = left_terms & right_terms
    same_topic = (_events(left) == _events(right) and len(shared) >= 3
                  and len(shared) / min(len(left_terms), len(right_terms)) >= .70)
    return not same_topic


def _independent_headline_pairs(vetted_pairs: dict) -> dict:
    """Select separate reporting pairs and avoid ranking alternate wording twice."""
    entries = list(vetted_pairs.items())

    for index, (first, first_title) in enumerate(entries):
        for second, second_title in entries[index + 1:]:
            used = set(first) | set(second)
            if len(used) != 4 or not distinct_headlines(first_title, second_title):
                continue
            chosen = {first: first_title, second: second_title}
            for pair, title in entries:
                if not used.intersection(pair) and all(distinct_headlines(title, prior) for prior in chosen.values()):
                    chosen[pair] = title
                    break
            return chosen
    return {}


def _headline_presentation_key(title) -> str:
    value = unicodedata.normalize("NFC", base.clean(title))
    # Only typography between textual clauses changes. Hyphenated words,
    # decimal punctuation, negation and signs attached to numbers stay exact.
    value = re.sub(r"(?<=\w)(?:\s+[–—-]\s+|:\s+)(?=[^\W\d_])", " ", value)
    return " ".join(value.split())


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
                if corroborated_headline(a, candidates[j]):
                    score += 100
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
    schema='''{"candidates":[{"title":"German headline","content_angle":"specific viewer angle","category":"...","trend_scope":"technology_ai|business_economy|world_society|sports|science_future|creator_media|mobility_energy","regional_relevance":"local|germany|europe|global","criteria":{"aktualitaet":<integer 0-100>,"viralitaet":<integer 0-100>,"tayvoriq_passung":<integer 0-100>,"quellenqualitaet":<integer 0-100>,"visuell":<integer 0-100>},"viral_potential":<integer 0-100>,"tayvoriq_fit":<integer 0-100>,"novelty_score":<integer 0-100>,"series_fit_score":<integer 0-100>,"return_viewer_score":<integer 0-100>,"follow_conversion_potential":<integer 0-100>,"open_loop_potential":<integer 0-100>,"proposed_series_id":"","proposed_series_name":"","next_episode_candidate":"","recommended_cta_type":"CURIOSITY|EXPERTISE|COMMUNITY|SERIES|DISCUSSION|IDENTITY","primary_hook":"...","viewer_question":"...","explanation_core":"...","surprise_or_reframe":"...","practical_relevance":"...","follow_reason":"...","open_loop":"","open_loop_status":"NONE|SOFT","next_episode_queue_status":"","cta_type":"CURIOSITY|EXPERTISE|COMMUNITY|SERIES|DISCUSSION|IDENTITY","cta_text":"...","sources":[{"source_id":"S001","supports":"supported fact"},{"source_id":"S002","supports":"supported fact"}],"fallback_editorial_answers":{"what_happened":"...","why_happening":"...","who_is_affected":"...","personal_impact":"...","action_now":"..."}}]}'''
    context_limit=800 if provider_kind=='groq' else 2500
    editorial_context = prompt[:context_limit]
    rescan_marker = next((marker for marker in RESCAN_MARKERS if marker in prompt), "")
    if rescan_marker:
        editorial_context += rescan_marker + prompt.split(rescan_marker, 1)[1][:1700]
    goal=('Return TWO or THREE complete candidates about current events in Stuttgart, Baden-Württemberg or Germany. '
          'Exclude Europe-only/global events and abstract laboratory research. A German brand alone does not establish German relevance.'
          if provider_kind=='groq' else
          'Aim for SIX distinct candidates across technology/AI, business/economy, world/society, science/nature, mobility/energy and sport when the records genuinely support them.')
    pair_hints = []
    vetted_pairs = {}
    source_bound = source_label in {'multi-publisher-rss', 'rss-article-context', 'rss-gdelt-context'}
    if provider_kind == 'groq' or source_bound:
        source_ids = list(by_id)
        for i, left in enumerate(source_ids):
            for right in source_ids[i + 1:]:
                a, b = by_id[left], by_id[right]
                score = _source_pair_score(a, b)
                if score and len(pair_hints) < 14:
                    pair_hints.append((score, f'{left}+{right}'))
                if score:
                    title = corroborated_headline(a, b)
                    if title:
                        vetted_pairs[left, right] = title
        pair_hints = sorted(pair_hints, reverse=True)[:12]
    pair_note = ('POTENTIAL SAME-EVENT CROSS-PUBLISHER LEADS (not evidence by themselves): ' +
                 ', '.join(x[1] for x in pair_hints) + '. Select only if full original SOURCE CONTRACT passes.'
                 if pair_hints else '')
    if source_bound:
        marker = "\nPreviously drafted source headlines: "
        if rescan_marker and marker in prompt:
            try:
                previous = json.loads(prompt.rsplit(marker, 1)[1])
            except ValueError:
                previous = []
            if isinstance(previous, list):
                previous = {title.casefold() for title in previous if isinstance(title, str)}
                vetted_pairs = dict(sorted(vetted_pairs.items(), key=lambda pair: pair[1].casefold() in previous))
        selected_pairs = _independent_headline_pairs(vetted_pairs)
        if not selected_pairs:
            diagnostics = []
            for _, ids in pair_hints[:5]:
                pair = [by_id[sid] for sid in ids.split("+")]
                titles = [record["title"] for record in pair]
                diagnostics.append({"titles": titles, "checks": validate_pair({"title": titles[0]}, pair)})
            print(json.dumps({"event": "insufficient_corroborated_stories", "pool": source_label,
                              "corroborated_titles": list(dict.fromkeys(vetted_pairs.values()))[:8],
                              "unverified_leads": diagnostics}, ensure_ascii=False))
            raise InsufficientFeedEvidence(
                f"HF source contract insufficient for {source_label}: "
                f"corroborated_headlines={len(set(vetted_pairs.values()))} separate_source_pairs=False"
            )
        vetted_pairs = selected_pairs
    exact_titles = len({title.casefold() for title in vetted_pairs.values()}) >= 2
    print(json.dumps({"event":"source_headline_preflight","source_label":source_label,
                      "corroborated_headlines":len(set(vetted_pairs.values())),
                      "strict_allowlist":exact_titles},ensure_ascii=False))
    if exact_titles:
        allowed_ids = {source_id for pair in vetted_pairs for source_id in pair}
        indexed = [item for item in indexed if item['source_id'] in allowed_ids]
        if rescan_marker and source_bound and source_label == 'multi-publisher-rss':
            originals = [by_id[item['source_id']] for item in indexed]
            enriched = rss.enrich_evidence(originals)
            enriched_count = 0
            for item, original, article in zip(indexed, originals, enriched):
                if article != original:
                    by_id[item['source_id']] = article
                    by_url[article['url']] = article
                    # The editorial normalizer consumes up to 600 characters of title and context.
                    item['context'] = base.clean(article.get('context'), 600 - len(article['title']) - 1)
                    enriched_count += 1
            print(json.dumps({"event": "editorial_rescan_article_evidence", "updated_records": enriched_count}))
        allowlist = [{'source_ids': list(pair), 'title': title} for pair, title in vetted_pairs.items()]
        pair_note = ('PICK ONLY FROM THESE CORROBORATED HEADLINES. Copy the title and its two source IDs '
                     'exactly. Only propose an angle grounded in that pair. Never add actors, outcomes, '
                     'numbers or locations from other stories. Draft one complete candidate per eligible pair. '
                     'Skip a pair only when the evidence or regional scope is insufficient.\n'
                     + json.dumps(allowlist, ensure_ascii=False))
    blob = json.dumps(indexed, ensure_ascii=False)
    print(json.dumps({"event":"source_prompt_budget","records":len(indexed),
                      "independent_domains":len({r['domain'] for r in indexed}),"chars":len(blob)},ensure_ascii=False))
    policy = ""
    if source_bound:
        policy = """DE_LOCAL_RELEVANCE_V2: supply a regional_scorecard for each candidate, in addition to the schema.
Use the two actual source_id keys for evidence, each with a verbatim 4-18 word excerpt showing the central event or consequence.
regional_scorecard = {"evidence":{"<first ID>":"original quote","<second ID>":"original quote"},
"ratings":{"consequence":[YT,TT,"German reason"],"proximity":[YT,TT,"reason"],"recognition":[YT,TT,"reason"],
"timeliness":[YT,TT,"reason"],"explanation":[YT,TT,"reason"],"resolution":[YT,TT,"reason"],"continuity":[YT,TT,"reason"]},
"platform_fit":{"youtube":"specific YouTube fit","tiktok":"specific TikTok fit"}}.
YT and TT are independently assessed integers 0 to 5, not text. 0 absent, 1 weak, 3 concrete, 5 strong and evidenced.
For each row give a specific 4-12 word reason grounded in this story. Rate in order: consequences for work/money/daily life,
German audience proximity, immediately recognizable actor/place, new dated development, explanation beyond the headline,
a question that can be answered now, and returning audience value. Do not predict view counts. Give a distinct fit reason
for each platform. Never increase scores to satisfy a quota. Preserve uncertainty, including when a study estimates an effect.
For why_happening, explain the documented decision or mechanism from the reports, without inventing a motive."""
    user=f'''Primary live browser providers are temporarily unavailable. Build TAYVORIQ candidates using ONLY the supplied current source records. Do not browse and do not infer facts beyond title + context. Search across ALL supplied publisher domains, not just the first records.

SOURCE CONTRACT:
- Each candidate must describe ONE coherent current story. Never combine two unrelated headlines, entities, warnings, discoveries or events into one candidate.
- A candidate is valid only with EXACTLY TWO source_id values from DIFFERENT domains that both clearly describe that same story.
- Return source_id values only; NEVER invent or copy URLs.
- Use a conservative headline whose substantive words and numbers occur in BOTH original records. Unsupported paraphrases are rejected. Source supports will be reconstructed from the original records, not your output.
- Fewer candidates are better than a fabricated cross-source match. Drop a candidate when two independent domains do not support the same story.

V5 CONTRACT:
- Every candidate must include ALL V5 fields from the schema.
- Return all five criteria and all seven V5 scores as JSON integers on a 0-100 scale.
- Score each independently from the paired evidence. Assess freshness from dates, audience interest from
  the specific change, channel fit from the audience consequence, source quality from provenance and
  visual feasibility from the proposed subject. Low scores are valid; do not inflate a score to qualify.
- Choose ONE literal trend_scope from the schema alternatives.
- content_angle, primary_hook, viewer_question, explanation_core, surprise_or_reframe, practical_relevance, follow_reason and cta_text must be non-empty.
- The German explanation has enough depth for a video. Use 9-16 words for primary_hook, 7-14 for viewer_question,
  17-32 for explanation_core, 12-22 for surprise_or_reframe, 10-18 for practical_relevance and 10-18 for follow_reason.
- Give the reframe a distinct, supported detail or a different consequence with at least three new substantive terms.
  Use the original evidence to explain the mechanism, uncertainty and what it means for the audience.
- Set regional_relevance to the literal value "local" for the Stuttgart/Baden-Württemberg area or "germany" for a German national story.
- CTA type must be one of CURIOSITY, EXPERTISE, COMMUNITY, SERIES, DISCUSSION, IDENTITY.
- CTA text must be topic-specific, naturally mention TAYVORIQ and must not be generic "Bitte abonnieren".
- This fallback may use only NONE or SOFT open loops. Never invent a HARD open loop or queued next episode.

{base.CINEMATIC_BRIEF_INSTRUCTIONS}

EDITORIAL FALLBACK CONTRACT:
- Provide all five fallback_editorial_answers.
- Each answer must be 5-15 words; together the five answers must total 38-49 words.
- Aim for about nine words per answer. Count all five answers together before returning them.
- why_happening must state a source-supported cause using wording such as weil, wegen, durch, Grund, Ursache, aufgrund, dadurch or deshalb.
- Use a concrete phrase from the paired reports in why_happening. Never guess an actor's motive or present a possible background factor as the cause.
- why_happening must add at least three substantive words beyond what_happened.
- personal_impact must contain "für dich".
- personal_impact must add at least three substantive words beyond what_happened and who_is_affected. Explain a concrete different consequence for the viewer using the paired evidence.
- action_now must start with a concrete verb such as Achte, Prüfe, Sichere, Vergleiche, Aktiviere, Reduziere, Kontaktiere, Beobachte, Exportiere, Wechsle, Plane, Kläre, Nutze, Begrenze or Speichere.

{policy}
{goal} Natural-event candidates must be dropped unless the available records support the WHY/HOW. Return complete candidates in German as valid JSON only.\nSCHEMA:\n{schema}\nEditorial ranking context only, never factual source:\n{editorial_context}\n{pair_note}\nSOURCE RECORDS ({source_label}):\n{blob}'''
    payload={"model":model,"messages":[{"role":"system","content":"Return valid JSON only. Source-bounded transformation; use only supplied source_id values and never invent facts."},{"role":"user","content":user}],"temperature":0,"stream":False}
    if provider_kind=="groq":
        payload.update({"max_completion_tokens":4000,"response_format":{"type":"json_object"}})
        if model.startswith("openai/gpt-oss-"):
            payload["reasoning_effort"] = "low"
    else:
        payload["max_tokens"]=8000
    interactive=bool(os.getenv('TAYVORIQ_RESEARCH_SELECTION_ID'))
    timeout=28 if interactive else 150
    def call()->dict[str,Any]:
        if provider_kind=="groq":
            raw=provider.post_groq(payload,token,timeout=timeout)
            print(json.dumps({"event":"provider_success","provider":"groq_rss","model":model,"source_label":source_label},ensure_ascii=False)); return raw
        raw,hs=http.post_json(HF_URL,payload,{"Content-Type":"application/json","Authorization":f"Bearer {token}","User-Agent":"tayvoriq-agent-v3-hf"},timeout)
        print(json.dumps({"event":"provider_success","provider":"huggingface","model":model,"source_label":source_label,"rate_limit":{k:hs[k] for k in http.RATE_HEADERS if k in hs}},ensure_ascii=False)); return raw
    raw=(call() if provider_kind=="groq" or interactive else http.retry("huggingface",call,2)); data=base.extract_json(provider.content_of(raw)); chunks=[]
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
        reasons = []
        if exact_titles:
            binding = vetted_pairs.get(tuple(sorted(sid for sid, _, _ in resolved)))
            if not binding or _headline_presentation_key(c.get('title')) != _headline_presentation_key(binding):
                reasons.append('candidate_does_not_match_preverified_headline_pair')
            else:
                c['title'] = binding
        reasons.extend(validate_pair(c, [rec for _,rec,_ in resolved]))
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
                               "support_origin":"retrieved_source_title_and_context",
                               "publisher_headline":base.clean(rec.get("title"),500),
                               "source_date":base.clean(rec.get("seen_date"),100),
                               "declared_origin":base.clean(rec.get("origin"),180)})
            chunks.append({"title":publisher,"uri":url})
        c["sources"]=normalized
        if source_bound:
            c["_retrieved_regional_assessment"] = evaluate_regional_relevance(c.get("regional_scorecard"), normalized)
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
