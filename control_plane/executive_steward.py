"""Pure, read-only Executive Steward composition.

This module is the canonical first OCR-6 read core.  It accepts immutable,
source-attributed facts gathered by existing owners and answers deterministic
responsibility, attention, runtime, blocker, and reviewed-surface queries.

It deliberately has no gather layer and no side effects.  Agent OS owns the
responsibility identity supplied here; Executive OS and RuntimeBinding own
runtime facts; Executive Inbox and Wake own attention facts; the existing
surface-binding store owns navigation facts.  A conflict or absent/stale
source is returned as typed uncertainty.  The Steward never chooses a winner
by title, clock order, provider label, or prose.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any, TypeVar

RESULT_SCHEMA = "mastermind.executive_steward.result.v1"


class _ValueEnum(str, enum.Enum):
    """String enum whose value is the public wire value."""


class SourceOwner(_ValueEnum):
    AGENT_OS = "agent_os"
    EXECUTIVE_OS = "executive_os"
    RUNTIME_BINDING = "runtime_binding"
    EXECUTIVE_INBOX = "executive_inbox"
    WAKE = "wake"
    SURFACE_BINDINGS = "surface_bindings"
    CAPACITY = "capacity"


class Seat(_ValueEnum):
    CHAIRMAN = "chairman"
    CEO = "ceo"
    COO = "coo"
    WORKER = "worker"


class Freshness(_ValueEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class EffectState(_ValueEnum):
    NONE = "none"
    APPLIED = "applied"
    EFFECT_UNKNOWN = "effect_unknown"


class CapacityState(_ValueEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class QueryStatus(_ValueEnum):
    OK = "ok"
    UNKNOWN = "unknown"
    DEGRADED = "degraded"
    REFUSED = "refused"


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise ValueError(f"{name} must be a non-empty token")
    return value


def _require_sentence(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _valid_responsibility_ref(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("WS:")
        and len(value) > 3
        and not any(char.isspace() for char in value)
    )


def _require_responsibility_ref(value: object) -> str:
    if not _valid_responsibility_ref(value):
        raise ValueError("responsibility_ref must be an exact WS:<key> identity")
    return value


def _require_job_ref(value: object) -> str:
    token = _require_text("root_job_id", value)
    if not token.startswith("JOB-"):
        raise ValueError("root_job_id must be an exact JOB-* identity")
    return token


def _require_enum(name: str, value: object, expected: type[enum.Enum]) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be {expected.__name__}")


def _require_source_owner(
    source: "SourceRef", allowed: tuple[SourceOwner, ...], fact_name: str
) -> None:
    if not isinstance(source, SourceRef):
        raise TypeError(f"{fact_name} must be SourceRef")
    if source.owner not in allowed:
        if len(allowed) == 1:
            raise ValueError(f"{fact_name} owner must be {allowed[0].value}")
        values = ", ".join(owner.value for owner in allowed)
        raise ValueError(f"{fact_name} owner must be one of: {values}")


@dataclasses.dataclass(frozen=True, slots=True)
class SourceRef:
    owner: SourceOwner
    ref: str
    observed_at: str | None
    freshness: Freshness

    def __post_init__(self) -> None:
        _require_enum("owner", self.owner, SourceOwner)
        _require_text("source ref", self.ref)
        if self.observed_at is not None:
            _require_text("observed_at", self.observed_at)
        _require_enum("freshness", self.freshness, Freshness)
        if self.freshness is not Freshness.UNKNOWN and self.observed_at is None:
            raise ValueError(
                "observed_at is required for current or stale source facts"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class ResponsibilityFact:
    responsibility_ref: str
    title: str
    accountable_seat: Seat
    state: str | None
    root_job_id: str | None
    source: SourceRef

    def __post_init__(self) -> None:
        _require_responsibility_ref(self.responsibility_ref)
        _require_sentence("title", self.title)
        _require_enum("accountable_seat", self.accountable_seat, Seat)
        if self.state is not None:
            _require_text("state", self.state)
        if self.root_job_id is not None:
            _require_job_ref(self.root_job_id)
        _require_source_owner(self.source, (SourceOwner.AGENT_OS,), "responsibility")


@dataclasses.dataclass(frozen=True, slots=True)
class AttentionFact:
    attention_id: str
    responsibility_ref: str
    target_seat: Seat
    kind: str
    reason: str
    source: SourceRef

    def __post_init__(self) -> None:
        _require_text("attention_id", self.attention_id)
        _require_responsibility_ref(self.responsibility_ref)
        _require_enum("target_seat", self.target_seat, Seat)
        _require_text("kind", self.kind)
        _require_sentence("reason", self.reason)
        _require_source_owner(
            self.source,
            (SourceOwner.EXECUTIVE_INBOX, SourceOwner.WAKE),
            "attention",
        )


@dataclasses.dataclass(frozen=True, slots=True)
class RuntimeFact:
    """Composed runtime evidence with independently enforced source authority."""

    responsibility_ref: str
    root_job_id: str
    seat: Seat
    attempt_id: str
    worker_id: str
    status: str
    session_alias: str
    runtime_binding_id: str
    binding_generation: int
    continuation_state: str
    effect_state: EffectState
    capacity_state: CapacityState
    previous_attempt_id: str | None
    movement_reason_code: str | None
    executive_source: SourceRef
    binding_source: SourceRef
    reasoning_surface: str | None = None
    account_label: str | None = None
    host_ref: str | None = None
    provider_session_id_present: bool | None = None

    def __post_init__(self) -> None:
        _require_responsibility_ref(self.responsibility_ref)
        _require_job_ref(self.root_job_id)
        _require_enum("seat", self.seat, Seat)
        _require_text("attempt_id", self.attempt_id)
        _require_text("worker_id", self.worker_id)
        _require_text("status", self.status)
        _require_text("session_alias", self.session_alias)
        _require_text("runtime_binding_id", self.runtime_binding_id)
        if type(self.binding_generation) is not int or self.binding_generation < 1:
            raise ValueError("binding_generation must be an integer >= 1")
        _require_text("continuation_state", self.continuation_state)
        _require_enum("effect_state", self.effect_state, EffectState)
        _require_enum("capacity_state", self.capacity_state, CapacityState)
        if self.previous_attempt_id is not None:
            _require_text("previous_attempt_id", self.previous_attempt_id)
        if self.movement_reason_code is not None:
            _require_text("movement_reason_code", self.movement_reason_code)
        if self.reasoning_surface is not None:
            _require_text("reasoning_surface", self.reasoning_surface)
        if self.account_label is not None:
            _require_text("account_label", self.account_label)
        if self.host_ref is not None:
            _require_text("host_ref", self.host_ref)
        if (
            self.provider_session_id_present is not None
            and type(self.provider_session_id_present) is not bool
        ):
            raise TypeError("provider_session_id_present must be bool or None")
        _require_source_owner(
            self.executive_source,
            (SourceOwner.EXECUTIVE_OS,),
            "executive_source",
        )
        _require_source_owner(
            self.binding_source,
            (SourceOwner.RUNTIME_BINDING,),
            "binding_source",
        )


def _runtime_sources(fact: RuntimeFact) -> tuple[SourceRef, SourceRef]:
    return (fact.executive_source, fact.binding_source)


def _runtime_candidate_sources(facts: tuple[RuntimeFact, ...]) -> tuple[SourceRef, ...]:
    return tuple(source for fact in facts for source in _runtime_sources(fact))


@dataclasses.dataclass(frozen=True, slots=True)
class BlockerFact:
    responsibility_ref: str
    code: str
    explanation: str
    target_seat: Seat
    effect_state: EffectState
    source: SourceRef

    def __post_init__(self) -> None:
        _require_responsibility_ref(self.responsibility_ref)
        _require_text("blocker code", self.code)
        _require_sentence("explanation", self.explanation)
        _require_enum("target_seat", self.target_seat, Seat)
        _require_enum("effect_state", self.effect_state, EffectState)
        _require_source_owner(
            self.source,
            (SourceOwner.EXECUTIVE_OS, SourceOwner.EXECUTIVE_INBOX, SourceOwner.WAKE),
            "blocker",
        )


@dataclasses.dataclass(frozen=True, slots=True)
class SurfaceFact:
    responsibility_ref: str
    role: Seat
    seat_ref: str | None
    surface_ref: str
    provider: str
    locator_kind: str
    reviewed_at: str | None
    source: SourceRef

    def __post_init__(self) -> None:
        _require_responsibility_ref(self.responsibility_ref)
        _require_enum("role", self.role, Seat)
        if self.seat_ref is not None:
            _require_text("seat_ref", self.seat_ref)
        _require_text("surface_ref", self.surface_ref)
        _require_text("provider", self.provider)
        _require_text("locator_kind", self.locator_kind)
        if self.reviewed_at is not None:
            _require_text("reviewed_at", self.reviewed_at)
        _require_source_owner(self.source, (SourceOwner.SURFACE_BINDINGS,), "surface")


@dataclasses.dataclass(frozen=True, slots=True)
class SourceFailure:
    owner: SourceOwner
    code: str
    explanation: str
    source_ref: str
    observed_at: str | None

    def __post_init__(self) -> None:
        _require_enum("owner", self.owner, SourceOwner)
        _require_text("source failure code", self.code)
        _require_sentence("source failure explanation", self.explanation)
        _require_text("source_ref", self.source_ref)
        if self.observed_at is not None:
            _require_text("observed_at", self.observed_at)

    def as_source(self) -> SourceRef:
        return SourceRef(
            owner=self.owner,
            ref=self.source_ref,
            observed_at=self.observed_at,
            freshness=Freshness.UNKNOWN,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class QueryIssue:
    code: str
    message: str
    sources: tuple[SourceRef, ...] = ()

    def __post_init__(self) -> None:
        _require_text("issue code", self.code)
        _require_sentence("issue message", self.message)
        if not isinstance(self.sources, tuple) or not all(
            isinstance(source, SourceRef) for source in self.sources
        ):
            raise TypeError("issue sources must be a tuple of SourceRef")


def _encode(value: object) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return {
            field.name: _encode(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class StewardResult:
    operation: str
    status: QueryStatus
    data: object | None
    issues: tuple[QueryIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RESULT_SCHEMA,
            "operation": self.operation,
            "status": self.status.value,
            "data": _encode(self.data),
            "issues": _encode(self.issues),
        }


_FactT = TypeVar("_FactT")


def _fact_tuple(
    name: str,
    values: object,
    expected: type[_FactT],
    key,
) -> tuple[_FactT, ...]:
    if not isinstance(values, tuple) or not all(
        isinstance(value, expected) for value in values
    ):
        raise TypeError(f"{name} must be a tuple of {expected.__name__}")
    return tuple(sorted(values, key=key))


def _source_key(source: SourceRef) -> tuple[str, str, str, str]:
    return (
        source.owner.value,
        source.ref,
        source.observed_at or "",
        source.freshness.value,
    )


def _issue(code: str, message: str, sources: tuple[SourceRef, ...] = ()) -> QueryIssue:
    return QueryIssue(
        code=code,
        message=message,
        sources=tuple(sorted(sources, key=_source_key)),
    )


def _issue_key(
    issue: QueryIssue,
) -> tuple[str, str, tuple[tuple[str, str, str, str], ...]]:
    return (
        issue.code,
        issue.message,
        tuple(_source_key(source) for source in issue.sources),
    )


def _result(
    operation: str,
    status: QueryStatus,
    data: object | None,
    issues: tuple[QueryIssue, ...] = (),
) -> StewardResult:
    return StewardResult(
        operation=operation,
        status=status,
        data=data,
        issues=tuple(sorted(issues, key=_issue_key)),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class ExecutiveStewardSnapshot:
    """Immutable query surface over one caller-supplied source snapshot."""

    responsibilities: tuple[ResponsibilityFact, ...] = ()
    attention: tuple[AttentionFact, ...] = ()
    runtimes: tuple[RuntimeFact, ...] = ()
    blockers: tuple[BlockerFact, ...] = ()
    surfaces: tuple[SurfaceFact, ...] = ()
    source_failures: tuple[SourceFailure, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "responsibilities",
            _fact_tuple(
                "responsibilities",
                self.responsibilities,
                ResponsibilityFact,
                lambda fact: (
                    fact.responsibility_ref,
                    fact.accountable_seat.value,
                    _source_key(fact.source),
                ),
            ),
        )
        object.__setattr__(
            self,
            "attention",
            _fact_tuple(
                "attention",
                self.attention,
                AttentionFact,
                lambda fact: (fact.attention_id, _source_key(fact.source)),
            ),
        )
        object.__setattr__(
            self,
            "runtimes",
            _fact_tuple(
                "runtimes",
                self.runtimes,
                RuntimeFact,
                lambda fact: (
                    fact.responsibility_ref,
                    fact.seat.value,
                    fact.root_job_id,
                    fact.attempt_id,
                    _source_key(fact.executive_source),
                    _source_key(fact.binding_source),
                ),
            ),
        )
        object.__setattr__(
            self,
            "blockers",
            _fact_tuple(
                "blockers",
                self.blockers,
                BlockerFact,
                lambda fact: (
                    fact.responsibility_ref,
                    fact.code,
                    _source_key(fact.source),
                ),
            ),
        )
        object.__setattr__(
            self,
            "surfaces",
            _fact_tuple(
                "surfaces",
                self.surfaces,
                SurfaceFact,
                lambda fact: (
                    fact.responsibility_ref,
                    fact.role.value,
                    fact.seat_ref or "",
                    fact.surface_ref,
                    _source_key(fact.source),
                ),
            ),
        )
        object.__setattr__(
            self,
            "source_failures",
            _fact_tuple(
                "source_failures",
                self.source_failures,
                SourceFailure,
                lambda failure: (
                    failure.owner.value,
                    failure.code,
                    failure.source_ref,
                    failure.observed_at or "",
                ),
            ),
        )

    def _source_issues(self, owners: tuple[SourceOwner, ...]) -> tuple[QueryIssue, ...]:
        return tuple(
            _issue(failure.code, failure.explanation, (failure.as_source(),))
            for failure in self.source_failures
            if failure.owner in owners
        )

    def _responsibility_matches(
        self, responsibility_ref: str
    ) -> tuple[ResponsibilityFact, ...]:
        return tuple(
            fact
            for fact in self.responsibilities
            if fact.responsibility_ref == responsibility_ref
        )

    def list_responsibilities(self, target_seat: Seat | None = None) -> StewardResult:
        operation = "list_responsibilities"
        if target_seat is not None and not isinstance(target_seat, Seat):
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "invalid_target_seat", "target_seat must be a canonical Seat"
                    ),
                ),
            )

        issues = list(self._source_issues((SourceOwner.AGENT_OS,)))
        selected: list[ResponsibilityFact] = []
        by_ref: dict[str, list[ResponsibilityFact]] = {}
        for fact in self.responsibilities:
            if target_seat is None or fact.accountable_seat is target_seat:
                by_ref.setdefault(fact.responsibility_ref, []).append(fact)
        for responsibility_ref in sorted(by_ref):
            facts = by_ref[responsibility_ref]
            if len(facts) != 1:
                issues.append(
                    _issue(
                        "ambiguous_responsibility_join",
                        f"{responsibility_ref} has {len(facts)} canonical candidates; no winner selected",
                        tuple(fact.source for fact in facts),
                    )
                )
                continue
            fact = facts[0]
            selected.append(fact)
            if fact.source.freshness is not Freshness.CURRENT:
                issues.append(
                    _issue(
                        "stale_responsibility_fact",
                        f"{responsibility_ref} is not current",
                        (fact.source,),
                    )
                )
        status = QueryStatus.DEGRADED if issues else QueryStatus.OK
        return _result(operation, status, tuple(selected), tuple(issues))

    def get_responsibility(self, responsibility_ref: str) -> StewardResult:
        operation = "get_responsibility"
        if not _valid_responsibility_ref(responsibility_ref):
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "invalid_responsibility_ref",
                        "responsibility_ref must be an exact WS:<key> identity",
                    ),
                ),
            )
        source_issues = self._source_issues((SourceOwner.AGENT_OS,))
        matches = self._responsibility_matches(responsibility_ref)
        if not matches:
            if source_issues:
                return _result(operation, QueryStatus.DEGRADED, None, source_issues)
            return _result(
                operation,
                QueryStatus.UNKNOWN,
                None,
                (
                    _issue(
                        "responsibility_unknown",
                        f"no Agent OS responsibility fact exists for {responsibility_ref}",
                    ),
                ),
            )
        if len(matches) != 1:
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "ambiguous_responsibility_join",
                        f"{responsibility_ref} has {len(matches)} canonical candidates; no winner selected",
                        tuple(fact.source for fact in matches),
                    ),
                )
                + source_issues,
            )
        fact = matches[0]
        issues = list(source_issues)
        if fact.source.freshness is not Freshness.CURRENT:
            issues.append(
                _issue(
                    "stale_responsibility_fact",
                    f"{responsibility_ref} is not current",
                    (fact.source,),
                )
            )
        status = QueryStatus.DEGRADED if issues else QueryStatus.OK
        return _result(operation, status, fact, tuple(issues))

    def get_attention(
        self,
        target_seat: Seat | None = None,
        responsibility_ref: str | None = None,
    ) -> StewardResult:
        operation = "get_attention"
        if target_seat is not None and not isinstance(target_seat, Seat):
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "invalid_target_seat", "target_seat must be a canonical Seat"
                    ),
                ),
            )
        if responsibility_ref is not None and not _valid_responsibility_ref(
            responsibility_ref
        ):
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "invalid_responsibility_ref",
                        "responsibility_ref must be an exact WS:<key> identity",
                    ),
                ),
            )

        candidates = tuple(
            fact
            for fact in self.attention
            if (target_seat is None or fact.target_seat is target_seat)
            and (
                responsibility_ref is None
                or fact.responsibility_ref == responsibility_ref
            )
        )
        issues = list(
            self._source_issues(
                (SourceOwner.AGENT_OS, SourceOwner.EXECUTIVE_INBOX, SourceOwner.WAKE)
            )
        )
        joined: list[AttentionFact] = []
        for fact in candidates:
            responsibilities = self._responsibility_matches(fact.responsibility_ref)
            if not responsibilities:
                issues.append(
                    _issue(
                        "attention_responsibility_unknown",
                        f"attention {fact.attention_id} has no exact Agent OS responsibility",
                        (fact.source,),
                    )
                )
                continue
            if len(responsibilities) != 1:
                issues.append(
                    _issue(
                        "ambiguous_attention_responsibility_join",
                        f"attention {fact.attention_id} joins multiple Agent OS responsibilities",
                        (fact.source,)
                        + tuple(item.source for item in responsibilities),
                    )
                )
                continue
            if responsibilities[0].source.freshness is not Freshness.CURRENT:
                issues.append(
                    _issue(
                        "stale_attention_responsibility_join",
                        f"attention {fact.attention_id} joins a stale responsibility",
                        (fact.source, responsibilities[0].source),
                    )
                )
                continue
            joined.append(fact)

        seen: dict[str, list[AttentionFact]] = {}
        for fact in joined:
            seen.setdefault(fact.attention_id, []).append(fact)
            if fact.source.freshness is not Freshness.CURRENT:
                issues.append(
                    _issue(
                        "stale_attention_fact",
                        f"attention {fact.attention_id} is not current",
                        (fact.source,),
                    )
                )
        for attention_id, duplicates in seen.items():
            if len(duplicates) > 1:
                issues.append(
                    _issue(
                        "ambiguous_attention_identity",
                        f"attention {attention_id} has {len(duplicates)} candidates",
                        tuple(fact.source for fact in duplicates),
                    )
                )
        facts = tuple(fact for fact in joined if len(seen[fact.attention_id]) == 1)
        status = QueryStatus.DEGRADED if issues else QueryStatus.OK
        return _result(operation, status, facts, tuple(issues))

    def get_current_runtime(self, responsibility_ref: str, seat: Seat) -> StewardResult:
        operation = "get_current_runtime"
        if not _valid_responsibility_ref(responsibility_ref):
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "invalid_responsibility_ref",
                        "responsibility_ref must be an exact WS:<key> identity",
                    ),
                ),
            )
        if not isinstance(seat, Seat):
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (_issue("invalid_seat", "seat must be a canonical Seat"),),
            )

        core_source_issues = self._source_issues(
            (
                SourceOwner.AGENT_OS,
                SourceOwner.EXECUTIVE_OS,
                SourceOwner.RUNTIME_BINDING,
            )
        )
        capacity_issues = self._source_issues((SourceOwner.CAPACITY,))
        source_issues = core_source_issues + capacity_issues
        responsibilities = self._responsibility_matches(responsibility_ref)
        if len(responsibilities) > 1:
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "ambiguous_responsibility_join",
                        f"{responsibility_ref} has multiple Agent OS candidates",
                        tuple(fact.source for fact in responsibilities),
                    ),
                )
                + source_issues,
            )
        if not responsibilities:
            if source_issues:
                return _result(operation, QueryStatus.DEGRADED, None, source_issues)
            return _result(
                operation,
                QueryStatus.UNKNOWN,
                None,
                (
                    _issue(
                        "responsibility_unknown",
                        f"no Agent OS responsibility fact exists for {responsibility_ref}",
                    ),
                ),
            )
        responsibility = responsibilities[0]
        if responsibility.root_job_id is None:
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "runtime_root_missing",
                        f"{responsibility_ref} has no exact root_job_id join",
                        (responsibility.source,),
                    ),
                )
                + source_issues,
            )

        candidates = tuple(
            fact
            for fact in self.runtimes
            if fact.responsibility_ref == responsibility_ref and fact.seat is seat
        )
        if not candidates:
            if source_issues:
                return _result(operation, QueryStatus.DEGRADED, None, source_issues)
            return _result(
                operation,
                QueryStatus.UNKNOWN,
                None,
                (
                    _issue(
                        "runtime_unknown",
                        f"no current runtime fact exists for {responsibility_ref}/{seat.value}",
                    ),
                ),
            )
        wrong_root = tuple(
            fact
            for fact in candidates
            if fact.root_job_id != responsibility.root_job_id
        )
        if wrong_root:
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "runtime_root_mismatch",
                        f"runtime candidates do not all join root {responsibility.root_job_id}",
                        _runtime_candidate_sources(candidates),
                    ),
                )
                + source_issues,
            )
        if len(candidates) != 1:
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "ambiguous_runtime_join",
                        f"{responsibility_ref}/{seat.value} has {len(candidates)} current candidates",
                        _runtime_candidate_sources(candidates),
                    ),
                )
                + source_issues,
            )
        fact = candidates[0]
        if fact.effect_state is EffectState.EFFECT_UNKNOWN:
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "reconciliation_required",
                        "runtime effect is unknown; no current operator may be asserted",
                        _runtime_sources(fact),
                    ),
                )
                + source_issues,
            )
        if (
            responsibility.source.freshness is not Freshness.CURRENT
            or fact.executive_source.freshness is not Freshness.CURRENT
            or fact.binding_source.freshness is not Freshness.CURRENT
        ):
            return _result(
                operation,
                QueryStatus.DEGRADED,
                None,
                (
                    _issue(
                        "stale_runtime_join",
                        "responsibility, Executive OS runtime, or RuntimeBinding evidence is not current",
                        (responsibility.source,) + _runtime_sources(fact),
                    ),
                )
                + source_issues,
            )
        if core_source_issues:
            return _result(operation, QueryStatus.DEGRADED, None, source_issues)
        if capacity_issues:
            return _result(operation, QueryStatus.DEGRADED, fact, capacity_issues)
        return _result(operation, QueryStatus.OK, fact)

    def explain_blocker(self, responsibility_ref: str) -> StewardResult:
        operation = "explain_blocker"
        if not _valid_responsibility_ref(responsibility_ref):
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "invalid_responsibility_ref",
                        "responsibility_ref must be an exact WS:<key> identity",
                    ),
                ),
            )
        source_issues = self._source_issues(
            (
                SourceOwner.AGENT_OS,
                SourceOwner.EXECUTIVE_OS,
                SourceOwner.EXECUTIVE_INBOX,
                SourceOwner.WAKE,
            )
        )
        responsibilities = self._responsibility_matches(responsibility_ref)
        if len(responsibilities) != 1:
            if not responsibilities and source_issues:
                return _result(operation, QueryStatus.DEGRADED, None, source_issues)
            code = (
                "responsibility_unknown"
                if not responsibilities
                else "ambiguous_responsibility_join"
            )
            status = (
                QueryStatus.UNKNOWN if not responsibilities else QueryStatus.REFUSED
            )
            return _result(
                operation,
                status,
                None,
                (
                    _issue(
                        code,
                        f"cannot establish one Agent OS responsibility for {responsibility_ref}",
                        tuple(fact.source for fact in responsibilities),
                    ),
                )
                + source_issues,
            )
        matches = tuple(
            fact
            for fact in self.blockers
            if fact.responsibility_ref == responsibility_ref
        )
        if not matches:
            if source_issues:
                return _result(operation, QueryStatus.DEGRADED, None, source_issues)
            return _result(
                operation,
                QueryStatus.UNKNOWN,
                None,
                (
                    _issue(
                        "blocker_unknown",
                        f"no source-authored blocker fact exists for {responsibility_ref}",
                    ),
                ),
            )
        if len(matches) != 1:
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "ambiguous_blocker_join",
                        f"{responsibility_ref} has {len(matches)} blocker candidates",
                        tuple(fact.source for fact in matches),
                    ),
                )
                + source_issues,
            )
        fact = matches[0]
        issues = list(source_issues)
        if responsibilities[0].source.freshness is not Freshness.CURRENT:
            issues.append(
                _issue(
                    "stale_blocker_join",
                    "blocker explanation joins a stale Agent OS responsibility",
                    (responsibilities[0].source, fact.source),
                )
            )
        if fact.effect_state is EffectState.EFFECT_UNKNOWN:
            issues.append(
                _issue(
                    "reconciliation_required",
                    "blocker carries EFFECT_UNKNOWN and requires reconciliation",
                    (fact.source,),
                )
            )
            return _result(
                operation,
                QueryStatus.REFUSED,
                fact,
                tuple(issues),
            )
        if fact.source.freshness is not Freshness.CURRENT:
            issues.append(
                _issue(
                    "stale_blocker_fact",
                    f"blocker for {responsibility_ref} is not current",
                    (fact.source,),
                )
            )
        status = QueryStatus.DEGRADED if issues else QueryStatus.OK
        return _result(operation, status, fact, tuple(issues))

    def resolve_surface(
        self,
        responsibility_ref: str,
        role: Seat,
        *,
        seat_ref: str | None = None,
    ) -> StewardResult:
        operation = "resolve_surface"
        if not _valid_responsibility_ref(responsibility_ref):
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "invalid_responsibility_ref",
                        "responsibility_ref must be an exact WS:<key> identity",
                    ),
                ),
            )
        if not isinstance(role, Seat):
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (_issue("invalid_role", "role must be a canonical Seat"),),
            )
        if seat_ref is not None:
            try:
                _require_text("seat_ref", seat_ref)
            except ValueError as exc:
                return _result(
                    operation,
                    QueryStatus.REFUSED,
                    None,
                    (_issue("invalid_seat_ref", str(exc)),),
                )

        source_issues = self._source_issues(
            (SourceOwner.AGENT_OS, SourceOwner.SURFACE_BINDINGS)
        )
        responsibilities = self._responsibility_matches(responsibility_ref)
        if len(responsibilities) != 1:
            if not responsibilities and source_issues:
                return _result(operation, QueryStatus.DEGRADED, None, source_issues)
            code = (
                "responsibility_unknown"
                if not responsibilities
                else "ambiguous_responsibility_join"
            )
            status = (
                QueryStatus.UNKNOWN if not responsibilities else QueryStatus.REFUSED
            )
            return _result(
                operation,
                status,
                None,
                (
                    _issue(
                        code,
                        f"cannot establish one Agent OS responsibility for {responsibility_ref}",
                        tuple(fact.source for fact in responsibilities),
                    ),
                )
                + source_issues,
            )
        if responsibilities[0].source.freshness is not Freshness.CURRENT:
            return _result(
                operation,
                QueryStatus.DEGRADED,
                None,
                (
                    _issue(
                        "stale_surface_join",
                        "surface resolution requires a current Agent OS responsibility",
                        (responsibilities[0].source,),
                    ),
                )
                + source_issues,
            )
        matches = tuple(
            fact
            for fact in self.surfaces
            if fact.responsibility_ref == responsibility_ref
            and fact.role is role
            and (seat_ref is None or fact.seat_ref == seat_ref)
        )
        if not matches:
            if source_issues:
                return _result(operation, QueryStatus.DEGRADED, None, source_issues)
            return _result(
                operation,
                QueryStatus.UNKNOWN,
                None,
                (
                    _issue(
                        "surface_unknown",
                        f"no exact surface binding exists for {responsibility_ref}/{role.value}",
                    ),
                ),
            )
        if len(matches) != 1:
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "ambiguous_surface_join",
                        f"{responsibility_ref}/{role.value} has {len(matches)} surface candidates",
                        tuple(fact.source for fact in matches),
                    ),
                )
                + source_issues,
            )
        fact = matches[0]
        if fact.reviewed_at is None:
            return _result(
                operation,
                QueryStatus.REFUSED,
                None,
                (
                    _issue(
                        "surface_not_reviewed",
                        "the exact binding has no accepted review timestamp",
                        (fact.source,),
                    ),
                )
                + source_issues,
            )
        if fact.source.freshness is not Freshness.CURRENT:
            return _result(
                operation,
                QueryStatus.DEGRADED,
                None,
                (
                    _issue(
                        "stale_surface_binding",
                        "the exact reviewed surface binding is not current",
                        (fact.source,),
                    ),
                )
                + source_issues,
            )
        if source_issues:
            return _result(operation, QueryStatus.DEGRADED, None, source_issues)
        return _result(operation, QueryStatus.OK, fact)
