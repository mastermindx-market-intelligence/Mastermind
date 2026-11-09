"""Rev 5 P0 — T3ExecutionAdapter cold-restart durability (A2 proof pack).

Pins, against the SQLite state store, exactly the failure-matrix rows the
handoff names (T3_HANDOFF_V2 §2 P0 / §6):

1. coordinator restart AFTER a successful start: a second adapter on the
   same store reattaches the SAME thread — native launch count still 1, no
   second bind, no native call at all;
2. crash BETWEEN intent-persist and ACK (the port minted the native thread
   then lost the reply): a second adapter replays the SAME key + namespace
   through ``replay_launch`` — never ``launch_thread``;
3. a DIFFERENT authenticated namespace (another OAuth client) is refused —
   two clients are never the same idempotency identity (live finding 1);
4. the status cursor and the requested-versus-settled cancel ledger survive
   the restart;
5. a replay returning a different thread than the known original is
   refused, and a receipt echoing a foreign key is refused.
"""
from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from control_plane.t3_execution_adapter import (
    SQLiteT3AdapterStateStore,
    T3ExecutionAdapter,
    T3ExecutionAdapterError,
    T3InterruptOutcome,
    T3LaunchEffectUnknownError,
    T3LaunchIntent,
    T3UnknownOutcomeError,
    T3ThreadLaunchReceipt,
    T3ThreadReadResult,
    default_t3_adapter_state_path,
    executive_runtime_db_path,
    derive_t3_client_request_id,
    t3_request_namespace,
)
from control_plane.worker_execution_contract import (
    WorkerProcessRef,
    WorkerRunStatus,
)
from tests.test_t3_execution_adapter import (
    FakeInspector,
    _binding,
    _clock,
    _launch_spec,
    _recovery_binding,
    _recovery_run_dir,
)

_PRINCIPAL_A = "oauth-client-A"
_PRINCIPAL_B = "oauth-client-B"

_TERMINAL_NATIVE = {
    "succeeded", "completed", "failed", "cancelled", "canceled",
    "timed_out", "timeout",
}


class CountingT3Port:
    """Fake native port that COUNTS launches and reports its principal.

    Models the upstream idempotency surface honestly: one (principal,
    namespace, key) maps to exactly one thread forever; ``lose_ack`` mints
    the native thread and then loses the reply (the effect-unknown zone).
    """

    def __init__(self, principal: str = "") -> None:
        self.principal = principal
        self.launch_count = 0
        self.replay_count = 0
        self.reads: list[tuple[str, str, str]] = []
        self.receipts_by_key: dict[str, T3ThreadLaunchReceipt] = {}
        self.status_by_thread: dict[str, str] = {}
        self.lose_ack = False
        self.replay_thread_override: tuple[str, str] | None = None
        self.replay_echo_mismatch = False

    def authenticated_namespace(self) -> str:
        return self.principal

    async def launch_thread(self, envelope) -> T3ThreadLaunchReceipt:
        self.launch_count += 1
        key = envelope.client_request_id
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
        if self.lose_ack:
            # The native thread now EXISTS upstream; the reply was lost.
            raise T3UnknownOutcomeError(
                "native launch outcome unknown (reply lost after creation)"
            )
        return receipt

    async def replay_launch(self, envelope) -> T3ThreadLaunchReceipt:
        self.replay_count += 1
        key = envelope.client_request_id
        receipt = self.receipts_by_key.get(key)
        if receipt is None:
            raise T3UnknownOutcomeError(
                f"no native command known for clientRequestId {key!r}"
            )
        if self.replay_thread_override is not None:
            thread_id, run_id = self.replay_thread_override
            return dataclasses.replace(receipt, thread_id=thread_id, run_id=run_id)
        if self.replay_echo_mismatch:
            return dataclasses.replace(receipt, client_request_id="f" * 64)
        return receipt

    async def read_thread(self, thread_id: str, run_id: str, cursor: str):
        self.reads.append((thread_id, run_id, cursor))
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
        return T3InterruptOutcome(
            requested=True, settled=False, already_exited=False,
            observed_native_status="running",
        )


def _store(tmpdir: Path, name: str) -> SQLiteT3AdapterStateStore:
    return SQLiteT3AdapterStateStore(tmpdir / name)


def _adapter(store, port) -> T3ExecutionAdapter:
    """A fresh adapter instance over the given (possibly pre-loaded) store."""
    return T3ExecutionAdapter(
        port, lambda spec: _binding(), FakeInspector(),
        clock=_clock, state_store=store,
    )


class ColdRestartDurabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mmos-t3-durability-")
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # (1) restart AFTER a successful start ---------------------------------

    async def test_restart_reattaches_same_thread_with_launch_count_one(
        self,
    ) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        path = self.tmpdir / "t3_adapter_state.sqlite3"
        port1 = CountingT3Port(principal=_PRINCIPAL_A)
        adapter1 = _adapter(_store(self.tmpdir, "t3_adapter_state.sqlite3"), port1)
        ref = await adapter1.start(spec)
        thread_id = ref.provider_session_id
        self.assertEqual(port1.launch_count, 1)

        # Simulated NEW PROCESS: a second store instance on the same file and
        # a second port for the SAME authenticated principal.
        port2 = CountingT3Port(principal=_PRINCIPAL_A)
        adapter2 = _adapter(SQLiteT3AdapterStateStore(path), port2)
        binding = _recovery_binding(spec, ref)
        reattached = await adapter2.reattach(spec, binding)

        self.assertEqual(reattached, ref)  # exact durable round-trip
        self.assertEqual(reattached.provider_session_id, thread_id)
        # Recovery of a retained execution needs NO native call at all.
        self.assertEqual(port2.launch_count, 0)
        self.assertEqual(port2.replay_count, 0)
        self.assertEqual(port2.reads, [])
        # And no second bind: start is dead for this run in the new process.
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter2.start(spec)
        self.assertEqual(port2.launch_count, 0)

    # (2) crash BETWEEN intent-persist and ACK ------------------------------

    async def test_crash_before_ack_replays_same_key_and_namespace(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        port1 = CountingT3Port(principal=_PRINCIPAL_A)
        port1.lose_ack = True
        adapter1 = _adapter(_store(self.tmpdir, "t3_adapter_state.sqlite3"), port1)
        with self.assertRaises(T3LaunchEffectUnknownError):
            await adapter1.start(spec)
        self.assertEqual(port1.launch_count, 1)
        # The native thread EXISTS (the port minted it before losing the ACK).
        key = derive_t3_client_request_id(_binding())
        self.assertIn(key, port1.receipts_by_key)

        # The supervisor's recovery binding predates any known thread: the
        # launch_nonce carries the deterministic key, the thread is unknown.
        pre_ack_ref = WorkerProcessRef(
            run_id=spec.run_id, pid=0, pgid=0,
            process_start_identity="", boot_session_id="",
            launch_nonce=key, provider_session_id=None,
            stdout_path="", stderr_path="", result_path="",
            started_at="", binary=ref_binary(), base_sha="",
        )
        binding = _recovery_binding(spec, pre_ack_ref)

        port2 = CountingT3Port(principal=_PRINCIPAL_A)
        port2.receipts_by_key.update(port1.receipts_by_key)  # same native owner
        adapter2 = _adapter(_store(self.tmpdir, "t3_adapter_state.sqlite3"), port2)
        reattached = await adapter2.reattach(spec, binding)

        # NEVER a fresh launch: recovery went through replay_launch only.
        self.assertEqual(port2.launch_count, 0)
        self.assertEqual(port2.replay_count, 1)
        # The replay used the SAME key + namespace as the persisted intent.
        intent = adapter2.launch_intent(spec.run_id)
        self.assertIsNotNone(intent)
        self.assertEqual(port2.replay_count, 1)
        self.assertEqual(reattached.launch_nonce, key)
        self.assertEqual(
            reattached.provider_session_id, port1.receipts_by_key[key].thread_id
        )
        self.assertEqual(
            intent.request_namespace, t3_request_namespace(_PRINCIPAL_A)
        )
        # The adopted execution is now durable: a third process reattaches
        # with no native call at all.
        port3 = CountingT3Port(principal=_PRINCIPAL_A)
        adapter3 = _adapter(_store(self.tmpdir, "t3_adapter_state.sqlite3"), port3)
        again = await adapter3.reattach(spec, _recovery_binding(spec, reattached))
        self.assertEqual(again, reattached)
        self.assertEqual(port3.launch_count, 0)
        self.assertEqual(port3.replay_count, 0)

    # (3) different authenticated namespace ---------------------------------

    async def test_restart_under_a_different_namespace_is_refused(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        port1 = CountingT3Port(principal=_PRINCIPAL_A)
        adapter1 = _adapter(_store(self.tmpdir, "t3_adapter_state.sqlite3"), port1)
        ref = await adapter1.start(spec)
        binding = _recovery_binding(spec, ref)

        # A DIFFERENT OAuth client recovers: refused — two clients are never
        # the same idempotency identity.
        port2 = CountingT3Port(principal=_PRINCIPAL_B)
        port2.receipts_by_key.update(port1.receipts_by_key)
        adapter2 = _adapter(_store(self.tmpdir, "t3_adapter_state.sqlite3"), port2)
        with self.assertRaises(T3ExecutionAdapterError) as ctx:
            await adapter2.reattach(spec, binding)
        self.assertIn("authenticated namespace", str(ctx.exception))
        self.assertEqual(port2.replay_count, 0)
        self.assertEqual(port2.launch_count, 0)

    # (4) cursor + cancel ledger survive the restart -------------------------

    async def test_cursor_and_cancel_ledger_survive_restart(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        path = self.tmpdir / "t3_adapter_state.sqlite3"
        port1 = CountingT3Port(principal=_PRINCIPAL_A)
        adapter1 = _adapter(SQLiteT3AdapterStateStore(path), port1)
        ref = await adapter1.start(spec)
        await adapter1.status(ref)  # cursor "" -> "1", persisted
        self.assertEqual(adapter1.read_cursor(spec.run_id), "1")
        await adapter1.cancel(ref, "superseded")  # requested, not settled

        port2 = CountingT3Port(principal=_PRINCIPAL_A)
        port2.receipts_by_key.update(port1.receipts_by_key)
        adapter2 = _adapter(SQLiteT3AdapterStateStore(path), port2)

        # The new process's first read uses the PERSISTED cursor, not "".
        self.assertEqual(await adapter2.status(ref), WorkerRunStatus.CANCELLING)
        self.assertEqual(port2.reads[-1][2], "1")
        # The cancel ledger survived: requested-but-unsettled, then settles.
        report = adapter2.cancel_report(spec.run_id)
        self.assertIsNotNone(report)
        self.assertTrue(report.requested)
        self.assertFalse(report.settled)
        port2.status_by_thread[ref.provider_session_id] = "cancelled"
        self.assertEqual(await adapter2.status(ref), WorkerRunStatus.CANCELLED)
        report = adapter2.cancel_report(spec.run_id)
        self.assertTrue(report.settled)
        self.assertEqual(report.settled_state, "CANCELLED")

    # (5) a replay returning a different thread is refused -------------------

    async def test_replay_returning_a_different_thread_is_refused(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        port1 = CountingT3Port(principal=_PRINCIPAL_A)
        adapter1 = _adapter(_store(self.tmpdir, "t3_adapter_state.sqlite3"), port1)
        ref = await adapter1.start(spec)
        binding = _recovery_binding(spec, ref)

        # A recovery binding that knows the original thread, replayed by a
        # store that lost the row (pre-durability binding shape): the replay
        # MUST return the original thread.
        port2 = CountingT3Port(principal=_PRINCIPAL_A)
        port2.receipts_by_key.update(port1.receipts_by_key)
        port2.replay_thread_override = ("thr-other", "t3run-other")
        fresh_store = SQLiteT3AdapterStateStore(self.tmpdir / "empty.sqlite3")
        adapter2 = _adapter(fresh_store, port2)
        with self.assertRaises(T3ExecutionAdapterError) as ctx:
            await adapter2.reattach(spec, binding)
        self.assertIn("DIFFERENT thread", str(ctx.exception))
        # Never a replacement launch; nothing was adopted.
        self.assertEqual(port2.launch_count, 0)
        self.assertIsNone(adapter2.retained_original_ref(spec.run_id))

    async def test_replay_receipt_echoing_a_foreign_key_is_refused(self) -> None:
        """Crash-zone replay: a receipt echoing a foreign key is refused."""
        spec = _launch_spec(run_dir=_recovery_run_dir())
        port1 = CountingT3Port(principal=_PRINCIPAL_A)
        port1.lose_ack = True
        adapter1 = _adapter(_store(self.tmpdir, "t3_adapter_state.sqlite3"), port1)
        with self.assertRaises(T3LaunchEffectUnknownError):
            await adapter1.start(spec)
        key = derive_t3_client_request_id(_binding())
        pre_ack_ref = WorkerProcessRef(
            run_id=spec.run_id, pid=0, pgid=0,
            process_start_identity="", boot_session_id="",
            launch_nonce=key, provider_session_id=None,
            stdout_path="", stderr_path="", result_path="",
            started_at="", binary=ref_binary(), base_sha="",
        )
        binding = _recovery_binding(spec, pre_ack_ref)

        port2 = CountingT3Port(principal=_PRINCIPAL_A)
        port2.receipts_by_key.update(port1.receipts_by_key)
        port2.replay_echo_mismatch = True
        adapter2 = _adapter(_store(self.tmpdir, "t3_adapter_state.sqlite3"), port2)
        with self.assertRaises(T3ExecutionAdapterError) as ctx:
            await adapter2.reattach(spec, binding)
        self.assertIn("foreign", str(ctx.exception))
        self.assertIsNone(adapter2.retained_original_ref(spec.run_id))


class StateStoreTests(unittest.TestCase):
    """Store-level round-trips and the coexistence contract."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mmos-t3-store-")
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_round_trip_preserves_every_record_exactly(self) -> None:
        from control_plane.t3_execution_adapter import T3LaunchIntent

        store = SQLiteT3AdapterStateStore(self.tmpdir / "t3_adapter_state.sqlite3")
        spec = _launch_spec()
        binding = _binding()
        envelope = None  # intent envelope built below via the adapter shape
        intent = T3LaunchIntent(
            run_id=spec.run_id,
            client_request_id=derive_t3_client_request_id(binding),
            request_namespace=t3_request_namespace("oauth-client-A"),
            adapter_id="t3-native",
            envelope=envelope,
            created_at="2026-11-08T12:00:00+00:00",
        )
        store.put_launch_intent(intent, binding=binding, spec=spec)
        loaded = store.load_run(spec.run_id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.intent, intent)
        self.assertEqual(loaded.binding, binding)  # incl. tuples + defaults
        self.assertEqual(loaded.spec, spec)  # incl. Paths, tuples, mappings
        self.assertEqual(loaded.cursor, "")
        self.assertEqual(store.run_ids(), (spec.run_id,))

    def test_default_path_is_a_sibling_of_the_executive_sqlite_file(self) -> None:
        # The Executive runtime pins a normalized digest over its ENTIRE
        # sqlite_master (executive_runtime._NORMALIZED_V7_SCHEMA_DIGEST) and
        # refuses to open on mismatch, so the adapter store must never share
        # that file.  Sibling file, same Executive-owned data directory.
        default = default_t3_adapter_state_path()
        self.assertEqual(default.name, "t3_adapter_state.sqlite3")
        self.assertEqual(default.parent, executive_runtime_db_path().parent)
        self.assertNotEqual(default, executive_runtime_db_path())

    def test_store_refuses_the_executive_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(T3ExecutionAdapterError):
                SQLiteT3AdapterStateStore(Path(tmp) / "executive.sqlite3")

    def test_store_tables_coexist_with_an_existing_database_file(self) -> None:
        import sqlite3

        path = self.tmpdir / "t3_adapter_state.sqlite3"
        # An "Executive-owned" table pre-exists in the file.
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE attempts (attempt_id TEXT PRIMARY KEY)"
            )
            conn.execute("INSERT INTO attempts VALUES ('a-1')")
        store = SQLiteT3AdapterStateStore(path)
        spec = _launch_spec()
        store.put_launch_intent(
            T3LaunchIntent(
                run_id=spec.run_id,
                client_request_id="k" * 64,
                request_namespace="ns",
                adapter_id="t3-native",
            ),
            binding=_binding(),
            spec=spec,
        )
        # The foreign table and its row are untouched.
        with sqlite3.connect(path) as conn:
            rows = conn.execute("SELECT attempt_id FROM attempts").fetchall()
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertEqual(rows, [("a-1",)])
        self.assertIn("attempts", tables)
        self.assertIn("t3_adapter_runs", tables)
        # Journal mode was NOT switched by this store (file-owner property).
        mode = sqlite3.connect(path).execute(
            "PRAGMA journal_mode"
        ).fetchone()[0]
        self.assertEqual(mode, "delete")

    def test_clear_launch_attempt_refuses_when_a_receipt_exists(self) -> None:
        from control_plane.t3_execution_adapter import T3LaunchIntent

        store = SQLiteT3AdapterStateStore(self.tmpdir / "t3_adapter_state.sqlite3")
        spec = _launch_spec()
        store.put_launch_intent(
            T3LaunchIntent(
                run_id=spec.run_id,
                client_request_id="k" * 64,
                request_namespace="ns",
                adapter_id="t3-native",
            ),
            binding=_binding(),
            spec=spec,
        )
        store.put_launch_receipt(
            spec.run_id,
            receipt=T3ThreadLaunchReceipt(
                thread_id="thr-1", run_id="t3run-1", client_request_id="k" * 64
            ),
            original_ref=_neutral_shaped_ref(spec.run_id),
            cursor="",
        )
        with self.assertRaises(T3ExecutionAdapterError):
            store.clear_launch_attempt(spec.run_id)
        self.assertIsNotNone(store.load_run(spec.run_id).receipt)
        # Without a receipt the clean-refusal rollback works.
        store.clear_launch_attempt("run-no-receipt")
        store2 = SQLiteT3AdapterStateStore(self.tmpdir / "other.sqlite3")
        store2.put_launch_intent(
            T3LaunchIntent(
                run_id="run-x", client_request_id="k" * 64,
                request_namespace="ns", adapter_id="t3-native",
            ),
            binding=_binding(),
            spec=spec,
        )
        store2.clear_launch_attempt("run-x")
        self.assertIsNone(store2.load_run("run-x"))


def ref_binary():
    from control_plane.t3_execution_adapter import _T3_REMOTE_BINARY_PLACEHOLDER

    return _T3_REMOTE_BINARY_PLACEHOLDER


def _neutral_shaped_ref(run_id: str) -> WorkerProcessRef:
    return WorkerProcessRef(
        run_id=run_id, pid=0, pgid=0,
        process_start_identity="t3:thr-x:t3run-x",
        boot_session_id="t3-native:thr-x",
        launch_nonce="k" * 64, provider_session_id="thr-x",
        stdout_path="t3://thread/thr-x/events",
        stderr_path="t3://thread/thr-x/events",
        result_path="t3://thread/thr-x/result",
        started_at="2026-11-08T12:00:00+00:00",
        binary=ref_binary(), base_sha="",
    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
