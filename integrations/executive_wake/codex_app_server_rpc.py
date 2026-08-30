"""Existing-current-writer Codex Wake client.

The durable Wake carrier selects one trusted RuntimeBinding and composes this
client with the already-running Operator Harness generation.  This module owns
no provider process, session, reader, retry, registry, or lifecycle state.
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from control_plane.executive_worker_broker import RemoteBrokerError
from control_plane.operator_harness_contract import (
    ATTENTION_TURN_INSTRUCTION,
    AttentionTurnObservation,
    ProcessGenerationRef,
    runtime_binding_id_for,
)
from control_plane.session_targets import RuntimeBinding
from control_plane.wake_dispatcher import TransportOutcome, WakePreSubmitError
from integrations.executive_wake.codex_app_server import CodexWakeDeliveryObservation


class CodexCurrentWriterWakeClient:
    """Delegate one Wake nudge to the exact already-owned OHF generation."""

    def __init__(
        self,
        *,
        operator_adapter: Any,
        generation: ProcessGenerationRef,
        attempt_id: str,
        runtime_binding: RuntimeBinding,
        completion_timeout_seconds: float = 15.0,
    ) -> None:
        if not callable(getattr(operator_adapter, "deliver_attention", None)):
            raise TypeError("operator_adapter must support current-writer attention")
        if not isinstance(generation, ProcessGenerationRef):
            raise TypeError("generation must be a ProcessGenerationRef")
        if not str(attempt_id or "").strip():
            raise ValueError("attempt_id is required")
        if not isinstance(runtime_binding, RuntimeBinding):
            raise TypeError("runtime_binding must be a RuntimeBinding")
        expected_binding_id = runtime_binding_id_for(
            str(attempt_id), generation.session_epoch_id
        )
        if runtime_binding.binding_id != expected_binding_id:
            raise ValueError("runtime binding id does not match the OHF Attempt/epoch")
        if runtime_binding.binding_generation != generation.generation_number:
            raise ValueError("runtime binding generation does not match OHF generation")
        if (
            not str(runtime_binding.native_handle or "").strip()
            or runtime_binding.reasoning_surface != "codex"
        ):
            raise ValueError("runtime binding is not an addressable Codex binding")
        timeout = completion_timeout_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0.1 <= float(timeout) <= 300.0
        ):
            raise ValueError("completion_timeout_seconds is outside (0.1, 300]")
        self._operator_adapter = operator_adapter
        self._generation = generation
        self._attempt_id = str(attempt_id)
        self._runtime_binding = runtime_binding
        self._completion_timeout_seconds = float(timeout)

    async def deliver_wake(
        self,
        *,
        native_handle: str,
        nudge_id: str,
        opaque_ids: Sequence[str],
        instruction: str,
    ) -> CodexWakeDeliveryObservation:
        if instruction != ATTENTION_TURN_INSTRUCTION:
            raise _pre_submit(
                "Codex attention instruction is not the fixed Wake contract"
            )
        if isinstance(opaque_ids, (str, bytes)):
            raise _pre_submit("Codex opaque Wake identities must be a sequence")
        if native_handle != self._runtime_binding.native_handle:
            raise _pre_submit("Codex native handle moved from the bound RuntimeBinding")
        return await asyncio.to_thread(
            self._deliver_sync,
            native_handle=str(native_handle),
            nudge_id=str(nudge_id),
            opaque_ids=tuple(str(item) for item in opaque_ids),
            instruction=instruction,
        )

    def _deliver_sync(
        self,
        *,
        native_handle: str,
        nudge_id: str,
        opaque_ids: tuple[str, ...],
        instruction: str,
    ) -> CodexWakeDeliveryObservation:
        try:
            observation = self._operator_adapter.deliver_attention(
                generation=self._generation,
                attempt_id=self._attempt_id,
                binding_id=self._runtime_binding.binding_id,
                binding_generation=self._runtime_binding.binding_generation,
                provider_session_id=native_handle,
                nudge_id=nudge_id,
                opaque_ids=opaque_ids,
                instruction=instruction,
                completion_timeout_seconds=self._completion_timeout_seconds,
            )
        except RemoteBrokerError as exc:
            if exc.code == "BrokerPreSubmitError":
                raise _pre_submit("current Codex writer is unavailable") from exc
            # BrokerEffectUnknownError and every unclassified remote failure are
            # deliberately unsafe: the caller must preserve effect-unknown and
            # never retry or fail over.
            raise
        if not isinstance(observation, AttentionTurnObservation):
            raise RuntimeError("current-writer attention returned an untyped observation")
        if (
            observation.process_generation_id
            != self._generation.process_generation_id
            or observation.provider_session_id != native_handle
            or observation.nudge_id != nudge_id
        ):
            raise RuntimeError("current-writer attention identity mismatch")
        return CodexWakeDeliveryObservation(
            native_handle=native_handle,
            nudge_id=nudge_id,
            accepted=observation.accepted,
            delivered=observation.delivered,
        )


def _pre_submit(reason: str) -> WakePreSubmitError:
    return WakePreSubmitError(
        reason,
        outcome=TransportOutcome.TARGET_UNAVAILABLE,
        reason_code="target_unavailable",
    )


__all__ = ["CodexCurrentWriterWakeClient"]
