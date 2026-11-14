import json
import os
from pathlib import Path

from tayvoriq_send_telegram import _telegram_video_request

workspace = Path(os.environ["GITHUB_WORKSPACE"])
evidence = json.loads((workspace / "replay/binding.json").read_text())
video = Path("site/tayvoriq/runs") / evidence["run_id"] / "short_tiktok.mp4"
page = f'{os.environ["GITHUB_SERVER_URL"]}/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{evidence["run_id"]}'
try:
    response = _telegram_video_request(
        os.environ["TELEGRAM_BOT_TOKEN"],
        video_path=video,
        payload={
            "chat_id": os.environ["TELEGRAM_CHAT_ID"],
            "caption": f'TAYVORIQ · Geprüftes Referenzvideo\nAuftrag {evidence["request_id"]}\nReview-Seite und beide Fassungen im GitHub-Artefakt.',
            "supports_streaming": True,
            "reply_markup": {"inline_keyboard": [[{"text": "Review-Artefakt", "url": page}]]},
        },
    )
except Exception as exc:
    raise SystemExit(f"TELEGRAM_REFERENCE_DELIVERY_FAILED:{type(exc).__name__}") from None
message_id = response.get("message_id")
if type(message_id) is not int or message_id <= 0 or not (response.get("video") or {}).get("file_id"):
    raise SystemExit("TELEGRAM_REFERENCE_DELIVERY_UNCONFIRMED")
evidence["telegram_message_id"] = message_id
evidence["quality_gate"] = "passed"
(workspace / "replay/telegram-receipt.json").write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
print(f'TELEGRAM_REVIEW_DELIVERED:{evidence["request_id"]}:{message_id}')
