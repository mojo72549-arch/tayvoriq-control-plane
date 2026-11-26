"""Source-bound research completion on the private Contabo runner."""

import json
from urllib.request import ProxyHandler, Request, build_opener

MODEL = 'qwen3.5:9b'
ENDPOINT = 'http://127.0.0.1:11434/api/chat'


def complete(payload, *, opener=None):
    options = {'temperature': 0, 'num_ctx': 8192, 'num_thread': 8,
               'num_predict': payload.get('max_completion_tokens', 2900)}
    local = {'model': MODEL, 'messages': payload['messages'], 'stream': True,
             'think': False, 'format': 'json', 'keep_alive': '45s', 'options': options}
    request = Request(ENDPOINT, data=json.dumps(local).encode(), headers={'Content-Type': 'application/json'})
    opener = opener or build_opener(ProxyHandler({}))
    fragments = []
    result = {}
    with opener.open(request, timeout=120) as response:
        for line in response:
            if not line.strip():
                continue
            result = json.loads(line)
            if result.get('model') != MODEL or result.get('error'):
                raise RuntimeError('OLLAMA_RESEARCH_RESPONSE_INVALID')
            fragments.append((result.get('message') or {}).get('content') or '')
            if result.get('done'):
                break
    content = ''.join(fragments)
    if result.get('done') is not True or result.get('done_reason') == 'length' or not content.strip():
        raise RuntimeError('OLLAMA_RESEARCH_RESPONSE_INCOMPLETE')
    return {'choices': [{'message': {'content': content}}]}
