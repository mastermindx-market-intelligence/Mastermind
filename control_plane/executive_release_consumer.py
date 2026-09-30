"""Release C1 consumer over the existing Control, Runtime and root broker.

Commit is unconditionally disarmed. Approval and preparation additionally need
an installed owner composition, root policy/key/staged-byte validation and real
same-process peer qualification. No request field can supply that composition.
"""
from __future__ import annotations

import hashlib
import dataclasses
import json
import os
import sqlite3
import threading
import time
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from control_plane import executive_release_contract as contract
from control_plane import executive_release_ingress as ingress
from control_plane.executive_authority import release_principal_projection
from control_plane.executive_peer_identity import capture_peer_identity, require_installed_service_peer
from control_plane.executive_installed_peer import qualify_installed_peer
from control_plane.executive_runtime import (
    ReleaseMaintenanceError, TrustedReleaseContext, _RELEASE_MAINTENANCE_CAPABILITY,
)

BROKER_SCHEMA = "mastermind.executive_release_broker/v1"
_BROKER_RESPONSE_CAPABILITY = object()
_RESERVATION_RESPONSE_CAPABILITY = object()
_FRESH_RELEASE_ADMISSION_CAPABILITY = object()
_START_RESPONSE_CAPABILITY = object()


class ReleaseConsumerError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _hash(value):
    return hashlib.sha256(contract.canonical_release_bytes(value)).hexdigest()


def _current_principal(principal, now_ms):
    if (type(now_ms) is not int or type(principal.issued_at) is not int
            or type(principal.expires_at) is not int
            or not principal.issued_at * 1000 <= now_ms < principal.expires_at * 1000):
        raise ReleaseConsumerError("RELEASE_PRINCIPAL_NOT_CURRENT")
    return release_principal_projection(principal)


def _qualify_connection(connection, role):
    # Capture and qualification happen in this actual serving process while
    # the accepted socket remains live. No capture/context crosses a helper.
    peer = capture_peer_identity(connection)
    binding = qualify_installed_peer(peer, role=role)
    return require_installed_service_peer(peer, binding)


class _RootReleaseResponse:
    __slots__ = ("approval", "result", "operation", "receiver_pid", "_capability")
    def __init__(self, *, approval, result, capability, operation=None):
        if capability is not _BROKER_RESPONSE_CAPABILITY:
            raise ReleaseConsumerError("RELEASE_BROKER_PROVENANCE_REQUIRED")
        self.approval, self.result = approval, result
        self.operation = operation
        self.receiver_pid, self._capability = os.getpid(), capability


class _ProcessLocalReleaseEvidence:
    """Private provenance and opaque tokens must not survive this process."""
    __slots__ = ()

    def __copy__(self):
        raise TypeError("release evidence is process-local")

    def __deepcopy__(self, memo):
        raise TypeError("release evidence is process-local")

    def __reduce_ex__(self, protocol):
        raise TypeError("release evidence is process-local")

    def __getstate__(self):
        raise TypeError("release evidence is process-local")

    def __setstate__(self, state):
        raise TypeError("release evidence is process-local")


@dataclasses.dataclass(frozen=True, slots=True, repr=False)
class _RootReleaseAdmissionResponse(_ProcessLocalReleaseEvidence):
    # Frozen slotted dataclasses otherwise generate restoring state hooks.
    __getstate__ = _ProcessLocalReleaseEvidence.__getstate__
    __setstate__ = _ProcessLocalReleaseEvidence.__setstate__

    frame_bytes: bytes
    approval: contract.ReleaseRecord
    reservation: contract.ReleaseRecord
    _capability: object
    receiver_pid: int = dataclasses.field(default_factory=os.getpid)


@dataclasses.dataclass(frozen=True, slots=True, repr=False, init=False)
class _FreshReleaseAdmission(_ProcessLocalReleaseEvidence):
    # Frozen slotted dataclasses otherwise generate restoring state hooks.
    __getstate__ = _ProcessLocalReleaseEvidence.__getstate__
    __setstate__ = _ProcessLocalReleaseEvidence.__setstate__

    root_response: _RootReleaseAdmissionResponse
    admission_evidence: Mapping
    _capability: object
    receiver_pid: int
    _consumed: bool
    _lock: Any

    def __init__(self, *args, **kwargs):
        # Generic construction, replacement and reinitialization never issue
        # START authority. Only the canonical new-admission path creates it.
        raise ReleaseConsumerError("RELEASE_FRESH_ADMISSION_REQUIRED")

    def _consume(self):
        # The one-shot bit is consumed even when preflight or transport fails.
        # There is no serialization, copy, restore, or public retry selector.
        with self._lock:
            if (self._capability is not _FRESH_RELEASE_ADMISSION_CAPABILITY
                    or self.receiver_pid != os.getpid() or self._consumed):
                raise ReleaseConsumerError("RELEASE_FRESH_ADMISSION_REQUIRED")
            object.__setattr__(self, "_consumed", True)
            frame, approval, reservation = _validated_reservation_response(
                self.root_response)
            evidence = _joined_admission_evidence(
                self.admission_evidence, approval, reservation)
            return frame, approval, reservation, evidence


@dataclasses.dataclass(frozen=True, slots=True, repr=False)
class _RootReleaseStartResponse(_ProcessLocalReleaseEvidence):
    # Frozen slotted dataclasses otherwise generate restoring state hooks.
    __getstate__ = _ProcessLocalReleaseEvidence.__getstate__
    __setstate__ = _ProcessLocalReleaseEvidence.__setstate__

    approval: contract.ReleaseRecord
    reservation: contract.ReleaseRecord
    admission: contract.ReleaseRecord
    start_record: contract.ReleaseRecord
    _capability: object
    receiver_pid: int = dataclasses.field(default_factory=os.getpid)


def _detached_commit_frame(frame):
    if type(frame) is not ingress.ReleaseFrame:
        raise ReleaseConsumerError("RELEASE_FRAME_INVALID")
    raw = ingress.encode_frame(ingress.project_frame(
        frame.operation, frame.arguments, principal=frame.principal))
    detached = ingress.decode_frame(raw)
    if detached.operation != "commit_prepared_release_transition":
        raise ReleaseConsumerError("RELEASE_FRAME_INVALID")
    return detached, raw


def _current_commit_approval(frame, approval):
    original = contract.validate_approval_evidence(approval)
    now = time.time_ns() // 1_000_000
    if (original["operation_key"] != frame.arguments["operation_key"]
            or original["principal_projection"] != _current_principal(frame.principal, now)
            or not original["created_at_ms"] <= now < original["expires_at_ms"]):
        raise ReleaseConsumerError("RELEASE_APPROVAL_NOT_CURRENT")
    return original


def _validated_reservation_response(response):
    if (type(response) is not _RootReleaseAdmissionResponse
            or response._capability is not _RESERVATION_RESPONSE_CAPABILITY
            or response.receiver_pid != os.getpid()):
        raise ReleaseConsumerError("RELEASE_RESERVATION_PROVENANCE_REQUIRED")
    frame = ingress.decode_frame(response.frame_bytes)
    frame, raw = _detached_commit_frame(frame)
    if raw != response.frame_bytes:
        raise ReleaseConsumerError("RELEASE_FRAME_INVALID")
    approval = _current_commit_approval(frame, response.approval)
    reservation = contract.validate_release_prestart_reservation(
        response.reservation, expected_approval=approval)
    prepared = reservation["prepared_payload"]
    now, monotonic = time.time_ns() // 1_000_000, time.monotonic_ns()
    if (reservation["prepared_token_digest"]
            != hashlib.sha256(frame.arguments["prepared_token"].encode("ascii")).hexdigest()
            or not reservation["reserved_at_ms"] <= now < prepared["expires_at_ms"]
            or not reservation["reserved_monotonic_ns"] <= monotonic < prepared["expires_monotonic_ns"]):
        raise ReleaseConsumerError("RELEASE_RESERVATION_NOT_CURRENT")
    return frame, approval, reservation


def _joined_admission_evidence(evidence, approval, reservation):
    code = "RELEASE_ADMISSION_READBACK_UNKNOWN"
    if not isinstance(evidence, Mapping) or set(evidence) != {
            "approval", "admission", "preconditions", "root_qualification_digest"}:
        raise ReleaseConsumerError(code)
    original = contract.validate_approval_evidence(evidence["approval"])
    admission = contract.validate_admission(evidence["admission"])
    preconditions = contract.validate_precondition_manifest(evidence["preconditions"])
    if (contract.canonical_release_bytes(original) != contract.canonical_release_bytes(approval)
            or contract.canonical_release_bytes(preconditions)
            != contract.canonical_release_bytes(reservation["preconditions"])
            or evidence["root_qualification_digest"] != _hash(reservation)):
        raise ReleaseConsumerError(code)
    from control_plane.executive_release_actuator import _ExecutiveReleaseActuatorJournal
    # Pure protected validation only: no journal construction or filesystem IO.
    _ExecutiveReleaseActuatorJournal._validate_admission_joins(
        admission, reservation, approval["operation_key"])
    return MappingProxyType({
        "approval": original, "admission": admission, "preconditions": preconditions,
        "root_qualification_digest": evidence["root_qualification_digest"],
    })


def _private_release_result(response, operation, approval, fields):
    code = "RELEASE_BROKER_RESPONSE_UNKNOWN"
    if (type(response) is not dict or response.get("schema") != BROKER_SCHEMA
            or response.get("operation") != operation or type(response.get("ok")) is not bool):
        raise ReleaseConsumerError(code)
    if not response["ok"]:
        if (set(response) != {"schema", "operation", "ok", "error"}
                or type(response["error"]) is not str or response["error"] not in {
                    "RELEASE_OWNER_UNCONFIGURED", "RELEASE_COMMIT_DISARMED", "RELEASE_REFUSED"}):
            raise ReleaseConsumerError(code)
        raise ReleaseConsumerError(response["error"])
    if set(response) != {"schema", "operation", "ok", "approval", "result"}:
        raise ReleaseConsumerError(code)
    returned = contract.validate_approval_evidence(response["approval"])
    if contract.canonical_release_bytes(returned) != contract.canonical_release_bytes(approval):
        raise ReleaseConsumerError("RELEASE_BROKER_APPROVAL_CHANGED")
    if type(response["result"]) is not dict or set(response["result"]) != fields:
        raise ReleaseConsumerError(code)
    return response["result"]


def _trusted_admission_context(runtime, connection, response):
    from control_plane import executive_runtime as runtime_api
    _, approval, reservation = _validated_reservation_response(response)
    # Reuse the canonical context record, never its test mint. Actual root
    # provenance is required before constructing the private Runtime context.
    record = runtime.release_maintenance._admission_context_record(
        approval=approval, request_fingerprint=contract.request_fingerprint_for(approval),
        preconditions=reservation["preconditions"],
        target_observation_digest=reservation["target_observation_digest"],
        prepared_deadline_ms=reservation["prepared_payload"]["expires_at_ms"],
        root_qualification_digest=_hash(reservation),
    )
    return runtime_api.TrustedReleaseAdmissionContext(
        _store=runtime.store, _connection=connection,
        _evidence_digest=_hash({"purpose": "admission", "record": record}),
        _capability=runtime_api._RELEASE_ADMISSION_CAPABILITY,
        _record=MappingProxyType(record),
    )


class ReleaseBrokerClient:
    """One request to the existing fixed root-owned socket, never a retry."""
    def reserve_release_prestart(self, *, frame, approval):
        from control_plane.executive_privileged_client import _send_one_frame, DEFAULT_SOCKET
        from control_plane.executive_installed_peer import _observe_real_boot_id
        detached, raw = _detached_commit_frame(frame)
        original = _current_commit_approval(detached, approval)
        public = ingress.project_frame(detached.operation, detached.arguments, principal=detached.principal)
        operation = "reserve_release_prestart"
        reply = _send_one_frame(
            {"schema": BROKER_SCHEMA, "operation": operation,
             "arguments": public["arguments"], "principal": public["principal"],
             "approval": original.to_dict()},
            socket_path=DEFAULT_SOCKET, timeout_seconds=15, require_root_peer=True,
        )
        result = _private_release_result(reply, operation, original, {"reservation"})
        reservation = contract.validate_release_prestart_reservation(
            result["reservation"], expected_approval=original)
        if reservation["preconditions"]["boot_id"] != _observe_real_boot_id():
            raise ReleaseConsumerError("RELEASE_RESERVATION_BOOT_CHANGED")
        response = _RootReleaseAdmissionResponse(
            raw, original, reservation, _RESERVATION_RESPONSE_CAPABILITY)
        _validated_reservation_response(response)
        return response

    def start_reserved_release(self, *, fresh_admission):
        from control_plane.executive_privileged_client import _send_one_frame, DEFAULT_SOCKET
        from control_plane.executive_release_actuator import (
            _validate_record, _ExecutiveReleaseActuatorJournal,
        )
        if type(fresh_admission) is not _FreshReleaseAdmission:
            raise ReleaseConsumerError("RELEASE_FRESH_ADMISSION_REQUIRED")
        frame, approval, reservation, evidence = fresh_admission._consume()
        public = ingress.project_frame(frame.operation, frame.arguments, principal=frame.principal)
        operation = "start_reserved_release"
        reply = _send_one_frame(
            {"schema": BROKER_SCHEMA, "operation": operation,
             "arguments": public["arguments"], "principal": public["principal"],
             "approval": approval.to_dict(), "reservation": reservation.to_dict(),
             "admission": evidence["admission"].to_dict()},
            socket_path=DEFAULT_SOCKET, timeout_seconds=15, require_root_peer=True,
        )
        result = _private_release_result(
            reply, operation, approval, {"reservation", "admission", "start_record"})
        if (contract.canonical_release_bytes(result["reservation"])
                != contract.canonical_release_bytes(reservation)
                or contract.canonical_release_bytes(result["admission"])
                != contract.canonical_release_bytes(evidence["admission"])):
            raise ReleaseConsumerError("RELEASE_START_READBACK_UNKNOWN")
        start = _validate_record(result["start_record"])
        _ExecutiveReleaseActuatorJournal._validate_start_reservation_joins(
            start, reservation, approval)
        _ExecutiveReleaseActuatorJournal._validate_admission_joins(
            start["admission"], reservation, approval["operation_key"])
        if (start["state"] != "STARTED" or start["journal_generation"] != 1
                or start["root_qualification_digest"] != _hash(reservation)
                or contract.canonical_release_bytes(start["admission"])
                != contract.canonical_release_bytes(evidence["admission"])):
            raise ReleaseConsumerError("RELEASE_START_READBACK_UNKNOWN")
        return _RootReleaseStartResponse(
            approval, reservation, evidence["admission"], start, _START_RESPONSE_CAPABILITY)

    def read_release_closure(self, *, approval) -> _RootReleaseResponse:
        """Private history query for the installed Control owner.

        The original sealed approval is evidence, not a renewed Web principal.
        This operation has no token, reservation, START, or effect selector.
        """
        from control_plane.executive_privileged_client import (
            _send_one_frame, DEFAULT_SOCKET,
        )
        original = contract.validate_approval_evidence(approval)
        operation = "read_release_closure"
        response = _send_one_frame(
            {"schema": BROKER_SCHEMA, "operation": operation,
             "approval": original.to_dict()},
            socket_path=DEFAULT_SOCKET, timeout_seconds=15, require_root_peer=True,
        )
        if (type(response) is not dict or response.get("schema") != BROKER_SCHEMA
                or response.get("operation") != operation
                or type(response.get("ok")) is not bool):
            raise ReleaseConsumerError("RELEASE_BROKER_RESPONSE_UNKNOWN")
        if not response["ok"]:
            if (set(response) != {"schema", "operation", "ok", "error"}
                    or type(response["error"]) is not str
                    or response["error"] not in {
                        "RELEASE_OWNER_UNCONFIGURED", "RELEASE_COMMIT_DISARMED",
                        "RELEASE_REFUSED"}):
                raise ReleaseConsumerError("RELEASE_BROKER_RESPONSE_UNKNOWN")
            raise ReleaseConsumerError(response["error"])
        if set(response) != {"schema", "operation", "ok", "approval", "result"}:
            raise ReleaseConsumerError("RELEASE_BROKER_RESPONSE_UNKNOWN")
        validated = contract.validate_approval_evidence(response["approval"])
        if contract.canonical_release_bytes(validated) != contract.canonical_release_bytes(original):
            raise ReleaseConsumerError("RELEASE_BROKER_APPROVAL_CHANGED")
        if (type(response["result"]) is not dict
                or set(response["result"]) != {
                    "reservation", "terminal_status", "cancellation"}):
            raise ReleaseConsumerError("RELEASE_BROKER_RESPONSE_UNKNOWN")
        return _RootReleaseResponse(
            approval=validated, result=response["result"],
            capability=_BROKER_RESPONSE_CAPABILITY, operation=operation,
        )

    def exchange(self, frame: ingress.ReleaseFrame, *, approval=None) -> _RootReleaseResponse:
        from control_plane.executive_privileged_client import (
            _send_one_frame, DEFAULT_SOCKET,
        )
        public = ingress.project_frame(frame.operation, frame.arguments, principal=frame.principal)
        payload = {**public, "schema": BROKER_SCHEMA,
                   "approval": None if approval is None else approval.to_dict()}
        response = _send_one_frame(payload, socket_path=DEFAULT_SOCKET,
                                   timeout_seconds=15, require_root_peer=True)
        if (type(response) is not dict or response.get("schema") != BROKER_SCHEMA
                or response.get("operation") != frame.operation
                or type(response.get("ok")) is not bool):
            raise ReleaseConsumerError("RELEASE_BROKER_RESPONSE_UNKNOWN")
        if not response["ok"]:
            if (set(response) != {"schema", "operation", "ok", "error"}
                    or type(response["error"]) is not str or response["error"] not in {
                        "RELEASE_OWNER_UNCONFIGURED", "RELEASE_COMMIT_DISARMED", "RELEASE_REFUSED"}):
                raise ReleaseConsumerError("RELEASE_BROKER_RESPONSE_UNKNOWN")
            raise ReleaseConsumerError(response["error"])
        if set(response) != {"schema", "operation", "ok", "approval", "result"}:
            raise ReleaseConsumerError("RELEASE_BROKER_RESPONSE_UNKNOWN")
        validated = contract.validate_approval_evidence(response["approval"])
        # Correlate every immutable identity before issuing any local context.
        expected_ref = contract.approval_ref_for(frame.arguments["operation_key"])
        if (validated["approved_transition_ref"] != expected_ref
                or validated["principal_projection"] != release_principal_projection(frame.principal)):
            raise ReleaseConsumerError("RELEASE_BROKER_IDENTITY_MISMATCH")
        if frame.operation == "approve_release_transition" and (
                validated["action"] != frame.arguments["action"]
                or validated["transition_digest"] != frame.arguments["transition_digest"]):
            raise ReleaseConsumerError("RELEASE_BROKER_IDENTITY_MISMATCH")
        if approval is not None and contract.canonical_release_bytes(validated) != contract.canonical_release_bytes(approval):
            raise ReleaseConsumerError("RELEASE_BROKER_APPROVAL_CHANGED")
        return _RootReleaseResponse(approval=validated, result=response["result"],
                                    capability=_BROKER_RESPONSE_CAPABILITY,
                                    operation=frame.operation)


def _validated_release_closure(response, evidence):
    """Join root history to one canonical unresolved admission snapshot.

    This detached validation neither writes an Event nor clears maintenance.
    The caller must re-read the same evidence in its owner write transaction
    before minting a purpose-bound closure context.
    """
    code = "RELEASE_CLOSURE_UNQUALIFIED"
    if (type(response) is not _RootReleaseResponse
            or response._capability is not _BROKER_RESPONSE_CAPABILITY
            or response.receiver_pid != os.getpid()
            or response.operation != "read_release_closure"):
        raise ReleaseConsumerError("RELEASE_BROKER_PROVENANCE_REQUIRED")
    if (not isinstance(evidence, Mapping) or set(evidence) != {
            "approval", "admission", "preconditions", "root_qualification_digest"}):
        raise ReleaseConsumerError(code)
    approval = contract.validate_approval_evidence(evidence["approval"])
    admission = contract.validate_admission(evidence["admission"])
    preconditions = contract.validate_precondition_manifest(evidence["preconditions"])
    if contract.canonical_release_bytes(response.approval) != contract.canonical_release_bytes(approval):
        raise ReleaseConsumerError(code)
    result = response.result
    if (type(result) is not dict or set(result) != {
            "reservation", "terminal_status", "cancellation"}
            or result["reservation"] is None
            or (result["terminal_status"] is None) == (result["cancellation"] is None)):
        raise ReleaseConsumerError(code)
    reservation = contract.validate_release_prestart_reservation(
        result["reservation"], expected_approval=approval)
    if (_hash(reservation) != evidence["root_qualification_digest"]
            or contract.canonical_release_bytes(reservation["preconditions"])
            != contract.canonical_release_bytes(preconditions)
            or reservation["target_observation_digest"] != admission["target_observation_digest"]):
        raise ReleaseConsumerError(code)
    if result["cancellation"] is not None:
        cancellation = contract.validate_release_prestart_cancellation(
            result["cancellation"], expected_reservation=reservation,
            expected_admission=admission, expected_approval=approval)
        return "cancellation", cancellation, reservation
    status = contract.validate_release_terminal_status(
        result["terminal_status"], expected_approval=approval)
    if status["state"] == "NOT_FOUND":
        raise ReleaseConsumerError(code)
    if status["state"] not in {"SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED"}:
        raise ReleaseConsumerError("RELEASE_EFFECT_IN_PROGRESS")
    if (contract.canonical_release_bytes(status["admission"])
            != contract.canonical_release_bytes(admission)
            or contract.canonical_release_bytes(status["preconditions"])
            != contract.canonical_release_bytes(preconditions)
            or contract.canonical_release_bytes(status["terminal_receipt"]["before"])
            != contract.canonical_release_bytes(reservation["before"])
            or status["started_at_ms"] < reservation["reserved_at_ms"]):
        raise ReleaseConsumerError(code)
    return "terminal", status, reservation


def _trusted_closure_context(runtime, connection, response, evidence):
    # No test mint, public mapping, or historical approval-only context can
    # supply this purpose. Provenance is rechecked in the owner transaction.
    from control_plane import executive_runtime as runtime_api

    kind, outcome, reservation = _validated_release_closure(response, evidence)
    approval = contract.validate_approval_evidence(evidence["approval"])
    # The release canonicalizer accepts closed record primitives, not the
    # transport's nullable union or boolean envelope. Hash the qualified
    # semantic observation after verifying its actual root provenance.
    observation_digest = _hash({
        "schema": "mastermind.executive_release_closure_observation/v1",
        "purpose": kind, "approval_evidence_digest": _hash(approval),
        "reservation_digest": _hash(reservation), "outcome_digest": _hash(outcome),
    })
    record = {
        "approval_evidence_digest": _hash(approval),
        "request_fingerprint": contract.request_fingerprint_for(approval),
        "admission_digest": _hash(evidence["admission"]),
        "journal_observation_digest": observation_digest,
        "owner_installation_id": approval["owner_installation_id"],
        "target_ref": approval["target_ref"],
        "principal_digest": _hash(approval["principal_projection"]),
        "grant_digest": approval["effective_grant_digest"],
        "key_id": approval["owner_seal"]["key_id"],
        "trust_generation": approval["owner_seal"]["trust_generation"],
    }
    if kind == "terminal":
        purpose = "closing"
        record.update(
            schema="mastermind.executive_release_closing_context/v1",
            terminal_status_digest=_hash(outcome),
            terminal_receipt_digest=_hash(outcome["terminal_receipt"]),
        )
        context_type = getattr(runtime_api, "TrustedReleaseClosingContext", None)
        capability = getattr(runtime_api, "_RELEASE_CLOSING_CAPABILITY", None)
    else:
        purpose = "cancellation"
        record.update(
            schema="mastermind.executive_release_cancellation_context/v1",
            reservation_digest=_hash(reservation), cancellation_digest=_hash(outcome),
            root_qualification_digest=evidence["root_qualification_digest"],
        )
        context_type = getattr(runtime_api, "TrustedReleaseCancellationContext", None)
        capability = getattr(runtime_api, "_RELEASE_CANCELLATION_CAPABILITY", None)
    if context_type is None or capability is None:
        raise ReleaseConsumerError("RELEASE_RUNTIME_CLOSURE_UNAVAILABLE")
    context = context_type(
        _store=runtime.store, _connection=connection,
        _evidence_digest=_hash({"purpose": purpose, "record": record}),
        _capability=capability, _record=MappingProxyType(record),
    )
    return kind, outcome, reservation, context


def _trusted_context(runtime, connection, response):
    # New production composition seam. It deliberately does not import the
    # Runtime's test mint. Only a correlated reply on the verified root socket
    # can supply this receipt; its store/connection binding is one transaction.
    if (type(response) is not _RootReleaseResponse
            or response._capability is not _BROKER_RESPONSE_CAPABILITY
            or response.receiver_pid != os.getpid()):
        raise ReleaseConsumerError("RELEASE_BROKER_PROVENANCE_REQUIRED")
    approval = response.approval
    grant, seal = approval["grant"], approval["owner_seal"]
    return TrustedReleaseContext(
        _store=runtime.store, _connection=connection,
        _sealed_evidence_digest=_hash(approval),
        _principal_digest=_hash(approval["principal_projection"]),
        _target_ref=approval["target_ref"],
        _owner_installation_id=approval["owner_installation_id"],
        _policy_id=grant["policy_id"], _policy_generation=grant["policy_generation"],
        _authority_policy_hash=grant["authority_policy_hash"],
        _key_id=seal["key_id"], _trust_generation=seal["trust_generation"],
        _capability=_RELEASE_MAINTENANCE_CAPABILITY,
    )


class ReleaseControlConsumer:
    """One Runtime owner for approval, closure and disarmed private composition."""
    def __init__(self, runtime, *, broker: ReleaseBrokerClient | None = None):
        self.runtime = runtime
        self.broker = broker if broker is not None else ReleaseBrokerClient()
        if type(self.broker) is not ReleaseBrokerClient:
            raise TypeError("release consumer requires the existing root broker client")

    def _reserve_and_admit(self, *, frame, connection):
        """Private R8.2 composition; public commit remains disarmed.

        A historical admission cannot reserve or acquire a START capability.
        The qualified serving connection is never held across a helper process.
        """
        frame, serving_frame = _detached_commit_frame(frame)
        _qualify_connection(connection, "gateway")
        approval = self._read(frame.arguments["operation_key"])
        if approval is None:
            raise ReleaseConsumerError("RELEASE_APPROVAL_NOT_FOUND")
        approval = _current_commit_approval(frame, approval)
        registry = self.runtime.release_maintenance
        identity = {"approved_transition_ref": approval["approved_transition_ref"],
                    "request_fingerprint": contract.request_fingerprint_for(approval)}
        with self.runtime.store.read() as sql:
            previous = registry.read_admission(sql, **identity)
            pending = registry.read_unresolved_admission(sql)
        if previous is not None:
            if pending is not None:
                if contract.canonical_release_bytes(pending["admission"]) != contract.canonical_release_bytes(previous):
                    raise ReleaseConsumerError("RELEASE_EFFECT_IN_PROGRESS")
                self.finalize_unresolved_admission()
            return None
        if pending is not None:
            raise ReleaseConsumerError("RELEASE_EFFECT_IN_PROGRESS")
        response = self.broker.reserve_release_prestart(frame=frame, approval=approval)
        _, original, reservation = _validated_reservation_response(response)
        if (response.frame_bytes != serving_frame
                or contract.canonical_release_bytes(original) != contract.canonical_release_bytes(approval)):
            raise ReleaseConsumerError("RELEASE_RESERVATION_PROVENANCE_REQUIRED")
        _qualify_connection(connection, "gateway")
        with self.runtime.store.transaction() as sql:
            # The same write lock must prove absence before the new insert.
            # An idempotent writer return is never evidence of freshness.
            if registry.read_admission(sql, **identity) is not None:
                raise ReleaseConsumerError("RELEASE_ADMISSION_NO_LONGER_FRESH")
            context = _trusted_admission_context(self.runtime, sql, response)
            recorded = registry.record_admission(
                sql, sealed_approval=original, request_fingerprint=identity["request_fingerprint"],
                preconditions=reservation["preconditions"],
                target_observation_digest=reservation["target_observation_digest"],
                trusted_context=context,
            )
            readback = registry.read_admission(sql, **identity)
            if readback is None or contract.canonical_release_bytes(recorded) != contract.canonical_release_bytes(readback):
                raise ReleaseConsumerError("RELEASE_ADMISSION_READBACK_UNKNOWN")
        with self.runtime.store.read() as sql:
            public = registry.read_admission(sql, **identity)
            evidence = _joined_admission_evidence(
                registry.read_admission_evidence(sql, **identity), original, reservation)
            pending = registry.read_unresolved_admission(sql)
            if (public is None or pending is None
                    or contract.canonical_release_bytes(recorded) != contract.canonical_release_bytes(public)
                    or contract.canonical_release_bytes(recorded) != contract.canonical_release_bytes(evidence["admission"])
                    or contract.canonical_release_bytes(pending) != contract.canonical_release_bytes(evidence)):
                raise ReleaseConsumerError("RELEASE_ADMISSION_READBACK_UNKNOWN")
        _qualify_connection(connection, "gateway")
        _validated_reservation_response(response)
        # Keep issuance local to this proven new-admission path: no generic
        # constructor, restoration hook or separately callable mint can reset it.
        fresh = object.__new__(_FreshReleaseAdmission)
        object.__setattr__(fresh, "root_response", response)
        object.__setattr__(fresh, "admission_evidence", evidence)
        object.__setattr__(fresh, "_capability", _FRESH_RELEASE_ADMISSION_CAPABILITY)
        object.__setattr__(fresh, "receiver_pid", os.getpid())
        object.__setattr__(fresh, "_consumed", False)
        object.__setattr__(fresh, "_lock", threading.Lock())
        return fresh

    def finalize_unresolved_admission(self) -> None:
        """Close qualified historical work through the one Runtime owner.

        Startup/canary callers quarantine on any exception. The root query is
        outside SQL; its result never authorizes reserve, START, or execution.
        """
        registry = self.runtime.release_maintenance
        if not all(callable(getattr(registry, name, None)) for name in (
                "read_unresolved_admission", "record_terminal", "record_cancellation")):
            raise ReleaseConsumerError("RELEASE_RUNTIME_CLOSURE_UNAVAILABLE")
        with self.runtime.store.read() as connection:
            original = registry.read_unresolved_admission(connection)
            if original is None:
                return None
            original_bytes = contract.canonical_release_bytes(original)
            # Detach before releasing the snapshot, even if a future reader
            # implementation accidentally exposes a mutable mapping.
            evidence = json.loads(original_bytes)
        response = self.broker.read_release_closure(approval=evidence["approval"])
        _validated_release_closure(response, evidence)
        with self.runtime.store.transaction() as connection:
            current = registry.read_unresolved_admission(connection)
            if (current is None
                    or contract.canonical_release_bytes(current) != original_bytes):
                raise ReleaseConsumerError("RELEASE_CLOSURE_ADMISSION_CHANGED")
            kind, outcome, reservation, context = _trusted_closure_context(
                self.runtime, connection, response, current)
            identity = {
                "approved_transition_ref": evidence["approval"]["approved_transition_ref"],
                "request_fingerprint": contract.request_fingerprint_for(evidence["approval"]),
                "trusted_context": context,
            }
            if kind == "terminal":
                recorded = registry.record_terminal(
                    connection, terminal_status=outcome, **identity)
            else:
                recorded = registry.record_cancellation(
                    connection, reservation=reservation, cancellation=outcome, **identity)
            if contract.canonical_release_bytes(recorded) != contract.canonical_release_bytes(outcome):
                raise ReleaseConsumerError("RELEASE_CLOSURE_READBACK_UNKNOWN")
        with self.runtime.store.read() as connection:
            if registry.read_unresolved_admission(connection) is not None:
                raise ReleaseConsumerError("RELEASE_CLOSURE_READBACK_UNKNOWN")
        return None

    def _read(self, operation_key):
        with self.runtime.store.read() as connection:
            try:
                return self.runtime.release_maintenance.read_approval(
                    connection, approved_transition_ref=contract.approval_ref_for(operation_key))
            except ReleaseMaintenanceError as exc:
                if exc.field == "approval" and exc.code == "NOT_FOUND":
                    return None
                raise

    def _history_admission_matches(self, approval, status):
        """Read the original admission through the one canonical registry.

        This intentionally fails closed until the Runtime owner implements its
        Event-qualified read seam. No journal bytes can manufacture admission,
        and this consumer never persists an admission or releases maintenance.
        """
        registry = self.runtime.release_maintenance
        read_admission = getattr(registry, "read_admission", None)
        if not callable(read_admission):
            return False
        with self.runtime.store.read() as connection:
            original = registry.read_approval(
                connection, approved_transition_ref=approval["approved_transition_ref"])
            if contract.canonical_release_bytes(original) != contract.canonical_release_bytes(approval):
                return False
            admission = read_admission(
                connection, approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=status["request_fingerprint"])
            if admission is None:
                return False
            validated = contract.validate_admission(admission)
            return contract.canonical_release_bytes(validated) == contract.canonical_release_bytes(status["admission"])

    def handle(self, raw: bytes, connection) -> dict:
        frame = ingress.decode_frame(raw)
        _qualify_connection(connection, "gateway")
        principal = _current_principal(frame.principal, time.time_ns() // 1_000_000)
        operation, arguments = frame.operation, frame.arguments
        result = {"schema": ingress.RESPONSE_SCHEMA, "operation": operation, "ok": True}
        if operation == "commit_prepared_release_transition":
            return {**result, "ok": False, "error": {"code": "RELEASE_COMMIT_DISARMED"}}
        approval = self._read(arguments["operation_key"])
        if approval is not None and approval["principal_projection"] != principal:
            raise ReleaseConsumerError("RELEASE_APPROVAL_PRINCIPAL_MISMATCH")
        if operation == "reconcile_release_transition":
            # Root verifies the original seal using current owner history
            # trust, without staging, expiry renewal, tokens or new Events.
            if approval is None:
                return {**result, "approval": None, "broker_status": None}
            response = self.broker.exchange(frame, approval=approval)
            _qualify_connection(connection, "gateway")
            _current_principal(frame.principal, time.time_ns() // 1_000_000)
            code = "RELEASE_HISTORY_FAMILY_UNQUALIFIED"
            try:
                if type(response.result) is not dict or set(response.result) != {"terminal_status"}:
                    raise ReleaseConsumerError(code)
                status = contract.validate_release_terminal_status(
                    response.result["terminal_status"], expected_approval=approval)
                if status["state"] != "NOT_FOUND":
                    code = "RELEASE_HISTORY_ADMISSION_UNQUALIFIED"
                    if not self._history_admission_matches(approval, status):
                        raise ReleaseConsumerError(code)
                if status["state"] in {"STARTED", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING"}:
                    code = "RELEASE_EFFECT_IN_PROGRESS"
                    raise ReleaseConsumerError(code)
            except (AttributeError, KeyError, TypeError, ValueError, OSError, RuntimeError, sqlite3.Error):
                # No legacy P2 status query, fallback, resend or new Event.
                # Unqualified and in-progress history never attest an outcome.
                return {**result, "ok": False, "effect": "EFFECT_UNKNOWN",
                        "error": {"code": code}}
            _qualify_connection(connection, "gateway")
            _current_principal(frame.principal, time.time_ns() // 1_000_000)
            return {**result, "approval": approval.to_dict(), "broker_status": status.to_dict()}
        if operation == "prepare_release_transition" and approval is None:
            raise ReleaseConsumerError("RELEASE_APPROVAL_NOT_FOUND")
        _qualify_connection(connection, "gateway")
        response = self.broker.exchange(frame, approval=approval)
        _qualify_connection(connection, "gateway")
        _current_principal(frame.principal, time.time_ns() // 1_000_000)
        if operation == "approve_release_transition":
            with self.runtime.store.transaction() as connection:
                now = time.time_ns() // 1_000_000
                if not response.approval["created_at_ms"] <= now < response.approval["expires_at_ms"]:
                    raise ReleaseConsumerError("RELEASE_APPROVAL_EXPIRED")
                recorded = self.runtime.release_maintenance.record_approval(
                    connection, sealed_approval=response.approval,
                    trusted_context=_trusted_context(self.runtime, connection, response))
            # Read back canonical bytes before returning an approval reference.
            original = self._read(arguments["operation_key"])
            if original != recorded:
                raise ReleaseConsumerError("RELEASE_APPROVAL_READBACK_UNKNOWN")
            return {**result, "approved_transition_ref": recorded["approved_transition_ref"],
                    "approval_evidence_digest": _hash(recorded)}
        if type(response.result) is not dict or set(response.result) != {"preview", "prepared_token", "expires_at_ms"}:
            raise ReleaseConsumerError("RELEASE_BROKER_RESPONSE_UNKNOWN")
        ingress.validate_arguments("commit_prepared_release_transition",
                                   {"operation_key": arguments["operation_key"],
                                    "prepared_token": response.result["prepared_token"]})
        expiry = response.result["expires_at_ms"]
        now = time.time_ns() // 1_000_000
        effect = approval["normalized_requested_effect"]
        preview = {"action": effect["action"], "target_ref": approval["target_ref"],
                   "from_release": effect["from_release_commit"], "to_release": effect["to_release_commit"]}
        if (type(expiry) is not int or not now < expiry <= min(now + 300_000, approval["expires_at_ms"])
                or response.result["preview"] != preview):
            raise ReleaseConsumerError("RELEASE_BROKER_RESPONSE_UNKNOWN")
        # Token production occurs only inside the root owner. Control neither
        # receives its key nor copies approval records into a parallel store.
        return {**result, **response.result}
