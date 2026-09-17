"""Fixed, read-only ASGI resource over an existing workspace-content owner.

The resource creates no issuer, token store, provider session, reader grant,
source registry, queue, retry loop, listener, or transcript persistence.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence
from typing import Protocol
from urllib.parse import urlsplit

from integrations.mastermind_workspace_content.live_window import (
    LiveWindowError,
    validate_visible_window,
)

WIRE_SCHEMA = "mastermind.workspace.content_read.v1"
MAX_RESPONSE_BYTES = 1_500_000
_SOURCE_REF = re.compile(r"\Amanaged-window:[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")


class _DuplicateJsonMember(ValueError):
    pass


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonMember
        result[key] = value
    return result


def _reject_json_constant(_value: str):
    raise ValueError("non-finite JSON number")


def _strict_json(value: bytes):
    return json.loads(
        value.decode("utf-8", errors="strict"),
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )


class ExistingWorkspaceContentOwner(Protocol):
    async def authorize(
        self, authorization_header: str, resource: str, source_ref: str
    ) -> tuple[object, ...] | None: ...

    async def read(self, source_ref: str) -> bytes: ...


def _ticket(value: object) -> tuple[object, ...] | None:
    if type(value) is not tuple or not 1 <= len(value) <= 16:
        return None
    for item in value:
        if type(item) is int:
            continue
        if type(item) is str and 0 < len(item) <= 2048:
            continue
        return None
    return tuple(value)


def _configured_url(value: object, *, origin: bool = False):
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError("invalid configured URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "%" in value
        or "\\" in value
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value)
    ):
        raise ValueError("invalid configured URL")
    if origin:
        if parsed.path:
            raise ValueError("origin must not contain a path")
    elif (
        re.fullmatch(r"/[A-Za-z0-9/_-]+", parsed.path) is None
        or "//" in parsed.path
    ):
        raise ValueError("invalid resource path")
    return parsed


class WorkspaceContentResource:
    """Expose one fixed source at one fixed authenticated GET resource."""

    def __init__(
        self,
        *,
        owner: ExistingWorkspaceContentOwner,
        resource: str,
        source_ref: str,
        allowed_origin: str,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        timeout_seconds: float = 15.0,
    ) -> None:
        if (
            owner is None
            or not callable(getattr(owner, "authorize", None))
            or not callable(getattr(owner, "read", None))
        ):
            raise TypeError("existing workspace content owner is required")
        resource_url = _configured_url(resource)
        origin_url = _configured_url(allowed_origin, origin=True)
        if resource_url.netloc != origin_url.netloc:
            raise ValueError("resource and browser origin must be same-origin")
        if (
            not isinstance(source_ref, str)
            or _SOURCE_REF.fullmatch(source_ref) is None
            or ".." in source_ref
        ):
            raise ValueError("invalid fixed source reference")
        if type(max_response_bytes) is not int or not 512 <= max_response_bytes <= MAX_RESPONSE_BYTES:
            raise ValueError("invalid response limit")
        if type(timeout_seconds) not in {int, float} or not 0 < timeout_seconds <= 30:
            raise ValueError("invalid timeout")
        self._owner = owner
        self._resource = resource
        self._source_ref = source_ref
        self._path = resource_url.path.encode("ascii")
        self._host = resource_url.netloc.encode("ascii")
        self._origin = allowed_origin.encode("ascii")
        self._limit = max_response_bytes
        self._timeout = float(timeout_seconds)

    @property
    def resource_url(self) -> str:
        return self._resource

    @property
    def resource_path(self) -> str:
        return self._path.decode("ascii")

    @property
    def source_ref(self) -> str:
        return self._source_ref

    async def __call__(self, scope, receive, send) -> None:
        async def reply(status: int, payload: object) -> None:
            raw = (
                payload
                if isinstance(payload, bytes)
                else json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            )
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"cache-control", b"no-store"),
                        (b"pragma", b"no-cache"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"content-length", str(len(raw)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": raw, "more_body": False})

        if scope.get("type") != "http":
            raise ValueError("HTTP resource only")
        raw_path = scope.get("raw_path")
        if (
            raw_path != self._path
            or scope.get("path", "").encode("ascii", errors="replace") != self._path
            or scope.get("root_path")
            or scope.get("query_string")
        ):
            await reply(404, {"error": "not_found"})
            return
        if scope.get("method") != "GET":
            await reply(405, {"error": "method_not_allowed"})
            return
        if scope.get("scheme") != "https":
            await reply(403, {"error": "transport_refused"})
            return

        raw_headers = scope.get("headers", ())
        if not isinstance(raw_headers, Sequence) or len(raw_headers) > 64:
            await reply(400, {"error": "invalid_request"})
            return
        headers: dict[bytes, list[bytes]] = {}
        for pair in raw_headers:
            if (
                not isinstance(pair, Sequence)
                or len(pair) != 2
                or not all(isinstance(value, bytes) for value in pair)
                or len(pair[1]) > 17_000
            ):
                await reply(400, {"error": "invalid_request"})
                return
            name, value = pair
            headers.setdefault(name.lower(), []).append(value)
        if (
            len(headers.get(b"host", [])) != 1
            or any(
                len(headers.get(name, [])) > 1
                for name in (b"authorization", b"origin", b"content-length")
            )
            or b"transfer-encoding" in headers
        ):
            await reply(400, {"error": "invalid_request"})
            return
        if (
            headers[b"host"][0] != self._host
            or headers.get(b"origin", [self._origin])[0] != self._origin
        ):
            await reply(403, {"error": "transport_refused"})
            return
        if headers.get(b"content-length", [b"0"])[0] != b"0":
            await reply(400, {"error": "invalid_request"})
            return
        authorization_values = headers.get(b"authorization", [])
        if not authorization_values:
            await reply(401, {"error": "authentication_required"})
            return
        try:
            authorization = authorization_values[0].decode("ascii")
            if (
                authorization != authorization.strip()
                or any(ord(character) < 0x20 or ord(character) == 0x7F for character in authorization)
            ):
                raise ValueError
        except (UnicodeError, ValueError):
            await reply(400, {"error": "invalid_request"})
            return

        async def empty_body() -> bool:
            for _ in range(8):
                message = await receive()
                if (
                    not isinstance(message, dict)
                    or message.get("type") != "http.request"
                    or message.get("body", b"") != b""
                ):
                    return False
                more_body = message.get("more_body", False)
                if type(more_body) is not bool:
                    return False
                if not more_body:
                    return True
            return False

        try:
            is_empty = await asyncio.wait_for(empty_body(), self._timeout)
        except Exception:
            is_empty = False
        if not is_empty:
            await reply(400, {"error": "invalid_request"})
            return

        try:
            first_ticket = _ticket(
                await asyncio.wait_for(
                    self._owner.authorize(authorization, self._resource, self._source_ref),
                    self._timeout,
                )
            )
        except Exception:
            first_ticket = None
        if first_ticket is None:
            await reply(401, {"error": "authentication_required"})
            return

        encoded: bytes | None = None
        try:
            raw = await asyncio.wait_for(self._owner.read(self._source_ref), self._timeout)
            if type(raw) is not bytes or not 0 < len(raw) <= self._limit:
                raise LiveWindowError("SOURCE_BOUND")
            document = _strict_json(raw)
            validated = validate_visible_window(document)
            if validated["source_ref"] != self._source_ref:
                raise LiveWindowError("SOURCE_SCOPE_MISMATCH")
            wire = {
                "schema": WIRE_SCHEMA,
                "selection_ref": self._source_ref,
                "mode": "observed-turn-window",
                "view": validated,
            }
            encoded = json.dumps(
                wire, ensure_ascii=True, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
            if len(encoded) > self._limit:
                raise LiveWindowError("OUTPUT_BOUND")
        except Exception:
            encoded = None

        try:
            final_ticket = _ticket(
                await asyncio.wait_for(
                    self._owner.authorize(authorization, self._resource, self._source_ref),
                    self._timeout,
                )
            )
        except Exception:
            final_ticket = None
        if final_ticket is None or final_ticket != first_ticket:
            await reply(403, {"error": "access_changed"})
            return
        if encoded is None:
            await reply(502, {"error": "source_unavailable"})
            return
        await reply(200, encoded)
