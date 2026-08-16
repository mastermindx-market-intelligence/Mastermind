"""Wake delivery + acknowledgement contract — not a second queue.

A persisted WAKE *request* is not a delivered wake.  PR-1 defines the states
and how they later map onto existing Executive OS ``events.command_id``
values.  It does not emit those events, add a table, or arm a transport.

Guarantee
---------
at-least-once external nudge + idempotent wake consumption.

Never exactly-once execution.  ``ALREADY_DELIVERED`` may be reconstructed only
from a durable *delivery* receipt, never from ``WAKE_REQUESTED`` uniqueness.

Crash after ``WAKE_REQUESTED`` and before dispatch leaves the obligation
``PENDING_RETRYABLE``.  A delivered wake without ``TARGET_ACKNOWLEDGED`` stays
distinguishable from an acknowledged wake.

Coalescing (contract only)
--------------------------
N pending obligations for one logical session collapse to one external nudge.
The target drains and acknowledges each obligation.  PR-1 does not queue.
"""
from __future__ import annotations

import dataclasses
import re
from enum import Enum
from typing import Mapping, Protocol, Sequence, runtime_checkable

from common.redaction import sanitize_external_text
from control_plane.session_targets import (
    WAKE_TRANSPORTS,
    RuntimeBinding,
    WakeRoute,
)
from control_plane.wake_events import WAKE_ID_RE, WakeObligation, utc_now_iso


DISPATCHER_INTERFACE_VERSION = "mastermind.wake_dispatcher/v1"
RECEIPT_SCHEMA = "mastermind.wake_receipt.v1"
_DETAIL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ALLOWED_DETAIL_KEYS = frozenset(
    {
        "ledger_command_id",
        "attempt_n",
        "policy_version",
        "coalesced_count",
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
        "delivery_attempt",
        "no_delivery_evidence",
        "unsupported_transport",
        "target_unavailable",
        "transport_failed",
        "delivered",
        "accepted",
    }
)


class WakeDispatchError(ValueError):
    """The dispatcher refused the call or an adapter forged a success receipt."""


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
    {
        WakeOutcome.ACCEPTED,
        WakeOutcome.DELIVERED,
        WakeOutcome.ALREADY_DELIVERED,
    }
)


class LedgerPhase(str, Enum):
    WAKE_REQUESTED = "WAKE_REQUESTED"
    DELIVERY_ATTEMPT = "DELIVERY_ATTEMPT"
    DELIVERED = "DELIVERED"
    ACCEPTED = "ACCEPTED"
    TARGET_ACKNOWLEDGED = "TARGET_ACKNOWLEDGED"


class ObligationStatus(str, Enum):
    NOT_SEEN = "NOT_SEEN"
    PENDING_RETRYABLE = "PENDING_RETRYABLE"
    DELIVERED_UNACKNOWLEDGED = "DELIVERED_UNACKNOWLEDGED"
    TARGET_ACKNOWLEDGED = "TARGET_ACKNOWLEDGED"


@dataclasses.dataclass(frozen=True)
class WakeTransportDescriptor:
    """Non-secret facts about one reviewed wake transport."""

    transport_id: str
    interface_version: str = DISPATCHER_INTERFACE_VERSION
    transport_implemented: bool = False


WAKE_TRANSPORT_DESCRIPTORS: dict[str, WakeTransportDescriptor] = {
    name: WakeTransportDescriptor(transport_id=name)
    for name in sorted(WAKE_TRANSPORTS)
}


def wake_transport_descriptor(transport_id: str) -> WakeTransportDescriptor:
    resolved = str(transport_id).strip()
    if resolved not in WAKE_TRANSPORTS:
        raise WakeDispatchError(f"unknown wake transport {transport_id!r}")
    return WAKE_TRANSPORT_DESCRIPTORS[resolved]


@dataclasses.dataclass(frozen=True)
class WakeReceipt:
    """Auditable outcome of one delivery attempt.  Success without this is invalid."""

    schema: str
    outcome: WakeOutcome
    obligation_id: str
    session_alias: str
    reasoning_surface: str
    wake_transport: str
    route_digest: str
    binding_generation: int
    transport_implemented: bool
    target_enabled: bool
    reason_code: str
    created_at: str
    details: tuple[tuple[str, str], ...] = ()

    def claims_success(self) -> bool:
        return self.outcome in SUCCESS_OUTCOMES

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "outcome": self.outcome.value,
            "obligation_id": self.obligation_id,
            "session_alias": self.session_alias,
            "reasoning_surface": self.reasoning_surface,
            "wake_transport": self.wake_transport,
            "route_digest": self.route_digest,
            "binding_generation": self.binding_generation,
            "transport_implemented": self.transport_implemented,
            "target_enabled": self.target_enabled,
            "reason_code": self.reason_code,
            "created_at": self.created_at,
            "details": dict(self.details),
        }


@dataclasses.dataclass(frozen=True)
class NudgePlan:
    """One external nudge covering one or more pending obligations.

    PR-1 does not send the nudge.  The plan is the contract that later runtime
    must honor: Grok (or any transport) types continue once, Chat Sol drains
    every listed obligation, then acknowledges each one.
    """

    session_alias: str
    reasoning_surface: str
    wake_transport: str
    obligation_ids: tuple[str, ...]
    route_digests: tuple[str, ...]

    @property
    def coalesced(self) -> bool:
        return len(self.obligation_ids) > 1

    def to_dict(self) -> dict[str, object]:
        return {
            "session_alias": self.session_alias,
            "reasoning_surface": self.reasoning_surface,
            "wake_transport": self.wake_transport,
            "obligation_ids": list(self.obligation_ids),
            "route_digests": list(self.route_digests),
            "coalesced": self.coalesced,
            "nudge_count": 1,
        }


def ledger_command_id(
    obligation_id: str,
    phase: LedgerPhase | str,
    *,
    attempt_n: int | None = None,
) -> str:
    """Map a wake lifecycle phase onto existing ``events.command_id``.

    ``WAKE-*`` fits the Executive OS command-id fence.  Delivery retries use a
    generation suffix because ``command_id`` is UNIQUE.
    """

    oid = _obligation_id(obligation_id)
    resolved = phase if isinstance(phase, LedgerPhase) else LedgerPhase(str(phase))
    if resolved is LedgerPhase.WAKE_REQUESTED:
        return oid
    if resolved is LedgerPhase.DELIVERY_ATTEMPT:
        n = int(attempt_n or 0)
        if n < 1:
            raise WakeDispatchError("delivery attempts are numbered from 1")
        return f"{oid}:A{n}"
    if resolved in {LedgerPhase.DELIVERED, LedgerPhase.ACCEPTED}:
        return f"{oid}:DELIVERED"
    return f"{oid}:ACK"


def reconstruct_status(obligation_id: str, command_ids: Sequence[str]) -> ObligationStatus:
    """Derive obligation status from existing Executive OS command_id rows.

    Presence of the request id alone is not delivery evidence.
    """

    oid = _obligation_id(obligation_id)
    seen = {str(item) for item in command_ids}
    if ledger_command_id(oid, LedgerPhase.TARGET_ACKNOWLEDGED) in seen:
        return ObligationStatus.TARGET_ACKNOWLEDGED
    if ledger_command_id(oid, LedgerPhase.DELIVERED) in seen:
        return ObligationStatus.DELIVERED_UNACKNOWLEDGED
    if oid in seen or any(
        item.startswith(f"{oid}:A") and item[len(oid) + 2 :].isdigit()
        for item in seen
    ):
        return ObligationStatus.PENDING_RETRYABLE
    return ObligationStatus.NOT_SEEN


def make_receipt(
    *,
    outcome: WakeOutcome | str,
    obligation: WakeObligation,
    route: WakeRoute,
    reason_code: str,
    created_at: str | None = None,
    details: Mapping[str, object] | None = None,
) -> WakeReceipt:
    resolved_outcome = (
        outcome if isinstance(outcome, WakeOutcome) else WakeOutcome(str(outcome))
    )
    code = str(reason_code or "").strip()
    if code not in TYPED_REASON_CODES:
        raise WakeDispatchError(f"untyped wake reason_code {code!r}")
    return WakeReceipt(
        schema=RECEIPT_SCHEMA,
        outcome=resolved_outcome,
        obligation_id=_obligation_id(obligation.obligation_id),
        session_alias=route.session_alias,
        reasoning_surface=route.reasoning_surface,
        wake_transport=route.wake_transport,
        route_digest=route.route_digest,
        binding_generation=route.binding_generation,
        transport_implemented=route.transport_implemented,
        target_enabled=route.target_enabled,
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
) -> WakeReceipt:
    """Bind a receipt to the expected obligation, route, and transport."""

    if receipt.schema != RECEIPT_SCHEMA:
        raise WakeDispatchError("receipt schema is not the wake-receipt contract")
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
    if receipt.binding_generation != route.binding_generation:
        raise WakeDispatchError("receipt binding_generation does not match the expected route")
    if receipt.wake_transport != descriptor.transport_id:
        raise WakeDispatchError("receipt wake_transport does not match the descriptor")
    if receipt.transport_implemented != descriptor.transport_implemented:
        raise WakeDispatchError(
            "receipt transport_implemented flag does not match the descriptor"
        )
    if receipt.claims_success() and not descriptor.transport_implemented:
        raise WakeDispatchError(
            "unimplemented wake transport cannot claim ACCEPTED, DELIVERED, "
            "or ALREADY_DELIVERED"
        )
    if receipt.claims_success() and not route.delivery_allowed:
        raise WakeDispatchError("delivery is not allowed for this route")
    return receipt


def already_delivered_receipt(
    obligation: WakeObligation,
    route: WakeRoute,
    *,
    found_command_id: str,
    created_at: str | None = None,
) -> WakeReceipt:
    """Trusted replay coalescing.  Requires actual delivery evidence.

    ``command_id == obligation_id`` is only ``WAKE_REQUESTED`` and must not
    produce ``ALREADY_DELIVERED``.
    """

    expected = ledger_command_id(obligation.obligation_id, LedgerPhase.DELIVERED)
    if found_command_id != expected:
        raise WakeDispatchError("no delivery evidence for ALREADY_DELIVERED")
    if route.obligation_id != obligation.obligation_id:
        raise WakeDispatchError("route obligation_id does not match the wake")
    return make_receipt(
        outcome=WakeOutcome.ALREADY_DELIVERED,
        obligation=obligation,
        route=route,
        reason_code="command_id_replay",
        created_at=created_at,
        details={"ledger_command_id": found_command_id},
    )


def coalesce_nudge(routes: Sequence[WakeRoute]) -> NudgePlan:
    """One logical session → one external nudge covering every obligation."""

    if not routes:
        raise WakeDispatchError("coalesce_nudge requires at least one route")
    first = routes[0]
    obligation_ids: list[str] = []
    digests: list[str] = []
    for route in routes:
        if route.session_alias != first.session_alias:
            raise WakeDispatchError("cannot coalesce routes for different sessions")
        if route.reasoning_surface != first.reasoning_surface:
            raise WakeDispatchError("cannot coalesce mixed reasoning surfaces")
        if route.wake_transport != first.wake_transport:
            raise WakeDispatchError("cannot coalesce mixed wake transports")
        if route.obligation_id not in obligation_ids:
            obligation_ids.append(route.obligation_id)
            digests.append(route.route_digest)
    return NudgePlan(
        session_alias=first.session_alias,
        reasoning_surface=first.reasoning_surface,
        wake_transport=first.wake_transport,
        obligation_ids=tuple(obligation_ids),
        route_digests=tuple(digests),
    )


@runtime_checkable
class WakeDispatcher(Protocol):
    async def wake(
        self, obligation: WakeObligation, route: WakeRoute
    ) -> WakeReceipt: ...


class UnsupportedWakeDispatcher:
    """PR-1 default: known transports exist, none are armed."""

    def __init__(self, transport_id: str) -> None:
        self.descriptor = wake_transport_descriptor(transport_id)

    async def wake(
        self, obligation: WakeObligation, route: WakeRoute
    ) -> WakeReceipt:
        if route.wake_transport != self.descriptor.transport_id:
            raise WakeDispatchError("dispatcher transport does not match the route")
        if route.obligation_id != obligation.obligation_id:
            return make_receipt(
                outcome=WakeOutcome.REFUSED,
                obligation=obligation,
                route=route,
                reason_code="obligation_mismatch",
            )
        if route.human_required:
            return make_receipt(
                outcome=WakeOutcome.HUMAN_REQUIRED,
                obligation=obligation,
                route=route,
                reason_code="human_required",
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


def dispatcher_for(transport_id: str) -> WakeDispatcher:
    descriptor = wake_transport_descriptor(transport_id)
    if descriptor.transport_implemented:
        raise WakeDispatchError(
            f"wake transport {transport_id!r} is marked implemented but PR-1 "
            "ships no production transport"
        )
    return UnsupportedWakeDispatcher(descriptor.transport_id)


async def dispatch_wake(
    obligation: WakeObligation,
    route: WakeRoute,
    *,
    dispatcher: WakeDispatcher | None = None,
    binding: RuntimeBinding | None = None,
) -> WakeReceipt:
    """Validate route/obligation, invoke the adapter, authenticate the receipt."""

    if route.obligation_id != obligation.obligation_id:
        raise WakeDispatchError("route obligation_id does not match the wake")
    if binding is not None:
        if binding.session_alias != route.session_alias:
            raise WakeDispatchError("runtime binding session_alias does not match the route")
        if binding.binding_generation != route.binding_generation:
            raise WakeDispatchError("runtime binding generation does not match the route")
    resolved = (
        dispatcher
        if dispatcher is not None
        else dispatcher_for(route.wake_transport)
    )
    receipt = await resolved.wake(obligation, route)
    return authenticate_receipt(
        receipt,
        obligation=obligation,
        route=route,
        descriptor=wake_transport_descriptor(route.wake_transport),
    )


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
    "LedgerPhase",
    "NudgePlan",
    "ObligationStatus",
    "RECEIPT_SCHEMA",
    "SUCCESS_OUTCOMES",
    "TYPED_REASON_CODES",
    "WAKE_TRANSPORT_DESCRIPTORS",
    "UnsupportedWakeDispatcher",
    "WakeDispatchError",
    "WakeDispatcher",
    "WakeOutcome",
    "WakeReceipt",
    "WakeTransportDescriptor",
    "already_delivered_receipt",
    "authenticate_receipt",
    "coalesce_nudge",
    "dispatch_wake",
    "dispatcher_for",
    "ledger_command_id",
    "make_receipt",
    "reconstruct_status",
    "wake_transport_descriptor",
]
