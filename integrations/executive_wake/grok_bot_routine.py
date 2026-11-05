"""Production-inert Wake adapter for one exact Grok routine target.

This module owns no transport implementation bit, target registration, credentials,
provider I/O, retry policy, session registry, lifecycle state, or completion truth.
Trusted composition injects one narrow client for the exact RuntimeBinding already
selected by the canonical Wake fabric.
"""
from __future__ import annotations

import asyncio
import dataclasses
import re
from typing import Protocol, Sequence, runtime_checkable

from control_plane.wake_dispatcher import (
    TransportOutcome,
    TransportReceipt,
    WakeEffectUnknownError,
    WakeNudge,
    WakePreSubmitError,
)
from control_plane.wake_events import utc_now_iso


_NUDGE_ID_RE = re.compile(r"^NUDGE-[0-9a-f]{32}$")
_MAX_OPAQUE_REF_CHARS = 256


def _bounded_opaque(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Grok routine observation requires a bounded {field}")
    token = value
    if (
        token.strip() != token
        or not token
        or len(token) > _MAX_OPAQUE_REF_CHARS
        or any(ord(character) < 32 or ord(character) == 127 for character in token)
    ):
        raise ValueError(f"Grok routine observation requires a bounded {field}")
    return token


@dataclasses.dataclass(frozen=True)
class GrokRoutineWakeObservation:
    """Provider-side evidence for one exact routine submission or observation."""

    native_handle: str
    nudge_id: str
    accepted: bool
    request_id: str | None = None

    def __post_init__(self) -> None:
        native_handle = _bounded_opaque(self.native_handle, field="native handle")
        nudge_id = _bounded_opaque(self.nudge_id, field="nudge id")
        if _NUDGE_ID_RE.fullmatch(nudge_id) is None:
            raise ValueError("Grok routine observation requires a canonical nudge id")
        if type(self.accepted) is not bool:
            raise ValueError("Grok routine accepted evidence must be boolean")
        request_id = self.request_id
        if request_id is not None:
            request_id = _bounded_opaque(request_id, field="request id")
        object.__setattr__(self, "native_handle", native_handle)
        object.__setattr__(self, "nudge_id", nudge_id)
        object.__setattr__(self, "request_id", request_id)


@runtime_checkable
class GrokRoutineWakeClient(Protocol):
    """Injected one-call client; carries no Executive authority-bearing prose."""

    async def deliver_wake(
        self,
        *,
        native_handle: str,
        nudge_id: str,
        binding_id: str,
        binding_generation: int,
        opaque_ids: Sequence[str],
    ) -> GrokRoutineWakeObservation: ...


@runtime_checkable
class GrokRoutineObservationSource(Protocol):
    """Read-only late-result source for the exact attempted nudge."""

    async def observe_wake(
        self,
        *,
        native_handle: str,
        nudge_id: str,
    ) -> GrokRoutineWakeObservation | None: ...


class GrokBotRoutineWakeDispatcher:
    """Submit at most one nudge and never claim target consumption or delivery."""

    transport_id = "grok-computer"
    reasoning_surface = "grok-bot"

    def __init__(
        self,
        client: GrokRoutineWakeClient,
        *,
        observation_source: GrokRoutineObservationSource | None = None,
    ) -> None:
        if client is None:
            raise ValueError("Grok routine dispatcher requires an injected client")
        self.client = client
        self.observation_source = observation_source

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

    @staticmethod
    def _native_handle(wake: WakeNudge) -> str | None:
        native_handle = str(wake.native_handle or "").strip()
        if not native_handle:
            return None
        return native_handle

    def _target_matches(self, wake: WakeNudge) -> bool:
        return (
            wake.wake_transport == self.transport_id
            and wake.reasoning_surface == self.reasoning_surface
        )

    async def nudge(self, wake: WakeNudge) -> TransportReceipt:
        """Perform one injected submission; uncertainty never retries or fails over."""

        if not isinstance(wake, WakeNudge):
            raise ValueError("Grok routine dispatcher requires a WakeNudge")
        native_handle = self._native_handle(wake)
        if native_handle is None or not self._target_matches(wake):
            return self._receipt(
                TransportOutcome.TARGET_UNAVAILABLE,
                "target_unavailable",
                nudge_id=wake.nudge_id,
            )

        opaque_ids = tuple(wake.obligation_ids) + tuple(wake.attempt_command_ids)
        submission_unknown = False
        observation = None
        try:
            observation = await self.client.deliver_wake(
                native_handle=native_handle,
                nudge_id=wake.nudge_id,
                binding_id=wake.binding_id,
                binding_generation=wake.binding_generation,
                opaque_ids=opaque_ids,
            )
        except WakePreSubmitError as exc:
            return self._receipt(
                exc.outcome,
                exc.reason_code,
                nudge_id=wake.nudge_id,
            )
        except asyncio.CancelledError:
            submission_unknown = True
        except Exception:
            submission_unknown = True
        if submission_unknown:
            raise WakeEffectUnknownError(
                "Grok routine submission effect is unknown after the client call began"
            )

        return self._receipt_from_observation(
            wake,
            observation,
            native_handle=native_handle,
        )

    async def reconcile(self, wake: WakeNudge) -> TransportReceipt:
        """Observe the exact attempted nudge without performing another submission."""

        if not isinstance(wake, WakeNudge):
            raise WakeEffectUnknownError(
                "Grok routine reconciliation requires the exact persisted WakeNudge"
            )
        native_handle = self._native_handle(wake)
        if native_handle is None or not self._target_matches(wake):
            raise WakeEffectUnknownError(
                "Grok routine reconciliation identity is not the bound target"
            )
        source = self.observation_source
        if source is None:
            raise WakeEffectUnknownError(
                "Grok routine reconciliation has no observation source"
            )
        observation_unavailable = False
        observation = None
        try:
            observation = await source.observe_wake(
                native_handle=native_handle,
                nudge_id=wake.nudge_id,
            )
        except asyncio.CancelledError:
            observation_unavailable = True
        except Exception:
            observation_unavailable = True
        if observation_unavailable or observation is None:
            raise WakeEffectUnknownError(
                "Grok routine submission effect remains unknown"
            )
        return self._receipt_from_observation(
            wake,
            observation,
            native_handle=native_handle,
        )

    def _receipt_from_observation(
        self,
        wake: WakeNudge,
        observation: object,
        *,
        native_handle: str,
    ) -> TransportReceipt:
        if not isinstance(observation, GrokRoutineWakeObservation):
            raise WakeEffectUnknownError(
                "Grok routine provider returned an untyped observation"
            )
        if (
            observation.native_handle != native_handle
            or observation.nudge_id != wake.nudge_id
        ):
            raise WakeEffectUnknownError(
                "Grok routine provider observation identity does not match the nudge"
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
    "GrokBotRoutineWakeDispatcher",
    "GrokRoutineObservationSource",
    "GrokRoutineWakeClient",
    "GrokRoutineWakeObservation",
]
