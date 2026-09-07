"""Ephemeral W3C runtime primitives owned by the existing Agent Relay process.

The waiter registry and candidate collector are deliberately process-local and
persistence-free. They own no dialogue, Wake, provider, lifecycle, target,
retry, queue, cursor, scheduler, thread pool, or durable authority.
"""
from __future__ import annotations

import asyncio
import inspect
import math
import re
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar


_T = TypeVar("_T")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,255}$")
_WAITER_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
_SESSION_REF_RE = re.compile(r"\Aasd-session-[a-z0-9][a-z0-9-]{7,63}\Z")
_SOURCE_REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SLACK_WORKSPACE_RE = re.compile(r"^T[A-Z0-9]{8,}$")
_SLACK_CHANNEL_RE = re.compile(r"^[CDG][A-Z0-9]{8,}$")
_SLACK_THREAD_RE = re.compile(r"^[0-9]{10,}\.[0-9]{6}$")
_REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$"
)
_WATCH_SOURCE_CONFLICT_CODES = frozenset(
    {
        "ACTIVE_BRANCH_WRITER_CONFLICT",
        "CANONICAL_WATCHER_AUTHORITY_CONFLICT",
        "CANONICAL_WATCHER_READ_INVALID",
        "WATCH_PASS_CONFLICT",
        "WATCH_PASS_INVALID",
        "WATCH_PASS_SOURCE_MISMATCH",
        "WATCH_PROJECTION_INVALID",
        "WATCH_SOURCE_CONFLICT",
        "WATCH_SOURCE_INVALID",
        "WATCH_SOURCE_REVISION_CONFLICT",
    }
)


class TurnRuntimePrimitiveError(RuntimeError):
    """One fixed, payload-free W3C primitive refusal."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ActiveWaiterConflict(TurnRuntimePrimitiveError):
    def __init__(self) -> None:
        super().__init__("ACTIVE_WAITER_CONFLICT")


class CandidateCollectionBusy(TurnRuntimePrimitiveError):
    def __init__(self) -> None:
        super().__init__("CANDIDATE_COLLECTION_INFLIGHT")


class CandidateCollectionUnavailable(TurnRuntimePrimitiveError):
    def __init__(self) -> None:
        super().__init__("CANDIDATE_SOURCE_UNAVAILABLE")


class CandidateCollectionTimeout(TurnRuntimePrimitiveError):
    def __init__(self) -> None:
        super().__init__("CANDIDATE_COLLECTION_TIMEOUT")


class CandidateCollectionOverflow(TurnRuntimePrimitiveError):
    def __init__(self) -> None:
        super().__init__("CANDIDATE_COLLECTION_OVERFLOW")


class WatchedSourceConflict(TurnRuntimePrimitiveError):
    """One bounded, payload-free watched-source or receipt refusal."""

    def __init__(self, code: str) -> None:
        if code not in _WATCH_SOURCE_CONFLICT_CODES:
            raise ValueError("unknown watched-source conflict code")
        super().__init__(code)


def _token(value: Any, *, code: str) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise TurnRuntimePrimitiveError(code)
    return value


class WatcherSide(str, Enum):
    SOL = "SOL"
    WORKER = "WORKER"


class WatchedResponsibility(str, Enum):
    IMPLEMENTATION_BRANCH_WRITER = "IMPLEMENTATION_BRANCH_WRITER"
    RELEASE_MAINTAINER = "RELEASE_MAINTAINER"


class SourceDisposition(str, Enum):
    CURRENT = "CURRENT"
    REMOTE_COMPLETE_AWAITING_STOP = "REMOTE_COMPLETE_AWAITING_STOP"
    TERMINAL_STOPPED = "TERMINAL_STOPPED"
    TERMINAL_SUPPRESSED = "TERMINAL_SUPPRESSED"


class HostExecutionState(str, Enum):
    NOT_INVOKED = "NOT_INVOKED"
    IDLE_GATED = "IDLE_GATED"
    ACTIVELY_BUSY = "ACTIVELY_BUSY"


class WatcherPassOutcome(str, Enum):
    HOST_NOT_INVOKED = "HOST_NOT_INVOKED"
    EXPECTED_OPPORTUNITY_NO_FIRE = "EXPECTED_OPPORTUNITY_NO_FIRE"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
    CARRIER_READ_FAILED = "CARRIER_READ_FAILED"
    ACTIONABLE_EVENT_DETECTED = "ACTIONABLE_EVENT_DETECTED"
    SAME_CARRIER_ACTION_COMPLETED = "SAME_CARRIER_ACTION_COMPLETED"
    EXACT_WAKE_TARGET_ACKNOWLEDGED = "EXACT_WAKE_TARGET_ACKNOWLEDGED"
    EXACT_WAKE_RECORDED_ACK_ABSENT = "EXACT_WAKE_RECORDED_ACK_ABSENT"
    WAKE_EFFECT_UNKNOWN = "WAKE_EFFECT_UNKNOWN"
    SAME_CARRIER_ACTION_FAILED = "SAME_CARRIER_ACTION_FAILED"
    EXACT_WAKE_FAILED = "EXACT_WAKE_FAILED"
    EXACT_TARGET_UNAVAILABLE = "EXACT_TARGET_UNAVAILABLE"
    ACTIVE_WAITER_SUPPRESSED = "ACTIVE_WAITER_SUPPRESSED"
    SOURCE_TERMINAL_SUPPRESSED = "SOURCE_TERMINAL_SUPPRESSED"
    WATCH_STOP_FAILED = "WATCH_STOP_FAILED"


class WatcherHealth(str, Enum):
    CURRENT = "CURRENT"
    WATCH_DEGRADED = "WATCH_DEGRADED"
    TERMINAL_SUPPRESSED = "TERMINAL_SUPPRESSED"


class WatcherAction(str, Enum):
    NO_ACTION = "NO_ACTION"
    SAME_CARRIER_ACTION = "SAME_CARRIER_ACTION"
    EXACT_RUNTIME_BINDING_WAKE = "EXACT_RUNTIME_BINDING_WAKE"
    SESSION_LOST_RUNTIME_BINDING_RECONCILIATION_REQUIRED = (
        "SESSION_LOST/RUNTIME_BINDING_RECONCILIATION_REQUIRED"
    )
    EXACT_TARGET_UNAVAILABLE = "EXACT_TARGET_UNAVAILABLE"
    SUPPRESS_TERMINAL_SOURCE = "SUPPRESS_TERMINAL_SOURCE"


@dataclass(frozen=True, slots=True)
class ExactWatcherCarrier:
    """Exact Slack root; titles, newest tabs, and account labels are excluded."""

    workspace_id: str
    channel_id: str
    thread_ts: str

    def __post_init__(self) -> None:
        if (
            type(self.workspace_id) is not str
            or _SLACK_WORKSPACE_RE.fullmatch(self.workspace_id) is None
            or type(self.channel_id) is not str
            or _SLACK_CHANNEL_RE.fullmatch(self.channel_id) is None
            or type(self.thread_ts) is not str
            or _SLACK_THREAD_RE.fullmatch(self.thread_ts) is None
        ):
            raise WatchedSourceConflict("WATCH_SOURCE_INVALID")


@dataclass(frozen=True, slots=True)
class RuntimeBindingIdentity:
    """Public exact-binding coordinates with no native handle or account label."""

    session_alias: str
    binding_id: str
    binding_generation: int
    reasoning_surface: str

    def __post_init__(self) -> None:
        try:
            _token(self.session_alias, code="WATCH_SOURCE_INVALID")
            _token(self.binding_id, code="WATCH_SOURCE_INVALID")
            _token(self.reasoning_surface, code="WATCH_SOURCE_INVALID")
        except TurnRuntimePrimitiveError:
            raise WatchedSourceConflict("WATCH_SOURCE_INVALID") from None
        if (
            type(self.binding_generation) is not int
            or self.binding_generation < 1
        ):
            raise WatchedSourceConflict("WATCH_SOURCE_INVALID")

    @classmethod
    def from_runtime_binding(cls, value: object) -> "RuntimeBindingIdentity":
        try:
            return cls(
                session_alias=value.session_alias,
                binding_id=value.binding_id,
                binding_generation=value.binding_generation,
                reasoning_surface=value.reasoning_surface,
            )
        except (AttributeError, TypeError, ValueError):
            raise WatchedSourceConflict("WATCH_SOURCE_INVALID") from None


@dataclass(frozen=True, slots=True)
class WatchedSource:
    """Closed, mechanically reconstructed responsibility/source projection.

    This is evidence only.  It has no registration, persistence, scheduling,
    lifecycle, retry, release, merge, or provider-effect seam.
    """

    side: WatcherSide
    responsibility: WatchedResponsibility
    operation_key: str
    exact_carrier: ExactWatcherCarrier
    purpose: str
    source_revision: str
    disposition: SourceDisposition
    repository: str
    pull_request: int
    branch: str
    runtime_binding: RuntimeBindingIdentity | None
    root_job_id: str
    job_id: str
    attempt_id: str
    worker_id: str
    branch_writer_released: bool = False

    def __post_init__(self) -> None:
        try:
            _token(self.operation_key, code="WATCH_SOURCE_INVALID")
            _token(self.purpose, code="WATCH_SOURCE_INVALID")
            _token(self.branch, code="WATCH_SOURCE_INVALID")
            _token(self.root_job_id, code="WATCH_SOURCE_INVALID")
            _token(self.job_id, code="WATCH_SOURCE_INVALID")
            _token(self.attempt_id, code="WATCH_SOURCE_INVALID")
            _token(self.worker_id, code="WATCH_SOURCE_INVALID")
        except TurnRuntimePrimitiveError:
            raise WatchedSourceConflict("WATCH_SOURCE_INVALID") from None
        if (
            type(self.side) is not WatcherSide
            or type(self.responsibility) is not WatchedResponsibility
            or type(self.exact_carrier) is not ExactWatcherCarrier
            or type(self.source_revision) is not str
            or _SOURCE_REVISION_RE.fullmatch(self.source_revision) is None
            or type(self.disposition) is not SourceDisposition
            or type(self.repository) is not str
            or _REPOSITORY_RE.fullmatch(self.repository) is None
            or type(self.pull_request) is not int
            or self.pull_request < 1
            or (
                self.runtime_binding is not None
                and type(self.runtime_binding) is not RuntimeBindingIdentity
            )
            or type(self.branch_writer_released) is not bool
            or self.branch_writer_released
            != (self.disposition is SourceDisposition.TERMINAL_SUPPRESSED)
        ):
            raise WatchedSourceConflict("WATCH_SOURCE_INVALID")

    @property
    def registration_identity(self) -> tuple[object, ...]:
        return (
            self.side,
            self.responsibility,
            self.operation_key,
            self.exact_carrier,
            self.purpose,
        )

    @property
    def identity(self) -> tuple[object, ...]:
        return self.registration_identity + (
            self.source_revision,
            self.disposition,
        )

    @property
    def git_writer_identity(self) -> tuple[str, int, str]:
        return (self.repository, self.pull_request, self.branch)

    @property
    def canonical_source_identity(self) -> tuple[str, str, str, str]:
        return (
            self.root_job_id,
            self.job_id,
            self.attempt_id,
            self.worker_id,
        )

    @property
    def terminal(self) -> bool:
        return self.disposition in {
            SourceDisposition.TERMINAL_STOPPED,
            SourceDisposition.TERMINAL_SUPPRESSED,
        }

    @property
    def semantically_active(self) -> bool:
        return not self.terminal

    @property
    def holds_branch_writer(self) -> bool:
        return not self.branch_writer_released


@dataclass(frozen=True, slots=True)
class WatcherPassReceipt:
    """One host-supplied expected opportunity/fire/read/action outcome fact."""

    source: WatchedSource
    schedule_generation: str
    expected_opportunity: str
    host_execution: HostExecutionState
    actual_fire_id: str | None
    outcome: WatcherPassOutcome
    observed_at: str
    evidence_digest: str
    runtime_binding: RuntimeBindingIdentity | None = None

    def __post_init__(self) -> None:
        try:
            _token(self.expected_opportunity, code="WATCH_PASS_INVALID")
            if self.actual_fire_id is not None:
                _token(self.actual_fire_id, code="WATCH_PASS_INVALID")
            parsed = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError, TurnRuntimePrimitiveError):
            raise WatchedSourceConflict("WATCH_PASS_INVALID") from None
        if (
            type(self.source) is not WatchedSource
            or type(self.schedule_generation) is not str
            or _FINGERPRINT_RE.fullmatch(self.schedule_generation) is None
            or type(self.host_execution) is not HostExecutionState
            or type(self.outcome) is not WatcherPassOutcome
            or parsed.tzinfo is None
            or type(self.evidence_digest) is not str
            or _FINGERPRINT_RE.fullmatch(self.evidence_digest) is None
            or (
                self.runtime_binding is not None
                and type(self.runtime_binding) is not RuntimeBindingIdentity
            )
            or (
                self.runtime_binding is not None
                and self.runtime_binding != self.source.runtime_binding
            )
            or (
                (self.host_execution is HostExecutionState.NOT_INVOKED)
                != (self.outcome is WatcherPassOutcome.HOST_NOT_INVOKED)
            )
            or (
                (self.actual_fire_id is None)
                != (
                    self.outcome
                    in {
                        WatcherPassOutcome.HOST_NOT_INVOKED,
                        WatcherPassOutcome.EXPECTED_OPPORTUNITY_NO_FIRE,
                    }
                )
            )
            or (
                self.outcome
                in {
                    WatcherPassOutcome.EXACT_WAKE_TARGET_ACKNOWLEDGED,
                    WatcherPassOutcome.EXACT_WAKE_RECORDED_ACK_ABSENT,
                }
                and self.runtime_binding is None
            )
            or (
                self.outcome is WatcherPassOutcome.WATCH_STOP_FAILED
                and not self.source.terminal
            )
        ):
            raise WatchedSourceConflict("WATCH_PASS_INVALID")


@dataclass(frozen=True, slots=True)
class WatcherProjection:
    """Deterministic health/action evidence with fixed zero mutation authority.

    ``active_sibling_sources`` counts only supplied source projections.  Aggregate
    watcher-resource identity and host liveness are deliberately not represented.
    """

    source: WatchedSource
    state: WatcherHealth
    reason: str
    schedule_generation: str
    latest_outcome: WatcherPassOutcome | None
    missed_opportunities: int
    last_fire_opportunity: str | None
    last_successful_opportunity: str | None
    action: WatcherAction
    watch_stop_failed: bool
    active_sibling_sources: int
    canonical_terminal_applied: bool
    authority_effect: str = "NONE"
    native_wake_authorized: bool = False
    job_write_authorized: bool = False
    attempt_write_authorized: bool = False
    worker_write_authorized: bool = False
    cadence_write_authorized: bool = False
    task_creation_authorized: bool = False
    retry_authorized: bool = False
    release_origination_authorized: bool = False
    merge_authorized: bool = False

    def __post_init__(self) -> None:
        authority = (
            self.native_wake_authorized,
            self.job_write_authorized,
            self.attempt_write_authorized,
            self.worker_write_authorized,
            self.cadence_write_authorized,
            self.task_creation_authorized,
            self.retry_authorized,
            self.release_origination_authorized,
            self.merge_authorized,
        )
        if (
            type(self.source) is not WatchedSource
            or type(self.state) is not WatcherHealth
            or type(self.reason) is not str
            or not self.reason
            or type(self.schedule_generation) is not str
            or _FINGERPRINT_RE.fullmatch(self.schedule_generation) is None
            or (
                self.latest_outcome is not None
                and type(self.latest_outcome) is not WatcherPassOutcome
            )
            or type(self.missed_opportunities) is not int
            or self.missed_opportunities < 0
            or type(self.action) is not WatcherAction
            or type(self.watch_stop_failed) is not bool
            or type(self.active_sibling_sources) is not int
            or self.active_sibling_sources < 0
            or type(self.canonical_terminal_applied) is not bool
            or self.authority_effect != "NONE"
            or any(type(value) is not bool or value for value in authority)
        ):
            raise WatchedSourceConflict("WATCH_PROJECTION_INVALID")


_MISSED_OUTCOMES = frozenset(
    {
        WatcherPassOutcome.HOST_NOT_INVOKED,
        WatcherPassOutcome.EXPECTED_OPPORTUNITY_NO_FIRE,
        WatcherPassOutcome.CARRIER_READ_FAILED,
        WatcherPassOutcome.EXACT_WAKE_RECORDED_ACK_ABSENT,
        WatcherPassOutcome.WAKE_EFFECT_UNKNOWN,
        WatcherPassOutcome.SAME_CARRIER_ACTION_FAILED,
        WatcherPassOutcome.EXACT_WAKE_FAILED,
        WatcherPassOutcome.EXACT_TARGET_UNAVAILABLE,
    }
)
_SUCCESSFUL_OUTCOMES = frozenset(
    {
        WatcherPassOutcome.NO_MATERIAL_CHANGE,
        WatcherPassOutcome.SAME_CARRIER_ACTION_COMPLETED,
        WatcherPassOutcome.EXACT_WAKE_TARGET_ACKNOWLEDGED,
        WatcherPassOutcome.ACTIVE_WAITER_SUPPRESSED,
    }
)


def normalize_watched_sources(
    sources: Sequence[WatchedSource],
) -> tuple[WatchedSource, ...]:
    """Deduplicate exact facts and refuse revision or active-writer conflicts."""

    if isinstance(sources, (str, bytes)) or not isinstance(sources, Sequence):
        raise WatchedSourceConflict("WATCH_SOURCE_INVALID")
    if len(sources) > 256:
        raise WatchedSourceConflict("WATCH_SOURCE_INVALID")
    normalized: list[WatchedSource] = []
    by_registration: dict[tuple[object, ...], WatchedSource] = {}
    for source in sources:
        if type(source) is not WatchedSource:
            raise WatchedSourceConflict("WATCH_SOURCE_INVALID")
        prior = by_registration.get(source.registration_identity)
        if prior is not None:
            if prior == source:
                continue
            if prior.source_revision != source.source_revision:
                raise WatchedSourceConflict("WATCH_SOURCE_REVISION_CONFLICT")
            raise WatchedSourceConflict("WATCH_SOURCE_CONFLICT")
        by_registration[source.registration_identity] = source
        normalized.append(source)

    active_writers: dict[tuple[str, int, str], WatchedSource] = {}
    for source in normalized:
        if not source.holds_branch_writer:
            continue
        prior = active_writers.get(source.git_writer_identity)
        if prior is not None and prior.registration_identity != source.registration_identity:
            raise WatchedSourceConflict("ACTIVE_BRANCH_WRITER_CONFLICT")
        active_writers[source.git_writer_identity] = source
    return tuple(normalized)


def _normalize_pass_receipts(
    source: WatchedSource,
    receipts: Sequence[WatcherPassReceipt],
) -> tuple[WatcherPassReceipt, ...]:
    if isinstance(receipts, (str, bytes)) or not isinstance(receipts, Sequence):
        raise WatchedSourceConflict("WATCH_PASS_INVALID")
    if len(receipts) > 4096:
        raise WatchedSourceConflict("WATCH_PASS_INVALID")
    by_opportunity: dict[tuple[str, str], WatcherPassReceipt] = {}
    for receipt in receipts:
        if type(receipt) is not WatcherPassReceipt:
            raise WatchedSourceConflict("WATCH_PASS_INVALID")
        if receipt.source != source:
            raise WatchedSourceConflict("WATCH_PASS_SOURCE_MISMATCH")
        key = (receipt.schedule_generation, receipt.expected_opportunity)
        prior = by_opportunity.get(key)
        if prior is not None and prior != receipt:
            raise WatchedSourceConflict("WATCH_PASS_CONFLICT")
        by_opportunity[key] = receipt
    return tuple(
        sorted(
            by_opportunity.values(),
            key=lambda value: (
                datetime.fromisoformat(value.observed_at.replace("Z", "+00:00")),
                value.schedule_generation,
                value.expected_opportunity,
                value.evidence_digest,
            ),
        )
    )


def project_watched_source(
    source: WatchedSource,
    *,
    schedule_generation: str,
    receipts: Sequence[WatcherPassReceipt],
    aggregate_sources: Sequence[WatchedSource] = (),
    current_sol_can_act: bool = False,
    sidecar: bool = False,
    exact_runtime_binding_available: bool = False,
    runtime_binding_reconciliation_required: bool = False,
    canonical_terminal_applied: bool = False,
) -> WatcherProjection:
    """Project current/degraded/terminal evidence from closed host facts only."""

    if (
        type(source) is not WatchedSource
        or type(schedule_generation) is not str
        or _FINGERPRINT_RE.fullmatch(schedule_generation) is None
        or type(current_sol_can_act) is not bool
        or type(sidecar) is not bool
        or (current_sol_can_act and sidecar)
        or type(exact_runtime_binding_available) is not bool
        or type(runtime_binding_reconciliation_required) is not bool
        or (
            exact_runtime_binding_available
            and runtime_binding_reconciliation_required
        )
        or type(canonical_terminal_applied) is not bool
    ):
        raise WatchedSourceConflict("WATCH_PROJECTION_INVALID")

    observed = _normalize_pass_receipts(source, receipts)
    current = tuple(
        receipt
        for receipt in observed
        if receipt.schedule_generation == schedule_generation
    )
    normalized_aggregate = normalize_watched_sources(aggregate_sources)
    aggregate = normalize_watched_sources((source, *normalized_aggregate))
    active_siblings = sum(
        candidate != source and candidate.semantically_active
        for candidate in aggregate
    )
    latest = current[-1] if current else None

    if source.terminal:
        watch_stop_failed = any(
            receipt.outcome is WatcherPassOutcome.WATCH_STOP_FAILED
            for receipt in current
        )
        return WatcherProjection(
            source=source,
            state=WatcherHealth.TERMINAL_SUPPRESSED,
            reason=(
                WatcherPassOutcome.WATCH_STOP_FAILED.value
                if watch_stop_failed
                else "SOURCE_TERMINAL_SUPPRESSED"
            ),
            schedule_generation=schedule_generation,
            latest_outcome=latest.outcome if latest is not None else None,
            missed_opportunities=0,
            last_fire_opportunity=(
                next(
                    (
                        receipt.expected_opportunity
                        for receipt in reversed(current)
                        if receipt.actual_fire_id is not None
                    ),
                    None,
                )
            ),
            last_successful_opportunity=None,
            action=WatcherAction.SUPPRESS_TERMINAL_SOURCE,
            watch_stop_failed=watch_stop_failed,
            active_sibling_sources=active_siblings,
            canonical_terminal_applied=canonical_terminal_applied,
        )

    missed = sum(receipt.outcome in _MISSED_OUTCOMES for receipt in current)
    state = (
        WatcherHealth.WATCH_DEGRADED
        if missed >= 2
        else WatcherHealth.CURRENT
    )
    action = WatcherAction.NO_ACTION
    reason = latest.outcome.value if latest is not None else WatcherHealth.CURRENT.value
    if latest is not None and latest.outcome is WatcherPassOutcome.ACTIONABLE_EVENT_DETECTED:
        if current_sol_can_act:
            action = WatcherAction.SAME_CARRIER_ACTION
            reason = action.value
        elif sidecar and runtime_binding_reconciliation_required:
            action = (
                WatcherAction.SESSION_LOST_RUNTIME_BINDING_RECONCILIATION_REQUIRED
            )
            reason = action.value
        elif sidecar and exact_runtime_binding_available and source.runtime_binding is not None:
            action = WatcherAction.EXACT_RUNTIME_BINDING_WAKE
            reason = action.value
        elif sidecar:
            action = WatcherAction.EXACT_TARGET_UNAVAILABLE
            reason = action.value
    elif (
        canonical_terminal_applied
        and source.disposition
        is SourceDisposition.REMOTE_COMPLETE_AWAITING_STOP
        and state is WatcherHealth.CURRENT
    ):
        reason = SourceDisposition.REMOTE_COMPLETE_AWAITING_STOP.value

    return WatcherProjection(
        source=source,
        state=state,
        reason=reason,
        schedule_generation=schedule_generation,
        latest_outcome=latest.outcome if latest is not None else None,
        missed_opportunities=missed,
        last_fire_opportunity=next(
            (
                receipt.expected_opportunity
                for receipt in reversed(current)
                if receipt.actual_fire_id is not None
            ),
            None,
        ),
        last_successful_opportunity=next(
            (
                receipt.expected_opportunity
                for receipt in reversed(current)
                if receipt.outcome in _SUCCESSFUL_OUTCOMES
            ),
            None,
        ),
        action=action,
        watch_stop_failed=False,
        active_sibling_sources=active_siblings,
        canonical_terminal_applied=canonical_terminal_applied,
    )


@dataclass(frozen=True, slots=True)
class ActiveWaiterKey:
    """Exact non-authoritative identity of one active Relay wait call."""

    parent_fingerprint: str
    operation_key: str
    session_ref_canonical: str
    target_seat: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.parent_fingerprint, str)
            or _FINGERPRINT_RE.fullmatch(self.parent_fingerprint) is None
        ):
            raise TurnRuntimePrimitiveError("WAITER_KEY_INVALID")
        _token(self.operation_key, code="WAITER_KEY_INVALID")
        _token(self.target_seat, code="WAITER_KEY_INVALID")
        if (
            not isinstance(self.session_ref_canonical, str)
            or _SESSION_REF_RE.fullmatch(self.session_ref_canonical) is None
        ):
            raise TurnRuntimePrimitiveError("WAITER_KEY_INVALID")

    @classmethod
    def from_parent(
        cls,
        parent: Mapping[str, Any],
        *,
        target_seat: str,
    ) -> "ActiveWaiterKey":
        if not isinstance(parent, Mapping):
            raise TurnRuntimePrimitiveError("WAITER_KEY_INVALID")
        return cls(
            parent_fingerprint=parent.get("fingerprint"),
            operation_key=parent.get("operation_key"),
            session_ref_canonical=parent.get("session_ref"),
            target_seat=target_seat,
        )


@dataclass(frozen=True, slots=True)
class ActiveWaiterRegistration:
    key: ActiveWaiterKey
    token: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, ActiveWaiterKey):
            raise TurnRuntimePrimitiveError("WAITER_REGISTRATION_INVALID")
        if (
            not isinstance(self.token, str)
            or _WAITER_TOKEN_RE.fullmatch(self.token) is None
        ):
            raise TurnRuntimePrimitiveError("WAITER_REGISTRATION_INVALID")


class ActiveWaiterRegistry:
    """One process-local exact waiter set with compare-and-delete removal."""

    def __init__(self, *, token_factory: Callable[[], str] | None = None) -> None:
        self._tokens: dict[ActiveWaiterKey, str] = {}
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self._generation = 0

    def register(self, key: ActiveWaiterKey) -> ActiveWaiterRegistration:
        if not isinstance(key, ActiveWaiterKey):
            raise TurnRuntimePrimitiveError("WAITER_KEY_INVALID")
        if key in self._tokens:
            raise ActiveWaiterConflict()
        try:
            material = self._token_factory()
        except Exception:
            raise TurnRuntimePrimitiveError("WAITER_TOKEN_UNAVAILABLE") from None
        if (
            type(material) is not str
            or _WAITER_TOKEN_RE.fullmatch(material) is None
        ):
            raise TurnRuntimePrimitiveError("WAITER_REGISTRATION_INVALID")
        generation = self._generation + 1
        suffix = f"-{generation:x}"
        if len(suffix) >= 256:
            raise TurnRuntimePrimitiveError("WAITER_TOKEN_UNAVAILABLE")
        # The monotonic suffix makes each process-lifetime registration unique
        # even under a deterministic or colliding entropy source.  It avoids
        # retaining an unbounded graveyard of old tokens while making stale
        # compare-delete registrations permanently inert.
        token = f"{material[: 256 - len(suffix)]}{suffix}"
        registration = ActiveWaiterRegistration(key=key, token=token)
        if token in self._tokens.values():
            raise TurnRuntimePrimitiveError("WAITER_TOKEN_CONFLICT")
        self._generation = generation
        self._tokens[key] = token
        return registration

    def is_active(self, key: ActiveWaiterKey) -> bool:
        if not isinstance(key, ActiveWaiterKey):
            raise TurnRuntimePrimitiveError("WAITER_KEY_INVALID")
        return key in self._tokens

    def unregister(self, registration: ActiveWaiterRegistration) -> bool:
        if not isinstance(registration, ActiveWaiterRegistration):
            raise TurnRuntimePrimitiveError("WAITER_REGISTRATION_INVALID")
        current = self._tokens.get(registration.key)
        if current != registration.token:
            return False
        del self._tokens[registration.key]
        return True

    @property
    def active_count(self) -> int:
        return len(self._tokens)

    @asynccontextmanager
    async def hold(self, key: ActiveWaiterKey):
        registration = self.register(key)
        try:
            yield registration
        finally:
            self.unregister(registration)


def _is_async_callable(value: object) -> bool:
    """Return whether calling ``value`` starts in this event loop asynchronously."""

    if inspect.iscoroutinefunction(value):
        return True
    return inspect.iscoroutinefunction(getattr(value, "__call__", None))


class AsyncCandidateCollector(Generic[_T]):
    """Acquire and collect one bounded immutable candidate tuple asynchronously.

    The source itself must be an async callable and must return one async
    iterator. Source acquisition and iteration share one absolute collection
    timeout. No synchronous callback, iterable fallback, thread, or executor
    escape exists. Only one collection may be in flight; every exit path closes
    an acquired iterator when it exposes ``aclose`` and releases the in-flight
    guard so a later healthy pass can recover.
    """

    def __init__(
        self,
        *,
        source: Callable[[], Awaitable[AsyncIterator[_T]]],
        max_candidates: int,
        timeout_seconds: float,
        cleanup_timeout_seconds: float = 1.0,
    ) -> None:
        if not _is_async_callable(source):
            raise TypeError("source must be an async callable")
        if (
            isinstance(max_candidates, bool)
            or not isinstance(max_candidates, int)
            or not 1 <= max_candidates <= 256
        ):
            raise ValueError("max_candidates must be an integer between 1 and 256")
        for value, name in (
            (timeout_seconds, "timeout_seconds"),
            (cleanup_timeout_seconds, "cleanup_timeout_seconds"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0
            ):
                raise ValueError(f"{name} must be finite and positive")
        self._source = source
        self.max_candidates = max_candidates
        self.timeout_seconds = float(timeout_seconds)
        self.cleanup_timeout_seconds = float(cleanup_timeout_seconds)
        self._inflight = False

    @property
    def inflight(self) -> bool:
        return self._inflight

    async def _close(self, iterator: object) -> None:
        close = getattr(iterator, "aclose", None)
        if not callable(close):
            return
        try:
            result = close()
        except Exception:
            return
        if not hasattr(result, "__await__"):
            return
        task = asyncio.create_task(result)
        try:
            await asyncio.wait_for(task, timeout=self.cleanup_timeout_seconds)
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        except Exception:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def collect(self) -> tuple[_T, ...]:
        if self._inflight:
            raise CandidateCollectionBusy()
        self._inflight = True
        iterator: object | None = None
        try:
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    try:
                        iterator = await self._source()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        raise CandidateCollectionUnavailable() from exc

                    if (
                        not hasattr(iterator, "__aiter__")
                        or not hasattr(iterator, "__anext__")
                    ):
                        raise CandidateCollectionUnavailable()

                    values: list[_T] = []
                    try:
                        async for value in iterator:  # type: ignore[union-attr]
                            values.append(value)
                            if len(values) > self.max_candidates:
                                raise CandidateCollectionOverflow()
                    except (CandidateCollectionOverflow, asyncio.CancelledError):
                        raise
                    except Exception as exc:
                        raise CandidateCollectionUnavailable() from exc
                    return tuple(values)
            except (CandidateCollectionOverflow, CandidateCollectionUnavailable):
                raise
            except TimeoutError as exc:
                raise CandidateCollectionTimeout() from exc
        finally:
            try:
                if iterator is not None:
                    await self._close(iterator)
            finally:
                self._inflight = False


__all__ = [
    "ActiveWaiterConflict",
    "ActiveWaiterKey",
    "ActiveWaiterRegistration",
    "ActiveWaiterRegistry",
    "AsyncCandidateCollector",
    "CandidateCollectionBusy",
    "CandidateCollectionOverflow",
    "CandidateCollectionTimeout",
    "CandidateCollectionUnavailable",
    "ExactWatcherCarrier",
    "HostExecutionState",
    "RuntimeBindingIdentity",
    "SourceDisposition",
    "TurnRuntimePrimitiveError",
    "WatchedResponsibility",
    "WatchedSource",
    "WatchedSourceConflict",
    "WatcherAction",
    "WatcherHealth",
    "WatcherPassOutcome",
    "WatcherPassReceipt",
    "WatcherProjection",
    "WatcherSide",
    "normalize_watched_sources",
    "project_watched_source",
]
