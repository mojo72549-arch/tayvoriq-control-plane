from __future__ import annotations
import json, urllib.parse, urllib.request
from urllib.parse import urlparse
import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http
base=provider.base
GDELT_URL="https://api.gdeltproject.org/api/v2/context/context"

def domain(url:str)->str:
    try:
        h=urlparse(url).netloc.casefold().split(":",1)[0]; return h[4:] if h.startswith("www.") else h
    except Exception: return ""

def source_pool()->list[dict[str,str]]:
    queries=["(wildfire OR earthquake OR volcano OR flood OR storm OR heatwave)","(AI OR technology OR cyber)","(Germany OR Stuttgart OR transport OR rail)","(economy OR prices OR energy OR automotive)","(sports OR football OR athletics) Germany"]
    out=[]; seen=set()
    for query in queries:
        params=urllib.parse.urlencode({"query":query,"mode":"artlist","maxrecords":75,"format":"json","timespan":"24H","sort":"DateDesc"})
        req=urllib.request.Request(f"{GDELT_URL}?{params}",headers={"User-Agent":"tayvoriq-agent-v3"})
        try:
            with urllib.request.urlopen(req,timeout=30) as resp: payload=json.loads(resp.read().decode())
        except Exception as exc:
            print(json.dumps({"event":"gdelt_query_failed","query":query,"error":http.summary(exc)},ensure_ascii=False)); continue
        for item in payload.get("articles") or []:
            if not isinstance(item,dict): continue
            url=base.clean(item.get("url"),2000); title=base.clean(item.get("title"),500); context=base.clean(item.get("context") or item.get("snippet"),1600); host=base.clean(item.get("domain"),200) or domain(url)
            if not url.startswith(("https://","http://")) or not title or not context or not host or url in seen: continue
            if any(marker in url.casefold() for marker in base.BLOCKED_SOURCE_MARKERS): continue
            seen.add(url); out.append({"title":title,"context":context,"url":url,"domain":host,"seen_date":base.clean(item.get("seendate"),80),"source_country":base.clean(item.get("sourcecountry"),80),"language":base.clean(item.get("language"),80)})
    print(json.dumps({"event":"gdelt_context_pool","records":len(out),"independent_domains":len({x['domain'] for x in out})},ensure_ascii=False)); return out[:100]
