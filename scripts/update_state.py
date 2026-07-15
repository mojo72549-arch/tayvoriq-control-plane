#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--path', default='state/tayvoriq-state.json')
p.add_argument('--state', required=True)
p.add_argument('--run-id')
p.add_argument('--commit')
p.add_argument('--next-action', required=True)
p.add_argument('--blocked-reason', default='')
p.add_argument('--attempt', type=int)
a = p.parse_args()
path = Path(a.path)
data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {"schema_version": 1}
data.update({
    "state": a.state,
    "run_id": a.run_id,
    "active_commit": a.commit,
    "next_action": a.next_action,
    "blocked_reason": a.blocked_reason or None,
    "updated_at": datetime.now(timezone.utc).isoformat(),
})
if a.attempt is not None:
    data["attempt"] = a.attempt
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
print(json.dumps(data, ensure_ascii=False))
