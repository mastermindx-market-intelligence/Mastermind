"""Producer-owned forward host custody context; dormant under policy None.

Implements the frozen ``_ForwardHostContext`` core ABC against the accepted
live-origin decision: genuine accepted-connection peer capture (the UID450
origin child; PID1 is never demanded of this peer), the original absolute
deadline tightened everywhere, the seven-stage closed witness protocol on the
single accepted connection, and once-only non-effect cleanup exchange.

The existing production composer selects this fixed factory only after a
source-owned policy amendment. Importing or unit-testing it is not activation.
The closed v2 witnesses bind both current authority and the inert frozen Relay
to independently observed content. This module never cleans durable forward
evidence or manufactures custody from a prior report.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import time

from control_plane import executive_incident_origin as origin_module
from control_plane import executive_release_observation as release
from control_plane import executive_incident_release_observation as incident_release
from control_plane import executive_recovery_namespace as namespace
from control_plane.executive_peer_identity import (
    PeerIdentityError,
    _current_capture,
    capture_peer_identity,
)
from control_plane.executive_process_identity import (
    _observe_process_instance as _observe_native_instance,
)
from control_plane.executive_recovery_observation_normalization import Instance

try:
    from ops.executive_os import provider_incident_forward as forward
except ModuleNotFoundError:  # pragma: no cover - installed direct-script mode
    import provider_incident_forward as forward  # type: ignore[no-redef]

__all__ = ()

_STAGES = origin_module._STAGES
_DIGEST_STAGES = frozenset(_STAGES[2:])
_SERVICE_UID = 450
_MAX_FRAME_BYTES = 65536
_MAX_BINDINGS = 64
_CHALLENGE_KEYS = origin_module._WITNESS
_RESPONSE_KEYS = origin_module._OBS | {"nonce", "reservation_sha256"}
_CLEANUP_KEYS = _CLEANUP_ACK_KEYS = origin_module._CLOSE
_KIND_CHALLENGE = "origin-witness-challenge"
_KIND_RESPONSE = "origin-witness-response"
_KIND_CLEANUP = "origin-witness-cleanup"
_KIND_CLEANUP_ACK = "origin-witness-cleanup-ack"


class ForwardHostContextError(ValueError):
    """Closed nonsecret host-context refusal."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> None:
    raise ForwardHostContextError(code) from None


def _canonical(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _hex64(value) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _require_binding_constants(request: forward._ForwardGuardRequest) -> None:
    """The context is valid only for the exact frozen I/D/M/R/Q/F bindings."""
    if type(request.original_request_id) is not str or (
        request.original_request_id != forward.ORIGINAL_ISSUER_REQUEST_ID
    ):
        _refuse("FORWARD_HOST_IDENTITY_MISMATCH")
    for name in ("original_request_sha256", "original_marker_sha256"):
        if not _hex64(getattr(request, name)):
            _refuse("FORWARD_HOST_IDENTITY_MALFORMED")
    if request.original_request_sha256 != forward.ORIGINAL_REQUEST_SHA256:
        _refuse("FORWARD_HOST_IDENTITY_MISMATCH")
    if request.original_release_sha != forward.ORIGINAL_RELEASE_SHA:
        _refuse("FORWARD_HOST_IDENTITY_MISMATCH")
    if request.original_marker_sha256 != forward.ORIGINAL_MARKER_SHA256:
        _refuse("FORWARD_HOST_IDENTITY_MISMATCH")
    if type(request.successor_request_id) is not str or (
        request.successor_request_id != forward.SUCCESSOR_REQUEST_ID
    ):
        _refuse("FORWARD_HOST_IDENTITY_MISMATCH")
    if not _hex64(request.forward_request_sha256):
        _refuse("FORWARD_HOST_REQUEST_DIGEST_MALFORMED")
    if type(request.policy_binding) is not tuple or not (
        0 < len(request.policy_binding) <= _MAX_BINDINGS
    ) or not all(
        type(pair) is tuple and len(pair) == 2 and type(pair[0]) is str
        and type(pair[1]) is str
        for pair in request.policy_binding
    ):
        _refuse("FORWARD_HOST_POLICY_BINDING_MALFORMED")
    if type(request.sealed_source) is not tuple or not (
        0 < len(request.sealed_source) <= _MAX_BINDINGS
    ) or not all(
        type(pair) is tuple and len(pair) == 2 and type(pair[0]) is str
        and type(pair[1]) is str
        for pair in request.sealed_source
    ):
        _refuse("FORWARD_HOST_SOURCE_BINDING_MALFORMED")
    if (len(dict(request.policy_binding)) != len(request.policy_binding)
            or len(dict(request.sealed_source)) != len(request.sealed_source)):
        _refuse("FORWARD_HOST_DUPLICATE_BINDING")
    if type(request.peer_uid) is not int or request.peer_uid != _SERVICE_UID:
        _refuse("FORWARD_HOST_PEER_MALFORMED")
    if request.invocation_token is None or isinstance(
        request.invocation_token, (str, bytes, bytearray, int, float, bool, list, dict)
    ):
        _refuse("FORWARD_HOST_TOKEN_INVALID")
    if (
        type(request.deadline_monotonic_ns) is not int
        or not 0 < request.deadline_monotonic_ns < 2**63
    ):
        _refuse("FORWARD_HOST_DEADLINE_INVALID")


def _send_frame(connection: socket.socket, value: dict,
                budget: release._Budget) -> None:
    raw = _canonical(value)
    if len(raw) > _MAX_FRAME_BYTES:
        _refuse("FORWARD_HOST_FRAME_TOO_LARGE")
    budget.check(force=True)
    view = memoryview(raw)
    while view:
        connection.settimeout(budget.remaining())
        written = connection.send(view)
        if written <= 0:
            _refuse("FORWARD_HOST_CONNECTION_CLOSED")
        view = view[written:]
    budget.check(force=True)


def _read_frame(connection: socket.socket, budget: release._Budget) -> dict:
    """One bounded JSON line on the accepted connection."""
    buffer = bytearray()
    while True:
        budget.check(force=True)
        remaining = (budget.endpoint - time.monotonic_ns()) / 1_000_000_000
        if remaining <= 0:
            _refuse("FORWARD_HOST_DEADLINE_EXCEEDED")
        connection.settimeout(remaining)
        try:
            chunk = connection.recv(min(4096, _MAX_FRAME_BYTES + 1 - len(buffer)))
        except socket.timeout:
            _refuse("FORWARD_HOST_DEADLINE_EXCEEDED")
        except OSError:
            _refuse("FORWARD_HOST_CONNECTION_UNAVAILABLE")
        if not chunk:
            _refuse("FORWARD_HOST_PEER_EOF")
        buffer.extend(chunk)
        if len(buffer) > _MAX_FRAME_BYTES:
            _refuse("FORWARD_HOST_FRAME_TOO_LARGE")
        newline = buffer.find(b"\n")
        if newline >= 0:
            if newline != len(buffer) - 1:
                _refuse("FORWARD_HOST_FRAME_NOT_SINGLE")
            break
    return origin_module._parse_frame_line(bytes(buffer[:-1]), code_prefix="FORWARD_HOST")


def _instance_record(value) -> Instance:
    if (
        type(value) is not dict
        or frozenset(value) != frozenset({"pid", "unique_id", "pidversion"})
    ):
        _refuse("FORWARD_HOST_WITNESS_INSTANCE_MALFORMED")
    instance = Instance(value["pid"], value["unique_id"], value["pidversion"])
    if (
        type(instance.pid) is not int or not 0 < instance.pid < 2**31
        or type(instance.unique_id) is not int or not 0 < instance.unique_id < 2**64
        or type(instance.pidversion) is not int or not 0 < instance.pidversion < 2**31
    ):
        _refuse("FORWARD_HOST_WITNESS_INSTANCE_MALFORMED")
    return instance


def _latched(method):
    def invoke(self, *args, **kwargs):
        if self._failed:
            _refuse("FORWARD_HOST_CONTEXT_FAILED")
        try:
            return method(self, *args, **kwargs)
        except BaseException:
            self._failed = True
            raise
    return invoke


class _IncidentForwardHostContext(forward._ForwardHostContext):
    """Held custody context; revalidates fresh native joins at every stage.

    This object is private code held inside the trusted broker process.  It is
    neither a credential nor a serialized authority: it cannot cross a socket
    or parser, and it holds no policy activation.
    """

    def __init__(self, binding: forward._ForwardGuardRequest):
        self._failed = False
        self._binding = binding
        self._endpoint = binding.deadline_monotonic_ns
        self._nonce = os.urandom(16).hex()
        self._captured = None
        self._entered = False
        self._exited = False
        self._ordinal = 0
        self._stage_index = 0
        self._reservation_sha256 = None
        self._cleanup_exchanged = False
        self._held_budget = release._Budget(self._endpoint)
        self._handles = None
        self._socket_anchor = None
        self._origin_anchor = self._broker_anchor = self._boot_anchor = self._release_anchor = None
        self._binding_sha256 = None
        self._child_anchor = None
        self._cohort_anchor = None

    def _budget(self) -> release._Budget:
        # One original endpoint for acquisition, every stage and cleanup.
        return self._held_budget

    # -- context protocol ------------------------------------------------

    def __enter__(self) -> "_IncidentForwardHostContext":
        if self._entered or self._exited:
            _refuse("FORWARD_HOST_CONTEXT_STATE_INVALID")
        if type(self._binding.connection) is not socket.socket:
            _refuse("FORWARD_HOST_CONNECTION_REQUIRED")
        budget = self._budget()
        captured = budget.call(capture_peer_identity, self._binding.connection)
        # Server side captures the actual UID450 origin child.  PID1 is never
        # demanded here: launchd owns the listening end, not this peer.
        if captured.euid != _SERVICE_UID:
            _refuse("FORWARD_HOST_PEER_NOT_ORIGIN_CLIENT")
        self._captured = captured
        try:
            self._handles = namespace._acquire_namespace(deadline_monotonic_ns=self._endpoint)
            self._socket_anchor = budget.call(namespace._observe_socket_node, self._handles)
            binding = self._binding
            payload = {"I": binding.original_request_id, "D": binding.original_request_sha256,
                "M": binding.original_marker_sha256, "R": binding.original_release_sha,
                "Q": binding.successor_request_id, "F": binding.forward_request_sha256,
                "source": dict(binding.sealed_source), "policy": dict(binding.policy_binding), "nonce": self._nonce,
                "observation_purpose": incident_release._PURPOSE}
            self._binding_sha256 = hashlib.sha256(_canonical(payload)).hexdigest()
            _send_frame(binding.connection, {"kind": "origin-witness-acquire", "v": origin_module._WIRE_VERSION,
                "nonce": self._nonce, "binding": payload, "binding_sha256": self._binding_sha256,
                "deadline_monotonic_ns": self._endpoint}, budget)
            reply = _read_frame(binding.connection, budget)
            self._endpoint = origin_module._tighten(budget, reply.get("deadline_monotonic_ns"))
            origin_module._tighten(self._handles.budget, self._endpoint)
            self._check_reply(reply, "acquire", 0, None)
            self._entered = True
            return self
        except BaseException:
            self._exited = True
            if self._handles is not None:
                namespace._release_namespace(self._handles)
            raise

    def _require_child_generation(self, origin_instance, budget):
        # A captured audit token remains attached to the socket even if a
        # process at that PID execs or is replaced. Join the fresh native
        # generation to that token, and to the exact child retained at entry.
        budget.call(_current_capture, self._captured)
        native = budget.call(_observe_native_instance, self._captured.pid)
        if (type(self._captured.pidversion) is not int
                or native.pidversion != self._captured.pidversion):
            _refuse("FORWARD_HOST_CHILD_PEER_GENERATION_MISMATCH")
        child = origin_module._require_instance(
            Instance(self._captured.pid, native.unique_id, native.pidversion),
            code="FORWARD_HOST_CHILD_INSTANCE_INVALID")
        if self._child_anchor is not None and child != self._child_anchor:
            _refuse("FORWARD_HOST_CHILD_INSTANCE_DRIFT")
        if (native.parent_unique_id != origin_instance.unique_id
                or native.parent_pidversion != origin_instance.pidversion):
            _refuse("FORWARD_HOST_ORIGIN_PARENT_MISMATCH")
        budget.check(force=True)
        return child

    def _check_reply(self, reply, stage, ordinal, reservation):
        origin_module._shape(reply, _RESPONSE_KEYS, _KIND_RESPONSE)
        if (reply["stage"] != stage or type(reply["ordinal"]) is not int or reply["ordinal"] != ordinal
                or reply["nonce"] != self._nonce or reply["reservation_sha256"] != reservation
                or reply["binding_sha256"] != self._binding_sha256
                or reply["deadline_monotonic_ns"] != self._endpoint):
            _refuse("FORWARD_HOST_WITNESS_ECHO_MISMATCH")
        budget = self._budget()
        budget.call(_current_capture, self._captured)
        budget.call(namespace._recheck_namespace, self._handles)
        budget.call(namespace._require_same_socket, self._handles, self._socket_anchor)
        fresh = budget.call(incident_release._observe_incident_release, deadline_monotonic_ns=self._endpoint)
        incident_release._validate_observation(fresh)
        if (reply["purpose"] != fresh.purpose
                or reply["cohort_content_sha256"] != fresh.cohort_content_sha256
                or (self._cohort_anchor is not None and fresh.cohort_content_sha256 != self._cohort_anchor)
                or any(row.state != "UNLOADED" for row in fresh.roles[:3])):
            _refuse("FORWARD_HOST_COHORT_MISMATCH")
        origin_instance, broker_instance = _instance_record(reply["origin"]), _instance_record(reply["broker"])
        child = self._require_child_generation(origin_instance, budget)
        owners = budget.call(origin_module._observe_running_owner_set, budget,
                            origin_instance=origin_instance, broker_observation=fresh)
        digest = hashlib.sha256(_canonical({"identity": self._socket_anchor.identity})).hexdigest()
        commit = fresh.roles[0].content.release_commit
        if (owners.origin_instance != origin_instance or owners.broker_instance != broker_instance
                or owners.boot_id != fresh.boot_id or reply["boot_id"] != fresh.boot_id
                or reply["release_commit"] != commit or reply["socket_sha256"] != digest
                or commit != dict(self._binding.sealed_source).get("release_sha")
                or fresh.roles[0].content.installed_manifest_digest != dict(self._binding.sealed_source).get("manifest_sha256")):
            _refuse("FORWARD_HOST_NATIVE_JOIN_MISMATCH")
        anchors = (origin_instance, broker_instance, fresh.boot_id, commit)
        if self._origin_anchor is not None and anchors != (self._origin_anchor, self._broker_anchor, self._boot_anchor, self._release_anchor):
            _refuse("FORWARD_HOST_NATIVE_JOIN_DRIFT")
        self._origin_anchor, self._broker_anchor, self._boot_anchor, self._release_anchor = anchors
        self._child_anchor = child
        self._cohort_anchor = fresh.cohort_content_sha256
        budget.check(force=True)
        return forward._ForwardHostObservation(hashlib.sha256(_canonical(reply)).hexdigest())

    @_latched
    def revalidate(self, request: forward._ForwardGuardRequest, *, stage: str,
                   reservation_sha256: str | None) -> forward._ForwardHostObservation:
        if not self._entered or self._exited or self._captured is None:
            _refuse("FORWARD_HOST_CONTEXT_STATE_INVALID")
        if request is not self._binding:
            _refuse("FORWARD_HOST_BINDING_MISMATCH")
        if type(stage) is not str or stage not in _STAGES:
            _refuse("FORWARD_HOST_STAGE_UNKNOWN")
        if self._stage_index >= len(_STAGES) or stage != _STAGES[self._stage_index]:
            _refuse("FORWARD_HOST_STAGE_ORDER")
        if stage in _DIGEST_STAGES:
            if not _hex64(reservation_sha256):
                _refuse("FORWARD_HOST_RESERVATION_DIGEST_REQUIRED")
            if self._reservation_sha256 is None:
                self._reservation_sha256 = reservation_sha256
            elif reservation_sha256 != self._reservation_sha256:
                _refuse("FORWARD_HOST_RESERVATION_DRIFT")
        elif reservation_sha256 is not None:
            _refuse("FORWARD_HOST_RESERVATION_DIGEST_PREMATURE")
        budget = self._budget()
        budget.call(_current_capture, self._captured)
        self._ordinal += 1
        challenge = {
            "kind": _KIND_CHALLENGE,
            "v": origin_module._WIRE_VERSION,
            "stage": stage,
            "ordinal": self._ordinal,
            "nonce": self._nonce,
            "reservation_sha256": reservation_sha256,
            "deadline_monotonic_ns": self._endpoint,
            "binding_sha256": self._binding_sha256,
        }
        _send_frame(self._binding.connection, challenge, budget)
        reply = _read_frame(self._binding.connection, budget)
        result = self._check_reply(reply, stage, self._ordinal, reservation_sha256)
        self._stage_index += 1
        return result

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if not self._entered or self._exited:
            _refuse("FORWARD_HOST_CONTEXT_STATE_INVALID")
        self._exited = True
        try:
            if exc_type is None and self._stage_index == len(_STAGES):
                budget = self._budget()
                self._require_child_generation(self._origin_anchor, budget)
                budget.call(namespace._require_same_socket, self._handles, self._socket_anchor)
                cleanup = {"kind": _KIND_CLEANUP, "v": origin_module._WIRE_VERSION, "nonce": self._nonce,
                    "ordinal": self._ordinal + 1, "binding_sha256": self._binding_sha256}
                _send_frame(self._binding.connection, cleanup, budget)
                ack = _read_frame(self._binding.connection, budget)
                origin_module._shape(ack, _CLEANUP_ACK_KEYS, _KIND_CLEANUP_ACK)
                if ack != dict(cleanup, kind=_KIND_CLEANUP_ACK):
                    _refuse("FORWARD_HOST_CLEANUP_ACK_INVALID")
                self._require_child_generation(self._origin_anchor, budget)
                self._cleanup_exchanged = True
                budget.check(force=True)
        finally:
            self._captured = None
            namespace._release_namespace(self._handles)
        return False


def _make_forward_host_context(request: forward._ForwardGuardRequest):
    """Sole producer of the held custody context; never composed in production.

    Only the genuine core invocation inputs are accepted: the real accepted
    connection object, the frozen I/D/M/R/Q/F bindings and one nonserializable
    invocation token.  No expected-value report, JSON rendering, environment
    switch or saved observation can reconstruct a context.
    """
    if type(request) is not forward._ForwardGuardRequest:
        _refuse("FORWARD_HOST_REQUEST_REQUIRED")
    _require_binding_constants(request)
    if type(request.connection) is not socket.socket:
        _refuse("FORWARD_HOST_CONNECTION_REQUIRED")
    return _IncidentForwardHostContext(request)
