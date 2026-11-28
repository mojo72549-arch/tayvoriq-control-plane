"""Source-bound research completion on the private Contabo runner."""

import hashlib
import json
import os
import re
import signal
import time
from contextlib import contextmanager
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

MODEL = 'qwen3.5:9b'
COMPACT_MODEL = 'qwen3.5:4b'
ENDPOINT = 'http://127.0.0.1:11434/api/chat'
VALIDATION_RESERVE_SECONDS = 20
MAXIMUM_CANDIDATE_SECONDS = 210
MINIMUM_REPAIR_SECONDS = 25
MAXIMUM_REPAIR_SECONDS = 45

WIRE_KEYS = {
    'content_angle': 'angle', 'category': 'cat', 'trend_scope': 'scope', 'regional_relevance': 'region',
    'viral_potential': 'viral', 'tayvoriq_fit': 'fit', 'novelty_score': 'novel', 'series_fit_score': 'series',
    'return_viewer_score': 'return', 'follow_conversion_potential': 'follow', 'open_loop_potential': 'loop',
    'proposed_series_id': 'seriesId', 'proposed_series_name': 'seriesName', 'next_episode_candidate': 'next',
    'recommended_cta_type': 'recommend', 'primary_hook': 'hook', 'viewer_question': 'question',
    'explanation_core': 'explain', 'surprise_or_reframe': 'reframe', 'practical_relevance': 'relevance',
    'follow_reason': 'whyFollow', 'open_loop': 'teaser', 'open_loop_status': 'loopStatus',
    'next_episode_queue_status': 'queue', 'cta_type': 'ctaType', 'cta_text': 'cta',
    'regional_scorecard': 'card', 'fallback_editorial_answers': 'spoken',
}
INTERNAL_KEYS = {wire: field for field, wire in WIRE_KEYS.items()}


def research_model():
    model = os.getenv('TAYVORIQ_RESEARCH_MODEL', COMPACT_MODEL)
    if model not in {MODEL, COMPACT_MODEL}:
        raise ValueError('Unsupported local research model')
    return model


def _shape(example):
    if isinstance(example, dict):
        return {'type': 'object', 'properties': {key: _shape(value) for key, value in example.items()},
                'required': list(example), 'additionalProperties': False}
    if isinstance(example, list):
        return {'type': 'array', 'minItems': len(example), 'maxItems': len(example),
                'items': {'anyOf': [_shape(value) for value in example[:1] + example[-1:]]}}
    if type(example) is int:
        return {'type': 'integer', 'minimum': 0, 'maximum': 100}
    return {'type': 'string'}


def research_format(example, pairs, scopes, *, compact=False):
    """Ask for a decision on each supplied pair, with null for insufficient evidence."""
    normalized = re.sub(r'<(?:integer 0-100|(?:YouTube|TikTok) integer 0-5)>', '0', example)
    candidate = json.loads(normalized)['candidates'][0]
    candidate.pop('source_pair_id')
    properties = {}
    for pair in pairs:
        shape = _shape(candidate)
        fields = shape['properties']
        fields['trend_scope'] = {'type': 'string', 'enum': sorted(set(scopes) - {'auto_scope'})}
        fields['regional_relevance'] = {'type': 'string', 'enum': ['local', 'germany']}
        regional = fields['regional_scorecard']['properties']
        regional['evidence'] = _shape({source: '' for source in pair})
        for criterion in regional['ratings']['properties']:
            rating = _shape({'y': 0, 't': 0, 'why': ''})
            for platform in ('y', 't'):
                rating['properties'][platform]['maximum'] = 5
            regional['ratings']['properties'][criterion] = rating
        if compact:
            shape['properties'] = {WIRE_KEYS.get(key, key): field for key, field in fields.items()}
            shape['required'] = list(shape['properties'])
        properties['+'.join(pair)] = {'anyOf': [shape, {'type': 'null'}]}
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def read_candidates(reply, pairs, *, compact=False):
    expected = {'+'.join(pair) for pair in pairs}
    if not isinstance(reply, dict) or set(reply) != expected or any(
            row is not None and not isinstance(row, dict) for row in reply.values()):
        raise RuntimeError('OLLAMA_RESEARCH_PAIR_DECISIONS_INCOMPLETE')
    candidates = []
    for key, row in reply.items():
        if row is None:
            continue
        if compact:
            row = {INTERNAL_KEYS.get(wire, wire): value for wire, value in row.items()}
        candidate = {**row, 'source_pair_id': key}
        regional = candidate.get('regional_scorecard')
        if isinstance(regional, dict) and isinstance(regional.get('ratings'), dict):
            ratings = {}
            for criterion, value in regional['ratings'].items():
                if not isinstance(value, dict) or set(value) != {'y', 't', 'why'}:
                    raise RuntimeError('OLLAMA_RESEARCH_INVALID_RATING_SHAPE')
                ratings[criterion] = [value['y'], value['t'], value['why']]
            candidate['regional_scorecard'] = {**regional, 'ratings': ratings}
        candidates.append(candidate)
    return {'candidates': candidates}


def remaining_research_seconds():
    deadline = os.getenv('TAYVORIQ_RESEARCH_DEADLINE_EPOCH')
    return float(deadline) - time.time() if deadline else float('inf')


def repair_budget():
    remaining = remaining_research_seconds() - VALIDATION_RESERVE_SECONDS
    return min(MAXIMUM_REPAIR_SECONDS, remaining) if remaining >= MINIMUM_REPAIR_SECONDS else 0


def source_pair_key(urls):
    return hashlib.sha256(json.dumps(sorted(urls), ensure_ascii=False).encode()).hexdigest()


def candidate_budget(pairs_remaining, *, first_pair=False, recovery=False):
    available = max(0, remaining_research_seconds() - VALIDATION_RESERVE_SECONDS)
    if recovery:
        return min(300, available)
    # The first inference includes cold model loading. Reserve a full warm
    # evaluation for the remaining pair, along with the final quality check.
    if first_pair and pairs_remaining == 2:
        return min(240, available / 2 + min(30, available * 0.08))
    return min(MAXIMUM_CANDIDATE_SECONDS, available / pairs_remaining)


@contextmanager
def completion_deadline(seconds):
    if seconds is None:
        yield
        return
    if seconds <= 0:
        raise TimeoutError('No time remains for a local research completion')

    def expire(signum, frame):
        raise TimeoutError('Local research completion reached its time budget')

    # Contabo evaluates the pairs sequentially in the main thread. Use a real
    # deadline across both the request and body reads, including silent streams.
    previous_handler = signal.signal(signal.SIGALRM, expire)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def complete(payload, *, opener=None, time_limit=None):
    model = research_model()
    options = {'temperature': 0, 'num_ctx': 8192, 'num_thread': 8,
               'num_predict': payload.get('max_completion_tokens', 2900)}
    local = {'model': model, 'messages': payload['messages'], 'stream': True,
             'think': False, 'format': payload.get('format', 'json'),
             'keep_alive': '4m' if model == COMPACT_MODEL else '45s', 'options': options}
    request = Request(ENDPOINT, data=json.dumps(local).encode(), headers={'Content-Type': 'application/json'})
    opener = opener or build_opener(ProxyHandler({}))
    fragments = []
    result = {}
    started = time.monotonic()
    try:
        with completion_deadline(time_limit), opener.open(request, timeout=time_limit or 330) as response:
            print(json.dumps({'event': 'ollama_response_started', 'provider': 'ollama',
                              'first_response_seconds': round(time.monotonic() - started, 1)}), flush=True)
            for line in response:
                if not line.strip():
                    continue
                result = json.loads(line)
                if result.get('model') != model or result.get('error'):
                    raise RuntimeError('OLLAMA_RESEARCH_RESPONSE_INVALID')
                fragments.append((result.get('message') or {}).get('content') or '')
                if result.get('done'):
                    break
    except (TimeoutError, URLError) as error:
        if isinstance(error, URLError) and not isinstance(error.reason, TimeoutError):
            raise
        print(json.dumps({'event': 'provider_attempt_failed', 'provider': 'ollama', 'error': 'Model timeout',
                          'model': model, 'elapsed_seconds': round(time.monotonic() - started, 1),
                          'generated_characters': sum(map(len, fragments))}), flush=True)
        if isinstance(error, URLError):
            raise error.reason from error
        raise
    content = ''.join(fragments)
    if result.get('done') is not True or result.get('done_reason') == 'length' or not content.strip():
        raise RuntimeError('OLLAMA_RESEARCH_RESPONSE_INCOMPLETE')
    return {'choices': [{'message': {'content': content}}]}
