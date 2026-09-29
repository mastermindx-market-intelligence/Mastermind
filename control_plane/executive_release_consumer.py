"""Release C1 consumer over the existing Control, Runtime and root broker.

Commit is unconditionally disarmed. Approval and preparation additionally need
an installed owner composition, root policy/key/staged-byte validation and real
same-process peer qualification. No request field can supply that composition.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from collections.abc import Mapping
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
    __slots__ = ("approval", "result", "receiver_pid", "_capability")
    def __init__(self, *, approval, result, capability):
        if capability is not _BROKER_RESPONSE_CAPABILITY:
            raise ReleaseConsumerError("RELEASE_BROKER_PROVENANCE_REQUIRED")
        self.approval, self.result = approval, result
        self.receiver_pid, self._capability = os.getpid(), capability


class ReleaseBrokerClient:
    """One request to the existing fixed root-owned socket, never a retry."""
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
            capability=_BROKER_RESPONSE_CAPABILITY,
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
                                    capability=_BROKER_RESPONSE_CAPABILITY)


def _validated_release_closure(response, evidence):
    """Join root history to one canonical unresolved admission snapshot.

    This detached validation neither writes an Event nor clears maintenance.
    The caller must re-read the same evidence in its owner write transaction
    before minting a purpose-bound closure context.
    """
    code = "RELEASE_CLOSURE_UNQUALIFIED"
    if (type(response) is not _RootReleaseResponse
            or response._capability is not _BROKER_RESPONSE_CAPABILITY
            or response.receiver_pid != os.getpid()):
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
    """Existing Runtime approval persistence and broker history only."""
    def __init__(self, runtime, *, broker: ReleaseBrokerClient | None = None):
        self.runtime = runtime
        self.broker = broker if broker is not None else ReleaseBrokerClient()
        if type(self.broker) is not ReleaseBrokerClient:
            raise TypeError("release consumer requires the existing root broker client")

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
