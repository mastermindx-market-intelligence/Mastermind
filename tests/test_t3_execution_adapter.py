"""Rev 5 D3 — T3ExecutionAdapter (built but unselected) coverage.

Fake T3NativeClientPort + fake binding source + injectable clock, following
the WO-10 fake patterns in tests/test_worker_adapter.py.  Pins the Rev 5
§3A/§7 semantics: binding-first fail-closed start, deterministic
clientRequestId, intent persisted before the native call, receipt + original
ref retained before the ACK, effect-unknown carrying the key, persisted
incremental-cursor exact-run reads, result-ledger ordering before the
CollectionReceipt, lease-stale cancel, requested-versus-settled cancel
reporting, and replay-only reattach under the SAME key + namespace.
"""
from __future__ import annotations

import dataclasses
import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from control_plane.child_execution_contracts import (
    C2_COMPLEX_BOUNDED,
    ExecutionBinding,
)
from control_plane.t3_execution_adapter import (
    T3_REQUEST_NAMESPACE,
    T3CancelReport,
    T3ExecutionAdapter,
    T3ExecutionAdapterError,
    T3InterruptOutcome,
    T3LaunchEffectUnknownError,
    T3UnknownOutcomeError,
    T3ThreadLaunchReceipt,
    T3ThreadReadResult,
    derive_t3_client_request_id,
)
from control_plane.worker_adapter import (
    ADAPTER_DESCRIPTORS,
    RecoverableWorkerExecutionAdapter,
    WorkerExecutionAdapter,
    adapter_descriptor,
    adapter_implementation,
    bind_reviewed_adapter,
    construct_reviewed_adapter,
)
from control_plane.worker_execution_contract import (
    CancelReceipt,
    ProcessInspector,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRecoveryBinding,
    WorkerRunStatus,
)

_HEX64 = "a" * 64
_LEASE_FUTURE = "2099-01-01T00:00:00Z"
_LEASE_PAST = "2000-01-01T00:00:00Z"
_LEASE_NAIVE = "2099-01-01T00:00:00"  # parseable but timezone-naive


def _clock() -> datetime:
    """Injectable clock: a fixed, timezone-aware moment."""
    return datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)


def _launch_spec(
    run_id: str = "run-1",
    worker_id: str = "workers/12",
    prompt: str = "do the work",
    run_dir: Path | None = None,
) -> WorkerLaunchSpec:
    if run_dir is None:
        run_dir = Path("/tmp/mmos-t3-run")
    return WorkerLaunchSpec(
        run_id=run_id, job_id="jobs/77", worker_id=worker_id,
        workspace_path=Path("/tmp/mmos-t3-ws"), run_dir=run_dir,
        prompt=prompt, result_schema_path=Path("/tmp/mmos-t3-run/input/schema.json"),
    )


def _binding(**overrides) -> ExecutionBinding:
    kwargs = dict(
        root_run_ref="root-1", immediate_parent_run_ref="parent-7",
        logical_child_key="child-a", request_digest=_HEX64,
        effective_complexity=C2_COMPLEX_BOUNDED, adapter_id="t3-native",
        worker_id="workers/12", fence_counter=7, lease_expiry=_LEASE_FUTURE,
    )
    kwargs.update(overrides)
    return ExecutionBinding(**kwargs)


class FakeInspector(ProcessInspector):
    """Minimal ProcessInspector stand-in."""

    def boot_session_id(self) -> str:
        return "boot-1"

    def identity(self, pid: int) -> tuple[str, int]:
        return (f"identity-{pid}", pid)

    def inspect(self, pid: int) -> object:
        return {"pid": pid}


_TERMINAL_NATIVE = {
    "succeeded", "completed", "failed", "cancelled", "canceled",
    "timed_out", "timeout",
}


class FakeT3Port:
    """In-memory T3NativeClientPort owned by the tests.

    Records the exact call order in ``trace`` and enforces upstream
    clientRequestId idempotency: one key maps to one receipt/thread forever
    (same principal + namespace + key => ORIGINAL thread).
    """

    def __init__(self, trace: list | None = None) -> None:
        self.trace = trace if trace is not None else []
        self.launch_calls: list = []
        self.replay_calls: list = []
        self.reads: list[tuple[str, str, str]] = []
        self.interrupts: list[tuple[WorkerProcessRef, str]] = []
        self.receipts_by_key: dict[str, T3ThreadLaunchReceipt] = {}
        self.status_by_thread: dict[str, str] = {}
        self.launch_error: Exception | None = None
        self.replay_error: Exception | None = None
        self.read_error: Exception | None = None
        self.interrupt_error: Exception | None = None
        self.unknown_outcome_on_launch = False
        self.unknown_outcome_on_replay = False
        self.read_override: T3ThreadReadResult | None = None
        self.interrupt_outcome = T3InterruptOutcome(
            requested=True, settled=False, already_exited=False,
            observed_native_status="running",
        )
        self.replay_thread_override: tuple[str, str] | None = None

    async def launch_thread(self, envelope) -> T3ThreadLaunchReceipt:
        key = envelope.client_request_id
        self.trace.append(("launch", key))
        self.launch_calls.append(envelope)
        if self.unknown_outcome_on_launch:
            raise T3UnknownOutcomeError("native launch outcome unknown")
        if self.launch_error is not None:
            raise self.launch_error
        receipt = self.receipts_by_key.get(key)
        if receipt is None:
            receipt = T3ThreadLaunchReceipt(
                thread_id=f"thr-{key[:8]}",
                run_id=f"t3run-{key[:8]}",
                project_id="proj-1",
                status="running",
                link=f"https://t3.example/thread/thr-{key[:8]}",
                created_at="2026-11-08T12:00:00+00:00",
                request_namespace=envelope.request_namespace,
                client_request_id=key,
            )
            self.receipts_by_key[key] = receipt
        return receipt

    async def replay_launch(self, envelope) -> T3ThreadLaunchReceipt:
        key = envelope.client_request_id
        self.trace.append(("replay", key))
        self.replay_calls.append(envelope)
        # Upstream idempotency: replaying an UNKNOWN key is a lost command,
        # not a fresh mint.
        receipt = self.receipts_by_key.get(key)
        if self.unknown_outcome_on_replay:
            raise T3UnknownOutcomeError("native replay outcome unknown")
        if self.replay_error is not None:
            raise self.replay_error
        if receipt is None:
            raise T3UnknownOutcomeError(
                f"no native command known for clientRequestId {key!r}"
            )
        if self.replay_thread_override is not None:
            thread_id, run_id = self.replay_thread_override
            return dataclasses.replace(receipt, thread_id=thread_id, run_id=run_id)
        return receipt

    async def read_thread(
        self, thread_id: str, run_id: str, cursor: str
    ) -> T3ThreadReadResult:
        self.trace.append(("read", thread_id, cursor))
        self.reads.append((thread_id, run_id, cursor))
        if self.read_error is not None:
            raise self.read_error
        if self.read_override is not None:
            return self.read_override
        native_status = self.status_by_thread.get(thread_id, "running")
        finished = native_status in _TERMINAL_NATIVE
        return T3ThreadReadResult(
            thread_id=thread_id, run_id=run_id,
            native_status=native_status,
            cursor=cursor, next_cursor=str(int(cursor or "0") + 1),
            result_ref=(f"t3://thread/{thread_id}/result" if finished else ""),
            result_payload=({"answer": "ok"} if finished else {}),
            started_at="2026-11-08T12:00:00+00:00",
            finished_at=("2026-11-08T12:05:00+00:00" if finished else ""),
            error=None, has_more=False,
        )

    async def interrupt_run(self, ref: WorkerProcessRef, reason: str):
        self.trace.append(("interrupt", ref.run_id, reason))
        self.interrupts.append((ref, reason))
        if self.interrupt_error is not None:
            raise self.interrupt_error
        return self.interrupt_outcome


class TraceIntentStore(dict):
    """Intent store that records every persist into a shared trace."""

    def __init__(self, trace: list) -> None:
        super().__init__()
        self._trace = trace

    def __setitem__(self, key, value) -> None:
        self._trace.append(("intent-persisted", key))
        super().__setitem__(key, value)


class TraceResultLedger(dict):
    """Result ledger that records every store into a shared trace."""

    def __init__(self, trace: list) -> None:
        super().__init__()
        self._trace = trace

    def __setitem__(self, key, value) -> None:
        self._trace.append(("ledger-store", key))
        super().__setitem__(key, value)


def _t3_adapter(
    port: FakeT3Port | None = None,
    binding: ExecutionBinding | None = None,
    binding_error: Exception | None = None,
    *,
    intent_store: dict | None = None,
    result_ledger: dict | None = None,
):
    port = port or FakeT3Port()
    current = {"binding": binding, "error": binding_error}

    def binding_source(spec: WorkerLaunchSpec):
        if current["error"] is not None:
            raise current["error"]
        return current["binding"]

    adapter = T3ExecutionAdapter(
        port, binding_source, FakeInspector(),
        clock=_clock, intent_store=intent_store, result_ledger=result_ledger,
    )
    return adapter, port, current


def _recovery_run_dir() -> Path:
    run_dir = Path(tempfile.mkdtemp(prefix="mmos-rev5-t3-recovery-"))
    (run_dir / "input").mkdir()
    return run_dir


def _recovery_binding(
    spec: WorkerLaunchSpec, ref: WorkerProcessRef, name: str = "prompt.txt"
) -> WorkerRecoveryBinding:
    """Build a real WorkerRecoveryBinding over a private prompt file."""
    import os

    prompt_path = spec.run_dir / "input" / name
    prompt_path.write_bytes(spec.prompt.encode("utf-8"))
    os.chmod(prompt_path, 0o600)
    return WorkerRecoveryBinding.bind(
        adapter_id="t3-native", spec=spec, process_ref=ref,
        prompt_path=prompt_path,
    )


# =============================================================================
# descriptor
# =============================================================================

class T3DescriptorTests(unittest.TestCase):
    def test_descriptor_is_registered_implemented_and_resolvable(self) -> None:
        # Flipped implemented=False -> True by the recorded LIVE receipt
        # (integrations/t3/live_proof/t3_live_proof_receipt.json; one real
        # t3_thread_launch + cursor read + result collection through the
        # adapter, 2026-11-09).  UNSELECTED status and the receipt path are
        # documented in tests/test_worker_adapter.py's pin docstring.
        descriptor = adapter_descriptor("t3-native")
        self.assertTrue(descriptor.implemented)
        self.assertEqual(descriptor.adapter_id, "t3-native")
        implementation = adapter_implementation("t3-native")
        self.assertIs(implementation, T3ExecutionAdapter)
        self.assertEqual(implementation.adapter_id, "t3-native")

    def test_t3_native_is_in_the_implemented_pin_with_documented_receipt(self) -> None:
        from tests.test_worker_adapter import MASTER_IMPLEMENTED_ADAPTER_IDS

        self.assertIs(ADAPTER_DESCRIPTORS["t3-native"].implemented, True)
        self.assertIn("t3-native", MASTER_IMPLEMENTED_ADAPTER_IDS)

    def test_constructed_adapter_binds_and_satisfies_protocols(self) -> None:
        adapter = construct_reviewed_adapter(
            "t3-native", FakeT3Port(), lambda spec: None, FakeInspector()
        )
        self.assertIsInstance(adapter, WorkerExecutionAdapter)
        self.assertIsInstance(adapter, RecoverableWorkerExecutionAdapter)
        descriptor = bind_reviewed_adapter(adapter, "t3-native")
        self.assertTrue(descriptor.implemented)


# =============================================================================
# start
# =============================================================================

class T3StartTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_refused_without_valid_execution_binding(self) -> None:
        cases = [
            ("no binding", None),
            ("wrong type", object()),
            ("other adapter", _binding(adapter_id="hermes-native")),
            ("worker mismatch", _binding(worker_id="workers/99")),
            ("empty worker", _binding(worker_id="")),
            ("expired lease", _binding(lease_expiry=_LEASE_PAST)),
            ("malformed lease", _binding(lease_expiry="not-a-time")),
            ("tz-naive lease", _binding(lease_expiry=_LEASE_NAIVE)),
        ]
        for label, binding in cases:
            with self.subTest(label):
                adapter, port, _ = _t3_adapter(binding=binding)
                with self.assertRaises(T3ExecutionAdapterError):
                    await adapter.start(_launch_spec())
                self.assertEqual(port.launch_calls, [])
                self.assertEqual(port.trace, [])
                self.assertEqual(len(adapter._launch_intents), 0)
                self.assertEqual(len(adapter._original_refs), 0)

    async def test_start_refused_when_binding_source_raises(self) -> None:
        adapter, port, _ = _t3_adapter(binding_error=RuntimeError("broker down"))
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.start(_launch_spec())
        self.assertEqual(port.launch_calls, [])
        self.assertEqual(len(adapter._launch_intents), 0)

    async def test_client_request_id_deterministic_and_stable(self) -> None:
        binding = _binding()
        first, port1, _ = _t3_adapter(binding=binding)
        second, port2, _ = _t3_adapter(binding=binding)
        ref1 = await first.start(_launch_spec())
        ref2 = await second.start(_launch_spec())
        self.assertEqual(
            port1.launch_calls[0].client_request_id,
            port2.launch_calls[0].client_request_id,
        )
        self.assertEqual(ref1.launch_nonce, ref2.launch_nonce)
        # The envelope key IS the derived deterministic key.
        self.assertEqual(
            derive_t3_client_request_id(binding),
            port1.launch_calls[0].client_request_id,
        )
        # Bounded and hex, per the donor's 256-char commandId cap.
        key = port1.launch_calls[0].client_request_id
        self.assertLessEqual(len(key), 256)
        int(key, 16)
        # Different request digest / child identity => different stable key.
        self.assertNotEqual(
            derive_t3_client_request_id(_binding(request_digest="b" * 64)),
            key,
        )
        self.assertNotEqual(
            derive_t3_client_request_id(_binding(logical_child_key="child-b")),
            key,
        )

    async def test_intent_persisted_before_native_call(self) -> None:
        trace: list = []
        port = FakeT3Port(trace=trace)
        store = TraceIntentStore(trace)
        adapter, _, _ = _t3_adapter(port=port, binding=_binding(),
                                    intent_store=store)
        await adapter.start(_launch_spec())
        self.assertEqual(
            [entry[0] for entry in trace],
            ["intent-persisted", "launch"],
        )

    async def test_start_retains_receipt_and_original_ref_before_ack(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        spec = _launch_spec()
        ref = await adapter.start(spec)
        # The ACK returns exactly the retained original ref object.
        self.assertIs(adapter._original_refs[spec.run_id], ref)
        receipt = adapter._launch_receipts[spec.run_id]
        self.assertEqual(receipt.thread_id, ref.provider_session_id)
        self.assertEqual(receipt.run_id, "t3run-" + ref.launch_nonce[:8])
        # The key rides in the neutral ref for every later identity check.
        self.assertEqual(
            ref.launch_nonce, port.launch_calls[0].client_request_id
        )
        self.assertEqual(ref.run_id, spec.run_id)

    async def test_lost_reply_effect_unknown_carries_client_request_id(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        port.unknown_outcome_on_launch = True
        with self.assertRaises(T3LaunchEffectUnknownError) as ctx:
            await adapter.start(_launch_spec())
        self.assertEqual(
            ctx.exception.client_request_id,
            derive_t3_client_request_id(_binding()),
        )
        # Never auto-retried: exactly one native launch call.
        self.assertEqual(len(port.launch_calls), 1)
        # The intent stays persisted; start() is dead for this run.
        self.assertEqual(len(adapter._launch_intents), 1)
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.start(_launch_spec())
        self.assertEqual(len(port.launch_calls), 1)

    async def test_clean_refusal_rolls_back_intent_and_reuses_same_key(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        port.launch_error = ValueError("authentication refused")
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.start(_launch_spec())
        # Clean refusal = no native effect: the intent is rolled back.
        self.assertEqual(len(adapter._launch_intents), 0)
        first_key = port.launch_calls[0].client_request_id
        port.launch_error = None
        ref = await adapter.start(_launch_spec())
        # A retry derives the SAME deterministic key — never a new one.
        self.assertEqual(port.launch_calls[1].client_request_id, first_key)
        self.assertTrue(ref.launch_nonce)

    async def test_start_refuses_duplicate_run(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        spec = _launch_spec()
        await adapter.start(spec)
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.start(spec)
        self.assertEqual(len(port.launch_calls), 1)


# =============================================================================
# status
# =============================================================================

class T3StatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_exact_run_read_and_cursor_advances_after_success(
        self,
    ) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        thread = ref.provider_session_id
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.RUNNING)
        self.assertEqual(port.reads, [(thread, f"t3run-{ref.launch_nonce[:8]}", "")])
        self.assertEqual(adapter._cursors[ref.run_id], "1")
        # The second read uses the PERSISTED advanced cursor.
        await adapter.status(ref)
        self.assertEqual(port.reads[-1], (thread, port.reads[0][1], "1"))

    async def test_status_does_not_advance_cursor_on_failed_read(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        port.read_error = RuntimeError("native read failed")
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.status(ref)
        self.assertEqual(adapter._cursors.get(ref.run_id, ""), "")
        port.read_error = None
        await adapter.status(ref)
        self.assertEqual(port.reads[-1][2], "")  # cursor was NOT advanced

    async def test_status_maps_unknown_native_state_to_non_terminal(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        port.status_by_thread[ref.provider_session_id] = "mysterious-state"
        state = await adapter.status(ref)
        # An unrecognized native state is never guessed as terminal.
        self.assertEqual(state, WorkerRunStatus.RUNNING)
        self.assertNotIn(state, {
            WorkerRunStatus.SUCCEEDED, WorkerRunStatus.FAILED,
            WorkerRunStatus.CANCELLED, WorkerRunStatus.TIMED_OUT,
            WorkerRunStatus.INVALID_RESULT,
        })

    async def test_status_refuses_foreign_read_result(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        port.read_override = T3ThreadReadResult(
            thread_id=ref.provider_session_id, run_id="t3run-other",
            native_status="succeeded", next_cursor="1",
        )
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.status(ref)
        self.assertEqual(adapter._cursors.get(ref.run_id, ""), "")

    async def test_status_refuses_unknown_or_swapped_refs(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        await adapter.start(_launch_spec())
        unknown = _neutral_ref_for("run-unknown")
        for op in (
            lambda: adapter.status(unknown),
            lambda: adapter.collect_result(unknown),
            lambda: adapter.cancel(unknown, "stop"),
        ):
            with self.assertRaises(T3ExecutionAdapterError):
                await op()


# =============================================================================
# collect_result
# =============================================================================

class T3CollectTests(unittest.IsolatedAsyncioTestCase):
    async def test_collect_stores_result_reference_before_the_receipt(self) -> None:
        trace: list = []
        port = FakeT3Port(trace=trace)
        ledger = TraceResultLedger(trace)
        adapter, _, _ = _t3_adapter(port=port, binding=_binding(),
                                    result_ledger=ledger)
        ref = await adapter.start(_launch_spec())
        trace.clear()
        port.status_by_thread[ref.provider_session_id] = "succeeded"
        # Watch the receipt construction to pin the ordering.
        original_build = adapter._build_collection_receipt

        def spy_build(original, read, state):
            trace.append(("build-receipt",))
            return original_build(original, read, state)

        adapter._build_collection_receipt = spy_build
        receipt = await adapter.collect_result(ref)
        # Ordering: port read -> ledger store -> receipt construction.
        self.assertEqual(
            [entry[0] for entry in trace],
            ["read", "ledger-store", "build-receipt"],
        )
        # Reading T3 is NOT company acceptance: the ledger holds the
        # canonical reference as evidence, separately from the neutral floor.
        entry = ledger[ref.run_id]
        self.assertEqual(entry.result_ref, f"t3://thread/{ref.provider_session_id}/result")
        self.assertEqual(receipt.process_ref, ref)
        self.assertEqual(receipt.result.run_id, ref.run_id)
        self.assertEqual(receipt.result.status, WorkerRunStatus.SUCCEEDED)
        self.assertEqual(
            receipt.result_sha256,
            hashlib.sha256(entry.result_ref.encode("utf-8")).hexdigest(),
        )

    async def test_collect_refuses_non_terminal_run(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        port.status_by_thread[ref.provider_session_id] = "running"
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.collect_result(ref)
        self.assertEqual(len(adapter._result_ledger), 0)

    async def test_collect_refuses_a_different_run_result(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        port.read_override = T3ThreadReadResult(
            thread_id=ref.provider_session_id, run_id="t3run-other",
            native_status="succeeded", next_cursor="1",
            result_ref="t3://thread/x/result",
        )
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.collect_result(ref)
        # A foreign result is never ledgered — no replacement.
        self.assertEqual(len(adapter._result_ledger), 0)

    async def test_collect_refuses_terminal_read_without_canonical_reference(
        self,
    ) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        native_run = adapter._launch_receipts[ref.run_id].run_id
        port.read_override = T3ThreadReadResult(
            thread_id=ref.provider_session_id, run_id=native_run,
            native_status="succeeded", next_cursor="1", result_ref="",
        )
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.collect_result(ref)
        self.assertEqual(len(adapter._result_ledger), 0)


# =============================================================================
# cancel
# =============================================================================

class T3CancelTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_allowed_with_expired_binding_lease(self) -> None:
        adapter, port, current = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        # The binding goes stale AFTER start: cancel must still work.
        current["binding"] = _binding(lease_expiry=_LEASE_PAST)
        receipt = await adapter.cancel(ref, "superseded")
        self.assertTrue(receipt.signal_sent)
        self.assertFalse(receipt.escalated_to_sigkill)
        self.assertEqual(len(port.interrupts), 1)
        self.assertEqual(port.interrupts[0][0], ref)

    async def test_cancel_reports_requested_not_settled_then_settles(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        receipt = await adapter.cancel(ref, "superseded")
        self.assertIsInstance(receipt, CancelReceipt)
        self.assertTrue(receipt.signal_sent)
        report = adapter.cancel_report(ref.run_id)
        self.assertIsInstance(report, T3CancelReport)
        self.assertTrue(report.requested)
        self.assertFalse(report.settled)
        self.assertIsNone(report.settled_at)
        # Requested cancellation that has not settled: honest intermediate.
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.CANCELLING)
        # The native side settles; only then does the report and status.
        port.status_by_thread[ref.provider_session_id] = "cancelled"
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.CANCELLED)
        report = adapter.cancel_report(ref.run_id)
        self.assertTrue(report.settled)
        self.assertEqual(report.settled_state, "CANCELLED")
        self.assertIsNotNone(report.settled_at)

    async def test_cancel_settles_immediately_when_outcome_confirms_terminal(
        self,
    ) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        port.interrupt_outcome = T3InterruptOutcome(
            requested=True, settled=True, already_exited=False,
            observed_native_status="cancelled",
            finished_at="2026-11-08T12:02:00+00:00",
        )
        await adapter.cancel(ref, "duplicate")
        report = adapter.cancel_report(ref.run_id)
        self.assertTrue(report.requested)
        self.assertTrue(report.settled)
        self.assertEqual(report.settled_state, "CANCELLED")
        port.status_by_thread[ref.provider_session_id] = "cancelled"
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.CANCELLED)

    async def test_cancel_does_not_claim_settled_without_terminal_state(self) -> None:
        """Reconcile native terminal state before claiming settled."""
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        port.interrupt_outcome = T3InterruptOutcome(
            requested=True, settled=True, already_exited=False,
            observed_native_status="",  # no observed native state
        )
        await adapter.cancel(ref, "interrupt sent")
        report = adapter.cancel_report(ref.run_id)
        self.assertTrue(report.requested)
        # A claimed settle without a reconciled terminal state stays unsettled.
        self.assertFalse(report.settled)
        self.assertIsNone(report.settled_state)
        port.status_by_thread[ref.provider_session_id] = "cancelled"
        await adapter.status(ref)
        report = adapter.cancel_report(ref.run_id)
        self.assertTrue(report.settled)
        self.assertEqual(report.settled_state, "CANCELLED")

    async def test_cancel_interrupt_lost_reply_records_requested_unsettled(
        self,
    ) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        port.interrupt_error = T3UnknownOutcomeError("lost reply")
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.cancel(ref, "stop")
        report = adapter.cancel_report(ref.run_id)
        self.assertTrue(report.requested)
        self.assertFalse(report.signal_sent)
        self.assertFalse(report.settled)

    async def test_cancel_requires_nonempty_reason(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.cancel(ref, "  ")
        self.assertEqual(port.interrupts, [])


# =============================================================================
# run_validation_argv (floor method, honest refusal)
# =============================================================================

class T3RunValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_validation_argv_refuses_no_native_argv_seam(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        before = list(port.trace)
        for argv in (["hermes", "--version"], "hermes --version", []):
            with self.subTest(argv=argv):
                with self.assertRaises(T3ExecutionAdapterError):
                    await adapter.run_validation_argv(_launch_spec(), argv)
        # Only the launch ever touched the port; no validation call exists.
        self.assertEqual(port.trace, before)


# =============================================================================
# reattach
# =============================================================================

class T3ReattachTests(unittest.IsolatedAsyncioTestCase):
    async def test_reattach_returns_retained_original_without_any_port_call(
        self,
    ) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(spec)
        before = list(port.trace)
        binding = _recovery_binding(spec, ref)
        reattached = await adapter.reattach(spec, binding)
        self.assertIs(reattached, ref)
        # Recovery of a retained execution needs NO native call at all.
        self.assertEqual(len(port.launch_calls), 1)
        self.assertEqual(port.replay_calls, [])
        self.assertEqual(port.trace, before)
        self.assertEqual(port.reads, [])

    async def test_reattach_refuses_foreign_or_drifted_bindings(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(spec)
        foreign = _recovery_binding(spec, ref)
        object.__setattr__(foreign, "adapter_id", "hermes-native")
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.reattach(spec, foreign)
        drifted = _recovery_binding(
            _launch_spec(prompt="a different task", run_dir=_recovery_run_dir()),
            ref, name="prompt2.txt",
        )
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.reattach(spec, drifted)
        other_run = _recovery_binding(spec, ref)
        object.__setattr__(other_run, "process_ref", _neutral_ref_for("run-other"))
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.reattach(spec, other_run)
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.reattach(spec, object())
        self.assertEqual(len(port.launch_calls), 1)
        self.assertEqual(port.replay_calls, [])

    async def test_reattach_after_restart_replays_same_key_and_thread(self) -> None:
        """Idempotent replay: SAME clientRequestId + namespace, original thread."""
        spec = _launch_spec(run_dir=_recovery_run_dir())
        port = FakeT3Port()
        first, _, _ = _t3_adapter(port=port, binding=_binding())
        ref = await first.start(spec)
        original_key = ref.launch_nonce
        binding = _recovery_binding(spec, ref)
        # Coordinator restart: a fresh adapter instance, same native owner —
        # no persisted intent, so the SAME command is replayed.
        second, _, _ = _t3_adapter(port=port, binding=_binding())
        reattached = await second.reattach(spec, binding)
        self.assertEqual(reattached, ref)
        # NEVER a fresh launch, and the replay used the SAME key + namespace.
        self.assertEqual(len(port.launch_calls), 1)
        self.assertEqual(len(port.replay_calls), 1)
        replayed = port.replay_calls[0]
        self.assertEqual(replayed.client_request_id, original_key)
        self.assertEqual(replayed.request_namespace, T3_REQUEST_NAMESPACE)
        self.assertEqual(("replay", original_key), port.trace[-1])
        # The recovered execution is now retained: the next reattach replays
        # nothing and returns the same object.
        again = await second.reattach(spec, binding)
        self.assertIs(again, reattached)
        self.assertEqual(len(port.replay_calls), 1)

    async def test_reattach_refuses_replay_returning_a_different_thread(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        port = FakeT3Port()
        first, _, _ = _t3_adapter(port=port, binding=_binding())
        ref = await first.start(spec)
        binding = _recovery_binding(spec, ref)
        second, _, _ = _t3_adapter(port=port, binding=_binding())
        port.replay_thread_override = ("thr-other", "t3run-other")
        with self.assertRaises(T3ExecutionAdapterError):
            await second.reattach(spec, binding)
        # Never a replacement launch; nothing was adopted.
        self.assertEqual(len(port.launch_calls), 1)
        self.assertEqual(len(port.replay_calls), 1)
        self.assertEqual(len(second._original_refs), 0)
        self.assertEqual(len(second._launch_receipts), 0)

    async def test_reattach_replay_lost_reply_carries_the_key(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        port = FakeT3Port()
        first, _, _ = _t3_adapter(port=port, binding=_binding())
        ref = await first.start(spec)
        binding = _recovery_binding(spec, ref)
        second, _, _ = _t3_adapter(port=port, binding=_binding())
        port.replay_error = T3UnknownOutcomeError("replay lost")
        with self.assertRaises(T3LaunchEffectUnknownError) as ctx:
            await second.reattach(spec, binding)
        self.assertEqual(ctx.exception.client_request_id, ref.launch_nonce)
        self.assertEqual(len(port.launch_calls), 1)

    async def test_reattach_refuses_without_original_key(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        port = FakeT3Port()
        adapter, _, _ = _t3_adapter(port=port, binding=_binding())
        ref = await adapter.start(spec)
        keyless = dataclasses.replace(ref, launch_nonce="")
        binding = _recovery_binding(spec, keyless)
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.reattach(spec, binding)
        self.assertEqual(port.replay_calls, [])


def _neutral_ref_for(run_id: str) -> WorkerProcessRef:
    """A neutral ref shaped like the T3 adapter's, for mismatch tests."""
    from control_plane.t3_execution_adapter import _T3_REMOTE_BINARY_PLACEHOLDER

    return WorkerProcessRef(
        run_id=run_id, pid=0, pgid=0, session_id=None,
        process_start_identity="t3:thr-x:t3run-x",
        boot_session_id="t3-native:thr-x",
        launch_nonce="k" * 64, provider_session_id="thr-x",
        stdout_path="t3://thread/thr-x/events",
        stderr_path="t3://thread/thr-x/events",
        result_path="t3://thread/thr-x/result",
        started_at="2026-11-08T12:00:00+00:00",
        binary=_T3_REMOTE_BINARY_PLACEHOLDER, base_sha="",
    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
