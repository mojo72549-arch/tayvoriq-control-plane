from __future__ import annotations
import json, os, time
from pathlib import Path
import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http
import tayvoriq_agent_rss_v2 as rss
import tayvoriq_agent_gdelt_v2 as gdelt
import tayvoriq_agent_hf_v2 as hf
base=provider.base
MARKER=Path('/tmp/tayvoriq-research-deferred.json')

def _defer(errors:list[str])->None:
    data={'status':'RESEARCH_DEFERRED','reason':'all live research paths unavailable after bounded retries','errors':errors[-10:],'created_at_epoch':int(time.time())}
    MARKER.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'event':'research_deferred',**data},ensure_ascii=False))

def grounded(prompt:str,gemini_key:str,groq_key:str):
    errors=[]; MARKER.unlink(missing_ok=True)
    if gemini_key:
        try:
            data,chunks,model=http.retry('gemini',lambda:http.gemini_grounded(prompt,gemini_key),3); return data,chunks,model,'gemini'
        except Exception as exc: errors.append(str(exc))
    if groq_key:
        try:
            data,chunks,model=provider.groq_browser_then_structure(prompt,groq_key); return data,chunks,model,'groq'
        except Exception as exc: errors.append(str(exc))
    token=str(os.getenv('HF_TOKEN') or os.getenv('HUGGINGFACE_TOKEN') or '').strip()
    rss_records=[]
    gdelt_records=[]
    try:
        rss_records=rss.source_pool()
    except Exception as exc:
        errors.append('RSS source collection unavailable: '+http.summary(exc))
    # The Groq browser tool can return a too-short dossier while the regular
    # Groq JSON API still works. Structure only verified, URL-bound RSS records
    # with Groq before falling back to a metered HF model.
    if groq_key and rss_records:
        try:
            data,chunks,model=hf.structure(
                prompt,groq_key,rss_records,'multi-publisher-rss',provider_kind='groq')
            return data,chunks,model,'groq_rss'
        except Exception as exc:
            errors.append('Groq/RSS fallback failed: '+http.summary(exc))
    if token and rss_records:
        try:
            data,chunks,model=hf.structure(prompt,token,rss_records,'multi-publisher-rss')
            return data,chunks,model,'huggingface_rss'
        except Exception as exc:
            errors.append('HuggingFace/RSS fallback failed: '+http.summary(exc))
    try:
        gdelt_records=gdelt.source_pool()
    except Exception as exc:
        errors.append('GDELT source collection unavailable: '+http.summary(exc))
    if groq_key and gdelt_records:
        try:
            data,chunks,model=hf.structure(
                prompt,groq_key,gdelt_records,'gdelt-context',provider_kind='groq')
            return data,chunks,model,'groq_gdelt'
        except Exception as exc:
            errors.append('Groq/GDELT fallback failed: '+http.summary(exc))
    if token and gdelt_records:
        try:
            data,chunks,model=hf.structure(prompt,token,gdelt_records,'gdelt-context')
            return data,chunks,model,'huggingface_gdelt'
        except Exception as exc:
            errors.append('HuggingFace/GDELT fallback failed: '+http.summary(exc))

    # The deterministic pool can pair syndicated mirrors and generates generic
    # topic labels/hooks. Editorial quality and source independence are not
    # established, so defer until a verified selection is available.
    errors.append('Deterministic source fallback disabled: syndicated mirrors and generic hooks cannot pass editorial quality')

    _defer(errors); raise RuntimeError('RESEARCH_DEFERRED: '+' | '.join(errors))

def install()->None:
    base.gemini_call=http.gemini_grounded; base.grounded_call=grounded
