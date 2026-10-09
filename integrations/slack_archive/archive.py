"""Slack-to-Drive archival orchestration.

The data model and merge primitives live in :mod:`archive_model`; this module
keeps the bounded Slack -> Drive run readable and independently reviewable.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import tempfile
from pathlib import Path
from typing import Any, Mapping

from integrations.slack_archive.archive_model import (
    ARCHIVE_SCHEMA,
    RUN_RECEIPT_SCHEMA,
    ArchiveRunStats,
    DriveArchiveSink,
    SlackArchiveSource,
    _bundle_logical_key,
    _conversation_label,
    _conversation_type,
    _day_for_ts,
    _file_ids,
    _file_logical_key,
    _iso,
    _safe_name,
    _sanitize_message,
    _set_archived_file,
    _slack_ts_epoch,
    _utc_now,
    merge_daily_bundle,
    merge_message_record,
)


class SlackDriveArchiver:
    def __init__(
        self,
        *,
        slack: SlackArchiveSource,
        drive: DriveArchiveSink,
        root_name: str = "Mastermind Slack Archive",
    ) -> None:
        self._slack = slack
        self._drive = drive
        self._root_name = root_name

    def run(self, *, lookback_days: int, now: dt.datetime | None = None) -> tuple[dict[str, Any], ArchiveRunStats]:
        if not isinstance(lookback_days, int) or isinstance(lookback_days, bool) or lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        started = now.astimezone(dt.timezone.utc) if now is not None else _utc_now()
        observed_at = _iso(started)
        oldest_epoch = started.timestamp() - (lookback_days * 86400)
        oldest = f"{oldest_epoch:.6f}"

        identity = self._slack.auth_test()
        workspace_id = identity.get("team_id")
        if not isinstance(workspace_id, str) or not workspace_id:
            raise RuntimeError("SLACK_ARCHIVE_WORKSPACE_ID_MISSING")

        root_id = self._drive.ensure_root(name=self._root_name)
        workspace_id_folder = self._drive.ensure_folder(
            logical_key=f"workspace:v1:{workspace_id}",
            name=_safe_name(f"workspace--{workspace_id}", fallback=workspace_id),
            parent_id=root_id,
        )
        workspace_files_folder = self._drive.ensure_folder(
            logical_key=f"files:v1:{workspace_id}",
            name="files",
            parent_id=workspace_id_folder,
        )

        stats = ArchiveRunStats()
        conversations = list(self._slack.list_conversations())
        for conversation in conversations:
            stats = stats.bump(conversations_seen=1)
            channel_id = conversation.get("id")
            if not isinstance(channel_id, str) or not channel_id:
                raise RuntimeError("SLACK_ARCHIVE_CONVERSATION_ID_INVALID")

            try:
                roots = list(self._slack.iter_history(channel_id=channel_id, oldest=oldest))
            except Exception as exc:
                code = getattr(exc, "code", "")
                if code in {"not_in_channel", "channel_not_found"}:
                    stats = stats.bump(conversations_inaccessible=1)
                    continue
                raise

            by_ts: dict[str, Mapping[str, Any]] = {}
            for raw in roots:
                ts = raw.get("ts")
                if isinstance(ts, str):
                    by_ts[ts] = raw
            for root in roots:
                ts = root.get("ts")
                reply_count = root.get("reply_count")
                if isinstance(ts, str) and isinstance(reply_count, int) and reply_count > 0:
                    try:
                        replies = self._slack.iter_replies(channel_id=channel_id, thread_ts=ts)
                        for reply in replies:
                            reply_ts = reply.get("ts")
                            if isinstance(reply_ts, str):
                                by_ts.setdefault(reply_ts, reply)
                    except Exception as exc:
                        code = getattr(exc, "code", "")
                        if code not in {"thread_not_found", "message_not_found", "channel_not_found", "not_in_channel"}:
                            raise

            if not by_ts:
                stats = stats.bump(conversations_archived=1)
                continue

            conversation_folder = self._drive.ensure_folder(
                logical_key=f"conversation:v1:{workspace_id}:{channel_id}",
                name=_conversation_label(conversation),
                parent_id=workspace_id_folder,
            )
            grouped: dict[str, list[Mapping[str, Any]]] = {}
            for raw in by_ts.values():
                day = _day_for_ts(str(raw["ts"]))
                grouped.setdefault(day, []).append(raw)
                stats = stats.bump(messages_observed=1, files_observed=len(_file_ids(raw)))

            for day, observed in sorted(grouped.items()):
                year, month, _date = day.split("-", 2)
                year_folder = self._drive.ensure_folder(
                    logical_key=f"year:v1:{workspace_id}:{channel_id}:{year}",
                    name=year,
                    parent_id=conversation_folder,
                )
                month_folder = self._drive.ensure_folder(
                    logical_key=f"month:v1:{workspace_id}:{channel_id}:{year}:{month}",
                    name=month,
                    parent_id=year_folder,
                )
                bundle_key = _bundle_logical_key(workspace_id, channel_id, day)
                existing_meta = self._drive.find_file(logical_key=bundle_key, parent_id=month_folder)
                existing_bundle = (
                    self._drive.read_json(file_id=str(existing_meta["id"]))
                    if isinstance(existing_meta, Mapping) and isinstance(existing_meta.get("id"), str)
                    else None
                )
                bundle, added = merge_daily_bundle(
                    existing_bundle,
                    workspace_id=workspace_id,
                    conversation=conversation,
                    day=day,
                    observed_messages=observed,
                    observed_at=observed_at,
                )
                stats = stats.bump(message_versions_added=added)
                records = {
                    str(record["ts"]): record
                    for record in bundle["messages"]
                    if isinstance(record, dict) and isinstance(record.get("ts"), str)
                }

                for raw in observed:
                    ts = str(raw["ts"])
                    record = records[ts]
                    for file_id in _file_ids(raw):
                        logical_key = _file_logical_key(workspace_id, file_id)
                        existing_file = self._drive.find_file(logical_key=logical_key, parent_id=workspace_files_folder)
                        if isinstance(existing_file, Mapping) and isinstance(existing_file.get("id"), str):
                            _set_archived_file(
                                record,
                                {
                                    "slack_file_id": file_id,
                                    "drive_file_id": str(existing_file["id"]),
                                    "status": "ARCHIVED",
                                },
                            )
                            stats = stats.bump(files_reused=1)
                            continue

                        try:
                            info = self._slack.file_info(file_id=file_id)
                        except Exception as exc:
                            code = getattr(exc, "code", "")
                            if code not in {"file_not_found", "not_visible"}:
                                raise
                            _set_archived_file(
                                record,
                                {
                                    "slack_file_id": file_id,
                                    "status": "UNAVAILABLE",
                                    "reason": str(code).upper(),
                                },
                            )
                            stats = stats.bump(files_unavailable=1)
                            continue
                        url = info.get("url_private_download") or info.get("url_private")
                        expected_size = info.get("size")
                        if not isinstance(expected_size, int) or expected_size < 0:
                            expected_size = None
                        if not isinstance(url, str) or not url:
                            _set_archived_file(
                                record,
                                {
                                    "slack_file_id": file_id,
                                    "status": "UNAVAILABLE",
                                    "reason": "NO_DOWNLOAD_URL",
                                },
                            )
                            stats = stats.bump(files_unavailable=1)
                            continue

                        original_name = info.get("name")
                        safe_name = _safe_name(
                            str(original_name) if isinstance(original_name, str) else file_id,
                            fallback=file_id,
                            limit=180,
                        )
                        archive_name = f"{file_id}--{safe_name}"
                        mime_type = info.get("mimetype")
                        if not isinstance(mime_type, str) or not mime_type:
                            mime_type = "application/octet-stream"
                        with tempfile.TemporaryDirectory(prefix="mmx-slack-archive-") as tmp:
                            path = Path(tmp) / "payload"
                            download = self._slack.download_file(
                                url=url,
                                destination=path,
                                expected_size=expected_size,
                            )
                            sha256 = download.get("sha256")
                            if not isinstance(sha256, str) or len(sha256) != 64:
                                sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                            uploaded = self._drive.upload_file(
                                logical_key=logical_key,
                                name=archive_name,
                                parent_id=workspace_files_folder,
                                source_path=path,
                                mime_type=mime_type,
                                sha256=sha256,
                            )
                        drive_file_id = uploaded.get("id")
                        if not isinstance(drive_file_id, str) or not drive_file_id:
                            raise RuntimeError("DRIVE_ARCHIVE_FILE_ID_MISSING")
                        _set_archived_file(
                            record,
                            {
                                "slack_file_id": file_id,
                                "drive_file_id": drive_file_id,
                                "sha256": sha256,
                                "status": "ARCHIVED",
                            },
                        )
                        stats = stats.bump(files_uploaded=1)

                bundle["messages"] = [records[key] for key in sorted(records, key=_slack_ts_epoch)]
                self._drive.upsert_json(
                    logical_key=bundle_key,
                    name=f"{day}.json",
                    parent_id=month_folder,
                    document=bundle,
                )
                stats = stats.bump(bundles_written=1)

            stats = stats.bump(conversations_archived=1)

        finished = _utc_now()
        receipt = {
            "schema": RUN_RECEIPT_SCHEMA,
            "workspace_id": workspace_id,
            "drive_root_folder_id": root_id,
            "lookback_days": lookback_days,
            "started_at": observed_at,
            "finished_at": _iso(finished),
            "stats": stats.__dict__,
        }
        return receipt, stats


__all__ = [
    "ARCHIVE_SCHEMA",
    "RUN_RECEIPT_SCHEMA",
    "ArchiveRunStats",
    "DriveArchiveSink",
    "SlackArchiveSource",
    "SlackDriveArchiver",
    "merge_daily_bundle",
    "merge_message_record",
]
