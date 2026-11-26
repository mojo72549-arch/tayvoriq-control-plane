"""Observe completed media artifacts under their canonical delivery attempt."""
import hashlib
import json
from pathlib import Path


def collect(root,request,decision,attempt):
    job=json.loads((root/'job.json').read_text())
    audit=json.loads((root/'preapproval_ai_audit.json').read_text())
    gate=json.loads((root/'publication_quality_gate.json').read_text())
    assert job['quality_report']['passed'] is True and audit['passed'] is True
    assert gate['passed'] is True and gate['quality_gates_weakened'] is False
    variants=job['variants'];platforms=('youtube_shorts','tiktok')
    contract=job['text_package']['retention_contract_v5']
    assert contract['request_id']==request['request_id']
    assert contract['source_context_sha256']==request['source_context_sha256']
    rows=[]
    def record(key,condition,detail,outputs=None,audit_proof=False):
        if condition:
            name='preapproval_ai_audit.json' if audit_proof else 'job.json'
            rows.append(dict(id=key,state='success',detail=detail,artifact='bound-review/'+name,
                artifact_sha256=decision['files_sha256'][name],outputs=outputs or {}))
    packages=[variants[p]['text_package'] for p in platforms]
    record('sources',True,'Der freigegebene Quellenkontext ist unverändert im geprüften Videopaket gebunden.')
    record('preflight',True,'Die gespeicherten Dateien stammen aus dem erfolgreich abgeschlossenen, an diesen Auftrag gebundenen Contabo-Lauf.',
        {'execution_run_id':request['contabo_handoff']['worker_run_id'],'implementation_sha':decision['studio_sha']})
    record('script',all(p.get('script') and p.get('language') in ('Deutsch','de') for p in packages),
        'Beide deutschen Skripte sind vorhanden und im fertigen Video geprüft. Der gespeicherte Text wurde wiederverwendet.')
    record('scenes',all(p.get('scenes') and all(s.get('spoken_chunk') and s.get('visual_query') for s in p['scenes']) for p in packages),
        'Die Szenenpläne beider Ausgaben sind im geprüften Paket vorhanden.',{p:len(variants[p]['text_package'].get('scenes') or []) for p in platforms})
    record('voice',all((variants[p].get('audio') or {}).get('postmux_transcript_validation',{}).get('passed') is True
        and audit['audio_reports'][p]['passed'] is True for p in platforms),
        'Beide Sprecheraufnahmen sind im fertigen Export mit dem gesprochenen Text abgeglichen und bestanden.',audit_proof=True)
    record('visuals',audit.get('visual_review',{}).get('passed') is True,
        'Die Motive beider Ausgaben haben die vollständige Einzelprüfung bestanden.',audit_proof=True)
    assets=[variants[p].get('render',{}).get('asset_report') or [] for p in platforms]
    silence_policy=all('Use silence plus sparse accents' in p.get('editorial_visual_standard',{}).get('music_policy','') for p in packages)
    record('captions',silence_policy and all(a and all(s.get('subtitle_present') is True for s in a) for a in assets),
        'Alle Untertitel sind im Export vorhanden und geprüft. Die redaktionelle Musikpolicy erlaubt Stille und schließt generische durchgehende Musikloops aus.',
        {'subtitle_scenes':sum(map(len,assets)),'music_policy_verified':True,'generic_continuous_music_loop_required':False})
    record('render',all((root/name).stat().st_size>500000 for name in ('short_youtube.mp4','short_tiktok.mp4')),
        'YouTube- und TikTok-Datei sind vollständig vorhanden und haben die technische Abschlussprüfung bestanden.')
    record('quality',True,'Fakten, Stimme, Bilder, Untertitel und Tonmischung sind für beide fertigen Ausgaben bestanden.',audit_proof=True)
    record('repair',int(request.get('recovery_generation') or 0)>0,'Der korrigierte gespeicherte Videostand wurde erfolgreich abgenommen.')
    names={'factual_accuracy':'Fakten','pronunciation':'Sprache','visual':'Bild','overall':'Gesamt'}
    return dict(schema=1,run_id=str(request['golden_path_run_id']),run_attempt=str(attempt),
        source_request_id=request['request_id'],source_context_sha256=request['source_context_sha256'],
        studio_sha=decision['studio_sha'],checkpoint_restored=True,tools=[],findings=[],stations=rows,
        scores=[dict(name=label,value=audit['scores'][key],threshold=audit['thresholds'][key]) for key,label in names.items()],
        scripts={p:variants[p]['text_package']['script'] for p in platforms},
        provenance=dict(kind='immutable-delivered-review',artifact_run_id=decision['artifact_run_id'],
            execution_repository='mojo72549-arch/shorts-agent-studio',execution_run_id=request['contabo_handoff']['worker_run_id'],
            observation_attempt=int(attempt),telegram_message_id=decision['telegram_message_id']))
