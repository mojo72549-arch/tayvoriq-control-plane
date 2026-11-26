"""Source-bound research completion on the private Contabo runner."""

import json
import os
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


def complete(payload, *, opener=None):
    model = research_model()
    options = {'temperature': 0, 'num_ctx': 8192, 'num_thread': 8,
               'num_predict': payload.get('max_completion_tokens', 2900)}
    local = {'model': model, 'messages': payload['messages'], 'stream': True,
             'think': False, 'format': 'json', 'keep_alive': '4m' if model == COMPACT_MODEL else '45s', 'options': options}
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
