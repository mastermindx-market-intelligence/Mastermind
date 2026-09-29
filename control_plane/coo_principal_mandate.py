"""Pure COO principal mandate projection over Mission Workspace v3.

This module is production-inert. It owns no authority, lifecycle, identity,
queue, session registry, OAuth verification, source lease, provider placement,
retry, clock, I/O, or persistence state.

Mission Workspace v3 is the primary organizational input. Additional facts are
already-qualified outputs from the existing OAuth/principal-binding, mission
authority, rich-principal capability, source grant, and economic owners.
"""
from __future__ import annotations

import dataclasses
import enum
import re
from collections.abc import Mapping
from typing import Any

from control_plane import mission_workspace as mw


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


class ReleaseClass(str, enum.Enum):
    AUTONOMOUS_SOURCE_RELEASE_WITH_GATES = "AUTONOMOUS_SOURCE_RELEASE_WITH_GATES"
    RESERVED_RELEASE = "RESERVED_RELEASE"


class DecisionPosture(str, enum.Enum):
    DECIDE_CONTINUE = "DECIDE_CONTINUE"
    DO_NOT_MICROMANAGE_WORKER = "DO_NOT_MICROMANAGE_WORKER"
    CONTINUE_PATH_DISJOINT = "CONTINUE_PATH_DISJOINT"
    READ_RECOMMEND_ONLY = "READ_RECOMMEND_ONLY"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"


class NewEffectGate(str, enum.Enum):
    OPEN = "OPEN"
    FENCED_UNQUALIFIED_MISSION = "FENCED_UNQUALIFIED_MISSION"
    FENCED_EFFECT_UNKNOWN = "FENCED_EFFECT_UNKNOWN"
    FENCED_RECONCILIATION_REQUIRED = "FENCED_RECONCILIATION_REQUIRED"
    FENCED_SOURCE_OR_LEASE_CONFLICT = "FENCED_SOURCE_OR_LEASE_CONFLICT"
    FENCED_NOT_COO_ACCOUNTABLE = "FENCED_NOT_COO_ACCOUNTABLE"


def _text(value: object, *, field: str, pattern: re.Pattern[str] = _REF_RE) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{field} is invalid")
    return value


def _digest(value: object, *, field: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _optional_digest(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _digest(value, field=field)


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
class AuthorityFact:
    work_ref: str
    mission_authority_ref: str
    authority_generation_digest: str
    outcome_ref: str
    proof_contract_ref: str
    release_class: ReleaseClass
    capability_profile_digest: str
    source_grant_digest: str | None
    economic_envelope_digest: str | None
    live_source_or_lease_conflict: bool = False

    def __post_init__(self) -> None:
        _text(self.work_ref, field="work_ref", pattern=_WORK_REF_RE)
        _text(self.mission_authority_ref, field="mission_authority_ref")
        _digest(self.authority_generation_digest, field="authority_generation_digest")
        _text(self.outcome_ref, field="outcome_ref")
        _text(self.proof_contract_ref, field="proof_contract_ref")
        if not isinstance(self.release_class, ReleaseClass):
            raise TypeError("release_class must be ReleaseClass")
        _digest(self.capability_profile_digest, field="capability_profile_digest")
        _optional_digest(self.source_grant_digest, field="source_grant_digest")
        _optional_digest(self.economic_envelope_digest, field="economic_envelope_digest")
        if type(self.live_source_or_lease_conflict) is not bool:
            raise TypeError("live_source_or_lease_conflict must be bool")


def _mapping(value: object, *, field: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"{field} does not match the Mission Workspace v3 contract")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class _MissionState:
    work_ref: str | None
    root_job_id: str | None
    read_state: str | None
    owner_observation_state: str | None
    source_generation_state: str | None
    runtime_root_state: str | None
    root_job_ambiguous: bool | None
    accountable_seat: str | None
    owed_seat: str | None
    owed_reason: str | None
    posture: str | None
    posture_rule: str | None
    dispatch_state: str | None
    qualified: bool
    effect_unknown: bool
    reconciliation_required: bool
    reason_codes: tuple[str, ...]


def _mission_state(document: object, *, expected_work_ref: str) -> _MissionState:
    top = _mapping(document, field="mission_workspace", keys=mw.OUTPUT_KEYS_V3)
    if top.get("schema") != mw.SCHEMA_V3:
        raise ValueError("mission_workspace must use mastermind.mission_workspace.v3")

    read_state = _mapping(
        top.get("read_state"), field="mission_workspace.read_state", keys=mw.READ_STATE_KEYS
    )
    source = _mapping(
        top.get("source"), field="mission_workspace.source", keys=mw.SOURCE_KEYS_V2
    )
    owner_observation = _mapping(
        source.get("owner_observation"),
        field="mission_workspace.source.owner_observation",
        keys=mw.OWNER_OBSERVATION_KEYS,
    )
    program = _mapping(
        top.get("program"), field="mission_workspace.program", keys=mw.PROGRAM_KEYS
    )
    mission = _mapping(
        top.get("mission"), field="mission_workspace.mission", keys=mw.MISSION_KEYS
    )
    principal = _mapping(
        top.get("principal"), field="mission_workspace.principal", keys=mw.PRINCIPAL_KEYS
    )
    transport = _mapping(
        top.get("transport"), field="mission_workspace.transport", keys=mw.TRANSPORT_KEYS
    )
    posture = _mapping(
        top.get("posture"), field="mission_workspace.posture", keys=mw.POSTURE_KEYS
    )

    source_generation = source.get("source_generation")
    if not isinstance(source_generation, Mapping) or set(source_generation) != {
        "state",
        "version",
        "generation",
    }:
        raise ValueError("mission_workspace.source.source_generation is invalid")

    owed = principal.get("owed_turn")
    if owed is not None:
        owed = _mapping(
            owed, field="mission_workspace.principal.owed_turn", keys=mw.OWED_TURN_KEYS
        )

    work_ref = program.get("work_ref") if isinstance(program.get("work_ref"), str) else None
    root_job_id = (
        mission.get("root_job_id") if isinstance(mission.get("root_job_id"), str) else None
    )
    selected_read_state = (
        read_state.get("state") if isinstance(read_state.get("state"), str) else None
    )
    observation_state = (
        owner_observation.get("state")
        if isinstance(owner_observation.get("state"), str)
        else None
    )
    generation_state = (
        source_generation.get("state")
        if isinstance(source_generation.get("state"), str)
        else None
    )
    root_state = (
        mission.get("runtime_root_state")
        if isinstance(mission.get("runtime_root_state"), str)
        else None
    )
    root_ambiguous = (
        mission.get("root_job_ambiguous")
        if type(mission.get("root_job_ambiguous")) is bool
        else None
    )
    accountable = (
        principal.get("accountable_seat")
        if isinstance(principal.get("accountable_seat"), str)
        else None
    )
    owed_seat = owed.get("seat") if isinstance(owed, Mapping) and isinstance(owed.get("seat"), str) else None
    owed_reason = (
        owed.get("reason")
        if isinstance(owed, Mapping) and isinstance(owed.get("reason"), str)
        else None
    )
    posture_value = (
        posture.get("value") if isinstance(posture.get("value"), str) else None
    )
    posture_rule = (
        posture.get("rule") if isinstance(posture.get("rule"), str) else None
    )
    dispatch_state = (
        transport.get("dispatch_state")
        if isinstance(transport.get("dispatch_state"), str)
        else None
    )

    reasons: list[str] = []
    if work_ref != expected_work_ref:
        reasons.append("mission_work_ref_mismatch")
    if selected_read_state != "CURRENT":
        reasons.append("mission_read_state_not_current")
    if observation_state != "SAME":
        reasons.append("owner_observation_not_same")
    if root_state == "CONFLICT" or root_ambiguous is True:
        reasons.append("mission_root_conflict")
    if generation_state != "CURRENT":
        reasons.append("source_generation_not_current")
    if root_job_id is None:
        reasons.append("mission_root_unresolved")

    effect_unknown = (
        posture_value == "EFFECT_UNKNOWN" or dispatch_state == "EFFECT_UNKNOWN"
    )
    reconciliation_required = (
        posture_value == "RECONCILIATION_REQUIRED"
        or dispatch_state == "RUNTIME_BINDING_RECONCILIATION_REQUIRED"
    )

    return _MissionState(
        work_ref=work_ref,
        root_job_id=root_job_id,
        read_state=selected_read_state,
        owner_observation_state=observation_state,
        source_generation_state=generation_state,
        runtime_root_state=root_state,
        root_job_ambiguous=root_ambiguous,
        accountable_seat=accountable,
        owed_seat=owed_seat,
        owed_reason=owed_reason,
        posture=posture_value,
        posture_rule=posture_rule,
        dispatch_state=dispatch_state,
        qualified=not reasons,
        effect_unknown=effect_unknown,
        reconciliation_required=reconciliation_required,
        reason_codes=tuple(sorted(set(reasons))),
    )


def _effect_gate(
    state: _MissionState,
    authority: AuthorityFact,
) -> tuple[NewEffectGate, tuple[str, ...]]:
    if not state.qualified:
        return NewEffectGate.FENCED_UNQUALIFIED_MISSION, state.reason_codes
    if state.effect_unknown:
        return NewEffectGate.FENCED_EFFECT_UNKNOWN, ("effect_unknown",)
    if state.reconciliation_required:
        return (
            NewEffectGate.FENCED_RECONCILIATION_REQUIRED,
            ("reconciliation_required",),
        )
    if authority.live_source_or_lease_conflict:
        return (
            NewEffectGate.FENCED_SOURCE_OR_LEASE_CONFLICT,
            ("live_source_or_lease_conflict",),
        )
    if state.accountable_seat != "coo":
        return NewEffectGate.FENCED_NOT_COO_ACCOUNTABLE, ("coo_not_accountable_seat",)
    return NewEffectGate.OPEN, ()


def _decision_posture(
    state: _MissionState,
    gate: NewEffectGate,
) -> tuple[DecisionPosture, tuple[str, ...]]:
    if gate in {
        NewEffectGate.FENCED_EFFECT_UNKNOWN,
        NewEffectGate.FENCED_RECONCILIATION_REQUIRED,
        NewEffectGate.FENCED_SOURCE_OR_LEASE_CONFLICT,
    }:
        return DecisionPosture.RECONCILE_REQUIRED, ("new_effects_fenced",)
    if gate is not NewEffectGate.OPEN:
        return DecisionPosture.READ_RECOMMEND_ONLY, ("modifying_mandate_unqualified",)
    if state.owed_seat == "coo":
        return DecisionPosture.DECIDE_CONTINUE, ()
    if state.owed_seat == "worker":
        return DecisionPosture.DO_NOT_MICROMANAGE_WORKER, ()
    if state.owed_seat in {"ceo", "chairman"}:
        return DecisionPosture.CONTINUE_PATH_DISJOINT, (
            f"{state.owed_seat}_turn_reserved",
        )
    return DecisionPosture.CONTINUE_PATH_DISJOINT, ("owed_turn_unknown",)


def project_coo_principal_mandate(
    *,
    principal: PrincipalFact,
    authority: AuthorityFact,
    mission_workspace: Mapping[str, Any],
) -> dict[str, Any]:
    """Return one deterministic read-only COO principal mandate projection.

    The App must build principal and authority from their existing canonical
    owners. This reducer authenticates nothing, persists nothing, and grants
    nothing merely because a caller can construct a similarly shaped object.
    """

    if not isinstance(principal, PrincipalFact):
        raise TypeError("principal must be PrincipalFact")
    if not isinstance(authority, AuthorityFact):
        raise TypeError("authority must be AuthorityFact")
    state = _mission_state(mission_workspace, expected_work_ref=authority.work_ref)
    gate, gate_reasons = _effect_gate(state, authority)
    decision, decision_reasons = _decision_posture(state, gate)
    reasons = sorted(set(state.reason_codes + gate_reasons + decision_reasons))

    return {
        "schema": SCHEMA,
        "seat": "coo",
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
            "work_ref": state.work_ref,
            "root_job_id": state.root_job_id,
            "mission_authority_ref": authority.mission_authority_ref,
            "authority_generation_digest": authority.authority_generation_digest,
            "outcome_ref": authority.outcome_ref,
            "proof_contract_ref": authority.proof_contract_ref,
            "read_state": state.read_state,
            "owner_observation_state": state.owner_observation_state,
            "source_generation_state": state.source_generation_state,
            "runtime_root_state": state.runtime_root_state,
            "accountable_seat": state.accountable_seat,
            "owed_turn": {
                "seat": state.owed_seat,
                "reason": state.owed_reason,
            },
            "source_posture": {
                "value": state.posture,
                "rule": state.posture_rule,
                "dispatch_state": state.dispatch_state,
            },
        },
        "capability": {
            "capability_profile_digest": authority.capability_profile_digest,
            "source_grant_digest": authority.source_grant_digest,
            "economic_envelope_digest": authority.economic_envelope_digest,
        },
        "release": {"release_class": authority.release_class.value},
        "continuity": {
            "session_assurance": "COO_PRINCIPAL_MISSION_BOUND",
            "current_coo_target": None,
        },
        "decision_posture": decision.value,
        "new_effect_gate": gate.value,
        "reserved_boundaries": list(RESERVED_BOUNDARIES),
        "reason_codes": reasons,
    }


__all__ = [
    "SCHEMA",
    "RESERVED_BOUNDARIES",
    "AuthorityFact",
    "DecisionPosture",
    "NewEffectGate",
    "PrincipalFact",
    "ReleaseClass",
    "project_coo_principal_mandate",
]
