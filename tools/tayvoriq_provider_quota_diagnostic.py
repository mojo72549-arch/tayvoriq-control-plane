"""One owner-bound, small Gemini request; publish only allowlisted quota diagnostics."""
import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

MODEL = 'gemini-3.6-flash'


def quota_details(payload):
    result={'tier_hint':'unknown','quota_metrics':[],'retry_after_seconds':None}
    error=payload.get('error') if isinstance(payload,dict) else {}
    for detail in (error or {}).get('details',[]):
        if not isinstance(detail,dict):
            continue
        if str(detail.get('@type','')).endswith('QuotaFailure'):
            for row in detail.get('violations',[])[:8]:
                metric=str(row.get('quotaMetric',''))
                quota=str(row.get('quotaId',''))
                if not re.fullmatch(r'[A-Za-z0-9_./-]{1,180}',metric) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,180}',quota):
                    continue
                value=str(row.get('quotaValue',''))
                result['quota_metrics'].append({'metric':metric,'quota_id':quota,
                    'limit':int(value) if value.isdigit() else None,
                    'kind':'daily' if 'perday' in quota.lower() else 'minute' if 'perminute' in quota.lower() else 'other'})
                if 'free' in (metric+' '+quota).lower():
                    result['tier_hint']='free'
        if str(detail.get('@type','')).endswith('RetryInfo'):
            match=re.fullmatch(r'(\d+(?:\.\d+)?)s',str(detail.get('retryDelay','')))
            if match:
                result['retry_after_seconds']=min(86400,float(match[1]))
    return result


def diagnose(control,owner,*,env=os.environ,clock=time.time,request=urlopen):
    now=clock()
    report={'schema':'tayvoriq-provider-quota-diagnostic-v1','provider':'gemini',
        'selection_id':control.get('selection_id'),'checked_at':datetime.fromtimestamp(now,timezone.utc).isoformat(),
        'diagnostic_run_id':str(env.get('GITHUB_RUN_ID','')),'calls':0,'max_output_tokens':64,
        'state':'NOT_RUN','http_status':None}
    if (control.get('schema')!='tayvoriq-provider-quota-diagnostic-request-v1'
            or not re.fullmatch(r'\d{8}-(morning|evening)-agentv2-c[0-9a-f]{8}',str(control.get('selection_id','')))
            or owner.get('selection_id')!=control.get('selection_id')
            or not 0<=now-float(control.get('requested_at_epoch') or 0)<=300):
        report['reason']='REQUEST_EXPIRED_OR_OWNER_CHANGED'
        return report
    key=str(env.get('GEMINI_API_KEY','')).strip()
    if not key:
        report['reason']='KEY_NOT_CONFIGURED'
        return report
    model=str(env.get('TAYVORIQ_TREND_MODEL') or MODEL)
    if not re.fullmatch(r'gemini-[A-Za-z0-9.-]{1,80}',model):
        report['reason']='INVALID_MODEL_CONFIGURATION'
        return report
    report['model']=model
    body={'contents':[{'role':'user','parts':[{'text':'Prüfe das heutige Datum per Google-Suche und antworte nur mit OK.'}]}],
          'tools':[{'google_search':{}}],'generationConfig':{'maxOutputTokens':64}}
    probe=Request(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
    report['calls']=1
    try:
        with request(probe,timeout=30) as response:
            payload=json.load(response)
        report.update(state='AVAILABLE',http_status=200,
                      total_tokens=(payload.get('usageMetadata') or {}).get('totalTokenCount'),
                      grounding_confirmed=any((c.get('groundingMetadata') or {}).get('groundingChunks') for c in payload.get('candidates',[])))
    except HTTPError as error:
        report.update(state='QUOTA_BLOCKED' if error.code==429 else 'PROVIDER_ERROR',http_status=error.code)
        try:
            report.update(quota_details(json.loads(error.read(64000))))
        except (ValueError,TypeError):
            report['tier_hint']='unknown'
    except (OSError,ValueError):
        report.update(state='UNAVAILABLE',reason='NETWORK_OR_RESPONSE_ERROR')
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    control=json.loads(Path(args.request).read_text())
    owner=json.loads(Path('state/tayvoriq-control-center-research.json').read_text())
    report=diagnose(control,owner)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
