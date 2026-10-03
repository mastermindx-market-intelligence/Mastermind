"""One-request Unix client for the incumbent Company consultation gateway.

No identity selector, retry, listener, Runtime mutation, or provider operation
is available here. The installed host independently authenticates each call.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
import contextlib
import os
from pathlib import Path
import socket
from typing import Any

from common.company_consultation_host_contract import (
    HostFrameError,
    MAX_RESPONSE_BYTES,
    TOOLS,
    decode_json_frame,
    encode_request,
)
from control_plane.executive_peer_identity import (
    _current_capture,
    capture_peer_identity,
)
from integrations.mastermind_company_mcp.consultation import (
    COMPANY_CONSULTATION_ERROR_CODES,
    COMPANY_CONSULTATION_RESULT_SCHEMA,
    COMPANY_CONSULTATION_SERVER_IDENTITY,
    COMPANY_CONSULTATION_SERVER_VERSION,
    CompanyConsultationToolError,
    _error,
    _closed_ambiguous_error_data,
    validate_company_consultation_tool_arguments,
)

_EFFECTING = frozenset({"company.consult", "company.reply"})


def _validated_response(frame: bytes, tool: str) -> dict[str, Any]:
    value = decode_json_frame(frame, limit=MAX_RESPONSE_BYTES)
    if (
        set(value) != {
            "schema", "tool", "ok", "server_identity", "server_version", "data", "error",
        }
        or value["schema"] != COMPANY_CONSULTATION_RESULT_SCHEMA
        or value["tool"] != tool
        or value["server_identity"] != COMPANY_CONSULTATION_SERVER_IDENTITY
        or value["server_version"] != COMPANY_CONSULTATION_SERVER_VERSION
        or type(value["ok"]) is not bool
    ):
        raise HostFrameError()
    if value["ok"]:
        if value["error"] is not None:
            raise HostFrameError()
    else:
        error = value["error"]
        if (
            type(error) is not dict or set(error) != {"code", "message"}
            or type(error["code"]) is not str
            or error["code"] not in COMPANY_CONSULTATION_ERROR_CODES
            or error["message"] != error["code"]
            or (error["code"] != "AMBIGUOUS" and value["data"] is not None)
            or (error["code"] == "AMBIGUOUS"
                and value["data"] != _closed_ambiguous_error_data(value["data"]))
        ):
            raise HostFrameError()
    return value


class UnixCompanyConsultationGateway:
    """Thin tools-only frontend; socket and server UID are installed bindings."""

    def __init__(
        self, *, socket_path: str, server_uid: int, timeout_seconds: float = 30.0,
    ) -> None:
        if (
            type(socket_path) is not str or not Path(socket_path).is_absolute()
            or os.path.normpath(socket_path) != socket_path or "\0" in socket_path
            or len(os.fsencode(socket_path)) > 103
            or type(server_uid) is not int or server_uid <= 0
            or type(timeout_seconds) not in (int, float)
            or not 0 < timeout_seconds <= 60
        ):
            raise ValueError("invalid Company host binding")
        self.socket_path = socket_path
        self.server_uid = server_uid
        self.timeout_seconds = timeout_seconds

    async def call(self, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if type(tool_name) is not str or tool_name not in TOOLS:
            return _error("unknown", "INVALID_REQUEST")
        # Existing semantic validation owns the tool argument contract.
        try:
            normalized = validate_company_consultation_tool_arguments(tool_name, arguments)
            request = encode_request(tool_name, normalized)
        except (CompanyConsultationToolError, HostFrameError, TypeError, ValueError):
            return _error(tool_name, "INVALID_REQUEST")
        writer = None
        peer_socket = None
        send_started = False
        try:
            async with asyncio.timeout(self.timeout_seconds):
                reader, writer = await asyncio.open_unix_connection(
                    self.socket_path, limit=MAX_RESPONSE_BYTES + 1,
                )
                transport_socket = writer.get_extra_info("socket")
                if transport_socket is None:
                    return _error(tool_name, "UNAVAILABLE")
                # Retain a real duplicate of this exact accepted connection;
                # never wrap/close the transport's owned descriptor.
                peer_socket = socket.socket(fileno=os.dup(transport_socket.fileno()))
                captured = capture_peer_identity(peer_socket)
                if captured.euid != self.server_uid:
                    return _error(tool_name, "ACCESS_REFUSED")
                _current_capture(captured)
                send_started = True
                writer.write(request)
                await writer.drain()
                response = await reader.readuntil(b"\n")
                # The host sends one frame then EOF. Never accept a second frame.
                if await reader.read(1):
                    raise HostFrameError()
                # EOF closes the authenticated peer; Darwin then withdraws its
                # live audit token. This dedicated reader remains bound to the
                # same connection authenticated before the request was sent.
                return _validated_response(response, tool_name)
        except asyncio.CancelledError:
            if send_started and tool_name in _EFFECTING:
                return _error(tool_name, "EFFECT_UNKNOWN")
            raise
        except Exception:
            return _error(
                tool_name,
                "EFFECT_UNKNOWN" if send_started and tool_name in _EFFECTING else "UNAVAILABLE",
            )
        finally:
            if peer_socket is not None:
                peer_socket.close()
            if writer is not None:
                writer.close()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
