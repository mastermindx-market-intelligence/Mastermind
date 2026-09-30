"""Private root-broker approval and preparation, without an actuator.

The existing installed owner supplies a fresh verified snapshot through host
composition. No public frame supplies paths, a key, a policy, a grant, arming,
or staged bytes. The production broker has no such composition by default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable, Mapping
import hashlib
import time

from control_plane import executive_release_contract as contract
from control_plane import executive_release_ingress as ingress
from control_plane.executive_release_actuator import (
    ExecutiveReleaseActuatorJournalError,
    _ExecutiveReleaseActuatorJournal,
)
from control_plane.executive_authority import (
    ReleaseControllerPolicy, authorize_release_transition, release_principal_projection,
)
from control_plane.executive_release_token import _OwnerReleaseCodec
from control_plane.executive_release_consumer import (
    BROKER_SCHEMA, ReleaseConsumerError, _qualify_connection, _current_principal,
)
from control_plane.ceo_request import app_request_ref


def _hash(value):
    return hashlib.sha256(contract.canonical_release_bytes(value)).hexdigest()


@dataclass(frozen=True)
class ReleaseOwnerSnapshot:
    """Owner-verified live inputs, never a request or authority by its type.

    The installed factory must pin root-owned descriptors and rehash policy,
    key, staged bytes and preconditions on every invocation. C1 deliberately
    has no default factory or caller-configurable staging/path resolver.
    """
    policy: ReleaseControllerPolicy
    codec: _OwnerReleaseCodec
    owner_installation_id: str
    target_ref: str
    boot_id: str
    key_id: str
    trust_generation: int
    app_generation: int
    schema_digest: str
    admission_contract_digest: str
    effect: contract.ReleaseRecord
    preconditions: Mapping
    input_identity_digest: str = ""
    actuator_generation: int = 0
    target_observation_digest: str = ""
    before: Mapping = field(default_factory=dict)


@dataclass(frozen=True)
class ReleaseHistoryTrust:
    """Fresh owner trust for history; independent of staging and expiry."""
    codec: _OwnerReleaseCodec
    owner_installation_id: str
    target_ref: str
    input_identity_digest: str = ""


_APPROVAL_PRECONDITIONS = frozenset({"approval_evidence_digest", "grant_digest"})
_PRIVATE_OPERATIONS = frozenset({
    "reserve_release_prestart", "start_reserved_release"
})
_RESERVE_KEYS = frozenset({"schema", "operation", "arguments", "principal", "approval"})
_START_KEYS = _RESERVE_KEYS | {"reservation", "admission"}
_EVIDENCE_KEYS = frozenset({"approval", "admission", "preconditions", "root_qualification_digest"})
_BEFORE_KEYS = frozenset({
    "release_commit", "release_tree", "installed_manifest_digest",
    "configuration_digest", "broker_source_commit", "broker_source_tree",
    "broker_binary_digest", "service_generation_digests",
})
_SERVICE_ROLES = frozenset({"control", "worker", "relay", "gateway", "broker"})


def _state_identity(state):
    if (type(state) is not ReleaseOwnerSnapshot
            or type(state.codec) is not _OwnerReleaseCodec
            or type(state.policy) is not ReleaseControllerPolicy
            or not isinstance(state.preconditions, Mapping)
            or _APPROVAL_PRECONDITIONS.intersection(state.preconditions)):
        raise ReleaseConsumerError("RELEASE_INSTALLED_OWNER_UNAVAILABLE")
    fields = {name: getattr(state, name) for name in state.__dataclass_fields__
              if name not in {"codec", "policy"}}
    fields["authority_policy_hash"] = state.policy.sha256
    return contract.canonical_release_bytes(fields)


class ReleaseBrokerOwner:
    """Installed private composition for two closed, non-install operations."""
    def __init__(self, snapshot: Callable[[str], ReleaseOwnerSnapshot], *,
                 history_trust: Callable[[], ReleaseHistoryTrust] | None = None,
                 root_journal: _ExecutiveReleaseActuatorJournal | None = None,
                 admission_reader: object | None = None):
        if not callable(snapshot):
            raise TypeError("installed snapshot factory required")
        self._snapshot = snapshot
        if history_trust is not None and not callable(history_trust):
            raise TypeError("installed history trust factory required")
        self._history_trust = history_trust
        if root_journal is not None and type(root_journal) is not _ExecutiveReleaseActuatorJournal:
            raise TypeError("installed root journal required")
        self._root_journal = root_journal
        if admission_reader is not None and not callable(getattr(
                admission_reader, "read_admission_evidence", None)):
            raise TypeError("installed admission reader required")
        self._admission_reader = admission_reader

    def _fresh(self, state, transition):
        observed = _state_identity(state)
        fresh = self._snapshot(transition)
        if _state_identity(fresh) != observed:
            raise ReleaseConsumerError("RELEASE_PRECONDITIONS_CHANGED")
        return fresh

    def _history(self, approval, principal, connection):
        if self._history_trust is None:
            raise ReleaseConsumerError("RELEASE_HISTORY_TRUST_UNAVAILABLE")
        original_identity = None
        for _ in range(2):
            trust = self._history_trust()
            if type(trust) is not ReleaseHistoryTrust or type(trust.codec) is not _OwnerReleaseCodec:
                raise ReleaseConsumerError("RELEASE_HISTORY_TRUST_UNAVAILABLE")
            identity = (trust.owner_installation_id, trust.target_ref, trust.input_identity_digest)
            if original_identity is not None and identity != original_identity:
                raise ReleaseConsumerError("RELEASE_HISTORY_TRUST_UNAVAILABLE")
            original_identity = identity
            verified = trust.codec.verify_approval(approval)
            if (verified["principal_projection"] != principal
                    or verified["owner_installation_id"] != trust.owner_installation_id
                    or verified["target_ref"] != trust.target_ref):
                raise ReleaseConsumerError("RELEASE_APPROVAL_IDENTITY_MISMATCH")
            _qualify_connection(connection, "control")
        return verified

    def _private_frame(self, raw, connection):
        if (type(raw) is not dict or raw.get("schema") != BROKER_SCHEMA
                or raw.get("operation") not in _PRIVATE_OPERATIONS
                or set(raw) != (_RESERVE_KEYS if raw.get("operation") == "reserve_release_prestart" else _START_KEYS)
                or not isinstance(raw.get("principal"), Mapping)):
            raise ReleaseConsumerError("RELEASE_BROKER_FRAME_INVALID")
        arguments = raw.get("arguments")
        if (not isinstance(arguments, Mapping)
                or set(arguments) != {"operation_key", "prepared_token"}):
            raise ReleaseConsumerError("RELEASE_BROKER_FRAME_INVALID")
        frame = ingress.validate_frame({
            "schema": ingress.FRAME_SCHEMA,
            "operation": "commit_prepared_release_transition",
            "arguments": dict(arguments),
            "principal": dict(raw["principal"]),
        })
        if (frame.arguments["operation_key"] != raw["arguments"]["operation_key"]
                or frame.arguments["prepared_token"] != raw["arguments"]["prepared_token"]):
            raise ReleaseConsumerError("RELEASE_BROKER_FRAME_INVALID")
        _qualify_connection(connection, "control")
        return frame

    def _live_state(self, frame, approval):
        transition = approval["transition_digest"]
        state = self._snapshot(transition)
        _state_identity(state)
        effect = contract.validate_normalized_effect(state.effect)
        if _hash(effect) != transition:
            raise ReleaseConsumerError("RELEASE_STAGED_TRANSITION_CHANGED")
        now = time.time_ns() // 1_000_000
        principal = _current_principal(frame.principal, now)
        current_grant = authorize_release_transition(
            frame.principal, effect, state.policy, target_ref=state.target_ref, now_ms=now)
        state = self._fresh(state, transition)
        now = time.time_ns() // 1_000_000
        principal = _current_principal(frame.principal, now)
        current_grant = authorize_release_transition(
            frame.principal, effect, state.policy, target_ref=state.target_ref, now_ms=now)
        sealed = state.codec.verify_approval(approval)
        if (sealed["operation_key"] != frame.arguments["operation_key"]
                or sealed["principal_projection"] != principal
                or sealed["owner_installation_id"] != state.owner_installation_id
                or sealed["target_ref"] != state.target_ref
                or sealed["normalized_requested_effect"] != effect
                or sealed["grant"]["authority_policy_hash"] != current_grant["authority_policy_hash"]
                or sealed["grant"]["policy_generation"] != current_grant["policy_generation"]
                or not sealed["created_at_ms"] <= now < sealed["expires_at_ms"]):
            raise ReleaseConsumerError("RELEASE_APPROVAL_NOT_CURRENT")
        return state, effect, sealed

    def _private_inputs(self, frame, raw):
        if self._root_journal is None:
            raise ReleaseConsumerError("RELEASE_ROOT_JOURNAL_UNAVAILABLE")
        try:
            approval = contract.validate_approval_evidence(raw["approval"])
        except (TypeError, ValueError, contract.ReleaseContractError):
            raise ReleaseConsumerError("RELEASE_APPROVAL_EVIDENCE_INVALID") from None
        if approval["operation_key"] != frame.arguments["operation_key"]:
            raise ReleaseConsumerError("RELEASE_APPROVAL_IDENTITY_MISMATCH")
        state, effect, sealed = self._live_state(frame, approval)
        now = time.time_ns() // 1_000_000
        monotonic = time.monotonic_ns()
        try:
            payload = state.codec.decode_prepared(
                frame.arguments["prepared_token"], now_ms=now,
                monotonic_ns=monotonic, boot_id=state.boot_id)
        except ValueError:
            raise ReleaseConsumerError("RELEASE_TOKEN_INVALID") from None
        expected = {
            "owner_installation_id": state.owner_installation_id,
            "app_generation": state.app_generation,
            "schema_digest": state.schema_digest,
            "trust_generation": state.trust_generation,
            "key_id": state.key_id,
            "authenticated_principal_digest": _hash(sealed["principal_projection"]),
            "approved_transition_ref": sealed["approved_transition_ref"],
            "approval_evidence_digest": _hash(sealed),
            "policy_id": sealed["grant"]["policy_id"],
            "policy_generation": sealed["grant"]["policy_generation"],
            "authority_policy_hash": sealed["grant"]["authority_policy_hash"],
            "effective_grant_digest": sealed["effective_grant_digest"],
            "action_target_digest": _hash({"action": effect["action"], "target_ref": state.target_ref}),
            "confirmation_requirement": sealed["grant"]["confirmation_requirement"],
            "operation_key": sealed["operation_key"],
            "action_family": effect["action"],
            "request_fingerprint": contract.request_fingerprint_for(sealed),
            "target_ref": state.target_ref,
            "boot_id": state.boot_id,
            "platform": "darwin",
            "normalized_requested_effect": effect,
            "normalized_requested_effect_digest": _hash(effect),
        }
        if any(payload[key] != value for key, value in expected.items()):
            raise ReleaseConsumerError("RELEASE_PREPARED_IDENTITY_MISMATCH")
        preconditions = self._preconditions(state, sealed)
        if (payload["expected_source_and_precondition_digest"] != _hash(preconditions)
                or payload["admission_contract_digest"] != state.admission_contract_digest):
            raise ReleaseConsumerError("RELEASE_PRECONDITIONS_CHANGED")
        if (type(state.actuator_generation) is not int or state.actuator_generation < 1
                or type(state.target_observation_digest) is not str
                or len(state.target_observation_digest) != 64
                or any(char not in "0123456789abcdef" for char in state.target_observation_digest)
                or not isinstance(state.before, Mapping)
                or set(state.before) != _BEFORE_KEYS
                or not isinstance(state.before["service_generation_digests"], Mapping)
                or set(state.before["service_generation_digests"]) != _SERVICE_ROLES):
            raise ReleaseConsumerError("RELEASE_ROOT_OWNER_UNAVAILABLE")
        return state, effect, sealed, payload, preconditions

    def _preconditions(self, state, sealed):
        try:
            preconditions = contract.validate_precondition_manifest({
                **state.preconditions,
                "approval_evidence_digest": _hash(sealed),
                "grant_digest": sealed["effective_grant_digest"],
            })
        except (TypeError, ValueError, contract.ReleaseContractError):
            raise ReleaseConsumerError("RELEASE_PRECONDITIONS_INVALID") from None
        effect = sealed["normalized_requested_effect"]
        required = {
            "owner_installation_id": state.owner_installation_id,
            "target_ref": state.target_ref,
            "boot_id": state.boot_id,
            "approval_evidence_digest": _hash(sealed),
            "authority_policy_hash": state.policy.sha256,
            "grant_digest": sealed["effective_grant_digest"],
            "from_installed_manifest_digest": effect["from_installed_manifest_digest"],
            "staged_artifact_digest": effect["staged_artifact_digest"],
            "staged_content_metadata_digest": effect["staged_content_metadata_digest"],
            "compatibility_proof_digest": effect["compatibility_proof_digest"],
            "preservation_plan_digest": effect["preservation_plan_digest"],
            "admission_contract_digest": state.admission_contract_digest,
        }
        if any(preconditions[key] != value for key, value in required.items()):
            raise ReleaseConsumerError("RELEASE_PRECONDITIONS_CHANGED")
        return preconditions

    @staticmethod
    def _validated(value):
        return value.to_dict() if hasattr(value, "to_dict") else dict(value)

    def _reservation(self, state, effect, sealed, payload, preconditions, *, token, now, monotonic):
        try:
            reservation = contract.validate_release_prestart_reservation({
                "schema": "mastermind.executive_release_prestart_reservation/v1",
                "request_id": contract.broker_request_id_for(payload["request_fingerprint"]),
                "request_fingerprint": payload["request_fingerprint"],
                "operation_key": sealed["operation_key"],
                "approved_transition_ref": sealed["approved_transition_ref"],
                "approval_evidence_digest": _hash(sealed),
                "authenticated_principal_digest": payload["authenticated_principal_digest"],
                "effective_grant_digest": sealed["effective_grant_digest"],
                "normalized_requested_effect_digest": _hash(effect),
                "action_family": effect["action"],
                "action_target_digest": payload["action_target_digest"],
                "owner_installation_id": state.owner_installation_id,
                "target_ref": state.target_ref,
                "from_release_commit": effect["from_release_commit"],
                "to_release_commit": effect["to_release_commit"],
                "reservation_generation": 1,
                "reserved_at_ms": now,
                "reserved_monotonic_ns": monotonic,
                "preconditions": preconditions.to_dict(),
                "expected_precondition_digest": _hash(preconditions),
                "prepared_payload": payload.to_dict(),
                "prepared_token_digest": hashlib.sha256(token.encode("ascii")).hexdigest(),
                # The installed owner supplies the observed physical before-state.
                # Service generation identities are independent facts; deriving
                # them from unrelated precondition digests would fabricate the
                # rollback/recovery preimage.
                "before": dict(state.before),
                "target_observation_digest": state.target_observation_digest,
            }, expected_approval=sealed)
        except contract.ReleaseContractError as exc:
            raise ReleaseConsumerError(
                f"RELEASE_RESERVATION_INVALID_{exc.field}_{exc.code}") from None
        except (TypeError, ValueError):
            raise ReleaseConsumerError("RELEASE_RESERVATION_INVALID") from None
        return reservation

    def _reserve_release_prestart(self, raw, connection):
        frame = self._private_frame(raw, connection)
        state, effect, sealed, payload, preconditions = self._private_inputs(frame, raw)
        now = time.time_ns() // 1_000_000
        monotonic = time.monotonic_ns()
        if not payload["issued_at_ms"] <= now < payload["expires_at_ms"]:
            raise ReleaseConsumerError("RELEASE_PREPARED_EXPIRED")
        if not payload["issued_monotonic_ns"] <= monotonic < payload["expires_monotonic_ns"]:
            raise ReleaseConsumerError("RELEASE_PREPARED_EXPIRED")
        reservation = self._reservation(
            state, effect, sealed, payload, preconditions,
            token=frame.arguments["prepared_token"], now=now, monotonic=monotonic)
        try:
            stored = self._root_journal.reserve_prestart(
                reservation=reservation, approval=sealed)
        except ExecutiveReleaseActuatorJournalError as exc:
            raise ReleaseConsumerError(
                "RELEASE_ROOT_JOURNAL_" + exc.code) from None
        return {"schema": BROKER_SCHEMA, "operation": frame.operation, "ok": True,
                "approval": sealed.to_dict(), "result": {"reservation": stored.to_dict()}}

    def _start_reserved_release(self, raw, connection):
        frame = self._private_frame(raw, connection)
        state, effect, sealed, payload, current = self._private_inputs(frame, raw)
        if self._admission_reader is None:
            raise ReleaseConsumerError("RELEASE_ROOT_START_UNAVAILABLE")
        now = time.time_ns() // 1_000_000
        if not payload["issued_at_ms"] <= now < payload["expires_at_ms"]:
            raise ReleaseConsumerError("RELEASE_PREPARED_EXPIRED")
        if not payload["issued_monotonic_ns"] <= time.monotonic_ns() < payload["expires_monotonic_ns"]:
            raise ReleaseConsumerError("RELEASE_PREPARED_EXPIRED")
        try:
            supplied_reservation = contract.validate_release_prestart_reservation(
                raw["reservation"], expected_approval=sealed)
            supplied_admission = contract.validate_admission(raw["admission"])
        except (TypeError, ValueError, contract.ReleaseContractError):
            raise ReleaseConsumerError("RELEASE_ROOT_START_EVIDENCE_INVALID") from None
        try:
            self._root_journal._validate_admission_joins(
                supplied_admission, supplied_reservation,
                frame.arguments["operation_key"])
        except ExecutiveReleaseActuatorJournalError as exc:
            raise ReleaseConsumerError(
                "RELEASE_ROOT_JOURNAL_" + exc.code) from None
        expected_reservation = self._reservation(
            state, effect, sealed, payload, current,
            token=frame.arguments["prepared_token"], now=supplied_reservation["reserved_at_ms"],
            monotonic=supplied_reservation["reserved_monotonic_ns"])
        if (contract.canonical_release_bytes(supplied_reservation)
                != contract.canonical_release_bytes(expected_reservation)
                or supplied_admission["target_observation_digest"] != state.target_observation_digest):
            raise ReleaseConsumerError("RELEASE_RESERVATION_MISMATCH")
        try:
            reservation = self._root_journal.read_prestart_reservation(
                frame.arguments["operation_key"], approval=sealed)
        except ExecutiveReleaseActuatorJournalError as exc:
            raise ReleaseConsumerError(
                "RELEASE_ROOT_JOURNAL_" + exc.code) from None
        if contract.canonical_release_bytes(reservation) != contract.canonical_release_bytes(supplied_reservation):
            raise ReleaseConsumerError("RELEASE_RESERVATION_MISMATCH")
        try:
            evidence = self._admission_reader.read_admission_evidence(
                approved_transition_ref=reservation["approved_transition_ref"],
                request_fingerprint=reservation["request_fingerprint"])
        except Exception:
            raise ReleaseConsumerError("RELEASE_ADMISSION_EVIDENCE_UNAVAILABLE") from None
        if not isinstance(evidence, Mapping) or set(evidence) != _EVIDENCE_KEYS:
            raise ReleaseConsumerError("RELEASE_ADMISSION_EVIDENCE_INVALID")
        try:
            evidence_approval = contract.validate_approval_evidence(evidence["approval"])
            evidence_admission = contract.validate_admission(evidence["admission"])
            evidence_preconditions = contract.validate_precondition_manifest(evidence["preconditions"])
        except (TypeError, ValueError, contract.ReleaseContractError):
            raise ReleaseConsumerError("RELEASE_ADMISSION_EVIDENCE_INVALID") from None
        if (type(evidence["root_qualification_digest"]) is not str
                or len(evidence["root_qualification_digest"]) != 64):
            raise ReleaseConsumerError("RELEASE_ADMISSION_EVIDENCE_INVALID")
        reservation_digest = hashlib.sha256(
            contract.canonical_release_bytes(reservation)).hexdigest()
        if (evidence["root_qualification_digest"] != reservation_digest
                or contract.canonical_release_bytes(evidence_approval) != contract.canonical_release_bytes(sealed)
                or contract.canonical_release_bytes(evidence_admission) != contract.canonical_release_bytes(supplied_admission)
                or contract.canonical_release_bytes(evidence_preconditions) != contract.canonical_release_bytes(reservation["preconditions"])):
            raise ReleaseConsumerError("RELEASE_ADMISSION_EVIDENCE_MISMATCH")
        before = reservation["before"]
        identity = {
            "operation_key": reservation["operation_key"],
            "request_fingerprint": reservation["request_fingerprint"],
            "approval_evidence_digest": reservation["approval_evidence_digest"],
            "normalized_requested_effect_digest": reservation["normalized_requested_effect_digest"],
            "expected_source_and_precondition_digest": reservation["expected_precondition_digest"],
            "action_target_digest": reservation["action_target_digest"],
            "owner_installation_id": reservation["owner_installation_id"],
            "target_ref": reservation["target_ref"],
            "before_release_commit": before["release_commit"],
            "before_release_tree": before["release_tree"],
            "before_installed_manifest_digest": before["installed_manifest_digest"],
            "before_configuration_digest": before["configuration_digest"],
            "target_release_commit": reservation["to_release_commit"],
            "target_release_tree": effect["to_release_tree"],
            "boot_id": reservation["preconditions"]["boot_id"],
        }
        try:
            start_record = self._root_journal.create(
                actuator_generation=state.actuator_generation,
                identity=identity,
                preconditions=reservation["preconditions"],
                admission=evidence_admission,
                approval=evidence_approval,
                reservation=reservation,
                root_qualification_digest=reservation_digest,
                started_at_ms=now,
            )
        except ExecutiveReleaseActuatorJournalError as exc:
            raise ReleaseConsumerError(
                "RELEASE_ROOT_JOURNAL_" + exc.code) from None
        return {"schema": BROKER_SCHEMA, "operation": frame.operation, "ok": True,
                "approval": sealed.to_dict(),
                "result": {"reservation": reservation.to_dict(),
                           "admission": evidence_admission.to_dict(),
                           "start_record": start_record.to_dict()}}

    def handle(self, raw, connection):
        if type(raw) is dict and raw.get("operation") in _PRIVATE_OPERATIONS:
            if raw.get("operation") == "reserve_release_prestart":
                return self._reserve_release_prestart(raw, connection)
            return self._start_reserved_release(raw, connection)
        if type(raw) is not dict or set(raw) != {"schema", "operation", "arguments", "principal", "approval"} or raw["schema"] != BROKER_SCHEMA:
            raise ReleaseConsumerError("RELEASE_BROKER_FRAME_INVALID")
        frame = ingress.validate_frame({key: value for key, value in
            {**raw, "schema": ingress.FRAME_SCHEMA}.items() if key != "approval"})
        _qualify_connection(connection, "control")
        if frame.operation == "commit_prepared_release_transition":
            raise ReleaseConsumerError("RELEASE_COMMIT_DISARMED")
        if frame.operation not in {"approve_release_transition", "prepare_release_transition", "reconcile_release_transition"}:
            raise ReleaseConsumerError("RELEASE_BROKER_OPERATION_INVALID")
        now = time.time_ns() // 1_000_000
        principal = _current_principal(frame.principal, now)
        old = None if raw["approval"] is None else contract.validate_approval_evidence(raw["approval"])
        if old is not None and old["operation_key"] != frame.arguments["operation_key"]:
            raise ReleaseConsumerError("RELEASE_APPROVAL_IDENTITY_MISMATCH")
        if frame.operation == "reconcile_release_transition":
            if old is None:
                raise ReleaseConsumerError("RELEASE_APPROVAL_NOT_FOUND")
            verified = self._history(old, principal, connection)
            _current_principal(frame.principal, time.time_ns() // 1_000_000)
            return {"schema": BROKER_SCHEMA, "operation": frame.operation, "ok": True,
                    "approval": verified.to_dict(), "result": {}}
        if frame.operation == "prepare_release_transition" and old is None:
            raise ReleaseConsumerError("RELEASE_APPROVAL_NOT_FOUND")
        transition = frame.arguments.get("transition_digest") if old is None else old["transition_digest"]
        state = self._snapshot(transition)
        _state_identity(state)
        effect = contract.validate_normalized_effect(state.effect)
        if _hash(effect) != transition:
            raise ReleaseConsumerError("RELEASE_STAGED_TRANSITION_CHANGED")
        if frame.operation == "approve_release_transition" and (
                frame.arguments["action"] != effect["action"]
                or frame.arguments["transition_digest"] != transition):
            raise ReleaseConsumerError("RELEASE_APPROVAL_IDENTITY_MISMATCH")
        # Independently authorize on the root side from the installed policy.
        # Required confirmation has no live issuer in C1 and refuses normally;
        # delegated authority still needs the exact installed clauses.
        current_grant = authorize_release_transition(frame.principal, effect,
            state.policy, target_ref=state.target_ref, now_ms=now)
        state = self._fresh(state, transition)
        now = time.time_ns() // 1_000_000
        _qualify_connection(connection, "control")
        principal = _current_principal(frame.principal, now)
        current_grant = authorize_release_transition(frame.principal, effect,
            state.policy, target_ref=state.target_ref, now_ms=now)
        if old is None:
            op = frame.arguments["operation_key"]
            approval = {
                "schema": "mastermind.executive_release_approval/v1",
                "operation_key": op, "request_ref": app_request_ref(op),
                "approved_transition_ref": contract.approval_ref_for(op),
                "action": effect["action"], "owner_installation_id": state.owner_installation_id,
                "target_ref": state.target_ref, "principal_projection": principal.to_dict(),
                "normalized_requested_effect": effect.to_dict(), "transition_digest": transition,
                "grant": current_grant.to_dict(), "effective_grant_digest": _hash(current_grant),
                "created_at_ms": now, "expires_at_ms": current_grant["expires_at_ms"],
                "owner_seal": {"key_id": state.key_id, "trust_generation": state.trust_generation,
                               "mac": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"},
            }
            _qualify_connection(connection, "control")
            sealed = state.codec.seal_approval(approval)
        else:
            sealed = state.codec.verify_approval(old)
            if (sealed["operation_key"] != frame.arguments["operation_key"]
                    or sealed["principal_projection"] != principal
                    or sealed["owner_installation_id"] != state.owner_installation_id
                    or sealed["target_ref"] != state.target_ref
                    or sealed["normalized_requested_effect"] != effect
                    or sealed["grant"]["authority_policy_hash"] != current_grant["authority_policy_hash"]
                    or sealed["grant"]["policy_generation"] != current_grant["policy_generation"]
                    or not sealed["created_at_ms"] <= now < sealed["expires_at_ms"]):
                raise ReleaseConsumerError("RELEASE_APPROVAL_NOT_CURRENT")
        result = {}
        if frame.operation == "prepare_release_transition":
            state = self._fresh(state, transition)
            sealed = state.codec.verify_approval(sealed)
            preconditions = contract.validate_precondition_manifest({
                **state.preconditions, "approval_evidence_digest": _hash(sealed),
                "grant_digest": sealed["effective_grant_digest"],
            })
            required = {
                "owner_installation_id": state.owner_installation_id, "target_ref": state.target_ref,
                "boot_id": state.boot_id, "approval_evidence_digest": _hash(sealed),
                "authority_policy_hash": state.policy.sha256,
                "grant_digest": sealed["effective_grant_digest"],
                "from_installed_manifest_digest": effect["from_installed_manifest_digest"],
                "staged_artifact_digest": effect["staged_artifact_digest"],
                "staged_content_metadata_digest": effect["staged_content_metadata_digest"],
                "compatibility_proof_digest": effect["compatibility_proof_digest"],
                "preservation_plan_digest": effect["preservation_plan_digest"],
                "admission_contract_digest": state.admission_contract_digest,
            }
            if any(preconditions[key] != value for key, value in required.items()):
                raise ReleaseConsumerError("RELEASE_PRECONDITIONS_CHANGED")
            issued = time.time_ns() // 1_000_000
            monotonic = time.monotonic_ns()
            expires = min(issued + 300_000, sealed["expires_at_ms"], current_grant["expires_at_ms"], frame.principal.expires_at * 1000)
            if not now <= issued < expires:
                raise ReleaseConsumerError("RELEASE_APPROVAL_EXPIRED")
            grant = sealed["grant"]
            prepared = {
                "token_schema": "mastermind.executive_release_prepared.v1", "app_id": "mastermind.executive",
                "owner_installation_id": state.owner_installation_id, "app_generation": state.app_generation,
                "schema_digest": state.schema_digest, "trust_generation": state.trust_generation, "key_id": state.key_id,
                "authenticated_principal_digest": _hash(principal), "approved_transition_ref": sealed["approved_transition_ref"],
                "approval_evidence_digest": _hash(sealed), "policy_id": grant["policy_id"],
                "policy_generation": grant["policy_generation"], "authority_policy_hash": grant["authority_policy_hash"],
                "effective_grant_digest": sealed["effective_grant_digest"],
                "action_target_digest": _hash({"action": effect["action"], "target_ref": state.target_ref}),
                "confirmation_requirement": grant["confirmation_requirement"], "privilege_class": "EXECUTIVE_RELEASE_TRANSITION",
                "operation_key": sealed["operation_key"], "action_family": effect["action"],
                "request_fingerprint": contract.request_fingerprint_for(sealed), "target_ref": state.target_ref,
                "boot_id": state.boot_id, "platform": "darwin", "normalized_requested_effect": effect.to_dict(),
                "normalized_requested_effect_digest": _hash(effect),
                "expected_source_and_precondition_digest": _hash(preconditions),
                "admission_contract_digest": state.admission_contract_digest,
                "issued_at_ms": issued, "expires_at_ms": expires,
                "issued_monotonic_ns": monotonic, "expires_monotonic_ns": monotonic + (expires-issued)*1_000_000,
            }
            _qualify_connection(connection, "control")
            _current_principal(frame.principal, time.time_ns() // 1_000_000)
            result = {"prepared_token": state.codec.encode_prepared(prepared), "expires_at_ms": expires,
                      "preview": {"action": effect["action"], "target_ref": state.target_ref,
                                  "from_release": effect["from_release_commit"], "to_release": effect["to_release_commit"]}}
        return {"schema": BROKER_SCHEMA, "operation": frame.operation, "ok": True,
                "approval": sealed.to_dict(), "result": result}
