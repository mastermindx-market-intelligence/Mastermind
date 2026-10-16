"""Public Google Drive v3 archive sink.

Transport, lookup primitives, and the resumable protocol are split into small
internal modules so each security-sensitive surface stays independently reviewable.
"""
from __future__ import annotations

import hashlib
import http.client
import secrets
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

from integrations.slack_archive.google_drive_base import GoogleDriveArchiveBase
from integrations.slack_archive.google_drive_resumable import DriveResumableMixin
from integrations.slack_archive.google_drive_transport import (
    DRIVE_API_ROOT,
    DRIVE_UPLOAD_ROOT,
    MAX_JSON_BYTES,
    MULTIPART_MAX_BYTES,
    RESUMABLE_CHUNK_BYTES,
    DriveApiError,
    DriveEffectUnknown,
    GoogleOAuthCredentials,
    _APP_SHA256,
    _decode_json,
    _stable_json_bytes,
)


class GoogleDriveArchiveClient(DriveResumableMixin, GoogleDriveArchiveBase):
    def _create_multipart_bytes(
        self,
        *,
        metadata: Mapping[str, Any],
        content: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        boundary = "mmx-" + secrets.token_hex(16)
        metadata_bytes = _stable_json_bytes(metadata)
        prefix = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        ).encode("ascii") + metadata_bytes + (
            f"\r\n--{boundary}\r\nContent-Type: {content_type}\r\n\r\n"
        ).encode("ascii")
        suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
        body = prefix + content + suffix
        params = urllib.parse.urlencode(
            {
                "uploadType": "multipart",
                "fields": "id,name,mimeType,md5Checksum,size,appProperties,parents",
                "supportsAllDrives": "true",
            }
        )
        return self._request_json(
            method="POST",
            url=f"{DRIVE_UPLOAD_ROOT}/files?{params}",
            body=body,
            content_type=f"multipart/related; boundary={boundary}",
            safe_retry=False,
        )

    def _update_media_bytes(self, *, file_id: str, content: bytes, content_type: str) -> dict[str, Any]:
        params = urllib.parse.urlencode(
            {
                "uploadType": "media",
                "fields": "id,name,mimeType,md5Checksum,size,appProperties,parents",
                "supportsAllDrives": "true",
            }
        )
        return self._request_json(
            method="PATCH",
            url=f"{DRIVE_UPLOAD_ROOT}/files/{urllib.parse.quote(file_id, safe='')}?{params}",
            body=content,
            content_type=content_type,
            safe_retry=False,
        )

    def _get_metadata(self, *, file_id: str) -> dict[str, Any]:
        params = urllib.parse.urlencode(
            {"fields": "id,name,mimeType,md5Checksum,size,appProperties,parents", "supportsAllDrives": "true"}
        )
        return self._request_json(
            method="GET",
            url=f"{DRIVE_API_ROOT}/files/{urllib.parse.quote(file_id, safe='')}?{params}",
            safe_retry=True,
        )

    def upsert_json(
        self,
        *,
        logical_key: str,
        name: str,
        parent_id: str,
        document: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        content = _stable_json_bytes(document)
        expected_md5 = hashlib.md5(content).hexdigest()  # nosec B324 - Drive integrity field.
        existing = self.find_file(logical_key=logical_key, parent_id=parent_id)
        if existing is None:
            metadata = self._metadata(
                logical_key=logical_key,
                name=name,
                parent_id=parent_id,
                mime_type="application/json",
            )
            try:
                if len(content) <= MULTIPART_MAX_BYTES:
                    return self._create_multipart_bytes(metadata=metadata, content=content, content_type="application/json")
                return self._resumable_create_bytes(metadata=metadata, content=content, content_type="application/json")
            except DriveApiError as exc:
                reconciled = self.find_file(logical_key=logical_key, parent_id=parent_id)
                if reconciled is not None and reconciled.get("md5Checksum") == expected_md5:
                    return reconciled
                raise DriveEffectUnknown("DRIVE_JSON_CREATE_EFFECT_UNKNOWN") from exc

        file_id = existing.get("id")
        if not isinstance(file_id, str) or not file_id:
            raise DriveApiError("DRIVE_FILE_ID_MISSING")
        if existing.get("md5Checksum") == expected_md5:
            return existing
        try:
            if len(content) <= MULTIPART_MAX_BYTES:
                return self._update_media_bytes(file_id=file_id, content=content, content_type="application/json")
            return self._resumable_update_bytes(file_id=file_id, content=content, content_type="application/json")
        except DriveApiError as exc:
            reconciled = self._get_metadata(file_id=file_id)
            if reconciled.get("md5Checksum") == expected_md5:
                return reconciled
            raise DriveEffectUnknown("DRIVE_JSON_UPDATE_EFFECT_UNKNOWN") from exc

    def _stream_create_file(
        self,
        *,
        metadata: Mapping[str, Any],
        source_path: Path,
        mime_type: str,
    ) -> dict[str, Any]:
        size = source_path.stat().st_size
        if size <= MULTIPART_MAX_BYTES:
            boundary = "mmx-" + secrets.token_hex(16)
            metadata_bytes = _stable_json_bytes(metadata)
            prefix = (
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            ).encode("ascii") + metadata_bytes + (
                f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n"
            ).encode("ascii")
            suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
            content_length = len(prefix) + size + len(suffix)
            query = urllib.parse.urlencode(
                {
                    "uploadType": "multipart",
                    "fields": "id,name,mimeType,md5Checksum,size,appProperties,parents",
                    "supportsAllDrives": "true",
                }
            )
            path = f"/upload/drive/v3/files?{query}"
            connection = http.client.HTTPSConnection(
                "www.googleapis.com",
                timeout=self._timeout_seconds,
                context=self._ssl_context,
            )
            try:
                connection.putrequest("POST", path)
                connection.putheader("Authorization", f"Bearer {self._token()}")
                connection.putheader("User-Agent", "Mastermind-Slack-Drive-Archive/1")
                connection.putheader("Accept", "application/json")
                connection.putheader("Content-Type", f"multipart/related; boundary={boundary}")
                connection.putheader("Content-Length", str(content_length))
                connection.endheaders()
                connection.send(prefix)
                with source_path.open("rb") as handle:
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        connection.send(chunk)
                connection.send(suffix)
                response = connection.getresponse()
                body = response.read(MAX_JSON_BYTES + 1)
                if response.status not in {200, 201}:
                    if response.status == 401:
                        self._access_token = None
                    raise DriveApiError("DRIVE_UPLOAD_UNAVAILABLE")
                return _decode_json(body)
            except DriveApiError:
                raise
            except Exception:
                raise DriveApiError("DRIVE_UPLOAD_UNAVAILABLE") from None
            finally:
                connection.close()

        session_url = self._start_resumable_session(
            metadata=metadata,
            content_type=mime_type,
            content_length=size,
        )
        with source_path.open("rb") as stream:
            return self._resumable_upload_stream(
                session_url=session_url,
                stream=stream,
                total_size=size,
                content_type=mime_type,
            )

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
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise ValueError("sha256 invalid")
        existing = self.find_file(logical_key=logical_key, parent_id=parent_id)
        if existing is not None:
            return existing
        metadata = self._metadata(
            logical_key=logical_key,
            name=name,
            parent_id=parent_id,
            mime_type=mime_type,
            sha256=sha256,
        )
        try:
            return self._stream_create_file(metadata=metadata, source_path=source_path, mime_type=mime_type)
        except DriveApiError as exc:
            reconciled = self.find_file(logical_key=logical_key, parent_id=parent_id)
            props = reconciled.get("appProperties") if isinstance(reconciled, Mapping) else None
            if isinstance(reconciled, Mapping) and isinstance(reconciled.get("id"), str) and isinstance(props, Mapping) and props.get(_APP_SHA256) == sha256:
                return reconciled
            raise DriveEffectUnknown("DRIVE_FILE_CREATE_EFFECT_UNKNOWN") from exc



__all__ = [
    "DRIVE_API_ROOT",
    "DRIVE_UPLOAD_ROOT",
    "MULTIPART_MAX_BYTES",
    "RESUMABLE_CHUNK_BYTES",
    "DriveApiError",
    "DriveEffectUnknown",
    "GoogleDriveArchiveClient",
    "GoogleOAuthCredentials",
]
