# Required repository secrets

Add these under Settings → Secrets and variables → Actions:

## Required for the first Quality Gate
- `PRIVATE_REPO_TOKEN` — fine-grained PAT restricted to `mojo72549-arch/shorts-agent-studio` with Contents: Read.

## Required for the later production stage
- `PAGES_DEPLOY_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `PEXELS_API_KEY`
- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `HF_TOKEN`

## Optional because fallbacks exist
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `ELEVENLABS_GERMAN_VOICE_ID`
- `YOUTUBE_API_KEY`

Never store secret values in repository files or logs.
