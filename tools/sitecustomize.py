from __future__ import annotations

"""Narrow CPython startup hooks for TAYVORIQ control-plane tools."""

import os
import sys
from pathlib import Path


if Path(sys.argv[0]).name == "tayvoriq_telegram_progress_v1.py":
    import tayvoriq_telegram_generation_truth_guard as _generation_guard

    _ORIGINAL_READ_TEXT = Path.read_text
    _REQUEST_ID = str(os.getenv("SOURCE_REQUEST_ID_PIN") or "").strip()
    _CURRENT_RUN_ID = str(os.getenv("GITHUB_RUN_ID") or "").strip()

    def _truthful_read_text(self: Path, *args, **kwargs):
        text = _ORIGINAL_READ_TEXT(self, *args, **kwargs)
        if not (_REQUEST_ID and _CURRENT_RUN_ID):
            return text
        expected_name = f"{_REQUEST_ID}.json"
        if self.name != expected_name or self.parent.name != "requests":
            return text
        return _generation_guard.sanitize_request_snapshot(text, _CURRENT_RUN_ID)

    Path.read_text = _truthful_read_text  # type: ignore[method-assign]
