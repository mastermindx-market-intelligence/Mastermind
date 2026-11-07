"""Slack-to-Drive archival orchestration.

This module deliberately owns no scheduler, token discovery, Slack write path,
queue, database, or retry plane.  One bounded run reads the currently visible
Slack history and merges it into Drive-owned daily archive bundles.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

ARCHIVE_SCHEMA = "mastermind.slack_drive_archive.daily.v1"
RUN_RECEIPT_SCHEMA = "mastermind.slack_drive_archive.run.v1"
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


class SlackArchiveSource(Protocol):
    def auth_test(self) -> Mapping[str, Any]: ...
    def list_conversations(self) -> Iterable[Mapping[str, Any]]: ...
    def iter_history(self, *, channel_id: str, oldest: str) -> Iterable[Mapping[str, Any]]: ...
    def iter_replies(self, *, channel_id: str, thread_ts: str) -> Iterable[Mapping[str, Any]]: ...
    def file_info(self, *, file_id: str) -> Mapping[str, Any]: ...
    def download_file(self, *, url: str, destination: Path, expected_size: int | None) -> Mapping[str, Any]: ...


class DriveArchiveSink(Protocol):
    def ensure_root(self, *, name: str) -> str: ...
    def ensure_folder(self, *, logical_key: str, name: str, parent_id: str) -> str: ...
    def find_file(self, *, logical_key: str, parent_id: str | None = None) -> Mapping[str, Any] | None: ...
    def read_json(self, *, file_id: str) -> Mapping[str, Any]: ...
    def upsert_json(
        self,
        *,
        logical_key: str,
        name: str,
        parent_id: str,
        document: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...
    def upload_file(
        self,
        *,
        logical_key: str,
        name: str,
        parent_id: str,
        source_path: Path,
        mime_type: str,
        sha256: str,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ArchiveRunStats:
    conversations_seen: int = 0
    conversations_archived: int = 0
    conversations_inaccessible: int = 0
    messages_observed: int = 0
    message_versions_added: int = 0
    bundles_written: int = 0
    files_observed: int = 0
    files_uploaded: int = 0
    files_reused: int = 0
    files_unavailable: int = 0

    def bump(self, **changes: int) -> "ArchiveRunStats":
        values = self.__dict__.copy()
        for key, delta in changes.items():
            values[key] = int(values[key]) + int(delta)
        return ArchiveRunStats(**values)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _slack_ts_epoch(ts: str) -> float:
    return float(ts)


def _day_for_ts(ts: str) -> str:
    instant = dt.datetime.fromtimestamp(_slack_ts_epoch(ts), tz=dt.timezone.utc)
    return instant.date().isoformat()


def _safe_name(value: str, *, fallback: str, limit: int = 120) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", value).strip(" ._")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or fallback)[:limit]


def _conversation_type(raw: Mapping[str, Any]) -> str:
    if raw.get("is_im") is True:
        return "im"
    if raw.get("is_mpim") is True:
        return "mpim"
    if raw.get("is_private") is True:
        return "private_channel"
    return "public_channel"


def _conversation_label(raw: Mapping[str, Any]) -> str:
    channel_id = str(raw.get("id") or "unknown")
    name = raw.get("name")
    if isinstance(name, str) and name:
        return _safe_name(f"{name}--{channel_id}", fallback=channel_id)
    if raw.get("is_im") is True:
        peer = raw.get("user")
        peer_label = str(peer) if isinstance(peer, str) and peer else "unknown-user"
        return _safe_name(f"dm--{peer_label}--{channel_id}", fallback=channel_id)
    return _safe_name(f"{_conversation_type(raw)}--{channel_id}", fallback=channel_id)


def _sanitize_file(raw: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "id",
        "name",
        "title",
        "mimetype",
        "filetype",
        "pretty_type",
        "mode",
        "size",
        "timestamp",
        "created",
        "user",
        "is_external",
        "external_type",
    )
    result: dict[str, Any] = {}
    for key in allowed:
        value = raw.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = value
    return result


def _sanitize_message(raw: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "type",
        "subtype",
        "ts",
        "thread_ts",
        "user",
        "bot_id",
        "username",
        "text",
        "client_msg_id",
        "reply_count",
        "reply_users_count",
        "latest_reply",
        "blocks",
        "attachments",
        "reactions",
    )
    result: dict[str, Any] = {}
    for key in allowed:
        if key in raw:
            value = raw[key]
            try:
                json.dumps(value, allow_nan=False)
            except (TypeError, ValueError):
                continue
            result[key] = value
    edited = raw.get("edited")
    if isinstance(edited, Mapping):
        result["edited"] = {
            key: value
            for key, value in edited.items()
            if key in {"user", "ts"} and isinstance(value, str)
        }
    raw_files = raw.get("files")
    if isinstance(raw_files, list):
        result["files"] = [
            _sanitize_file(item) for item in raw_files if isinstance(item, Mapping)
        ]
    return result


def _version_signature(version: Mapping[str, Any]) -> tuple[str, str | None]:
    text = version.get("text")
    edited_ts = version.get("edited_ts")
    return (str(text) if isinstance(text, str) else "", str(edited_ts) if isinstance(edited_ts, str) else None)


def merge_message_record(
    existing: Mapping[str, Any] | None,
    raw: Mapping[str, Any],
    *,
    observed_at: str,
) -> tuple[dict[str, Any], bool]:
    """Merge one observed Slack message while retaining prior text versions."""
    ts = raw.get("ts")
    if not isinstance(ts, str) or not ts:
        raise ValueError("message missing ts")
    text = raw.get("text")
    text_value = text if isinstance(text, str) else ""
    edited_raw = raw.get("edited")
    edited_ts = edited_raw.get("ts") if isinstance(edited_raw, Mapping) else None
    if not isinstance(edited_ts, str):
        edited_ts = None

    prior_versions: list[dict[str, Any]] = []
    first_observed_at = observed_at
    prior_files: list[dict[str, Any]] = []
    if isinstance(existing, Mapping):
        first = existing.get("first_observed_at")
        if isinstance(first, str) and first:
            first_observed_at = first
        versions = existing.get("versions")
        if isinstance(versions, list):
            for version in versions:
                if isinstance(version, Mapping):
                    prior_versions.append(dict(version))
        files = existing.get("archived_files")
        if isinstance(files, list):
            prior_files = [dict(item) for item in files if isinstance(item, Mapping)]

    candidate = {
        "observed_at": observed_at,
        "edited_ts": edited_ts,
        "text": text_value,
    }
    added_version = not prior_versions or _version_signature(prior_versions[-1]) != _version_signature(candidate)
    versions = prior_versions + ([candidate] if added_version else [])

    record = {
        "ts": ts,
        "thread_ts": raw.get("thread_ts") if isinstance(raw.get("thread_ts"), str) else None,
        "user": raw.get("user") if isinstance(raw.get("user"), str) else None,
        "subtype": raw.get("subtype") if isinstance(raw.get("subtype"), str) else None,
        "first_observed_at": first_observed_at,
        "last_observed_at": observed_at,
        "versions": versions,
        "latest": _sanitize_message(raw),
        "archived_files": prior_files,
    }
    return record, added_version


def merge_daily_bundle(
    existing: Mapping[str, Any] | None,
    *,
    workspace_id: str,
    conversation: Mapping[str, Any],
    day: str,
    observed_messages: Iterable[Mapping[str, Any]],
    observed_at: str,
) -> tuple[dict[str, Any], int]:
    existing_records: dict[str, Mapping[str, Any]] = {}
    created_at = observed_at
    if isinstance(existing, Mapping):
        if existing.get("schema") != ARCHIVE_SCHEMA:
            raise ValueError("archive schema mismatch")
        if existing.get("workspace_id") != workspace_id or existing.get("day") != day:
            raise ValueError("archive identity mismatch")
        created = existing.get("created_at")
        if isinstance(created, str) and created:
            created_at = created
        raw_messages = existing.get("messages")
        if not isinstance(raw_messages, list):
            raise ValueError("archive messages invalid")
        for record in raw_messages:
            if not isinstance(record, Mapping):
                raise ValueError("archive record invalid")
            ts = record.get("ts")
            if not isinstance(ts, str) or ts in existing_records:
                raise ValueError("archive record identity invalid")
            existing_records[ts] = record

    versions_added = 0
    for raw in observed_messages:
        ts = raw.get("ts")
        if not isinstance(ts, str):
            raise ValueError("message missing ts")
        merged, added = merge_message_record(existing_records.get(ts), raw, observed_at=observed_at)
        existing_records[ts] = merged
        versions_added += int(added)

    ordered = [existing_records[key] for key in sorted(existing_records, key=_slack_ts_epoch)]
    conversation_projection = {
        "id": str(conversation.get("id") or ""),
        "name": conversation.get("name") if isinstance(conversation.get("name"), str) else None,
        "type": _conversation_type(conversation),
        "is_archived": bool(conversation.get("is_archived")),
    }
    return (
        {
            "schema": ARCHIVE_SCHEMA,
            "workspace_id": workspace_id,
            "conversation": conversation_projection,
            "day": day,
            "created_at": created_at,
            "updated_at": observed_at,
            "messages": ordered,
        },
        versions_added,
    )


def _file_logical_key(workspace_id: str, file_id: str) -> str:
    return f"slack-file:v1:{workspace_id}:{file_id}"


def _bundle_logical_key(workspace_id: str, channel_id: str, day: str) -> str:
    return f"slack-bundle:v1:{workspace_id}:{channel_id}:{day}"


def _file_ids(raw: Mapping[str, Any]) -> list[str]:
    files = raw.get("files")
    if not isinstance(files, list):
        return []
    result: list[str] = []
    for item in files:
        if isinstance(item, Mapping):
            file_id = item.get("id")
            if isinstance(file_id, str) and file_id and file_id not in result:
                result.append(file_id)
    return result


def _set_archived_file(record: dict[str, Any], archived: Mapping[str, Any]) -> None:
    items = record.setdefault("archived_files", [])
    if not isinstance(items, list):
        raise ValueError("archived_files invalid")
    file_id = archived.get("slack_file_id")
    retained = [
        item
        for item in items
        if not (isinstance(item, Mapping) and item.get("slack_file_id") == file_id)
    ]
    retained.append(dict(archived))
    retained.sort(key=lambda item: str(item.get("slack_file_id") or ""))
    record["archived_files"] = retained


__all__ = [
    "ARCHIVE_SCHEMA",
    "RUN_RECEIPT_SCHEMA",
    "ArchiveRunStats",
    "DriveArchiveSink",
    "SlackArchiveSource",
    "_bundle_logical_key",
    "_conversation_label",
    "_conversation_type",
    "_day_for_ts",
    "_file_ids",
    "_file_logical_key",
    "_iso",
    "_safe_name",
    "_sanitize_message",
    "_set_archived_file",
    "_slack_ts_epoch",
    "_utc_now",
    "merge_daily_bundle",
    "merge_message_record",
]
