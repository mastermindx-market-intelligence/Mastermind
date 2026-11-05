#!/usr/bin/env python3
"""Run one bounded Slack -> Google Drive retention archive sweep."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integrations.slack_archive.archive import SlackDriveArchiver
from integrations.slack_archive.google_drive import (
    DriveEffectUnknown,
    GoogleDriveArchiveClient,
    GoogleOAuthCredentials,
)
from integrations.slack_archive.slack_api import SlackApiError, SlackArchiveClient


def _read_secret_text(path: Path, *, label: str) -> str:
    try:
        st = path.stat()
    except OSError as exc:
        raise RuntimeError(f"{label}_SECRET_UNAVAILABLE") from exc
    if not stat.S_ISREG(st.st_mode):
        raise RuntimeError(f"{label}_SECRET_NOT_REGULAR_FILE")
    if os.name == "posix" and stat.S_IMODE(st.st_mode) & 0o077:
        raise RuntimeError(f"{label}_SECRET_PERMISSIONS_REFUSED")
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"{label}_SECRET_UNAVAILABLE") from exc
    if not value:
        raise RuntimeError(f"{label}_SECRET_EMPTY")
    return value


def _read_google_credentials(path: Path) -> GoogleOAuthCredentials:
    text = _read_secret_text(path, label="GOOGLE_OAUTH")
    try:
        raw: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_OAUTH_SECRET_INVALID_JSON") from exc
    if not isinstance(raw, dict):
        raise RuntimeError("GOOGLE_OAUTH_SECRET_INVALID_JSON")
    try:
        return GoogleOAuthCredentials.from_mapping(raw)
    except ValueError as exc:
        raise RuntimeError("GOOGLE_OAUTH_SECRET_INVALID") from exc


def _safe_error(exc: BaseException) -> str:
    if isinstance(exc, DriveEffectUnknown):
        return str(exc) or "DRIVE_EFFECT_UNKNOWN"
    if isinstance(exc, SlackApiError):
        return f"SLACK_{exc.code.upper()}"
    text = str(exc)
    if text and len(text) <= 160 and all(ord(ch) >= 32 for ch in text):
        return text
    return type(exc).__name__.upper()


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slack-token-file", required=True, type=Path)
    parser.add_argument("--google-oauth-file", required=True, type=Path)
    parser.add_argument("--drive-root-folder-id")
    parser.add_argument("--root-name", default="Mastermind Slack Archive")
    parser.add_argument("--lookback-days", type=int, default=100)
    parser.add_argument("--max-file-mib", type=int, default=2048)
    args = parser.parse_args(argv)

    if args.lookback_days <= 0 or args.lookback_days > 3660:
        _emit({"schema": "mastermind.slack_drive_archive.run.v1", "ok": False, "error": "LOOKBACK_DAYS_REFUSED"})
        return 2
    if args.max_file_mib <= 0 or args.max_file_mib > 10240:
        _emit({"schema": "mastermind.slack_drive_archive.run.v1", "ok": False, "error": "MAX_FILE_SIZE_REFUSED"})
        return 2

    try:
        slack_token = _read_secret_text(args.slack_token_file, label="SLACK")
        google_credentials = _read_google_credentials(args.google_oauth_file)
        slack = SlackArchiveClient(
            token=slack_token,
            max_file_bytes=args.max_file_mib * 1024 * 1024,
        )
        drive = GoogleDriveArchiveClient(
            credentials=google_credentials,
            root_folder_id=args.drive_root_folder_id,
        )
        archiver = SlackDriveArchiver(slack=slack, drive=drive, root_name=args.root_name)
        receipt, _stats = archiver.run(lookback_days=args.lookback_days)
    except Exception as exc:  # bounded CLI boundary; response is secret-safe.
        _emit(
            {
                "schema": "mastermind.slack_drive_archive.run.v1",
                "ok": False,
                "error": _safe_error(exc),
            }
        )
        return 1

    receipt = dict(receipt)
    receipt["ok"] = True
    _emit(receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
