from __future__ import annotations
import json, os, time
from pathlib import Path
import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http
import tayvoriq_agent_gdelt_v2 as gdelt
import tayvoriq_agent_hf_v2 as hf
base=provider.base
MARKER=Path('/tmp/tayvoriq-research-deferred.json')

def _defer(errors:list[str])->None:
    data={'status':'RESEARCH_DEFERRED','reason':'all live research paths unavailable after bounded retries','errors':errors[-8:],'created_at_epoch':int(time.time())}
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
    try:
        token=str(os.getenv('HF_TOKEN') or os.getenv('HUGGINGFACE_TOKEN') or '').strip(); records=gdelt.source_pool(); data,chunks,model=hf.structure(prompt,token,records); return data,chunks,model,'huggingface_gdelt'
    except Exception as exc: errors.append('HuggingFace/GDELT fallback failed: '+http.summary(exc))
    _defer(errors); raise RuntimeError('RESEARCH_DEFERRED: '+' | '.join(errors))

def install()->None:
    base.gemini_call=http.gemini_grounded; base.grounded_call=grounded
