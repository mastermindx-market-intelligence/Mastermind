"""Web-Sol bridge for the existing ChatGPT GUI Wake dispatcher."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
import secrets
from typing import Any

from control_plane.wake_dispatcher import WakeEffectUnknownError, WakePreSubmitError
from integrations.executive_wake.chatgpt_gui import ChatGPTGuiWakeDeliveryObservation

from . import web_sol_client as web_client
from . import web_sol_runtime_binding as wrb


class WebSolWakeClient:
    """Map one exact Wake nudge onto the fixed Web-Sol continuation effect."""

    def __init__(
        self,
        navigation_binding: dict[str, Any],
        runtime_binding_lease: wrb.WebSolRuntimeBindingLease,
        *,
        submitter: Callable[..., dict[str, Any]] = web_client.submit_continuation_via_extension,
        now: Callable[[], datetime] | None = None,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(navigation_binding, dict):
            raise ValueError("Web-Sol Wake client requires a navigation binding")
        if not isinstance(runtime_binding_lease, wrb.WebSolRuntimeBindingLease):
            raise ValueError("Web-Sol Wake client requires a RuntimeBinding lease")
        if not callable(submitter):
            raise ValueError("Web-Sol Wake client submitter must be callable")
        self._navigation_binding = dict(navigation_binding)
        self._lease = runtime_binding_lease
        self._submitter = submitter
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
        opaque_ids: Sequence[str],
    ) -> None:
        current = self._lease.runtime_binding
        if (
            native_handle != current.native_handle
            or binding_id != current.binding_id
            or binding_generation != current.binding_generation
            or session_alias != current.session_alias
        ):
            raise WakePreSubmitError("Web-Sol RuntimeBinding no longer matches the Wake")
        if not nudge_id.startswith("NUDGE-") or not opaque_ids:
            raise WakePreSubmitError("Web-Sol Wake correlation identity is invalid")

    async def deliver_wake(
        self,
        *,
        native_handle: str,
        binding_id: str,
        binding_generation: int,
        session_alias: str,
        nudge_id: str,
        opaque_ids: Sequence[str],
    ) -> ChatGPTGuiWakeDeliveryObservation:
        self._require_exact_wake(
            native_handle=native_handle,
            binding_id=binding_id,
            binding_generation=binding_generation,
            session_alias=session_alias,
            nudge_id=nudge_id,
            opaque_ids=opaque_ids,
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

    async def reconcile_wake(self, **_kwargs) -> ChatGPTGuiWakeDeliveryObservation:
        raise WakeEffectUnknownError(
            "Web-Sol cannot infer an earlier continuation effect from a later browser state"
        )


__all__ = ["WebSolWakeClient"]
