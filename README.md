# TAYVORIQ Control Plane

Public orchestration repository for the private TAYVORIQ implementation.

## Golden Path V4 project standard

The binding architecture, recovery, notification, project-reporting and morning/evening serialization standard is documented in:

- [`docs/TAYVORIQ_GOLDEN_PATH_V4_PROJECT_STANDARD.md`](docs/TAYVORIQ_GOLDEN_PATH_V4_PROJECT_STANDARD.md)

All future Golden Path, Recovery, Telegram notification and slot-orchestration changes must be evaluated against that standard. Quality gates must not be weakened.

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
- `PRIVATE_REPO_WAKE_TOKEN` – for immediate Contabo research and production starts, a separately scoped token restricted to `mojo72549-arch/shorts-agent-studio` with `Contents: Read and write`. It writes the request-bound `.automation/contabo-research-wakeup.json` or `.automation/contabo-wakeup.json` in Studio. No Actions dispatch permission is required. The existing read token stays read-only. If wake access is unavailable, the scheduled consumer can still accept the queue; only a bound worker receipt confirms that the worker started.
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

## Daily production and manual preproduction

The Agent V2 clock opens the morning slot at 05:30 and the evening slot at 19:00 in Europe/Berlin. The Control Center and Telegram can also start a fresh search and accept a manually selected topic. A production request already assigned to that Berlin day and slot takes precedence over the automatic render. A portfolio entry by itself carries no scheduled release date.

For a free slot the clock can reserve the highest-ranked eligible Contabo story for production. It binds the private worker receipt, source records and editorial checks to a single request named `slot-YYYYMMDD-morning` or `slot-YYYYMMDD-evening`. Scheduled authority permits rendering for review only. The dispatcher rechecks slot ownership before claiming work. News without sufficient evidence remains in the existing bounded research recovery.

Review delivery still requires the final quality gates and a verified Telegram receipt. The operator can release the approved video from Telegram or the Control Center. The current YouTube publisher uploads the approved master. TikTok currently receives a downloadable video and caption for manual posting.
