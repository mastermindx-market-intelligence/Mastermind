"""Control-side Operator Harness adapter over the existing worker broker.

The concrete Codex App Server process stays inside the dedicated worker UID.
This object is a synchronous typed proxy used by
``OperatorHarnessOrchestrator``; it owns no Job, Attempt, lease, epoch, or
session state.  Those identities are supplied by Executive Runtime and are
rechecked on both sides of the Unix socket.
"""
from __future__ import annotations

import dataclasses
from typing import Callable
from uuid import uuid4

from control_plane.executive_worker_broker import WorkerBrokerClient
from control_plane.operator_harness_contract import (
    AttentionTurnObservation,
    HarnessAdapterCapabilities,
    ProcessGenerationRef,
    TurnRef,
)
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter


TurnInputLoader = Callable[[TurnRef], str]


class ConsultationIngressUnavailable(RuntimeError):
    """The requested native consultation surface is not qualified."""


class ConsultationIngressRefused(RuntimeError):
    """The managed Codex writer refused before provider I/O."""


@dataclasses.dataclass(frozen=True)
class CodexConsultationIngress:
    """Start one reference-only consultation turn on an idle managed thread."""

    adapter: object
    generation: ProcessGenerationRef
    attempt_id: str
    binding_id: str
    binding_generation: int
    provider_session_id: str
    surface: str
    active_turn: bool = False

    def __post_init__(self) -> None:
        if self.surface != "codex":
            raise ConsultationIngressUnavailable(
                "consultation recipient is UNQUALIFIED for claude"
            )
        if not callable(getattr(self.adapter, "deliver_attention", None)):
            raise TypeError("adapter must support managed Codex attention")

    def with_active_turn(self, active: bool) -> "CodexConsultationIngress":
        return dataclasses.replace(self, active_turn=active)

    def deliver(
        self,
        *,
        consultation_ref: str,
        message_key: str,
        semantic_fingerprint: str,
        wake_obligation_id: str,
    ) -> dict[str, object]:
        if self.active_turn:
            raise ConsultationIngressRefused(
                "active consultation recipient turn refused before provider I/O"
            )
        instruction = (
            "Company consultation reference only; no authority is granted:\n"
            f"consultation_id={consultation_ref}\n"
            f"message_key={message_key}\n"
            f"semantic_fingerprint={semantic_fingerprint}\n"
            f"opaque_wake_id={wake_obligation_id}"
        )
        observation = self.adapter.deliver_attention(
            generation=self.generation,
            attempt_id=self.attempt_id,
            binding_id=self.binding_id,
            binding_generation=self.binding_generation,
            provider_session_id=self.provider_session_id,
            nudge_id="consult-" + uuid4().hex,
            opaque_ids=(wake_obligation_id,),
            instruction=instruction,
            completion_timeout_seconds=15.0,
        )
        if not isinstance(observation, AttentionTurnObservation):
            raise ConsultationIngressUnavailable("adapter returned untyped evidence")
        return {
            "native_thread_id": observation.provider_session_id,
            "native_turn_id": observation.provider_native_turn_id,
            "accepted": observation.accepted,
        }


def codex_remote_capabilities() -> HarnessAdapterCapabilities:
    """Return the exact reviewed control-side capability profile for Codex."""

    return HarnessAdapterCapabilities(
        interface_version=RemoteOperatorHarnessAdapter.interface_version,
        supported_required_operations=(
            "start_session",
            "begin_turn",
            "read_events",
            "interrupt_turn",
            "collect_candidate_result",
            "graceful_stop",
            "cancel",
            "reconcile",
        ),
        supported_optional_operations=("resume_session",),
        supports_native_resume=True,
        supports_native_fork=False,
        supports_steering=False,
        supports_approval_response=False,
        supports_checkpoint=False,
        supports_config_staging=False,
        supports_subagent_capability_ceiling=True,
        supports_structured_events=True,
        supports_provider_native_idempotency=False,
        provider_capability_ids=("codex-app-server-stdio",),
    )


class RemoteCodexOperatorAdapter(RemoteOperatorHarnessAdapter):
    """Compatibility wrapper for the reviewed Codex App Server realm."""

    def __init__(
        self,
        client: WorkerBrokerClient,
        *,
        turn_input_loader: TurnInputLoader,
    ) -> None:
        super().__init__(
            client,
            turn_input_loader=turn_input_loader,
            capabilities=codex_remote_capabilities(),
        )


__all__ = [
    "RemoteCodexOperatorAdapter",
    "CodexConsultationIngress",
    "codex_remote_capabilities",
]
