"""One structured usage record per actual research-provider HTTP request."""
import json
import os
import time
import urllib.request


def post(request, timeout, provider, model):
    started = time.monotonic()
    record = dict(event="research_http_usage", provider=provider, model=model,
                  run_id=os.getenv("GITHUB_RUN_ID"), run_attempt=os.getenv("GITHUB_RUN_ATTEMPT"),
                  selection_id=os.getenv("TAYVORIQ_RESEARCH_SELECTION_ID") or None,
                  status=None, input_tokens=None, output_tokens=None, total_tokens=None)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            record["status"] = response.status
            raw = json.loads(response.read().decode("utf-8"))
            headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
        if isinstance(raw, dict):
            counts = raw.get("usageMetadata") or raw.get("usage") or {}
            if isinstance(counts, dict):
                for name, fields in (
                    ("input_tokens", ("promptTokenCount", "prompt_tokens")),
                    ("output_tokens", ("candidatesTokenCount", "completion_tokens")),
                    ("total_tokens", ("totalTokenCount", "total_tokens")),
                ):
                    for key in fields:
                        count = counts.get(key)
                        if type(count) is int and count >= 0:
                            record[name] = count
                            break
        return raw, headers
    except Exception as exc:
        record["status"] = getattr(exc, "code", None) or record["status"]
        record["error_type"] = type(exc).__name__
        raise
    finally:
        record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        print(json.dumps(record, ensure_ascii=False))
