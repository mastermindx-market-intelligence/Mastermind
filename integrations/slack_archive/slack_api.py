"""Read-only Slack archive operations built on the fixed-origin transport."""
from __future__ import annotations

import hashlib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

from integrations.slack_archive.slack_transport import (
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    SLACK_API_ROOT,
    SlackApiError,
    SlackReadTransport,
    _safe_file_host,
)


class SlackArchiveClient(SlackReadTransport):
    def auth_test(self) -> Mapping[str, Any]:
        payload = self._request_json("auth.test")
        team_id = payload.get("team_id")
        if not isinstance(team_id, str) or not team_id:
            raise SlackApiError("workspace_identity_missing")
        return payload

    def list_conversations(self) -> Iterable[Mapping[str, Any]]:
        cursor = ""
        seen_cursors: set[str] = set()
        seen_ids: set[str] = set()
        while True:
            query = {
                "types": "public_channel,private_channel,mpim,im",
                "exclude_archived": "false",
                "limit": "200",
            }
            if cursor:
                query["cursor"] = cursor
            payload = self._request_json("conversations.list", query)
            channels = payload.get("channels")
            if not isinstance(channels, list):
                raise SlackApiError("invalid_response")
            for raw in channels:
                if not isinstance(raw, Mapping):
                    raise SlackApiError("invalid_response")
                channel_id = raw.get("id")
                if not isinstance(channel_id, str) or not channel_id:
                    raise SlackApiError("invalid_response")
                if channel_id in seen_ids:
                    continue
                seen_ids.add(channel_id)
                yield dict(raw)
            next_cursor = self._next_cursor(payload)
            if not next_cursor:
                return
            if next_cursor in seen_cursors:
                raise SlackApiError("cursor_cycle")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

    def _paginate_messages(self, *, path: str, base_query: Mapping[str, str]) -> Iterable[Mapping[str, Any]]:
        cursor = ""
        seen_cursors: set[str] = set()
        seen_ts: set[str] = set()
        while True:
            query = dict(base_query)
            query["limit"] = "200"
            if cursor:
                query["cursor"] = cursor
            payload = self._request_json(path, query)
            messages = payload.get("messages")
            if not isinstance(messages, list):
                raise SlackApiError("invalid_response")
            for raw in messages:
                if not isinstance(raw, Mapping):
                    raise SlackApiError("invalid_response")
                ts = raw.get("ts")
                if not isinstance(ts, str) or not ts:
                    continue
                if ts in seen_ts:
                    continue
                seen_ts.add(ts)
                yield dict(raw)
            next_cursor = self._next_cursor(payload)
            has_more = payload.get("has_more")
            if not next_cursor:
                if has_more not in (False, None):
                    raise SlackApiError("pagination_incomplete")
                return
            if next_cursor in seen_cursors:
                raise SlackApiError("cursor_cycle")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

    def iter_history(self, *, channel_id: str, oldest: str) -> Iterable[Mapping[str, Any]]:
        if not isinstance(channel_id, str) or not channel_id:
            raise ValueError("channel_id must be non-empty")
        if not isinstance(oldest, str) or not oldest:
            raise ValueError("oldest must be non-empty")
        return self._paginate_messages(
            path="conversations.history",
            base_query={"channel": channel_id, "oldest": oldest, "inclusive": "true"},
        )

    def iter_replies(self, *, channel_id: str, thread_ts: str) -> Iterable[Mapping[str, Any]]:
        if not isinstance(channel_id, str) or not channel_id:
            raise ValueError("channel_id must be non-empty")
        if not isinstance(thread_ts, str) or not thread_ts:
            raise ValueError("thread_ts must be non-empty")
        return self._paginate_messages(
            path="conversations.replies",
            base_query={"channel": channel_id, "ts": thread_ts, "inclusive": "true"},
        )

    def file_info(self, *, file_id: str) -> Mapping[str, Any]:
        if not isinstance(file_id, str) or not file_id:
            raise ValueError("file_id must be non-empty")
        payload = self._request_json("files.info", {"file": file_id})
        raw = payload.get("file")
        if not isinstance(raw, Mapping) or raw.get("id") != file_id:
            raise SlackApiError("invalid_response")
        return dict(raw)

    def download_file(
        self,
        *,
        url: str,
        destination: Path,
        expected_size: int | None,
    ) -> Mapping[str, Any]:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or not _safe_file_host(parsed.hostname):
            raise SlackApiError("file_url_refused")
        if parsed.fragment:
            raise SlackApiError("file_url_refused")
        if expected_size is not None:
            if not isinstance(expected_size, int) or expected_size < 0:
                raise ValueError("expected_size invalid")
            if expected_size > self._max_file_bytes:
                raise SlackApiError("file_too_large")

        destination.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "Mastermind-Slack-Drive-Archive/1",
            },
        )
        sha256 = hashlib.sha256()
        md5 = hashlib.md5()  # nosec B324 - Drive exposes MD5 for integrity comparison only.
        total = 0
        try:
            with self._file_opener.open(request, timeout=self._timeout_seconds) as response:
                final = urllib.parse.urlsplit(str(response.geturl()))
                if final.scheme != "https" or not _safe_file_host(final.hostname):
                    raise SlackApiError("file_redirect_refused")
                with destination.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > self._max_file_bytes:
                            raise SlackApiError("file_too_large")
                        sha256.update(chunk)
                        md5.update(chunk)
                        handle.write(chunk)
        except SlackApiError:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError):
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            raise SlackApiError("file_download_unavailable") from None

        if expected_size is not None and total != expected_size:
            destination.unlink(missing_ok=True)
            raise SlackApiError("file_size_mismatch")
        return {"size": total, "sha256": sha256.hexdigest(), "md5": md5.hexdigest()}


__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "SLACK_API_ROOT",
    "SlackApiError",
    "SlackArchiveClient",
]
