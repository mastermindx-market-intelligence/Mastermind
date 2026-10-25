"""Append-only local JSONL usage ledger. Rows never contain credential material."""

from __future__ import annotations

import json
import os
import stat
import threading
from collections.abc import Mapping
from pathlib import Path


class MeterError(RuntimeError):
    """The usage ledger could not be written safely."""


USAGE_FIELDS = (
    "schema",
    "ts",
    "profile",
    "role",
    "provider_id",
    "requested_model",
    "served_model",
    "turn_id",
    "effect",
    "http_status",
    "outcome",
    "replayed",
    "failover_from",
    "attempt_index",
    "backoff_seconds",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "wall_time_ms",
    "quota_debit",
    "account",
    "weekly_reset",
    "tool_calls",
    "executive_admission",
    "capacity_claimed",
)

_lock = threading.Lock()


class UsageMeter:
    def __init__(self, path: Path, secrets: list[str] | None = None) -> None:
        self.path = Path(path)
        self.secrets = secrets if secrets is not None else []

    def write(self, row: Mapping[str, object]) -> None:
        unknown = set(row) - set(USAGE_FIELDS)
        if unknown:
            raise MeterError("usage record contained an unexpected field")
        missing = [field for field in USAGE_FIELDS if field not in row]
        if missing:
            raise MeterError("usage record omitted a required field")
        payload = {field: _jsonable(row[field]) for field in USAGE_FIELDS}
        encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n"
        self._reject_secrets(encoded)
        if "\n" in encoded[:-1]:
            raise MeterError("usage record is invalid")
        data = encoded.encode("ascii")
        with _lock:
            fd = _open_ledger(self.path)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)

    def _reject_secrets(self, encoded: str) -> None:
        for secret in self.secrets:
            if secret and secret in encoded:
                raise MeterError("usage record contained credential material")


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise MeterError("usage record is invalid")
        return value
    text = str(value)
    if any(ch in text for ch in "\r\n\x00"):
        raise MeterError("usage record is invalid")
    if len(text) > 256:
        raise MeterError("usage record is invalid")
    return text


def _open_ledger(path: Path) -> int:
    parent = path.parent
    if not parent.is_dir():
        raise MeterError("usage ledger directory is unavailable")
    flags = os.O_WRONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        fd = os.open(path, flags | os.O_APPEND)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            os.close(fd)
            raise MeterError("usage ledger is not a private file")
        return fd
    try:
        os.fchmod(fd, 0o600)
        info = os.fstat(fd)
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise MeterError("usage ledger is not a private file")
    except Exception:
        os.close(fd)
        raise
    return fd
