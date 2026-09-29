"""Release C1 consumer over the existing Control, Runtime and root broker.

Commit is unconditionally disarmed. Approval and preparation additionally need
an installed owner composition, root policy/key/staged-byte validation and real
same-process peer qualification. No request field can supply that composition.
"""
from __future__ import annotations

import hashlib
import os
import time
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
            raise ReleaseConsumerError("RELEASE_BROKER_REFUSED")
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
            self.broker.exchange(frame, approval=approval)
            from control_plane.executive_privileged_client import send_status, validate_status_response
            from control_plane.executive_privileged_action import STATUS_REQUEST_SCHEMA
            request_id = contract.broker_request_id_for(contract.request_fingerprint_for(approval))
            status = send_status({"schema": STATUS_REQUEST_SCHEMA, "request_id": request_id},
                                 require_root_peer=True)
            projection = validate_status_response(status, expected_request_id=request_id)
            _qualify_connection(connection, "gateway")
            _current_principal(frame.principal, time.time_ns() // 1_000_000)
            if projection["status"] != "NOT_FOUND":
                # C1 has no P4 actuator/receipt schema. A historical P2 family
                # with a colliding shortened id cannot attest the full P4
                # fingerprint; neither terminal success nor not-applied may
                # be inferred from it. Preserve ambiguity without mutation.
                return {**result, "ok": False, "effect": "EFFECT_UNKNOWN",
                        "error": {"code": "RELEASE_HISTORY_FAMILY_UNQUALIFIED"}}
            return {**result, "approval": approval.to_dict(), "broker_status": projection}
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
                                   {"prepared_token": response.result["prepared_token"]})
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
