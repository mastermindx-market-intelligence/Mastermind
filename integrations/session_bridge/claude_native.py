"""Exact live-Claude attention through the incumbent session-management owner.

This module does not open Claude inbox sockets, read provider credentials, inspect
session titles, or own provider session lifecycle. The installed host injects
the already-attested Claude session-management owner through a closed port.

A target is addressable only when the management owner supplies one exact
session id + host + generation tuple. A successful send is attention evidence
only: it is not PICKUP_ACK, START, RESULT, target consumption, or parent
consumption. Ambiguous post-send outcomes reconcile through the same owner and
are never resent or failed over.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import inspect
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from uuid import UUID

from .native_wire import AttentionReference, _notice
from .schemas import BridgeError

_GENERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_MAX_TARGETS = 256


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _uuid(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Claude session id is invalid")
    try:
        normalized = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError("Claude session id is invalid") from None
    if normalized != value:
        raise ValueError("Claude session id is invalid")
    return value


def _generation(value: Any) -> str:
    if not isinstance(value, str) or _GENERATION_RE.fullmatch(value) is None:
        raise ValueError("Claude session generation is invalid")
    return value


def _host(value: Any) -> str:
    if not isinstance(value, str) or _HOST_RE.fullmatch(value) is None:
        raise ValueError("Claude host binding is invalid")
    return value


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclasses.dataclass(frozen=True)
class ClaudeManagedSession:
    """Host-normalized current session fact from the incumbent management owner."""

    session_id: str
    generation: str
    addressable: bool
    host_ref: str

    def __post_init__(self) -> None:
        _uuid(self.session_id)
        _generation(self.generation)
        _host(self.host_ref)
        if type(self.addressable) is not bool:
            raise ValueError("Claude session addressability is invalid")


@dataclasses.dataclass(frozen=True)
class ClaudeManagementSendReceipt:
    """Closed send result normalized by the incumbent management owner."""

    state: str

    def __post_init__(self) -> None:
        if self.state not in {"accepted", "refused"}:
            raise ValueError("Claude management send state is invalid")


class ClaudeSessionManagementPort(Protocol):
    """Injected incumbent Claude session-management capability.

    list/get are current read facts. send_message is the one modifying provider
    call. reconcile_message is a same-owner read/reconciliation path and must
    never send the message again.
    """

    def list_sessions(self) -> Sequence[ClaudeManagedSession]: ...

    def get_session(self, session_id: str) -> ClaudeManagedSession | None: ...

    def send_message(
        self, session_id: str, message: str
    ) -> ClaudeManagementSendReceipt | Any: ...

    def reconcile_message(
        self, session_id: str, operation_key: str
    ) -> ClaudeManagementSendReceipt | None | Any: ...


@dataclasses.dataclass(frozen=True)
class ClaudeNativeTarget:
    """Private exact target binding; only public_projection crosses MCP."""

    target_ref: str
    session_id: str
    generation: str
    host_ref: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.target_ref, str)
            or not self.target_ref.startswith("claude:")
            or len(self.target_ref) != len("claude:") + 64
        ):
            raise ValueError("Claude target ref is invalid")
        _uuid(self.session_id)
        _generation(self.generation)
        _host(self.host_ref)

    def public_projection(self) -> dict[str, Any]:
        return {
            "target_ref": self.target_ref,
            "kind": "claude",
            "host_ref": self.host_ref,
            "generation": self.generation,
            "addressable": True,
        }


class ClaudeNativeTargetProjector:
    """Project exact targets from the existing management owner, without a registry."""

    def __init__(self, management_port: ClaudeSessionManagementPort) -> None:
        required = ("list_sessions", "get_session", "send_message", "reconcile_message")
        if any(not callable(getattr(management_port, name, None)) for name in required):
            raise TypeError("complete Claude session-management owner is required")
        self._port = management_port

    @staticmethod
    def _target(value: ClaudeManagedSession) -> ClaudeNativeTarget:
        if type(value) is not ClaudeManagedSession:
            raise BridgeError(
                "native_unavailable", "Claude management projection is invalid"
            )
        identity = {
            "host_ref": value.host_ref,
            "session_id": value.session_id,
            "generation": value.generation,
        }
        digest = hashlib.sha256(_canonical_json(identity)).hexdigest()
        return ClaudeNativeTarget(
            target_ref=f"claude:{digest}",
            session_id=value.session_id,
            generation=value.generation,
            host_ref=value.host_ref,
        )

    def list_targets(self) -> list[ClaudeNativeTarget]:
        try:
            values = self._port.list_sessions()
        except Exception:
            raise BridgeError(
                "native_unavailable", "Claude session-management owner is unavailable"
            ) from None
        if (
            isinstance(values, (str, bytes, Mapping))
            or not isinstance(values, Sequence)
            or len(values) > _MAX_TARGETS
        ):
            raise BridgeError(
                "native_unavailable", "Claude management projection is invalid"
            )

        targets: list[ClaudeNativeTarget] = []
        session_ids: set[str] = set()
        refs: set[str] = set()
        for value in values:
            if type(value) is not ClaudeManagedSession:
                raise BridgeError(
                    "native_unavailable", "Claude management projection is invalid"
                )
            if value.session_id in session_ids:
                raise BridgeError(
                    "native_unavailable", "Claude management projection is ambiguous"
                )
            session_ids.add(value.session_id)
            if not value.addressable:
                continue
            target = self._target(value)
            if target.target_ref in refs:
                raise BridgeError(
                    "native_unavailable", "Claude management projection is ambiguous"
                )
            refs.add(target.target_ref)
            targets.append(target)
        return targets

    def resolve(self, target_ref: str) -> ClaudeNativeTarget:
        if not isinstance(target_ref, str) or not target_ref.startswith("claude:"):
            raise BridgeError(
                "native_target_stale", "Claude target is no longer current"
            )
        matches = [
            item for item in self.list_targets() if item.target_ref == target_ref
        ]
        if len(matches) != 1:
            raise BridgeError(
                "native_target_stale", "Claude target is no longer current"
            )
        selected = matches[0]
        try:
            current = self._port.get_session(selected.session_id)
        except Exception:
            raise BridgeError(
                "native_target_stale", "Claude target is no longer current"
            ) from None
        if (
            type(current) is not ClaudeManagedSession
            or not current.addressable
            or self._target(current) != selected
        ):
            raise BridgeError(
                "native_target_stale", "Claude target is no longer current"
            )
        return selected


class ClaudeSessionManagementAttentionAdapter:
    """Callable bridge seam over the incumbent Claude session-management owner."""

    def __init__(self, projector: ClaudeNativeTargetProjector) -> None:
        if type(projector) is not ClaudeNativeTargetProjector:
            raise TypeError("Claude native projector is required")
        self._projector = projector

    async def __call__(
        self, target_ref: str, reference: AttentionReference
    ) -> dict[str, Any]:
        target = self._projector.resolve(target_ref)
        return await ClaudeNativeAttentionClient(
            self._projector, target=target
        ).deliver(reference)


class ClaudeNativeAttentionClient:
    """One exact management-owner send with same-owner uncertainty reconciliation."""

    def __init__(
        self,
        projector: ClaudeNativeTargetProjector,
        *,
        target: ClaudeNativeTarget,
    ) -> None:
        if type(projector) is not ClaudeNativeTargetProjector:
            raise TypeError("Claude native projector is required")
        if type(target) is not ClaudeNativeTarget:
            raise TypeError("exact Claude native target is required")
        self._projector = projector
        self._target = target
        self._port = projector._port

    def _current_target(self) -> ClaudeNativeTarget:
        current = self._projector.resolve(self._target.target_ref)
        if current != self._target:
            raise BridgeError(
                "native_target_stale", "Claude target is no longer current"
            )
        return current

    @staticmethod
    def _accepted(
        target: ClaudeNativeTarget, *, reconciled: bool
    ) -> dict[str, Any]:
        return {
            "state": "ATTENTION_ACCEPTED",
            "target_ref": target.target_ref,
            "target_consumed": False,
            "parent_consumed": False,
            "reconciled": reconciled,
        }

    async def _reconcile_uncertain(
        self,
        target: ClaudeNativeTarget,
        reference: AttentionReference,
    ) -> dict[str, Any]:
        try:
            receipt = await _maybe_await(
                self._port.reconcile_message(
                    target.session_id, reference.operation_key
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            receipt = None
        if (
            type(receipt) is ClaudeManagementSendReceipt
            and receipt.state == "accepted"
        ):
            return self._accepted(target, reconciled=True)
        raise BridgeError(
            "native_effect_unknown",
            "Claude management attention outcome is unknown; reconcile the original operation",
        )

    async def deliver(self, reference: AttentionReference) -> dict[str, Any]:
        if type(reference) is not AttentionReference:
            raise BridgeError(
                "invalid_input", "Claude attention reference is invalid"
            )
        target = self._current_target()
        notice = _notice(reference)
        try:
            receipt = await _maybe_await(
                self._port.send_message(target.session_id, notice)
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return await self._reconcile_uncertain(target, reference)

        if type(receipt) is not ClaudeManagementSendReceipt:
            return await self._reconcile_uncertain(target, reference)
        if receipt.state == "accepted":
            return self._accepted(target, reconciled=False)
        if receipt.state == "refused":
            raise BridgeError(
                "native_refused", "Claude management owner refused attention"
            )
        return await self._reconcile_uncertain(target, reference)


__all__ = [
    "ClaudeManagedSession",
    "ClaudeManagementSendReceipt",
    "ClaudeNativeAttentionClient",
    "ClaudeNativeTarget",
    "ClaudeNativeTargetProjector",
    "ClaudeSessionManagementAttentionAdapter",
    "ClaudeSessionManagementPort",
]
