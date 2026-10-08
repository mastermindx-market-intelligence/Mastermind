"""Unix host transport for the COO-principal Company Dialogue facet.

The model-facing stdio edge sends only a validated tool name and arguments.
Principal identity, child binding, dialogue thread, Runtime fencing and Relay
effects remain inside the Executive-side PrincipalCompanyDialogueHost.

This module creates no daemon, queue, retry plane, credential store, principal
registry or Runtime lifecycle.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
import contextlib
import os
from pathlib import Path
import socket
from typing import Any

from integrations.company_dialogue_principal_host_contract import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    PrincipalHostFrameError,
    decode_request,
    encode_json_frame,
    encode_request,
    validate_response,
)
from control_plane.executive_peer_identity import (
    _current_capture,
    capture_peer_identity,
)
from integrations.mastermind_company_mcp.principal_schemas import (
    ERROR_CODES,
    PrincipalGatewayError,
    principal_error_envelope,
    validate_principal_tool_arguments,
)
from integrations.mastermind_company_principal_host import (
    PrincipalCompanyDialogueHost,
)


_EFFECTING = frozenset({"ruling", "continue", "stop"})


def _error(tool: str, code: str) -> dict[str, Any]:
    return principal_error_envelope(
        tool,
        code=code,
        message=code,
    )


class PrincipalCompanyDialogueSocketHost:
    """One-frame authenticated Unix frontend over an already-composed host."""

    def __init__(
        self,
        host: PrincipalCompanyDialogueHost,
        *,
        worker_uid: int,
        timeout_seconds: float = 60.0,
    ) -> None:
        if type(host) is not PrincipalCompanyDialogueHost:
            raise TypeError("principal dialogue host must be exact composed host")
        if (
            type(worker_uid) is not int
            or worker_uid <= 0
            or type(timeout_seconds) not in (int, float)
            or isinstance(timeout_seconds, bool)
            or not 0 < float(timeout_seconds) <= 60
        ):
            raise ValueError("principal dialogue socket host binding is invalid")
        self.host = host
        self.worker_uid = worker_uid
        self.timeout_seconds = float(timeout_seconds)

    async def call(self, peer: Any, frame: bytes) -> bytes:
        """Validate one request and call the existing principal gateway once."""

        try:
            _current_capture(peer)
            if peer.euid != self.worker_uid:
                raise PrincipalHostFrameError()
            tool, arguments = decode_request(frame)
            # Host revalidates arguments independently of the stdio client.
            validate_principal_tool_arguments(tool, arguments)
            result = await self.host.gateway.call(tool, arguments)
            return encode_json_frame(result, limit=MAX_RESPONSE_BYTES)
        except (PrincipalHostFrameError, PrincipalGatewayError, TypeError, ValueError):
            return encode_json_frame(
                _error("unknown", "INVALID_REQUEST"),
                limit=MAX_RESPONSE_BYTES,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return encode_json_frame(
                _error("unknown", "SERVICE_UNAVAILABLE"),
                limit=MAX_RESPONSE_BYTES,
            )

    async def handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Serve exactly one bounded request; the Executive service owns listener lifetime."""

        connected: socket.socket | None = None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                transport = writer.get_extra_info("socket")
                if transport is None:
                    return
                connected = socket.socket(fileno=os.dup(transport.fileno()))
                peer = capture_peer_identity(connected)
                if peer.euid != self.worker_uid:
                    return
                frame = await reader.readuntil(b"\n")
                if len(frame) > MAX_REQUEST_BYTES:
                    return
                writer.write(await self.call(peer, frame))
                await writer.drain()
        except (
            OSError,
            ValueError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            TimeoutError,
        ):
            pass
        finally:
            if connected is not None:
                connected.close()
            writer.close()
            with contextlib.suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), timeout=1.0)


class UnixPrincipalCompanyDialogueGateway:
    """Thin stdio-edge client bound to one installed Executive Unix socket."""

    def __init__(
        self,
        *,
        socket_path: str,
        server_uid: int,
        timeout_seconds: float = 30.0,
    ) -> None:
        if (
            type(socket_path) is not str
            or not Path(socket_path).is_absolute()
            or os.path.normpath(socket_path) != socket_path
            or "\0" in socket_path
            or len(os.fsencode(socket_path)) > 103
            or type(server_uid) is not int
            or server_uid <= 0
            or type(timeout_seconds) not in (int, float)
            or isinstance(timeout_seconds, bool)
            or not 0 < float(timeout_seconds) <= 60
        ):
            raise ValueError("invalid principal Company host binding")
        self.socket_path = socket_path
        self.server_uid = server_uid
        self.timeout_seconds = float(timeout_seconds)

    async def call(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            if arguments is None:
                raw_arguments: dict[str, Any] = {}
            elif isinstance(arguments, Mapping):
                raw_arguments = dict(arguments)
            else:
                raise TypeError("principal arguments must be a mapping")
            # Validate before opening the socket, but transmit the original
            # public shape. The Executive host validates independently and
            # derives host-owned fields such as scope_change/canonical_ref once.
            validate_principal_tool_arguments(tool_name, raw_arguments)
            request = encode_request(tool_name, raw_arguments)
        except (PrincipalGatewayError, PrincipalHostFrameError, TypeError, ValueError):
            return _error(
                tool_name if isinstance(tool_name, str) else "unknown",
                "INVALID_REQUEST",
            )

        writer: asyncio.StreamWriter | None = None
        peer_socket: socket.socket | None = None
        send_started = False
        try:
            async with asyncio.timeout(self.timeout_seconds):
                reader, writer = await asyncio.open_unix_connection(
                    self.socket_path,
                    limit=MAX_RESPONSE_BYTES + 1,
                )
                transport = writer.get_extra_info("socket")
                if transport is None:
                    return _error(tool_name, "SERVICE_UNAVAILABLE")
                peer_socket = socket.socket(fileno=os.dup(transport.fileno()))
                captured = capture_peer_identity(peer_socket)
                if captured.euid != self.server_uid:
                    return _error(tool_name, "SERVICE_UNAVAILABLE")
                _current_capture(captured)

                send_started = True
                writer.write(request)
                await writer.drain()
                response = await reader.readuntil(b"\n")
                if await reader.read(1):
                    raise PrincipalHostFrameError()
                return validate_response(response, tool=tool_name)
        except asyncio.CancelledError:
            if send_started and tool_name in _EFFECTING:
                return _error(tool_name, "EFFECT_UNKNOWN")
            raise
        except Exception:
            return _error(
                tool_name,
                "EFFECT_UNKNOWN"
                if send_started and tool_name in _EFFECTING
                else "SERVICE_UNAVAILABLE",
            )
        finally:
            if peer_socket is not None:
                peer_socket.close()
            if writer is not None:
                writer.close()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await asyncio.wait_for(writer.wait_closed(), timeout=1.0)


async def run_principal_company_dialogue_stdio(
    *,
    socket_path: str,
    server_uid: int,
    timeout_seconds: float = 30.0,
) -> None:
    """Run the existing four-tool MCP server over one installed Unix host binding."""

    gateway = UnixPrincipalCompanyDialogueGateway(
        socket_path=socket_path,
        server_uid=server_uid,
        timeout_seconds=timeout_seconds,
    )
    from integrations.mastermind_company_mcp.server import run_principal_stdio

    await run_principal_stdio(gateway)


__all__ = [
    "PrincipalCompanyDialogueSocketHost",
    "UnixPrincipalCompanyDialogueGateway",
    "run_principal_company_dialogue_stdio",
]
