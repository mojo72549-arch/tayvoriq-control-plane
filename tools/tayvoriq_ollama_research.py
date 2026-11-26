"""Source-bound research completion on the private Contabo runner."""

import json
import os
import re
import time
from urllib.request import ProxyHandler, Request, build_opener

MODEL = 'qwen3.5:9b'
COMPACT_MODEL = 'qwen3.5:4b'
ENDPOINT = 'http://127.0.0.1:11434/api/chat'


def research_model():
    model = os.getenv('TAYVORIQ_RESEARCH_MODEL', MODEL)
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


def research_format(example, pairs, scopes):
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
        fields['regional_scorecard']['properties']['evidence'] = _shape({source: '' for source in pair})
        properties['+'.join(pair)] = {'anyOf': [shape, {'type': 'null'}]}
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def read_candidates(reply, pairs):
    expected = {'+'.join(pair) for pair in pairs}
    if not isinstance(reply, dict) or set(reply) != expected or any(
            row is not None and not isinstance(row, dict) for row in reply.values()):
        raise RuntimeError('OLLAMA_RESEARCH_PAIR_DECISIONS_INCOMPLETE')
    return {'candidates': [{**row, 'source_pair_id': key} for key, row in reply.items() if row is not None]}


def complete(payload, *, opener=None):
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
        # The HTTP response starts only after Ollama loads the model and processes the prompt.
        # The worker separately enforces the overall research time limit.
        with opener.open(request, timeout=330) as response:
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
    except TimeoutError:
        print(json.dumps({'event': 'provider_attempt_failed', 'provider': 'ollama', 'error': 'Model timeout'}), flush=True)
        raise
    content = ''.join(fragments)
    if result.get('done') is not True or result.get('done_reason') == 'length' or not content.strip():
        raise RuntimeError('OLLAMA_RESEARCH_RESPONSE_INCOMPLETE')
    return {'choices': [{'message': {'content': content}}]}
