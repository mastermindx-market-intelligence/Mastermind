"""Wake delivery + acknowledgement contract — not a second queue.

A persisted WAKE *request* is not a delivered wake.  Delivery attempts are
route-specific.  The external transport unit is a :class:`NudgeAttempt`.
Acknowledgement and source resolution are obligation-global.

Guarantee: at-least-once external nudge + idempotent consumption.
``ALREADY_DELIVERED`` is a fabric reconciliation result, never a transport
result.
"""
from __future__ import annotations

import dataclasses
import re
from enum import Enum
from typing import Mapping, Protocol, Sequence, runtime_checkable

from common.redaction import sanitize_external_text
from control_plane.session_targets import RuntimeBinding, WakeRoute
from control_plane.wake_events import ISO_UTC_RE, WAKE_ID_RE, WakeObligation, utc_now_iso
from control_plane.wake_ledger import (
    DeliveryAttempt,
    LedgerPhase,
    ObligationStatus,
    WakeLedgerRecord,
    already_delivered_to_destination,
    attempt_record,
    eligible_for_nudge,
    ledger_command_id,
    make_delivery_attempt,
    reconstruct_status,
)
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


class TransportOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    DELIVERED = "DELIVERED"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    FAILED = "FAILED"


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
        if eligible_for_nudge(route.obligation_id, records_by_obligation.get(route.obligation_id, ()))
    ]
    return coalesce_nudge(eligible)


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
    return WakeReceipt(
        schema=RECEIPT_SCHEMA,
        outcome=resolved_outcome,
        obligation_id=_obligation_id(obligation.obligation_id),
        attempt_n=n,
        attempt_command_id=command,
        session_alias=route.session_alias,
        reasoning_surface=route.reasoning_surface,
        wake_transport=route.wake_transport,
        route_digest=route.route_digest,
        destination_digest=route.destination_digest,
        binding_id=route.binding_id,
        binding_generation=route.binding_generation,
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
    if receipt.session_alias != route.session_alias:
        raise WakeDispatchError("receipt session_alias does not match the expected route")
    if receipt.reasoning_surface != route.reasoning_surface:
        raise WakeDispatchError("receipt reasoning_surface does not match the expected route")
    if receipt.wake_transport != route.wake_transport:
        raise WakeDispatchError("receipt wake_transport does not match the expected route")
    if receipt.route_digest != route.route_digest:
        raise WakeDispatchError("receipt route_digest does not match the expected route")
    if receipt.destination_digest != route.destination_digest:
        raise WakeDispatchError("receipt destination_digest does not match the expected route")
    if receipt.binding_generation != route.binding_generation:
        raise WakeDispatchError("receipt binding_generation does not match the expected route")
    if receipt.binding_id != route.binding_id:
        raise WakeDispatchError("receipt binding_id does not match the expected route")
    if receipt.wake_transport != descriptor.transport_id:
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
        if not attempt.matches_route(route):
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
    _bounded_details(dict(receipt.details))
    return receipt


def already_delivered_receipt(
    obligation: WakeObligation,
    route: WakeRoute,
    *,
    found: WakeLedgerRecord,
    created_at: str | None = None,
) -> WakeReceipt:
    if found.phase is not LedgerPhase.DELIVERED:
        raise WakeDispatchError("no delivery evidence for ALREADY_DELIVERED")
    if found.destination_digest != route.destination_digest:
        raise WakeDispatchError("delivery evidence does not match the current destination")
    attempt_n = int(found.attempt_n or 0)
    return authenticate_receipt(
        make_receipt(
            outcome=WakeOutcome.ALREADY_DELIVERED,
            obligation=obligation,
            route=route,
            reason_code="command_id_replay",
            created_at=created_at,
            details={
                "ledger_command_id": found.command_id,
                "attempt_n": str(attempt_n),
            },
            attempt=DeliveryAttempt(
                obligation_id=obligation.obligation_id,
                attempt_n=attempt_n,
                attempt_command_id=ledger_command_id(
                    obligation.obligation_id,
                    LedgerPhase.DELIVERY_ATTEMPT,
                    attempt_n=attempt_n,
                ),
                destination_digest=route.destination_digest,
                route_digest=route.route_digest,
                binding_id=route.binding_id,
                binding_generation=route.binding_generation,
                session_alias=route.session_alias,
                reasoning_surface=route.reasoning_surface,
                wake_transport=route.wake_transport,
            ),
        ),
        obligation=obligation,
        route=route,
        descriptor=_descriptor(route.wake_transport),
        allow_fabric_outcome=True,
    )


@runtime_checkable
class WakeDispatcher(Protocol):
    async def nudge(self, wake: WakeNudge) -> TransportReceipt: ...


class UnsupportedWakeDispatcher:
    def __init__(self, transport_id: str) -> None:
        self.descriptor = _descriptor(transport_id)

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
    )


async def dispatch_nudge(
    pairs: Sequence[tuple[WakeObligation, WakeRoute]],
    *,
    dispatcher: WakeDispatcher | None = None,
    binding: RuntimeBinding | None = None,
    attempt_n: int = 1,
    records_by_obligation: Mapping[str, Sequence[WakeLedgerRecord]] | None = None,
    descriptor: WakeTransportDescriptor | None = None,
) -> tuple[NudgeAttempt, TransportReceipt | None, tuple[WakeReceipt, ...]]:
    if not pairs:
        raise WakeDispatchError("dispatch_nudge requires at least one obligation/route")
    eligible_pairs = []
    for obligation, route in pairs:
        if records_by_obligation is not None and not eligible_for_nudge(
            obligation.obligation_id,
            records_by_obligation.get(obligation.obligation_id, ()),
        ):
            continue
        eligible_pairs.append((obligation, route))
    if not eligible_pairs:
        raise WakeDispatchError("no eligible obligations remain for this nudge")
    plan = coalesce_nudge([route for _obligation, route in eligible_pairs])
    attempts = tuple(
        make_delivery_attempt(obligation, route, attempt_n=attempt_n)
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
    first_obligation, first_route = eligible_pairs[0]
    resolved_descriptor = descriptor or _descriptor(first_route.wake_transport)
    preflight = dispatcher_for(first_route.wake_transport)
    if first_route.human_required or not first_route.delivery_allowed:
        fabric = await preflight.wake(first_obligation, first_route)
        authenticated = authenticate_receipt(
            fabric,
            obligation=first_obligation,
            route=first_route,
            descriptor=resolved_descriptor,
            attempt=attempts[0],
            allow_fabric_outcome=True,
        )
        return nudge_attempt, None, (authenticated,)
    resolved = dispatcher if dispatcher is not None else preflight
    wake = _nudge_from(attempts, binding=binding, first_route=first_route)
    transport = await resolved.nudge(wake)
    if not isinstance(transport, TransportReceipt):
        raise WakeDispatchError("adapter must return a TransportReceipt")
    if transport.outcome.value not in TRANSPORT_OUTCOMES:
        raise WakeDispatchError("adapter returned a fabric-only outcome")
    receipts = []
    for obligation, route, attempt in zip(
        (item[0] for item in eligible_pairs),
        (item[1] for item in eligible_pairs),
        attempts,
        strict=True,
    ):
        reasons = OUTCOME_REASONS[transport.outcome.value]
        reason_code = transport.reason_code
        if reason_code not in reasons:
            reason_code = sorted(reasons)[0]
        receipt = make_receipt(
            outcome=WakeOutcome(transport.outcome.value),
            obligation=obligation,
            route=route,
            reason_code=reason_code,
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
    return nudge_attempt, transport, tuple(receipts)


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
) -> WakeLedgerRecord:
    if phase is LedgerPhase.WAKE_REQUESTED:
        return WakeLedgerRecord(command_id=obligation_id, phase=phase)
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
    "WakeLedgerRecord",
    "WakeNudge",
    "WakeOutcome",
    "WakeReceipt",
    "WakeTransportDescriptor",
    "already_delivered_receipt",
    "authenticate_receipt",
    "coalesce_nudge",
    "delivery_record",
    "dispatch_nudge",
    "dispatch_wake",
    "dispatcher_for",
    "ledger_command_id",
    "make_receipt",
    "plan_eligible_nudge",
    "reconstruct_status",
    "wake_transport_descriptor",
]
