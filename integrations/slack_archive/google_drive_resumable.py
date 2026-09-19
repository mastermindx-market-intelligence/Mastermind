"""Resumable Google Drive upload protocol for the Slack archive."""
from __future__ import annotations

import io
import http.client
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from integrations.slack_archive.google_drive_transport import (
    DRIVE_UPLOAD_ROOT,
    MAX_JSON_BYTES,
    RESUMABLE_CHUNK_BYTES,
    DriveApiError,
    DriveEffectUnknown,
    _decode_json,
    _stable_json_bytes,
)


class DriveResumableMixin:
    @staticmethod
    def _session_url_parts(session_url: str) -> tuple[str, str]:
        parsed = urllib.parse.urlsplit(session_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "www.googleapis.com"
            or parsed.username
            or parsed.password
            or not parsed.path.startswith("/upload/drive/v3/files")
        ):
            raise DriveApiError("DRIVE_RESUMABLE_SESSION_REFUSED")
        path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        return parsed.hostname, path

    def _start_resumable_session(
        self,
        *,
        metadata: Mapping[str, Any],
        content_type: str,
        content_length: int,
        file_id: str | None = None,
    ) -> str:
        if content_length < 0:
            raise ValueError("content_length invalid")
        params = urllib.parse.urlencode(
            {
                "uploadType": "resumable",
                "fields": "id,name,mimeType,md5Checksum,size,appProperties,parents",
                "supportsAllDrives": "true",
            }
        )
        if file_id is None:
            url = f"{DRIVE_UPLOAD_ROOT}/files?{params}"
            method = "POST"
        else:
            url = f"{DRIVE_UPLOAD_ROOT}/files/{urllib.parse.quote(file_id, safe='')}?{params}"
            method = "PATCH"
        body = _stable_json_bytes(metadata)
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "User-Agent": "Mastermind-Slack-Drive-Archive/1",
                "Accept": "application/json",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": content_type,
                "X-Upload-Content-Length": str(content_length),
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                if int(response.status) != 200 or str(response.geturl()) != url:
                    raise DriveApiError("DRIVE_RESUMABLE_INIT_UNAVAILABLE")
                location = response.headers.get("Location")
        except DriveApiError:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                self._access_token = None
            raise DriveApiError("DRIVE_RESUMABLE_INIT_UNAVAILABLE") from None
        except Exception:
            raise DriveApiError("DRIVE_RESUMABLE_INIT_UNAVAILABLE") from None
        if not isinstance(location, str) or not location:
            raise DriveApiError("DRIVE_RESUMABLE_LOCATION_MISSING")
        self._session_url_parts(location)
        return location

    @staticmethod
    def _next_offset_from_range(value: str | None) -> int:
        if not value:
            return 0
        match = re.fullmatch(r"bytes=0-([0-9]+)", value.strip())
        if match is None:
            raise DriveApiError("DRIVE_RESUMABLE_RANGE_INVALID")
        return int(match.group(1)) + 1

    def _resumable_status(self, *, session_url: str, total_size: int) -> tuple[int, dict[str, Any] | None]:
        host, path = self._session_url_parts(session_url)
        for refresh_attempt in range(2):
            connection = http.client.HTTPSConnection(
                host,
                timeout=self._timeout_seconds,
                context=self._ssl_context,
            )
            try:
                connection.putrequest("PUT", path)
                connection.putheader("Authorization", f"Bearer {self._token(force_refresh=refresh_attempt > 0)}")
                connection.putheader("User-Agent", "Mastermind-Slack-Drive-Archive/1")
                connection.putheader("Content-Length", "0")
                connection.putheader("Content-Range", f"bytes */{total_size}")
                connection.endheaders()
                response = connection.getresponse()
                body = response.read(MAX_JSON_BYTES + 1)
                if response.status in {200, 201}:
                    return total_size, _decode_json(body)
                if response.status == 308:
                    return self._next_offset_from_range(response.getheader("Range")), None
                if response.status == 401 and refresh_attempt == 0:
                    self._access_token = None
                    continue
                raise DriveEffectUnknown("DRIVE_RESUMABLE_STATUS_EFFECT_UNKNOWN")
            except DriveApiError:
                raise
            except Exception as exc:
                raise DriveEffectUnknown("DRIVE_RESUMABLE_STATUS_EFFECT_UNKNOWN") from exc
            finally:
                connection.close()
        raise DriveEffectUnknown("DRIVE_RESUMABLE_STATUS_EFFECT_UNKNOWN")

    def _resumable_upload_stream(
        self,
        *,
        session_url: str,
        stream: Any,
        total_size: int,
        content_type: str,
    ) -> dict[str, Any]:
        if total_size <= 0:
            raise ValueError("resumable upload requires positive content length")
        host, path = self._session_url_parts(session_url)
        offset = 0
        recoveries = 0
        while offset < total_size:
            stream.seek(offset)
            chunk = stream.read(min(RESUMABLE_CHUNK_BYTES, total_size - offset))
            if not isinstance(chunk, (bytes, bytearray)) or not chunk:
                raise DriveApiError("DRIVE_RESUMABLE_SOURCE_TRUNCATED")
            chunk_bytes = bytes(chunk)
            end = offset + len(chunk_bytes) - 1
            connection = http.client.HTTPSConnection(
                host,
                timeout=self._timeout_seconds,
                context=self._ssl_context,
            )
            try:
                connection.putrequest("PUT", path)
                connection.putheader("Authorization", f"Bearer {self._token()}")
                connection.putheader("User-Agent", "Mastermind-Slack-Drive-Archive/1")
                connection.putheader("Content-Type", content_type)
                connection.putheader("Content-Length", str(len(chunk_bytes)))
                connection.putheader("Content-Range", f"bytes {offset}-{end}/{total_size}")
                connection.endheaders()
                connection.send(chunk_bytes)
                response = connection.getresponse()
                body = response.read(MAX_JSON_BYTES + 1)
                if response.status in {200, 201}:
                    result = _decode_json(body)
                    if end + 1 != total_size:
                        raise DriveEffectUnknown("DRIVE_RESUMABLE_EARLY_COMPLETION")
                    return result
                if response.status == 308:
                    next_offset = self._next_offset_from_range(response.getheader("Range"))
                    if next_offset <= offset or next_offset > total_size:
                        raise DriveEffectUnknown("DRIVE_RESUMABLE_PROGRESS_INVALID")
                    offset = next_offset
                    recoveries = 0
                    continue
                if response.status == 401:
                    self._access_token = None
                if response.status not in {401, 408, 429, 500, 502, 503, 504}:
                    raise DriveEffectUnknown("DRIVE_RESUMABLE_UPLOAD_EFFECT_UNKNOWN")
            except DriveEffectUnknown:
                raise
            except Exception:
                pass
            finally:
                connection.close()

            recoveries += 1
            if recoveries > 4:
                raise DriveEffectUnknown("DRIVE_RESUMABLE_UPLOAD_EFFECT_UNKNOWN")
            time.sleep(min(recoveries, 3))
            next_offset, completed = self._resumable_status(
                session_url=session_url,
                total_size=total_size,
            )
            if completed is not None:
                return completed
            if next_offset < 0 or next_offset > total_size:
                raise DriveEffectUnknown("DRIVE_RESUMABLE_PROGRESS_INVALID")
            offset = next_offset

        next_offset, completed = self._resumable_status(session_url=session_url, total_size=total_size)
        if completed is not None:
            return completed
        raise DriveEffectUnknown(
            "DRIVE_RESUMABLE_COMPLETION_UNPROVEN"
            if next_offset == total_size
            else "DRIVE_RESUMABLE_PROGRESS_INVALID"
        )

    def _resumable_create_bytes(
        self,
        *,
        metadata: Mapping[str, Any],
        content: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        session_url = self._start_resumable_session(
            metadata=metadata,
            content_type=content_type,
            content_length=len(content),
        )
        with io.BytesIO(content) as stream:
            return self._resumable_upload_stream(
                session_url=session_url,
                stream=stream,
                total_size=len(content),
                content_type=content_type,
            )

    def _resumable_update_bytes(
        self,
        *,
        file_id: str,
        content: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        session_url = self._start_resumable_session(
            metadata={},
            content_type=content_type,
            content_length=len(content),
            file_id=file_id,
        )
        with io.BytesIO(content) as stream:
            return self._resumable_upload_stream(
                session_url=session_url,
                stream=stream,
                total_size=len(content),
                content_type=content_type,
            )



__all__ = ["DriveResumableMixin"]
