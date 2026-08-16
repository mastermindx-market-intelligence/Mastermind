"""Provider-neutral execution-adapter contract for Executive OS workers.

The first implementation is the existing attested Codex CLI adapter.  Future
Qwen, GLM, xAI, ACP, or cloud implementations plug into this interface; they do
not get their own queue, lease model, or lifecycle database.

The protocol deliberately names only the operations the current supervisor
uses.  Optional receipts (launch attestation, UID sweep, cleanup) remain
feature-detected by the supervisor and can become required by a provider's
acceptance policy without weakening this common floor.
"""
from __future__ import annotations

import dataclasses
from typing import Protocol, Sequence, runtime_checkable

from control_plane.codex_worker import (
    CancelReceipt,
    CollectionReceipt,
    LaunchSpec,
    ProcessInspector,
    ProcessRef,
    ValidationReceipt,
)


ADAPTER_INTERFACE_VERSION = "mastermind.worker_adapter/v1"


@dataclasses.dataclass(frozen=True)
class AdapterDescriptor:
    """Non-secret facts about one reviewed execution interface."""

    adapter_id: str
    interface_version: str = ADAPTER_INTERFACE_VERSION
    structured_output: bool = True
    implemented: bool = False


ADAPTER_DESCRIPTORS: dict[str, AdapterDescriptor] = {
    "codex-cli": AdapterDescriptor(adapter_id="codex-cli", implemented=True),
    # Clean, deliberately unarmed seams for later provider work.  A routing
    # policy cannot bind a live worker through an unimplemented descriptor.
    "openai-compatible": AdapterDescriptor(
        adapter_id="openai-compatible", implemented=False
    ),
    "acp": AdapterDescriptor(adapter_id="acp", implemented=False),
}


def adapter_descriptor(adapter_id: str) -> AdapterDescriptor:
    """Resolve a reviewed adapter id or fail closed."""

    resolved = str(adapter_id).strip().lower()
    try:
        return ADAPTER_DESCRIPTORS[resolved]
    except KeyError as exc:
        raise ValueError(f"unknown worker adapter {adapter_id!r}") from exc


@runtime_checkable
class WorkerExecutionAdapter(Protocol):
    """Minimum process adapter consumed by :class:`ExecutiveSupervisor`."""

    inspector: ProcessInspector

    async def start(self, spec: LaunchSpec) -> ProcessRef: ...

    async def collect_result(self, ref: ProcessRef) -> CollectionReceipt: ...

    async def cancel(self, ref: ProcessRef, reason: str) -> CancelReceipt: ...

    async def run_validation_argv(
        self,
        spec: LaunchSpec,
        argv: Sequence[str],
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt: ...


__all__ = [
    "ADAPTER_DESCRIPTORS",
    "ADAPTER_INTERFACE_VERSION",
    "AdapterDescriptor",
    "WorkerExecutionAdapter",
    "adapter_descriptor",
]
