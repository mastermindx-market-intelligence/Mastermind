"""Google Drive v3 sink for the Slack retention archive.

The client intentionally uses OAuth refresh credentials supplied from a local
secret file.  It does not depend on a Google SDK, own credential persistence,
or discover unrelated Drive content.  App-owned files are located through one
private ``appProperties`` key so repeated archive runs are idempotent.
"""
from __future__ import annotations

import hashlib
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

DRIVE_API_ROOT = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_ROOT = "https://www.googleapis.com/upload/drive/v3"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
FOLDER_MIME = "application/vnd.google-apps.folder"
MAX_JSON_BYTES = 32 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 60.0
MULTIPART_MAX_BYTES = 5 * 1024 * 1024
RESUMABLE_CHUNK_BYTES = 8 * 1024 * 1024
_APP_KEY = "mmx_key"
_APP_SHA256 = "mmx_sha256"


class DriveApiError(RuntimeError):
    pass


class DriveEffectUnknown(DriveApiError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


@dataclass(frozen=True)
class GoogleOAuthCredentials:
    client_id: str
    client_secret: str
    refresh_token: str
    token_uri: str = GOOGLE_TOKEN_URI

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GoogleOAuthCredentials":
        allowed = {"client_id", "client_secret", "refresh_token", "token_uri"}
        if set(raw) - allowed:
            raise ValueError("google oauth secret has unknown keys")
        client_id = raw.get("client_id")
        client_secret = raw.get("client_secret")
        refresh_token = raw.get("refresh_token")
        token_uri = raw.get("token_uri", GOOGLE_TOKEN_URI)
        if not all(isinstance(v, str) and v for v in (client_id, client_secret, refresh_token, token_uri)):
            raise ValueError("google oauth secret is incomplete")
        parsed = urllib.parse.urlsplit(str(token_uri))
        if parsed.scheme != "https" or parsed.hostname != "oauth2.googleapis.com" or parsed.path != "/token":
            raise ValueError("google oauth token_uri refused")
        return cls(
            client_id=str(client_id),
            client_secret=str(client_secret),
            refresh_token=str(refresh_token),
            token_uri=str(token_uri),
        )


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ValueError("invalid constant")


def _decode_json(body: bytes) -> dict[str, Any]:
    if len(body) > MAX_JSON_BYTES:
        raise DriveApiError("DRIVE_RESPONSE_TOO_LARGE")
    try:
        value: Any = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise DriveApiError("DRIVE_INVALID_JSON") from None
    if not isinstance(value, dict):
        raise DriveApiError("DRIVE_INVALID_JSON")
    return value


def _stable_json_bytes(document: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                dict(document),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise DriveApiError("DRIVE_DOCUMENT_INVALID") from None


def _logical_digest(logical_key: str) -> str:
    if not isinstance(logical_key, str) or not logical_key:
        raise ValueError("logical_key must be non-empty")
    return hashlib.sha256(logical_key.encode("utf-8")).hexdigest()


def _escape_q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveTransport:
    def __init__(
        self,
        *,
        credentials: GoogleOAuthCredentials,
        root_folder_id: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if root_folder_id is not None and (not isinstance(root_folder_id, str) or not root_folder_id.strip()):
            raise ValueError("root_folder_id invalid")
        self._credentials = credentials
        self._root_folder_id = root_folder_id.strip() if isinstance(root_folder_id, str) else None
        self._timeout_seconds = float(timeout_seconds)
        self._ssl_context = ssl_context or ssl.create_default_context()
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirectHandler(),
            urllib.request.HTTPSHandler(context=self._ssl_context),
        )
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._folder_cache: dict[tuple[str, str], str] = {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(root_folder_configured={self._root_folder_id is not None})"

    def _refresh_access_token(self) -> str:
        body = urllib.parse.urlencode(
            {
                "client_id": self._credentials.client_id,
                "client_secret": self._credentials.client_secret,
                "refresh_token": self._credentials.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("ascii")
        request = urllib.request.Request(
            self._credentials.token_uri,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "Mastermind-Slack-Drive-Archive/1",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                if int(response.status) != 200 or str(response.geturl()) != self._credentials.token_uri:
                    raise DriveApiError("GOOGLE_OAUTH_UNAVAILABLE")
                payload = _decode_json(response.read(MAX_JSON_BYTES + 1))
        except DriveApiError:
            raise
        except Exception:
            raise DriveApiError("GOOGLE_OAUTH_UNAVAILABLE") from None
        token = payload.get("access_token")
        expires_in = payload.get("expires_in", 3600)
        if not isinstance(token, str) or not token:
            raise DriveApiError("GOOGLE_OAUTH_INVALID_RESPONSE")
        try:
            ttl = max(60, int(expires_in))
        except (TypeError, ValueError):
            ttl = 3600
        self._access_token = token
        self._access_token_expires_at = time.time() + ttl
        return token

    def _token(self, *, force_refresh: bool = False) -> str:
        if (
            force_refresh
            or self._access_token is None
            or time.time() >= self._access_token_expires_at - 60
        ):
            return self._refresh_access_token()
        return self._access_token

    def _request(
        self,
        *,
        method: str,
        url: str,
        body: bytes | None = None,
        content_type: str | None = None,
        expect_json: bool = True,
        safe_retry: bool = False,
    ) -> bytes:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "www.googleapis.com":
            raise DriveApiError("DRIVE_URL_REFUSED")
        attempts = 3 if safe_retry else 1
        forced_refresh = False
        for attempt in range(attempts):
            headers = {
                "Authorization": f"Bearer {self._token(force_refresh=forced_refresh)}",
                "User-Agent": "Mastermind-Slack-Drive-Archive/1",
            }
            if expect_json:
                headers["Accept"] = "application/json"
            if content_type is not None:
                headers["Content-Type"] = content_type
            request = urllib.request.Request(url, data=body, method=method, headers=headers)
            try:
                with self._opener.open(request, timeout=self._timeout_seconds) as response:
                    if int(response.status) not in {200, 201} or str(response.geturl()) != url:
                        raise DriveApiError("DRIVE_TRANSPORT_UNAVAILABLE")
                    return response.read(MAX_JSON_BYTES + 1 if expect_json else MAX_JSON_BYTES)
            except urllib.error.HTTPError as exc:
                http_code = exc.code
                if http_code == 401 and not forced_refresh:
                    forced_refresh = True
                    continue
                if safe_retry and (http_code == 429 or 500 <= http_code < 600) and attempt + 1 < attempts:
                    retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
                    try:
                        delay = max(1, min(30, int(str(retry_after))))
                    except (TypeError, ValueError):
                        delay = 1 + attempt
                    time.sleep(delay)
                    continue
                raise DriveApiError("DRIVE_TRANSPORT_UNAVAILABLE") from None
            except DriveApiError:
                raise
            except Exception:
                if safe_retry and attempt + 1 < attempts:
                    time.sleep(1 + attempt)
                    continue
                raise DriveApiError("DRIVE_TRANSPORT_UNAVAILABLE") from None
        raise DriveApiError("DRIVE_TRANSPORT_UNAVAILABLE")

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        body: bytes | None = None,
        content_type: str | None = None,
        safe_retry: bool = False,
    ) -> dict[str, Any]:
        return _decode_json(
            self._request(
                method=method,
                url=url,
                body=body,
                content_type=content_type,
                expect_json=True,
                safe_retry=safe_retry,
            )
        )


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "DRIVE_API_ROOT",
    "DRIVE_UPLOAD_ROOT",
    "FOLDER_MIME",
    "GOOGLE_TOKEN_URI",
    "MAX_JSON_BYTES",
    "MULTIPART_MAX_BYTES",
    "RESUMABLE_CHUNK_BYTES",
    "DriveApiError",
    "DriveEffectUnknown",
    "GoogleDriveTransport",
    "GoogleOAuthCredentials",
    "_APP_KEY",
    "_APP_SHA256",
    "_decode_json",
    "_escape_q",
    "_logical_digest",
    "_stable_json_bytes",
]
