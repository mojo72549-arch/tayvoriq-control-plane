from __future__ import annotations
import json, os, random, time, urllib.error, urllib.request
from typing import Any, Callable
import tayvoriq_agent_trend_provider_v3 as provider
base=provider.base
TRANSIENT={408,409,425,429,500,502,503,504,520,522,524}
RATE_HEADERS=("retry-after","x-ratelimit-limit-requests","x-ratelimit-limit-tokens","x-ratelimit-remaining-requests","x-ratelimit-remaining-tokens","x-ratelimit-reset-requests","x-ratelimit-reset-tokens")

def is_transient(exc:Exception)->bool:
    if isinstance(exc,urllib.error.HTTPError): return int(exc.code) in TRANSIENT
    t=f"{type(exc).__name__}: {exc}".casefold()
    return any(x in t for x in ("429","too many requests","rate limit","timeout","timed out"," 500"," 502"," 503"," 504"," 520"," 522"," 524","temporarily unavailable","connection reset"))

def rate_headers(exc:Exception)->dict[str,str]:
    if not isinstance(exc,urllib.error.HTTPError): return {}
    h=exc.headers or {}; return {k:str(h.get(k)) for k in RATE_HEADERS if h.get(k)}

def summary(exc:Exception)->str:
    if isinstance(exc,urllib.error.HTTPError):
        r=rate_headers(exc); return f"HTTP {int(exc.code)} {exc.reason}"+(f" rate={json.dumps(r,sort_keys=True)}" if r else "")
    return f"{type(exc).__name__}: {exc}"

def retry(label:str,call:Callable[[],Any],attempts:int)->Any:
    errors=[]
    for i in range(attempts):
        try: return call()
        except Exception as exc:
            transient=is_transient(exc); errors.append(summary(exc))
            print(json.dumps({"event":"provider_attempt_failed","provider":label,"attempt":i+1,"attempts":attempts,"transient":transient,"error":summary(exc),"rate_limit":rate_headers(exc)},ensure_ascii=False))
            if not transient or i+1>=attempts: break
            ra=(exc.headers or {}).get("Retry-After") if isinstance(exc,urllib.error.HTTPError) else None
            try: delay=min(60.0,max(8.0,float(ra))) if ra else min(60.0,8.0*(2**i)+random.uniform(.5,2.0))
            except Exception: delay=min(60.0,8.0*(2**i)+random.uniform(.5,2.0))
            print(json.dumps({"event":"provider_backoff","provider":label,"seconds":round(delay,2)},ensure_ascii=False)); time.sleep(delay)
    raise RuntimeError(f"{label} failed after {len(errors)} attempt(s): "+" | ".join(errors))

def post_json(url:str,payload:dict[str,Any],headers:dict[str,str],timeout:int)->tuple[dict[str,Any],dict[str,str]]:
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers,method="POST")
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        hs={str(k).lower():str(v) for k,v in resp.headers.items()}; return json.loads(resp.read().decode()),hs

def gemini_grounded(prompt:str,key:str):
    configured=base.clean(os.getenv("TAYVORIQ_TREND_MODEL"),100) or "gemini-3.6-flash"; models=[]
    for m in (configured,"gemini-3.6-flash","gemini-3.5-flash"):
        if m not in models: models.append(m)
    non=[]
    for model in models:
        payload={"contents":[{"role":"user","parts":[{"text":prompt}]}],"tools":[{"google_search":{}}],"generationConfig":{"maxOutputTokens":12000}}
        try:
            raw,hs=post_json(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",payload,{"Content-Type":"application/json","x-goog-api-key":key,"User-Agent":"tayvoriq-agent-v3"},120)
            c=(raw.get("candidates") or [{}])[0]; parts=((c.get("content") or {}).get("parts") or []); text="\n".join(str(p.get("text") or "") for p in parts if isinstance(p,dict)).strip(); data=base.extract_json(text); chunks=[]
            for ch in ((c.get("groundingMetadata") or {}).get("groundingChunks") or []):
                web=ch.get("web") if isinstance(ch,dict) else None
                if isinstance(web,dict) and web.get("uri"): chunks.append({"title":base.clean(web.get("title"),500),"uri":base.clean(web.get("uri"),2000)})
            print(json.dumps({"event":"provider_success","provider":"gemini","model":model,"rate_limit":{k:hs[k] for k in RATE_HEADERS if k in hs}},ensure_ascii=False)); return data,chunks,model
        except Exception as exc:
            if is_transient(exc): raise
            non.append(f"{model}: {summary(exc)}")
    raise RuntimeError("Gemini grounded scan failed: "+" | ".join(non))
