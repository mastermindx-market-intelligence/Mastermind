"""Web-Sol bridge for the existing ChatGPT GUI Wake dispatcher."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
import secrets
from typing import Any

from control_plane.wake_ack_ingress import TrustedWebSolWakeAckProjection
from control_plane.wake_dispatcher import WakeEffectUnknownError, WakePreSubmitError
from control_plane.wake_ledger import NUDGE_ID_RE
from integrations.executive_wake.chatgpt_gui import (
    ChatGPTGuiWakeAckObservation,
    ChatGPTGuiWakeDeliveryObservation,
)

from . import web_sol_client as web_client
from . import web_sol_protocol as wsp
from . import web_sol_runtime_binding as wrb


class WebSolWakeClient:
    """Map one exact Wake nudge onto the fixed Web-Sol continuation effect."""

    def __init__(
        self,
        navigation_binding: dict[str, Any],
        runtime_binding_lease: wrb.WebSolRuntimeBindingLease,
        *,
        submitter: Callable[..., dict[str, Any]] = web_client.submit_continuation_via_extension,
        observer: Callable[..., dict[str, Any]] = web_client.observe_continuation_ack_via_extension,
        now: Callable[[], datetime] | None = None,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(navigation_binding, dict):
            raise ValueError("Web-Sol Wake client requires a navigation binding")
        if not isinstance(runtime_binding_lease, wrb.WebSolRuntimeBindingLease):
            raise ValueError("Web-Sol Wake client requires a RuntimeBinding lease")
        if not callable(submitter):
            raise ValueError("Web-Sol Wake client submitter must be callable")
        if not callable(observer):
            raise ValueError("Web-Sol Wake client observer must be callable")
        self._navigation_binding = dict(navigation_binding)
        self._lease = runtime_binding_lease
        self._submitter = submitter
        self._observer = observer
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._nonce_factory = nonce_factory or (lambda: secrets.token_urlsafe(24))

    def _require_exact_wake(
        self,
        *,
        native_handle: str,
        binding_id: str,
        binding_generation: int,
        session_alias: str,
        nudge_id: str,
        obligation_ids: Sequence[str],
    ) -> None:
        current = self._lease.runtime_binding
        if (
            native_handle != current.native_handle
            or binding_id != current.binding_id
            or binding_generation != current.binding_generation
            or session_alias != current.session_alias
        ):
            raise WakePreSubmitError("Web-Sol RuntimeBinding no longer matches the Wake")
        if NUDGE_ID_RE.fullmatch(str(nudge_id or "")) is None:
            raise WakePreSubmitError("Web-Sol Wake nudge identity is invalid")
        try:
            wsp.wake_obligation_digest(tuple(obligation_ids))
        except Exception as exc:
            raise WakePreSubmitError(
                "Web-Sol Wake obligation identities are invalid"
            ) from exc

    async def deliver_wake(
        self,
        *,
        native_handle: str,
        binding_id: str,
        binding_generation: int,
        session_alias: str,
        nudge_id: str,
        obligation_ids: Sequence[str],
    ) -> ChatGPTGuiWakeDeliveryObservation:
        self._require_exact_wake(
            native_handle=native_handle,
            binding_id=binding_id,
            binding_generation=binding_generation,
            session_alias=session_alias,
            nudge_id=nudge_id,
            obligation_ids=obligation_ids,
        )
        issued = self._now().astimezone(timezone.utc).replace(microsecond=0)
        expires = issued + timedelta(seconds=30)
        nonce = self._nonce_factory()
        try:
            receipt = await asyncio.to_thread(
                self._submitter,
                self._navigation_binding,
                self._lease,
                operation_key=f"web-sol-wake:{nudge_id}",
                turn_id=nudge_id,
                wake_obligation_ids=tuple(obligation_ids),
                issued_at=issued.isoformat().replace("+00:00", "Z"),
                expires_at=expires.isoformat().replace("+00:00", "Z"),
                nonce=nonce,
            )
        except web_client.WebSolExtensionError as exc:
            if exc.code == "continuation_submit_effect_unknown":
                raise WakeEffectUnknownError(
                    "Web-Sol continuation effect remains unknown"
                ) from exc
            raise WakePreSubmitError(
                f"Web-Sol refused before a proven continuation start: {exc.code}"
            ) from exc
        except Exception as exc:
            raise WakeEffectUnknownError(
                "Web-Sol continuation effect is unknown after provider call began"
            ) from exc
        status = receipt.get("status") if isinstance(receipt, dict) else None
        if status == "CONTINUATION_STARTED":
            return ChatGPTGuiWakeDeliveryObservation(
                native_handle=native_handle,
                binding_id=binding_id,
                binding_generation=binding_generation,
                session_alias=session_alias,
                nudge_id=nudge_id,
                generation_started=True,
            )
        if status == "CONTINUATION_NOT_SUBMITTED":
            raise WakePreSubmitError("Web-Sol continuation was not submitted")
        if status == "CONTINUATION_SUBMIT_EFFECT_UNKNOWN":
            raise WakeEffectUnknownError("Web-Sol continuation submission may have taken effect")
        raise WakeEffectUnknownError("Web-Sol returned an unrecognized continuation state")

    async def observe_wake_ack(
        self,
        *,
        native_handle: str,
        binding_id: str,
        binding_generation: int,
        session_alias: str,
        nudge_id: str,
        obligation_ids: Sequence[str],
    ) -> ChatGPTGuiWakeAckObservation:
        """Read one exact completed-turn ACK; never submit or retry provider work."""

        self._require_exact_wake(
            native_handle=native_handle,
            binding_id=binding_id,
            binding_generation=binding_generation,
            session_alias=session_alias,
            nudge_id=nudge_id,
            obligation_ids=obligation_ids,
        )
        issued = self._now().astimezone(timezone.utc).replace(microsecond=0)
        expires = issued + timedelta(seconds=30)
        try:
            receipt = await asyncio.to_thread(
                self._observer,
                self._navigation_binding,
                self._lease,
                operation_key=f"web-sol-wake-ack:{nudge_id}",
                nudge_id=nudge_id,
                wake_obligation_ids=tuple(obligation_ids),
                issued_at=issued.isoformat().replace("+00:00", "Z"),
                expires_at=expires.isoformat().replace("+00:00", "Z"),
                nonce=self._nonce_factory(),
            )
        except web_client.WebSolExtensionError as exc:
            raise WakePreSubmitError(
                f"Web-Sol semantic ACK observation refused: {exc.code}"
            ) from exc
        except Exception as exc:
            raise WakePreSubmitError(
                "Web-Sol semantic ACK observation is unavailable"
            ) from exc
        status = receipt.get("status") if isinstance(receipt, dict) else None
        if status != "CONTINUATION_ACKNOWLEDGED":
            if status in {
                "CONTINUATION_ACK_PENDING",
                "CONTINUATION_ACK_REFUSED",
            }:
                raise WakePreSubmitError(
                    f"Web-Sol semantic ACK is not ready: {status}"
                )
            raise WakePreSubmitError(
                "Web-Sol semantic ACK returned an unrecognized state"
            )
        current = self._lease.runtime_binding
        projection = TrustedWebSolWakeAckProjection(
            session_alias=current.session_alias,
            reasoning_surface=current.reasoning_surface,
            binding_id=current.binding_id,
            binding_generation=current.binding_generation,
            native_handle=current.native_handle,
            runtime_binding_fingerprint=self._lease.runtime_binding_fingerprint,
            conversation_fingerprint=self._lease.target.conversation_fingerprint,
            provider_native_turn_id=str(receipt.get("provider_native_turn_id") or ""),
            nudge_id=nudge_id,
            obligation_ids=tuple(receipt.get("acknowledged_obligation_ids") or ()),
            terminal_ack_trailer=receipt.get("terminal_ack_trailer") is True,
        )
        if projection.obligation_ids != tuple(obligation_ids):
            raise WakePreSubmitError(
                "Web-Sol semantic ACK obligation set does not match the delivered Wake"
            )
        return ChatGPTGuiWakeAckObservation(
            projection=projection,
            runtime_binding_lease=self._lease,
        )

    async def reconcile_wake(self, **_kwargs) -> ChatGPTGuiWakeDeliveryObservation:
        raise WakeEffectUnknownError(
            "Web-Sol cannot infer an earlier continuation effect from a later browser state"
        )


__all__ = ["WebSolWakeClient"]
