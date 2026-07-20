#!/usr/bin/env python3
"""Create the three GitHub secrets required for YouTube uploads.

Run this script only on your own computer. The generated file contains a
refresh token and must never be committed to GitHub.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "client_secret_json",
        type=Path,
        help="Downloaded OAuth Desktop client JSON from Google Cloud",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("youtube-github-secrets.json"),
        help="Local output file containing the three GitHub secret values",
    )
    args = parser.parse_args()

    if not args.client_secret_json.is_file():
        raise SystemExit(f"File not found: {args.client_secret_json}")

    raw = json.loads(args.client_secret_json.read_text(encoding="utf-8"))
    client = raw.get("installed") or raw.get("web")
    if not client:
        raise SystemExit("The JSON does not contain an OAuth client configuration.")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(args.client_secret_json),
        scopes=[SCOPE],
    )
    credentials = flow.run_local_server(
        host="localhost",
        port=0,
        authorization_prompt_message=(
            "A browser window will open. Sign in with the Google account that owns "
            "the TAYVORIQ YouTube channel and approve video uploads."
        ),
        success_message="YouTube authorization completed. You can close this window.",
        open_browser=True,
        access_type="offline",
        prompt="consent",
    )

    if not credentials.refresh_token:
        raise SystemExit(
            "Google returned no refresh token. Revoke the app grant and run again "
            "with consent enabled."
        )

    payload = {
        "YOUTUBE_CLIENT_ID": client["client_id"],
        "YOUTUBE_CLIENT_SECRET": client["client_secret"],
        "YOUTUBE_REFRESH_TOKEN": credentials.refresh_token,
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Created: {args.output.resolve()}")
    print("Copy each value into the matching GitHub repository secret.")
    print("Delete this local file after the GitHub secrets have been saved.")


if __name__ == "__main__":
    main()
