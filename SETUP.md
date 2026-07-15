# Setup checklist

1. Add the required repository secrets.
2. Create `PRIVATE_REPO_TOKEN` as a fine-grained PAT restricted to `shorts-agent-studio` with Contents: Read.
3. Ensure `PAGES_DEPLOY_TOKEN` can push to `mind-reset-daily`.
4. Run `TAYVORIQ Golden Path` with `mode=quality_gate_only`.
5. Only after green, run with `mode=full`.
6. Do not enable any additional 5-minute scheduler.
