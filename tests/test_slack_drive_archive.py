from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import pytest

from integrations.slack_archive.archive import (
    ARCHIVE_SCHEMA,
    SlackDriveArchiver,
    merge_daily_bundle,
    merge_message_record,
)
import integrations.slack_archive.google_drive_resumable as drive_resumable

from integrations.slack_archive.google_drive import (
    MULTIPART_MAX_BYTES,
    GoogleDriveArchiveClient,
    GoogleOAuthCredentials,
)
from integrations.slack_archive.slack_api import SlackApiError, SlackArchiveClient


NOW = dt.datetime(2026, 9, 18, 12, 0, tzinfo=dt.timezone.utc)
ROOT_TS = "1789732800.000001"
REPLY_TS = "1789732860.000002"


def test_message_versions_are_append_only() -> None:
    first, added = merge_message_record(
        None,
        {"type": "message", "ts": ROOT_TS, "user": "U123", "text": "first"},
        observed_at="2026-09-18T12:00:00Z",
    )
    assert added is True
    same, added = merge_message_record(
        first,
        {"type": "message", "ts": ROOT_TS, "user": "U123", "text": "first"},
        observed_at="2026-09-18T12:15:00Z",
    )
    assert added is False
    assert len(same["versions"]) == 1

    edited, added = merge_message_record(
        same,
        {
            "type": "message",
            "ts": ROOT_TS,
            "user": "U123",
            "text": "second",
            "edited": {"user": "U123", "ts": "1789732900.000003"},
        },
        observed_at="2026-09-18T12:30:00Z",
    )
    assert added is True
    assert [item["text"] for item in edited["versions"]] == ["first", "second"]
    assert edited["first_observed_at"] == "2026-09-18T12:00:00Z"


def test_daily_bundle_retains_previously_archived_messages_not_in_later_poll() -> None:
    conversation = {"id": "C123", "name": "general", "is_private": False}
    first, _ = merge_daily_bundle(
        None,
        workspace_id="T123",
        conversation=conversation,
        day="2026-09-18",
        observed_messages=[{"type": "message", "ts": ROOT_TS, "user": "U1", "text": "old"}],
        observed_at="2026-09-18T12:00:00Z",
    )
    merged, added = merge_daily_bundle(
        first,
        workspace_id="T123",
        conversation=conversation,
        day="2026-09-18",
        observed_messages=[{"type": "message", "ts": REPLY_TS, "user": "U2", "text": "new"}],
        observed_at="2026-09-18T12:15:00Z",
    )
    assert added == 1
    assert [record["ts"] for record in merged["messages"]] == [ROOT_TS, REPLY_TS]
    assert merged["schema"] == ARCHIVE_SCHEMA


class FakeSlack:
    def __init__(self) -> None:
        self.root_text = "root v1"
        self.inaccessible = False
        self.downloads = 0

    def auth_test(self) -> Mapping[str, Any]:
        return {"team_id": "T12345678"}

    def list_conversations(self) -> Iterable[Mapping[str, Any]]:
        yield {"id": "C12345678", "name": "general", "is_private": False, "is_archived": False}
        if self.inaccessible:
            yield {"id": "G12345678", "name": "private", "is_private": True, "is_archived": False}

    def iter_history(self, *, channel_id: str, oldest: str) -> Iterable[Mapping[str, Any]]:
        assert oldest
        if channel_id == "G12345678":
            raise SlackApiError("not_in_channel")
        yield {
            "type": "message",
            "ts": ROOT_TS,
            "user": "U12345678",
            "text": self.root_text,
            "reply_count": 1,
            "files": [{"id": "F12345678", "name": "evidence.txt", "mimetype": "text/plain", "size": 7}],
        }

    def iter_replies(self, *, channel_id: str, thread_ts: str) -> Iterable[Mapping[str, Any]]:
        assert channel_id == "C12345678"
        assert thread_ts == ROOT_TS
        yield {
            "type": "message",
            "ts": ROOT_TS,
            "user": "U12345678",
            "text": self.root_text,
            "reply_count": 1,
        }
        yield {
            "type": "message",
            "ts": REPLY_TS,
            "thread_ts": ROOT_TS,
            "user": "U87654321",
            "text": "reply",
        }

    def file_info(self, *, file_id: str) -> Mapping[str, Any]:
        assert file_id == "F12345678"
        return {
            "id": file_id,
            "name": "evidence.txt",
            "mimetype": "text/plain",
            "size": 7,
            "url_private_download": "https://files.slack.com/fake",
        }

    def download_file(self, *, url: str, destination: Path, expected_size: int | None) -> Mapping[str, Any]:
        assert url == "https://files.slack.com/fake"
        assert expected_size == 7
        payload = b"archive"
        destination.write_bytes(payload)
        self.downloads += 1
        import hashlib

        return {"size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


class FakeDrive:
    def __init__(self) -> None:
        self.next_id = 1
        self.folders: dict[tuple[str, str], str] = {}
        self.files: dict[tuple[str | None, str], dict[str, Any]] = {}
        self.documents: dict[str, dict[str, Any]] = {}
        self.upload_calls = 0

    def _id(self) -> str:
        value = f"drive-{self.next_id}"
        self.next_id += 1
        return value

    def ensure_root(self, *, name: str) -> str:
        assert name
        return "root-1"

    def ensure_folder(self, *, logical_key: str, name: str, parent_id: str) -> str:
        key = (parent_id, logical_key)
        if key not in self.folders:
            self.folders[key] = self._id()
        return self.folders[key]

    def find_file(self, *, logical_key: str, parent_id: str | None = None) -> Mapping[str, Any] | None:
        item = self.files.get((parent_id, logical_key))
        return copy.deepcopy(item) if item is not None else None

    def read_json(self, *, file_id: str) -> Mapping[str, Any]:
        return copy.deepcopy(self.documents[file_id])

    def upsert_json(
        self,
        *,
        logical_key: str,
        name: str,
        parent_id: str,
        document: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        key = (parent_id, logical_key)
        current = self.files.get(key)
        file_id = str(current["id"]) if current else self._id()
        meta = {"id": file_id, "name": name, "mimeType": "application/json"}
        self.files[key] = meta
        self.documents[file_id] = copy.deepcopy(dict(document))
        return copy.deepcopy(meta)

    def upload_file(
        self,
        *,
        logical_key: str,
        name: str,
        parent_id: str,
        source_path: Path,
        mime_type: str,
        sha256: str,
    ) -> Mapping[str, Any]:
        self.upload_calls += 1
        file_id = self._id()
        meta = {"id": file_id, "name": name, "mimeType": mime_type, "sha256": sha256}
        self.files[(parent_id, logical_key)] = meta
        assert source_path.read_bytes() == b"archive"
        return copy.deepcopy(meta)


def _single_bundle(drive: FakeDrive) -> dict[str, Any]:
    bundles = [doc for doc in drive.documents.values() if doc.get("schema") == ARCHIVE_SCHEMA]
    assert len(bundles) == 1
    return bundles[0]


def test_archiver_reconciles_thread_file_and_later_edit_without_duplicate_file() -> None:
    slack = FakeSlack()
    drive = FakeDrive()
    archiver = SlackDriveArchiver(slack=slack, drive=drive)

    receipt, stats = archiver.run(lookback_days=100, now=NOW)
    assert receipt["workspace_id"] == "T12345678"
    assert stats.messages_observed == 2
    assert stats.message_versions_added == 2
    assert stats.files_uploaded == 1
    assert slack.downloads == 1
    assert drive.upload_calls == 1

    slack.root_text = "root v2"
    _receipt2, stats2 = archiver.run(lookback_days=100, now=NOW + dt.timedelta(minutes=15))
    assert stats2.files_reused == 1
    assert stats2.files_uploaded == 0
    assert drive.upload_calls == 1
    bundle = _single_bundle(drive)
    root = next(record for record in bundle["messages"] if record["ts"] == ROOT_TS)
    assert [item["text"] for item in root["versions"]] == ["root v1", "root v2"]
    assert root["archived_files"][0]["status"] == "ARCHIVED"


def test_archiver_treats_missing_membership_as_lane_local() -> None:
    slack = FakeSlack()
    slack.inaccessible = True
    drive = FakeDrive()
    _receipt, stats = SlackDriveArchiver(slack=slack, drive=drive).run(lookback_days=100, now=NOW)
    assert stats.conversations_seen == 2
    assert stats.conversations_archived == 1
    assert stats.conversations_inaccessible == 1


def test_resumable_transport_has_stdlib_https_connection() -> None:
    assert drive_resumable.http.client.HTTPSConnection is not None


def test_drive_file_metadata_binds_slack_file_sha256() -> None:
    metadata = GoogleDriveArchiveClient._metadata(
        logical_key="slack-file:v1:T123:F123",
        name="F123--evidence.pdf",
        parent_id="folder-files",
        mime_type="application/pdf",
        sha256="a" * 64,
    )
    assert metadata["appProperties"]["mmx_sha256"] == "a" * 64


def test_google_oauth_secret_is_closed_and_fixed_origin() -> None:
    creds = GoogleOAuthCredentials.from_mapping(
        {
            "client_id": "client",
            "client_secret": "secret",
            "refresh_token": "refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    assert creds.client_id == "client"
    with pytest.raises(ValueError):
        GoogleOAuthCredentials.from_mapping(
            {"client_id": "a", "client_secret": "b", "refresh_token": "c", "extra": "no"}
        )
    with pytest.raises(ValueError):
        GoogleOAuthCredentials.from_mapping(
            {
                "client_id": "a",
                "client_secret": "b",
                "refresh_token": "c",
                "token_uri": "https://evil.example/token",
            }
        )


def test_slack_client_has_only_read_api_methods() -> None:
    source = Path(SlackArchiveClient.__module__.replace(".", "/") + ".py")
    # Source path resolution under pytest differs by cwd; inspect through module file instead.
    import integrations.slack_archive.slack_api as module

    text = Path(module.__file__).read_text(encoding="utf-8")
    for write_method in ("chat.postMessage", "chat.update", "chat.delete", "files.delete", "conversations.archive"):
        assert write_method not in text
    client = SlackArchiveClient(token="xoxp-test")
    with pytest.raises(SlackApiError, match="request_refused"):
        client._api_url("chat.postMessage")



def test_drive_resumable_range_parser_is_closed() -> None:
    assert GoogleDriveArchiveClient._next_offset_from_range(None) == 0
    assert GoogleDriveArchiveClient._next_offset_from_range("bytes=0-1048575") == 1048576
    with pytest.raises(Exception, match="DRIVE_RESUMABLE_RANGE_INVALID"):
        GoogleDriveArchiveClient._next_offset_from_range("bytes=8-9")


def test_large_drive_json_uses_resumable_create(monkeypatch: pytest.MonkeyPatch) -> None:
    creds = GoogleOAuthCredentials.from_mapping(
        {"client_id": "a", "client_secret": "b", "refresh_token": "c"}
    )
    client = GoogleDriveArchiveClient(credentials=creds)
    calls: list[str] = []
    monkeypatch.setattr(client, "find_file", lambda **_kwargs: None)
    monkeypatch.setattr(
        client,
        "_create_multipart_bytes",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("multipart must not be used")),
    )

    def resumable(**_kwargs: Any) -> dict[str, Any]:
        calls.append("resumable")
        return {"id": "drive-large"}

    monkeypatch.setattr(client, "_resumable_create_bytes", resumable)
    document = {"payload": "x" * (MULTIPART_MAX_BYTES + 1024)}
    result = client.upsert_json(
        logical_key="large-json",
        name="large.json",
        parent_id="parent",
        document=document,
    )
    assert result["id"] == "drive-large"
    assert calls == ["resumable"]
