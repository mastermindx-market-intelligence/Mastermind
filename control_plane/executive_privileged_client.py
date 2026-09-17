"""One shared, one-send transport and response validation for the privileged broker.

This is the single importable client used by both scripts/mmx_admin.py and
any control-service caller. It owns the fixed production socket, the
bounded one-frame Unix-socket request/response transport, and exact
effect/status response validation. It performs no automatic retry or
failover and accepts no caller-selected production socket path. It does
not duplicate the action catalog, executor, or receipt store; effect
correlation reuses
control_plane.executive_privileged_broker.validate_terminal_receipt.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
from pathlib import Path
from typing import Mapping

from control_plane.executive_privileged_action import (
    canonical_request_bytes,
    validate_request,
    validate_status_request,
)
from control_plane.executive_privileged_broker import (
    BrokerTrustError,
    STATUS_EFFECT_UNKNOWN,
    STATUS_NOT_FOUND,
    STATUS_TERMINAL,
    WIRE_RESPONSE_SCHEMA,
    validate_terminal_receipt,
)


DEFAULT_SOCKET = Path("/var/run/mastermind-executive/privileged.sock")
DEFAULT_CLIENT_TIMEOUT_SECONDS = 11 * 60
_MAX_RESPONSE_BYTES = 128 * 1024
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


def _read_response(connection: socket.socket) -> dict[str, object]:
    buffer = bytearray()
    while True:
        chunk = connection.recv(min(4096, _MAX_RESPONSE_BYTES + 1 - len(buffer)))
        if not chunk:
            raise RuntimeError("privileged broker closed before a response")
        buffer.extend(chunk)
        if len(buffer) > _MAX_RESPONSE_BYTES:
            raise RuntimeError("privileged broker response exceeded the client bound")
        newline = buffer.find(b"\n")
        if newline >= 0:
            if newline != len(buffer) - 1:
                raise RuntimeError("privileged broker returned multiple frames")
            break
    value = json.loads(bytes(buffer[:-1]).decode("utf-8", errors="strict"))
    if not isinstance(value, dict) or not isinstance(value.get("ok"), bool):
        raise RuntimeError("privileged broker returned an invalid response")
    return value


def _send_one_frame(
    payload: Mapping[str, object],
    *,
    socket_path: Path,
    timeout_seconds: int,
) -> dict[str, object]:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout_seconds)
        connection.connect(str(socket_path))
        connection.sendall(encoded)
        return _read_response(connection)
    finally:
        connection.close()


def send_effect(
    request: Mapping[str, object],
    *,
    socket_path: Path = DEFAULT_SOCKET,
    timeout_seconds: int = DEFAULT_CLIENT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Send one validated effect request over one bounded connection; no retry."""
    validated = validate_request(request)
    return _send_one_frame(validated.to_dict(), socket_path=socket_path, timeout_seconds=timeout_seconds)


def send_status(
    request: Mapping[str, object],
    *,
    socket_path: Path = DEFAULT_SOCKET,
    timeout_seconds: int = DEFAULT_CLIENT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Send one validated status request over one bounded connection; no retry."""
    validated = validate_status_request(request)
    return _send_one_frame(validated.to_dict(), socket_path=socket_path, timeout_seconds=timeout_seconds)


def validate_effect_response(
    response: Mapping[str, object],
    request: Mapping[str, object],
    *,
    expected_release_sha: str | None = None,
) -> dict[str, object]:
    """Validate a wire effect response's shape and its exact correlation to the request.

    Returns the response once it is known safe to inspect. Raises
    ``RuntimeError`` for a malformed/ambiguous envelope and
    ``BrokerTrustError`` for a validated but uncorrelated terminal receipt.
    """
    if response.get("schema") != WIRE_RESPONSE_SCHEMA or not isinstance(response.get("ok"), bool):
        raise RuntimeError("privileged broker returned an invalid effect response")
    if response["ok"] is False:
        if frozenset(response) != frozenset({"schema", "ok", "error", "detail"}):
            raise RuntimeError("privileged broker returned an invalid refusal response")
        if not isinstance(response.get("error"), str) or not isinstance(response.get("detail"), str):
            raise RuntimeError("privileged broker returned an invalid refusal response")
        return dict(response)
    if (
        frozenset(response) != frozenset({"schema", "ok", "replayed", "receipt"})
        or not isinstance(response.get("replayed"), bool)
        or not isinstance(response.get("receipt"), dict)
    ):
        raise RuntimeError("privileged broker returned an invalid success response")
    validated = validate_request(request)
    digest = hashlib.sha256(canonical_request_bytes(validated)).hexdigest()
    receipt = validate_terminal_receipt(
        response["receipt"],
        expected_request_id=validated.request_id,
        expected_request_sha256=digest,
        expected_release_sha=expected_release_sha,
        expected_action=validated.action,
    )
    return {"schema": response["schema"], "ok": True, "replayed": response["replayed"], "receipt": receipt}


def validate_status_response(
    response: Mapping[str, object],
    *,
    expected_request_id: str,
) -> dict[str, object]:
    """Validate the exact broker status envelope and complete historical receipt.

    A successful query does not assert that the original effect succeeded.
    Historical receipt/marker releases deliberately need not equal the currently
    installed release. Validation grants no effect or retry authority.
    """
    if (
        not isinstance(response, Mapping)
        or response.get("schema") != WIRE_RESPONSE_SCHEMA
        or response.get("ok") is not True
        or response.get("query") is not True
        or response.get("request_id") != expected_request_id
        or not isinstance(response.get("installed_release_sha"), str)
        or _SHA40_RE.fullmatch(response["installed_release_sha"]) is None
    ):
        raise RuntimeError("privileged broker returned an invalid status response")
    base_keys = frozenset({
        "schema", "ok", "query", "status", "request_id", "installed_release_sha",
    })
    status = response.get("status")
    if status == STATUS_TERMINAL:
        expected_keys = base_keys | {"receipt"}
    elif status == STATUS_EFFECT_UNKNOWN:
        expected_keys = base_keys | {"marker_release_sha"}
    elif status == STATUS_NOT_FOUND:
        expected_keys = base_keys
    else:
        raise RuntimeError("privileged broker returned an unknown status")
    if frozenset(response) != expected_keys:
        raise RuntimeError("privileged broker returned an invalid status envelope")
    result = dict(response)
    if status == STATUS_TERMINAL:
        result["receipt"] = validate_terminal_receipt(
            response["receipt"], expected_request_id=expected_request_id,
        )
    elif status == STATUS_EFFECT_UNKNOWN:
        marker_release = response["marker_release_sha"]
        if not isinstance(marker_release, str) or _SHA40_RE.fullmatch(marker_release) is None:
            raise RuntimeError("privileged broker returned an invalid marker release")
    return result


__all__ = [
    "BrokerTrustError",
    "DEFAULT_SOCKET",
    "DEFAULT_CLIENT_TIMEOUT_SECONDS",
    "send_effect",
    "send_status",
    "validate_effect_response",
    "validate_status_response",
]
