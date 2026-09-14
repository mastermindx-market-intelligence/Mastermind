"""Single-account Go streaming edge; no retries, proxy daemon or account selector.

The existing harness owns the process, transcript, tools, workspace and admission.
A required caller-owned request check is subordinate to that admission. This module
never promotes a model, enrolls a key, reserves quota or changes an active account.
"""
from __future__ import annotations

import http.client
import json
import math
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlsplit

from control_plane.opencode_go_pooled_transport import (
    AccountChoice, OpenCodeGoEffectUnknown, OpenCodeGoTransportContractError,
    ProviderRequest, UpstreamResponse, _choice, _freeze_request, _unique_object,
    _reject_json_constant, prepare_upstream_request,
)

MAX_EVENT_BYTES = 1024 * 1024
MAX_STREAM_BYTES = 64 * 1024 * 1024
MAX_ERROR_BYTES = 256 * 1024
RESPONSE_HEADERS = frozenset({"content-type", "retry-after", "x-request-id", "request-id"})


class OpenCodeGoStreamCancelled(OpenCodeGoEffectUnknown):
    """Local cancellation does not establish absence of provider-side effects."""


@dataclass(frozen=True)
class StreamReceipt:
    account_id: str
    pool_generation: str
    http_status: int
    bytes_forwarded: int
    terminal_observed: bool
    error_response: Optional[UpstreamResponse] = field(default=None, repr=False)


class _SSEObserver:
    """Bounded framing only. Tool calls and content remain the harness's job."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.buffer = bytearray()
        self.data: list[bytes] = []
        self.event = b""
        self.event_bytes = 0
        self.terminal = False

    def _dispatch(self) -> None:
        if not self.data:
            self.event, self.event_bytes = b"", 0
            return
        data = b"\n".join(self.data)
        self.data = []
        event, self.event = self.event, b""
        self.event_bytes = 0
        if self.terminal:
            raise ValueError("data after terminal")
        if self.path == "chat/completions" and data == b"[DONE]":
            if event not in (b"", b"message"):
                raise ValueError("conflicting terminal event")
            self.terminal = True
            return
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=_reject_json_constant)
        if not isinstance(payload, dict):
            raise ValueError("invalid event data")
        kind = payload.get("type")
        if event == b"error" or "error" in payload or kind in {
            "error", "response.failed", "response.incomplete", "response.cancelled",
        }:
            raise ValueError("provider error event")
        if self.path == "messages" and kind == "message_stop":
            if event not in (b"", b"message_stop"):
                raise ValueError("conflicting terminal event")
            self.terminal = True
        elif self.path == "responses" and kind == "response.completed":
            response = payload.get("response")
            if (event not in (b"", b"response.completed") or not isinstance(response, dict)
                    or response.get("status") != "completed"):
                raise ValueError("invalid response completion")
            self.terminal = True

    def _line(self, line: bytes) -> None:
        self.event_bytes += len(line) + 1
        if self.event_bytes > MAX_EVENT_BYTES:
            raise ValueError("event size exceeded")
        if not line:
            self._dispatch()
        elif line.startswith(b"data:"):
            value = line[5:]
            self.data.append(value[1:] if value.startswith(b" ") else value)
        elif line.startswith(b"event:"):
            self.event = line[6:].lstrip(b" ")

    def finish(self) -> None:
        # A final bare CR is a valid line ending; unterminated data is not.
        if self.buffer.endswith(b"\r"):
            self._line(bytes(self.buffer[:-1]))
            self.buffer.clear()

    def feed(self, chunk: bytes) -> None:
        self.buffer.extend(chunk)
        while True:
            positions = [p for p in (self.buffer.find(b"\n"), self.buffer.find(b"\r")) if p >= 0]
            if not positions:
                break
            pos = min(positions)
            if self.buffer[pos] == 13 and pos + 1 == len(self.buffer):
                break  # A CRLF may be split across reads.
            step = 2 if self.buffer[pos:pos + 2] == b"\r\n" else 1
            line = bytes(self.buffer[:pos])
            del self.buffer[:pos + step]
            self._line(line)
        if len(self.buffer) + self.event_bytes > MAX_EVENT_BYTES:
            raise ValueError("event size exceeded")


def _positive_seconds(value: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpenCodeGoTransportContractError("invalid stream timeout")
    if not math.isfinite(value) or not 0 < value <= maximum:
        raise OpenCodeGoTransportContractError("invalid stream timeout")
    return float(value)


def stream_single_account(
    request: ProviderRequest, *, choice: AccountChoice,
    credential_loader: Callable[[str], str],
    request_check: Callable[[ProviderRequest], None],
    on_chunk: Callable[[bytes], None],
    cancel: Optional[threading.Event] = None,
    idle_timeout_seconds: float = 5.0, total_timeout_seconds: float = 600.0,
    connection_factory: Callable = http.client.HTTPSConnection,
    monotonic: Callable[[], float] = time.monotonic,
) -> StreamReceipt:
    """Forward one approved streaming request, keeping the exact account and body.

    The request check runs before key access and again immediately before POST.
    It must raise to refuse and return None on success. The real binding must wire
    its current Provider Control / offer checks here; a fixture check is not live
    authority. No retry occurs for any HTTP status, stream failure or cancellation.
    A terminal wire event is not a claim that the user's coding task succeeded.
    """
    frozen = _freeze_request(request, replayable=False)
    payload = json.loads(frozen.body)
    if payload.get("stream") is not True or payload.get("background") is True:
        raise OpenCodeGoTransportContractError("foreground streaming request required")
    if not isinstance(choice, AccountChoice):
        raise OpenCodeGoTransportContractError("invalid account choice")
    selected = _choice(choice, pool_id=choice.pool_id)
    if not all(callable(x) for x in (credential_loader, request_check, on_chunk, connection_factory, monotonic)):
        raise OpenCodeGoTransportContractError("stream dependencies must be callable")
    if cancel is not None and not isinstance(cancel, threading.Event):
        raise OpenCodeGoTransportContractError("invalid cancellation signal")
    idle = _positive_seconds(idle_timeout_seconds, 30.0)
    total = _positive_seconds(total_timeout_seconds, 1800.0)
    deadline = monotonic() + total
    connection = response = None
    submitted = False
    forwarded = 0

    def check_cancel_deadline() -> None:
        cancelled = cancel is not None and cancel.is_set()
        expired = monotonic() >= deadline
        if cancelled or expired:
            if submitted:
                error = OpenCodeGoStreamCancelled if cancelled else OpenCodeGoEffectUnknown
                raise error(selected.account_id, (selected.account_id,))
            raise OpenCodeGoTransportContractError("stream cancelled or expired before submission")

    def check_request() -> None:
        try:
            result = request_check(frozen)
        except Exception:
            raise OpenCodeGoTransportContractError("current request evidence refused") from None
        if result is not None:
            raise OpenCodeGoTransportContractError("request check returned invalid result")

    def refresh_timeout() -> None:
        check_cancel_deadline()
        remaining = min(idle, deadline - monotonic())
        if remaining <= 0:
            check_cancel_deadline()
        connection.timeout = max(0.001, remaining)
        sock = getattr(connection, "sock", None)
        if sock is not None:
            sock.settimeout(connection.timeout)

    try:
        check_cancel_deadline()
        check_request()
        try:
            credential = credential_loader(selected.account_id)
            upstream = prepare_upstream_request(frozen, choice=selected, credential=credential)
        except Exception:
            raise OpenCodeGoTransportContractError("provider credential unavailable") from None
        connection = connection_factory("opencode.ai", timeout=min(idle, total))
        check_cancel_deadline()
        check_request()
        refresh_timeout()
        submitted = True  # Even an exception from request() may follow a partial write.
        connection.request("POST", urlsplit(upstream.url).path, body=upstream.body,
                           headers=dict(upstream.headers))
        refresh_timeout()
        response = connection.getresponse()
        status = response.status
        if type(status) is not int or not 100 <= status <= 599:
            raise ValueError("invalid HTTP response")
        headers = {}
        for key, value in response.getheaders():
            if key.lower() in RESPONSE_HEADERS:
                if key.lower() in headers or any(ord(c) < 32 or ord(c) == 127 for c in value):
                    raise ValueError("invalid response headers")
                headers[key.lower()] = value
        if status != 200:
            refresh_timeout()
            parts = []
            size = 0
            while True:
                refresh_timeout()
                chunk = response.read1(min(16384, MAX_ERROR_BYTES + 1 - size))
                check_cancel_deadline()
                if not isinstance(chunk, bytes):
                    raise ValueError("invalid error response")
                if not chunk:
                    break
                parts.append(chunk)
                size += len(chunk)
                if size > MAX_ERROR_BYTES:
                    raise ValueError("error response size exceeded")
            body = b"".join(parts)
            return StreamReceipt(selected.account_id, selected.pool_generation, status, 0,
                                 False, UpstreamResponse(status, headers, body))
        if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "text/event-stream":
            raise ValueError("stream response type mismatch")
        observer = _SSEObserver(frozen.path)
        while not observer.terminal:
            refresh_timeout()
            chunk = response.read1(16384)
            check_cancel_deadline()
            if not isinstance(chunk, bytes):
                raise ValueError("invalid stream bytes")
            if not chunk:
                observer.finish()
                if observer.terminal:
                    break
                raise ValueError("stream ended before terminal")
            if forwarded + len(chunk) > MAX_STREAM_BYTES:
                raise ValueError("stream size exceeded")
            observer.feed(chunk)
            on_chunk(chunk)
            forwarded += len(chunk)
        return StreamReceipt(selected.account_id, selected.pool_generation, status,
                             forwarded, True)
    except OpenCodeGoEffectUnknown:
        raise
    except OpenCodeGoTransportContractError:
        if submitted:
            raise OpenCodeGoEffectUnknown(selected.account_id, (selected.account_id,)) from None
        raise
    except Exception:
        if submitted:
            raise OpenCodeGoEffectUnknown(selected.account_id, (selected.account_id,)) from None
        raise OpenCodeGoTransportContractError("stream preparation failed") from None
    finally:
        primary_error = sys.exc_info()[0] is not None
        cleanup_failed = False
        for item in (response, connection):
            if item is not None:
                try:
                    item.close()
                except Exception:
                    cleanup_failed = True
        if cleanup_failed and not primary_error:
            if submitted:
                raise OpenCodeGoEffectUnknown(selected.account_id, (selected.account_id,)) from None
            raise OpenCodeGoTransportContractError("stream cleanup uncertain") from None
