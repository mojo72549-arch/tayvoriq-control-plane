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


def _defer(errors: list[str], next_at: float | None, *, issue: str) -> None:
    queued = research_retry.defer(os.getenv('TAYVORIQ_RESEARCH_SLOT', ''), next_at, issue=issue)
    data = {'status': 'RESEARCH_DEFERRED',
            'reason': 'all live research paths unavailable after bounded retries',
            'errors': errors[-10:], 'created_at_epoch': int(time.time()),
            'retry_at_epoch': next_at, 'retry_state': queued.get('state', 'UNSCHEDULED'), 'last_issue': issue}
    MARKER.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'event': 'research_deferred', **data}, ensure_ascii=False))


def defer_editorial(slot: str) -> None:
    queued = research_retry.defer_candidate_selection(slot, issue='EDITORIAL_MINIMUM_NOT_MET')
    status = {'status': 'RESEARCH_DEFERRED', 'result': 'REJECTED', 'retry_state': queued.get('state', 'UNSCHEDULED'),
              'reason': 'EDITORIAL_MINIMUM_NOT_MET'}
    MARKER.write_text(json.dumps(status, ensure_ascii=False) + '\n', encoding='utf-8')


def _still_current(draft, records):
    pair = [records.get(source["url"]) for source in draft["sources"]]
    if not all(pair) or hf.validate_pair(draft, pair):
        return False
    return all(hf.source_support(record)[1] == source["source_record_sha256"]
               and record.get("seen_date") == source.get("source_date")
               and (record.get("origin") or "") == (source.get("declared_origin") or "")
               for record, source in zip(pair, draft["sources"]))


def local_grounded(prompt):
    records = {}
    rejected_titles = []
    last_error = None
    def article_sources():
        if not isinstance(last_error, hf.InsufficientFeedEvidence):
            return []
        originals = hf.article_research_records(list(records.values()))
        enriched = rss.enrich_evidence(originals)
        # The same publisher URL gains its original article context. Discovery
        # time, reporting origin and the bound headline remain unchanged.
        return [{**before, 'context': after['context']} for before, after in zip(originals, enriched)
                if after.get('url') == before['url'] and after.get('context')
                and after['context'] != before.get('context')]

    for label, collect in (('multi-publisher-rss', lambda: rss.source_pool(expanded=True)),
                           ('rss-article-context', article_sources),
                           ('rss-gdelt-context', gdelt.source_pool)):
        discovered = {row['url']: row for row in collect() if row.get('url')}
        updated = {url: row for url, row in discovered.items()
                   if url not in records or label == 'rss-article-context'}
        if not updated:
            continue
        records.update(updated)
        print(json.dumps({'event': 'source_records_loaded', 'source_label': label,
                          'updated_records': len(updated), 'total_records': len(records)}), flush=True)
        print(json.dumps({'event': 'provider_attempt_started', 'provider': 'ollama'}), flush=True)
        try:
            data, chunks, model = hf.structure(
                prompt, '', list(records.values()), label, provider_kind='ollama',
                **({'rejected_titles': tuple(rejected_titles)} if rejected_titles else {}),
                **({'allow_single': True} if os.getenv('TAYVORIQ_RESEARCH_SELECTION_ID') or
                    os.getenv('TAYVORIQ_EDITORIAL_TOPIC', '').strip() else {}),
            )
            return data, chunks, model, 'ollama_gdelt' if label == 'rss-gdelt-context' else 'ollama_rss'
        except hf.InsufficientSourceEvidence as error:
            if isinstance(error, hf.RejectedSourceHeadline):
                rejected_titles.append(error.title)
            last_error = error
    if rejected_titles or (isinstance(last_error, hf.InsufficientSourceEvidence)
                           and not isinstance(last_error, hf.InsufficientFeedEvidence)):
        raise RuntimeError('OLLAMA_EDITORIAL_RESULT_INCOMPLETE') from last_error
    print(json.dumps({'event': 'local_research_failed', 'issue': 'SOURCE_MINIMUM_NOT_MET'}), flush=True)
    raise RuntimeError('OLLAMA_SOURCE_MINIMUM_NOT_MET') from last_error


def grounded(prompt: str, gemini_key: str, groq_key: str):
    if os.environ.get('TAYVORIQ_LOCAL_RESEARCH') == 'true':
        return local_grounded(prompt)
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
    rescan = any(marker in prompt for marker in hf.RESCAN_MARKERS)
    if rescan:
        # A successful response can still fail editorial review. On rescan,
        # prefer another model over repeating the same source-bound draft.
        source_models = dict(sorted(source_models.items(), key=lambda row: row[1] is None))
    keys = {'gemini': gemini_key, 'huggingface': token}
    keys.update({name: groq_key for name in source_models if name.startswith('groq')})
    if groq_key:
        health.available('groq', groq_key)  # honor a legitimately rotated key
    groq_account_blocked = (health.state['providers'].get('groq') or {}).get('state') == 'PAYMENT_BLOCKED'
    insufficient_feeds = False
    failed_source_contract = False

    def attempt(name, label, call):
        nonlocal groq_account_blocked, insufficient_feeds, failed_source_contract, blocked_groq_preflight
        key = keys[name]
        if not key:
            return None
        if name.startswith('groq') and groq_account_blocked:
            errors.append(label + ' skipped: shared account/payment block')
            return None
        if not health.available(name, key):
            errors.append(label + ' skipped: persistent provider cooldown/payment block')
            return None
        print(json.dumps({"event": "provider_attempt_started", "provider": name}), flush=True)
        try:
            result = call()
            health.success(name)
            return result
        except Exception as exc:
            if http_failure(exc)[0] in {401, 403}:
                raise RuntimeError('RESEARCH_PROVIDER_ACCESS_BLOCKED: ' + label) from exc
            if isinstance(exc, hf.InsufficientSourceEvidence):
                failed_source_contract = True
                health.success(name)
                if isinstance(exc, hf.InsufficientFeedEvidence):
                    insufficient_feeds = True
                    if name.startswith('groq'):
                        blocked_groq_preflight = True
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
    partials = {}

    def article_sources():
        if not insufficient_feeds:
            return []
        leads = hf.article_research_records(list(source_records.values()))
        originals = [source_records[item["url"]] for item in leads]
        enriched = rss.enrich_evidence(originals)
        return [after for before, after in zip(originals, enriched) if before != after]

    collect_rss = (lambda: rss.source_pool(expanded=True)) if (rescan or scheduled_research) else rss.source_pool
    for label, collect in (('multi-publisher-rss', collect_rss),
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
        print(json.dumps({"event":"source_records_loaded","source_label":label,"updated_records":updated,"total_records":len(source_records)}))
        records = list(source_records.values())
        blocked_groq_preflight = False
        for name, model in source_models.items():
            if blocked_groq_preflight and name.startswith('groq'):
                continue
            result = attempt(name, name + '/' + label, lambda: hf.structure(
                prompt, keys[name], records, label,
                provider_kind='groq' if name.startswith('groq') else name,
                **({'model_override': model} if model else {})))
            if result is not None:
                provider_name = ('groq' if name.startswith('groq') else name) + (
                    '_gdelt' if label == 'rss-gdelt-context' else '_rss')
                data, chunks, used_model = result
                candidates = data.get("candidates") or []
                if len(candidates) == 1 and len(chunks) == 2 and candidates[0].get("_retrieved_regional_assessment", {}).get("passed"):
                    draft = candidates[0]
                    pair = tuple(sorted(source["url"] for source in draft["sources"]))
                    if pair not in partials:
                        partials[pair] = draft, chunks, used_model, provider_name
                    if len(partials) < 2:
                        continue
                else:
                    if not partials:
                        return (*result, provider_name)
                merged = list(candidates)
                evidence = {c["uri"]: c for c in chunks}
                used_models = [used_model]
                for prior, prior_chunks, prior_model, _ in partials.values():
                    if not _still_current(prior, source_records):
                        continue
                    if any(c["uri"] in evidence for c in prior_chunks):
                        continue
                    if any(not hf.distinct_headlines(prior["title"], row["title"]) for row in merged):
                        continue
                    merged.append(prior)
                    evidence.update({c["uri"]: c for c in prior_chunks})
                    if prior_model not in used_models:
                        used_models.append(prior_model)
                if len(merged) >= 2:
                    return {**data, "candidates": merged}, list(evidence.values()), " + ".join(used_models), provider_name

    for draft, chunks, used_model, provider_name in partials.values():
        if _still_current(draft, source_records):
            # The radar still checks duplicates, editorial quality and relevance.
            return {"candidates": [draft]}, chunks, used_model, provider_name

    if scheduled_research and not interactive and insufficient_feeds:
        blocked_groq_preflight = False
        for name, model in source_models.items():
            result = attempt(name, name + '/sole-corroborated-story', lambda: hf.structure(
                prompt, keys[name], list(source_records.values()), 'rss-article-context',
                provider_kind='groq' if name.startswith('groq') else name,
                allow_single=True, **({'model_override': model} if model else {})))
            if result is not None:
                return (*result, 'groq_rss' if name.startswith('groq') else 'huggingface_rss')
            if blocked_groq_preflight:
                break

    if scheduled_research:
        result = try_groq_browser()
        if result is not None:
            return (*result, 'groq')

    errors.append('Deterministic source fallback disabled: syndicated mirrors and generic hooks cannot pass editorial quality')
    retry_keys = {name: key for name, key in keys.items()
                  if not (name.startswith('groq') and groq_account_blocked)}
    issue = 'SOURCE_MINIMUM_NOT_MET' if failed_source_contract else 'RESEARCH_PROVIDER_UNAVAILABLE'
    # A valid provider can reject a source pair without being rate-limited.
    # Give a new set of article leads one of the existing bounded slot retries.
    delay = (research_retry.EDITORIAL_RETRY_SECONDS
             if scheduled_research and not interactive and failed_source_contract else 900)
    _defer(errors, health.next_retry(retry_keys, available_delay_seconds=delay), issue=issue)
    raise RuntimeError('RESEARCH_DEFERRED: ' + ' | '.join(errors))


def install() -> None:
    base.gemini_call=http.gemini_grounded
    base.grounded_call=grounded
