#!/usr/bin/env python3
"""Fixed UID450 foreground origin client; dormant, privately launched only.

Launched exclusively by the trusted root origin factory's fixed direct child
spawn (pinned signed interpreter, ``-I -S -B``, this one sealed entrypoint,
inherited stdio).  There is no public caller-selected action, path, source,
role or endpoint: any argv refuses, the interval record arrives on inherited
stdin, and the broker endpoint is the one fixed canonical socket.

Before any action bytes the client captures its own connected-server peer and
requires the launchd transport owner (euid0/PID1) — never a plain root broker
PID — and joins a fresh independent RUNNING broker/source/socket observation
performed by its still-live root parent.  It sends the canonical closed
forward request exactly once, then services bounded private witness
challenges on that single connection while waiting for the ordinary final
response.  Parent EOF closes the socket immediately.  No origin/source hint
is ever treated as authority, the original deadline is never renewed, and no
credential or token is created.
"""
from __future__ import annotations

import json
import os
import socket
import selectors
import sys
import time

_RELEASE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RELEASE_ROOT not in sys.path:
    sys.path.insert(0, _RELEASE_ROOT)

from control_plane import executive_recovery_namespace as namespace
from control_plane import executive_incident_origin as protocol
from control_plane.executive_privileged_client import validate_forward_recovery_response
from control_plane.executive_peer_identity import (
    PeerIdentityError,
    capture_peer_identity,
    _current_capture,
)
from control_plane.executive_process_identity import _observe_process_instance

try:
    from ops.executive_os import provider_incident_forward as forward
except ModuleNotFoundError:  # pragma: no cover - installed direct-script mode
    import provider_incident_forward as forward  # type: ignore[no-redef]

__all__ = ()

_BROKER_SOCKET = namespace._CANONICAL
_WIRE_RESPONSE_SCHEMA = "mastermind.executive_privileged_action_response.v1"
_MAX_FRAME_BYTES = 65536
_MAX_WITNESS_EXCHANGES = 16
_LOCAL_TIMEOUT_CAP_SECONDS = 30.0
_INTERVAL_KEYS = frozenset({
    "kind", "v", "boot_id", "release_commit", "origin",
    "deadline_monotonic_ns", "request", "socket", "purpose", "cohort_content_sha256",
})
_PRECHECK_KEYS = frozenset({
    "kind", "v", "boot_id", "release_commit", "broker", "socket_sha256", "purpose", "cohort_content_sha256",
})
_OBSERVATION_KEYS = frozenset({
    "kind", "v", "stage", "ordinal", "boot_id", "release_commit",
    "origin", "broker", "socket_sha256", "purpose", "cohort_content_sha256",
})
_CHALLENGE_KEYS = frozenset({
    "kind", "v", "stage", "ordinal", "nonce", "reservation_sha256",
    "deadline_monotonic_ns",
})
_CLEANUP_KEYS = frozenset({"kind", "v", "nonce", "ordinal"})
_KIND_CHALLENGE = "origin-witness-challenge"
_KIND_CLEANUP = "origin-witness-cleanup"


class OriginClientError(ValueError):
    """Closed nonsecret client refusal; never a fabricated wire response."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> None:
    raise OriginClientError(code) from None


def _canonical(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


_StreamBuffer = protocol._FrameBuffer


def _parse_frame_line(line, *, code_prefix):
    try:
        return protocol._parse_frame_line(line, code_prefix=code_prefix)
    except protocol.OriginIntervalError as error:
        _refuse(error.code)


def _read_stream_frame(stream, buffer=None, budget=None):
    # The first inherited frame has a finite acquisition ceiling; every later
    # read uses the retained, possibly tightened original interval budget.
    if budget is None:
        budget = protocol.release._Budget(time.monotonic_ns() + 30_000_000_000)
    try:
        return protocol._stream_frame(stream, _StreamBuffer() if buffer is None else buffer, budget)
    except protocol.OriginIntervalError as error:
        _refuse(error.code)


def _write_stream_frame(stream, value, budget):
    protocol._stream_send(stream, value, budget)


def _read_socket_frame(connection: socket.socket, endpoint: int,
                       buffer: _StreamBuffer, parent_stream=None) -> dict:
    code_prefix = "CLIENT_SERVER"
    while True:
        remaining = (endpoint - time.monotonic_ns()) / 1_000_000_000
        if remaining <= 0:
            _refuse("CLIENT_DEADLINE_EXPIRED")
        line = buffer.extract(code_prefix=code_prefix)
        if line is not None:
            return _parse_frame_line(line, code_prefix=code_prefix)
        if parent_stream is not None:
            # The parent can disappear while the broker is silent. Monitor the
            # owned inherited channel as well as the broker, without waiting
            # for a timeout or inventing a successor owner.
            with selectors.DefaultSelector() as selector:
                selector.register(connection, selectors.EVENT_READ, "broker")
                selector.register(parent_stream, selectors.EVENT_READ, "parent")
                ready = selector.select(min(.05, remaining))
            if any(key.data == "parent" for key, _ in ready):
                _refuse("CLIENT_PARENT_EOF_OR_UNSOLICITED_FRAME")
            if not ready:
                continue
        connection.settimeout(min(_LOCAL_TIMEOUT_CAP_SECONDS, remaining))
        try:
            chunk = connection.recv(4096)
        except socket.timeout:
            _refuse("CLIENT_DEADLINE_EXPIRED")
        except OSError:
            _refuse("CLIENT_CONNECTION_UNAVAILABLE")
        if not chunk:
            _refuse("CLIENT_SERVER_EOF")
        buffer.feed(chunk, code_prefix=code_prefix)


def _send_socket_frame(connection: socket.socket, value: dict,
                       endpoint: int) -> None:
    raw = _canonical(value)
    if len(raw) > _MAX_FRAME_BYTES:
        _refuse("CLIENT_SERVER_FRAME_TOO_LARGE")
    view = memoryview(raw)
    while view:
        remaining = (endpoint - time.monotonic_ns()) / 1_000_000_000
        if remaining <= 0:
            _refuse("CLIENT_DEADLINE_EXPIRED")
        connection.settimeout(min(_LOCAL_TIMEOUT_CAP_SECONDS, remaining))
        written = connection.send(view)
        if written <= 0:
            _refuse("CLIENT_CONNECTION_CLOSED")
        view = view[written:]
    if time.monotonic_ns() >= endpoint:
        _refuse("CLIENT_DEADLINE_EXPIRED")


def _instance_fields(value) -> dict:
    if (
        type(value) is not dict
        or frozenset(value) != frozenset({"pid", "unique_id", "pidversion"})
        or type(value["pid"]) is not int or not 0 < value["pid"] < 2**31
        or type(value["unique_id"]) is not int
        or not 0 < value["unique_id"] < 2**64
        or type(value["pidversion"]) is not int
        or not 0 < value["pidversion"] < 2**31
    ):
        _refuse("CLIENT_INSTANCE_MALFORMED")
    return value


def _run_origin_client(*, stdin=None, stdout=None) -> int:
    stdin = sys.stdin.buffer if stdin is None else stdin
    stdout = sys.stdout.buffer if stdout is None else stdout
    parent_buffer, socket_buffer = _StreamBuffer(), _StreamBuffer()
    budget = protocol.release._Budget(time.monotonic_ns() + 30_000_000_000)
    interval = _read_stream_frame(stdin, parent_buffer, budget)
    protocol._shape(interval, _INTERVAL_KEYS, "origin-interval")
    if interval["socket"] != _BROKER_SOCKET or not protocol._hex(interval["release_commit"], 40):
        _refuse("CLIENT_INTERVAL_MALFORMED")
    if (interval["purpose"] != protocol.incident_release._PURPOSE
            or not protocol._hex(interval["cohort_content_sha256"])):
        _refuse("CLIENT_INTERVAL_PURPOSE_REFUSED")
    protocol._tighten(budget, interval["deadline_monotonic_ns"])
    origin_instance = _instance_fields(interval["origin"])
    request, forward_digest = forward.validate_forward_request(interval["request"])
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    captured = None
    acquired = closed = False
    nonce = binding_digest = None
    ordinal = 0

    def parent(frame):
        _write_stream_frame(stdout, frame, budget)
        value = _read_stream_frame(stdin, parent_buffer, budget)
        if value is None: _refuse("CLIENT_PARENT_EOF")
        return value

    def live():
        budget.check(force=True)
        _current_capture(captured)
        own = _observe_process_instance(os.getpid())
        if (own.parent_unique_id != origin_instance["unique_id"] or
                own.parent_pidversion != origin_instance["pidversion"]):
            _refuse("CLIENT_PARENT_NOT_LIVE")

    try:
        connection.settimeout(budget.remaining())
        connection.connect(_BROKER_SOCKET)
        captured = capture_peer_identity(connection)
        if captured.euid != 0 or captured.pid != 1:
            _refuse("CLIENT_SERVER_PEER_NOT_LAUNCHD")
        live()
        precheck = parent({"kind": "need-precheck", "v": protocol._WIRE_VERSION})
        protocol._shape(precheck, _PRECHECK_KEYS, "precheck")
        if (precheck["boot_id"] != interval["boot_id"] or
                precheck["release_commit"] != interval["release_commit"] or
                precheck["purpose"] != interval["purpose"] or
                precheck["cohort_content_sha256"] != interval["cohort_content_sha256"] or
                not protocol._hex(precheck["socket_sha256"])):
            _refuse("CLIENT_PRECHECK_MISMATCH")
        _instance_fields(precheck["broker"])
        # Parent records the attempt before acknowledging. Every partial or
        # uncertain write after this edge remains UNKNOWN in the parent.
        ack = parent({"kind": "sent", "v": protocol._WIRE_VERSION, "forward_request_sha256": forward_digest})
        protocol._shape(ack, {"kind", "v", "forward_request_sha256"}, "attempt-ack")
        if ack["forward_request_sha256"] != forward_digest: _refuse("CLIENT_ATTEMPT_MISMATCH")
        live()
        connection.settimeout(budget.remaining())
        connection.sendall(_canonical(request.to_dict()))
        while True:
            live()
            frame = _read_socket_frame(connection, budget.endpoint, socket_buffer, stdin)
            kind = frame.get("kind")
            if kind == "origin-witness-acquire":
                protocol._shape(frame, protocol._ACQUIRE, kind)
                if acquired or not protocol._hex(frame["nonce"], 32): _refuse("CLIENT_ACQUIRE_REPLAY")
                expected_digest = protocol.hashlib.sha256(_canonical(frame["binding"])).hexdigest()
                if (frame["binding_sha256"] != expected_digest or frame["binding"].get("F") != forward_digest
                        or frame["binding"].get("nonce") != frame["nonce"]
                        or frame["binding"].get("observation_purpose") != interval["purpose"]):
                    _refuse("CLIENT_BINDING_MISMATCH")
                protocol._tighten(budget, frame["deadline_monotonic_ns"])
                # Relay our earlier retained ceiling; the trusted parent will
                # take the minimum and independently reconstruct the binding.
                frame = dict(frame, deadline_monotonic_ns=budget.endpoint)
                observation = parent(frame)
                protocol._shape(observation, protocol._OBS, "observation")
                protocol._tighten(budget, observation["deadline_monotonic_ns"])
                nonce, binding_digest = frame["nonce"], expected_digest
                expected_stage, expected_ordinal = "acquire", 0
                acquired = True
            elif kind == _KIND_CHALLENGE:
                protocol._shape(frame, protocol._WITNESS, kind)
                if (not acquired or closed or ordinal >= len(protocol._STAGES)
                        or frame["stage"] != protocol._STAGES[ordinal]
                        or type(frame["ordinal"]) is not int or frame["ordinal"] != ordinal + 1
                        or frame["nonce"] != nonce or frame["binding_sha256"] != binding_digest
                        or frame["deadline_monotonic_ns"] != budget.endpoint):
                    _refuse("CLIENT_CHALLENGE_MISMATCH")
                ordinal += 1
                observation = parent(frame)
                protocol._shape(observation, protocol._OBS, "observation")
                expected_stage, expected_ordinal = frame["stage"], ordinal
            elif kind == _KIND_CLEANUP:
                protocol._shape(frame, protocol._CLOSE, kind)
                if (closed or not acquired or ordinal != len(protocol._STAGES)
                        or frame["ordinal"] != ordinal + 1 or frame["nonce"] != nonce
                        or frame["binding_sha256"] != binding_digest):
                    _refuse("CLIENT_CLEANUP_MISMATCH")
                ack = parent(frame)
                if ack != dict(frame, kind="origin-witness-cleanup-ack"):
                    _refuse("CLIENT_CLEANUP_UNPROVEN")
                closed = True
                _send_socket_frame(connection, ack, budget.endpoint)
                continue
            else:
                response = validate_forward_recovery_response(frame, request.to_dict(),
                    expected_release_sha=interval["release_commit"])
                if response["ok"] and not closed: _refuse("CLIENT_SUCCESS_BEFORE_CLEANUP")
                _write_stream_frame(stdout, {"kind": "response", "v": protocol._WIRE_VERSION, "response": response}, budget)
                return 0
            if (observation["stage"] != expected_stage or type(observation["ordinal"]) is not int
                    or observation["ordinal"] != expected_ordinal or observation["binding_sha256"] != binding_digest
                    or observation["deadline_monotonic_ns"] != budget.endpoint
                    or observation["origin"] != origin_instance or observation["boot_id"] != interval["boot_id"]
                    or observation["release_commit"] != interval["release_commit"]
                    or observation["purpose"] != interval["purpose"]
                    or observation["cohort_content_sha256"] != interval["cohort_content_sha256"]
                    or observation["broker"] != precheck["broker"] or observation["socket_sha256"] != precheck["socket_sha256"]):
                _refuse("CLIENT_OBSERVATION_MISMATCH")
            live()
            reply = dict(observation, kind="origin-witness-response", nonce=nonce,
                         reservation_sha256=frame.get("reservation_sha256"))
            _send_socket_frame(connection, reply, budget.endpoint)
    finally:
        # No unbounded extra read waiting for a nonexistent done frame.
        connection.close()


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        _refuse("CLIENT_ARGUMENTS_REFUSED")
    return _run_origin_client()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OriginClientError as error:
        sys.stderr.write(error.code + "\n")
        raise SystemExit(3)
