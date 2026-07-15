# Security

- This repository is public and must never contain private implementation code or plaintext secrets.
- Workflows do not run on pull requests.
- The private repository token must be fine-grained and restricted to `shorts-agent-studio`.
- Provider and Telegram credentials belong only in GitHub Actions Secrets.
- Logs must never print token values.
