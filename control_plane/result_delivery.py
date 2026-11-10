"""Pluggable result-return delivery (plan V3 §8a: identities joined
explicitly; one work item → several jobs, so a typed origin must survive
to delivery).

This module owns "where does the verified result go?": an ``OriginRef``
(a ``kind`` string plus opaque caller-supplied ids — no Hermes-specific
field baked in), one ``ResultDeliveryTransport`` per kind behind an
explicit registry.  An UNKNOWN kind is a typed refusal
(``UnknownOriginKindError``), never a silent default and never a drop.
The incumbent Hermes deliverer is wrapped as the transport for
``HERMES_ORIGIN_KIND`` at the seam's install site.  Transport-agnostic:
no integrations import, no HTTP client (a Paperclip gateway is a later
lane).
"""
from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Protocol, runtime_checkable

#: Origin kind of the incumbent return path: a Hermes conversation seat.
HERMES_ORIGIN_KIND = "hermes_conversation"

_ORIGIN_ID_MAX = 256


class UnknownOriginKindError(Exception):
    """Typed refusal: no transport is registered for the origin kind."""

    def __init__(self, kind: str) -> None:
        super().__init__(
            f"no result-delivery transport is registered for origin kind {kind!r}")
        self.kind = kind


def _bounded_text(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > _ORIGIN_ID_MAX:
        raise ValueError(f"{label} must be bounded non-blank text")
    return value


@dataclasses.dataclass(frozen=True)
class OriginRef:
    """WHERE a verified result returns: ``kind`` selects the transport;
    ``ids`` are opaque caller-supplied references (their meaning belongs
    to the origin's transport, not to this type)."""

    kind: str
    ids: Mapping[str, str]

    def __post_init__(self) -> None:
        _bounded_text(self.kind, "origin kind")
        if not isinstance(self.ids, Mapping):
            raise ValueError("origin ids must be a mapping of bounded text")
        for key, value in self.ids.items():
            _bounded_text(key, "origin id name")
            _bounded_text(value, f"origin id {key!r}")


@runtime_checkable
class ResultDeliveryTransport(Protocol):
    """Deliver one verified result payload to its origin; returns a receipt
    mapping whose ``state`` the wiring seam checks against the projection's
    delivery-state vocabulary."""

    async def deliver(
        self, origin: OriginRef, payload: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class HermesResultDeliveryTransport:
    """The incumbent Hermes deliverer (``async deliver(record) -> receipt``)
    as the transport for HERMES_ORIGIN_KIND.  The projected record already
    carries the requester block, so the origin ref is not consulted —
    wrapping preserves today's behavior byte-for-byte."""

    def __init__(self, deliverer: Any) -> None:
        if not callable(getattr(deliverer, "deliver", None)):
            raise TypeError("deliverer must expose an async deliver(record) method")
        self._deliverer = deliverer

    async def deliver(
        self, origin: OriginRef, payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return await self._deliverer.deliver(payload)


class ResultDeliveryRegistry:
    """kind -> transport, explicit.  ``lookup`` NEVER silently defaults:
    an unregistered kind raises ``UnknownOriginKindError``.  Registering a
    kind claims every origin of that kind; re-registration is an
    install-time act (the seam install site owns it)."""

    def __init__(self) -> None:
        self._transports: dict[str, ResultDeliveryTransport] = {}

    def register(self, kind: str, transport: ResultDeliveryTransport) -> None:
        _bounded_text(kind, "origin kind")
        if not callable(getattr(transport, "deliver", None)):
            raise TypeError("transport must expose an async deliver(origin, payload) method")
        self._transports[kind] = transport

    def has(self, kind: str) -> bool:
        return kind in self._transports

    def lookup(self, kind: str) -> ResultDeliveryTransport:
        transport = self._transports.get(kind)
        if transport is None:
            raise UnknownOriginKindError(kind)
        return transport

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._transports))


__all__ = [
    "HERMES_ORIGIN_KIND",
    "HermesResultDeliveryTransport",
    "OriginRef",
    "ResultDeliveryRegistry",
    "ResultDeliveryTransport",
    "UnknownOriginKindError",
]
