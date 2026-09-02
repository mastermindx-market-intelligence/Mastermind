"""Pure deterministic operator-continuity projection.

The composer accepts already exact-joined Executive, RuntimeBinding,
continuation, capacity, and transport facts.  It performs no gathering, I/O,
persistence, routing, lifecycle mutation, provider work, clock read, or model
inference.

Schema: ``mastermind.operator_continuity_projection.v1``.
"""
from __future__ import annotations

import dataclasses
import enum
import re
from typing import Any


SCHEMA = "mastermind.operator_continuity_projection.v1"

_JOB_ID_RE = re.compile(r"^JOB-\d{3,}$")
_ATTEMPT_ID_RE = re.compile(r"^ATT-[0-9a-f]{32}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SESSION_ALIAS_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")
_BINDING_ID_RE = re.compile(r"^bind-[a-z0-9][a-z0-9._-]{7,63}$")
_REASON_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class _ValueEnum(str, enum.Enum):
    """String enum whose value is the public wire value."""


class Seat(_ValueEnum):
    CHAIRMAN = "chairman"
    CEO = "ceo"
    COO = "coo"


class AttemptState(_ValueEnum):
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    RATE_LIMITED = "RATE_LIMITED"
    FAILED = "FAILED"
    LOST = "LOST"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ContinuationState(_ValueEnum):
    NONE = "NONE"
    PREPARED = "PREPARED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNKNOWN = "UNKNOWN"


class EffectState(_ValueEnum):
    NONE = "none"
    APPLIED = "applied"
    EFFECT_UNKNOWN = "effect_unknown"


class CurrentJoinState(_ValueEnum):
    EXACT = "exact"
    NONE = "none"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    CONTRADICTORY = "contradictory"


class CapacityState(_ValueEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class ContinuityStatus(_ValueEnum):
    RUNNING = "RUNNING"
    REBINDING = "REBINDING"
    BLOCKED = "BLOCKED"
    WAITING_CAPACITY = "WAITING_CAPACITY"
    COMPLETED = "COMPLETED"
    UNKNOWN = "UNKNOWN"


class AttentionClass(_ValueEnum):
    NONE = "none"
    DECISION_REQUIRED = "decision_required"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    CAPACITY_RISK = "capacity_risk"
    TRANSPORT_DEGRADED = "transport_degraded"


_TERMINAL = frozenset(
    {
        AttemptState.RATE_LIMITED,
        AttemptState.FAILED,
        AttemptState.LOST,
        AttemptState.COMPLETED,
        AttemptState.CANCELLED,
    }
)
_ACTIVE = frozenset(
    {
        AttemptState.CLAIMED,
        AttemptState.RUNNING,
        AttemptState.CHECKPOINTED,
        AttemptState.CANCEL_REQUESTED,
    }
)


def _enum(name: str, value: object, expected: type[enum.Enum]) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be {expected.__name__}")


def _match(name: str, value: object, pattern: re.Pattern[str], message: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"{name} {message}")
    return value


def _job(name: str, value: object) -> str:
    return _match(name, value, _JOB_ID_RE, "must be an exact JOB-* identity")


def _attempt(name: str, value: object) -> str:
    return _match(name, value, _ATTEMPT_ID_RE, "must be an exact ATT-* identity")


def _identifier(name: str, value: object) -> str:
    return _match(name, value, _IDENTIFIER_RE, "must be a bounded opaque identifier")


def _alias(value: object) -> str:
    return _match(
        "session_alias",
        value,
        _SESSION_ALIAS_RE,
        "must be an exact logical session identity",
    )


def _opaque(name: str, value: object, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    result = _identifier(name, value)
    if "@" in result:
        raise ValueError(f"{name} must be an opaque non-PII token")
    return result


def _binding(binding_id: object, generation: object) -> None:
    if binding_id is None and generation is None:
        return
    if binding_id is None or generation is None:
        raise ValueError("binding_id and binding_generation must be present together")
    _match(
        "binding_id",
        binding_id,
        _BINDING_ID_RE,
        "must be a durable bind-* identity",
    )
    if type(generation) is not int or generation < 1:
        raise ValueError("binding_generation must be an integer >= 1")


def _capsule(state: ContinuationState, capsule_id: object) -> None:
    if state in {ContinuationState.PREPARED, ContinuationState.ACKNOWLEDGED}:
        _match(
            "capsule_id",
            capsule_id,
            _DIGEST_RE,
            "must be a digest for PREPARED or ACKNOWLEDGED continuation",
        )
        return
    if state is ContinuationState.UNKNOWN and capsule_id is not None:
        _match("capsule_id", capsule_id, _DIGEST_RE, "must be a digest")
        return
    if state is ContinuationState.NONE and capsule_id is not None:
        raise ValueError("capsule_id is invalid when continuation state is NONE")


def _actor(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("logical_actor must be a non-empty trimmed string")
    if (
        len(value) > 128
        or "@" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("logical_actor is outside the bounded public label contract")
    return value


def _reasons(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError("reason_codes must be a tuple")
    if len(value) > 32:
        raise ValueError("reason_codes may contain at most 32 entries")
    result: set[str] = set()
    for code in value:
        if not isinstance(code, str) or _REASON_CODE_RE.fullmatch(code) is None:
            raise ValueError("reason_codes must contain bounded lowercase tokens")
        result.add(code)
    return tuple(sorted(result))


@dataclasses.dataclass(frozen=True, slots=True)
class CapacityEvidence:
    state: CapacityState
    eligible: bool | None
    evidence_age_seconds: int | None
    stale: bool
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _enum("capacity state", self.state, CapacityState)
        if self.eligible is not None and type(self.eligible) is not bool:
            raise TypeError("capacity eligible must be bool or None")
        if self.evidence_age_seconds is not None and (
            type(self.evidence_age_seconds) is not int
            or self.evidence_age_seconds < 0
        ):
            raise ValueError("evidence_age_seconds must be a non-negative integer or None")
        if type(self.stale) is not bool:
            raise TypeError("capacity stale must be bool")
        if (
            self.state is not CapacityState.UNKNOWN or self.stale
        ) and self.evidence_age_seconds is None:
            raise ValueError("non-unknown or stale capacity requires evidence_age_seconds")
        if self.state is CapacityState.AVAILABLE and self.eligible is not True:
            raise ValueError("available capacity requires eligible=True")
        if self.state is CapacityState.UNKNOWN and self.eligible is not None:
            raise ValueError("unknown capacity requires eligible=None")
        object.__setattr__(self, "reason_codes", _reasons(self.reason_codes))


@dataclasses.dataclass(frozen=True, slots=True)
class TransportEvidence:
    degraded: bool = False
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.degraded) is not bool:
            raise TypeError("transport degraded must be bool")
        object.__setattr__(self, "reason_codes", _reasons(self.reason_codes))


@dataclasses.dataclass(frozen=True, slots=True)
class CurrentAttemptFact:
    root_job_id: str
    job_id: str
    attempt_id: str
    worker_id: str
    attempt_state: AttemptState
    target_seat: Seat
    session_alias: str
    provider: str
    account_label: str
    host_ref: str | None
    provider_session_id_present: bool | None
    binding_id: str | None
    binding_generation: int | None
    continuation_state: ContinuationState
    capsule_id: str | None
    predecessor_attempt_id: str | None

    def __post_init__(self) -> None:
        _job("current root_job_id", self.root_job_id)
        _job("current job_id", self.job_id)
        _attempt("current attempt_id", self.attempt_id)
        _identifier("worker_id", self.worker_id)
        _enum("attempt_state", self.attempt_state, AttemptState)
        _enum("target_seat", self.target_seat, Seat)
        _alias(self.session_alias)
        _opaque("provider", self.provider)
        _opaque("account_label", self.account_label)
        _opaque("host_ref", self.host_ref, optional=True)
        if self.provider_session_id_present is not None and (
            type(self.provider_session_id_present) is not bool
        ):
            raise TypeError("provider_session_id_present must be bool or None")
        _binding(self.binding_id, self.binding_generation)
        _enum("continuation_state", self.continuation_state, ContinuationState)
        _capsule(self.continuation_state, self.capsule_id)
        if self.predecessor_attempt_id is not None:
            _attempt("predecessor_attempt_id", self.predecessor_attempt_id)


@dataclasses.dataclass(frozen=True, slots=True)
class PreviousAttemptFact:
    root_job_id: str
    job_id: str
    attempt_id: str
    worker_id: str
    terminal_state: AttemptState
    provider: str
    account_label: str

    def __post_init__(self) -> None:
        _job("previous root_job_id", self.root_job_id)
        _job("previous job_id", self.job_id)
        _attempt("previous attempt_id", self.attempt_id)
        _identifier("previous worker_id", self.worker_id)
        _enum("terminal_state", self.terminal_state, AttemptState)
        if self.terminal_state not in _TERMINAL:
            raise ValueError("previous terminal_state must be terminal")
        _opaque("previous provider", self.provider)
        _opaque("account_label", self.account_label)


@dataclasses.dataclass(frozen=True, slots=True)
class OperatorContinuityFacts:
    root_job_id: str
    job_id: str
    current_attempt_id: str | None
    target_seat: Seat
    session_alias: str
    logical_actor: str
    current_join: CurrentJoinState
    current: CurrentAttemptFact | None
    previous: PreviousAttemptFact | None
    requeue_committed: bool
    effect_state: EffectState
    capacity: CapacityEvidence | None = None
    transport: TransportEvidence = dataclasses.field(default_factory=TransportEvidence)

    def __post_init__(self) -> None:
        _job("root_job_id", self.root_job_id)
        _job("job_id", self.job_id)
        if self.current_attempt_id is not None:
            _attempt("current_attempt_id", self.current_attempt_id)
        _enum("target_seat", self.target_seat, Seat)
        _alias(self.session_alias)
        _actor(self.logical_actor)
        _enum("current_join", self.current_join, CurrentJoinState)
        _enum("effect_state", self.effect_state, EffectState)
        if self.current is not None and not isinstance(self.current, CurrentAttemptFact):
            raise TypeError("current must be CurrentAttemptFact or None")
        if self.previous is not None and not isinstance(self.previous, PreviousAttemptFact):
            raise TypeError("previous must be PreviousAttemptFact or None")
        if type(self.requeue_committed) is not bool:
            raise TypeError("requeue_committed must be bool")
        if self.capacity is not None and not isinstance(self.capacity, CapacityEvidence):
            raise TypeError("capacity must be CapacityEvidence or None")
        if not isinstance(self.transport, TransportEvidence):
            raise TypeError("transport must be TransportEvidence")
        self._validate_joins()
        self._validate_requeue()

    def _validate_joins(self) -> None:
        if self.current_join is CurrentJoinState.EXACT:
            if self.current is None or self.current_attempt_id is None:
                raise ValueError("EXACT current join requires current and current_attempt_id")
            checks = {
                "current_attempt_id": self.current.attempt_id == self.current_attempt_id,
                "current root_job_id": self.current.root_job_id == self.root_job_id,
                "current job_id": self.current.job_id == self.job_id,
                "current target_seat": self.current.target_seat is self.target_seat,
                "current session_alias": self.current.session_alias == self.session_alias,
            }
            failed = next((name for name, valid in checks.items() if not valid), None)
            if failed is not None:
                raise ValueError(f"{failed} does not match the exact current join")
        elif self.current is not None or self.current_attempt_id is not None:
            raise ValueError("non-EXACT current join cannot carry a selected current Attempt")
        if self.previous is not None and self.previous.root_job_id != self.root_job_id:
            raise ValueError("previous root_job_id does not match exact root")

    def _validate_requeue(self) -> None:
        if not self.requeue_committed:
            if self.current is not None and self.current.predecessor_attempt_id is not None:
                raise ValueError("predecessor_attempt_id requires requeue_committed=True")
            return
        if self.current_join is not CurrentJoinState.EXACT:
            raise ValueError("committed requeue requires an exact current Attempt")
        if self.current is None or self.previous is None:
            raise ValueError("committed requeue requires current and previous Attempt facts")
        if self.current.predecessor_attempt_id != self.previous.attempt_id:
            raise ValueError("predecessor_attempt_id does not match previous Attempt")
        if self.current.attempt_id == self.previous.attempt_id:
            raise ValueError("committed requeue requires a distinct Attempt")
        if self.current.job_id == self.previous.job_id:
            raise ValueError("committed requeue requires a distinct Job")


@dataclasses.dataclass(frozen=True, slots=True)
class CurrentProjection:
    attempt_id: str
    worker_id: str
    lifecycle_status: AttemptState
    provider: str
    account_label: str
    host_ref: str | None
    provider_session_id_present: bool | None
    binding_id: str | None
    binding_generation: int | None
    continuation_state: ContinuationState
    capsule_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "lifecycle_status": self.lifecycle_status.value,
            "provider": self.provider,
            "account_label": self.account_label,
            "host_ref": self.host_ref,
            "provider_session_id_present": self.provider_session_id_present,
            "binding_id": self.binding_id,
            "binding_generation": self.binding_generation,
            "continuation_state": self.continuation_state.value,
            "capsule_id": self.capsule_id,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class PreviousProjection:
    attempt_id: str
    job_id: str
    worker_id: str
    terminal_status: AttemptState
    provider: str
    account_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "job_id": self.job_id,
            "worker_id": self.worker_id,
            "terminal_status": self.terminal_status.value,
            "provider": self.provider,
            "account_label": self.account_label,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class CapacityProjection:
    state: CapacityState
    eligible: bool | None
    evidence_age_seconds: int | None
    stale: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "eligible": self.eligible,
            "evidence_age_seconds": self.evidence_age_seconds,
            "stale": self.stale,
            "reason_codes": list(self.reason_codes),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class TransportProjection:
    degraded: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"degraded": self.degraded, "reason_codes": list(self.reason_codes)}


@dataclasses.dataclass(frozen=True, slots=True)
class OperatorContinuityProjection:
    root_job_id: str
    job_id: str
    target_seat: Seat
    session_alias: str
    logical_actor: str
    status: ContinuityStatus
    effect_state: EffectState
    current: CurrentProjection | None
    previous: PreviousProjection | None
    capacity: CapacityProjection
    transport: TransportProjection
    attention: AttentionClass
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "root_job_id": self.root_job_id,
            "job_id": self.job_id,
            "target_seat": self.target_seat.value,
            "session_alias": self.session_alias,
            "logical_actor": self.logical_actor,
            "status": self.status.value,
            "effect_state": self.effect_state.value,
            "current": self.current.to_dict() if self.current else None,
            "previous": self.previous.to_dict() if self.previous else None,
            "capacity": self.capacity.to_dict(),
            "transport": self.transport.to_dict(),
            "attention": self.attention.value,
            "reason_codes": list(self.reason_codes),
        }


def _capacity_projection(value: CapacityEvidence | None) -> CapacityProjection:
    if value is None:
        return CapacityProjection(
            CapacityState.UNKNOWN,
            None,
            None,
            False,
            ("capacity_evidence_missing",),
        )
    if value.stale:
        return CapacityProjection(
            CapacityState.UNKNOWN,
            None,
            value.evidence_age_seconds,
            True,
            tuple(sorted({*value.reason_codes, "capacity_evidence_stale"})),
        )
    return CapacityProjection(
        value.state,
        value.eligible,
        value.evidence_age_seconds,
        False,
        value.reason_codes,
    )


def _current(value: CurrentAttemptFact | None) -> CurrentProjection | None:
    if value is None:
        return None
    return CurrentProjection(
        value.attempt_id,
        value.worker_id,
        value.attempt_state,
        value.provider,
        value.account_label,
        value.host_ref,
        value.provider_session_id_present,
        value.binding_id,
        value.binding_generation,
        value.continuation_state,
        value.capsule_id,
    )


def _previous(value: PreviousAttemptFact | None) -> PreviousProjection | None:
    if value is None:
        return None
    return PreviousProjection(
        value.attempt_id,
        value.job_id,
        value.worker_id,
        value.terminal_state,
        value.provider,
        value.account_label,
    )


def _classify(
    facts: OperatorContinuityFacts,
    capacity: CapacityProjection,
) -> tuple[ContinuityStatus, AttentionClass, set[str]]:
    reasons: set[str] = set()
    if facts.effect_state is EffectState.EFFECT_UNKNOWN:
        return (
            ContinuityStatus.BLOCKED,
            AttentionClass.RECONCILIATION_REQUIRED,
            {"effect_unknown"},
        )
    join_reasons = {
        CurrentJoinState.MISSING: "current_join_missing",
        CurrentJoinState.AMBIGUOUS: "current_join_ambiguous",
        CurrentJoinState.CONTRADICTORY: "current_join_contradictory",
    }
    if facts.current_join in join_reasons:
        return (
            ContinuityStatus.UNKNOWN,
            AttentionClass.DECISION_REQUIRED,
            {join_reasons[facts.current_join]},
        )
    if facts.current_join is CurrentJoinState.NONE:
        reasons.add("current_attempt_absent")
        if facts.previous is not None and capacity.eligible is False:
            reasons.add("no_eligible_capacity")
            return ContinuityStatus.WAITING_CAPACITY, AttentionClass.CAPACITY_RISK, reasons
        if facts.previous is None:
            reasons.add("previous_attempt_missing")
        if capacity.eligible is None:
            reasons.add("capacity_unknown")
        return ContinuityStatus.UNKNOWN, AttentionClass.DECISION_REQUIRED, reasons

    current = facts.current
    if current is None:
        raise AssertionError("validated exact current join lost its current fact")
    if current.attempt_state is AttemptState.COMPLETED:
        return ContinuityStatus.COMPLETED, AttentionClass.NONE, {"current_attempt_completed"}
    if current.attempt_state in _TERMINAL:
        if capacity.eligible is False:
            return (
                ContinuityStatus.WAITING_CAPACITY,
                AttentionClass.CAPACITY_RISK,
                {"no_eligible_capacity"},
            )
        return (
            ContinuityStatus.UNKNOWN,
            AttentionClass.DECISION_REQUIRED,
            {"current_attempt_terminal_without_successor"},
        )
    if current.attempt_state not in _ACTIVE:
        raise AssertionError("closed AttemptState set is incomplete")

    if current.attempt_state is AttemptState.CLAIMED:
        reasons.add("current_attempt_claimed")
    if current.provider_session_id_present is not True:
        reasons.add("provider_session_absent")
    if current.binding_id is None or current.binding_generation is None:
        reasons.add("runtime_binding_absent")
    continuation_reason = {
        ContinuationState.PREPARED: "continuation_prepared",
        ContinuationState.ACKNOWLEDGED: "continuation_acknowledged",
        ContinuationState.UNKNOWN: "continuation_unknown",
    }.get(current.continuation_state)
    if continuation_reason:
        reasons.add(continuation_reason)
    elif facts.requeue_committed:
        reasons.add("continuation_ack_missing")

    binding_ready = (
        current.provider_session_id_present is True
        and current.binding_id is not None
        and current.binding_generation is not None
    )
    continuation_ready = (
        not facts.requeue_committed
        or current.continuation_state is ContinuationState.ACKNOWLEDGED
    )
    if (
        current.attempt_state is AttemptState.CLAIMED
        or not binding_ready
        or current.continuation_state is ContinuationState.PREPARED
        or not continuation_ready
    ):
        return ContinuityStatus.REBINDING, AttentionClass.NONE, reasons
    reasons.add("current_attempt_running")
    if facts.requeue_committed:
        reasons.add("lawful_requeue")
    return ContinuityStatus.RUNNING, AttentionClass.NONE, reasons


def project_operator_continuity(
    facts: OperatorContinuityFacts,
) -> OperatorContinuityProjection:
    """Return one immutable, canonical, side-effect-free projection."""

    if not isinstance(facts, OperatorContinuityFacts):
        raise TypeError("facts must be OperatorContinuityFacts")
    capacity = _capacity_projection(facts.capacity)
    transport = TransportProjection(
        facts.transport.degraded,
        facts.transport.reason_codes,
    )
    status, attention, reasons = _classify(facts, capacity)

    reasons.update(
        code
        for code in capacity.reason_codes
        if code in {"capacity_evidence_missing", "capacity_evidence_stale"}
    )
    capacity_at_risk = (
        capacity.stale
        or capacity.state is CapacityState.DEGRADED
        or capacity.eligible is False
    )
    if transport.degraded:
        reasons.add("transport_degraded")
    if capacity.state is CapacityState.DEGRADED:
        reasons.add("capacity_degraded")
    if capacity.eligible is False:
        reasons.add("no_eligible_capacity")

    if attention is AttentionClass.NONE:
        if transport.degraded:
            attention = AttentionClass.TRANSPORT_DEGRADED
        elif capacity_at_risk and status is not ContinuityStatus.COMPLETED:
            attention = AttentionClass.CAPACITY_RISK

    return OperatorContinuityProjection(
        facts.root_job_id,
        facts.job_id,
        facts.target_seat,
        facts.session_alias,
        facts.logical_actor,
        status,
        facts.effect_state,
        _current(facts.current),
        _previous(facts.previous),
        capacity,
        transport,
        attention,
        tuple(sorted(reasons)),
    )


__all__ = [
    "SCHEMA",
    "AttentionClass",
    "AttemptState",
    "CapacityEvidence",
    "CapacityState",
    "ContinuityStatus",
    "ContinuationState",
    "CurrentAttemptFact",
    "CurrentJoinState",
    "EffectState",
    "OperatorContinuityFacts",
    "OperatorContinuityProjection",
    "PreviousAttemptFact",
    "Seat",
    "TransportEvidence",
    "project_operator_continuity",
]
