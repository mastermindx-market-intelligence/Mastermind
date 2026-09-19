"""ChatGPT GUI Wake adapter over the existing Executive Wake lifecycle.

This module owns no Wake state, retry policy, browser discovery, RuntimeBinding
persistence, result store, or semantic acknowledgement. Trusted composition
injects one narrow client for the already-bound Web-Sol exact conversation.
"""
from __future__ import annotations

import dataclasses
from typing import Protocol, Sequence, runtime_checkable

from control_plane.wake_dispatcher import (
    TransportOutcome,
    TransportReceipt,
    WakeEffectUnknownError,
    WakeNudge,
    WakePreSubmitError,
)
from control_plane.wake_events import utc_now_iso


@dataclasses.dataclass(frozen=True)
class ChatGPTGuiWakeDeliveryObservation:
    """Exact Web-Sol evidence after one possible fixed continuation submit."""

    native_handle: str
    binding_id: str
    binding_generation: int
    session_alias: str
    nudge_id: str
    generation_started: bool

    def __post_init__(self) -> None:
        for name in ("native_handle", "binding_id", "session_alias", "nudge_id"):
            value = str(getattr(self, name) or "").strip()
            if not value or value != getattr(self, name):
                raise ValueError(f"{name} is required and must be trimmed")
        if type(self.binding_generation) is not int or self.binding_generation < 1:
            raise ValueError("binding_generation must be an integer >= 1")
        if type(self.generation_started) is not bool:
            raise ValueError("generation_started must be boolean")


@runtime_checkable
class ChatGPTGuiWakeClient(Protocol):
    """Narrow injected Web-Sol client; no Executive authority-bearing prose."""

    async def deliver_wake(
        self,
        *,
        native_handle: str,
        binding_id: str,
        binding_generation: int,
        session_alias: str,
        nudge_id: str,
        opaque_ids: Sequence[str],
    ) -> ChatGPTGuiWakeDeliveryObservation: ...


class ChatGPTGuiWakeDispatcher:
    """Deliver one fixed continuation to one exact Web-Sol RuntimeBinding."""

    transport_id = "chatgpt-gui"
    reasoning_surface = "chatgpt-sol"

    def __init__(self, client: ChatGPTGuiWakeClient) -> None:
        if client is None:
            raise ValueError("ChatGPT GUI wake dispatcher requires an injected client")
        self.client = client

    @staticmethod
    def _receipt(
        outcome: TransportOutcome,
        reason_code: str,
        *,
        nudge_id: str,
    ) -> TransportReceipt:
        return TransportReceipt(
            outcome=outcome,
            reason_code=reason_code,
            created_at=utc_now_iso(),
            details=(("nudge_id", nudge_id),),
        )

    async def nudge(self, wake: WakeNudge) -> TransportReceipt:
        """Attempt one exact generation start; never retry or fail over."""

        if not isinstance(wake, WakeNudge):
            raise ValueError("ChatGPT GUI wake dispatcher requires a WakeNudge")
        native_handle = str(wake.native_handle or "").strip()
        if (
            not native_handle
            or wake.wake_transport != self.transport_id
            or wake.reasoning_surface != self.reasoning_surface
        ):
            return self._receipt(
                TransportOutcome.TARGET_UNAVAILABLE,
                "target_unavailable",
                nudge_id=wake.nudge_id,
            )

        opaque_ids = tuple(wake.obligation_ids) + tuple(wake.attempt_command_ids)
        try:
            observation = await self.client.deliver_wake(
                native_handle=native_handle,
                binding_id=wake.binding_id,
                binding_generation=wake.binding_generation,
                session_alias=wake.session_alias,
                nudge_id=wake.nudge_id,
                opaque_ids=opaque_ids,
            )
        except WakePreSubmitError as exc:
            return self._receipt(
                exc.outcome,
                exc.reason_code,
                nudge_id=wake.nudge_id,
            )
        except Exception as exc:
            raise WakeEffectUnknownError(
                "ChatGPT GUI continuation effect is unknown after provider call began"
            ) from exc

        if not isinstance(observation, ChatGPTGuiWakeDeliveryObservation):
            raise WakeEffectUnknownError(
                "ChatGPT GUI returned an untyped observation after possible write"
            )
        if (
            observation.native_handle != native_handle
            or observation.binding_id != wake.binding_id
            or observation.binding_generation != wake.binding_generation
            or observation.session_alias != wake.session_alias
            or observation.nudge_id != wake.nudge_id
        ):
            raise WakeEffectUnknownError(
                "ChatGPT GUI observation identity does not match the attempted nudge"
            )
        if not observation.generation_started:
            raise WakeEffectUnknownError(
                "ChatGPT GUI continuation was submitted but exact generation start is unproven"
            )
        return self._receipt(
            TransportOutcome.DELIVERED,
            "delivered",
            nudge_id=wake.nudge_id,
        )

    async def reconcile(self, wake: WakeNudge) -> TransportReceipt:
        """Never infer a prior browser submit from current DOM state."""

        raise WakeEffectUnknownError(
            "ChatGPT GUI has no safe same-effect reconciliation after uncertain submit"
        )


__all__ = [
    "ChatGPTGuiWakeClient",
    "ChatGPTGuiWakeDeliveryObservation",
    "ChatGPTGuiWakeDispatcher",
]
