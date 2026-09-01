"""Wake delivery + acknowledgement contract — not a second queue.

A persisted WAKE *request* is not a delivered wake.  Delivery attempts are
route-specific.  The external transport unit is a :class:`NudgeAttempt`.
Acknowledgement and source resolution are obligation-global.

Guarantee: at-most-one provider submission per durable nudge identity.
``ALREADY_DELIVERED`` is a fabric reconciliation result, never a transport
result.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
from enum import Enum
from typing import Mapping, Protocol, Sequence, runtime_checkable

from common.redaction import sanitize_external_text
from control_plane.session_targets import RuntimeBinding, SessionTargetRegistry, WakeRoute
from control_plane.wake_ack_ingress import (
    TrustedWorkerWakeAckProjection,
    WakeAckClaim,
    acknowledge_consumed_wakes,
)
from control_plane.wake_events import (
    ISO_UTC_RE,
    WAKE_ID_RE,
    WakeObligation,
    canonical_json_bytes,
    utc_now_iso,
)
from control_plane.wake_ledger import (
    DeliveryAttempt,
    LedgerPhase,
    ObligationStatus,
    UNARMED_RETRY_POLICY,
    WakeLedgerRecord,
    WakeRetryPolicy,
    attempt_record,
    eligible_for_nudge,
    ledger_command_id,
    make_delivery_attempt,
    next_attempt_n,
    parse_ledger_record,
    reconstruct_status,
    requested_record,
    unfinished_attempt_n,
)
from control_plane.wake_persist import WakeLedgerRepository
from control_plane.wake_transport import (
    DISPATCHER_INTERFACE_VERSION,
    WAKE_TRANSPORT_DESCRIPTORS,
    WakeTransportDescriptor,
    WakeTransportError,
    transport_implemented,
    wake_transport_descriptor as canonical_wake_transport_descriptor,
)

RECEIPT_SCHEMA = "mastermind.wake_receipt.v1"
_DETAIL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_NUDGE_ID_RE = re.compile(r"^NUDGE-[0-9a-f]{32}$")
ALLOWED_DETAIL_KEYS = frozenset(
    {
        "ledger_command_id",
        "attempt_n",
        "policy_version",
        "coalesced_count",
        "nudge_id",
    }
)
TYPED_REASON_CODES = frozenset(
    {
        "transport_not_implemented",
        "target_disabled",
        "human_required",
        "delivery_not_allowed",
        "session_alias_mismatch",
        "obligation_mismatch",
        "route_digest_mismatch",
        "binding_mismatch",
        "surface_mismatch",
        "transport_mismatch",
        "adapter_forged_success",
        "command_id_replay",
        "pending_retryable",
        "target_acknowledged",
        "source_resolved",
        "delivery_attempt",
        "no_delivery_evidence",
        "unsupported_transport",
        "target_unavailable",
        "transport_failed",
        "delivered",
        "accepted",
        "production_disarmed",
        "binding_not_ready",
    }
)
OUTCOME_REASONS = {
    "ACCEPTED": frozenset({"accepted"}),
    "DELIVERED": frozenset({"delivered"}),
    "TARGET_UNAVAILABLE": frozenset({"target_unavailable"}),
    "FAILED": frozenset({"transport_failed"}),
    "ALREADY_DELIVERED": frozenset({"command_id_replay"}),
    "HUMAN_REQUIRED": frozenset({"human_required"}),
    "UNSUPPORTED": frozenset(
        {
            "transport_not_implemented",
            "target_disabled",
            "production_disarmed",
            "binding_not_ready",
            "delivery_not_allowed",
        }
    ),
    "REFUSED": frozenset({"delivery_not_allowed", "adapter_forged_success"}),
}
FABRIC_ONLY_OUTCOMES = frozenset({"ALREADY_DELIVERED", "HUMAN_REQUIRED", "UNSUPPORTED", "REFUSED"})
TRANSPORT_OUTCOMES = frozenset({"ACCEPTED", "DELIVERED", "TARGET_UNAVAILABLE", "FAILED"})


class WakeDispatchError(ValueError):
    """The dispatcher refused the call or an adapter forged a success receipt."""


class WakeEffectUnknownError(WakeDispatchError):
    """A provider submission may have started and must not be retried."""


class TransportOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    DELIVERED = "DELIVERED"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    FAILED = "FAILED"


class WakePreSubmitError(WakeDispatchError):
    """Typed proof that a provider submission did not begin."""

    def __init__(
        self,
        reason: str,
        *,
        outcome: TransportOutcome = TransportOutcome.TARGET_UNAVAILABLE,
        reason_code: str = "target_unavailable",
    ) -> None:
        super().__init__(reason)
        if outcome not in {
            TransportOutcome.TARGET_UNAVAILABLE,
            TransportOutcome.FAILED,
        }:
            raise ValueError("pre-submit failures cannot claim provider success")
        if reason_code not in OUTCOME_REASONS[outcome.value]:
            raise ValueError("pre-submit outcome/reason is contradictory")
        self.outcome = outcome
        self.reason_code = reason_code


class PersistedNudgeState(str, Enum):
    ACCEPTED = "ACCEPTED"
    DELIVERED = "DELIVERED"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class FabricOutcome(str, Enum):
    ALREADY_DELIVERED = "ALREADY_DELIVERED"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    REFUSED = "REFUSED"


class WakeOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    DELIVERED = "DELIVERED"
    ALREADY_DELIVERED = "ALREADY_DELIVERED"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    REFUSED = "REFUSED"
    FAILED = "FAILED"


SUCCESS_OUTCOMES = frozenset(
    {WakeOutcome.ACCEPTED, WakeOutcome.DELIVERED, WakeOutcome.ALREADY_DELIVERED}
)


@dataclasses.dataclass(frozen=True)
class WakeReceipt:
    schema: str
    outcome: WakeOutcome
    obligation_id: str
    attempt_n: int
    attempt_command_id: str
    session_alias: str
    reasoning_surface: str
    wake_transport: str
    route_digest: str
    destination_digest: str
    binding_id: str
    binding_generation: int
    transport_implemented: bool
    target_enabled: bool
    production_armed: bool
    interface_version: str
    reason_code: str
    created_at: str
    details: tuple[tuple[str, str], ...] = ()

    def claims_success(self) -> bool:
        return self.outcome in SUCCESS_OUTCOMES

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self) | {
            "outcome": self.outcome.value,
            "details": dict(self.details),
        }


@dataclasses.dataclass(frozen=True)
class WakeNudge:
    """Adapter input.  No worker prose, objective, result, or authority data."""

    session_alias: str
    reasoning_surface: str
    wake_transport: str
    binding_id: str
    binding_generation: int
    native_handle: str | None
    account_label: str | None
    destination_digest: str
    obligation_ids: tuple[str, ...]
    attempt_command_ids: tuple[str, ...]
    nudge_id: str


@dataclasses.dataclass(frozen=True)
class NudgeAttempt:
    destination_digest: str
    session_alias: str
    reasoning_surface: str
    wake_transport: str
    binding_id: str
    binding_generation: int
    attempts: tuple[DeliveryAttempt, ...]

    @property
    def nudge_id(self) -> str:
        return mint_nudge_id(
            self.destination_digest,
            tuple(item.attempt_command_id for item in self.attempts),
        )

    @property
    def obligation_ids(self) -> tuple[str, ...]:
        return tuple(item.obligation_id for item in self.attempts)

    @property
    def coalesced(self) -> bool:
        return len(self.attempts) > 1


@dataclasses.dataclass(frozen=True)
class NudgePlan:
    session_alias: str
    reasoning_surface: str
    wake_transport: str
    binding_generation: int
    binding_id: str
    destination_digest: str
    obligation_ids: tuple[str, ...]
    route_digests: tuple[str, ...]
    attempts: tuple[DeliveryAttempt, ...] = ()

    @property
    def coalesced(self) -> bool:
        return len(self.obligation_ids) > 1

    def to_dict(self) -> dict[str, object]:
        return {
            "session_alias": self.session_alias,
            "reasoning_surface": self.reasoning_surface,
            "wake_transport": self.wake_transport,
            "binding_generation": self.binding_generation,
            "binding_id": self.binding_id,
            "destination_digest": self.destination_digest,
            "obligation_ids": list(self.obligation_ids),
            "route_digests": list(self.route_digests),
            "coalesced": self.coalesced,
            "nudge_count": 1,
        }


@dataclasses.dataclass(frozen=True)
class TransportReceipt:
    outcome: TransportOutcome
    reason_code: str
    created_at: str
    details: tuple[tuple[str, str], ...] = ()


@dataclasses.dataclass(frozen=True)
class WakeTransportCompletion:
    """Transient non-wire transport result; the projection is never receipt data."""

    receipt: TransportReceipt
    target_ack_projection: TrustedWorkerWakeAckProjection | None = dataclasses.field(
        default=None,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, TransportReceipt):
            raise WakeDispatchError("Wake transport completion requires a receipt")
        projection = self.target_ack_projection
        if projection is not None:
            if not isinstance(projection, TrustedWorkerWakeAckProjection):
                raise WakeDispatchError(
                    "Wake transport completion ACK projection must be trusted and typed"
                )
            if self.receipt.outcome is not TransportOutcome.DELIVERED:
                raise WakeDispatchError(
                    "Wake transport completion ACK projection requires DELIVERED"
                )


def normalize_transport_completion(
    value: TransportReceipt | WakeTransportCompletion,
) -> tuple[TransportReceipt, TrustedWorkerWakeAckProjection | None]:
    if isinstance(value, TransportReceipt):
        return value, None
    if isinstance(value, WakeTransportCompletion):
        return value.receipt, value.target_ack_projection
    raise WakeDispatchError("adapter returned an invalid Wake transport completion")


@dataclasses.dataclass(frozen=True)
class PersistedNudgeResult:
    """Non-wire result of the persist-before-provider coordinator."""

    state: PersistedNudgeState
    nudge_attempt: NudgeAttempt
    transport_receipt: TransportReceipt | None = None
    receipts: tuple[WakeReceipt, ...] = ()

    @property
    def nudge_id(self) -> str:
        return self.nudge_attempt.nudge_id


def coalesce_nudge(routes: Sequence[WakeRoute]) -> NudgePlan:
    if not routes:
        raise WakeDispatchError("coalesce_nudge requires at least one route")
    first = routes[0]
    obligation_ids: list[str] = []
    digests: list[str] = []
    for route in routes:
        if route.destination_digest != first.destination_digest:
            raise WakeDispatchError("cannot coalesce mixed delivery destinations")
        if route.session_alias != first.session_alias:
            raise WakeDispatchError("cannot coalesce routes for different sessions")
        if route.reasoning_surface != first.reasoning_surface:
            raise WakeDispatchError("cannot coalesce mixed reasoning surfaces")
        if route.wake_transport != first.wake_transport:
            raise WakeDispatchError("cannot coalesce mixed wake transports")
        if route.binding_generation != first.binding_generation:
            raise WakeDispatchError("cannot coalesce mixed binding generations")
        if route.binding_id != first.binding_id:
            raise WakeDispatchError("cannot coalesce mixed binding identities")
        if route.obligation_id not in obligation_ids:
            obligation_ids.append(route.obligation_id)
            digests.append(route.route_digest)
    return NudgePlan(
        session_alias=first.session_alias,
        reasoning_surface=first.reasoning_surface,
        wake_transport=first.wake_transport,
        binding_generation=first.binding_generation,
        binding_id=first.binding_id,
        destination_digest=first.destination_digest,
        obligation_ids=tuple(obligation_ids),
        route_digests=tuple(digests),
    )


def plan_eligible_nudge(
    routes: Sequence[WakeRoute],
    records_by_obligation: Mapping[str, Sequence[WakeLedgerRecord]],
) -> NudgePlan:
    eligible = [
        route
        for route in routes
        if eligible_for_nudge(
            route.obligation_id,
            records_by_obligation.get(route.obligation_id, ()),
            destination_digest=route.destination_digest,
        )
    ]
    return coalesce_nudge(eligible)


def mint_nudge_id(
    destination_digest: str, attempt_command_ids: Sequence[str]
) -> str:
    payload = canonical_json_bytes(
        {
            "destination_digest": str(destination_digest),
            "attempt_command_ids": sorted(str(item) for item in attempt_command_ids),
        }
    )
    return "NUDGE-" + hashlib.sha256(payload).hexdigest()[:32]


def make_receipt(
    *,
    outcome: WakeOutcome | str,
    obligation: WakeObligation,
    route: WakeRoute,
    reason_code: str,
    created_at: str | None = None,
    details: Mapping[str, object] | None = None,
    attempt: DeliveryAttempt | None = None,
) -> WakeReceipt:
    resolved_outcome = (
        outcome if isinstance(outcome, WakeOutcome) else WakeOutcome(str(outcome))
    )
    code = str(reason_code or "").strip()
    if code not in TYPED_REASON_CODES:
        raise WakeDispatchError(f"untyped wake reason_code {code!r}")
    n = 1 if attempt is None else attempt.attempt_n
    command = (
        ledger_command_id(obligation.obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=n)
        if attempt is None
        else attempt.attempt_command_id
    )
    snapshot = attempt
    return WakeReceipt(
        schema=RECEIPT_SCHEMA,
        outcome=resolved_outcome,
        obligation_id=_obligation_id(obligation.obligation_id),
        attempt_n=n,
        attempt_command_id=command,
        session_alias=snapshot.session_alias if snapshot else route.session_alias,
        reasoning_surface=snapshot.reasoning_surface if snapshot else route.reasoning_surface,
        wake_transport=snapshot.wake_transport if snapshot else route.wake_transport,
        route_digest=snapshot.route_digest if snapshot else route.route_digest,
        destination_digest=snapshot.destination_digest if snapshot else route.destination_digest,
        binding_id=snapshot.binding_id if snapshot else route.binding_id,
        binding_generation=snapshot.binding_generation if snapshot else route.binding_generation,
        transport_implemented=route.transport_implemented,
        target_enabled=route.target_enabled,
        production_armed=route.production_armed,
        interface_version=route.interface_version,
        reason_code=code,
        created_at=created_at or utc_now_iso(),
        details=_bounded_details(details),
    )


def authenticate_receipt(
    receipt: WakeReceipt,
    *,
    obligation: WakeObligation,
    route: WakeRoute,
    descriptor: WakeTransportDescriptor,
    attempt: DeliveryAttempt | None = None,
    allow_fabric_outcome: bool = False,
    historical_delivery: bool = False,
) -> WakeReceipt:
    """Treat the receipt as untrusted adapter (or fabric) output."""

    if not isinstance(receipt, WakeReceipt):
        raise WakeDispatchError("receipt is not a WakeReceipt")
    if receipt.schema != RECEIPT_SCHEMA:
        raise WakeDispatchError("receipt schema is not the wake-receipt contract")
    if ISO_UTC_RE.fullmatch(str(receipt.created_at or "")) is None:
        raise WakeDispatchError("receipt created_at must be UTC ISO-8601")
    if receipt.interface_version != descriptor.interface_version:
        raise WakeDispatchError("receipt interface version does not match the descriptor")
    if receipt.obligation_id != obligation.obligation_id:
        raise WakeDispatchError("receipt obligation_id does not match the expected wake")
    if receipt.destination_digest != route.destination_digest:
        raise WakeDispatchError("receipt destination_digest does not match the expected route")
    if not historical_delivery:
        if receipt.session_alias != route.session_alias:
            raise WakeDispatchError("receipt session_alias does not match the expected route")
        if receipt.reasoning_surface != route.reasoning_surface:
            raise WakeDispatchError("receipt reasoning_surface does not match the expected route")
        if receipt.wake_transport != route.wake_transport:
            raise WakeDispatchError("receipt wake_transport does not match the expected route")
        if receipt.route_digest != route.route_digest:
            raise WakeDispatchError("receipt route_digest does not match the expected route")
        if receipt.binding_generation != route.binding_generation:
            raise WakeDispatchError("receipt binding_generation does not match the expected route")
        if receipt.binding_id != route.binding_id:
            raise WakeDispatchError("receipt binding_id does not match the expected route")
    if receipt.wake_transport != descriptor.transport_id and not historical_delivery:
        raise WakeDispatchError("receipt wake_transport does not match the descriptor")
    if receipt.target_enabled != route.target_enabled:
        raise WakeDispatchError("receipt target_enabled snapshot does not match the route")
    if receipt.production_armed != route.production_armed:
        raise WakeDispatchError("receipt production_armed snapshot does not match the route")
    canonical_flag = transport_implemented(route.wake_transport)
    injected = descriptor.transport_implemented != canonical_flag
    if not injected and route.transport_implemented != descriptor.transport_implemented:
        raise WakeDispatchError(
            "route transport_implemented disagrees with the canonical descriptor"
        )
    if receipt.transport_implemented != descriptor.transport_implemented:
        raise WakeDispatchError(
            "receipt transport_implemented flag does not match the descriptor"
        )
    expected_reasons = OUTCOME_REASONS.get(receipt.outcome.value, frozenset())
    if receipt.reason_code not in TYPED_REASON_CODES:
        raise WakeDispatchError(f"untyped wake reason_code {receipt.reason_code!r}")
    if receipt.reason_code not in expected_reasons:
        raise WakeDispatchError("receipt outcome/reason pairing is closed and contradictory")
    if receipt.outcome.value in FABRIC_ONLY_OUTCOMES and not allow_fabric_outcome:
        raise WakeDispatchError(
            f"adapter cannot author fabric outcome {receipt.outcome.value}"
        )
    if attempt is not None:
        if receipt.attempt_n != attempt.attempt_n:
            raise WakeDispatchError("receipt attempt_n does not match the delivery attempt")
        if receipt.attempt_command_id != attempt.attempt_command_id:
            raise WakeDispatchError("receipt attempt_command_id does not match")
        if receipt.route_digest != attempt.route_digest:
            raise WakeDispatchError("receipt route_digest does not match the delivery attempt")
        if receipt.destination_digest != attempt.destination_digest:
            raise WakeDispatchError("receipt destination_digest does not match the delivery attempt")
        if not historical_delivery and not attempt.matches_route(route):
            raise WakeDispatchError("delivery attempt does not match the current route")
    if receipt.claims_success() and not descriptor.transport_implemented:
        if not (allow_fabric_outcome and receipt.outcome is WakeOutcome.ALREADY_DELIVERED):
            raise WakeDispatchError(
                "unimplemented wake transport cannot claim ACCEPTED, DELIVERED, "
                "or ALREADY_DELIVERED"
            )
    if receipt.claims_success() and not route.delivery_allowed:
        if not (allow_fabric_outcome and receipt.outcome is WakeOutcome.ALREADY_DELIVERED):
            raise WakeDispatchError("delivery is not allowed for this route")
    return dataclasses.replace(receipt, details=_bounded_details(dict(receipt.details)))


def already_delivered_receipt(
    obligation: WakeObligation,
    route: WakeRoute,
    *,
    found: WakeLedgerRecord,
    created_at: str | None = None,
) -> WakeReceipt:
    try:
        parsed = parse_ledger_record(found)
    except WakeLedgerError as exc:
        raise WakeDispatchError(str(exc)) from exc
    if parsed.phase is not LedgerPhase.DELIVERED:
        raise WakeDispatchError("no delivery evidence for ALREADY_DELIVERED")
    found_oid = str(parsed.command_id).split(":", 1)[0]
    if found_oid != obligation.obligation_id:
        raise WakeDispatchError("delivery evidence belongs to a different obligation")
    if parsed.destination_digest != route.destination_digest:
        raise WakeDispatchError("delivery evidence does not match the current destination")
    historical = DeliveryAttempt(
        obligation_id=obligation.obligation_id,
        attempt_n=parsed.attempt_n or 0,
        attempt_command_id=ledger_command_id(
            obligation.obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=parsed.attempt_n,
        ),
        destination_digest=str(parsed.destination_digest),
        route_digest=str(parsed.route_digest),
        binding_id=str(parsed.binding_id),
        binding_generation=int(parsed.binding_generation or 0),
        session_alias=str(parsed.session_alias),
        reasoning_surface=str(parsed.reasoning_surface),
        wake_transport=str(parsed.wake_transport),
    )
    return authenticate_receipt(
        make_receipt(
            outcome=WakeOutcome.ALREADY_DELIVERED,
            obligation=obligation,
            route=route,
            reason_code="command_id_replay",
            created_at=created_at,
            details={
                "ledger_command_id": parsed.command_id,
                "attempt_n": str(historical.attempt_n),
            },
            attempt=historical,
        ),
        obligation=obligation,
        route=route,
        descriptor=_descriptor(route.wake_transport),
        attempt=historical,
        allow_fabric_outcome=True,
        historical_delivery=True,
    )


@runtime_checkable
class WakeDispatcher(Protocol):
    transport_id: str

    async def nudge(
        self,
        wake: WakeNudge,
    ) -> TransportReceipt | WakeTransportCompletion: ...


class UnsupportedWakeDispatcher:
    def __init__(self, transport_id: str) -> None:
        self.descriptor = _descriptor(transport_id)
        self.transport_id = self.descriptor.transport_id

    async def nudge(self, wake: WakeNudge) -> TransportReceipt:
        if wake.wake_transport != self.descriptor.transport_id:
            raise WakeDispatchError("dispatcher transport does not match the nudge")
        return TransportReceipt(
            outcome=TransportOutcome.FAILED,
            reason_code="unsupported_transport",
            created_at=utc_now_iso(),
        )

    async def wake(self, obligation: WakeObligation, route: WakeRoute) -> WakeReceipt:
        if route.human_required:
            return make_receipt(
                outcome=WakeOutcome.HUMAN_REQUIRED,
                obligation=obligation,
                route=route,
                reason_code="human_required",
            )
        if not route.production_armed:
            return make_receipt(
                outcome=WakeOutcome.UNSUPPORTED,
                obligation=obligation,
                route=route,
                reason_code="production_disarmed",
            )
        if not route.target_enabled:
            return make_receipt(
                outcome=WakeOutcome.UNSUPPORTED,
                obligation=obligation,
                route=route,
                reason_code="target_disabled",
            )
        if not self.descriptor.transport_implemented:
            return make_receipt(
                outcome=WakeOutcome.UNSUPPORTED,
                obligation=obligation,
                route=route,
                reason_code="transport_not_implemented",
            )
        return make_receipt(
            outcome=WakeOutcome.UNSUPPORTED,
            obligation=obligation,
            route=route,
            reason_code="delivery_not_allowed",
        )


def dispatcher_for(transport_id: str) -> UnsupportedWakeDispatcher:
    descriptor = _descriptor(transport_id)
    if descriptor.transport_implemented:
        raise WakeDispatchError(
            f"wake transport {transport_id!r} is marked implemented but PR-1 "
            "ships no production transport"
        )
    return UnsupportedWakeDispatcher(descriptor.transport_id)


def _nudge_from(
    attempts: Sequence[DeliveryAttempt],
    *,
    binding: RuntimeBinding | None,
    first_route: WakeRoute,
) -> WakeNudge:
    first = attempts[0]
    native = None if binding is None else binding.native_handle
    account = None if binding is None else binding.account_label
    if binding is not None:
        if binding.session_alias != first.session_alias:
            raise WakeDispatchError("runtime binding session_alias does not match the route")
        if binding.binding_generation != first.binding_generation:
            raise WakeDispatchError("runtime binding generation does not match the route")
        if binding.binding_id != first.binding_id:
            raise WakeDispatchError("runtime binding id does not match the route")
    return WakeNudge(
        session_alias=first.session_alias,
        reasoning_surface=first.reasoning_surface,
        wake_transport=first.wake_transport,
        binding_id=first.binding_id,
        binding_generation=first.binding_generation,
        native_handle=native,
        account_label=account,
        destination_digest=first.destination_digest,
        obligation_ids=tuple(item.obligation_id for item in attempts),
        attempt_command_ids=tuple(item.attempt_command_id for item in attempts),
        nudge_id=mint_nudge_id(
            first.destination_digest,
            tuple(item.attempt_command_id for item in attempts),
        ),
    )


def _attempt_from_record(record: WakeLedgerRecord) -> DeliveryAttempt:
    parsed = parse_ledger_record(record)
    if parsed.phase not in {
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.ACCEPTED,
        LedgerPhase.DELIVERED,
        LedgerPhase.FAILED,
        LedgerPhase.TARGET_UNAVAILABLE,
    }:
        raise WakeDispatchError("persisted nudge identity requires an attempt record")
    return DeliveryAttempt(
        obligation_id=str(parsed.command_id).split(":", 1)[0],
        attempt_n=int(parsed.attempt_n or 0),
        attempt_command_id=ledger_command_id(
            str(parsed.command_id).split(":", 1)[0],
            LedgerPhase.DELIVERY_ATTEMPT,
            attempt_n=parsed.attempt_n,
        ),
        destination_digest=str(parsed.destination_digest),
        route_digest=str(parsed.route_digest),
        binding_id=str(parsed.binding_id),
        binding_generation=int(parsed.binding_generation or 0),
        session_alias=str(parsed.session_alias),
        reasoning_surface=str(parsed.reasoning_surface),
        wake_transport=str(parsed.wake_transport),
        nudge_id=parsed.nudge_id,
        nudge_attempt_command_ids=tuple(parsed.nudge_attempt_command_ids),
    )


def _nudge_attempt_from(attempts: Sequence[DeliveryAttempt]) -> NudgeAttempt:
    if not attempts:
        raise WakeDispatchError("persisted nudge requires at least one attempt")
    first = attempts[0]
    for attempt in attempts:
        if (
            attempt.destination_digest != first.destination_digest
            or attempt.session_alias != first.session_alias
            or attempt.reasoning_surface != first.reasoning_surface
            or attempt.wake_transport != first.wake_transport
            or attempt.binding_id != first.binding_id
            or attempt.binding_generation != first.binding_generation
        ):
            raise WakeDispatchError("persisted nudge group has mixed route identity")
    nudge = NudgeAttempt(
        destination_digest=first.destination_digest,
        session_alias=first.session_alias,
        reasoning_surface=first.reasoning_surface,
        wake_transport=first.wake_transport,
        binding_id=first.binding_id,
        binding_generation=first.binding_generation,
        attempts=tuple(attempts),
    )
    expected_group = tuple(sorted(item.attempt_command_id for item in attempts))
    for attempt in attempts:
        if attempt.nudge_id != nudge.nudge_id:
            raise WakeDispatchError("persisted nudge_id does not match its attempts")
        if attempt.nudge_attempt_command_ids != expected_group:
            raise WakeDispatchError("persisted nudge group identity is incomplete")
    return nudge


def _load_persisted_nudge(
    repo: WakeLedgerRepository, record: WakeLedgerRecord
) -> NudgeAttempt:
    parsed = parse_ledger_record(record)
    if not parsed.nudge_id or not parsed.nudge_attempt_command_ids:
        raise WakeDispatchError(
            "unfinished attempt lacks durable nudge reconciliation identity"
        )
    attempts: list[DeliveryAttempt] = []
    for command_id in parsed.nudge_attempt_command_ids:
        persisted = repo.get_by_command_id(command_id)
        if persisted is None:
            raise WakeDispatchError("persisted nudge group is missing an attempt")
        attempt = _attempt_from_record(persisted.record)
        if (
            attempt.nudge_id != parsed.nudge_id
            or attempt.nudge_attempt_command_ids
            != parsed.nudge_attempt_command_ids
        ):
            raise WakeDispatchError("persisted nudge group identity disagrees")
        attempts.append(attempt)
    return _nudge_attempt_from(attempts)


def _latest_attempt_phase(
    records: Sequence[WakeLedgerRecord], attempt_n: int
) -> LedgerPhase | None:
    phases = [
        record.phase
        for record in records
        if record.attempt_n == attempt_n
        and record.phase
        in {
            LedgerPhase.ACCEPTED,
            LedgerPhase.DELIVERED,
            LedgerPhase.FAILED,
            LedgerPhase.TARGET_UNAVAILABLE,
        }
    ]
    return phases[-1] if phases else None


def _state_for_phase(phase: LedgerPhase) -> PersistedNudgeState:
    return PersistedNudgeState(phase.value)


def _reconciliation_required(
    nudge_attempt: NudgeAttempt,
) -> PersistedNudgeResult:
    return PersistedNudgeResult(
        state=PersistedNudgeState.RECONCILIATION_REQUIRED,
        nudge_attempt=nudge_attempt,
    )


async def dispatch_persisted_nudge(
    repo: WakeLedgerRepository,
    pairs: Sequence[tuple[WakeObligation, WakeRoute]],
    *,
    dispatcher: WakeDispatcher,
    binding: RuntimeBinding | None = None,
    descriptor: WakeTransportDescriptor | None = None,
    retry_policy: WakeRetryPolicy | None = None,
    target_registry: SessionTargetRegistry | None = None,
) -> PersistedNudgeResult:
    """Persist one exact nudge before making at most one provider submission."""

    if not isinstance(repo, WakeLedgerRepository):
        raise WakeDispatchError("persisted dispatch requires WakeLedgerRepository")
    if not pairs:
        raise WakeDispatchError("persisted dispatch requires at least one route")
    obligation_ids = [obligation.obligation_id for obligation, _route in pairs]
    if len(obligation_ids) != len(set(obligation_ids)):
        raise WakeDispatchError("persisted dispatch refuses duplicate obligations")
    first_obligation, first_route = pairs[0]
    resolved_descriptor = descriptor or _descriptor(first_route.wake_transport)
    if str(getattr(dispatcher, "transport_id", "") or "") != first_route.wake_transport:
        raise WakeDispatchError(
            "dispatcher transport identity does not match the canonical route"
        )
    policy = retry_policy if retry_policy is not None else UNARMED_RETRY_POLICY
    if not policy.armed:
        raise WakeDispatchError("automated dispatch refuses an unarmed retry policy")

    records_by_obligation: dict[str, tuple[WakeLedgerRecord, ...]] = {}
    unfinished: WakeLedgerRecord | None = None
    terminal_seed: WakeLedgerRecord | None = None
    terminal_phases: list[LedgerPhase] = []
    for obligation, route in pairs:
        if route.obligation_id != obligation.obligation_id:
            raise WakeDispatchError("route obligation_id does not match the wake")
        records = tuple(
            item.record for item in repo.list_records(obligation.obligation_id)
        )
        records_by_obligation[obligation.obligation_id] = records
        if not any(record.phase is LedgerPhase.WAKE_REQUESTED for record in records):
            raise WakeDispatchError("persisted dispatch requires WAKE_REQUESTED")
        pending_n = unfinished_attempt_n(records)
        if pending_n is not None:
            candidate = next(
                record
                for record in records
                if record.phase is LedgerPhase.DELIVERY_ATTEMPT
                and record.attempt_n == pending_n
            )
            unfinished = unfinished or candidate
        attempt_records = [
            record for record in records if record.phase is LedgerPhase.DELIVERY_ATTEMPT
        ]
        if attempt_records:
            latest = attempt_records[-1]
            terminal = _latest_attempt_phase(records, int(latest.attempt_n or 0))
            if terminal is not None:
                terminal_seed = terminal_seed or latest
                terminal_phases.append(terminal)

    if unfinished is not None:
        nudge_attempt = _load_persisted_nudge(repo, unfinished)
        return _reconciliation_required(nudge_attempt)

    if terminal_seed is not None:
        if len(terminal_phases) != len(pairs):
            raise WakeDispatchError(
                "persisted nudge group has partial terminal evidence"
            )
        if len(set(terminal_phases)) != 1:
            raise WakeDispatchError("persisted nudge terminal phases disagree")
        nudge_attempt = _load_persisted_nudge(repo, terminal_seed)
        return PersistedNudgeResult(
            state=_state_for_phase(terminal_phases[0]),
            nudge_attempt=nudge_attempt,
        )

    if first_route.human_required or not first_route.delivery_allowed:
        raise WakeDispatchError("persisted provider path requires an allowed route")
    _assert_binding_ready(binding, first_route, resolved_descriptor)
    plan = coalesce_nudge([route for _obligation, route in pairs])
    base_attempts = tuple(
        make_delivery_attempt(
            obligation,
            route,
            attempt_n=next_attempt_n(records_by_obligation[obligation.obligation_id]),
        )
        for obligation, route in pairs
    )
    command_ids = tuple(sorted(item.attempt_command_id for item in base_attempts))
    nudge_id = mint_nudge_id(plan.destination_digest, command_ids)
    attempts = tuple(
        dataclasses.replace(
            attempt,
            nudge_id=nudge_id,
            nudge_attempt_command_ids=command_ids,
        )
        for attempt in base_attempts
    )
    nudge_attempt = _nudge_attempt_from(attempts)
    persisted = repo.append_records_atomic(
        tuple(
            (attempt_record(attempt, LedgerPhase.DELIVERY_ATTEMPT), obligation)
            for attempt, (obligation, _route) in zip(attempts, pairs, strict=True)
        )
    )
    if not all(item.inserted for item in persisted):
        return _reconciliation_required(nudge_attempt)

    wake = _nudge_from(attempts, binding=binding, first_route=first_route)
    target_ack_projection: TrustedWorkerWakeAckProjection | None = None
    try:
        raw_completion = await dispatcher.nudge(wake)
        raw_transport, target_ack_projection = normalize_transport_completion(
            raw_completion
        )
        transport = authenticate_transport_receipt(
            raw_transport, expected_nudge_id=wake.nudge_id
        )
    except WakePreSubmitError as exc:
        transport = TransportReceipt(
            outcome=exc.outcome,
            reason_code=exc.reason_code,
            created_at=utc_now_iso(),
            details=(("nudge_id", wake.nudge_id),),
        )
    except Exception:
        return PersistedNudgeResult(
            state=PersistedNudgeState.RECONCILIATION_REQUIRED,
            nudge_attempt=nudge_attempt,
        )

    phase = LedgerPhase(transport.outcome.value)
    terminal_persisted = repo.append_records_atomic(
        tuple(
            (attempt_record(attempt, phase), obligation)
            for attempt, (obligation, _route) in zip(attempts, pairs, strict=True)
        )
    )
    if target_ack_projection is not None:
        if phase is not LedgerPhase.DELIVERED:
            raise WakeDispatchError(
                "Wake ACK projection cannot accompany a non-delivered transport"
            )
        if not all(item.inserted for item in terminal_persisted):
            raise WakeDispatchError(
                "Wake ACK projection requires newly persisted DELIVERED evidence"
            )
        if target_registry is None:
            raise WakeDispatchError(
                "Wake ACK projection requires the current SessionTargetRegistry"
            )
        acknowledge_consumed_wakes(
            repo.runtime,
            target_registry,
            claim=WakeAckClaim(target_ack_projection.obligation_ids),
            trusted=target_ack_projection,
        )
    receipts: list[WakeReceipt] = []
    for attempt, (obligation, route) in zip(attempts, pairs, strict=True):
        receipt = make_receipt(
            outcome=WakeOutcome(transport.outcome.value),
            obligation=obligation,
            route=route,
            reason_code=transport.reason_code,
            created_at=transport.created_at,
            details=dict(transport.details),
            attempt=attempt,
        )
        receipts.append(
            authenticate_receipt(
                receipt,
                obligation=obligation,
                route=route,
                descriptor=resolved_descriptor,
                attempt=attempt,
            )
        )
    return PersistedNudgeResult(
        state=PersistedNudgeState(transport.outcome.value),
        nudge_attempt=nudge_attempt,
        transport_receipt=transport,
        receipts=tuple(receipts),
    )


async def dispatch_nudge(
    pairs: Sequence[tuple[WakeObligation, WakeRoute]],
    *,
    dispatcher: WakeDispatcher | None = None,
    binding: RuntimeBinding | None = None,
    records_by_obligation: Mapping[str, Sequence[WakeLedgerRecord]] | None = None,
    descriptor: WakeTransportDescriptor | None = None,
    retry_policy: WakeRetryPolicy | None = None,
) -> tuple[NudgeAttempt | None, TransportReceipt | None, tuple[WakeReceipt, ...]]:
    if not pairs:
        raise WakeDispatchError("dispatch_nudge requires at least one obligation/route")
    eligible_pairs = []
    for obligation, route in pairs:
        records = () if records_by_obligation is None else records_by_obligation.get(
            obligation.obligation_id, ()
        )
        if records_by_obligation is not None and not eligible_for_nudge(
            obligation.obligation_id,
            records,
            destination_digest=route.destination_digest,
        ):
            continue
        eligible_pairs.append((obligation, route))
    if not eligible_pairs:
        raise WakeDispatchError("no eligible obligations remain for this nudge")
    first_obligation, first_route = eligible_pairs[0]
    resolved_descriptor = descriptor or _descriptor(first_route.wake_transport)
    preflight = UnsupportedWakeDispatcher(first_route.wake_transport)
    if first_route.human_required or not first_route.delivery_allowed:
        fabric = await preflight.wake(first_obligation, first_route)
        authenticated = authenticate_receipt(
            fabric,
            obligation=first_obligation,
            route=first_route,
            descriptor=resolved_descriptor,
            allow_fabric_outcome=True,
        )
        return None, None, (authenticated,)
    policy = retry_policy if retry_policy is not None else UNARMED_RETRY_POLICY
    if not policy.armed:
        raise WakeDispatchError("automated dispatch refuses an unarmed retry policy")
    _assert_binding_ready(binding, first_route, resolved_descriptor)
    plan = coalesce_nudge([route for _obligation, route in eligible_pairs])
    attempts = tuple(
        make_delivery_attempt(
            obligation,
            route,
            attempt_n=next_attempt_n(
                ()
                if records_by_obligation is None
                else records_by_obligation.get(obligation.obligation_id, ())
            ),
        )
        for obligation, route in eligible_pairs
    )
    nudge_attempt = NudgeAttempt(
        destination_digest=plan.destination_digest,
        session_alias=plan.session_alias,
        reasoning_surface=plan.reasoning_surface,
        wake_transport=plan.wake_transport,
        binding_id=plan.binding_id,
        binding_generation=plan.binding_generation,
        attempts=attempts,
    )
    resolved = (
        dispatcher
        if dispatcher is not None
        else dispatcher_for(first_route.wake_transport)
    )
    if str(getattr(resolved, "transport_id", "") or "") != first_route.wake_transport:
        raise WakeDispatchError(
            "dispatcher transport identity does not match the canonical route"
        )
    wake = _nudge_from(attempts, binding=binding, first_route=first_route)
    raw_completion = await resolved.nudge(wake)
    transport, _discarded_projection = normalize_transport_completion(raw_completion)
    authenticated_transport = authenticate_transport_receipt(
        transport, expected_nudge_id=wake.nudge_id
    )
    receipts = []
    for obligation, route, attempt in zip(
        (item[0] for item in eligible_pairs),
        (item[1] for item in eligible_pairs),
        attempts,
        strict=True,
    ):
        receipt = make_receipt(
            outcome=WakeOutcome(authenticated_transport.outcome.value),
            obligation=obligation,
            route=route,
            reason_code=authenticated_transport.reason_code,
            created_at=authenticated_transport.created_at,
            details=dict(authenticated_transport.details),
            attempt=attempt,
        )
        receipts.append(
            authenticate_receipt(
                receipt,
                obligation=obligation,
                route=route,
                descriptor=resolved_descriptor,
                attempt=attempt,
            )
        )
    return nudge_attempt, authenticated_transport, tuple(receipts)


async def dispatch_wake(
    obligation: WakeObligation,
    route: WakeRoute,
    *,
    dispatcher: WakeDispatcher | None = None,
    binding: RuntimeBinding | None = None,
    descriptor: WakeTransportDescriptor | None = None,
) -> WakeReceipt:
    _nudge, _transport, receipts = await dispatch_nudge(
        [(obligation, route)],
        dispatcher=dispatcher,
        binding=binding,
        descriptor=descriptor,
    )
    return receipts[0]


def wake_transport_descriptor(transport_id: str) -> WakeTransportDescriptor:
    return _descriptor(transport_id)


def delivery_record(
    obligation_id: str,
    phase: LedgerPhase,
    *,
    attempt_n: int | None = None,
    route: WakeRoute | None = None,
    obligation: WakeObligation | None = None,
) -> WakeLedgerRecord:
    if phase is LedgerPhase.WAKE_REQUESTED:
        if obligation is None:
            raise WakeDispatchError("WAKE_REQUESTED requires the frozen obligation envelope")
        if obligation.obligation_id != obligation_id:
            raise WakeDispatchError("obligation_id does not match the envelope")
        return requested_record(obligation)
    if route is None:
        raise WakeDispatchError("attempt/delivery records require a route snapshot")
    attempt = DeliveryAttempt(
        obligation_id=obligation_id,
        attempt_n=int(attempt_n or 1),
        attempt_command_id=ledger_command_id(
            obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=attempt_n or 1
        ),
        destination_digest=route.destination_digest,
        route_digest=route.route_digest,
        binding_id=route.binding_id,
        binding_generation=route.binding_generation,
        session_alias=route.session_alias,
        reasoning_surface=route.reasoning_surface,
        wake_transport=route.wake_transport,
    )
    return attempt_record(attempt, phase)


def authenticate_transport_receipt(
    receipt: object,
    *,
    expected_nudge_id: str | None = None,
) -> TransportReceipt:
    if not isinstance(receipt, TransportReceipt):
        raise WakeDispatchError("adapter must return a TransportReceipt")
    if ISO_UTC_RE.fullmatch(str(receipt.created_at or "")) is None:
        raise WakeDispatchError("transport created_at must be UTC ISO-8601")
    if receipt.outcome.value not in TRANSPORT_OUTCOMES:
        raise WakeDispatchError("adapter returned a fabric-only outcome")
    expected = OUTCOME_REASONS[receipt.outcome.value]
    if receipt.reason_code not in expected:
        raise WakeDispatchError("invalid transport reason_code")
    details = _bounded_details(dict(receipt.details))
    found = dict(details).get("nudge_id")
    if expected_nudge_id is not None and found not in (None, expected_nudge_id):
        raise WakeDispatchError("transport receipt nudge_id does not match")
    return dataclasses.replace(receipt, details=details)


def _assert_binding_ready(
    binding: RuntimeBinding | None,
    route: WakeRoute,
    descriptor: WakeTransportDescriptor,
) -> None:
    if not descriptor.requires_runtime_binding:
        return
    if binding is None:
        raise WakeDispatchError("binding is not ready")
    if binding.session_alias != route.session_alias:
        raise WakeDispatchError("runtime binding session_alias does not match the route")
    if binding.binding_id != route.binding_id:
        raise WakeDispatchError("runtime binding id does not match the route")
    if binding.binding_generation != route.binding_generation:
        raise WakeDispatchError("runtime binding generation does not match the route")
    if binding.reasoning_surface not in (None, route.reasoning_surface):
        raise WakeDispatchError("runtime binding reasoning_surface does not match the route")
    if not str(binding.native_handle or "").strip():
        raise WakeDispatchError("binding is not addressable for this transport")


def _descriptor(transport_id: str) -> WakeTransportDescriptor:
    try:
        return canonical_wake_transport_descriptor(transport_id)
    except WakeTransportError as exc:
        raise WakeDispatchError(str(exc)) from exc


def _obligation_id(value: str) -> str:
    token = str(value or "").strip()
    if WAKE_ID_RE.fullmatch(token) is None:
        raise WakeDispatchError("obligation_id must be a canonical WAKE-* identity")
    return token


def _bounded_details(
    details: Mapping[str, object] | None,
) -> tuple[tuple[str, str], ...]:
    bounded: list[tuple[str, str]] = []
    for key, value in (details or {}).items():
        token = str(key).strip()
        if token not in ALLOWED_DETAIL_KEYS or _DETAIL_KEY_RE.fullmatch(token) is None:
            raise WakeDispatchError("receipt detail keys must be the closed typed set")
        if token == "nudge_id":
            text = str(value or "").strip()
            if _NUDGE_ID_RE.fullmatch(text) is None:
                raise WakeDispatchError("receipt nudge_id detail is malformed")
        else:
            text = sanitize_external_text(value, limit=128)
        if not text:
            continue
        bounded.append((token, text))
    return tuple(bounded)


__all__ = [
    "ALLOWED_DETAIL_KEYS",
    "DISPATCHER_INTERFACE_VERSION",
    "FABRIC_ONLY_OUTCOMES",
    "FabricOutcome",
    "LedgerPhase",
    "NudgeAttempt",
    "NudgePlan",
    "ObligationStatus",
    "PersistedNudgeResult",
    "PersistedNudgeState",
    "RECEIPT_SCHEMA",
    "SUCCESS_OUTCOMES",
    "TRANSPORT_OUTCOMES",
    "TYPED_REASON_CODES",
    "TransportOutcome",
    "TransportReceipt",
    "UnsupportedWakeDispatcher",
    "WAKE_TRANSPORT_DESCRIPTORS",
    "WakeDispatchError",
    "WakeDispatcher",
    "WakeEffectUnknownError",
    "WakeLedgerRecord",
    "WakeNudge",
    "WakeOutcome",
    "WakePreSubmitError",
    "WakeReceipt",
    "WakeTransportDescriptor",
    "WakeTransportCompletion",
    "already_delivered_receipt",
    "authenticate_receipt",
    "authenticate_transport_receipt",
    "coalesce_nudge",
    "delivery_record",
    "dispatch_nudge",
    "dispatch_persisted_nudge",
    "dispatch_wake",
    "dispatcher_for",
    "ledger_command_id",
    "make_receipt",
    "mint_nudge_id",
    "normalize_transport_completion",
    "plan_eligible_nudge",
    "reconstruct_status",
    "wake_transport_descriptor",
]
