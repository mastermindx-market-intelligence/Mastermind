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
import time
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
    STATUS_RECONCILED_NOT_APPLIED,
    STATUS_TERMINAL,
    WIRE_RESPONSE_SCHEMA,
    validate_terminal_receipt,
    validate_reconciliation_record,
)


DEFAULT_SOCKET = Path("/var/run/mastermind-executive/privileged.sock")
DEFAULT_CLIENT_TIMEOUT_SECONDS = 11 * 60
_MAX_RESPONSE_BYTES = 128 * 1024
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_DEADLINE_EXPIRED = "privileged broker client deadline expired"


def _validated_deadline(deadline_monotonic_ns: int) -> int:
    """Return the one absolute endpoint, refusing a non-exact or non-positive int.

    ``bool``, ``int`` subclasses, floats and strings are all refused, so no
    caller can smuggle a relative or truthy value into the deadline path.
    """
    if type(deadline_monotonic_ns) is not int:
        raise TypeError("deadline_monotonic_ns must be an exact int")
    if deadline_monotonic_ns <= 0:
        raise ValueError("deadline_monotonic_ns must be positive")
    return deadline_monotonic_ns


def _require_within_deadline(deadline_monotonic_ns: int) -> None:
    """Acceptance fence: a phase returning at or after the endpoint is not success.

    Syscalls, JSON parsing and close cannot be preempted mid-flight, so this
    only refuses to accept work that finished past the endpoint. Expiry is not
    evidence that the broker did not apply an effect.
    """
    if deadline_monotonic_ns - time.monotonic_ns() <= 0:
        raise TimeoutError(_DEADLINE_EXPIRED)


def _clamped_timeout_seconds(existing_timeout_seconds, deadline_monotonic_ns: int) -> float:
    """Return min(existing timeout, remaining endpoint); refuse an expired wait."""
    remaining_ns = deadline_monotonic_ns - time.monotonic_ns()
    if remaining_ns <= 0:
        raise TimeoutError(_DEADLINE_EXPIRED)
    if existing_timeout_seconds is not None:
        # Preserve nonblocking zero and let settimeout reject a negative local
        # limit, exactly as it does without an aggregate deadline. Compare in
        # nanoseconds before division so a large integer endpoint cannot overflow
        # when the ordinary finite socket limit is already the tighter bound.
        if remaining_ns >= existing_timeout_seconds * 1_000_000_000:
            return existing_timeout_seconds
    return remaining_ns / 1_000_000_000


def _read_response(
    connection: socket.socket,
    *,
    deadline_monotonic_ns: int | None = None,
) -> dict[str, object]:
    deadline = None if deadline_monotonic_ns is None else _validated_deadline(deadline_monotonic_ns)
    if deadline is not None:
        _require_within_deadline(deadline)
    buffer = bytearray()
    while True:
        if deadline is not None:
            # The live socket timeout is already at most the original bound, so
            # clamping against it keeps every recv at min(existing, remaining).
            connection.settimeout(_clamped_timeout_seconds(connection.gettimeout(), deadline))
        chunk = connection.recv(min(4096, _MAX_RESPONSE_BYTES + 1 - len(buffer)))
        if deadline is not None:
            _require_within_deadline(deadline)
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
    if deadline is not None:
        _require_within_deadline(deadline)
    value = json.loads(bytes(buffer[:-1]).decode("utf-8", errors="strict"))
    if deadline is not None:
        _require_within_deadline(deadline)
    if not isinstance(value, dict) or not isinstance(value.get("ok"), bool):
        raise RuntimeError("privileged broker returned an invalid response")
    if deadline is not None:
        _require_within_deadline(deadline)
    return value


def _send_one_frame(
    payload: Mapping[str, object],
    *,
    socket_path: Path,
    timeout_seconds: int,
    require_root_peer: bool = False,
    deadline_monotonic_ns: int | None = None,
) -> dict[str, object]:
    deadline = None
    if deadline_monotonic_ns is not None:
        deadline = _validated_deadline(deadline_monotonic_ns)
        _require_within_deadline(deadline)
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if deadline is None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.settimeout(timeout_seconds)
            connection.connect(str(socket_path))
            if require_root_peer:
                # P4's Control caller verifies the root end before sending any
                # principal/approval bytes. There is no UID fallback on platforms
                # without the Darwin connected-peer primitive.
                if not hasattr(connection, "getpeereid") or connection.getpeereid()[0] != 0:
                    raise RuntimeError("release broker root peer unavailable")
            connection.sendall(encoded)
            return _read_response(connection)
        finally:
            connection.close()
    _require_within_deadline(deadline)
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        _require_within_deadline(deadline)
        connection.settimeout(_clamped_timeout_seconds(timeout_seconds, deadline))
        connection.connect(str(socket_path))
        _require_within_deadline(deadline)
        if require_root_peer:
            if not hasattr(connection, "getpeereid") or connection.getpeereid()[0] != 0:
                raise RuntimeError("release broker root peer unavailable")
            _require_within_deadline(deadline)
        connection.settimeout(_clamped_timeout_seconds(timeout_seconds, deadline))
        connection.sendall(encoded)
        _require_within_deadline(deadline)
        response = _read_response(connection, deadline_monotonic_ns=deadline)
    except BaseException:
        try:
            connection.close()
        except BaseException:
            # Cleanup is attempted once without replacing the active failure.
            pass
        raise
    connection.close()
    _require_within_deadline(deadline)
    return response


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
    require_root_peer: bool = False,
) -> dict[str, object]:
    """Send one validated status request over one bounded connection; no retry."""
    validated = validate_status_request(request)
    if require_root_peer:
        return _send_one_frame(validated.to_dict(), socket_path=socket_path,
                               timeout_seconds=timeout_seconds, require_root_peer=True)
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
    elif status == STATUS_RECONCILED_NOT_APPLIED:
        expected_keys = base_keys | {"marker_release_sha", "reconciliation"}
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
    elif status in (STATUS_EFFECT_UNKNOWN, STATUS_RECONCILED_NOT_APPLIED):
        marker_release = response["marker_release_sha"]
        if not isinstance(marker_release, str) or _SHA40_RE.fullmatch(marker_release) is None:
            raise RuntimeError("privileged broker returned an invalid marker release")
        if status == STATUS_RECONCILED_NOT_APPLIED:
            record = validate_reconciliation_record(
                response["reconciliation"], expected_request_id=expected_request_id,
            )
            if record["target_release_sha"] != marker_release:
                raise RuntimeError("privileged broker reconciliation differs from marker release")
            result["reconciliation"] = record
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
