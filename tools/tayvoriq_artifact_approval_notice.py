"""Confirm the YouTube receipt and hand the TikTok upload package to Telegram."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests


def main():
    job = Path(sys.argv[1])
    youtube = json.loads((job / 'publish_result.json').read_text())['results']['youtube_shorts']
    caption = (job / 'tiktok_caption.txt').read_text().strip()
    text = f'YouTube veröffentlicht\n{youtube["url"]}\n\nTikTok-Uploadpaket zur manuellen Veröffentlichung\n{caption}'
    token = os.environ['TELEGRAM_BOT_TOKEN']
    try:
        with (job / 'short_tiktok.mp4').open('rb') as f:
            response = requests.post(f'https://api.telegram.org/bot{token}/sendDocument',
                                     data={'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'caption': text[:1024]},
                                     files={'document': ('short_tiktok.mp4', f, 'video/mp4')}, timeout=(10, 180))
        response.raise_for_status()
        payload = response.json()
        result = payload.get('result', {})
        if payload.get('ok') is not True or type(result.get('message_id')) is not int or not result.get('document'):
            raise ValueError('unconfirmed')
    except (requests.RequestException, ValueError, OSError) as exc:
        raise RuntimeError(f'TIKTOK_PACKAGE_DELIVERY_UNCONFIRMED:{type(exc).__name__}') from None
    print(f'TIKTOK_PACKAGE_DELIVERED:{result["message_id"]}')


if __name__ == '__main__':
    main()
