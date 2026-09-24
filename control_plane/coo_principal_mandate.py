"""Pure COO principal mandate projection over already-qualified owner facts.

This module owns no authority, lifecycle, identity, queue, session registry, OAuth
verification, source lease, provider placement, retry or persistence state. It
reduces immutable facts supplied by their existing canonical owners into the
read-only mastermind.coo_principal_mandate.v1 projection used by rich principal
clients such as Fable.

The projection separates organizational decision posture from technical
capability exposure. Exact tool, MCP, plugin and source capability still belongs
to the existing target owners at action time.
"""
from __future__ import annotations

import dataclasses
import enum
import re
from typing import Any


SCHEMA = "mastermind.coo_principal_mandate.v1"

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,255}$")
_WORK_REF_RE = re.compile(r"^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$")
_SCOPE_RE = re.compile(r"^[a-z][a-z0-9._:-]{2,95}$")

RESERVED_BOUNDARIES = (
    "OUTCOME_CHANGE",
    "COMPANY_STRATEGY_CHANGE",
    "SELF_AUTHORITY_EXPANSION",
    "HUMAN_OR_ADMIN_CREDENTIAL_CEREMONY",
    "RESERVED_CAPITAL_OR_DESTRUCTIVE_EFFECT",
    "UNDELEGATED_EXTERNAL_PUBLIC_EFFECT",
    "BUDGET_OR_RISK_EXPANSION",
    "EFFECT_UNKNOWN",
    "LIVE_SOURCE_OR_LEASE_CONFLICT",
    "EXPLICIT_RESERVED_RELEASE",
    "MISSING_REQUIRED_PROOF_WITH_NO_IN_SCOPE_RECOVERY",
)


class Seat(str, enum.Enum):
    CHAIRMAN = "chairman"
    CEO = "ceo"
    COO = "coo"
    WORKER = "worker"
    NONE = "none"


class EffectState(str, enum.Enum):
    NONE = "none"
    APPLIED = "applied"
    EFFECT_UNKNOWN = "effect_unknown"


class ReleaseClass(str, enum.Enum):
    AUTONOMOUS_SOURCE_RELEASE_WITH_GATES = "AUTONOMOUS_SOURCE_RELEASE_WITH_GATES"
    RESERVED_RELEASE = "RESERVED_RELEASE"


class DecisionPosture(str, enum.Enum):
    DECIDE_CONTINUE = "DECIDE_CONTINUE"
    DO_NOT_MICROMANAGE_WORKER = "DO_NOT_MICROMANAGE_WORKER"
    RECOMMEND_ONLY_FOR_OWED_TURN = "RECOMMEND_ONLY_FOR_OWED_TURN"
    CONTINUE_PATH_DISJOINT = "CONTINUE_PATH_DISJOINT"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"


class NewEffectGate(str, enum.Enum):
    OPEN = "OPEN"
    FENCED_EFFECT_UNKNOWN = "FENCED_EFFECT_UNKNOWN"
    FENCED_SOURCE_OR_LEASE_CONFLICT = "FENCED_SOURCE_OR_LEASE_CONFLICT"


class SessionAssurance(str, enum.Enum):
    MISSION_BOUND = "COO_PRINCIPAL_MISSION_BOUND"
    PROVIDER_SESSION_BOUND = "COO_PRINCIPAL_PROVIDER_SESSION_BOUND"
    CRYPTOGRAPHIC_SESSION_BOUND = "COO_PRINCIPAL_CRYPTOGRAPHIC_SESSION_BOUND"


def _text(value: object, *, field: str, pattern: re.Pattern[str] = _REF_RE) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{field} is invalid")
    return value


def _digest(value: object, *, field: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _optional_ref(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field=field)


def _scope_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not tuple or not value or len(value) > 16:
        raise ValueError("scopes must be a non-empty tuple with at most 16 entries")
    result: list[str] = []
    for scope in value:
        if type(scope) is not str or _SCOPE_RE.fullmatch(scope) is None:
            raise ValueError("scopes contain an invalid scope")
        if scope in result:
            raise ValueError("scopes contain a duplicate")
        result.append(scope)
    if tuple(sorted(result)) != tuple(result):
        raise ValueError("scopes must be sorted")
    return tuple(result)


@dataclasses.dataclass(frozen=True, slots=True)
class PrincipalFact:
    policy_id: str
    issuer_digest: str
    subject_digest: str
    client_ref: str
    resource_ref: str
    scopes: tuple[str, ...]
    principal_binding_digest: str

    def __post_init__(self) -> None:
        _text(self.policy_id, field="policy_id")
        _digest(self.issuer_digest, field="issuer_digest")
        _digest(self.subject_digest, field="subject_digest")
        _digest(self.client_ref, field="client_ref")
        _text(self.resource_ref, field="resource_ref")
        object.__setattr__(self, "scopes", _scope_tuple(self.scopes))
        _digest(self.principal_binding_digest, field="principal_binding_digest")


@dataclasses.dataclass(frozen=True, slots=True)
class MissionAuthorityFact:
    work_ref: str
    mission_authority_ref: str
    authority_generation_digest: str
    accountable_seat: Seat
    owed_seat: Seat
    release_class: ReleaseClass
    outcome_ref: str
    proof_contract_ref: str
    capability_profile_ref: str
    source_grant_ref: str | None
    economic_envelope_ref: str | None

    def __post_init__(self) -> None:
        _text(self.work_ref, field="work_ref", pattern=_WORK_REF_RE)
        _text(self.mission_authority_ref, field="mission_authority_ref")
        _digest(self.authority_generation_digest, field="authority_generation_digest")
        if not isinstance(self.accountable_seat, Seat):
            raise TypeError("accountable_seat must be Seat")
        if not isinstance(self.owed_seat, Seat):
            raise TypeError("owed_seat must be Seat")
        if not isinstance(self.release_class, ReleaseClass):
            raise TypeError("release_class must be ReleaseClass")
        _text(self.outcome_ref, field="outcome_ref")
        _text(self.proof_contract_ref, field="proof_contract_ref")
        _text(self.capability_profile_ref, field="capability_profile_ref")
        _optional_ref(self.source_grant_ref, field="source_grant_ref")
        _optional_ref(self.economic_envelope_ref, field="economic_envelope_ref")


@dataclasses.dataclass(frozen=True, slots=True)
class SafetyFact:
    effect_state: EffectState
    live_source_or_lease_conflict: bool
    runtime_binding_ref: str | None = None
    session_assurance: SessionAssurance = SessionAssurance.MISSION_BOUND

    def __post_init__(self) -> None:
        if not isinstance(self.effect_state, EffectState):
            raise TypeError("effect_state must be EffectState")
        if type(self.live_source_or_lease_conflict) is not bool:
            raise TypeError("live_source_or_lease_conflict must be bool")
        _optional_ref(self.runtime_binding_ref, field="runtime_binding_ref")
        if not isinstance(self.session_assurance, SessionAssurance):
            raise TypeError("session_assurance must be SessionAssurance")


def _effect_gate(safety: SafetyFact) -> tuple[NewEffectGate, tuple[str, ...]]:
    if safety.effect_state is EffectState.EFFECT_UNKNOWN:
        return NewEffectGate.FENCED_EFFECT_UNKNOWN, ("effect_unknown",)
    if safety.live_source_or_lease_conflict:
        return (
            NewEffectGate.FENCED_SOURCE_OR_LEASE_CONFLICT,
            ("live_source_or_lease_conflict",),
        )
    return NewEffectGate.OPEN, ()


def _decision_posture(
    mission: MissionAuthorityFact,
    gate: NewEffectGate,
) -> tuple[DecisionPosture, tuple[str, ...]]:
    if mission.accountable_seat is not Seat.COO:
        return DecisionPosture.RECOMMEND_ONLY_FOR_OWED_TURN, (
            "coo_not_accountable_seat",
        )
    if gate is not NewEffectGate.OPEN:
        return DecisionPosture.RECONCILE_REQUIRED, ("new_effects_fenced",)
    if mission.owed_seat is Seat.COO:
        return DecisionPosture.DECIDE_CONTINUE, ()
    if mission.owed_seat is Seat.WORKER:
        return DecisionPosture.DO_NOT_MICROMANAGE_WORKER, ()
    if mission.owed_seat in {Seat.CEO, Seat.CHAIRMAN}:
        return DecisionPosture.CONTINUE_PATH_DISJOINT, (
            f"{mission.owed_seat.value}_turn_reserved",
        )
    return DecisionPosture.DECIDE_CONTINUE, ()


def project_coo_principal_mandate(
    *,
    principal: PrincipalFact,
    mission: MissionAuthorityFact,
    safety: SafetyFact,
) -> dict[str, Any]:
    """Return one deterministic read-only COO mandate projection.

    The caller must supply facts already qualified by their canonical owners.
    This reducer authenticates nothing and grants nothing.
    """

    if not isinstance(principal, PrincipalFact):
        raise TypeError("principal must be PrincipalFact")
    if not isinstance(mission, MissionAuthorityFact):
        raise TypeError("mission must be MissionAuthorityFact")
    if not isinstance(safety, SafetyFact):
        raise TypeError("safety must be SafetyFact")

    gate, gate_reasons = _effect_gate(safety)
    posture, posture_reasons = _decision_posture(mission, gate)
    reason_codes = tuple(sorted(set(gate_reasons + posture_reasons)))

    return {
        "schema": SCHEMA,
        "seat": Seat.COO.value,
        "principal": {
            "policy_id": principal.policy_id,
            "issuer_digest": principal.issuer_digest,
            "subject_digest": principal.subject_digest,
            "client_ref": principal.client_ref,
            "resource_ref": principal.resource_ref,
            "scopes": list(principal.scopes),
            "principal_binding_digest": principal.principal_binding_digest,
        },
        "mission": {
            "work_ref": mission.work_ref,
            "mission_authority_ref": mission.mission_authority_ref,
            "authority_generation_digest": mission.authority_generation_digest,
            "accountable_seat": mission.accountable_seat.value,
            "owed_seat": mission.owed_seat.value,
            "outcome_ref": mission.outcome_ref,
            "proof_contract_ref": mission.proof_contract_ref,
        },
        "capability": {
            "capability_profile_ref": mission.capability_profile_ref,
            "source_grant_ref": mission.source_grant_ref,
            "economic_envelope_ref": mission.economic_envelope_ref,
        },
        "release": {
            "release_class": mission.release_class.value,
        },
        "continuity": {
            "effect_state": safety.effect_state.value,
            "live_source_or_lease_conflict": safety.live_source_or_lease_conflict,
            "runtime_binding_ref": safety.runtime_binding_ref,
            "session_assurance": safety.session_assurance.value,
        },
        "decision_posture": posture.value,
        "new_effect_gate": gate.value,
        "reserved_boundaries": list(RESERVED_BOUNDARIES),
        "reason_codes": list(reason_codes),
    }


__all__ = [
    "SCHEMA",
    "RESERVED_BOUNDARIES",
    "DecisionPosture",
    "EffectState",
    "MissionAuthorityFact",
    "NewEffectGate",
    "PrincipalFact",
    "ReleaseClass",
    "SafetyFact",
    "Seat",
    "SessionAssurance",
    "project_coo_principal_mandate",
]
