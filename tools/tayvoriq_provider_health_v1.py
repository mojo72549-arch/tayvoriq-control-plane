"""Persist provider cooldowns without credentials or generated content."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from email.utils import parsedate_to_datetime
from pathlib import Path


def read(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("PROVIDER_STATE_INVALID")
    return value


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def http_failure(exc: Exception) -> tuple[int, dict]:
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "code", None)
        if code in {402, 429}:
            return code, {str(k).lower(): str(v) for k, v in (getattr(current, "headers", {}) or {}).items()}
        current = current.__cause__ or current.__context__
    match = re.search(r"\b(402|429)\b", str(exc))
    return (int(match.group(1)), {}) if match else (0, {})


def retry_at(headers: dict, now: float) -> float:
    deadlines = []
    hint = headers.get("retry-after", "")
    if hint:
        try:
            deadlines.append(now + max(1, float(hint)))
        except ValueError:
            try:
                deadlines.append(parsedate_to_datetime(hint).timestamp())
            except (ValueError, TypeError, OverflowError):
                pass
    for name in ("requests", "tokens"):
        hint = headers.get(f"x-ratelimit-reset-{name}", "")
        parts = re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?", hint)
        if parts and any(parts.groups()):
            deadlines.append(now + sum(float(v or 0) * scale for v, scale in zip(parts.groups(), (3600, 60, 1))))
    return max([now + 1] + deadlines) if deadlines else now + 900


class ProviderHealth:
    def __init__(self, path: Path | None = None, *, clock=time.time):
        self.path, self.clock = path, clock
        self.state = read(path) or {"schema": "tayvoriq-provider-health-v1", "providers": {}}
        if self.state.get("schema") != "tayvoriq-provider-health-v1" or not isinstance(self.state.get("providers"), dict):
            raise ValueError("PROVIDER_HEALTH_SCHEMA_INVALID")

    def _save(self):
        if self.path is not None:
            write(self.path, self.state)

    def available(self, provider: str, key: str) -> bool:
        record = self.state["providers"].get(provider) or {}
        fingerprint = hashlib.sha256(key.encode()).hexdigest()
        if record and record.get("credential_fingerprint") != fingerprint:
            self.success(provider)
            record = {}
        return record.get("state") != "PAYMENT_BLOCKED" and float(record.get("retry_at_epoch") or 0) <= self.clock()

    def failure(self, provider: str, key: str, exc: Exception) -> None:
        code, headers = http_failure(exc)
        if code not in {402, 429}:
            return  # A short browser dossier must still allow JSON structuring.
        self.state["providers"][provider] = {
            "state": "PAYMENT_BLOCKED" if code == 402 else "COOLDOWN",
            "http_status": code, "observed_at_epoch": self.clock(),
            "retry_at_epoch": None if code == 402 else retry_at(headers, self.clock()),
            "credential_fingerprint": hashlib.sha256(key.encode()).hexdigest(),
        }
        self._save()

    def success(self, provider: str) -> None:
        self.state["providers"].pop(provider, None)
        self._save()

    def next_retry(self, providers: dict[str, str]) -> float | None:
        deadlines = []
        for provider, key in providers.items():
            if not key:
                continue
            available = self.available(provider, key)
            record = self.state["providers"].get(provider) or {}
            if record.get("state") == "PAYMENT_BLOCKED":
                continue
            deadlines.append(self.clock() + 900 if available else float(record["retry_at_epoch"]))
        return min(deadlines) if deadlines else None
