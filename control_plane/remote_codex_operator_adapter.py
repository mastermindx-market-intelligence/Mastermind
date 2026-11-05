"""Control-side Operator Harness adapter over the existing worker broker.

The concrete Codex App Server process stays inside the dedicated worker UID.
This object is a synchronous typed proxy used by
``OperatorHarnessOrchestrator``; it owns no Job, Attempt, lease, epoch, or
session state.  Those identities are supplied by Executive Runtime and are
rechecked on both sides of the Unix socket.
"""
from __future__ import annotations

from typing import Callable

from control_plane.executive_worker_broker import WorkerBrokerClient
from control_plane.operator_harness_contract import (
    HarnessAdapterCapabilities,
    TurnRef,
)
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter


TurnInputLoader = Callable[[TurnRef], str]


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
    "codex_remote_capabilities",
]
