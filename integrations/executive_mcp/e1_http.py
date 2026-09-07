"""Bounded, SDK-free inner HTTP boundary for the temporary E1 read profile."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

MAX_REQUEST_BYTES = 65_536
MAX_RESPONSE_BYTES = 262_144
E1_READ_PATHS = frozenset(
    {
        "/v1/tools/executive_state",
        "/v1/tools/executive_inbox",
        "/v1/tools/executive_job",
        "/v1/tools/ceo_intent_status",
    }
)
E1_PROFILE_SHA256 = hashlib.sha256(
    json.dumps(
        {
            "profile": "e1-read",
            "tools": sorted(path.rsplit("/", 1)[-1] for path in E1_READ_PATHS),
            "max_request_bytes": MAX_REQUEST_BYTES,
            "max_response_bytes": MAX_RESPONSE_BYTES,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()

_Receive = Callable[[], Awaitable[Mapping[str, Any]]]
_Send = Callable[[Mapping[str, Any]], Awaitable[None]]


class _RequestTooLarge(Exception):
    pass


class _ResponseTooLarge(Exception):
    pass


class _ResponseMalformed(Exception):
    pass


async def _error(send: _Send, status: int, code: str, message: str) -> None:
    body = (
        '{"ok":false,"error":{"code":"'
        + code
        + '","message":"'
        + message
        + '"}}'
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


class BoundedE1App:
    """Buffer one bounded ASGI request/response before crossing either edge.

    Buffering is deliberately bounded at both seams: request frames are counted
    before the Starlette/MCP body reader can collect them, and response frames
    are held until their total is known safe so an overflow cannot leak a
    healthy-looking partial response through ``ASGITransport``.
    """

    def __init__(self, app: Callable[[Mapping[str, Any], _Receive, _Send], Awaitable[None]]):
        self._app = app

    async def aclose(self) -> None:
        """Delegate lifecycle ownership to the one direct app when available."""

        close = getattr(self._app, "aclose", None)
        if close is not None:
            await close()

    async def __call__(self, scope: Mapping[str, Any], receive: _Receive, send: _Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        try:
            request_body = await self._bounded_request(receive)
        except _RequestTooLarge:
            await _error(send, 413, "invalid_input", "request body exceeds 65536 bytes")
            return
        except RuntimeError:
            await _error(send, 400, "invalid_input", "request body is incomplete")
            return

        replayed = False

        async def replay_receive() -> Mapping[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            return {"type": "http.disconnect"}

        start: Mapping[str, Any] | None = None
        response_body = bytearray()
        response_total = 0
        response_complete = False

        async def bounded_send(event: Mapping[str, Any]) -> None:
            nonlocal start, response_total, response_complete
            event_type = event.get("type")
            if event_type == "http.response.start":
                if start is not None or response_complete:
                    raise _ResponseMalformed
                start = dict(event)
                return
            if event_type != "http.response.body":
                raise _ResponseMalformed
            if start is None or response_complete:
                raise _ResponseMalformed
            body = bytes(event.get("body", b""))
            if response_total + len(body) > MAX_RESPONSE_BYTES:
                raise _ResponseTooLarge
            response_total += len(body)
            response_body.extend(body)
            if not event.get("more_body", False):
                response_complete = True

        try:
            await self._app(scope, replay_receive, bounded_send)
        except _ResponseTooLarge:
            await _error(send, 503, "output_too_large", "E1 response exceeds 262144 bytes")
            return
        except _ResponseMalformed:
            await _error(send, 503, "backend_unavailable", "E1 response is unavailable")
            return
        except Exception:
            await _error(send, 503, "backend_unavailable", "E1 response is unavailable")
            return
        if start is None or not response_complete:
            await _error(send, 503, "backend_unavailable", "E1 response is unavailable")
            return
        await send(start)
        await send(
            {
                "type": "http.response.body",
                "body": bytes(response_body),
                "more_body": False,
            }
        )

    @staticmethod
    async def _bounded_request(receive: _Receive) -> bytes:
        request_body = bytearray()
        total = 0
        while True:
            event = await receive()
            if event.get("type") == "http.disconnect":
                raise RuntimeError("request disconnected")
            if event.get("type") != "http.request":
                raise RuntimeError("unexpected ASGI request event")
            body = bytes(event.get("body", b""))
            total += len(body)
            if total > MAX_REQUEST_BYTES:
                raise _RequestTooLarge
            request_body.extend(body)
            if not event.get("more_body", False):
                return bytes(request_body)


class BoundedRequestApp:
    """Receive-only guard used inside outer authentication before MCP dispatch."""

    def __init__(self, app: Callable[[Mapping[str, Any], _Receive, _Send], Awaitable[None]]):
        self._app = app

    async def __call__(self, scope: Mapping[str, Any], receive: _Receive, send: _Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        try:
            request_body = await BoundedE1App._bounded_request(receive)
        except _RequestTooLarge:
            await _error(send, 413, "invalid_input", "request body exceeds 65536 bytes")
            return
        except RuntimeError:
            await _error(send, 400, "invalid_input", "request body is incomplete")
            return
        replayed = False

        async def replay_receive() -> Mapping[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            return {"type": "http.disconnect"}

        await self._app(scope, replay_receive, send)


class FixedE1App(BoundedE1App):
    """Literal four-POST E1 tool map; metadata remains owned by the inner app."""

    async def __call__(self, scope: Mapping[str, Any], receive: _Receive, send: _Send) -> None:
        path = str(scope.get("path", ""))
        if scope.get("type") == "http" and path.startswith("/v1/tools/"):
            raw_path = scope.get("raw_path")
            literal_path = path.encode("ascii") if path.isascii() else b""
            is_literal_reader = (
                scope.get("method") == "POST"
                and not scope.get("query_string", b"")
                and path in E1_READ_PATHS
                and raw_path == literal_path
            )
            if not is_literal_reader:
                await _error(send, 404, "not_found", "unknown E1 read tool")
                return
        await super().__call__(scope, receive, send)


def build_e1_app(settings: Any) -> FixedE1App:
    """Construct the fixed profile from a direct read-only app settings object."""

    if not getattr(settings, "read_only", False):
        raise ValueError("E1 requires read_only AppSettings")
    from integrations.mastermind_executive_app.app import create_app

    return FixedE1App(create_app(settings))
