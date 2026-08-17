#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

WORKFLOW = Path('.github/workflows/tayvoriq-agent-orchestrator-v2.yml')


def patch(text: str) -> str:
    if '  HF_TOKEN:' not in text:
        lines = text.splitlines()
        out: list[str] = []
        inserted = False
        for line in lines:
            out.append(line)
            if line.startswith('  GROQ_API_KEY:') and not inserted:
                out.append("  HF_TOKEN: ${{ secrets.HF_TOKEN }}")
                out.append("  HUGGINGFACE_TOKEN: ${{ secrets.HUGGINGFACE_TOKEN }}")
                inserted = True
        if not inserted:
            raise RuntimeError('GROQ env anchor missing')
        text = '\n'.join(out) + '\n'

    marker = '      - name: Notify gate failure once for this run\n'
    if marker not in text:
        if 'Research providers temporarily saturated; deferred internally.' in text:
            return text
        raise RuntimeError('failure notification anchor missing')

    prefix = text.split(marker, 1)[0]
    replacement = '''      - name: Notify gate failure once for this run
        if: failure() && steps.slot.outputs.should_run == 'true'
        continue-on-error: true
        run: |
          if [ -f /tmp/tayvoriq-research-deferred.json ]; then
            echo "Research providers temporarily saturated; deferred internally. No user-facing Telegram failure sent."
            exit 0
          fi
          text="❌ TAYVORIQ Agent V2 konnte die aktuelle Growth-Rangliste nicht sicher erstellen. Es wurde keine Produktion gestartet. Run: ${GITHUB_RUN_ID}"
          curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=${text}" >/dev/null || true
'''
    return prefix + replacement


def main() -> int:
    before = WORKFLOW.read_text(encoding='utf-8')
    after = patch(before)
    WORKFLOW.write_text(after, encoding='utf-8')
    print({'changed': before != after, 'workflow': str(WORKFLOW)})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
