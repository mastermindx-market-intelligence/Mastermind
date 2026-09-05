"""Explicit, in-memory provider dispatcher composition for Executive Wake.

This registry owns no wake state and performs no provider discovery.  It only
maps a canonical, already-reviewed wake transport id to the concrete dispatcher
instance supplied by trusted process composition.  Canonical descriptor state
remains in :mod:`control_plane.wake_transport` and all delivery identity,
receipts and reconciliation remain in the existing Wake Fabric.
"""
from __future__ import annotations

from collections.abc import Mapping

from control_plane.wake_dispatcher import (
    WakeDispatcher,
    WakeDispatchError,
    dispatcher_for,
)
from control_plane.wake_transport import (
    WakeTransportError,
    wake_transport_descriptor,
)


class WakeDispatcherRegistry:
    """Resolve one explicitly composed dispatcher by canonical transport id.

    An unimplemented transport resolves through the existing fail-closed
    ``UnsupportedWakeDispatcher``.  Once the canonical descriptor says a
    transport is implemented, process composition must explicitly provide its
    dispatcher; absence is an error rather than a fake unsupported success.
    """

    def __init__(
        self,
        dispatchers: Mapping[str, WakeDispatcher] | None = None,
    ) -> None:
        supplied = {} if dispatchers is None else dispatchers
        if not isinstance(supplied, Mapping):
            raise WakeDispatchError("wake dispatcher registry requires an explicit mapping")
        resolved: dict[str, WakeDispatcher] = {}
        for raw_transport_id, dispatcher in supplied.items():
            transport_id = str(raw_transport_id or "").strip()
            descriptor = self._descriptor(transport_id)
            if descriptor.transport_id != transport_id:
                raise WakeDispatchError("registered wake transport id is not canonical")
            if not descriptor.transport_implemented:
                raise WakeDispatchError(
                    f"wake transport {transport_id!r} is not marked implemented"
                )
            if dispatcher is None:
                raise WakeDispatchError(
                    f"wake transport {transport_id!r} has no dispatcher instance"
                )
            dispatcher_id = str(getattr(dispatcher, "transport_id", "") or "").strip()
            if dispatcher_id != descriptor.transport_id:
                raise WakeDispatchError(
                    "dispatcher transport identity does not match the canonical descriptor"
                )
            resolved[transport_id] = dispatcher
        self._dispatchers = resolved

    @staticmethod
    def _descriptor(transport_id: str):
        try:
            return wake_transport_descriptor(transport_id)
        except WakeTransportError as exc:
            raise WakeDispatchError(str(exc)) from exc

    def resolve(self, transport_id: str) -> WakeDispatcher:
        descriptor = self._descriptor(str(transport_id or "").strip())
        if not descriptor.transport_implemented:
            return dispatcher_for(descriptor.transport_id)
        dispatcher = self._dispatchers.get(descriptor.transport_id)
        if dispatcher is None:
            raise WakeDispatchError(
                f"wake transport {descriptor.transport_id!r} is implemented "
                "but has no registered dispatcher"
            )
        return dispatcher


__all__ = ["WakeDispatcherRegistry"]
