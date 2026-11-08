"""One finite read on an already-owned native-process socket-pair endpoint.

No address, FD number, credential, listener, child, reconnect, queue or retry is
accepted here. The trusted existing process composition supplies the capability;
wire projections never authenticate themselves.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import secrets
import socket
from collections.abc import Callable, Mapping
from typing import Any

from control_plane.executive_ceo_ingress import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES

from control_plane.native_conversation_read_contract import (
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    _SHA,
    NativeReadUnavailable,
    canonical,
    _unique_object,
    _invalid_number,
    _result_data,
    validate_native_read_association,
    validate_native_read_request,
    validate_native_read_response,
    native_read_frame,
    validate_native_read_binding,
)


class OwnedNativeReadPort:
    """Nominal capability for one anonymous endpoint, under its original owner."""

    def __init__(self, endpoint: socket.socket, *, association_sha256: str):
        try:
            valid_endpoint = (
                type(endpoint) is socket.socket and endpoint.family == socket.AF_UNIX
                and endpoint.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_STREAM
                and endpoint.getsockname() in ("", b"")
                and endpoint.getpeername() in ("", b""))
        except OSError:
            valid_endpoint = False
        # getpeername proves connection and excludes listeners. SO_ACCEPTCONN
        # is unavailable on Darwin AF_UNIX socket pairs and adds no authority.
        if (not valid_endpoint or type(association_sha256) is not str
                or _SHA.fullmatch(association_sha256) is None):
            raise TypeError("owned anonymous native socket-pair capability required")
        self._endpoint = endpoint
        self._fd = endpoint.fileno()
        info = os.fstat(self._fd)
        self._identity = (info.st_dev, info.st_ino)
        self._association_sha256 = association_sha256
        self._retired = False
        self._busy = False
        endpoint.setblocking(False)

    @property
    def association_sha256(self) -> str:
        return self._association_sha256

    def require_current(self) -> None:
        try:
            info = os.fstat(self._endpoint.fileno())
            if (self._retired or self._endpoint.fileno() != self._fd
                    or (info.st_dev, info.st_ino) != self._identity):
                raise NativeReadUnavailable()
        except (OSError, ValueError):
            raise NativeReadUnavailable() from None

    def retire(self) -> None:
        if self._retired:
            return
        self._retired = True
        self._endpoint.close()

    async def read(self, *, principal_scope: str, issued_at: int, expires_at: int,
                   request: Mapping[str, Any], before_write: Callable[[], None]) -> dict[str, Any]:
        self.require_current()
        if self._busy or not callable(before_write):
            raise NativeReadUnavailable()
        if (type(principal_scope) is not str or _SHA.fullmatch(principal_scope) is None
                or type(issued_at) is not int or type(expires_at) is not int
                or not 0 <= issued_at < expires_at <= 2**53-1):
            raise NativeReadUnavailable()
        # Correlation for one finite invocation, never an authorization epoch.
        request_id = secrets.token_hex(32)
        frame = {"schema": REQUEST_SCHEMA, "request_id": request_id,
                 "association_sha256": self._association_sha256,
                 "principal": {"principal_scope": principal_scope,
                               "issued_at": issued_at, "expires_at": expires_at},
                 "read": dict(request)}
        try:
            encoded = canonical(frame) + b"\n"
        except (TypeError, ValueError, UnicodeError):
            raise NativeReadUnavailable() from None
        if len(encoded) > MAX_REQUEST_BYTES:
            raise NativeReadUnavailable()
        self._busy = True
        try:
            async with asyncio.timeout(4.0):
                self.require_current()
                guard_result = before_write()
                if guard_result is not None:
                    if inspect.iscoroutine(guard_result):
                        guard_result.close()
                    raise NativeReadUnavailable()
                loop = asyncio.get_running_loop()
                await loop.sock_sendall(self._endpoint, encoded)
                received = bytearray()
                while b"\n" not in received:
                    block = await loop.sock_recv(self._endpoint, min(4096, MAX_RESPONSE_BYTES + 1-len(received)))
                    if not block:
                        raise NativeReadUnavailable()
                    received.extend(block)
                    if len(received) > MAX_RESPONSE_BYTES:
                        raise NativeReadUnavailable()
                line, extra = bytes(received).split(b"\n", 1)
                if extra:
                    raise NativeReadUnavailable()
                value = json.loads(line.decode("utf-8", errors="strict"),
                                   object_pairs_hook=_unique_object, parse_constant=_invalid_number)
                value = validate_native_read_response(value, frame)
                self.require_current()
                return value
        except BaseException:
            # A partial frame or interrupted read cannot be re-homed/replayed.
            # Closing the original endpoint retires its native Peer as well.
            self.retire()
            raise
        finally:
            self._busy = False
