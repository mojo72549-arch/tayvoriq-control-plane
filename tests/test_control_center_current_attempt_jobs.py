from __future__ import annotations

import subprocess
from pathlib import Path


def test_control_center_uses_latest_attempt_jobs_in_both_deploy_layouts():
    api = Path("api/live.js").read_text(encoding="utf-8")
    dashboard = Path("dashboard/api/live.js").read_text(encoding="utf-8")
    assert api == dashboard
    assert "canonicalRun=await getRun(CONTROL_REPO,canonicalRunId,gh.headers)" in api
    node = r"""
const fs = require('fs');
const source = fs.readFileSync('api/live.js', 'utf8');
const start = source.indexOf('async function getJobs(');
const end = source.indexOf('\nfunction selectJob', start);
if (start < 0 || end < 0) throw Error('getJobs missing');
let requested = [];
const jsonFetch = async (url) => { requested.push(url); return {jobs: []}; };
const getJobs = new Function('API', 'jsonFetch',
  'return (' + source.slice(start, end).trim() + ')'
)('https://api.github.com', jsonFetch);
(async () => {
  await getJobs('owner/repo', 36261304535, {}, 3);
  await getJobs('owner/repo', 36261304535, {}, 1);
  if (!requested[0].includes('/runs/36261304535/attempts/3/jobs?'))
    throw Error('rerun did not select attempt 3');
  if (!requested[1].includes('/runs/36261304535/jobs?filter=latest'))
    throw Error('first run job lookup changed');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", node], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
