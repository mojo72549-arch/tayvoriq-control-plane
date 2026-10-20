from __future__ import annotations
import json, os, time
from pathlib import Path
import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http
import tayvoriq_agent_rss_v2 as rss
import tayvoriq_agent_gdelt_v2 as gdelt
import tayvoriq_agent_hf_v2 as hf
from tayvoriq_provider_health_v1 import ProviderHealth
import tayvoriq_research_retry_v1 as research_retry
base=provider.base
MARKER=Path('/tmp/tayvoriq-research-deferred.json')


def _defer(errors: list[str], next_at: float | None = None) -> None:
    queued = research_retry.defer(os.getenv('TAYVORIQ_RESEARCH_SLOT', ''), next_at)
    data = {'status': 'RESEARCH_DEFERRED',
            'reason': 'all live research paths unavailable after bounded retries',
            'errors': errors[-10:], 'created_at_epoch': int(time.time()),
            'retry_at_epoch': next_at, 'retry_state': queued.get('state', 'UNSCHEDULED')}
    MARKER.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'event': 'research_deferred', **data}, ensure_ascii=False))


def grounded(prompt: str, gemini_key: str, groq_key: str):
    errors = []
    MARKER.unlink(missing_ok=True)
    health_path = os.getenv('TAYVORIQ_PROVIDER_HEALTH_FILE')
    health = ProviderHealth(Path(health_path) if health_path else None)
    token = str(os.getenv('HF_TOKEN') or os.getenv('HUGGINGFACE_TOKEN') or '').strip()
    keys = {'gemini': gemini_key, 'groq': groq_key, 'huggingface': token}

    def attempt(name, label, call):
        key = keys[name]
        if not key:
            return None
        if not health.available(name, key):
            errors.append(label + ' skipped: persistent provider cooldown/payment block')
            return None
        try:
            result = call()
            health.success(name)
            return result
        except Exception as exc:
            health.failure(name, key, exc)
            errors.append(label + ' failed: ' + http.summary(exc))
            return None

    result = attempt('gemini', 'Gemini', lambda: http.retry(
        'gemini', lambda: http.gemini_grounded(prompt, gemini_key), 3))
    if result is not None:
        return (*result, 'gemini')
    result = attempt('groq', 'Groq browser', lambda: provider.groq_browser_then_structure(prompt, groq_key))
    if result is not None:
        return (*result, 'groq')

    for label, collect in (('multi-publisher-rss', rss.source_pool), ('gdelt-context', gdelt.source_pool)):
        # A depleted Groq quota is shared by browser, RSS and GDELT structuring.
        if not any(key and health.available(name, key) for name, key in keys.items() if name != 'gemini'):
            break
        try:
            records = collect()
        except Exception as exc:
            errors.append(label + ' collection unavailable: ' + http.summary(exc))
            continue
        if not records:
            continue
        for name in ('groq', 'huggingface'):
            result = attempt(name, name + '/' + label, lambda name=name: hf.structure(
                prompt, keys[name], records, label, provider_kind=name))
            if result is not None:
                return (*result, name + ('_rss' if label == 'multi-publisher-rss' else '_gdelt'))

    errors.append('Deterministic source fallback disabled: syndicated mirrors and generic hooks cannot pass editorial quality')
    _defer(errors, health.next_retry(keys))
    raise RuntimeError('RESEARCH_DEFERRED: ' + ' | '.join(errors))


def install() -> None:
    base.gemini_call=http.gemini_grounded
    base.grounded_call=grounded
