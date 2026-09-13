"""Provider-neutral attended DevBox port.

The port is transport-only composition. Implementations do not mint Executive
Jobs/Attempts/Workers, caller identity, target selection or source authority.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclasses.dataclass(frozen=True)
class DevBoxCaller:
    """Request-local authenticated caller projection, never a grant issuer."""

    subject_digest: str
    client_ref: str
    resource: str
    scopes: tuple[str, ...]
    expires_at: int


class DevBoxPortRefused(RuntimeError):
    """Closed provider/resource refusal safe to surface as a code only."""

    _CODES = frozenset(
        {
            "DEVBOX_REFUSED",
            "BINDING_CHANGED",
            "OPERATION_CONFLICT",
            "PROCESS_NOT_FOUND",
            "PROCESS_IDENTITY_UNKNOWN",
            "EFFECT_UNKNOWN",
            "CANCEL_UNCERTAIN",
        }
    )

    def __init__(self, code: str = "DEVBOX_REFUSED") -> None:
        if code not in self._CODES:
            raise ValueError("unknown DevBox port refusal")
        self.code = code
        super().__init__(code)


@runtime_checkable
class DevBoxPort(Protocol):
    async def call(
        self,
        caller: DevBoxCaller,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


__all__ = ["DevBoxCaller", "DevBoxPort", "DevBoxPortRefused"]
