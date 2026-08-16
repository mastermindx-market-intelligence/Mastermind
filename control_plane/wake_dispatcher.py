"""Provider-neutral Wake Dispatcher contract.

Mirrors :mod:`control_plane.worker_adapter`: a typed protocol plus reviewed
adapter descriptors.  PR-1 implements no GUI automation, no Codex App Server
client, and no Grok computer-control.  Every known adapter is registered as
``implemented=False`` and the default dispatcher returns ``UNSUPPORTED`` with
an auditable receipt.

An adapter must not claim success.  :func:`authenticate_receipt` refuses
``ACCEPTED`` / ``DELIVERED`` / ``ALREADY_DELIVERED`` from an unimplemented
descriptor.  Replay coalescing is trusted fabric code
(:func:`already_delivered_receipt`), not an adapter lie, and is intended for
PR-2 once Executive OS persists ``command_id = wake.event_id``.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Protocol, runtime_checkable

from control_plane.session_targets import ADAPTER_TYPES, SessionTarget
from control_plane.wake_events import WAKE_ID_RE, WakeEvent, utc_now_iso


DISPATCHER_INTERFACE_VERSION = "mastermind.wake_dispatcher/v1"
RECEIPT_SCHEMA = "mastermind.wake_receipt.v1"


class WakeDispatchError(ValueError):
    """The dispatcher refused the call or an adapter forged a success receipt."""


class WakeOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    DELIVERED = "DELIVERED"
    ALREADY_DELIVERED = "ALREADY_DELIVERED"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    REFUSED = "REFUSED"
    FAILED = "FAILED"


SUCCESS_OUTCOMES = frozenset(
    {
        WakeOutcome.ACCEPTED,
        WakeOutcome.DELIVERED,
        WakeOutcome.ALREADY_DELIVERED,
    }
)


@dataclasses.dataclass(frozen=True)
class WakeAdapterDescriptor:
    """Non-secret facts about one reviewed wake transport."""

    adapter_id: str
    interface_version: str = DISPATCHER_INTERFACE_VERSION
    implemented: bool = False


WAKE_ADAPTER_DESCRIPTORS: dict[str, WakeAdapterDescriptor] = {
    "codex-app-server": WakeAdapterDescriptor(adapter_id="codex-app-server"),
    "codex-cli": WakeAdapterDescriptor(adapter_id="codex-cli"),
    "chatgpt-gui": WakeAdapterDescriptor(adapter_id="chatgpt-gui"),
    "grok-computer": WakeAdapterDescriptor(adapter_id="grok-computer"),
}


def wake_adapter_descriptor(adapter_id: str) -> WakeAdapterDescriptor:
    resolved = str(adapter_id).strip().lower()
    if resolved not in ADAPTER_TYPES:
        raise WakeDispatchError(f"unknown wake adapter {adapter_id!r}")
    try:
        return WAKE_ADAPTER_DESCRIPTORS[resolved]
    except KeyError as exc:
        raise WakeDispatchError(f"unknown wake adapter {adapter_id!r}") from exc


@dataclasses.dataclass(frozen=True)
class WakeReceipt:
    """Auditable outcome of one wake attempt.  Success without this is invalid."""

    schema: str
    outcome: WakeOutcome
    event_id: str
    session_alias: str
    adapter_type: str
    implemented: bool
    reason_code: str
    created_at: str
    details: tuple[tuple[str, str], ...] = ()

    def claims_success(self) -> bool:
        return self.outcome in SUCCESS_OUTCOMES

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "outcome": self.outcome.value,
            "event_id": self.event_id,
            "session_alias": self.session_alias,
            "adapter_type": self.adapter_type,
            "implemented": self.implemented,
            "reason_code": self.reason_code,
            "created_at": self.created_at,
            "details": dict(self.details),
        }


def make_receipt(
    *,
    outcome: WakeOutcome | str,
    event: WakeEvent,
    target: SessionTarget,
    reason_code: str,
    implemented: bool,
    created_at: str | None = None,
    details: dict[str, str] | None = None,
) -> WakeReceipt:
    resolved_outcome = (
        outcome if isinstance(outcome, WakeOutcome) else WakeOutcome(str(outcome))
    )
    if WAKE_ID_RE.fullmatch(event.event_id) is None:
        raise WakeDispatchError("receipt event_id must be a canonical WAKE-* identity")
    bounded: list[tuple[str, str]] = []
    for key, value in (details or {}).items():
        token = str(key).strip()
        if not token or len(token) > 64:
            raise WakeDispatchError("receipt detail keys must be bounded identifiers")
        text = str(value)
        if len(text) > 256:
            raise WakeDispatchError("receipt detail values exceed the 256-char ceiling")
        bounded.append((token, text))
    return WakeReceipt(
        schema=RECEIPT_SCHEMA,
        outcome=resolved_outcome,
        event_id=event.event_id,
        session_alias=target.session_alias,
        adapter_type=target.adapter_type,
        implemented=implemented,
        reason_code=str(reason_code).strip() or "unspecified",
        created_at=created_at or utc_now_iso(),
        details=tuple(bounded),
    )


def authenticate_receipt(
    receipt: WakeReceipt, descriptor: WakeAdapterDescriptor
) -> WakeReceipt:
    """Refuse a success claim from an unimplemented or mismatched adapter."""

    if receipt.schema != RECEIPT_SCHEMA:
        raise WakeDispatchError("receipt schema is not the wake-receipt contract")
    if receipt.adapter_type != descriptor.adapter_id:
        raise WakeDispatchError("receipt adapter_type does not match the descriptor")
    if receipt.claims_success() and not descriptor.implemented:
        raise WakeDispatchError(
            "unimplemented wake adapter cannot claim ACCEPTED, DELIVERED, "
            "or ALREADY_DELIVERED"
        )
    if receipt.implemented != descriptor.implemented:
        raise WakeDispatchError("receipt implemented flag does not match the descriptor")
    return receipt


def already_delivered_receipt(
    event: WakeEvent,
    target: SessionTarget,
    *,
    found_command_id: str,
    created_at: str | None = None,
) -> WakeReceipt:
    """Trusted replay coalescing for PR-2 command_id uniqueness.

    This is fabric code, not an adapter.  It may only fire when the durable
    Executive OS event row already carries this wake's ``event_id`` as
    ``command_id``.
    """

    if found_command_id != event.event_id:
        raise WakeDispatchError("replay command_id does not match the wake event")
    if event.session_alias != target.session_alias:
        raise WakeDispatchError("replay target does not match the wake event")
    if event.target_seat != target.target_seat:
        raise WakeDispatchError("replay seat does not match the wake event")
    return make_receipt(
        outcome=WakeOutcome.ALREADY_DELIVERED,
        event=event,
        target=target,
        reason_code="command_id_replay",
        implemented=True,
        created_at=created_at,
        details={"command_id": found_command_id},
    )


@runtime_checkable
class WakeDispatcher(Protocol):
    """Minimum wake transport consumed by later Control Panel / runtime glue."""

    async def wake(self, target: SessionTarget, event: WakeEvent) -> WakeReceipt: ...


class UnsupportedWakeDispatcher:
    """PR-1 default: known adapter types exist, none are armed."""

    def __init__(self, adapter_id: str) -> None:
        self.descriptor = wake_adapter_descriptor(adapter_id)

    async def wake(self, target: SessionTarget, event: WakeEvent) -> WakeReceipt:
        if target.adapter_type != self.descriptor.adapter_id:
            raise WakeDispatchError("dispatcher adapter_type does not match the target")
        if event.session_alias != target.session_alias:
            return make_receipt(
                outcome=WakeOutcome.REFUSED,
                event=event,
                target=target,
                reason_code="session_alias_mismatch",
                implemented=False,
            )
        if event.target_seat != target.target_seat:
            return make_receipt(
                outcome=WakeOutcome.REFUSED,
                event=event,
                target=target,
                reason_code="target_seat_mismatch",
                implemented=False,
            )
        return make_receipt(
            outcome=WakeOutcome.UNSUPPORTED,
            event=event,
            target=target,
            reason_code="adapter_not_implemented",
            implemented=False,
            details={"adapter_type": target.adapter_type},
        )


def dispatcher_for(adapter_id: str) -> WakeDispatcher:
    """Resolve a reviewed adapter.  Unknown ids fail closed."""

    descriptor = wake_adapter_descriptor(adapter_id)
    if descriptor.implemented:
        raise WakeDispatchError(
            f"wake adapter {adapter_id!r} is marked implemented but PR-1 "
            "ships no production transport"
        )
    return UnsupportedWakeDispatcher(descriptor.adapter_id)


async def dispatch_wake(
    target: SessionTarget,
    event: WakeEvent,
    *,
    dispatcher: WakeDispatcher | None = None,
) -> WakeReceipt:
    """Validate target/event, invoke the adapter, authenticate the receipt."""

    if event.session_alias != target.session_alias:
        raise WakeDispatchError("event session_alias does not match the target")
    if event.target_seat != target.target_seat:
        raise WakeDispatchError("event target_seat does not match the target")
    resolved = dispatcher if dispatcher is not None else dispatcher_for(target.adapter_type)
    receipt = await resolved.wake(target, event)
    return authenticate_receipt(receipt, wake_adapter_descriptor(target.adapter_type))


__all__ = [
    "DISPATCHER_INTERFACE_VERSION",
    "RECEIPT_SCHEMA",
    "SUCCESS_OUTCOMES",
    "WAKE_ADAPTER_DESCRIPTORS",
    "UnsupportedWakeDispatcher",
    "WakeAdapterDescriptor",
    "WakeDispatchError",
    "WakeDispatcher",
    "WakeOutcome",
    "WakeReceipt",
    "already_delivered_receipt",
    "authenticate_receipt",
    "dispatch_wake",
    "dispatcher_for",
    "make_receipt",
    "wake_adapter_descriptor",
]
