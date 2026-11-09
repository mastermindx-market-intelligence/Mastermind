"""Hermes-native worker adapter (MMOS V1 WO-10, Rev 4 §S3.D l.259–272).

``HermesWorkerAdapter`` implements the incumbent ``WorkerExecutionAdapter``
floor (``control_plane/worker_adapter.py``) plus the optional
``RecoverableWorkerExecutionAdapter.reattach`` seam against the shared
child-execution contracts (WO-02, ``control_plane/child_execution_contracts.py``):

* ``start`` validates the *current* broker ``ExecutionBinding.v1`` resolved
  through the authenticated owner, launches only through the native
  process/session owner port, and retains the original native
  ``WorkerProcessRef`` *before* acknowledging start.
* ``cancel`` invokes the real native stop owner and reports requested versus
  settled cancellation honestly; a requested-but-unsettled stop surfaces as
  ``CANCELLING`` until the native state settles.
* ``reattach`` recovers the SAME execution after interruption: it returns the
  original native reference and never launches, so a caller timeout can never
  mint a replacement execution.
* ``status`` / ``collect_result`` read the actual native state and the
  original retained outputs/artifacts.

Descriptor status: registered in ``ADAPTER_DESCRIPTORS`` as ``hermes-native``
and BUILT, but deliberately **UNSELECTED** — no routing policy binds a live
worker through this adapter until the incumbent runtime selects it (Rev 4
l.253 honest-behavior table).  ``run_validation_argv`` preserves the current
explicitly authorized command contract; its presence schedules no campaign.

The native process/session owner (Engineering's native runner, WO-12) is
injected through :class:`HermesNativeRunnerPort`.  This module never spawns
processes itself, holds no credentials, and adds no signing authority (Rev 4
§S3.D: use the incumbent broker owner channel only).
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from control_plane.child_execution_contracts import ExecutionBinding
from control_plane.worker_adapter import AdapterBindingError
from control_plane.worker_execution_contract import (
    CancelReceipt,
    CollectionReceipt,
    ProcessInspector,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRecoveryBinding,
    WorkerRunStatus,
    worker_launch_spec_sha256,
)

HERMES_NATIVE_ADAPTER_ID = "hermes-native"

_TERMINAL_STATES = frozenset({
    WorkerRunStatus.SUCCEEDED,
    WorkerRunStatus.FAILED,
    WorkerRunStatus.INVALID_RESULT,
    WorkerRunStatus.CANCELLED,
    WorkerRunStatus.TIMED_OUT,
})


class HermesWorkerAdapterError(AdapterBindingError):
    """Hermes-native adapter refused an operation; fail closed, never guess."""


@dataclasses.dataclass(frozen=True)
class NativeCancelOutcome:
    """What the real native stop owner reported about one stop request."""

    requested: bool
    settled: bool
    already_exited: bool
    escalated_to_sigkill: bool = False
    finished_at: str = ""


@dataclasses.dataclass(frozen=True)
class HermesCancelReport:
    """Honest requested-versus-settled view of one cancellation."""

    run_id: str
    reason: str
    requested: bool
    signal_sent: bool
    escalated_to_sigkill: bool
    already_exited: bool
    settled: bool
    requested_at: str
    settled_at: str | None
    settled_state: str | None
    finished_at: str


@dataclasses.dataclass
class _CancelLedgerEntry:
    reason: str
    requested: bool
    signal_sent: bool
    escalated_to_sigkill: bool
    already_exited: bool
    settled: bool
    requested_at: str
    settled_at: str | None = None
    settled_state: str | None = None
    finished_at: str = ""


@runtime_checkable
class HermesNativeRunnerPort(Protocol):
    """The existing native process/session owner this adapter launches through.

    Engineering's native runner (WO-12) implements this port; tests inject a
    fake.  The adapter never bypasses it to touch processes directly.
    """

    async def launch(self, spec: WorkerLaunchSpec) -> WorkerProcessRef: ...

    async def native_state(self, ref: WorkerProcessRef) -> WorkerRunStatus: ...

    async def collect(self, ref: WorkerProcessRef) -> CollectionReceipt: ...

    async def terminate(
        self, ref: WorkerProcessRef, reason: str
    ) -> NativeCancelOutcome: ...

    async def validate_argv(
        self,
        spec: WorkerLaunchSpec,
        argv: Sequence[str],
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt: ...

    def knows_execution(self, ref: WorkerProcessRef) -> bool:
        """Synchronously confirm the owner still holds this exact execution."""
        ...


class HermesWorkerAdapter:
    """Built-but-unselected Hermes adapter over the incumbent worker protocol.

    Every method follows Rev 4 §S3.D l.265–270.  Selection is a deployment act
    by the incumbent runtime; constructing or registering this class selects
    nothing.
    """

    adapter_id = HERMES_NATIVE_ADAPTER_ID

    def __init__(
        self,
        runner: HermesNativeRunnerPort,
        binding_source: Callable[[WorkerLaunchSpec], ExecutionBinding | None],
        inspector: ProcessInspector,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._runner = runner
        self._binding_source = binding_source
        self.inspector = inspector
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # The original native ref per run, retained at start BEFORE the ACK.
        self._original_refs: dict[str, WorkerProcessRef] = {}
        # The broker binding that authorized each start (observability only).
        self._start_bindings: dict[str, ExecutionBinding] = {}
        # Requested-versus-settled cancellation ledger per run.
        self._cancel_records: dict[str, _CancelLedgerEntry] = {}

    # --- start -------------------------------------------------------------

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        """Launch through the native owner under the current broker binding.

        Refuses fail-closed without a valid, current ``ExecutionBinding``.
        The original native reference is retained *before* the returned ref
        acknowledges start.
        """

        if not isinstance(spec, WorkerLaunchSpec):
            raise HermesWorkerAdapterError("start requires a WorkerLaunchSpec")
        if spec.run_id in self._original_refs:
            raise HermesWorkerAdapterError(
                "run was already started; reattach recovers the same execution "
                "instead of starting a replacement"
            )
        binding = self._require_current_binding(spec)
        ref = await self._runner.launch(spec)
        if not isinstance(ref, WorkerProcessRef) or ref.run_id != spec.run_id:
            raise HermesWorkerAdapterError(
                "native owner returned a reference for a different run; "
                "refusing to acknowledge start"
            )
        # Retain the ORIGINAL native ref before the ACK (the return below).
        self._original_refs[spec.run_id] = ref
        self._start_bindings[spec.run_id] = binding
        return ref

    def _require_current_binding(self, spec: WorkerLaunchSpec) -> ExecutionBinding:
        try:
            binding = self._binding_source(spec)
        except AdapterBindingError:
            raise
        except Exception as exc:
            raise HermesWorkerAdapterError(
                f"broker ExecutionBinding resolution failed: {exc}"
            ) from exc
        if binding is None:
            raise HermesWorkerAdapterError(
                "refused: no current broker ExecutionBinding for this launch"
            )
        if not isinstance(binding, ExecutionBinding):
            raise HermesWorkerAdapterError(
                "refused: broker binding is not an ExecutionBinding.v1"
            )
        if binding.adapter_id != HERMES_NATIVE_ADAPTER_ID:
            raise HermesWorkerAdapterError(
                "refused: binding is not a fenced assignment of the "
                f"{HERMES_NATIVE_ADAPTER_ID!r} adapter"
            )
        if not binding.worker_id or binding.worker_id != spec.worker_id:
            raise HermesWorkerAdapterError(
                "refused: binding worker assignment does not match the launch spec"
            )
        if binding.lease_expiry:
            try:
                expiry = datetime.fromisoformat(
                    binding.lease_expiry.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise HermesWorkerAdapterError(
                    "refused: binding lease expiry is malformed"
                ) from exc
            if expiry.tzinfo is None or expiry.utcoffset() is None:
                raise HermesWorkerAdapterError(
                    "refused: binding lease expiry is not timezone aware"
                )
            if expiry <= self._clock():
                raise HermesWorkerAdapterError(
                    "refused: binding lease has expired (stale fenced assignment)"
                )
        return binding

    # --- status ------------------------------------------------------------

    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus:
        """Return the actual native state for that attempt."""

        original = self._require_original_ref(ref)
        state = await self._runner.native_state(original)
        entry = self._cancel_records.get(original.run_id)
        if entry is not None and not entry.settled:
            if state in _TERMINAL_STATES:
                self._settle(entry, state)
            else:
                # Requested cancellation that has not settled yet: report the
                # honest intermediate state, never a premature CANCELLED.
                return WorkerRunStatus.CANCELLING
        return state

    # --- collect_result ----------------------------------------------------

    async def collect_result(self, ref: WorkerProcessRef) -> CollectionReceipt:
        """Read the original retained output/artifacts and measured usage."""

        original = self._require_original_ref(ref)
        receipt = await self._runner.collect(original)
        if not isinstance(receipt, CollectionReceipt) or (
            receipt.process_ref.run_id != original.run_id
        ):
            raise HermesWorkerAdapterError(
                "collection did not return the original retained execution's "
                "result; refusing a replacement"
            )
        return receipt

    # --- cancel ------------------------------------------------------------

    async def cancel(self, ref: WorkerProcessRef, reason: str) -> CancelReceipt:
        """Invoke the real native stop owner; report requested vs settled."""

        original = self._require_original_ref(ref)
        if not isinstance(reason, str) or not reason.strip():
            raise HermesWorkerAdapterError("cancel requires a non-empty reason")
        outcome = await self._runner.terminate(original, reason)
        now = self._now_iso()
        settled = bool(outcome.settled or outcome.already_exited)
        self._cancel_records[original.run_id] = _CancelLedgerEntry(
            reason=reason,
            requested=bool(outcome.requested),
            signal_sent=bool(outcome.requested),
            escalated_to_sigkill=bool(outcome.escalated_to_sigkill),
            already_exited=bool(outcome.already_exited),
            settled=settled,
            requested_at=now,
            finished_at=outcome.finished_at or now,
        )
        return CancelReceipt(
            run_id=original.run_id,
            reason=reason,
            signal_sent=bool(outcome.requested),
            escalated_to_sigkill=bool(outcome.escalated_to_sigkill),
            already_exited=bool(outcome.already_exited),
            finished_at=outcome.finished_at or now,
        )

    def cancel_report(self, run_id: str) -> HermesCancelReport | None:
        """The requested-versus-settled record for a run, if any."""

        entry = self._cancel_records.get(str(run_id))
        if entry is None:
            return None
        return HermesCancelReport(
            run_id=str(run_id),
            reason=entry.reason,
            requested=entry.requested,
            signal_sent=entry.signal_sent,
            escalated_to_sigkill=entry.escalated_to_sigkill,
            already_exited=entry.already_exited,
            settled=entry.settled,
            requested_at=entry.requested_at,
            settled_at=entry.settled_at,
            settled_state=entry.settled_state,
            finished_at=entry.finished_at,
        )

    def _settle(self, entry: _CancelLedgerEntry, state: WorkerRunStatus) -> None:
        entry.settled = True
        entry.settled_at = self._now_iso()
        entry.settled_state = state.value

    # --- run_validation_argv -----------------------------------------------

    async def run_validation_argv(
        self,
        spec: WorkerLaunchSpec,
        argv: Sequence[str],
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt:
        """Preserve the explicitly authorized command contract and scope.

        Presence of this method does not schedule a test campaign (Rev 4
        §S3.D l.268–269).
        """

        if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
            raise HermesWorkerAdapterError(
                "validation argv must be a sequence of command arguments"
            )
        if not argv or not all(isinstance(item, str) for item in argv):
            raise HermesWorkerAdapterError(
                "validation argv must be an explicitly authorized non-empty "
                "command"
            )
        if timeout_seconds <= 0:
            raise HermesWorkerAdapterError("validation timeout must be positive")
        return await self._runner.validate_argv(
            spec, tuple(argv), timeout_seconds=timeout_seconds
        )

    # --- reattach ----------------------------------------------------------

    def reattach(
        self, spec: WorkerLaunchSpec, binding: WorkerRecoveryBinding
    ) -> WorkerProcessRef:
        """Recover the SAME execution; never create a replacement.

        A caller timeout is never a reason to launch again: this method never
        calls ``launch`` and never mints a new reference.
        """

        if not isinstance(spec, WorkerLaunchSpec):
            raise HermesWorkerAdapterError("reattach requires a WorkerLaunchSpec")
        if not isinstance(binding, WorkerRecoveryBinding):
            raise HermesWorkerAdapterError(
                "reattach requires a WorkerRecoveryBinding"
            )
        if binding.adapter_id != HERMES_NATIVE_ADAPTER_ID:
            raise HermesWorkerAdapterError(
                "recovery binding belongs to another adapter"
            )
        original = binding.process_ref
        if original.run_id != spec.run_id:
            raise HermesWorkerAdapterError(
                "recovery binding run identity does not match the spec"
            )
        if binding.launch_spec_sha256 != worker_launch_spec_sha256(spec):
            raise HermesWorkerAdapterError(
                "recovery binding does not bind this launch spec"
            )
        retained = self._original_refs.get(spec.run_id)
        if retained is not None:
            if retained != original:
                raise HermesWorkerAdapterError(
                    "retained original native ref differs from the recovery "
                    "binding; refusing to swap executions"
                )
            return retained
        # Coordinator/process restart: adopt the ORIGINAL ref only if the
        # native owner still knows that exact execution.  No launch happens.
        if not self._runner.knows_execution(original):
            raise HermesWorkerAdapterError(
                "the original native execution is unknown to the native "
                "owner; refusing to create a replacement"
            )
        self._original_refs[spec.run_id] = original
        return original

    # --- internals ---------------------------------------------------------

    def _require_original_ref(self, ref: WorkerProcessRef) -> WorkerProcessRef:
        if not isinstance(ref, WorkerProcessRef):
            raise HermesWorkerAdapterError("operation requires a WorkerProcessRef")
        retained = self._original_refs.get(ref.run_id)
        if retained is None:
            raise HermesWorkerAdapterError(
                f"no original native ref retained for run {ref.run_id!r}"
            )
        if retained != ref:
            raise HermesWorkerAdapterError(
                "ref does not match the retained original native ref"
            )
        return retained

    def _now_iso(self) -> str:
        return self._clock().isoformat()


__all__ = [
    "HERMES_NATIVE_ADAPTER_ID",
    "HermesCancelReport",
    "HermesNativeRunnerPort",
    "HermesWorkerAdapter",
    "HermesWorkerAdapterError",
    "NativeCancelOutcome",
]
