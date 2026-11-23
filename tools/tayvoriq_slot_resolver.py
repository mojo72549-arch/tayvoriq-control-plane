"""Resolve one Berlin production slot without starting research or production."""
from datetime import datetime
import os
import re
import subprocess
from zoneinfo import ZoneInfo

from tayvoriq_rejected_review_followup import followup
from tayvoriq_research_retry_v1 import due_slot, review_due

TRIGGER = '.github/run-now/tayvoriq-agent-trigger.txt'
WORKFLOW = '.github/workflows/tayvoriq-agent-orchestrator-v2.yml'


def push_paths(env):
    before, after = env.get('PUSH_BEFORE', ''), env.get('GITHUB_SHA', '')
    if not all(re.fullmatch('[0-9a-f]{40}', sha) for sha in (before, after)):
        return set()
    if before == '0' * 40:
        return set()
    output = subprocess.check_output(['git', 'diff', '--name-only', before, after], text=True)
    return set(output.splitlines())


def resolve(env, now):
    event = env.get('EVENT_NAME')
    cron = env.get('EVENT_SCHEDULE')
    if env.get('RECONCILE_ONLY') == 'true' or now.date().isoformat() < '2026-08-15':
        return '', ''
    if event == 'workflow_dispatch':
        if env.get('RESEARCH_RETRY_WAKEUP') == 'true':
            return due_slot(now=now.timestamp()), ''
        slot = env.get('INPUT_SLOT')
        return (slot if slot in ('morning', 'evening') else ''), ''
    if event == 'schedule':
        summer = now.utcoffset().total_seconds() == 7200
        if cron == ('30 3 * * *' if summer else '30 4 * * *'):
            return 'morning', ''
        if cron == ('0 17 * * *' if summer else '0 18 * * *'):
            return 'evening', ''
        if cron != '*/5 * * * *':
            return '', ''
    elif event != 'push':
        return '', ''

    paths = push_paths(env) if event == 'push' else set()
    plan = followup()
    if plan and plan['new_trends_requested'] and not plan['selection_delivered']:
        selected = plan['selection_id']
        if (event == 'schedule' or paths.intersection({WORKFLOW, plan['decision_path']})) and review_due(selected, now=now.timestamp()):
            return plan['slot'], selected
    if event == 'schedule':
        return due_slot(now=now.timestamp()), ''
    if TRIGGER in paths:
        return due_slot(now=now.timestamp()) or ('morning' if now.hour < 12 else 'evening'), ''
    return '', ''


def main():
    now = datetime.now(ZoneInfo('Europe/Berlin'))
    slot, selection = resolve(os.environ, now)
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f"should_run={'true' if slot else 'false'}\nslot={slot}\nrejection_selection={selection}\n")
    print({'berlin': now.isoformat(), 'slot': slot, 'rejection_selection': selection})


if __name__ == '__main__':
    main()
