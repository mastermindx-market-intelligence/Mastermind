"""Connect committed session continuations to the existing Executive Wake owner.

This adapter owns no listener, activation grant, target registry, retry loop,
provider process or delivery ledger. It resolves the original committed source,
then asks the already-composed owner once. A Wake receipt is not consumption.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

from control_plane.executive_service import DialogueWakeResult
from .canary_source import resolve_continuation_attention
from .native_wire import AttentionReference


class RuntimeSessionAttention:
    def __init__(
        self, runtime: Any, *, dialogue_socket_path: Path,
        wake_handler_provider: Callable[[], Any], admission_guard: Callable[[], bool],
    ) -> None:
        for callback in (wake_handler_provider, admission_guard):
            if (not callable(callback) or inspect.iscoroutinefunction(callback)
                    or inspect.iscoroutinefunction(getattr(callback, "__call__", None))):
                raise TypeError("synchronous owner and admission callbacks are required")
        self._runtime = runtime
        self._socket_path = dialogue_socket_path
        self._wake_handler_provider = wake_handler_provider
        self._admission_guard = admission_guard

    async def __call__(
        self, target_ref: str, reference: AttentionReference, read_ref: str,
    ) -> dict[str, str]:
        # Nothing before the owner call below can request native attention.
        # Cancellation is never converted into a retryable no-effect result.
        try:
            if type(reference) is not AttentionReference:
                return {"state": "UNAVAILABLE", "reason": "ATTENTION_REFERENCE_REFUSED"}
            if self._admission_guard() is not True:
                return {"state": "UNAVAILABLE", "reason": "ATTENTION_ADMISSION_UNAVAILABLE"}
            handler = self._wake_handler_provider()
            if not callable(handler):
                return {"state": "UNAVAILABLE", "reason": "WAKE_OWNER_UNAVAILABLE"}
            source = await resolve_continuation_attention(
                self._runtime, read_ref=read_ref, socket_path=self._socket_path)
            if (source.target_ref != target_ref or source.read_ref != read_ref
                    or source.operation_key != reference.operation_key
                    or source.message_key != reference.message_key):
                return {"state": "UNAVAILABLE", "reason": "ATTENTION_SOURCE_REFUSED"}
            if (self._admission_guard() is not True
                    or self._wake_handler_provider() is not handler):
                return {"state": "UNAVAILABLE", "reason": "ATTENTION_ADMISSION_CHANGED"}
        except Exception:
            return {"state": "UNAVAILABLE", "reason": "ATTENTION_SOURCE_UNAVAILABLE"}

        try:
            result = handler(self._runtime, source.request)
            if inspect.isawaitable(result):
                result = await result
            if (type(result) is not DialogueWakeResult
                    or self._admission_guard() is not True
                    or self._wake_handler_provider() is not handler):
                return {"state": "EFFECT_UNKNOWN", "reason": "WAKE_OUTCOME_UNCONFIRMED"}
        except Exception:
            return {"state": "EFFECT_UNKNOWN", "reason": "WAKE_OUTCOME_UNCONFIRMED"}
        return {
            "state": "UNAVAILABLE" if result.state == "MISSING" else result.state,
            "reason": result.reason,
            "obligation_id": source.request.obligation.obligation_id,
        }
