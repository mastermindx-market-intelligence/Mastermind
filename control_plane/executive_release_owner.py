"""Private root-broker approval and preparation, without an actuator.

The existing installed owner supplies a fresh verified snapshot through host
composition. No public frame supplies paths, a key, a policy, a grant, arming,
or staged bytes. The production broker has no such composition by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Mapping
import hashlib
import time

from control_plane import executive_release_contract as contract
from control_plane import executive_release_ingress as ingress
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


@dataclass(frozen=True)
class ReleaseHistoryTrust:
    """Fresh owner trust for history; independent of staging and expiry."""
    codec: _OwnerReleaseCodec
    owner_installation_id: str
    target_ref: str


_APPROVAL_PRECONDITIONS = frozenset({"approval_evidence_digest", "grant_digest"})


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
                 history_trust: Callable[[], ReleaseHistoryTrust] | None = None):
        if not callable(snapshot):
            raise TypeError("installed snapshot factory required")
        self._snapshot = snapshot
        if history_trust is not None and not callable(history_trust):
            raise TypeError("installed history trust factory required")
        self._history_trust = history_trust

    def _fresh(self, state, transition):
        observed = _state_identity(state)
        fresh = self._snapshot(transition)
        if _state_identity(fresh) != observed:
            raise ReleaseConsumerError("RELEASE_PRECONDITIONS_CHANGED")
        return fresh

    def _history(self, approval, principal, connection):
        if self._history_trust is None:
            raise ReleaseConsumerError("RELEASE_HISTORY_TRUST_UNAVAILABLE")
        for _ in range(2):
            trust = self._history_trust()
            if type(trust) is not ReleaseHistoryTrust or type(trust.codec) is not _OwnerReleaseCodec:
                raise ReleaseConsumerError("RELEASE_HISTORY_TRUST_UNAVAILABLE")
            verified = trust.codec.verify_approval(approval)
            if (verified["principal_projection"] != principal
                    or verified["owner_installation_id"] != trust.owner_installation_id
                    or verified["target_ref"] != trust.target_ref):
                raise ReleaseConsumerError("RELEASE_APPROVAL_IDENTITY_MISMATCH")
            _qualify_connection(connection, "control")
        return verified

    def handle(self, raw, connection):
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
