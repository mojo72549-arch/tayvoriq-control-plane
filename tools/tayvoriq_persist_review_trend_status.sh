#!/usr/bin/env bash
set -euo pipefail
[[ "$1" =~ ^review-(morning|evening)-[1-9][0-9]{0,19}$ ]]
path=".automation/tayvoriq-agent-v2/review-trend-status/$1.json"
[ -f "$path" ] || exit 0
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -- "$path"
git diff --cached --quiet -- "$path" && exit 0
git commit -m "ops(tayvoriq): record review trend status" -- "$path"
for attempt in 1 2 3; do
  git pull --rebase --autostash origin main
  if git push origin HEAD:main; then exit 0; fi
  sleep "$((attempt * 2))"
done
exit 1
