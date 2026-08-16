"""Canonical wake-transport descriptors — one implementation-state authority.

``target_enabled`` lives on the session target.  ``transport_implemented``
lives here and nowhere else.  Route construction and dispatcher authentication
must both read this module so they cannot silently disagree.
"""
from __future__ import annotations

import dataclasses

DISPATCHER_INTERFACE_VERSION = "mastermind.wake_dispatcher/v1"

WAKE_TRANSPORTS = frozenset(
    {
        "grok-computer",
        "chatgpt-gui",
        "codex-app-server",
        "human",
    }
)


class WakeTransportError(ValueError):
    """Unknown or contradictory wake-transport configuration."""


@dataclasses.dataclass(frozen=True)
class WakeTransportDescriptor:
    """Non-secret facts about one reviewed wake transport."""

    transport_id: str
    interface_version: str = DISPATCHER_INTERFACE_VERSION
    transport_implemented: bool = False


#: PR-1: every transport is a descriptor only.  Flip a bit here in a separately
#: reviewed adapter PR — never by duplicating the flag on a target or router.
WAKE_TRANSPORT_DESCRIPTORS: dict[str, WakeTransportDescriptor] = {
    name: WakeTransportDescriptor(transport_id=name)
    for name in sorted(WAKE_TRANSPORTS)
}


def wake_transport_descriptor(transport_id: str) -> WakeTransportDescriptor:
    resolved = str(transport_id or "").strip()
    if resolved not in WAKE_TRANSPORTS:
        raise WakeTransportError(f"unknown wake transport {transport_id!r}")
    return WAKE_TRANSPORT_DESCRIPTORS[resolved]


def transport_implemented(wake_transport: str) -> bool:
    return wake_transport_descriptor(wake_transport).transport_implemented


__all__ = [
    "DISPATCHER_INTERFACE_VERSION",
    "WAKE_TRANSPORTS",
    "WAKE_TRANSPORT_DESCRIPTORS",
    "WakeTransportDescriptor",
    "WakeTransportError",
    "transport_implemented",
    "wake_transport_descriptor",
]
