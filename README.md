# TAYVORIQ Control Plane

Public orchestration repository for the private TAYVORIQ implementation.

## Golden Path

1. Compile, Preflight and complete tests.
2. Exactly one full production controller run.
3. 9:16 video with speech, matching visuals, subtitles, YouTube and TikTok metadata.
4. Publication and visual quality gates.
5. Publish the GitHub Pages review.
6. Telegram sends the review link with **Freigeben** and **Ablehnen**.

## Required repository secrets

The public control plane cannot read secrets from the private repository automatically. Configure these under **Settings → Secrets and variables → Actions**:

- `PRIVATE_REPO_TOKEN` – fine-grained PAT restricted to `mojo72549-arch/shorts-agent-studio`, permission `Contents: Read`.
- `PAGES_DEPLOY_TOKEN` – token with write access to `mojo72549-arch/mind-reset-daily`.
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `PEXELS_API_KEY`
- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `HF_TOKEN`
- `ELEVENLABS_API_KEY` – optional; Edge Neural TTS remains the fallback.
- `ELEVENLABS_VOICE_ID` – optional.
- `ELEVENLABS_GERMAN_VOICE_ID` – optional.
- `YOUTUBE_API_KEY` – optional where required by source probes.

## Safe first run

The `TAYVORIQ Control Plane Smoke` workflow validates the private checkout and complete quality gate without starting production.

After it is green, run `TAYVORIQ Golden Path` with:

- `mode = full`
- `trend_scope = auto_scope`
- `topic =` empty

No five-minute scheduler is enabled. The control plane starts only deliberately until the first complete end-to-end success is confirmed.
