"""Bounded transport to one operator-bound Paperclip instance, without retries."""
from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .contract import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, PaperclipError, canonical


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def checked_origin(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 512 or any(ord(c) < 33 for c in value):
        raise ValueError("invalid Paperclip origin")
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Paperclip origin must have no credentials or path")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Paperclip port") from exc
    if parsed.scheme == "http":
        if parsed.hostname not in {"127.0.0.1", "::1"}:
            raise ValueError("unencrypted Paperclip transport is loopback-only")
    elif parsed.scheme != "https":
        raise ValueError("Paperclip transport requires HTTPS")
    return value.rstrip("/")


@dataclass(frozen=True)
class PaperclipHttpClient:
    origin: str
    timeout_seconds: float = 7.0

    def __post_init__(self):
        object.__setattr__(self, "origin", checked_origin(self.origin))
        if type(self.timeout_seconds) not in {float, int} or not 0.5 <= self.timeout_seconds <= 15:
            raise ValueError("bounded Paperclip timeout required")

    async def request(self, method: str, path: str, *, token: str | None, local_operator: bool = False, body: dict | None = None):
        if method not in {"GET", "POST"} or not path.startswith("/api/"):
            raise PaperclipError("INVALID_SOURCE_REQUEST", status=400)
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.fragment or ".." in parsed.path or "%" in parsed.path or "//" in parsed.path:
            raise PaperclipError("INVALID_SOURCE_REQUEST", status=400)
        if token is None:
            if not local_operator or urlsplit(self.origin).hostname not in {"127.0.0.1", "::1"}:
                raise PaperclipError("SOURCE_CREDENTIAL_UNAVAILABLE")
        elif not isinstance(token, str) or not 1 <= len(token) <= 16384 or any(c.isspace() for c in token):
            raise PaperclipError("SOURCE_CREDENTIAL_UNAVAILABLE")
        payload = None if body is None else canonical(body).encode("utf-8")
        if (method == "GET" and payload is not None) or (payload is not None and len(payload) > MAX_REQUEST_BYTES):
            raise PaperclipError("INVALID_SOURCE_REQUEST", status=400)
        return await asyncio.to_thread(self._once, method, path, token, payload)

    def _once(self, method: str, path: str, token: str | None, payload: bytes | None):
        headers = {"Accept": "application/json", "Cache-Control": "no-store"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.origin + path, data=payload, method=method, headers=headers)
        # Never follow a redirect with a private bearer or inherit a proxy from a
        # shell environment. Deployment chooses the one existing service origin.
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        uncertain = "EFFECT_UNKNOWN" if method != "GET" else "NOT_APPLIED"
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                if response.status < 200 or response.status >= 300:
                    raise PaperclipError("SOURCE_RESPONSE_INVALID", effect=uncertain)
                if response.headers.get_content_type() != "application/json":
                    raise PaperclipError("SOURCE_RESPONSE_INVALID", effect=uncertain)
                data = response.read(MAX_RESPONSE_BYTES + 1)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise PaperclipError("SOURCE_RESPONSE_TOO_LARGE", effect=uncertain)
                return json.loads(data.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except HTTPError as exc:
            # An upstream 5xx/redirect can follow a committed write. Keep it held.
            if exc.code in {400, 401, 403, 404, 409, 422, 429}:
                code = "SOURCE_ACCESS_DENIED" if exc.code in {401, 403} else "SOURCE_CONFLICT" if exc.code == 409 else "SOURCE_NOT_FOUND" if exc.code == 404 else "SOURCE_REQUEST_REFUSED"
                raise PaperclipError(code, status=403 if exc.code in {401, 403} else 409 if exc.code == 409 else 503) from None
            raise PaperclipError("SOURCE_OUTCOME_UNCONFIRMED", effect=uncertain) from None
        except PaperclipError:
            raise
        except (URLError, TimeoutError, socket.timeout, UnicodeError, ValueError, OSError):
            raise PaperclipError("SOURCE_OUTCOME_UNCONFIRMED", effect=uncertain) from None
