"""Read-only Hermes occurrence -> proposed canonical Wake obligation (H24-03).

The injected, host-qualified adapter authenticates native observations and reads
the original Work/Runtime/Wake owners. A hook payload is never source authority.
This module has no application IO, clock reads, model, scheduler, ledger,
dispatch or retry owner. ZoneInfo only validates the supplied profile zone.
Concurrent callers may render the same proposal; only incumbent atomic Wake
admission/dispatch can guarantee at-most-one original effect submission.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import re
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from control_plane.wake_events import (
    JOB_ID_RE, RUNTIME_JOB_REF_RE, SourceKind, WakeObligation,
    WakeObligationError, canonical_json_bytes, mint_obligation, parse_obligation,
)

HERMES_PIN = "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
BUILD_BASE = "b54cb10e4abdd3766c62d4088f6a576ecfe80437"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_EXECUTION = re.compile(r"[0-9a-f]{32}\Z")
_HOOKS = frozenset({"gateway:startup", "session:start", "session:end",
                    "session:reset", "agent:start", "agent:step", "agent:end"})
_SOURCES = frozenset({SourceKind.AGENT_DIALOGUE_ATTENTION,
                      SourceKind.EXECUTIVE_INBOX_ATTENTION,
                      SourceKind.EXECUTIVE_RUNTIME_EVENT})


class NativeKind(str, Enum):
    HOOK = "hermes_hook"
    CRON = "hermes_cron"
    SLACK_KEYWORD = "slack_keyword"  # Representable only to refuse it.


class ObservationMode(str, Enum):
    EVENT = "event"
    SOURCE_SNAPSHOT = "source_snapshot"


class Eligibility(str, Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNKNOWN = "unknown"


class EffectState(str, Enum):
    ABSENT = "absent"  # Positive, current owner read; never a default on error.
    REQUESTED = "requested"
    POSSIBLE_SEND = "possible_send"
    UNKNOWN = "unknown"
    DELIVERED = "delivered"
    RESOLVED = "resolved"


class ProjectionStatus(str, Enum):
    PROPOSED = "proposed"
    NO_CHANGE = "no_change"
    INELIGIBLE = "ineligible"
    REJECTED = "rejected"
    RECONCILE_REQUIRED = "reconcile_required"


@dataclass(frozen=True)
class RoutineRoute:
    routine_id: str
    native_schedule: str | None
    wake_source: SourceKind | None
    supported: bool = True


# Inert mapping only. No catalog read, native registration, prompt or install.
ROUTINE_ROUTES = (
    RoutineRoute("slack-secretary-ping-scan", "12,42 * * * *", SourceKind.AGENT_DIALOGUE_ATTENTION),
    RoutineRoute("overnight-three-room-sweep", "34 * * * *", SourceKind.AGENT_DIALOGUE_ATTENTION),
    RoutineRoute("blocked-hold-listener", None, None, False),
    RoutineRoute("chatgpt-browser-session-watcher", "5,35 * * * *", SourceKind.AGENT_DIALOGUE_ATTENTION),
    RoutineRoute("codex-usage-reset-watcher", "30m", None),
    RoutineRoute("m2studio-browser-tab-sweep", "40 2-23/3 * * *", None),
    RoutineRoute("codex-continuity-audit", "20 */2 * * *", SourceKind.AGENT_DIALOGUE_ATTENTION),
)


@dataclass(frozen=True)
class NativeBinding:
    """Actual role/session/source binding supplied by the qualified host, not text."""
    profile_id: str
    role: str
    original_root: str
    session_id: str
    session_generation: int
    source_revision: str  # Exact immutable Mastermind source, never a branch name.
    profile_timezone: str
    hermes_revision: str = HERMES_PIN


@dataclass(frozen=True)
class NativeOccurrence:
    """Original native identity; recovery must retain every field.

    Cron occurrence_id is executions.id, paired with the original native job ID
    and scheduled_instant. Hooks need the native owner's retained event ID and
    sequence: HookRegistry's event name/message alone cannot supply those facts.
    """
    kind: NativeKind
    occurrence_id: str
    origin: NativeBinding
    event_name: str
    event_sequence: int
    occurred_at: str
    expires_at: str
    routine_id: str | None = None
    cron_job_id: str | None = None
    scheduled_instant: str | None = None


@dataclass(frozen=True)
class NativeObservation:
    mode: ObservationMode
    binding: NativeBinding  # Current observing session, distinct from origin.
    occurrence: NativeOccurrence
    observed_at: str


@dataclass(frozen=True)
class SemanticEvidence:
    """Optional prior observation from the existing owner; not a send lock."""
    occurrence_key: tuple[str, ...]
    source_identity: tuple[str, str, str]
    fingerprint: str


@dataclass(frozen=True)
class EffectEvidence:
    """Current incumbent Wake read for this exact canonical obligation.

    Missing/unreadable evidence is NOT ABSENT. An existing effect retains its
    original occurrence and command even when a later cron fire observes it.
    """
    obligation_id: str
    state: EffectState
    original_occurrence: NativeOccurrence | None
    command_id: str | None


@dataclass(frozen=True)
class CurrentAttention:
    """One coherent read through the existing native/Work/Runtime/Wake owners.

    Native and canonical source sequences are separate streams. Watermarks may
    advance beyond the original event; neither may manufacture its identity.
    """
    binding: NativeBinding
    retained_occurrence: NativeOccurrence
    native_watermark: int
    source_event_sequence: int
    source_watermark: int
    read_at: str
    expires_at: str
    role_qualified: Eligibility
    work_eligibility: Eligibility
    runtime_eligibility: Eligibility
    attention: WakeObligation | None
    effect: EffectEvidence | None
    previous: SemanticEvidence | None = None
    native_execution_status: str | None = None


class AuthenticatedAttentionSource(Protocol):
    """Trusted injected adapter; no implementation or credential path ships here.

    Authenticate using actual native session/role custody and retained source
    records. Never accept payload flags such as authenticated/owner_verified.
    Both methods must be bounded reads and must not instantiate cognition.
    """
    def authenticate(self, notice: object) -> NativeObservation | None: ...
    def read_current(self, observation: NativeObservation) -> CurrentAttention: ...


@dataclass(frozen=True)
class AttentionProjection:
    status: ProjectionStatus
    reason: str
    proposed_obligation: WakeObligation | None = None
    observed_occurrence: NativeOccurrence | None = None
    evidence: SemanticEvidence | None = None
    original_effect: EffectEvidence | None = None

    @property
    def new_cognition(self) -> bool:
        return False

    @property
    def new_submission(self) -> bool:
        return False


class _Refusal(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise _Refusal(code)


def _token(value: object) -> bool:
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def _positive(value: object) -> bool:
    return type(value) is int and value > 0


def _instant(value: object) -> datetime:
    _require(isinstance(value, str) and len(value) <= 40, "TIMESTAMP_INVALID")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _Refusal("TIMESTAMP_INVALID") from None
    _require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
             "TIMESTAMP_AMBIGUOUS")
    return stamp.astimezone(timezone.utc)


def _binding(value: NativeBinding) -> None:
    _require(type(value) is NativeBinding, "BINDING_INVALID")
    _require(_token(value.profile_id) and value.role in {"mmsecretary", "mmmeta"}
             and isinstance(value.original_root, str)
             and JOB_ID_RE.fullmatch(value.original_root) is not None
             and _positive(value.session_generation), "BINDING_INVALID")
    try:
        _require(str(UUID(value.session_id)) == value.session_id, "SESSION_INVALID")
        ZoneInfo(value.profile_timezone)
    except (ValueError, TypeError, AttributeError, ZoneInfoNotFoundError):
        raise _Refusal("BINDING_INVALID") from None
    _require(isinstance(value.source_revision, str)
             and _SHA.fullmatch(value.source_revision) is not None
             and value.hermes_revision == HERMES_PIN, "SOURCE_PIN_INVALID")


def _scope(binding: NativeBinding) -> tuple[str, str, str]:
    return binding.profile_id, binding.role, binding.original_root


def occurrence_key(value: NativeOccurrence) -> tuple[str, ...]:
    """Native canonical slot/event identity, not a new lifecycle ID.

    Execution ID is retained separately even for the same cron slot. UTC
    normalization matches pinned cron.occurrences.scheduled_instant semantics;
    no local wall-clock recurrence calculation occurs in this boundary.
    """
    if value.kind is NativeKind.CRON:
        return (value.kind.value, value.origin.profile_id, value.cron_job_id,
                _instant(value.scheduled_instant).isoformat())
    return (value.kind.value, value.origin.profile_id, value.origin.original_root,
            value.origin.session_id, str(value.origin.session_generation),
            value.occurrence_id, str(value.event_sequence))


def _occurrence(value: NativeOccurrence) -> None:
    _require(type(value) is NativeOccurrence, "OCCURRENCE_INVALID")
    _binding(value.origin)
    _require(type(value.kind) is NativeKind, "NATIVE_KIND_INVALID")
    _require(value.kind is not NativeKind.SLACK_KEYWORD, "SLACK_KEYWORD_UNSUPPORTED")
    _require(_token(value.occurrence_id) and _positive(value.event_sequence),
             "OCCURRENCE_INVALID")
    _require(_instant(value.occurred_at) < _instant(value.expires_at), "OCCURRENCE_WINDOW_INVALID")
    if value.routine_id is not None:
        routes = [r for r in ROUTINE_ROUTES if r.routine_id == value.routine_id]
        _require(len(routes) == 1, "ROUTINE_UNSUPPORTED")
        _require(routes[0].supported, "SLACK_KEYWORD_UNSUPPORTED")
    if value.kind is NativeKind.HOOK:
        _require(value.event_name in _HOOKS and value.cron_job_id is None
                 and value.scheduled_instant is None, "HOOK_INVALID")
    else:
        _require(value.event_name == "cron:occurrence" and value.routine_id is not None
                 and _token(value.cron_job_id)
                 and _EXECUTION.fullmatch(value.occurrence_id) is not None,
                 "CRON_IDENTITY_INVALID")
        _instant(value.scheduled_instant)


def _same_occurrence(left: NativeOccurrence, right: NativeOccurrence) -> bool:
    # Equivalent offset spellings do not change an original native instant.
    return (left.kind, left.occurrence_id, left.origin, left.event_name,
            left.event_sequence, _instant(left.occurred_at), _instant(left.expires_at),
            left.routine_id, occurrence_key(left)) == (
                right.kind, right.occurrence_id, right.origin, right.event_name,
                right.event_sequence, _instant(right.occurred_at), _instant(right.expires_at),
                right.routine_id, occurrence_key(right))


def _effect(value: EffectEvidence | None, obligation: WakeObligation,
            binding: NativeBinding) -> EffectEvidence:
    _require(type(value) is EffectEvidence, "EFFECT_READ_UNAVAILABLE")
    _require(value.obligation_id == obligation.obligation_id
             and type(value.state) is EffectState, "EFFECT_IDENTITY_MISMATCH")
    if value.state is EffectState.ABSENT:
        _require(value.original_occurrence is None and value.command_id is None,
                 "EFFECT_ABSENCE_CONTRADICTION")
    else:
        _occurrence(value.original_occurrence)
        _require(_scope(value.original_occurrence.origin) == _scope(binding)
                 and _token(value.command_id)
                 and (value.command_id.startswith(obligation.obligation_id + ":")
                      or (value.state is EffectState.REQUESTED
                          and value.command_id == obligation.obligation_id)),
                 "ORIGINAL_EFFECT_MISMATCH")
    return value


def _semantic(obligation: WakeObligation, occurrence: NativeOccurrence) -> SemanticEvidence:
    # Evidence/display/observation times, reconnects and current session generation
    # cannot turn the same unresolved source into another attention request.
    meaning = obligation.to_dict()
    for key in ("source_created_at", "emitted_at", "evidence_refs"):
        meaning.pop(key)
    return SemanticEvidence(
        occurrence_key(occurrence),
        (obligation.source_kind.value, obligation.source_ref, obligation.wake_kind.value),
        hashlib.sha256(canonical_json_bytes(meaning)).hexdigest(),
    )


def project_native_attention(
    notice: object, *, source: AuthenticatedAttentionSource,
    binding: NativeBinding, now: datetime, max_snapshot_age_seconds: int = 300,
) -> AttentionProjection:
    """Authenticate, read once, validate, and return at most one inert proposal.

    No adapter is constructed here. Missing authentication, currentness or effect
    evidence fails closed. A new projector/reconnect never means effect absence.
    The original Wake owner must fresh-read again and atomically admit any later
    effect; this read-only result is neither authority nor a delivery receipt.
    """
    observed = None
    try:
        _binding(binding)
        _require(type(now) is datetime and now.tzinfo is not None
                 and now.utcoffset() is not None, "CLOCK_INVALID")
        _require(_positive(max_snapshot_age_seconds), "FRESHNESS_POLICY_INVALID")
        clock = now.astimezone(timezone.utc)
        try:
            observed = source.authenticate(notice)
        except Exception:
            return AttentionProjection(ProjectionStatus.REJECTED, "AUTH_SOURCE_UNAVAILABLE")
        _require(type(observed) is NativeObservation, "UNAUTHENTICATED_SOURCE")
        _require(type(observed.mode) is ObservationMode, "OBSERVATION_MODE_INVALID")
        _binding(observed.binding)
        _require(observed.binding == binding, "FOREIGN_OR_STALE_BINDING")
        event = observed.occurrence
        _occurrence(event)
        _require(_scope(event.origin) == _scope(binding), "FOREIGN_ORIGINAL_ROOT")
        if observed.mode is ObservationMode.EVENT:
            _require(event.origin == binding, "STALE_SESSION_GENERATION")
        else:
            _require(event.origin.session_generation <= binding.session_generation,
                     "FUTURE_SESSION_GENERATION")
        created, expires, seen = map(_instant, (event.occurred_at, event.expires_at, observed.observed_at))
        _require(created <= seen <= clock < expires, "OCCURRENCE_STALE_OR_FUTURE")
        _require((clock - seen).total_seconds() <= max_snapshot_age_seconds,
                 "OBSERVATION_STALE")
        try:
            current = source.read_current(observed)
        except Exception:
            return AttentionProjection(ProjectionStatus.REJECTED, "CURRENT_SOURCE_UNAVAILABLE",
                                       observed_occurrence=event)
        _require(type(current) is CurrentAttention, "CURRENT_SOURCE_INVALID")
        _binding(current.binding)
        _require(current.binding == binding, "SOURCE_CHANGED_DURING_READ")
        _occurrence(current.retained_occurrence)
        _require(_same_occurrence(event, current.retained_occurrence), "ORIGINAL_OCCURRENCE_MISMATCH")
        _require(_positive(current.native_watermark)
                 and current.native_watermark >= event.event_sequence
                 and _positive(current.source_event_sequence)
                 and _positive(current.source_watermark)
                 and current.source_watermark >= current.source_event_sequence,
                 "EVENT_SEQUENCE_UNVERIFIED")
        read_at, valid_until = _instant(current.read_at), _instant(current.expires_at)
        _require(seen <= read_at <= clock < valid_until
                 and (clock - read_at).total_seconds() <= max_snapshot_age_seconds
                 and (valid_until - read_at).total_seconds() <= max_snapshot_age_seconds,
                 "CURRENT_SOURCE_STALE_OR_FUTURE")
        states = (current.role_qualified, current.work_eligibility, current.runtime_eligibility)
        _require(all(type(s) is Eligibility for s in states), "ELIGIBILITY_INVALID")
        _require(Eligibility.UNKNOWN not in states, "ELIGIBILITY_UNAVAILABLE")
        if event.kind is NativeKind.CRON:
            _require(current.native_execution_status in {"claimed", "running", "completed", "failed", "unknown"},
                     "CRON_EXECUTION_UNVERIFIED")
            if current.native_execution_status == "unknown":
                return AttentionProjection(ProjectionStatus.RECONCILE_REQUIRED,
                                           "NATIVE_CRON_EFFECT_UNKNOWN", observed_occurrence=event)
        else:
            _require(current.native_execution_status is None, "HOOK_EXECUTION_CONTRADICTION")
        if current.attention is None:
            _require(current.effect is None, "ATTENTION_EFFECT_CONTRADICTION")
            return AttentionProjection(ProjectionStatus.INELIGIBLE, "NO_CANONICAL_ATTENTION",
                                       observed_occurrence=event)
        _require(type(current.attention) is WakeObligation, "ATTENTION_NOT_TYPED")
        # Incumbent parser re-mints and validates the complete closed schema.
        canonical = parse_obligation(current.attention.to_dict())
        _require(canonical.source_kind in _SOURCES, "ATTENTION_SOURCE_UNSUPPORTED")
        _require(canonical.root_job_id == binding.original_root, "ATTENTION_ROOT_MISMATCH")
        if canonical.source_kind is SourceKind.EXECUTIVE_RUNTIME_EVENT:
            match = RUNTIME_JOB_REF_RE.fullmatch(canonical.source_ref)
            _require(match is not None and int(match.group(2)) == current.source_event_sequence,
                     "CANONICAL_EVENT_SEQUENCE_MISMATCH")
        _require(canonical.source_created_at is not None
                 and _instant(canonical.source_created_at) <= read_at, "ATTENTION_TIME_INVALID")
        effect = _effect(current.effect, canonical, binding)
        evidence = _semantic(canonical, event)
        if effect.state in {EffectState.POSSIBLE_SEND, EffectState.UNKNOWN}:
            return AttentionProjection(ProjectionStatus.RECONCILE_REQUIRED, "ORIGINAL_EFFECT_UNKNOWN",
                                       observed_occurrence=event, evidence=evidence, original_effect=effect)
        if effect.state is not EffectState.ABSENT:
            return AttentionProjection(ProjectionStatus.NO_CHANGE, "ORIGINAL_EFFECT_ALREADY_ADMITTED",
                                       observed_occurrence=event, evidence=evidence, original_effect=effect)
        if Eligibility.INELIGIBLE in states:
            return AttentionProjection(ProjectionStatus.INELIGIBLE, "ATTENTION_NOT_CURRENTLY_ELIGIBLE",
                                       observed_occurrence=event)
        if event.routine_id is not None:
            route = next(r for r in ROUTINE_ROUTES if r.routine_id == event.routine_id)
            if route.wake_source is None:
                return AttentionProjection(ProjectionStatus.INELIGIBLE, "ROUTINE_HAS_NO_WAKE_SOURCE",
                                           observed_occurrence=event)
            _require(route.wake_source is canonical.source_kind, "ROUTINE_SOURCE_MISMATCH")
        prior = current.previous
        if prior is not None:
            _require(type(prior) is SemanticEvidence and isinstance(prior.fingerprint, str)
                     and _DIGEST.fullmatch(prior.fingerprint) is not None,
                     "PRIOR_EVIDENCE_INVALID")
            same_source = prior.source_identity == evidence.source_identity
            _require(not (same_source and prior.occurrence_key == evidence.occurrence_key
                          and prior.fingerprint != evidence.fingerprint), "OCCURRENCE_SOURCE_CONFLICT")
            if same_source and prior.fingerprint == evidence.fingerprint:
                return AttentionProjection(ProjectionStatus.NO_CHANGE, "SEMANTIC_SNAPSHOT_UNCHANGED",
                                           observed_occurrence=event, evidence=evidence)
        fields = canonical.to_dict()
        fields.pop("schema")
        fields.pop("obligation_id")
        fields["emitted_at"] = clock.isoformat()
        proposed = mint_obligation(**fields)
        parse_obligation(proposed.to_dict())
        return AttentionProjection(ProjectionStatus.PROPOSED, "OWNER_VERIFIED_ATTENTION",
                                   proposed, event, evidence)
    except _Refusal as exc:
        return AttentionProjection(ProjectionStatus.REJECTED, str(exc))
    except (WakeObligationError, ValueError, TypeError, AttributeError, OverflowError):
        # Never expose adapter exceptions, raw hook text or private source data.
        return AttentionProjection(ProjectionStatus.REJECTED, "SOURCE_SCHEMA_INVALID")
