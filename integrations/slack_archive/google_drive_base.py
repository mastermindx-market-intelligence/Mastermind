"""Drive archive lookup/folder primitives."""
from __future__ import annotations

import urllib.parse
from typing import Any, Mapping

from integrations.slack_archive.google_drive_transport import (
    DRIVE_API_ROOT,
    FOLDER_MIME,
    DriveApiError,
    DriveEffectUnknown,
    GoogleDriveTransport,
    _APP_KEY,
    _APP_SHA256,
    _decode_json,
    _escape_q,
    _logical_digest,
    _stable_json_bytes,
)


class GoogleDriveArchiveBase(GoogleDriveTransport):
    def _find_all(self, *, logical_key: str, parent_id: str | None = None) -> list[dict[str, Any]]:
        digest = _logical_digest(logical_key)
        terms = [
            "trashed = false",
            f"appProperties has {{ key='{_APP_KEY}' and value='{_escape_q(digest)}' }}",
        ]
        if parent_id is not None:
            terms.append(f"'{_escape_q(parent_id)}' in parents")
        query = " and ".join(terms)
        params = urllib.parse.urlencode(
            {
                "q": query,
                "spaces": "drive",
                "pageSize": "10",
                "fields": "files(id,name,mimeType,md5Checksum,size,appProperties,parents)",
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
            }
        )
        payload = self._request_json(
            method="GET",
            url=f"{DRIVE_API_ROOT}/files?{params}",
            safe_retry=True,
        )
        files = payload.get("files")
        if not isinstance(files, list):
            raise DriveApiError("DRIVE_INVALID_RESPONSE")
        return [dict(item) for item in files if isinstance(item, Mapping)]

    def find_file(self, *, logical_key: str, parent_id: str | None = None) -> Mapping[str, Any] | None:
        files = self._find_all(logical_key=logical_key, parent_id=parent_id)
        if len(files) > 1:
            raise DriveApiError("DRIVE_DUPLICATE_ARCHIVE_KEY")
        return files[0] if files else None

    @staticmethod
    def _metadata(*, logical_key: str, name: str, parent_id: str | None, mime_type: str, sha256: str | None = None) -> dict[str, Any]:
        props = {_APP_KEY: _logical_digest(logical_key)}
        if sha256 is not None:
            props[_APP_SHA256] = sha256
        metadata: dict[str, Any] = {
            "name": name,
            "mimeType": mime_type,
            "appProperties": props,
        }
        if parent_id is not None:
            metadata["parents"] = [parent_id]
        return metadata

    def _create_metadata(self, metadata: Mapping[str, Any]) -> dict[str, Any]:
        body = _stable_json_bytes(metadata)
        params = urllib.parse.urlencode(
            {
                "fields": "id,name,mimeType,md5Checksum,size,appProperties,parents",
                "supportsAllDrives": "true",
            }
        )
        return self._request_json(
            method="POST",
            url=f"{DRIVE_API_ROOT}/files?{params}",
            body=body,
            content_type="application/json; charset=utf-8",
            safe_retry=False,
        )

    def ensure_root(self, *, name: str) -> str:
        if self._root_folder_id is not None:
            return self._root_folder_id
        return self.ensure_folder(logical_key="slack-archive-root:v1", name=name, parent_id="root")

    def ensure_folder(self, *, logical_key: str, name: str, parent_id: str) -> str:
        cache_key = (parent_id, logical_key)
        cached = self._folder_cache.get(cache_key)
        if cached is not None:
            return cached
        existing = self.find_file(logical_key=logical_key, parent_id=parent_id)
        if existing is not None:
            if existing.get("mimeType") != FOLDER_MIME or not isinstance(existing.get("id"), str):
                raise DriveApiError("DRIVE_ARCHIVE_KEY_TYPE_MISMATCH")
            folder_id = str(existing["id"])
            self._folder_cache[cache_key] = folder_id
            return folder_id

        metadata = self._metadata(
            logical_key=logical_key,
            name=name,
            parent_id=parent_id,
            mime_type=FOLDER_MIME,
        )
        try:
            created = self._create_metadata(metadata)
        except DriveApiError as exc:
            reconciled = self.find_file(logical_key=logical_key, parent_id=parent_id)
            if reconciled is None or reconciled.get("mimeType") != FOLDER_MIME or not isinstance(reconciled.get("id"), str):
                raise DriveEffectUnknown("DRIVE_FOLDER_CREATE_EFFECT_UNKNOWN") from exc
            created = dict(reconciled)
        folder_id = created.get("id")
        if not isinstance(folder_id, str) or not folder_id:
            raise DriveApiError("DRIVE_FOLDER_ID_MISSING")
        self._folder_cache[cache_key] = folder_id
        return folder_id

    def read_json(self, *, file_id: str) -> Mapping[str, Any]:
        if not isinstance(file_id, str) or not file_id:
            raise ValueError("file_id must be non-empty")
        body = self._request(
            method="GET",
            url=f"{DRIVE_API_ROOT}/files/{urllib.parse.quote(file_id, safe='')}?alt=media&supportsAllDrives=true",
            expect_json=False,
            safe_retry=True,
        )
        return _decode_json(body)


__all__ = ["GoogleDriveArchiveBase"]
