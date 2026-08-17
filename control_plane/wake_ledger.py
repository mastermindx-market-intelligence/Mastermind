"""Wake event-ledger contract — existing Executive OS events, no new table.

Future persistence (PR-2) writes these rows into ``events`` with::

    aggregate_type = "wake"
    aggregate_id   = obligation_id

PR-1 constructs and parses the records.  It does not write SQLite.
"""
from __future__ import annotations

import dataclasses
import re
from enum import Enum
from typing import Mapping, Sequence

from control_plane.session_targets import (
    BINDING_ID_RE,
    REASONING_SURFACES,
    SESSION_ALIAS_RE,
    WakeRoute,
)
from control_plane.wake_events import (
    ISO_UTC_RE,
    SEATS,
    WAKE_ID_RE,
    SourceKind,
    WakeKind,
    WakeObligation,
    WakeObligationError,
    parse_obligation,
    utc_now_iso,
)


WAKE_AGGREGATE_TYPE = "wake"


class WakeLedgerError(ValueError):
    """A wake ledger record is malformed, incoherent, or causally illegal."""


class LedgerPhase(str, Enum):
    WAKE_REQUESTED = "WAKE_REQUESTED"
    DELIVERY_ATTEMPT = "DELIVERY_ATTEMPT"
    ACCEPTED = "ACCEPTED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    TARGET_ACKNOWLEDGED = "TARGET_ACKNOWLEDGED"
    SOURCE_RESOLVED = "SOURCE_RESOLVED"


class ObligationStatus(str, Enum):
    NOT_SEEN = "NOT_SEEN"
    PENDING_RETRYABLE = "PENDING_RETRYABLE"
    ATTEMPTED = "ATTEMPTED"
    ACCEPTED = "ACCEPTED"
    DELIVERED_UNACKNOWLEDGED = "DELIVERED_UNACKNOWLEDGED"
    TARGET_ACKNOWLEDGED = "TARGET_ACKNOWLEDGED"
    SOURCE_RESOLVED = "SOURCE_RESOLVED"


class AckMode(str, Enum):
    REASONING_SESSION = "reasoning_session"
    HUMAN_OPERATOR = "human_operator"


class SourceReadHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


class SourceResolutionCode(str, Enum):
    RUNTIME_REVIEW_ABSENT = "runtime_review_absent"
    INBOX_ATTENTION_ABSENT = "inbox_attention_absent"
    AGENTOS_ITEM_ABSENT = "agentos_item_absent"


SNAPSHOT_DIGEST_RE = re.compile(r"^[0-9a-f]{16,64}$")
OPERATOR_AUTHORITY_RECEIPT_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_RESOLUTION_CODE_BY_SOURCE = {
    SourceKind.EXECUTIVE_RUNTIME_EVENT: SourceResolutionCode.RUNTIME_REVIEW_ABSENT,
    SourceKind.EXECUTIVE_INBOX_ATTENTION: SourceResolutionCode.INBOX_ATTENTION_ABSENT,
}


ATTEMPT_PHASES = frozenset(
    {
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.ACCEPTED,
        LedgerPhase.DELIVERED,
        LedgerPhase.FAILED,
        LedgerPhase.TARGET_UNAVAILABLE,
    }
)
ATTEMPT_TERMINALS = frozenset(
    {
        LedgerPhase.DELIVERED,
        LedgerPhase.FAILED,
        LedgerPhase.TARGET_UNAVAILABLE,
    }
)
GLOBAL_PHASES = frozenset(
    {
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.TARGET_ACKNOWLEDGED,
        LedgerPhase.SOURCE_RESOLVED,
    }
)
TERMINAL_CLOSE = frozenset(
    {LedgerPhase.TARGET_ACKNOWLEDGED, LedgerPhase.SOURCE_RESOLVED}
)


@dataclasses.dataclass(frozen=True)
class DeliveryAttempt:
    """Exact durable delivery attempt.  Adapter receipts bind to this object."""

    obligation_id: str
    attempt_n: int
    attempt_command_id: str
    destination_digest: str
    route_digest: str
    binding_id: str
    binding_generation: int
    session_alias: str
    reasoning_surface: str
    wake_transport: str

    def matches_route(self, route: WakeRoute) -> bool:
        return (
            self.obligation_id == route.obligation_id
            and self.destination_digest == route.destination_digest
            and self.route_digest == route.route_digest
            and self.binding_id == route.binding_id
            and self.binding_generation == route.binding_generation
            and self.session_alias == route.session_alias
            and self.reasoning_surface == route.reasoning_surface
            and self.wake_transport == route.wake_transport
        )


@dataclasses.dataclass(frozen=True)
class TrustedAckContext:
    """Host/gateway-injected identity.  The model does not author these fields."""

    ack_mode: AckMode
    target_seat: str
    session_alias: str
    reasoning_surface: str
    binding_id: str | None = None
    acknowledged_at: str | None = None
    operator_authority_receipt: str | None = None


@dataclasses.dataclass(frozen=True)
class WakeAcknowledgement:
    obligation_id: str
    ack_mode: AckMode
    target_seat: str
    session_alias: str
    reasoning_surface: str
    binding_id: str | None
    acknowledged_at: str
    claimed_obligation_ids: tuple[str, ...]
    operator_authority_receipt: str | None = None


@dataclasses.dataclass(frozen=True)
class SourceResolution:
    obligation_id: str
    code: SourceResolutionCode
    health: SourceReadHealth
    source_present: bool
    source_kind: str
    source_ref: str
    snapshot_digest: str
    resolved_at: str
    evidence_refs: tuple[str, ...] = ()
    annotation: str = ""


@dataclasses.dataclass(frozen=True)
class WakeRetryPolicy:
    """Required shape before any automated transport may be armed.

    Numeric values are a PR-2 policy decision unless repository law already
    supplies them.  Job ``attempt_limit`` is not a wake-nudge bound.
    """

    max_delivery_attempts: int | None = None
    retry_cooldown_s: int | None = None
    accepted_ttl_s: int | None = None
    target_unavailable_backoff_s: int | None = None
    reenable_on_binding_rotation: bool = True
    armed: bool = False

    def __post_init__(self) -> None:
        if not self.armed:
            return
        for name in (
            "max_delivery_attempts",
            "retry_cooldown_s",
            "accepted_ttl_s",
            "target_unavailable_backoff_s",
        ):
            _strict_positive_int(getattr(self, name), name)


UNARMED_RETRY_POLICY = WakeRetryPolicy()


@dataclasses.dataclass(frozen=True)
class WakeLedgerRecord:
    command_id: str
    phase: LedgerPhase
    attempt_n: int | None = None
    route_digest: str | None = None
    destination_digest: str | None = None
    binding_id: str | None = None
    binding_generation: int | None = None
    session_alias: str | None = None
    reasoning_surface: str | None = None
    wake_transport: str | None = None
    native_handle: str | None = None
    ack: WakeAcknowledgement | None = None
    source_resolution: SourceResolution | None = None
    obligation: WakeObligation | None = None

    def matches_attempt(self, attempt: DeliveryAttempt) -> bool:
        return (
            self.attempt_n == attempt.attempt_n
            and self.route_digest == attempt.route_digest
            and self.destination_digest == attempt.destination_digest
            and self.binding_id == attempt.binding_id
            and self.binding_generation == attempt.binding_generation
            and self.session_alias == attempt.session_alias
            and self.reasoning_surface == attempt.reasoning_surface
            and self.wake_transport == attempt.wake_transport
        )


def ledger_command_id(
    obligation_id: str,
    phase: LedgerPhase | str,
    *,
    attempt_n: int | None = None,
) -> str:
    oid = _obligation_id(obligation_id)
    resolved = phase if isinstance(phase, LedgerPhase) else LedgerPhase(str(phase))
    if resolved is LedgerPhase.WAKE_REQUESTED:
        return oid
    if resolved is LedgerPhase.TARGET_ACKNOWLEDGED:
        return f"{oid}:ACK"
    if resolved is LedgerPhase.SOURCE_RESOLVED:
        return f"{oid}:RESOLVED"
    n = _strict_positive_int(attempt_n)
    if resolved is LedgerPhase.DELIVERY_ATTEMPT:
        return f"{oid}:A{n}"
    if resolved is LedgerPhase.ACCEPTED:
        return f"{oid}:A{n}:ACCEPTED"
    if resolved is LedgerPhase.DELIVERED:
        return f"{oid}:A{n}:DELIVERED"
    if resolved is LedgerPhase.FAILED:
        return f"{oid}:A{n}:FAILED"
    if resolved is LedgerPhase.TARGET_UNAVAILABLE:
        return f"{oid}:A{n}:UNAVAILABLE"
    raise WakeLedgerError(f"unsupported ledger phase {resolved}")


def make_delivery_attempt(obligation: WakeObligation, route: WakeRoute, *, attempt_n: int) -> DeliveryAttempt:
    n = _strict_positive_int(attempt_n)
    if route.obligation_id != obligation.obligation_id:
        raise WakeLedgerError("route obligation_id does not match the wake")
    return DeliveryAttempt(
        obligation_id=obligation.obligation_id,
        attempt_n=n,
        attempt_command_id=ledger_command_id(
            obligation.obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=n
        ),
        destination_digest=route.destination_digest,
        route_digest=route.route_digest,
        binding_id=route.binding_id,
        binding_generation=route.binding_generation,
        session_alias=route.session_alias,
        reasoning_surface=route.reasoning_surface,
        wake_transport=route.wake_transport,
    )


def requested_record(obligation: WakeObligation) -> WakeLedgerRecord:
    parsed = parse_obligation(obligation.to_dict())
    return parse_ledger_record(
        WakeLedgerRecord(
            command_id=ledger_command_id(
                parsed.obligation_id, LedgerPhase.WAKE_REQUESTED
            ),
            phase=LedgerPhase.WAKE_REQUESTED,
            obligation=parsed,
        )
    )


def attempt_record(
    attempt: DeliveryAttempt, phase: LedgerPhase
) -> WakeLedgerRecord:
    if phase not in ATTEMPT_PHASES:
        raise WakeLedgerError(f"{phase} is not an attempt-scoped phase")
    return parse_ledger_record(
        WakeLedgerRecord(
            command_id=ledger_command_id(
                attempt.obligation_id, phase, attempt_n=attempt.attempt_n
            ),
            phase=phase,
            attempt_n=attempt.attempt_n,
            route_digest=attempt.route_digest,
            destination_digest=attempt.destination_digest,
            binding_id=attempt.binding_id,
            binding_generation=attempt.binding_generation,
            session_alias=attempt.session_alias,
            reasoning_surface=attempt.reasoning_surface,
            wake_transport=attempt.wake_transport,
        )
    )


def parse_ledger_record(record: WakeLedgerRecord) -> WakeLedgerRecord:
    oid = _obligation_id_from_command(record.command_id)
    expected = ledger_command_id(
        oid, record.phase, attempt_n=record.attempt_n
    )
    if record.command_id != expected:
        raise WakeLedgerError("command_id does not match phase/attempt")
    if record.phase in GLOBAL_PHASES:
        if record.attempt_n is not None:
            raise WakeLedgerError("global wake phase cannot carry attempt_n")
        if any(
            (
                record.route_digest,
                record.destination_digest,
                record.binding_id,
                record.binding_generation,
                record.session_alias,
                record.reasoning_surface,
                record.wake_transport,
                record.native_handle,
            )
        ):
            raise WakeLedgerError("global wake phase cannot carry route/native fields")
        if record.phase is LedgerPhase.WAKE_REQUESTED:
            if record.ack is not None or record.source_resolution is not None:
                raise WakeLedgerError("WAKE_REQUESTED cannot carry ack or resolution evidence")
            if record.obligation is None:
                raise WakeLedgerError("WAKE_REQUESTED requires frozen obligation envelope")
            try:
                parsed_obligation = parse_obligation(record.obligation.to_dict())
            except WakeObligationError as exc:
                raise WakeLedgerError(str(exc)) from exc
            if parsed_obligation.obligation_id != oid:
                raise WakeLedgerError("WAKE_REQUESTED obligation_id does not match command_id")
            return dataclasses.replace(record, obligation=parsed_obligation)
        if record.phase is LedgerPhase.TARGET_ACKNOWLEDGED:
            parse_acknowledgement(record.ack, obligation_id=oid)
        if record.phase is LedgerPhase.SOURCE_RESOLVED:
            if record.source_resolution is None:
                raise WakeLedgerError("SOURCE_RESOLVED requires source-resolution evidence")
            parse_source_resolution(record.source_resolution, obligation_id=oid)
        return record
    _strict_positive_int(record.attempt_n)
    if not (
        record.route_digest
        and record.destination_digest
        and record.session_alias
        and record.reasoning_surface
        and record.wake_transport
    ):
        raise WakeLedgerError("attempt phase requires a complete route snapshot")
    if record.native_handle:
        raise WakeLedgerError("ledger records must not persist native handles")
    if record.ack is not None or record.source_resolution is not None:
        raise WakeLedgerError("attempt phase cannot carry ack or resolution evidence")
    if record.obligation is not None:
        raise WakeLedgerError("attempt phase cannot carry the obligation envelope")
    return record


def acknowledge(
    obligation: WakeObligation,
    *,
    trusted: TrustedAckContext,
    claimed_obligation_ids: Sequence[str],
) -> WakeAcknowledgement:
    """ACK identity comes from trusted host context, never from model prose."""

    if not isinstance(trusted.ack_mode, AckMode):
        raise WakeLedgerError("ack_mode must be AckMode")
    claimed = {str(item).strip() for item in claimed_obligation_ids}
    if obligation.obligation_id not in claimed:
        raise WakeLedgerError("trusted ack does not include this obligation_id")
    seat = str(trusted.target_seat or "").strip().lower()
    if seat not in SEATS:
        raise WakeLedgerError("trusted ack target_seat is not a canonical seat")
    alias = str(trusted.session_alias or "").strip()
    if SESSION_ALIAS_RE.fullmatch(alias) is None:
        raise WakeLedgerError("trusted ack session_alias is malformed")
    surface = str(trusted.reasoning_surface or "").strip()
    if surface not in REASONING_SURFACES:
        raise WakeLedgerError("trusted ack reasoning_surface is unknown")
    stamp = trusted.acknowledged_at or utc_now_iso()
    if ISO_UTC_RE.fullmatch(stamp) is None:
        raise WakeLedgerError("acknowledged_at must be UTC ISO-8601")
    binding_id = trusted.binding_id
    receipt = trusted.operator_authority_receipt
    if trusted.ack_mode is AckMode.REASONING_SESSION:
        if seat != obligation.declared_target_seat:
            raise WakeLedgerError("reasoning_session ack target_seat must match the obligation")
        token = str(binding_id or "").strip()
        if BINDING_ID_RE.fullmatch(token) is None:
            raise WakeLedgerError("reasoning_session ack requires trusted binding context")
        binding_id = token
        if receipt:
            raise WakeLedgerError("reasoning_session ack cannot carry operator authority receipt")
        receipt = None
    elif trusted.ack_mode is AckMode.HUMAN_OPERATOR:
        token = str(receipt or "").strip()
        if OPERATOR_AUTHORITY_RECEIPT_RE.fullmatch(token) is None:
            raise WakeLedgerError("human_operator ack requires operator_authority_receipt")
        receipt = token
        binding_id = None if binding_id in (None, "") else str(binding_id).strip()
        if binding_id and BINDING_ID_RE.fullmatch(binding_id) is None:
            raise WakeLedgerError("human_operator binding_id is malformed")
    else:
        raise WakeLedgerError("unsupported ack_mode")
    return WakeAcknowledgement(
        obligation_id=obligation.obligation_id,
        ack_mode=trusted.ack_mode,
        target_seat=seat,
        session_alias=alias,
        reasoning_surface=surface,
        binding_id=binding_id,
        acknowledged_at=stamp,
        claimed_obligation_ids=tuple(str(item).strip() for item in claimed_obligation_ids),
        operator_authority_receipt=receipt,
    )


def parse_acknowledgement(
    ack: WakeAcknowledgement | None, *, obligation_id: str
) -> WakeAcknowledgement:
    if not isinstance(ack, WakeAcknowledgement):
        raise WakeLedgerError("TARGET_ACKNOWLEDGED requires acknowledgement evidence")
    if not isinstance(ack.ack_mode, AckMode):
        raise WakeLedgerError("ack_mode must be AckMode")
    oid = _obligation_id(obligation_id)
    if ack.obligation_id != oid:
        raise WakeLedgerError("acknowledgement obligation_id does not match command_id")
    seat = str(ack.target_seat or "").strip().lower()
    if seat not in SEATS:
        raise WakeLedgerError("trusted ack target_seat is not a canonical seat")
    if SESSION_ALIAS_RE.fullmatch(str(ack.session_alias or "")) is None:
        raise WakeLedgerError("trusted ack session_alias is malformed")
    if str(ack.reasoning_surface or "") not in REASONING_SURFACES:
        raise WakeLedgerError("trusted ack reasoning_surface is unknown")
    if ISO_UTC_RE.fullmatch(str(ack.acknowledged_at or "")) is None:
        raise WakeLedgerError("acknowledged_at must be UTC ISO-8601")
    if oid not in {str(item).strip() for item in ack.claimed_obligation_ids}:
        raise WakeLedgerError("trusted ack does not include this obligation_id")
    if ack.ack_mode is AckMode.REASONING_SESSION:
        if BINDING_ID_RE.fullmatch(str(ack.binding_id or "")) is None:
            raise WakeLedgerError("reasoning_session ack requires trusted binding context")
        if ack.operator_authority_receipt:
            raise WakeLedgerError("reasoning_session ack cannot carry operator authority receipt")
    elif ack.ack_mode is AckMode.HUMAN_OPERATOR:
        if OPERATOR_AUTHORITY_RECEIPT_RE.fullmatch(str(ack.operator_authority_receipt or "")) is None:
            raise WakeLedgerError("human_operator ack requires operator_authority_receipt")
    else:
        raise WakeLedgerError("unsupported ack_mode")
    return ack


def ack_record(
    obligation: WakeObligation, ack: WakeAcknowledgement
) -> WakeLedgerRecord:
    if ack.obligation_id != obligation.obligation_id:
        raise WakeLedgerError("acknowledgement obligation_id does not match")
    return parse_ledger_record(
        WakeLedgerRecord(
            command_id=ledger_command_id(
                obligation.obligation_id, LedgerPhase.TARGET_ACKNOWLEDGED
            ),
            phase=LedgerPhase.TARGET_ACKNOWLEDGED,
            ack=ack,
        )
    )


def resolve_source(
    obligation: WakeObligation,
    *,
    code: SourceResolutionCode,
    health: SourceReadHealth,
    source_present: bool,
    snapshot_digest: str,
    evidence_refs: Sequence[str] = (),
    annotation: str = "",
    resolved_at: str | None = None,
) -> SourceResolution:
    if not isinstance(code, SourceResolutionCode):
        raise WakeLedgerError("source resolution code must be SourceResolutionCode")
    if health is SourceReadHealth.DEGRADED:
        raise WakeLedgerError("degraded canonical read cannot SOURCE_RESOLVE")
    if health is not SourceReadHealth.HEALTHY:
        raise WakeLedgerError("source resolution requires a healthy canonical read")
    if source_present:
        raise WakeLedgerError("source condition is still present")
    expected = expected_resolution_code(obligation)
    if code is not expected:
        raise WakeLedgerError("source resolution code does not match the obligation source")
    digest = str(snapshot_digest or "").strip().lower()
    if SNAPSHOT_DIGEST_RE.fullmatch(digest) is None:
        raise WakeLedgerError("source resolution requires a snapshot digest")
    stamp = resolved_at or utc_now_iso()
    if ISO_UTC_RE.fullmatch(stamp) is None:
        raise WakeLedgerError("resolved_at must be UTC ISO-8601")
    return SourceResolution(
        obligation_id=obligation.obligation_id,
        code=code,
        health=health,
        source_present=False,
        source_kind=obligation.source_kind.value,
        source_ref=obligation.source_ref,
        snapshot_digest=digest,
        resolved_at=stamp,
        evidence_refs=tuple(str(item) for item in evidence_refs),
        annotation=str(annotation or ""),
    )


def parse_source_resolution(
    resolution: SourceResolution | None, *, obligation_id: str
) -> SourceResolution:
    if not isinstance(resolution, SourceResolution):
        raise WakeLedgerError("SOURCE_RESOLVED requires source-resolution evidence")
    if not isinstance(resolution.code, SourceResolutionCode):
        raise WakeLedgerError("source resolution code must be SourceResolutionCode")
    oid = _obligation_id(obligation_id)
    if resolution.obligation_id != oid:
        raise WakeLedgerError("source resolution obligation_id does not match command_id")
    if resolution.health is SourceReadHealth.DEGRADED:
        raise WakeLedgerError("degraded canonical read cannot SOURCE_RESOLVE")
    if resolution.health is not SourceReadHealth.HEALTHY:
        raise WakeLedgerError("source resolution requires a healthy canonical read")
    if resolution.source_present:
        raise WakeLedgerError("source condition is still present")
    if SNAPSHOT_DIGEST_RE.fullmatch(str(resolution.snapshot_digest or "")) is None:
        raise WakeLedgerError("source resolution requires a snapshot digest")
    if ISO_UTC_RE.fullmatch(str(resolution.resolved_at or "")) is None:
        raise WakeLedgerError("resolved_at must be UTC ISO-8601")
    if str(resolution.source_kind or "") not in {item.value for item in SourceKind}:
        raise WakeLedgerError("source resolution source_kind is unknown")
    if not resolution.source_ref:
        raise WakeLedgerError("source resolution source_ref is required")
    return resolution


def expected_resolution_code(obligation: WakeObligation) -> SourceResolutionCode:
    if obligation.wake_kind is WakeKind.CEO_DECISION_PENDING:
        return SourceResolutionCode.AGENTOS_ITEM_ABSENT
    try:
        return _RESOLUTION_CODE_BY_SOURCE[obligation.source_kind]
    except KeyError as exc:
        raise WakeLedgerError("source resolution code does not match the obligation source") from exc


def resolved_record(
    obligation: WakeObligation, resolution: SourceResolution
) -> WakeLedgerRecord:
    if resolution.obligation_id != obligation.obligation_id:
        raise WakeLedgerError("source resolution obligation_id does not match")
    return parse_ledger_record(
        WakeLedgerRecord(
            command_id=ledger_command_id(
                obligation.obligation_id, LedgerPhase.SOURCE_RESOLVED
            ),
            phase=LedgerPhase.SOURCE_RESOLVED,
            source_resolution=resolution,
        )
    )


def reconstruct_status(
    obligation_id: str,
    records: Sequence[WakeLedgerRecord],
    *,
    route: WakeRoute | None = None,
    destination_digest: str | None = None,
) -> ObligationStatus:
    oid = _obligation_id(obligation_id)
    scoped = [
        parse_ledger_record(record)
        for record in records
        if str(record.command_id) == oid or str(record.command_id).startswith(oid + ":")
    ]
    if not _has_requested(scoped):
        if scoped:
            raise WakeLedgerError("delivery evidence without WAKE_REQUESTED")
        return ObligationStatus.NOT_SEEN
    terminals = [record.phase for record in scoped if record.phase in TERMINAL_CLOSE]
    if terminals:
        first = terminals[0]
        if first is LedgerPhase.TARGET_ACKNOWLEDGED:
            return ObligationStatus.TARGET_ACKNOWLEDGED
        return ObligationStatus.SOURCE_RESOLVED
    dest = destination_digest
    if route is not None:
        dest = route.destination_digest
    if dest is None:
        return ObligationStatus.PENDING_RETRYABLE
    matching = [
        record
        for record in scoped
        if record.phase in ATTEMPT_PHASES and record.destination_digest == dest
    ]
    if any(record.phase is LedgerPhase.DELIVERED for record in matching):
        return ObligationStatus.DELIVERED_UNACKNOWLEDGED
    if any(record.phase is LedgerPhase.ACCEPTED for record in matching):
        return ObligationStatus.ACCEPTED
    if any(record.phase is LedgerPhase.DELIVERY_ATTEMPT for record in matching):
        return ObligationStatus.ATTEMPTED
    return ObligationStatus.PENDING_RETRYABLE


def assert_causal(records: Sequence[WakeLedgerRecord]) -> None:
    """Refuse nonsense sequences PR-2 must not persist."""

    parsed = [parse_ledger_record(record) for record in records]
    if not parsed:
        return
    oids = {_obligation_id_from_command(record.command_id) for record in parsed}
    if len(oids) != 1:
        raise WakeLedgerError("causal stream must be a single obligation")
    if parsed[0].phase is not LedgerPhase.WAKE_REQUESTED:
        raise WakeLedgerError("REQUESTED must precede delivery attempts")
    requested = parsed[0].obligation
    if requested is None:
        raise WakeLedgerError("WAKE_REQUESTED requires frozen obligation envelope")
    seen_attempts: dict[int, set[LedgerPhase]] = {}
    closed: LedgerPhase | None = None
    for record in parsed[1:]:
        if record.phase is LedgerPhase.WAKE_REQUESTED:
            raise WakeLedgerError("duplicate WAKE_REQUESTED")
        if record.phase in TERMINAL_CLOSE:
            if record.phase is LedgerPhase.TARGET_ACKNOWLEDGED:
                ack = parse_acknowledgement(
                    record.ack, obligation_id=requested.obligation_id
                )
                if ack.ack_mode is AckMode.REASONING_SESSION:
                    if ack.target_seat != requested.declared_target_seat:
                        raise WakeLedgerError(
                            "reasoning_session ack target_seat must match the obligation"
                        )
            else:
                resolution = parse_source_resolution(
                    record.source_resolution, obligation_id=requested.obligation_id
                )
                if resolution.source_ref != requested.source_ref:
                    raise WakeLedgerError("source resolution source_ref does not match")
                if resolution.source_kind != requested.source_kind.value:
                    raise WakeLedgerError("source resolution source_kind does not match")
                if resolution.code is not expected_resolution_code(requested):
                    raise WakeLedgerError(
                        "source resolution code does not match the obligation source"
                    )
            if closed is not None and closed is not record.phase:
                raise WakeLedgerError("conflicting terminal close")
            closed = record.phase
            continue
        if closed is not None and record.phase in ATTEMPT_PHASES:
            raise WakeLedgerError("no further delivery after terminal close")
        if record.phase in ATTEMPT_PHASES:
            n = _strict_positive_int(record.attempt_n)
            if n > 1:
                previous = seen_attempts.get(n - 1, set())
                if LedgerPhase.DELIVERY_ATTEMPT not in previous:
                    raise WakeLedgerError(
                        "later attempt cannot start before the previous attempt exists"
                    )
                if not (previous & ATTEMPT_TERMINALS):
                    raise WakeLedgerError(
                        "later attempt cannot start while the previous attempt is unfinished"
                    )
            seen_attempts.setdefault(n, set())
            if record.phase is not LedgerPhase.DELIVERY_ATTEMPT:
                if LedgerPhase.DELIVERY_ATTEMPT not in seen_attempts[n]:
                    raise WakeLedgerError(
                        "DELIVERY_ATTEMPT must exist before ACCEPTED/DELIVERED/FAILED"
                    )
            if record.phase in ATTEMPT_TERMINALS and (seen_attempts[n] & ATTEMPT_TERMINALS):
                raise WakeLedgerError("at most one terminal per delivery attempt")
            seen_attempts[n].add(record.phase)


def unfinished_attempt_n(records: Sequence[WakeLedgerRecord]) -> int | None:
    """Restart reuses A1 when A1 has no terminal evidence.  Never auto-allocates A2."""

    parsed = [parse_ledger_record(record) for record in records]
    by_n: dict[int, set[LedgerPhase]] = {}
    for record in parsed:
        if record.phase in ATTEMPT_PHASES and record.attempt_n is not None:
            by_n.setdefault(record.attempt_n, set()).add(record.phase)
    for n in sorted(by_n):
        phases = by_n[n]
        if LedgerPhase.DELIVERY_ATTEMPT in phases and not (
            phases & ATTEMPT_TERMINALS
        ):
            return n
    return None


def next_attempt_n(records: Sequence[WakeLedgerRecord]) -> int:
    unfinished = unfinished_attempt_n(records)
    if unfinished is not None:
        return unfinished
    parsed = [parse_ledger_record(record) for record in records]
    seen = [
        _strict_positive_int(record.attempt_n)
        for record in parsed
        if record.attempt_n is not None
    ]
    return (max(seen) + 1) if seen else 1


def already_delivered_to_destination(
    records: Sequence[WakeLedgerRecord], destination_digest: str
) -> bool:
    return any(
        parse_ledger_record(record).phase is LedgerPhase.DELIVERED
        and record.destination_digest == destination_digest
        for record in records
    )


def eligible_for_nudge(
    obligation_id: str,
    records: Sequence[WakeLedgerRecord],
    *,
    destination_digest: str | None = None,
) -> bool:
    status = reconstruct_status(
        obligation_id, records, destination_digest=destination_digest
    )
    if status in {
        ObligationStatus.TARGET_ACKNOWLEDGED,
        ObligationStatus.SOURCE_RESOLVED,
        ObligationStatus.NOT_SEEN,
    }:
        return False
    if destination_digest and already_delivered_to_destination(
        records, destination_digest
    ):
        return False
    return True


def _has_requested(records: Sequence[WakeLedgerRecord]) -> bool:
    return any(record.phase is LedgerPhase.WAKE_REQUESTED for record in records)


def _obligation_id(value: str) -> str:
    token = str(value or "").strip()
    if WAKE_ID_RE.fullmatch(token) is None:
        raise WakeLedgerError("obligation_id must be a canonical WAKE-* identity")
    return token


def _obligation_id_from_command(command_id: str) -> str:
    token = str(command_id or "").strip()
    oid = token.split(":", 1)[0]
    return _obligation_id(oid)


def _strict_positive_int(value: object, name: str = "attempt_n") -> int:
    if type(value) is not int or isinstance(value, bool) or value < 1:
        raise WakeLedgerError(f"{name} must be an integer >= 1")
    return value


__all__ = [
    "AckMode",
    "DeliveryAttempt",
    "LedgerPhase",
    "ObligationStatus",
    "SourceReadHealth",
    "SourceResolution",
    "SourceResolutionCode",
    "TrustedAckContext",
    "UNARMED_RETRY_POLICY",
    "WAKE_AGGREGATE_TYPE",
    "WakeAcknowledgement",
    "WakeLedgerError",
    "WakeLedgerRecord",
    "WakeRetryPolicy",
    "ack_record",
    "acknowledge",
    "already_delivered_to_destination",
    "assert_causal",
    "attempt_record",
    "eligible_for_nudge",
    "expected_resolution_code",
    "ledger_command_id",
    "make_delivery_attempt",
    "next_attempt_n",
    "parse_acknowledgement",
    "parse_ledger_record",
    "parse_source_resolution",
    "reconstruct_status",
    "requested_record",
    "resolve_source",
    "resolved_record",
    "unfinished_attempt_n",
]
