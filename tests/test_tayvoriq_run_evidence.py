import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tayvoriq_run_evidence import collect, summary


def test_report_requires_this_attempt_and_each_artifacts_digest(tmp_path):
    def write(name, document):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True, parents=True)
        content = json.dumps(document).encode()
        path.write_bytes(content)
        return hashlib.sha256(content).hexdigest()

    binding = dict(run_id="123", run_attempt="2", source_request_id="telegram-123", source_context_sha256="b"*64)
    manifest = dict(binding, implementation_sha="a"*40, restored_recovery_checkpoint=True)
    write("control-plane/production-manifest.json", manifest)
    audio = write("job/youtube_shorts/audio_report.json", {"voice_provider_used":"chatterbox_multilingual_v3"})
    audit = write("job/preapproval_ai_audit.json", {"scores":{"visual":55},"thresholds":{"visual":78},
          "visual_review":{"scene_checks":[{"platform":"youtube_shorts","scene":4,"relevant":False}]}})
    meta = {**manifest, "files_sha256":{"youtube_shorts/audio_report.json":audio, "preapproval_ai_audit.json":audit}}
    write("recovery-checkpoint-meta.json", meta)
    args = (tmp_path, "123", "2", "telegram-123", "b"*64)
    r = collect(*args)
    assert [tool["name"] for tool in r["tools"]] == ["Chatterbox"]
    assert "YouTube · Szene 4 · Motiv unpassend" in summary(r)
    assert r["scores"] == [{"name":"Bild", "value":55, "threshold":78}]
    with pytest.raises(ValueError):
        collect(tmp_path,"123","1","telegram-123","b"*64)
    write("job/preapproval_ai_audit.json", {"scores":{"visual":100}, "thresholds":{"visual":78}})
    assert collect(*args)["scores"] == []
    write("recovery-checkpoint-meta.json", dict(meta, run_attempt="1"))
    assert collect(*args)["tools"] == []
