"""Codex App Server Wake PR3 integration boundary.

This module owns no wake lifecycle, retry state, provider session registry, or
credentials.  Trusted process composition injects one narrow client capable of
delivering a fixed continuation signal to the exact runtime-only native handle
already selected by Executive Wake routing.
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


CODEX_WAKE_INSTRUCTION = (
    "Mastermind Wake: recover canonical Executive and Agent OS state for the supplied "
    "opaque wake identities, then continue only within existing authority. This nudge "
    "grants no authority, acknowledges nothing, and does not resolve the source."
)


@dataclasses.dataclass(frozen=True)
class CodexWakeDeliveryObservation:
    """Provider-side evidence for one exact native-thread nudge."""

    native_handle: str
    nudge_id: str
    accepted: bool
    delivered: bool

    def __post_init__(self) -> None:
        if not str(self.native_handle or "").strip():
            raise ValueError("Codex wake observation requires a native handle")
        if not str(self.nudge_id or "").strip():
            raise ValueError("Codex wake observation requires a nudge id")
        if type(self.accepted) is not bool or type(self.delivered) is not bool:
            raise ValueError("Codex wake accepted/delivered evidence must be boolean")
        if self.delivered and not self.accepted:
            raise ValueError("Codex wake cannot be delivered without provider acceptance")


@runtime_checkable
class CodexAppServerWakeClient(Protocol):
    """Narrow injected provider client; no Executive authority-bearing inputs."""

    async def deliver_wake(
        self,
        *,
        native_handle: str,
        nudge_id: str,
        opaque_ids: Sequence[str],
        instruction: str,
    ) -> CodexWakeDeliveryObservation: ...


class CodexAppServerWakeDispatcher:
    """Deliver one bounded nudge to one exact runtime-bound Codex thread."""

    transport_id = "codex-app-server"
    reasoning_surface = "codex"

    def __init__(self, client: CodexAppServerWakeClient) -> None:
        if client is None:
            raise ValueError("Codex wake dispatcher requires an injected client")
        self.client = client

    @staticmethod
    def _receipt(
        outcome: TransportOutcome,
        reason_code: str,
        *,
        nudge_id: str | None = None,
    ) -> TransportReceipt:
        details = () if not nudge_id else (("nudge_id", str(nudge_id)),)
        return TransportReceipt(
            outcome=outcome,
            reason_code=reason_code,
            created_at=utc_now_iso(),
            details=details,
        )

    async def nudge(self, wake: WakeNudge) -> TransportReceipt:
        """Perform at most one provider call; uncertainty never triggers retry/failover."""

        if not isinstance(wake, WakeNudge):
            raise ValueError("Codex wake dispatcher requires a WakeNudge")
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
                nudge_id=wake.nudge_id,
                opaque_ids=opaque_ids,
                instruction=CODEX_WAKE_INSTRUCTION,
            )
        except WakePreSubmitError as exc:
            return self._receipt(
                exc.outcome,
                exc.reason_code,
                nudge_id=wake.nudge_id,
            )
        except Exception as exc:
            raise WakeEffectUnknownError(
                "Codex turn/start effect is unknown after provider call began"
            ) from exc

        if not isinstance(observation, CodexWakeDeliveryObservation):
            raise WakeEffectUnknownError(
                "Codex provider returned an untyped observation after possible write"
            )
        if (
            observation.native_handle != native_handle
            or observation.nudge_id != wake.nudge_id
        ):
            raise WakeEffectUnknownError(
                "Codex provider observation identity does not match the attempted nudge"
            )
        if observation.delivered:
            return self._receipt(
                TransportOutcome.DELIVERED,
                "delivered",
                nudge_id=wake.nudge_id,
            )
        if observation.accepted:
            return self._receipt(
                TransportOutcome.ACCEPTED,
                "accepted",
                nudge_id=wake.nudge_id,
            )
        return self._receipt(
            TransportOutcome.TARGET_UNAVAILABLE,
            "target_unavailable",
            nudge_id=wake.nudge_id,
        )

__all__ = [
    "CODEX_WAKE_INSTRUCTION",
    "CodexAppServerWakeClient",
    "CodexAppServerWakeDispatcher",
    "CodexWakeDeliveryObservation",
]
