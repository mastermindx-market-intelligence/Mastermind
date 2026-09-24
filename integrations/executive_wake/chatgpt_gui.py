"""ChatGPT GUI Wake adapter over the existing Executive Wake lifecycle.

This module owns no Wake state, retry policy, browser discovery, RuntimeBinding
persistence, result store, or ACK ledger. Trusted composition injects one narrow
client for the already-bound Web-Sol exact conversation and provider-local ACK.
"""
from __future__ import annotations

import dataclasses
from typing import Protocol, Sequence, runtime_checkable

from control_plane.wake_ack_ingress import TrustedWebSolWakeAckProjection
from control_plane.wake_dispatcher import (
    TransportOutcome,
    TransportReceipt,
    WakeEffectUnknownError,
    WakeNudge,
    WakePreSubmitError,
    WakeTransportCompletion,
    WebSolWakeAckCompletion,
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


@dataclasses.dataclass(frozen=True)
class ChatGPTGuiWakeAckObservation:
    """Transient exact semantic ACK and its detached current lease."""

    projection: TrustedWebSolWakeAckProjection
    runtime_binding_lease: object = dataclasses.field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.projection, TrustedWebSolWakeAckProjection):
            raise ValueError("semantic ACK observation requires a trusted projection")
        if self.runtime_binding_lease is None:
            raise ValueError("semantic ACK observation requires the current lease")


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
        obligation_ids: Sequence[str],
    ) -> ChatGPTGuiWakeDeliveryObservation: ...

    async def observe_wake_ack(
        self,
        *,
        native_handle: str,
        binding_id: str,
        binding_generation: int,
        session_alias: str,
        nudge_id: str,
        obligation_ids: Sequence[str],
    ) -> ChatGPTGuiWakeAckObservation: ...


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

        obligation_ids = tuple(sorted(wake.obligation_ids))
        try:
            observation = await self.client.deliver_wake(
                native_handle=native_handle,
                binding_id=wake.binding_id,
                binding_generation=wake.binding_generation,
                session_alias=wake.session_alias,
                nudge_id=wake.nudge_id,
                obligation_ids=obligation_ids,
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

    async def reconcile_delivered_ack(
        self,
        wake: WakeNudge,
    ) -> WakeTransportCompletion | TransportReceipt:
        """Read one semantic ACK after canonical DELIVERED; never resubmit."""

        if not isinstance(wake, WakeNudge):
            raise ValueError("ChatGPT GUI ACK reconciliation requires a WakeNudge")
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
        obligation_ids = tuple(sorted(wake.obligation_ids))
        try:
            observation = await self.client.observe_wake_ack(
                native_handle=native_handle,
                binding_id=wake.binding_id,
                binding_generation=wake.binding_generation,
                session_alias=wake.session_alias,
                nudge_id=wake.nudge_id,
                obligation_ids=obligation_ids,
            )
        except WakePreSubmitError:
            raise
        except Exception as exc:
            raise WakePreSubmitError(
                "ChatGPT GUI semantic ACK observation is unavailable"
            ) from exc
        if not isinstance(observation, ChatGPTGuiWakeAckObservation):
            raise WakePreSubmitError(
                "ChatGPT GUI semantic ACK observation is untyped"
            )
        projection = observation.projection
        if (
            projection.native_handle != native_handle
            or projection.binding_id != wake.binding_id
            or projection.binding_generation != wake.binding_generation
            or projection.session_alias != wake.session_alias
            or projection.nudge_id != wake.nudge_id
            or projection.obligation_ids != obligation_ids
        ):
            raise WakePreSubmitError(
                "ChatGPT GUI semantic ACK identity does not match the delivered nudge"
            )
        return WakeTransportCompletion(
            receipt=self._receipt(
                TransportOutcome.DELIVERED,
                "delivered",
                nudge_id=wake.nudge_id,
            ),
            target_ack_projection=WebSolWakeAckCompletion(
                projection=projection,
                runtime_binding_lease=observation.runtime_binding_lease,
            ),
        )

    async def reconcile(self, wake: WakeNudge) -> TransportReceipt:
        """Never infer a prior browser submit from current DOM state."""

        raise WakeEffectUnknownError(
            "ChatGPT GUI has no safe same-effect reconciliation after uncertain submit"
        )


__all__ = [
    "ChatGPTGuiWakeAckObservation",
    "ChatGPTGuiWakeClient",
    "ChatGPTGuiWakeDeliveryObservation",
    "ChatGPTGuiWakeDispatcher",
]
