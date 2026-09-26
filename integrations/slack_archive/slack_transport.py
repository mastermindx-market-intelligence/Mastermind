"""Minimal read-only Slack Web API client for retention archiving."""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

SLACK_API_ROOT = "https://slack.com/api/"
MAX_JSON_BYTES = 16 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
_ALLOWED_API_PATHS = frozenset(
    {
        "auth.test",
        "conversations.list",
        "conversations.history",
        "conversations.replies",
        "files.info",
    }
)


class SlackApiError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ValueError("invalid constant")


def _json_loads(body: bytes) -> dict[str, Any]:
    if len(body) > MAX_JSON_BYTES:
        raise SlackApiError("response_too_large")
    try:
        payload: Any = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise SlackApiError("invalid_json") from None
    if not isinstance(payload, dict):
        raise SlackApiError("invalid_json")
    return payload


def _safe_file_host(host: str | None) -> bool:
    if not isinstance(host, str) or not host:
        return False
    lowered = host.lower().rstrip(".")
    return (
        lowered == "slack.com"
        or lowered.endswith(".slack.com")
        or lowered == "slack-files.com"
        or lowered.endswith(".slack-files.com")
        or lowered == "slack-edge.com"
        or lowered.endswith(".slack-edge.com")
    )


class _SafeSlackFileRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        parsed = urllib.parse.urlsplit(str(newurl))
        if parsed.scheme != "https" or parsed.username or parsed.password or not _safe_file_host(parsed.hostname):
            raise urllib.error.HTTPError(req.full_url, code, "unsafe redirect refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SlackReadTransport:
    """Read-only Slack client. It has no Slack mutation methods by design."""

    def __init__(
        self,
        *,
        token: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if not isinstance(token, str) or not token.strip():
            raise ValueError("token must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not isinstance(max_file_bytes, int) or isinstance(max_file_bytes, bool) or max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        self._token = token.strip()
        self._timeout_seconds = float(timeout_seconds)
        self._max_file_bytes = max_file_bytes
        self._ssl_context = ssl_context or ssl.create_default_context()
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirectHandler(),
            urllib.request.HTTPSHandler(context=self._ssl_context),
        )
        self._file_opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _SafeSlackFileRedirectHandler(),
            urllib.request.HTTPSHandler(context=self._ssl_context),
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(read_only=True)"

    def _api_url(self, path: str, query: Mapping[str, str] | None = None) -> str:
        if path not in _ALLOWED_API_PATHS:
            raise SlackApiError("request_refused")
        url = SLACK_API_ROOT + path
        if query:
            pairs: list[tuple[str, str]] = []
            for key, value in sorted(query.items()):
                if not isinstance(key, str) or not isinstance(value, str):
                    raise SlackApiError("request_refused")
                pairs.append((key, value))
            url += "?" + urllib.parse.urlencode(pairs)
        return url

    def _request_json(self, path: str, query: Mapping[str, str] | None = None) -> dict[str, Any]:
        url = self._api_url(path, query)
        last_error: Exception | None = None
        for attempt in range(5):
            request = urllib.request.Request(
                url,
                method="GET",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "User-Agent": "Mastermind-Slack-Drive-Archive/1",
                    "Accept": "application/json",
                },
            )
            try:
                with self._opener.open(request, timeout=self._timeout_seconds) as response:
                    if int(response.status) != 200 or str(response.geturl()) != url:
                        raise SlackApiError("transport_unavailable")
                    content_type = str(response.headers.get("content-type", ""))
                    if not content_type.lower().startswith("application/json"):
                        raise SlackApiError("invalid_response")
                    body = response.read(MAX_JSON_BYTES + 1)
                payload = _json_loads(body)
                if payload.get("ok") is not True:
                    code = payload.get("error")
                    raise SlackApiError(str(code) if isinstance(code, str) and code else "api_refused")
                return payload
            except urllib.error.HTTPError as exc:
                last_error = exc
                http_code = exc.code
                if http_code == 429 and attempt < 4:
                    retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
                    try:
                        delay = max(1, min(60, int(str(retry_after))))
                    except (TypeError, ValueError):
                        delay = min(2 ** attempt, 15)
                    time.sleep(delay)
                    continue
                if 500 <= http_code < 600 and attempt < 2:
                    time.sleep(1 + attempt)
                    continue
                raise SlackApiError("transport_unavailable") from None
            except SlackApiError:
                raise
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1 + attempt)
                    continue
                break
        raise SlackApiError("transport_unavailable") from last_error

    @staticmethod
    def _next_cursor(payload: Mapping[str, Any]) -> str:
        metadata = payload.get("response_metadata")
        if not isinstance(metadata, Mapping):
            return ""
        cursor = metadata.get("next_cursor")
        return cursor if isinstance(cursor, str) else ""


__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_JSON_BYTES",
    "SLACK_API_ROOT",
    "SlackApiError",
    "SlackReadTransport",
    "_safe_file_host",
]
