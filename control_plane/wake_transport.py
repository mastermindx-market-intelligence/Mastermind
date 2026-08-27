"""Canonical wake-transport descriptors — one implementation-state authority.

``target_enabled`` lives on the session target.  ``transport_implemented``
and ``requires_runtime_binding`` live here and nowhere else.  Route
construction and dispatcher authentication must both read this module so they
cannot silently disagree.
"""
from __future__ import annotations

import dataclasses

DISPATCHER_INTERFACE_VERSION = "mastermind.wake_dispatcher/v1"

WAKE_TRANSPORTS = frozenset(
    {
        "grok-computer",
        "chatgpt-gui",
        "codex-app-server",
        "claude-code-session",
        "human",
    }
)
_REQUIRES_BINDING = frozenset(
    {
        "grok-computer",
        "chatgpt-gui",
        "codex-app-server",
        "claude-code-session",
    }
)


class WakeTransportError(ValueError):
    """Unknown or contradictory wake-transport configuration."""


@dataclasses.dataclass(frozen=True)
class WakeTransportDescriptor:
    """Non-secret facts about one reviewed execution interface."""

    transport_id: str
    interface_version: str = DISPATCHER_INTERFACE_VERSION
    transport_implemented: bool = False
    requires_runtime_binding: bool = False


#: Descriptor construction is the single reviewed implementation-state source.
#: PR3 implements only Codex App Server here; Claude remains false until a real
#: installed-host preflight proves the exact native-resume contract.
WAKE_TRANSPORT_DESCRIPTORS: dict[str, WakeTransportDescriptor] = {
    name: WakeTransportDescriptor(
        transport_id=name,
        requires_runtime_binding=name in _REQUIRES_BINDING,
    )
    for name in sorted(WAKE_TRANSPORTS)
}
WAKE_TRANSPORT_DESCRIPTORS["codex-app-server"] = dataclasses.replace(
    WAKE_TRANSPORT_DESCRIPTORS["codex-app-server"],
    transport_implemented=True,
)


def wake_transport_descriptor(transport_id: str) -> WakeTransportDescriptor:
    resolved = str(transport_id or "").strip()
    if resolved not in WAKE_TRANSPORTS:
        raise WakeTransportError(f"unknown wake transport {transport_id!r}")
    return WAKE_TRANSPORT_DESCRIPTORS[resolved]


def transport_implemented(wake_transport: str) -> bool:
    return wake_transport_descriptor(wake_transport).transport_implemented


def requires_runtime_binding(wake_transport: str) -> bool:
    return wake_transport_descriptor(wake_transport).requires_runtime_binding


__all__ = [
    "DISPATCHER_INTERFACE_VERSION",
    "WAKE_TRANSPORTS",
    "WAKE_TRANSPORT_DESCRIPTORS",
    "WakeTransportDescriptor",
    "WakeTransportError",
    "requires_runtime_binding",
    "transport_implemented",
    "wake_transport_descriptor",
]
