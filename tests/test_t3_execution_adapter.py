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
    InMemoryT3AdapterStateStore,
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
    t3_request_namespace,
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

    def __init__(
        self, trace: list | None = None, principal: str | None = "oauth-client-test"
    ) -> None:
        # The attested authenticated principal (``None`` models a port that
        # cannot attest: launches and principal-scoped recovery are refused).
        self.principal = principal
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

    def authenticated_namespace(self) -> str | None:
        return self.principal

    def expected_launch_thread_id(self, client_request_id: str) -> str:
        """Mirror this fake's principal-independent minting rule (re-audit R1)."""
        return f"thr-{client_request_id[:8]}"

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


class TracingStateStore(InMemoryT3AdapterStateStore):
    """State store that records ordering-critical writes into a shared trace."""

    def __init__(self, trace: list) -> None:
        super().__init__()
        self._trace = trace

    def claim_launch_intent(self, intent, *, binding, spec, claim_token) -> bool:
        self._trace.append(("intent-persisted", intent.run_id))
        return super().claim_launch_intent(
            intent, binding=binding, spec=spec, claim_token=claim_token
        )

    def put_result_reference(self, reference):
        self._trace.append(("ledger-store", reference.run_id))
        return super().put_result_reference(reference)


def _t3_adapter(
    port: FakeT3Port | None = None,
    binding: ExecutionBinding | None = None,
    binding_error: Exception | None = None,
    *,
    state_store=None,
):
    port = port or FakeT3Port()
    current = {"binding": binding, "error": binding_error}

    def binding_source(spec: WorkerLaunchSpec):
        if current["error"] is not None:
            raise current["error"]
        return current["binding"]

    adapter = T3ExecutionAdapter(
        port, binding_source, FakeInspector(),
        clock=_clock, state_store=state_store,
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
                self.assertIsNone(adapter.launch_intent("run-1"))
                self.assertIsNone(adapter.retained_original_ref("run-1"))

    async def test_start_refused_when_binding_source_raises(self) -> None:
        adapter, port, _ = _t3_adapter(binding_error=RuntimeError("broker down"))
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.start(_launch_spec())
        self.assertEqual(port.launch_calls, [])
        self.assertIsNone(adapter.launch_intent("run-1"))

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
        store = TracingStateStore(trace)
        adapter, _, _ = _t3_adapter(port=port, binding=_binding(),
                                    state_store=store)
        await adapter.start(_launch_spec())
        self.assertEqual(
            [entry[0] for entry in trace],
            ["intent-persisted", "launch"],
        )

    async def test_start_retains_receipt_and_original_ref_before_ack(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        spec = _launch_spec()
        ref = await adapter.start(spec)
        # The ACK returns exactly the retained original ref (durable read).
        self.assertEqual(adapter.retained_original_ref(spec.run_id), ref)
        receipt = adapter.launch_receipt(spec.run_id)
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
        self.assertIsNotNone(adapter.launch_intent("run-1"))
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.start(_launch_spec())
        self.assertEqual(len(port.launch_calls), 1)

    async def test_clean_refusal_rolls_back_intent_and_reuses_same_key(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        port.launch_error = ValueError("authentication refused")
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.start(_launch_spec())
        # Clean refusal = no native effect: the intent is rolled back.
        self.assertIsNone(adapter.launch_intent("run-1"))
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
        self.assertEqual(adapter.read_cursor(ref.run_id), "1")
        # The second read uses the PERSISTED advanced cursor.
        await adapter.status(ref)
        self.assertEqual(port.reads[-1], (thread, port.reads[0][1], "1"))

    async def test_status_does_not_advance_cursor_on_failed_read(self) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        port.read_error = RuntimeError("native read failed")
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.status(ref)
        self.assertEqual(adapter.read_cursor(ref.run_id), "")
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
        self.assertEqual(adapter.read_cursor(ref.run_id), "")

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
        ledger = TracingStateStore(trace)
        adapter, _, _ = _t3_adapter(port=port, binding=_binding(),
                                    state_store=ledger)
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
        entry = adapter.result_ledger_entry(ref.run_id)
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
        self.assertIsNone(adapter.result_ledger_entry(ref.run_id))

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
        self.assertIsNone(adapter.result_ledger_entry(ref.run_id))

    async def test_collect_refuses_terminal_read_without_canonical_reference(
        self,
    ) -> None:
        adapter, port, _ = _t3_adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        native_run = adapter.launch_receipt(ref.run_id).run_id
        port.read_override = T3ThreadReadResult(
            thread_id=ref.provider_session_id, run_id=native_run,
            native_status="succeeded", next_cursor="1", result_ref="",
        )
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.collect_result(ref)
        self.assertIsNone(adapter.result_ledger_entry(ref.run_id))


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
        # The durable retained copy is the authority: recovery returns the
        # VALUE-equal original ref (a store round-trip reconstructs it).
        self.assertEqual(reattached, ref)
        self.assertEqual(adapter.retained_original_ref(spec.run_id), ref)
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
        # The principal-qualified namespace of the attested port.
        self.assertEqual(
            replayed.request_namespace, t3_request_namespace("oauth-client-test")
        )
        self.assertEqual(("replay", original_key), port.trace[-1])
        # The recovered execution is now retained: the next reattach replays
        # nothing and returns the same object.
        again = await second.reattach(spec, binding)
        self.assertEqual(again, reattached)
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
        self.assertIsNone(second.retained_original_ref(spec.run_id))
        self.assertIsNone(second.launch_receipt(spec.run_id))

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


# =============================================================================
# A3 audit rework — reference live port (findings #3 live attestation, #4, #7,
# #13).  New names are resolved through the module INSIDE each test so this
# file still imports against the pre-rework adapter (fail-before per test).
# =============================================================================

import base64 as _b64  # noqa: E402
import json as _json  # noqa: E402

import control_plane.t3_execution_adapter as _t3m  # noqa: E402

_SID = "3f2a6c1e-0d4b-4a8e-9b1f-2c7d5e6a8b90"


def _session_token(sid: str = _SID, sub: str = "mcp-client", kind: str = "session") -> str:
    claims = {
        "v": 1, "kind": kind, "sid": sid, "sub": sub,
        "scopes": ["orchestration:operate"], "method": "bearer-access-token",
        "iat": 1, "exp": 2,
    }
    body = _b64.urlsafe_b64encode(_json.dumps(claims).encode()).rstrip(b"=").decode()
    return body + ".signature-not-checked-here"


class FakeMcpTransport:
    """Models the donor's MCP thread tools at the pin for one client session.

    ``failures`` maps a tool name to an exception raised INSTEAD of answering
    (after recording the call — i.e. the request was sent).
    """

    def __init__(self, namespace: str = f"client:{_SID}") -> None:
        self.namespace = namespace
        self.calls: list[tuple[str, dict]] = []
        self.failures: dict[str, BaseException] = {}
        self.runs: dict[str, str] = {}  # threadId -> native runId
        self.run_status: dict[str, str] = {}
        self.items: dict[str, list[dict]] = {}
        self.thread_override: str | None = None
        self.interrupt_echo_run: str | None = None

    def __call__(self, tool: str, arguments):
        self.calls.append((tool, dict(arguments)))
        if tool in self.failures:
            raise self.failures[tool]
        if tool == "t3_thread_launch":
            thread_id = self.thread_override or _t3m.t3_expected_launch_thread_id(
                self.namespace, arguments["clientRequestId"]
            )
            run_id = self.runs.setdefault(thread_id, f"run-{len(self.runs) + 1}")
            self.run_status.setdefault(run_id, "running")
            return {"threadId": thread_id, "runId": run_id, "projectId": "p-1",
                    "status": "running", "link": f"https://app.t3/{thread_id}"}
        if tool == "t3_thread_read":
            thread_id = arguments["threadId"]
            runs = [
                {"runId": run, "status": self.run_status.get(run, "running")}
                for tid, run in self.runs.items() if tid == thread_id
            ]
            items = self.items.get(thread_id, [])
            after = arguments.get("afterPosition")
            page = [dict(i, sourceThreadId=thread_id, textTruncated=False)
                    for i in items if after is None or i["position"] > after]
            return {"thread": {"threadId": thread_id, "status": "idle"},
                    "recentRuns": runs, "items": page,
                    "nextPosition": (page[-1]["position"] if page else after),
                    "hasMore": False}
        if tool == "t3_thread_interrupt":
            return {"threadId": arguments["threadId"],
                    "runId": self.interrupt_echo_run or arguments.get("runId"),
                    "status": "interrupt_requested"}
        raise AssertionError(f"unexpected tool {tool}")


def _live_adapter(transport, *, binding=None, state_store=None):
    port = _t3m.T3McpToolPort.from_access_token(
        transport, _session_token(), launch_arguments={"scratch": True}
    )
    adapter = T3ExecutionAdapter(
        port, lambda spec: binding or _binding(), FakeInspector(),
        clock=_clock, state_store=state_store,
    )
    return adapter, port


class T3LivePortReworkTests(unittest.IsolatedAsyncioTestCase):
    # --- #3: the live port attests the OAuth client session ----------------

    def test_port_attests_the_upstream_session_from_the_token_claims(self) -> None:
        port = _t3m.T3McpToolPort.from_access_token(FakeMcpTransport(), _session_token())
        self.assertEqual(port.authenticated_namespace(), f"client:{_SID}")
        for bad in (
            _session_token(sub="browser"), _session_token(kind="websocket"),
            _session_token(sid=""), "not-a-token", "a.b.c",
        ):
            with self.subTest(bad=bad[:16]):
                with self.assertRaises(_t3m.T3NamespaceAttestationError):
                    _t3m.T3McpToolPort.from_access_token(FakeMcpTransport(), bad)

    def test_expected_thread_id_matches_the_donor_json_stringify_derivation(self) -> None:
        # Vectors computed with node: "mcp:launch:" +
        # sha256(JSON.stringify([namespace, key])) (donor launchCommandId).
        self.assertEqual(
            _t3m.t3_expected_launch_thread_id(
                f"client:{_SID}",
                "7348fa34d653782d54e319fb602bcced1178ac0a3a7a9ed54065390405774d9b",
            ),
            "mcp:launch:a27cfb88f5b919561560799fb12a142a0929645101d128e23cd0b15e5e1c9314",
        )
        self.assertEqual(
            _t3m.t3_expected_launch_thread_id("client:é-ünïcode", 'k"ey\\x'),
            "mcp:launch:687d3153f67224acec9e4e8749f6aa648a04b67b289d465d6ed91a23ae09a646",
        )

    async def test_receipt_echoes_come_only_from_the_upstream_thread_id(self) -> None:
        transport = FakeMcpTransport()
        adapter, port = _live_adapter(transport)
        ref = await adapter.start(_launch_spec())
        receipt = adapter.launch_receipt("run-1")
        self.assertEqual(receipt.client_request_id, ref.launch_nonce)
        self.assertEqual(
            receipt.request_namespace, _t3m.t3_request_namespace(f"client:{_SID}")
        )
        self.assertEqual(receipt.created_at, "")  # never a local clock
        # An upstream thread id that does NOT prove (namespace, key) is an
        # UNKNOWN outcome (re-audit N5) — never an echo-free receipt.
        foreign = FakeMcpTransport()
        foreign.thread_override = "mcp:launch:" + "0" * 64
        other_port = _t3m.T3McpToolPort.from_access_token(foreign, _session_token())
        with self.assertRaises(T3UnknownOutcomeError):
            await other_port.launch_thread(adapter.launch_intent("run-1").envelope)

    async def test_port_refuses_an_envelope_for_another_namespace_before_sending(self) -> None:
        transport = FakeMcpTransport()
        adapter, port = _live_adapter(transport)
        envelope = adapter._launch_envelope(
            _launch_spec(), "k" * 64, _t3m.t3_request_namespace("client:someone-else")
        )
        with self.assertRaises(T3ExecutionAdapterError):
            await port.launch_thread(envelope)
        self.assertEqual(transport.calls, [])

    # --- #4: lost replies are unknown outcomes, never clean refusals --------

    async def test_lost_replies_keep_the_intent_and_clean_refusals_roll_back(self) -> None:
        err = _t3m.T3McpTransportError
        # Re-audit N1 supersedes audit #4's table: 429 and a codeless (or
        # non-allowlisted) tool isError are UNKNOWN, not clean refusals.
        unknown = {
            "timeout after send": err("timed out", phase="after_send"),
            "connection reset": err("reset by peer", phase="after_send"),
            "HTTP 502 after send": err("bad gateway", phase="after_send", http_status=502),
            "HTTP 408": err("request timeout", phase="after_send", http_status=408),
            "HTTP 429": err("rate limited", phase="after_send", http_status=429),
            "JSON-RPC internal error": err("internal", phase="after_send", rpc_code=-32603),
            "unclassified exception": OSError("socket closed mid-read"),
            "tool isError without code": err("x", phase="after_send", tool_error=True),
            "tool isError invalid_request": err(
                "x", phase="after_send", tool_error=True, tool_error_code="invalid_request"
            ),
        }
        clean = {
            "pre-send connection refused": err("refused", phase="pre_send"),
            "HTTP 400": err("bad request", phase="after_send", http_status=400),
            "HTTP 403": err("forbidden", phase="after_send", http_status=403),
            "JSON-RPC invalid params": err("invalid", phase="after_send", rpc_code=-32602),
            "tool isError capability_denied": err(
                "x", phase="after_send", tool_error=True, tool_error_code="capability_denied"
            ),
        }
        for label, failure in unknown.items():
            with self.subTest(unknown=label):
                transport = FakeMcpTransport()
                transport.failures["t3_thread_launch"] = failure
                adapter, _ = _live_adapter(transport)
                with self.assertRaises(T3LaunchEffectUnknownError):
                    await adapter.start(_launch_spec())
                self.assertIsNotNone(adapter.launch_intent("run-1"))
        for label, failure in clean.items():
            with self.subTest(clean=label):
                transport = FakeMcpTransport()
                transport.failures["t3_thread_launch"] = failure
                adapter, _ = _live_adapter(transport)
                with self.assertRaises(T3ExecutionAdapterError) as ctx:
                    await adapter.start(_launch_spec())
                self.assertNotIsInstance(ctx.exception, T3LaunchEffectUnknownError)
                self.assertIsNone(adapter.launch_intent("run-1"))

    async def test_unparsable_launch_reply_is_an_unknown_outcome(self) -> None:
        transport = FakeMcpTransport()
        adapter, port = _live_adapter(transport)
        port._call_tool = lambda tool, arguments: "<html>gateway</html>"
        with self.assertRaises(T3LaunchEffectUnknownError):
            await adapter.start(_launch_spec())
        self.assertIsNotNone(adapter.launch_intent("run-1"))

    # --- #7: exact-run interrupt carries threadId AND the native runId -------

    async def test_interrupt_payload_carries_thread_and_native_run_id(self) -> None:
        transport = FakeMcpTransport()
        adapter, _ = _live_adapter(transport)
        ref = await adapter.start(_launch_spec())
        native_run = adapter.launch_receipt("run-1").run_id
        await adapter.cancel(ref, "superseded")
        tool, arguments = transport.calls[-1]
        self.assertEqual(tool, "t3_thread_interrupt")
        self.assertEqual(arguments["threadId"], ref.provider_session_id)
        self.assertEqual(arguments["runId"], native_run)
        self.assertEqual(
            _t3m.t3_native_run_coordinates(ref), (ref.provider_session_id, native_run)
        )

    async def test_interrupt_echoing_another_run_is_an_unknown_outcome(self) -> None:
        transport = FakeMcpTransport()
        adapter, _ = _live_adapter(transport)
        ref = await adapter.start(_launch_spec())
        transport.interrupt_echo_run = "run-newest"
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.cancel(ref, "superseded")
        report = adapter.cancel_report("run-1")
        self.assertTrue(report.requested)
        self.assertFalse(report.settled)

    # --- #13: dedicated terminal read of the exact run's final reply --------

    async def test_collect_reads_the_exact_runs_final_assistant_item(self) -> None:
        transport = FakeMcpTransport()
        adapter, _ = _live_adapter(transport)
        ref = await adapter.start(_launch_spec())
        native_run = adapter.launch_receipt("run-1").run_id
        thread = ref.provider_session_id
        transport.items[thread] = [
            {"position": 1, "itemId": "i-1", "runId": native_run,
             "type": "user_message", "text": "do the work"},
            {"position": 2, "itemId": "i-2", "runId": native_run,
             "type": "assistant_message", "text": "FINAL-ANSWER"},
            {"position": 3, "itemId": "i-3", "runId": "run-appended-by-human",
             "type": "assistant_message", "text": "later chatter"},
        ]
        transport.run_status[native_run] = "completed"
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.SUCCEEDED)
        self.assertEqual(adapter.read_cursor("run-1"), "3")
        receipt = await adapter.collect_result(ref)
        entry = adapter.result_ledger_entry("run-1")
        self.assertEqual(entry.result_ref, f"t3://thread/{thread}/run/{native_run}/item/i-2")
        self.assertEqual(receipt.result.structured_output["text"], "FINAL-ANSWER")

    async def test_collect_refuses_when_the_exact_run_has_no_final_reply(self) -> None:
        transport = FakeMcpTransport()
        adapter, _ = _live_adapter(transport)
        ref = await adapter.start(_launch_spec())
        native_run = adapter.launch_receipt("run-1").run_id
        transport.run_status[native_run] = "completed"
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.collect_result(ref)
        self.assertIsNone(adapter.result_ledger_entry("run-1"))


# =============================================================================
# A4 re-audit (N1-N9) — donor-faithful MCP server model.  New names are
# resolved through the module INSIDE each test (fail-before per test).
# =============================================================================


def _donor_failure(code: str):
    """The donor's declared-failure wire body (effect McpServer, return mode)."""
    return _t3m.T3McpTransportError(
        f"tool returned failure: {code}", phase="after_send", tool_error=True,
        tool_error_code=code,
    )


class DonorMcpServer:
    """Shared upstream state; ``session(sid)`` is one OAuth client's transport.

    Models the donor at the pin: ``threadId = mcp:launch:sha256(JSON[ns,
    key])`` with ``ns = client:<sid>`` (a replay under the SAME session
    returns the original thread; another session mints another thread); the
    initial user message carries ``messageId == threadId``; reads page from
    the head (``limit`` items after ``afterPosition``; ``hasMore``;
    ``nextPosition``), list only the newest ``runLimit`` runs, and report
    ``thread.runCount``; ``t3_thread_wait`` looks a run up by id.
    """

    def __init__(self) -> None:
        self.threads: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict]] = []
        #: raised ONCE after the next launch COMMITTED (lost reply after commit)
        self.after_commit_failure: BaseException | None = None
        self.wait_echo_run: str | None = None

    def session(self, sid: str):
        namespace = f"client:{sid}"

        def call_tool(tool: str, arguments):
            self.calls.append((sid, tool, dict(arguments)))
            return self._handle(namespace, tool, dict(arguments))

        return call_tool

    def mints(self) -> int:
        return len(self.threads)

    def add_runs(self, thread_id: str, count: int, status: str = "completed") -> None:
        runs = self.threads[thread_id]["runs"]
        for _ in range(count):
            runs.append({"runId": f"later-{len(runs) + 1}", "ordinal": len(runs) + 1,
                         "status": status})

    def _thread(self, thread_id: str) -> dict:
        thread = self.threads.get(thread_id)
        if thread is None:
            raise _donor_failure("thread_not_found")
        return thread

    def _handle(self, namespace: str, tool: str, arguments: dict):
        if tool == "t3_thread_launch":
            thread_id = _t3m.t3_expected_launch_thread_id(
                namespace, arguments["clientRequestId"]
            )
            thread = self.threads.get(thread_id)
            if thread is None:
                run_id = f"run-{len(self.threads) + 1}"
                thread = {
                    "runs": [{"runId": run_id, "ordinal": 1, "status": "running"}],
                    "items": [{"position": 1, "itemId": f"{thread_id}:u1",
                               "runId": run_id, "messageId": thread_id,
                               "type": "user_message", "text": arguments["message"]}],
                }
                self.threads[thread_id] = thread
            reply = {"threadId": thread_id, "runId": thread["runs"][0]["runId"],
                     "projectId": "p-1", "status": thread["runs"][0]["status"],
                     "link": f"https://app.t3/{thread_id}"}
            if self.after_commit_failure is not None:
                failure, self.after_commit_failure = self.after_commit_failure, None
                raise failure
            return reply
        if tool == "t3_thread_read":
            thread_id = arguments["threadId"]
            thread = self._thread(thread_id)
            after = arguments.get("afterPosition", -1)
            limit = min(int(arguments.get("limit", 20)), 100)
            run_limit = min(int(arguments.get("runLimit", 10)), 50)
            rest = [i for i in thread["items"] if i["position"] > after]
            page = rest[:limit]
            runs = sorted(thread["runs"], key=lambda r: -r["ordinal"])[:run_limit]
            return {
                "thread": {"threadId": thread_id, "projectId": "p-1",
                           "runCount": len(thread["runs"]), "status": "idle",
                           "link": f"https://app.t3/{thread_id}"},
                "recentRuns": [dict(r) for r in runs],
                "items": [dict(i, sourceThreadId=thread_id, textTruncated=False)
                          for i in page],
                "nextPosition": page[-1]["position"] if page else None,
                "hasMore": len(rest) > len(page),
            }
        if tool == "t3_thread_wait":
            thread = self._thread(arguments["threadId"])
            run = next((r for r in thread["runs"] if r["runId"] == arguments["runId"]), None)
            if run is None:
                raise _donor_failure("run_not_found")
            return {"threadId": arguments["threadId"],
                    "runId": self.wait_echo_run or run["runId"],
                    "status": run["status"], "timedOut": run["status"] == "running"}
        if tool == "t3_thread_interrupt":
            self._thread(arguments["threadId"])
            return {"threadId": arguments["threadId"], "runId": arguments.get("runId"),
                    "status": "interrupt_requested"}
        raise AssertionError(f"unexpected tool {tool}")


_SID_B = "9c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f"


def _donor_adapter(server: DonorMcpServer, sid: str = _SID, *, state_store=None):
    port = _t3m.T3McpToolPort.from_access_token(
        server.session(sid), _session_token(sid), launch_arguments={"scratch": True}
    )
    adapter = T3ExecutionAdapter(
        port, lambda spec: _binding(), FakeInspector(),
        clock=_clock, state_store=state_store,
    )
    return adapter, port


def _pre_ack_ref(spec: WorkerLaunchSpec, key: str) -> WorkerProcessRef:
    from control_plane.t3_execution_adapter import _T3_REMOTE_BINARY_PLACEHOLDER

    return WorkerProcessRef(
        run_id=spec.run_id, pid=0, pgid=0, session_id=None,
        process_start_identity="", boot_session_id="",
        launch_nonce=key, provider_session_id=None,
        stdout_path="", stderr_path="", result_path="",
        started_at="", binary=_T3_REMOTE_BINARY_PLACEHOLDER, base_sha="",
    )


def _mutating_calls(server: DonorMcpServer) -> list:
    return [c for c in server.calls if c[1] in {"t3_thread_launch", "t3_thread_interrupt"}]


class A4ReauditN1ClassifierTests(unittest.TestCase):
    """N1: the lost-reply classifier is an explicit, total allowlist."""

    def test_n1_classifier_table(self) -> None:
        err = _t3m.T3McpTransportError
        classify = _t3m.t3_mcp_failure_is_definitive_refusal
        launch, interrupt = "t3_thread_launch", "t3_thread_interrupt"

        class Exploding(err):
            @property
            def http_status(self):  # noqa: D401 — attribute access raises
                raise RuntimeError("boom")

            @http_status.setter
            def http_status(self, value):
                pass

        table = [
            # (label, failure, tool, definitive refusal?)
            ("pre-send", err("x", phase="pre_send"), launch, True),
            ("after-send, nothing explicit", err("x", phase="after_send"), launch, False),
            ("HTTP 400", err("x", phase="after_send", http_status=400), launch, True),
            ("HTTP 401", err("x", phase="after_send", http_status=401), launch, True),
            ("HTTP 403", err("x", phase="after_send", http_status=403), launch, True),
            ("HTTP 405", err("x", phase="after_send", http_status=405), launch, True),
            ("HTTP 406", err("x", phase="after_send", http_status=406), launch, True),
            ("HTTP 415", err("x", phase="after_send", http_status=415), launch, True),
            ("HTTP 404 (post-handler swap)", err("x", phase="after_send", http_status=404), launch, False),
            ("HTTP 408", err("x", phase="after_send", http_status=408), launch, False),
            ("HTTP 409", err("x", phase="after_send", http_status=409), launch, False),
            ("HTTP 422", err("x", phase="after_send", http_status=422), launch, False),
            ("HTTP 429", err("x", phase="after_send", http_status=429), launch, False),
            ("HTTP 499", err("x", phase="after_send", http_status=499), launch, False),
            ("HTTP 500", err("x", phase="after_send", http_status=500), launch, False),
            ("HTTP 503", err("x", phase="after_send", http_status=503), launch, False),
            ("status as str", err("x", phase="after_send", http_status="400"), launch, False),
            ("status as bool", err("x", phase="after_send", http_status=True), launch, False),
            ("status as float", err("x", phase="after_send", http_status=400.0), launch, False),
            ("JSON-RPC -32602", err("x", phase="after_send", rpc_code=-32602), launch, True),
            ("JSON-RPC -32601", err("x", phase="after_send", rpc_code=-32601), launch, True),
            ("JSON-RPC -32603", err("x", phase="after_send", rpc_code=-32603), launch, False),
            ("JSON-RPC code as str", err("x", phase="after_send", rpc_code="-32602"), launch, False),
            ("isError no code", err("x", phase="after_send", tool_error=True), launch, False),
            ("isError orchestration_error (post-commit wrap)", _donor_failure("orchestration_error"), launch, False),
            ("isError invalid_request (post-create dispatch refusal)", _donor_failure("invalid_request"), launch, False),
            ("isError capability_denied", _donor_failure("capability_denied"), launch, True),
            ("isError parent_not_active", _donor_failure("parent_not_active"), launch, True),
            ("isError thread_not_found (calling thread)", _donor_failure("thread_not_found"), launch, True),
            ("isError target_required", _donor_failure("target_required"), launch, True),
            ("isError runtime escalation", _donor_failure("runtime_mode_escalation_denied"), launch, True),
            ("isError interaction escalation", _donor_failure("interaction_mode_escalation_denied"), launch, True),
            ("isError unknown future code", _donor_failure("quota_exceeded"), launch, False),
            ("isError allowlisted code, no tool named", _donor_failure("capability_denied"), None, False),
            ("isError allowlisted code, unknown tool", _donor_failure("capability_denied"), "t3_thread_send", False),
            ("interrupt thread_not_found", _donor_failure("thread_not_found"), interrupt, True),
            ("interrupt target_required", _donor_failure("target_required"), interrupt, False),
            ("interrupt orchestration_error", _donor_failure("orchestration_error"), interrupt, False),
            ("isError + allowlisted HTTP status", err("x", phase="after_send", tool_error=True,
                                                      http_status=400), launch, False),
            ("not a transport error", RuntimeError("x"), launch, False),
            ("None", None, launch, False),
            ("classification raises", Exploding("x", phase="after_send"), launch, False),
        ]
        for label, failure, tool, expected in table:
            with self.subTest(label):
                self.assertIs(classify(failure, tool=tool), expected)

    def test_n1_tool_error_code_parses_only_the_donor_declared_failure_shape(self) -> None:
        parse = _t3m.t3_mcp_tool_error_code
        declared = {"isError": True, "content": [{"type": "text", "text": _json.dumps(
            {"_tag": "OrchestratorMcpFailure", "code": "capability_denied",
             "message": "This credential cannot control threads."})}]}
        defect = {"isError": True, "content": [{"type": "text",
                  "text": "Tool execution failed due to an internal server error."}]}
        self.assertEqual(parse(declared), "capability_denied")
        for label, value in {
            "defect text": defect,
            "other tag": {"content": [{"type": "text", "text": _json.dumps(
                {"_tag": "Other", "code": "capability_denied"})}]},
            "code not a string": {"content": [{"type": "text", "text": _json.dumps(
                {"_tag": "OrchestratorMcpFailure", "code": 7})}]},
            "no content": {"isError": True},
            "content not a list": {"content": 3},
            "not a mapping": "isError",
            "None": None,
        }.items():
            with self.subTest(label):
                self.assertIsNone(parse(value))


class ReCheckR1LivePortNoRowTests(unittest.IsolatedAsyncioTestCase):
    """Re-audit #3 R1 through the REAL T3McpToolPort (re-check M1): a
    pre-durability recovery (store has NO row for the run) under another
    OAuth client makes ZERO mutating calls and is refused typed; under the
    original client it adopts the ORIGINAL thread by a read (no replay)."""

    async def _launched_under_a(self):
        server = DonorMcpServer()
        adapter_a, _ = _donor_adapter(server, state_store=InMemoryT3AdapterStateStore())
        spec = _launch_spec(run_dir=_recovery_run_dir())
        ref = await adapter_a.start(spec)
        self.assertEqual(server.mints(), 1)
        return server, spec, ref, _recovery_binding(spec, ref)

    async def test_other_oauth_client_is_refused_with_zero_mutating_calls(self) -> None:
        server, spec, ref, binding = await self._launched_under_a()
        before = len(_mutating_calls(server))
        other, _ = _donor_adapter(server, _SID_B, state_store=InMemoryT3AdapterStateStore())
        with self.assertRaises(_t3m.T3NamespaceAttestationError) as ctx:
            await other.reattach(spec, binding)
        self.assertEqual(ctx.exception.reason, "PRINCIPAL_MISMATCH")
        self.assertEqual(len(_mutating_calls(server)), before)  # nothing sent
        self.assertEqual([c[0] for c in server.calls].count(_SID_B), 0)
        self.assertEqual(server.mints(), 1)

    async def test_original_client_adopts_by_read_without_a_replay(self) -> None:
        server, spec, ref, binding = await self._launched_under_a()
        before = len(_mutating_calls(server))
        again, _ = _donor_adapter(server, state_store=InMemoryT3AdapterStateStore())
        adopted = await again.reattach(spec, binding)
        self.assertEqual(adopted.provider_session_id, ref.provider_session_id)
        self.assertEqual(adopted, ref)
        self.assertEqual(len(_mutating_calls(server)), before)  # READ, not replay
        self.assertEqual(server.mints(), 1)
        # Durable: the adopted receipt is persisted; a second reattach is free.
        self.assertIsNotNone(again.launch_receipt(spec.run_id))
        self.assertEqual(await again.reattach(spec, binding), ref)
        self.assertEqual(len(_mutating_calls(server)), before)


class A4ReauditLivePortTests(unittest.IsolatedAsyncioTestCase):
    async def test_n1_is_error_after_commit_keeps_intent_and_replay_adopts_original(self) -> None:
        """Reviewer's double-launch: a post-commit isError must stay UNKNOWN."""
        server = DonorMcpServer()
        store = InMemoryT3AdapterStateStore()
        server.after_commit_failure = _donor_failure("orchestration_error")
        adapter, port = _donor_adapter(server, state_store=store)
        spec = _launch_spec(run_dir=_recovery_run_dir())
        with self.assertRaises(T3LaunchEffectUnknownError):
            await adapter.start(spec)
        self.assertEqual(server.mints(), 1)  # the launch DID commit upstream
        intent = adapter.launch_intent("run-1")
        self.assertIsNotNone(intent)  # kept: never rolled back
        # A retry from ANOTHER OAuth client can never relaunch the run: the
        # claim is held, so no second thread is minted (pre-fix: intent was
        # cleared and this minted thread #2).
        other, _ = _donor_adapter(server, _SID_B, state_store=store)
        with self.assertRaises(T3ExecutionAdapterError):
            await other.start(spec)
        self.assertEqual(server.mints(), 1)
        # Recovery under the ORIGINAL session replays and adopts the ORIGINAL.
        ref = await adapter.reattach(
            spec, _recovery_binding(spec, _pre_ack_ref(spec, intent.client_request_id))
        )
        self.assertEqual(
            ref.provider_session_id,
            _t3m.t3_expected_launch_thread_id(f"client:{_SID}", intent.client_request_id),
        )
        self.assertEqual(server.mints(), 1)
        self.assertEqual([c[0] for c in _mutating_calls(server)].count(_SID_B), 0)

    async def test_n1_mcp_isError_with_an_allowlisted_code_is_a_clean_refusal(self) -> None:
        server = DonorMcpServer()
        adapter, port = _donor_adapter(server)
        port._call_tool = lambda tool, arguments: (_ for _ in ()).throw(
            _donor_failure("capability_denied")
        )
        with self.assertRaises(T3ExecutionAdapterError) as ctx:
            await adapter.start(_launch_spec())
        self.assertNotIsInstance(ctx.exception, T3LaunchEffectUnknownError)
        self.assertIsNone(adapter.launch_intent("run-1"))

    async def test_n5_unproven_thread_id_is_unknown_and_never_acked(self) -> None:
        server = DonorMcpServer()
        adapter, port = _donor_adapter(server)
        inner = port._call_tool

        def foreign_thread(tool, arguments):
            reply = dict(inner(tool, arguments))
            if tool == "t3_thread_launch":
                reply["threadId"] = "mcp:launch:" + "0" * 64
            return reply

        port._call_tool = foreign_thread
        with self.assertRaises(T3LaunchEffectUnknownError):
            await adapter.start(_launch_spec())
        self.assertIsNotNone(adapter.launch_intent("run-1"))  # intent kept
        self.assertIsNone(adapter.launch_receipt("run-1"))  # never ACKed

    async def test_n5_adapter_never_acks_an_echo_free_receipt(self) -> None:
        class EchoFreeLaunchPort(FakeT3Port):
            async def launch_thread(self, envelope):
                receipt = await super().launch_thread(envelope)
                return dataclasses.replace(receipt, client_request_id="", request_namespace="")

        adapter, port, _ = _t3_adapter(EchoFreeLaunchPort(), binding=_binding())
        with self.assertRaises(T3LaunchEffectUnknownError):
            await adapter.start(_launch_spec())
        self.assertIsNotNone(adapter.launch_intent("run-1"))
        self.assertIsNone(adapter.launch_receipt("run-1"))

    async def _terminal_run_with_timeline(self, total_items: int):
        server = DonorMcpServer()
        adapter, port = _donor_adapter(server)
        ref = await adapter.start(_launch_spec())
        receipt = adapter.launch_receipt("run-1")
        thread = server.threads[receipt.thread_id]
        thread["runs"][0]["status"] = "completed"
        for position in range(2, total_items + 1):
            thread["items"].append({
                "position": position, "itemId": f"i-{position}",
                "runId": receipt.run_id, "messageId": None,
                "type": "assistant_message", "text": f"step {position}",
            })
        return server, adapter, port, ref, receipt

    async def test_n2_terminal_read_refuses_when_pages_run_out_with_has_more(self) -> None:
        server, adapter, port, ref, receipt = await self._terminal_run_with_timeline(1200)
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.collect_result(ref)
        # Never ledgered an intermediate assistant item (e.g. "step 1000").
        self.assertIsNone(adapter.result_ledger_entry("run-1"))
        direct = await port.read_result(receipt.thread_id, receipt.run_id)
        self.assertEqual(direct.result_ref, "")
        self.assertEqual(dict(direct.result_payload), {})

    async def test_n2_terminal_read_names_the_final_item_of_a_complete_timeline(self) -> None:
        server, adapter, port, ref, receipt = await self._terminal_run_with_timeline(900)
        await adapter.collect_result(ref)
        self.assertEqual(
            adapter.result_ledger_entry("run-1").result_ref,
            f"t3://thread/{receipt.thread_id}/run/{receipt.run_id}/item/i-900",
        )

    async def test_n2_stalled_paging_with_has_more_refuses(self) -> None:
        server, adapter, port, ref, receipt = await self._terminal_run_with_timeline(60)
        inner = port._call_tool

        def stalled(tool, arguments):
            reply = dict(inner(tool, arguments))
            if tool == "t3_thread_read":
                reply["hasMore"] = True
                reply["nextPosition"] = arguments.get("afterPosition") or 0
            return reply

        port._call_tool = stalled
        with self.assertRaises(_t3m.T3PortRefusalError):
            await port.read_result(receipt.thread_id, receipt.run_id)

    async def test_n9_run_beyond_recent_runs_is_looked_up_exactly(self) -> None:
        server = DonorMcpServer()
        adapter, port = _donor_adapter(server)
        ref = await adapter.start(_launch_spec())
        receipt = adapter.launch_receipt("run-1")
        server.threads[receipt.thread_id]["runs"][0]["status"] = "completed"
        server.add_runs(receipt.thread_id, 60, status="running")  # 61 runs > 50 listed
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.SUCCEEDED)
        lookups = [c for c in server.calls if c[1] == "t3_thread_wait"]
        self.assertEqual(len(lookups), 1)
        self.assertEqual(lookups[0][2]["runId"], receipt.run_id)
        self.assertEqual(lookups[0][2]["timeoutMs"], 1)

    async def test_n9_exact_lookup_never_guesses(self) -> None:
        server = DonorMcpServer()
        adapter, port = _donor_adapter(server)
        ref = await adapter.start(_launch_spec())
        receipt = adapter.launch_receipt("run-1")
        server.threads[receipt.thread_id]["runs"][0]["status"] = "completed"
        server.add_runs(receipt.thread_id, 60)
        server.wait_echo_run = "later-61"  # upstream followed a continuation
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.RUNNING)
        server.wait_echo_run = None
        server.threads[receipt.thread_id]["runs"].pop(0)  # run no longer listed at all
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.RUNNING)

    async def test_n9_listed_run_needs_no_lookup(self) -> None:
        server = DonorMcpServer()
        adapter, port = _donor_adapter(server)
        ref = await adapter.start(_launch_spec())
        receipt = adapter.launch_receipt("run-1")
        server.threads[receipt.thread_id]["runs"][0]["status"] = "completed"
        server.add_runs(receipt.thread_id, 30)  # 31 runs <= 50: listed
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.SUCCEEDED)
        self.assertFalse([c for c in server.calls if c[1] == "t3_thread_wait"])


class A4DryRunStatusVocabularyTests(unittest.IsolatedAsyncioTestCase):
    """D1 (found by the A4 canary dry run): the donor's terminal run statuses."""

    def test_d1_every_donor_run_status_maps_honestly(self) -> None:
        mapping = {
            "preparing": WorkerRunStatus.STARTING, "queued": WorkerRunStatus.STARTING,
            "starting": WorkerRunStatus.STARTING, "running": WorkerRunStatus.RUNNING,
            "waiting": WorkerRunStatus.RUNNING, "completed": WorkerRunStatus.SUCCEEDED,
            "interrupted": WorkerRunStatus.CANCELLED, "failed": WorkerRunStatus.FAILED,
            "cancelled": WorkerRunStatus.CANCELLED, "rolled_back": WorkerRunStatus.CANCELLED,
        }
        for native, expected in mapping.items():
            with self.subTest(native):
                self.assertEqual(_t3m._map_t3_status(native), expected)

    async def test_d1_an_interrupted_run_settles_the_requested_cancel(self) -> None:
        server = DonorMcpServer()
        adapter, port = _donor_adapter(server)
        ref = await adapter.start(_launch_spec())
        receipt = adapter.launch_receipt("run-1")
        await adapter.cancel(ref, "stop")
        self.assertFalse(adapter.cancel_report("run-1").settled)
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.CANCELLING)
        server.threads[receipt.thread_id]["runs"][0]["status"] = "interrupted"
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.CANCELLED)
        report = adapter.cancel_report("run-1")
        self.assertTrue(report.settled)
        self.assertEqual(report.settled_state, "CANCELLED")


class A4ReauditAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_n4_undecodable_specs_are_refused_before_any_claim(self) -> None:
        cases = {
            "isolation_roots list item": dict(isolation_roots=(["x"],)),
            "result_schema_path int": dict(result_schema_path=123),
        }
        for label, override in cases.items():
            with self.subTest(label):
                adapter, port, _ = _t3_adapter(binding=_binding())
                spec = dataclasses.replace(_launch_spec(), **override)
                with self.assertRaises(_t3m.T3LaunchSpecNotDurableError) as ctx:
                    await adapter.start(spec)
                self.assertEqual(ctx.exception.code, "T3_SPEC_NOT_DURABLE")
                self.assertIsNone(adapter.launch_intent("run-1"))
                self.assertEqual(port.launch_calls, [])

    async def test_n4_round_trip_drift_is_refused(self) -> None:
        """A value whose JSON round trip changes the spec sha is not durable."""
        adapter, port, _ = _t3_adapter(binding=_binding())
        # A str given for a Path field reloads as Path("…/x"): "./" is
        # normalized away, so the reloaded spec hashes differently.
        spec = dataclasses.replace(_launch_spec(), workspace_path="/tmp/mmos-t3-ws/./x")
        with self.assertRaises(_t3m.T3LaunchSpecNotDurableError):
            await adapter.start(spec)
        self.assertIsNone(adapter.launch_intent("run-1"))
        self.assertEqual(port.launch_calls, [])

    async def test_n4_sqlite_store_never_persists_an_undecodable_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = _t3m.SQLiteT3AdapterStateStore(Path(tmp) / "state.sqlite3")
            adapter, port, _ = _t3_adapter(binding=_binding(), state_store=store)
            spec = dataclasses.replace(_launch_spec(), result_schema_path=123)
            with self.assertRaises(_t3m.T3LaunchSpecNotDurableError):
                await adapter.start(spec)
            self.assertEqual(store.run_ids(), ())
            store.close()

    async def test_n7_status_cancel_collect_check_namespace_continuity(self) -> None:
        store = InMemoryT3AdapterStateStore()
        owner, owner_port, _ = _t3_adapter(
            FakeT3Port(principal="client:A"), binding=_binding(), state_store=store
        )
        ref = await owner.start(_launch_spec())
        for label, principal, reason in (
            ("different principal", "client:B", "PRINCIPAL_MISMATCH"),
            ("unattested port", None, "UNATTESTED"),
        ):
            with self.subTest(label):
                port = FakeT3Port(principal=principal)
                other, _, _ = _t3_adapter(port, binding=_binding(), state_store=store)
                for operation in (
                    lambda: other.status(ref),
                    lambda: other.collect_result(ref),
                    lambda: other.cancel(ref, "stop"),
                ):
                    with self.assertRaises(_t3m.T3NamespaceAttestationError) as ctx:
                        await operation()
                    self.assertEqual(ctx.exception.reason, reason)
                self.assertEqual(port.trace, [])  # zero native calls
                self.assertIsNone(owner.cancel_report("run-1"))
        # The original principal still operates normally.
        self.assertEqual(await owner.status(ref), WorkerRunStatus.RUNNING)

    async def test_n6_any_session_adopts_a_stranded_launch_by_deterministic_read(self) -> None:
        server = DonorMcpServer()
        store = InMemoryT3AdapterStateStore()
        server.after_commit_failure = _donor_failure("orchestration_error")
        owner, _ = _donor_adapter(server, state_store=store)
        spec = _launch_spec(run_dir=_recovery_run_dir())
        with self.assertRaises(T3LaunchEffectUnknownError):
            await owner.start(spec)
        intent = owner.launch_intent("run-1")
        binding = _recovery_binding(spec, _pre_ack_ref(spec, intent.client_request_id))
        other, other_port = _donor_adapter(server, _SID_B, state_store=store)
        # Replay under another principal stays refused — unchanged by N6.
        calls_before = len(server.calls)
        with self.assertRaises(_t3m.T3NamespaceAttestationError) as ctx:
            await other.reattach(spec, binding)
        self.assertEqual(ctx.exception.reason, "PRINCIPAL_MISMATCH")
        self.assertEqual(len(server.calls), calls_before)  # zero native calls
        # Read-only adoption by the deterministic id works under ANY session.
        ref = await other.adopt_stranded_launch(spec, binding)
        expected = _t3m.t3_expected_launch_thread_id(f"client:{_SID}", intent.client_request_id)
        self.assertEqual(ref.provider_session_id, expected)
        self.assertEqual(server.mints(), 1)
        b_tools = [c[1] for c in server.calls[calls_before:]]
        self.assertEqual(b_tools, ["t3_thread_read"])  # NO launch/replay
        receipt = owner.launch_receipt("run-1")
        self.assertEqual(receipt.request_namespace, intent.request_namespace)
        self.assertEqual(receipt.client_request_id, intent.client_request_id)
        # The original principal reattaches the adopted ref with zero calls.
        calls_before = len(server.calls)
        self.assertEqual(await owner.reattach(spec, _recovery_binding(spec, ref)), ref)
        self.assertEqual(len(server.calls), calls_before)
        # ...and the adopter still cannot operate the run (N7).
        with self.assertRaises(_t3m.T3NamespaceAttestationError):
            await other.status(ref)

    async def test_n6_absence_proves_nothing_and_keeps_the_intent(self) -> None:
        server = DonorMcpServer()
        store = InMemoryT3AdapterStateStore()
        owner, owner_port = _donor_adapter(server, state_store=store)
        owner_port._call_tool = lambda tool, arguments: (_ for _ in ()).throw(
            _t3m.T3McpTransportError("reset", phase="after_send")
        )
        spec = _launch_spec(run_dir=_recovery_run_dir())
        with self.assertRaises(T3LaunchEffectUnknownError):
            await owner.start(spec)  # never reached upstream in this model
        intent = owner.launch_intent("run-1")
        binding = _recovery_binding(spec, _pre_ack_ref(spec, intent.client_request_id))
        other, _ = _donor_adapter(server, _SID_B, state_store=store)
        with self.assertRaises(T3LaunchEffectUnknownError):
            await other.adopt_stranded_launch(spec, binding)
        self.assertIsNotNone(owner.launch_intent("run-1"))
        self.assertIsNone(owner.launch_receipt("run-1"))
        self.assertEqual(_mutating_calls(server), [])

    async def test_n6_ports_without_the_read_seam_are_refused(self) -> None:
        store = InMemoryT3AdapterStateStore()
        owner, port, _ = _t3_adapter(
            FakeT3Port(principal="client:A"), binding=_binding(), state_store=store
        )
        port.unknown_outcome_on_launch = True
        spec = _launch_spec(run_dir=_recovery_run_dir())
        with self.assertRaises(T3LaunchEffectUnknownError):
            await owner.start(spec)
        intent = owner.launch_intent("run-1")
        binding = _recovery_binding(spec, _pre_ack_ref(spec, intent.client_request_id))
        with self.assertRaises(T3ExecutionAdapterError):
            await owner.adopt_stranded_launch(spec, binding)
        self.assertEqual(port.replay_calls, [])


def _import_live_proof_harness(name: str):
    """Import one A2/A3 live-proof harness module from its directory."""
    import importlib
    import sys

    harness_dir = str(
        Path(__file__).resolve().parent.parent / "integrations" / "t3" / "live_proof"
    )
    added = harness_dir not in sys.path
    if added:
        sys.path.insert(0, harness_dir)
    try:
        return importlib.import_module(name)
    finally:
        if added:
            sys.path.remove(harness_dir)


class T3LiveProofHarnessTests(unittest.IsolatedAsyncioTestCase):
    """The harness edits forced by the A3 API change (no live call made)."""

    def test_live_proof_port_is_the_reference_port_with_typed_transport(self) -> None:
        import socket
        import urllib.error
        from unittest import mock

        harness = _import_live_proof_harness("t3_live_proof")
        self.assertTrue(issubclass(harness.LiveT3McpPort, _t3m.T3McpToolPort))
        self.assertEqual(
            Path(harness.REPO).resolve(), Path(__file__).resolve().parent.parent
        )
        mcp = harness.McpHttp("unused-token")
        port = harness.LiveT3McpPort(mcp, _session_token())
        self.assertEqual(port.authenticated_namespace(), f"client:{_SID}")
        cases = [
            (urllib.error.URLError(ConnectionRefusedError()), "pre_send", None),
            (urllib.error.URLError(socket.gaierror()), "pre_send", None),
            (urllib.error.URLError(TimeoutError()), "after_send", None),
            (TimeoutError("read timed out"), "after_send", None),
            (ConnectionResetError("reset"), "after_send", None),
        ]
        for raised, phase, status in cases:
            with self.subTest(raised=type(raised).__name__):
                with mock.patch.object(harness.urllib.request, "urlopen", side_effect=raised):
                    with self.assertRaises(_t3m.T3McpTransportError) as ctx:
                        mcp.call_tool("t3_thread_launch", {})
                self.assertEqual(ctx.exception.phase, phase)
                self.assertEqual(ctx.exception.http_status, status)

    async def test_canary_crash_hook_store_forwards_the_launch_claim(self) -> None:
        canary = _import_live_proof_harness("t3_durable_canary")
        import os
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("T3_CANARY_CRASH_MODE", None)
            store = canary.CrashHookStore(
                _t3m.SQLiteT3AdapterStateStore(Path(tmp) / "state.sqlite3"),
                Path(tmp) / "side.json", [],
            )
            adapter = T3ExecutionAdapter(
                FakeT3Port(), lambda spec: _binding(), FakeInspector(),
                clock=_clock, state_store=store,
            )
            ref = await adapter.start(_launch_spec())
            self.assertEqual(adapter.retained_original_ref("run-1"), ref)


class _FakeHttpReply:
    def __init__(self, payload: dict) -> None:
        self._raw = _json.dumps(payload).encode()
        self.headers = {"Content-Type": "application/json"}
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def read(self) -> bytes:
        return self._raw


class A4HarnessTests(unittest.IsolatedAsyncioTestCase):
    """The A4 harness edits (no live call made)."""

    def test_mcp_http_carries_the_donor_failure_code(self) -> None:
        from unittest import mock

        harness = _import_live_proof_harness("t3_live_proof")
        mcp = harness.McpHttp("unused-token")
        declared = {"jsonrpc": "2.0", "id": 1, "result": {"isError": True, "content": [
            {"type": "text", "text": _json.dumps({"_tag": "OrchestratorMcpFailure",
                                                 "code": "orchestration_error",
                                                 "message": "The operation could not be completed."})}]}}
        defect = {"jsonrpc": "2.0", "id": 1, "result": {"isError": True, "content": [
            {"type": "text", "text": "Tool execution failed due to an internal server error."}]}}
        for payload, code in ((declared, "orchestration_error"), (defect, None)):
            with self.subTest(code=code):
                with mock.patch.object(
                    harness.urllib.request, "urlopen", return_value=_FakeHttpReply(payload)
                ):
                    with self.assertRaises(_t3m.T3McpTransportError) as ctx:
                        mcp.call_tool("t3_thread_launch", {})
                self.assertTrue(ctx.exception.tool_error)
                self.assertEqual(ctx.exception.tool_error_code, code)
                self.assertFalse(
                    _t3m.t3_mcp_failure_is_definitive_refusal(
                        ctx.exception, tool="t3_thread_launch"
                    )
                )

    def test_canary_r2_is_built_on_the_reference_port(self) -> None:
        canary = _import_live_proof_harness("t3_durable_canary")
        harness = _import_live_proof_harness("t3_live_proof")
        self.assertTrue(issubclass(canary.CanaryToolPort, _t3m.T3McpToolPort))
        self.assertFalse(hasattr(canary, "CanaryLivePort"))
        self.assertIs(canary.McpHttp, harness.McpHttp)
        import os

        if "T3_CANARY_RECEIPT_OUT" not in os.environ:
            # r2 writes its OWN receipt; r1's is immutable evidence.
            self.assertEqual(canary.RECEIPT_OUT.name, "t3_durable_canary_receipt_r2.json")
        self.assertEqual(canary.THREAD_BUDGET, 5)
        port = canary.CanaryToolPort(DonorMcpServer().session(_SID), _session_token(), events=[])
        self.assertEqual(port.authenticated_namespace(), f"client:{_SID}")

    async def test_canary_s5_injection_keeps_the_intent_and_replay_adopts(self) -> None:
        canary = _import_live_proof_harness("t3_durable_canary")
        server = DonorMcpServer()
        store = InMemoryT3AdapterStateStore()
        events: list = []
        lost = canary.LostReplyTransport(server.session(_SID), events)
        port = canary.CanaryToolPort(lost, _session_token(), events=events)
        adapter = T3ExecutionAdapter(port, lambda s: _binding(), FakeInspector(),
                                     clock=_clock, state_store=store)
        spec = _launch_spec(run_dir=_recovery_run_dir())
        with self.assertRaises(T3LaunchEffectUnknownError):
            await adapter.start(spec)
        self.assertEqual(server.mints(), 1)
        intent = adapter.launch_intent("run-1")
        self.assertIsNotNone(intent)
        recover_port = canary.CanaryToolPort(server.session(_SID), _session_token(), events=[])
        recover = T3ExecutionAdapter(recover_port, lambda s: _binding(), FakeInspector(),
                                     clock=_clock, state_store=store)
        ref = await recover.reattach(
            spec, _recovery_binding(spec, _pre_ack_ref(spec, intent.client_request_id))
        )
        self.assertEqual(ref.provider_session_id, lost.observed_reply["thread_id"])
        self.assertEqual(recover_port.counts()["replay"], 1)
        self.assertEqual(recover_port.counts()["launch"], 0)
        self.assertEqual(server.mints(), 1)


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
