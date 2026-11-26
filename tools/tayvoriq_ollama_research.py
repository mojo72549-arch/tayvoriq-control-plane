"""Source-bound research completion on the private Contabo runner."""

import json
from urllib.request import ProxyHandler, Request, build_opener

MODEL = 'qwen3.5:9b'
ENDPOINT = 'http://127.0.0.1:11434/api/chat'


def complete(payload, *, opener=None):
    options = {'temperature': 0, 'num_ctx': 12288,
               'num_predict': payload.get('max_completion_tokens', 3800)}
    local = {'model': MODEL, 'messages': payload['messages'], 'stream': False,
             'think': False, 'format': 'json', 'keep_alive': '45s', 'options': options}
    request = Request(ENDPOINT, data=json.dumps(local).encode(), headers={'Content-Type': 'application/json'})
    opener = opener or build_opener(ProxyHandler({}))
    with opener.open(request, timeout=210) as response:
        result = json.load(response)
    content = (result.get('message') or {}).get('content')
    if (result.get('model') != MODEL or result.get('done') is not True
            or result.get('done_reason') == 'length' or not isinstance(content, str) or not content.strip()):
        raise RuntimeError('OLLAMA_RESEARCH_RESPONSE_INCOMPLETE')
    return {'choices': [{'message': {'content': content}}]}
