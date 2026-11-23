from __future__ import annotations
import json, os, time
from pathlib import Path
import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http
import tayvoriq_agent_rss_v2 as rss
import tayvoriq_agent_gdelt_v2 as gdelt
import tayvoriq_agent_hf_v2 as hf
from tayvoriq_provider_health_v1 import ProviderHealth, http_failure
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
    interactive = bool(os.getenv('TAYVORIQ_RESEARCH_SELECTION_ID'))
    scheduled_research = os.getenv('TAYVORIQ_RESEARCH_SLOT') in {'morning', 'evening'}
    # Model budgets are separate on the existing Groq free plan.
    # The legacy 'groq' record belongs to the previously hard-coded 20B model.
    # An account/payment block stays shared; a 429 on 20B does not prove that
    # the separate 120B model budget has also been consumed.
    source_models = {'groq': None, 'groq:openai/gpt-oss-120b': 'openai/gpt-oss-120b',
                     'groq:qwen/qwen3.8-27b': 'qwen/qwen3.8-27b', 'huggingface': None}
    if hf.EDITORIAL_RESCAN in prompt:
        # A successful response can still fail editorial review. On rescan,
        # prefer another model over repeating the same source-bound draft.
        source_models = dict(sorted(source_models.items(), key=lambda row: row[1] is None))
    keys = {'gemini': gemini_key, 'huggingface': token}
    keys.update({name: groq_key for name in source_models if name.startswith('groq')})
    if groq_key:
        health.available('groq', groq_key)  # honor a legitimately rotated key
    groq_account_blocked = (health.state['providers'].get('groq') or {}).get('state') == 'PAYMENT_BLOCKED'
    insufficient_feeds = False

    def attempt(name, label, call):
        nonlocal groq_account_blocked, insufficient_feeds
        key = keys[name]
        if not key:
            return None
        if name.startswith('groq') and groq_account_blocked:
            errors.append(label + ' skipped: shared account/payment block')
            return None
        if not health.available(name, key):
            errors.append(label + ' skipped: persistent provider cooldown/payment block')
            return None
        try:
            result = call()
            health.success(name)
            return result
        except Exception as exc:
            if http_failure(exc)[0] in {401, 403}:
                raise RuntimeError('RESEARCH_PROVIDER_ACCESS_BLOCKED: ' + label) from exc
            if isinstance(exc, hf.InsufficientSourceEvidence):
                health.success(name)
                if isinstance(exc, hf.InsufficientFeedEvidence):
                    insufficient_feeds = True
            else:
                health.failure(name, key, exc)
            if name.startswith('groq') and http_failure(exc)[0] == 402:
                groq_account_blocked = True
                health.failure('groq', key, exc)
            errors.append(label + ' failed: ' + http.summary(exc))
            return None

    result = attempt('gemini', 'Gemini', lambda: http.retry(
        'gemini', lambda: http.gemini_grounded(prompt, gemini_key), 1 if interactive else 3))
    if result is not None:
        return (*result, 'gemini')
    def try_groq_browser():
        if interactive:
            errors.append('Groq browser skipped: interactive research uses independent source records')
            return None
        if (health.state['providers'].get('groq') or {}).get('http_status') == 429:
            errors.append('Groq browser deferred: quota recovery uses compact source-bound requests')
            return None
        kwargs = {'timeout':45} if scheduled_research else {}
        return attempt('groq', 'Groq browser', lambda: provider.groq_browser_then_structure(prompt, groq_key, **kwargs))

    if not scheduled_research:
        result = try_groq_browser()
        if result is not None:
            return (*result, 'groq')

    source_records = {}

    def article_sources():
        if not insufficient_feeds:
            return []
        leads = hf._groq_source_records(list(source_records.values()))[:8]
        originals = [source_records[item["url"]] for item in leads]
        enriched = rss.enrich_evidence(originals)
        return [after for before, after in zip(originals, enriched) if before != after]

    for label, collect in (('multi-publisher-rss', rss.source_pool),
                           ('rss-article-context', article_sources),
                           ('rss-gdelt-context', gdelt.source_pool)):
        # A model quota is shared by that model's browser and source structurer.
        if not any(key and health.available(name, key) and
                   not (name.startswith('groq') and groq_account_blocked)
                   for name, key in keys.items() if name != 'gemini'):
            break
        try:
            records = collect()
        except Exception as exc:
            errors.append(label + ' collection unavailable: ' + http.summary(exc))
            continue
        updated = 0
        for record in records:
            url = record.get('url')
            if url and (url not in source_records or label == 'rss-article-context'):
                source_records[url] = record
                updated += 1
        if not updated:
            continue
        print(json.dumps({"event":"source_records_loaded","source_label":label,"updated_records":updated}))
        records = list(source_records.values())
        for name, model in source_models.items():
            result = attempt(name, name + '/' + label, lambda: hf.structure(
                prompt, keys[name], records, label,
                provider_kind='groq' if name.startswith('groq') else name,
                **({'model_override': model} if model else {})))
            if result is not None:
                return (*result, ('groq' if name.startswith('groq') else name) +
                        ('_gdelt' if label == 'rss-gdelt-context' else '_rss'))

    if scheduled_research:
        result = try_groq_browser()
        if result is not None:
            return (*result, 'groq')

    errors.append('Deterministic source fallback disabled: syndicated mirrors and generic hooks cannot pass editorial quality')
    retry_keys = {name: key for name, key in keys.items()
                  if not (name.startswith('groq') and groq_account_blocked)}
    _defer(errors, health.next_retry(retry_keys))
    raise RuntimeError('RESEARCH_DEFERRED: ' + ' | '.join(errors))


def install() -> None:
    base.gemini_call=http.gemini_grounded
    base.grounded_call=grounded
