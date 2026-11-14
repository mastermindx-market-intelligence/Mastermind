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
    T3NamespaceAttestationError,
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

    def expected_launch_thread_id(self, client_request_id: str) -> str:
        """This fake mints principal-INDEPENDENT ids (``thr-<key8>``), so the
        derivation is the same rule; principal-qualified fakes override it."""
        return f"thr-{client_request_id[:8]}"

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

    def test_store_refuses_an_existing_file_with_foreign_tables_before_ddl(
        self,
    ) -> None:
        """Audit #6: a file another owner already uses (any foreign table) is
        refused BEFORE any DDL — the adapter never adds its table to someone
        else's database (the Executive runtime pins its whole-file digest).
        Replaces the old coexistence contract, which the audit refuted."""
        import sqlite3

        path = self.tmpdir / "t3_adapter_state.sqlite3"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE attempts (attempt_id TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO attempts VALUES ('a-1')")
        with self.assertRaises(T3ExecutionAdapterError) as ctx:
            SQLiteT3AdapterStateStore(path)
        self.assertIn("foreign schema objects", str(ctx.exception))
        with sqlite3.connect(path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            rows = conn.execute("SELECT attempt_id FROM attempts").fetchall()
        self.assertEqual(tables, {"attempts"})  # no t3_adapter_runs DDL ran
        self.assertEqual(rows, [("a-1",)])
        # A file holding ONLY the adapter's table reopens fine, and the
        # journal mode was NOT switched by this store (file-owner property).
        own = self.tmpdir / "own.sqlite3"
        SQLiteT3AdapterStateStore(own).close()
        SQLiteT3AdapterStateStore(own).close()
        mode = sqlite3.connect(own).execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode, "delete")

    def test_clear_launch_attempt_refuses_when_a_receipt_exists(self) -> None:
        from control_plane.t3_execution_adapter import T3LaunchIntent

        store = SQLiteT3AdapterStateStore(self.tmpdir / "t3_adapter_state.sqlite3")
        spec = _launch_spec()
        token = store.put_launch_intent(
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
            store.clear_launch_attempt(spec.run_id, claim_token=token)
        self.assertIsNotNone(store.load_run(spec.run_id).receipt)
        # Without a receipt the clean-refusal rollback works (no row: no-op).
        store.clear_launch_attempt("run-no-receipt", claim_token=token)
        store2 = SQLiteT3AdapterStateStore(self.tmpdir / "other.sqlite3")
        token2 = store2.put_launch_intent(
            T3LaunchIntent(
                run_id="run-x", client_request_id="k" * 64,
                request_namespace="ns", adapter_id="t3-native",
            ),
            binding=_binding(),
            spec=spec,
        )
        store2.clear_launch_attempt("run-x", claim_token=token2)
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


# =============================================================================
# A3 audit rework — one regression per finding (AUDIT_T3_DURABLE_ADAPTER_OPUS_
# 20261109.md).  Every test below FAILS against the pre-rework adapter
# (70dabba15) and passes after; names the rework added are looked up through
# the module INSIDE each test so this file still imports against the pre-fix
# code (the fail-before evidence is per test, not an import error).
# =============================================================================

import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import sqlite3  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from unittest import mock  # noqa: E402

import control_plane.t3_execution_adapter as t3m  # noqa: E402
from control_plane.t3_execution_adapter import InMemoryT3AdapterStateStore  # noqa: E402
from control_plane.worker_execution_contract import WorkerRecoveryBinding  # noqa: E402
from tests.test_t3_execution_adapter import FakeT3Port  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent


class ThreadSafeCountingPort(CountingT3Port):
    """CountingT3Port shared across threads/event loops (one native owner).

    ``launch_delay`` keeps the winner in flight (intent claimed, no receipt)
    so a concurrent claimant hits the real race window.
    """

    def __init__(self, principal: str = _PRINCIPAL_A, launch_delay: float = 0.0) -> None:
        super().__init__(principal=principal)
        self._mutex = threading.Lock()
        self.launch_delay = launch_delay

    async def launch_thread(self, envelope):
        with self._mutex:
            receipt = await super().launch_thread(envelope)
        if self.launch_delay:
            await asyncio.sleep(self.launch_delay)
        return receipt

    async def replay_launch(self, envelope):
        with self._mutex:
            return await super().replay_launch(envelope)


class UnattestedPort(CountingT3Port):
    """A port that cannot attest its principal (no authenticated_namespace)."""

    authenticated_namespace = None  # type: ignore[assignment]


class EchoFreePort(CountingT3Port):
    """Returns receipts WITHOUT echo fields (no upstream proof of identity)."""

    async def replay_launch(self, envelope):
        receipt = await super().replay_launch(envelope)
        return dataclasses.replace(receipt, client_request_id="", request_namespace="")


def _slow_binding_source(delay: float = 0.3):
    def source(spec):
        time.sleep(delay)  # widen the read->launch window (audit #1 probe)
        return _binding()
    return source


def _pre_ack_ref(spec, key: str) -> WorkerProcessRef:
    return WorkerProcessRef(
        run_id=spec.run_id, pid=0, pgid=0,
        process_start_identity="", boot_session_id="",
        launch_nonce=key, provider_session_id=None,
        stdout_path="", stderr_path="", result_path="",
        started_at="", binary=ref_binary(), base_sha="",
    )


class _ProxyConnection:
    """sqlite3.Connection proxy that can fail or interleave on chosen SQL."""

    def __init__(self, inner, *, fail_on=None, before=None) -> None:
        self._inner = inner
        self._fail_on = fail_on
        self._before = before
        self.failures = 0

    def execute(self, sql, params=()):
        head = sql.strip().split()[0].upper()
        if self._before is not None and head in self._before:
            hook = self._before.pop(head)
            hook()
        if self._fail_on is not None and head == self._fail_on and self.failures == 0:
            self.failures += 1
            raise sqlite3.OperationalError("injected failure on " + head)
        return self._inner.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class AuditReworkStartRaceTests(unittest.IsolatedAsyncioTestCase):
    """Finding #1 (BLOCKER) — NM-01/NM-02: no cross-process double launch."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mmos-t3-race-")
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _race(self, port, spec, path, *, binding_delay=0.3):
        """Two threads, two event loops, two SEPARATE SQLite connections."""
        barrier = threading.Barrier(2)
        outcomes: list = [None, None]

        def contender(index: int) -> None:
            adapter = T3ExecutionAdapter(
                port, _slow_binding_source(binding_delay), FakeInspector(),
                clock=_clock, state_store=SQLiteT3AdapterStateStore(path),
            )
            barrier.wait()
            try:
                outcomes[index] = ("ref", asyncio.run(adapter.start(spec)))
            except Exception as exc:  # noqa: BLE001 - recorded for assertions
                outcomes[index] = ("error", exc)

        threads = [threading.Thread(target=contender, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        return outcomes

    async def test_nm01_two_connections_race_start_exactly_one_launch(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        path = self.tmpdir / "t3_adapter_state.sqlite3"
        port = ThreadSafeCountingPort()
        outcomes = self._race(port, spec, path)

        # Exactly ONE native launch reached the port across both claimants.
        self.assertEqual(port.launch_count, 1, outcomes)
        refs = [value for kind, value in outcomes if kind == "ref"]
        errors = [value for kind, value in outcomes if kind == "error"]
        self.assertEqual(len(refs), 1, outcomes)
        self.assertEqual(len(errors), 1, outcomes)
        self.assertIsInstance(errors[0], t3m.T3LaunchClaimConflictError)
        winner = refs[0]
        # Ledger count 1: one row, owned by the winner's claim.
        store = SQLiteT3AdapterStateStore(path)
        self.assertEqual(store.run_ids(), (spec.run_id,))
        self.assertTrue(store.load_run(spec.run_id).claim_token)
        # The loser reattaches to the WINNER's thread with no native call.
        loser_port = ThreadSafeCountingPort()
        loser = _adapter(store, loser_port)
        retained = loser.retained_original_ref(spec.run_id)
        reattached = await loser.reattach(spec, _recovery_binding(spec, retained))
        self.assertEqual(reattached, winner)
        self.assertEqual(loser_port.launch_count, 0)
        self.assertEqual(loser_port.replay_count, 0)

    async def test_nm02_loser_during_in_flight_launch_replays_the_winner(self) -> None:
        """The loser races while the winner's native launch is IN FLIGHT
        (intent claimed, no receipt yet): it never launches; its crash-zone
        reattach replays the SAME key and adopts the winner's thread; the
        winner's later receipt write is an idempotent no-op (write-once)."""
        spec = _launch_spec(run_dir=_recovery_run_dir())
        path = self.tmpdir / "t3_adapter_state.sqlite3"
        port = ThreadSafeCountingPort(launch_delay=0.6)
        key = derive_t3_client_request_id(_binding())

        results: dict = {}

        def winner_thread() -> None:
            adapter = T3ExecutionAdapter(
                port, lambda s: _binding(), FakeInspector(),
                clock=_clock, state_store=SQLiteT3AdapterStateStore(path),
            )
            try:
                results["winner"] = asyncio.run(adapter.start(spec))
            except Exception as exc:  # noqa: BLE001
                results["winner"] = exc

        thread = threading.Thread(target=winner_thread)
        thread.start()
        deadline = time.monotonic() + 10
        while port.launch_count == 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        # Winner is now inside the native launch (thread minted upstream).
        loser = T3ExecutionAdapter(
            port, lambda s: _binding(), FakeInspector(),
            clock=_clock, state_store=SQLiteT3AdapterStateStore(path),
        )
        with self.assertRaises(T3ExecutionAdapterError):
            await loser.start(spec)
        adopted = await loser.reattach(spec, _recovery_binding(spec, _pre_ack_ref(spec, key)))
        thread.join(timeout=30)
        winner = results["winner"]
        self.assertIsInstance(winner, WorkerProcessRef, winner)
        self.assertEqual(adopted, winner)
        self.assertEqual(port.launch_count, 1)
        self.assertEqual(port.replay_count, 1)
        self.assertEqual(SQLiteT3AdapterStateStore(path).run_ids(), (spec.run_id,))

    def test_nm01_two_processes_race_start_exactly_one_launch(self) -> None:
        """Subprocess variant: two OS processes, one on-disk store."""
        run_dir = _recovery_run_dir()
        state = self.tmpdir / "state.sqlite3"
        launches = self.tmpdir / "launches.log"
        go = self.tmpdir / "go"
        script = self.tmpdir / "contender.py"
        script.write_text(_CONTENDER_SCRIPT)
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        procs = []
        for index in range(2):
            procs.append(subprocess.Popen(
                [sys.executable, str(script), str(_REPO_ROOT), str(state),
                 str(launches), str(go), str(run_dir), str(index)],
                cwd=str(_REPO_ROOT), env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            ))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not all(
            (self.tmpdir / f"ready-{i}").exists() for i in range(2)
        ):
            time.sleep(0.02)
        go.write_text("go")
        outputs = [proc.communicate(timeout=60) for proc in procs]
        results = sorted(json.loads(out.strip().splitlines()[-1])["outcome"]
                         for out, _err in outputs)
        self.assertEqual(results, ["claim_conflict", "started"], outputs)
        self.assertEqual(len(launches.read_text().splitlines()), 1)
        store = SQLiteT3AdapterStateStore(state)
        self.assertEqual(store.run_ids(), ("run-1",))


_CONTENDER_SCRIPT = r'''
import asyncio, json, os, sys, time
from pathlib import Path
repo, state, launches, go, run_dir, index = sys.argv[1:7]
sys.path.insert(0, repo)
import control_plane.t3_execution_adapter as t3m
from control_plane.t3_execution_adapter import (
    SQLiteT3AdapterStateStore, T3ExecutionAdapter, T3ThreadLaunchReceipt,
    T3ExecutionAdapterError,
)
from tests.test_t3_execution_adapter import FakeInspector, _binding, _clock, _launch_spec

class FilePort:
    def authenticated_namespace(self):
        return "oauth-client-A"
    async def launch_thread(self, envelope):
        fd = os.open(launches, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.write(fd, (envelope.client_request_id + "\n").encode())
        os.close(fd)
        key = envelope.client_request_id
        return T3ThreadLaunchReceipt(
            thread_id="thr-" + key[:8], run_id="t3run-" + key[:8],
            created_at="2026-11-08T12:00:00+00:00",
            request_namespace=envelope.request_namespace, client_request_id=key)
    async def replay_launch(self, envelope):
        raise AssertionError("replay not expected")
    async def read_thread(self, *a):
        raise AssertionError("read not expected")
    async def interrupt_run(self, *a):
        raise AssertionError("interrupt not expected")

def source(spec):
    time.sleep(0.3)
    return _binding()

spec = _launch_spec(run_dir=Path(run_dir))
adapter = T3ExecutionAdapter(FilePort(), source, FakeInspector(), clock=_clock,
                             state_store=SQLiteT3AdapterStateStore(state))
Path(state).parent.joinpath("ready-" + index).write_text("1")
while not Path(go).exists():
    time.sleep(0.005)
try:
    ref = asyncio.run(adapter.start(spec))
    outcome = "started"
except T3ExecutionAdapterError as exc:
    conflict = getattr(t3m, "T3LaunchClaimConflictError", None)
    outcome = "claim_conflict" if conflict and isinstance(exc, conflict) else "refused:" + str(exc)[:80]
print(json.dumps({"outcome": outcome}))
'''


class AuditReworkStoreTests(unittest.TestCase):
    """Findings #1 (store), #6, #8, #10, #11 and Director G's read-only API."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mmos-t3-store-a3-")
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _intent(self, run_id="run-1", key="k" * 64):
        return T3LaunchIntent(
            run_id=run_id, client_request_id=key,
            request_namespace=t3_request_namespace(_PRINCIPAL_A),
            adapter_id="t3-native",
        )

    # --- #1: intents are claimed once, never upserted; clear is conditional

    def test_launch_intents_are_never_upserted(self) -> None:
        store = SQLiteT3AdapterStateStore(self.tmpdir / "s.sqlite3")
        spec = _launch_spec()
        store.put_launch_intent(self._intent(), binding=_binding(), spec=spec)
        with self.assertRaises(T3ExecutionAdapterError):
            store.put_launch_intent(
                self._intent(key="f" * 64), binding=_binding(), spec=spec
            )
        self.assertEqual(store.load_run("run-1").intent.client_request_id, "k" * 64)

    def test_clear_launch_attempt_is_claimant_conditional(self) -> None:
        store = SQLiteT3AdapterStateStore(self.tmpdir / "s.sqlite3")
        spec = _launch_spec()
        self.assertTrue(store.claim_launch_intent(
            self._intent(), binding=_binding(), spec=spec, claim_token="token-A"
        ))
        self.assertFalse(store.claim_launch_intent(
            self._intent(), binding=_binding(), spec=spec, claim_token="token-B"
        ))
        with self.assertRaises(t3m.T3LaunchClaimConflictError):
            store.clear_launch_attempt("run-1", claim_token="token-B")
        self.assertIsNotNone(store.load_run("run-1"))
        store.clear_launch_attempt("run-1", claim_token="token-A")
        self.assertIsNone(store.load_run("run-1"))

    # --- #6: the Executive file guard -------------------------------------

    def _fake_executive(self) -> Path:
        executive = self.tmpdir / "control_plane" / "executive.sqlite3"
        executive.parent.mkdir()
        with sqlite3.connect(executive) as conn:
            conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY)")
        return executive

    def _assert_executive_untouched(self, executive: Path) -> None:
        with sqlite3.connect(executive) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"jobs"})

    def test_executive_guard_refuses_a_case_variant_name(self) -> None:
        executive = self._fake_executive()
        variant = executive.with_name("Executive.sqlite3")
        with mock.patch.object(t3m, "executive_runtime_db_path", return_value=executive):
            with self.assertRaises(T3ExecutionAdapterError):
                SQLiteT3AdapterStateStore(variant)
        self._assert_executive_untouched(executive)

    def test_executive_guard_refuses_a_symlink_alias(self) -> None:
        executive = self._fake_executive()
        alias = self.tmpdir / "t3_adapter_state.sqlite3"
        alias.symlink_to(executive)
        with mock.patch.object(t3m, "executive_runtime_db_path", return_value=executive):
            with self.assertRaises(T3ExecutionAdapterError):
                SQLiteT3AdapterStateStore(alias)
        self._assert_executive_untouched(executive)

    def test_executive_guard_refuses_a_hardlink_alias_by_inode(self) -> None:
        executive = self.tmpdir / "control_plane" / "executive.sqlite3"
        executive.parent.mkdir()
        executive.write_bytes(b"")  # empty: only inode identity can catch it
        alias = self.tmpdir / "state.sqlite3"
        os.link(executive, alias)
        with mock.patch.object(t3m, "executive_runtime_db_path", return_value=executive):
            with self.assertRaises(T3ExecutionAdapterError):
                SQLiteT3AdapterStateStore(alias)
        self.assertEqual(executive.stat().st_size, 0)

    # --- #8: forward-only cursor -----------------------------------------

    def test_nm03_cursor_never_moves_backwards_across_writers(self) -> None:
        path = self.tmpdir / "s.sqlite3"
        writer_a = SQLiteT3AdapterStateStore(path)
        writer_b = SQLiteT3AdapterStateStore(path)
        writer_a.put_launch_intent(self._intent(), binding=_binding(), spec=_launch_spec())
        writer_a.put_cursor("run-1", "7")
        writer_b.put_cursor("run-1", "4")   # stale concurrent reader
        self.assertEqual(writer_a.load_run("run-1").cursor, "7")
        writer_b.put_cursor("run-1", "")    # empty next_cursor is NOT a reset
        self.assertEqual(writer_a.load_run("run-1").cursor, "7")
        writer_b.put_cursor("run-1", "8")   # a valid advance lands exactly once
        self.assertEqual(writer_a.load_run("run-1").cursor, "8")

    # --- #10: write-once result ledger ------------------------------------

    def test_result_ledger_is_write_once(self) -> None:
        store = SQLiteT3AdapterStateStore(self.tmpdir / "s.sqlite3")
        store.put_launch_intent(self._intent(), binding=_binding(), spec=_launch_spec())
        first = t3m.T3ResultReference(
            run_id="run-1", thread_id="thr-1", result_ref="t3://r/1",
            native_status="completed", recorded_at="t1",
        )
        store.put_result_reference(first)
        store.put_result_reference(dataclasses.replace(first, recorded_at="t2"))
        with self.assertRaises(T3ExecutionAdapterError):
            store.put_result_reference(
                dataclasses.replace(first, result_ref="t3://r/forged")
            )
        self.assertEqual(store.load_run("run-1").result_reference, first)

    # --- #11: COMMIT failure / existence check + rowcount inside the tx ----

    def test_commit_failure_rolls_back_closes_tx_and_is_typed(self) -> None:
        store = SQLiteT3AdapterStateStore(self.tmpdir / "s.sqlite3")
        store.put_launch_intent(self._intent(), binding=_binding(), spec=_launch_spec())
        real = store._connection
        store._connection = _ProxyConnection(real, fail_on="COMMIT")
        with self.assertRaises(T3ExecutionAdapterError) as ctx:
            store.put_cursor("run-1", "3")
        self.assertNotIsInstance(ctx.exception, sqlite3.Error)
        self.assertFalse(real.in_transaction)  # the transaction was closed
        store.put_cursor("run-1", "4")         # the next write still works
        self.assertEqual(store.load_run("run-1").cursor, "4")

    def test_existence_check_and_rowcount_are_inside_the_transaction(self) -> None:
        path = self.tmpdir / "s.sqlite3"
        store = SQLiteT3AdapterStateStore(path)
        store.put_launch_intent(self._intent(), binding=_binding(), spec=_launch_spec())

        def concurrent_delete() -> None:
            other = sqlite3.connect(path)
            other.execute("DELETE FROM t3_adapter_runs WHERE run_id='run-1'")
            other.commit()
            other.close()

        store._connection = _ProxyConnection(
            store._connection, before={"BEGIN": concurrent_delete}
        )
        # The row vanished between "check" and "write": a silent 0-row UPDATE
        # must never pass for a successful write.
        with self.assertRaises(T3ExecutionAdapterError):
            store.put_cursor("run-1", "5")

    # --- Director G: read-only constructor -------------------------------

    def test_open_read_only_reads_without_ddl_and_refuses_writes(self) -> None:
        path = self.tmpdir / "s.sqlite3"
        writer = SQLiteT3AdapterStateStore(path)
        writer.put_launch_intent(self._intent(), binding=_binding(), spec=_launch_spec())
        writer.close()
        before = path.read_bytes()
        reader = SQLiteT3AdapterStateStore.open_read_only(path)
        self.assertTrue(reader.read_only)
        self.assertEqual(reader.run_ids(), ("run-1",))
        self.assertEqual(reader.load_run("run-1").intent.client_request_id, "k" * 64)
        with self.assertRaises(T3ExecutionAdapterError):
            reader.put_cursor("run-1", "9")
        reader.close()
        self.assertEqual(path.read_bytes(), before)  # no DDL, no write
        with self.assertRaises(T3ExecutionAdapterError):
            SQLiteT3AdapterStateStore.open_read_only(self.tmpdir / "missing.sqlite3")
        self.assertFalse((self.tmpdir / "missing.sqlite3").exists())


class AuditReworkAdapterTests(unittest.IsolatedAsyncioTestCase):
    """Findings #3, #5, #8, #9, #12, #13 and Director C's C-P1 at the adapter."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mmos-t3-adapter-a3-")
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _path(self) -> Path:
        return self.tmpdir / "t3_adapter_state.sqlite3"

    # --- #3: namespace isolation never fails open (NM-08) -----------------

    async def test_nm08_unattested_port_cannot_reattach_a_principal_scoped_run(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        ref = await _adapter(SQLiteT3AdapterStateStore(self._path()),
                             CountingT3Port(principal=_PRINCIPAL_A)).start(spec)
        port = UnattestedPort()
        adapter = _adapter(SQLiteT3AdapterStateStore(self._path()), port)
        with self.assertRaises(T3ExecutionAdapterError) as ctx:
            await adapter.reattach(spec, _recovery_binding(spec, ref))
        self.assertEqual(getattr(ctx.exception, "code", None), "T3_REAUTH_REQUIRED")
        self.assertEqual((port.launch_count, port.replay_count), (0, 0))

    async def test_nm08_unattested_port_cannot_replay_a_crash_zone_intent(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        first = CountingT3Port(principal=_PRINCIPAL_A)
        first.lose_ack = True
        with self.assertRaises(T3LaunchEffectUnknownError):
            await _adapter(SQLiteT3AdapterStateStore(self._path()), first).start(spec)
        key = derive_t3_client_request_id(_binding())
        port = UnattestedPort()
        port.receipts_by_key.update(first.receipts_by_key)
        adapter = _adapter(SQLiteT3AdapterStateStore(self._path()), port)
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.reattach(spec, _recovery_binding(spec, _pre_ack_ref(spec, key)))
        self.assertEqual(port.replay_count, 0)
        self.assertIsNone(adapter.retained_original_ref(spec.run_id))

    async def test_nm08_unattested_port_cannot_launch(self) -> None:
        port = UnattestedPort()
        adapter = _adapter(SQLiteT3AdapterStateStore(self._path()), port)
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.start(_launch_spec())
        self.assertEqual(port.launch_count, 0)
        self.assertIsNone(adapter.launch_intent("run-1"))

    async def test_crash_zone_replay_without_upstream_echo_is_not_adopted(self) -> None:
        spec = _launch_spec(run_dir=_recovery_run_dir())
        first = CountingT3Port(principal=_PRINCIPAL_A)
        first.lose_ack = True
        with self.assertRaises(T3LaunchEffectUnknownError):
            await _adapter(SQLiteT3AdapterStateStore(self._path()), first).start(spec)
        key = derive_t3_client_request_id(_binding())
        port = EchoFreePort(principal=_PRINCIPAL_A)
        port.receipts_by_key.update(first.receipts_by_key)
        adapter = _adapter(SQLiteT3AdapterStateStore(self._path()), port)
        with self.assertRaises(T3LaunchEffectUnknownError):
            await adapter.reattach(spec, _recovery_binding(spec, _pre_ack_ref(spec, key)))
        self.assertIsNone(adapter.retained_original_ref(spec.run_id))

    # --- #5: exact spec round-trip, post-restart reattach -----------------

    async def test_spec_with_non_normalized_paths_round_trips_and_reattaches(self) -> None:
        spec = dataclasses.replace(
            _launch_spec(run_dir=_recovery_run_dir()),
            allowed_artifact_paths=("out/./result.json", "out//notes.md"),
            timeout_seconds=30,
        )
        ref = await _adapter(SQLiteT3AdapterStateStore(self._path()),
                             CountingT3Port(principal=_PRINCIPAL_A)).start(spec)
        store = SQLiteT3AdapterStateStore(self._path())
        loaded = store.load_run(spec.run_id).spec
        self.assertEqual(loaded, spec)
        self.assertEqual(loaded.allowed_artifact_paths, spec.allowed_artifact_paths)
        self.assertTrue(all(isinstance(p, str) for p in loaded.allowed_artifact_paths))
        port = CountingT3Port(principal=_PRINCIPAL_A)
        reattached = await _adapter(store, port).reattach(spec, _recovery_binding(spec, ref))
        self.assertEqual(reattached, ref)
        self.assertEqual((port.launch_count, port.replay_count), (0, 0))

    # --- #8 at the adapter: an empty next_cursor never rewinds -----------

    async def test_nm03_status_read_with_empty_or_lower_cursor_never_rewinds(self) -> None:
        port = FakeT3Port()
        adapter = T3ExecutionAdapter(
            port, lambda s: _binding(), FakeInspector(), clock=_clock,
            state_store=SQLiteT3AdapterStateStore(self._path()),
        )
        ref = await adapter.start(_launch_spec())
        thread, native_run = ref.provider_session_id, adapter.launch_receipt("run-1").run_id
        for proposed, expected in (("5", "5"), ("", "5"), ("3", "5"), ("6", "6")):
            port.read_override = T3ThreadReadResult(
                thread_id=thread, run_id=native_run, native_status="running",
                next_cursor=proposed,
            )
            await adapter.status(ref)
            self.assertEqual(adapter.read_cursor("run-1"), expected, proposed)

    # --- #9: a second cancel never downgrades a settled record -----------

    async def test_second_cancel_never_downgrades_a_settled_record(self) -> None:
        port = FakeT3Port()
        adapter = T3ExecutionAdapter(
            port, lambda s: _binding(), FakeInspector(), clock=_clock,
            state_store=SQLiteT3AdapterStateStore(self._path()),
        )
        ref = await adapter.start(_launch_spec())
        await adapter.cancel(ref, "superseded")
        port.status_by_thread[ref.provider_session_id] = "cancelled"
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.CANCELLED)
        settled = adapter.cancel_report("run-1")
        self.assertTrue(settled.settled)
        port.status_by_thread[ref.provider_session_id] = "running"  # stale echo
        await adapter.cancel(ref, "again")
        report = adapter.cancel_report("run-1")
        self.assertTrue(report.settled)
        self.assertEqual(report.settled_state, "CANCELLED")
        self.assertEqual(report.reason, "superseded")
        self.assertEqual(len(port.interrupts), 1)  # idempotent, not a 2nd cancel

    # --- #12: store failure after a successful launch is EFFECT_UNKNOWN ---

    async def test_store_failure_after_successful_launch_is_effect_unknown(self) -> None:
        class FailingReceiptStore(InMemoryT3AdapterStateStore):
            def put_launch_receipt(self, run_id, **kwargs):
                raise sqlite3.OperationalError("disk I/O error")

        port = FakeT3Port()
        adapter = T3ExecutionAdapter(
            port, lambda s: _binding(), FakeInspector(), clock=_clock,
            state_store=FailingReceiptStore(),
        )
        with self.assertRaises(T3LaunchEffectUnknownError) as ctx:
            await adapter.start(_launch_spec())
        self.assertEqual(
            ctx.exception.client_request_id, derive_t3_client_request_id(_binding())
        )
        self.assertEqual(len(port.launch_calls), 1)
        self.assertIsNotNone(adapter.launch_intent("run-1"))  # intent kept

    # --- #13: collect reads a dedicated terminal read --------------------

    async def test_collect_uses_a_terminal_read_not_the_status_cursor(self) -> None:
        class PagedPort(FakeT3Port):
            """Incremental reads past the final reply return an EMPTY page."""

            async def read_thread(self, thread_id, run_id, cursor):
                read = await super().read_thread(thread_id, run_id, cursor)
                if cursor:  # an incremental page after the head
                    return dataclasses.replace(read, result_ref="", result_payload={})
                return read

        port = PagedPort()
        adapter = T3ExecutionAdapter(
            port, lambda s: _binding(), FakeInspector(), clock=_clock,
            state_store=SQLiteT3AdapterStateStore(self._path()),
        )
        ref = await adapter.start(_launch_spec())
        port.status_by_thread[ref.provider_session_id] = "succeeded"
        await adapter.status(ref)  # terminal poll advances the cursor to "1"
        self.assertEqual(adapter.read_cursor("run-1"), "1")
        receipt = await adapter.collect_result(ref)
        self.assertEqual(receipt.result.status, WorkerRunStatus.SUCCEEDED)
        self.assertEqual(port.reads[-1][2], "")      # head (terminal) read
        self.assertEqual(adapter.read_cursor("run-1"), "1")  # cursor untouched

    async def test_collect_refuses_a_bare_thread_id_as_result_reference(self) -> None:
        port = FakeT3Port()
        adapter = T3ExecutionAdapter(
            port, lambda s: _binding(), FakeInspector(), clock=_clock,
            state_store=SQLiteT3AdapterStateStore(self._path()),
        )
        ref = await adapter.start(_launch_spec())
        native_run = adapter.launch_receipt("run-1").run_id
        port.read_override = T3ThreadReadResult(
            thread_id=ref.provider_session_id, run_id=native_run,
            native_status="completed", result_ref=ref.provider_session_id,
        )
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.collect_result(ref)
        self.assertIsNone(adapter.result_ledger_entry("run-1"))

    # --- Director C, C-P1: verify the v1.1 t3 join at launch --------------

    async def test_cp1_drifted_operation_key_is_refused(self) -> None:
        drifted = _binding(runtime_kind="t3-native", operation_key="0" * 64,
                           caller_namespace=t3m.T3_REQUEST_NAMESPACE)
        port = FakeT3Port()
        adapter = T3ExecutionAdapter(port, lambda s: drifted, FakeInspector(), clock=_clock)
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.start(_launch_spec())
        self.assertEqual(port.launch_calls, [])
        self.assertIsNone(adapter.launch_intent("run-1"))

    async def test_cp1_foreign_caller_namespace_is_refused(self) -> None:
        base = _binding(runtime_kind="t3-native")
        foreign = _binding(
            runtime_kind="t3-native",
            operation_key=derive_t3_client_request_id(base),
            caller_namespace=t3_request_namespace("some-other-client"),
        )
        port = FakeT3Port()
        adapter = T3ExecutionAdapter(port, lambda s: foreign, FakeInspector(), clock=_clock)
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter.start(_launch_spec())
        self.assertEqual(port.launch_calls, [])

    async def test_cp1_claim_seam_binding_launches_under_the_joined_key(self) -> None:
        """End to end with Director C's real claim seam: the binding issued by
        ``AttemptRegistry.claim_job`` launches under EXACTLY its operation_key
        and the attested principal's namespace; a hand-corrupted copy of the
        same binding is refused (C's suggested test)."""
        from control_plane.child_execution_contracts import ExecutionBinding
        from tests.test_executive_claim_job_placement_authority import (
            _observations, _runtime, _t3_spec,
        )

        runtime, _ = _runtime(self.tmpdir)
        runtime.workers.register_worker(
            "worker-t3", provider="codex", account_label="acct-t3",
            worker_type="mock", capabilities=["code"],
            quota_classes={"default": {"capabilities": ["code"],
                                       "metadata": {"adapter_id": "t3-native"}}},
            metadata={"host_id": "ubuntu0"},
        )
        job = runtime.jobs.create_job(
            "t3 child", constraints={"child_placement": _t3_spec("t3-child-a3")}
        )
        lease = runtime.attempts.claim_job(job.job_id, placement_observations=_observations())
        binding = ExecutionBinding.from_dict(
            runtime.attempts.execution_binding(lease.attempt.attempt_id)
        )
        self.assertEqual(binding.runtime_kind, "t3-native")
        expiry = binding.lease_expiry
        clock = (
            (lambda: datetime.fromisoformat(expiry.replace("Z", "+00:00"))
             - timedelta(seconds=1))
            if expiry else _clock
        )
        spec = dataclasses.replace(_launch_spec(), worker_id=binding.worker_id)
        port = FakeT3Port()
        adapter = T3ExecutionAdapter(port, lambda s: binding, FakeInspector(), clock=clock)
        ref = await adapter.start(spec)
        self.assertEqual(ref.launch_nonce, binding.operation_key)
        self.assertEqual(port.launch_calls[0].client_request_id, binding.operation_key)
        self.assertEqual(
            port.launch_calls[0].request_namespace,
            t3_request_namespace("oauth-client-test"),
        )
        corrupted = dataclasses.replace(binding, operation_key="e" * 64)
        port2 = FakeT3Port()
        adapter2 = T3ExecutionAdapter(port2, lambda s: corrupted, FakeInspector(), clock=clock)
        with self.assertRaises(T3ExecutionAdapterError):
            await adapter2.start(spec)
        self.assertEqual(port2.launch_calls, [])

# =============================================================================
# A4 re-audit N3 — a same-NAME foreign table is verified by its columns.
# =============================================================================

_V1_DDL = (
    "CREATE TABLE t3_adapter_runs ("
    " run_id TEXT PRIMARY KEY, intent_json TEXT, receipt_json TEXT,"
    " original_ref_json TEXT, binding_json TEXT, spec_json TEXT,"
    " cursor_text TEXT NOT NULL DEFAULT '', cancel_json TEXT,"
    " result_ref_json TEXT,"
    " schema_version TEXT NOT NULL DEFAULT 'mastermind.t3_adapter_state/v1',"
    " updated_ms INTEGER NOT NULL)"
)


class A4ReauditN3StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @staticmethod
    def _columns(path: Path) -> list[tuple]:
        with sqlite3.connect(path) as conn:
            return [tuple(row) for row in conn.execute("PRAGMA table_info(t3_adapter_runs)")]

    def test_n3_same_name_foreign_tables_are_refused_before_any_ddl(self) -> None:
        foreign_ddls = {
            "different columns": "CREATE TABLE t3_adapter_runs (run_id TEXT PRIMARY KEY, owner TEXT)",
            "extra column": _V1_DDL[:-1] + ", foreign_note TEXT)",
            "missing column": _V1_DDL.replace(" cancel_json TEXT,", ""),
            "different type": _V1_DDL.replace("updated_ms INTEGER", "updated_ms TEXT"),
            "nullability differs": _V1_DDL.replace(
                "cursor_text TEXT NOT NULL DEFAULT ''", "cursor_text TEXT DEFAULT ''"
            ),
            "no primary key": _V1_DDL.replace("run_id TEXT PRIMARY KEY", "run_id TEXT"),
            "added column with another type": _V1_DDL[:-1] + ", claim_token INTEGER)",
        }
        for label, ddl in foreign_ddls.items():
            with self.subTest(label):
                path = self.tmpdir / f"{label.replace(' ', '_')}.sqlite3"
                with sqlite3.connect(path) as conn:
                    conn.execute(ddl)
                before = self._columns(path)
                with self.assertRaises(T3ExecutionAdapterError) as ctx:
                    SQLiteT3AdapterStateStore(path)
                self.assertIn("not this adapter's", str(ctx.exception))
                self.assertEqual(self._columns(path), before)  # no ALTER/CREATE ran
                with self.assertRaises(T3ExecutionAdapterError):
                    SQLiteT3AdapterStateStore.open_read_only(path)

    def test_n3_a_genuine_v1_table_is_accepted_and_upgraded_in_place(self) -> None:
        path = self.tmpdir / "v1.sqlite3"
        with sqlite3.connect(path) as conn:
            conn.execute(_V1_DDL)
        store = SQLiteT3AdapterStateStore(path)
        store.close()
        names = [row[1] for row in self._columns(path)]
        self.assertEqual(names[-2:], ["spec_sha256", "claim_token"])
        SQLiteT3AdapterStateStore(path).close()  # reopen of our own table
        SQLiteT3AdapterStateStore.open_read_only(path).close()




class PrincipalQualifiedT3Port(CountingT3Port):
    """Fake upstream that, like T3, derives the thread id from (principal,
    key): the same key under another OAuth client is a DIFFERENT thread."""

    def _thread_for(self, key: str) -> str:
        return f"thr-{self.principal}-{key[:8]}"

    def expected_launch_thread_id(self, client_request_id: str) -> str:
        return self._thread_for(client_request_id)

    async def launch_thread(self, envelope) -> T3ThreadLaunchReceipt:
        self.launch_count += 1
        key = envelope.client_request_id
        receipt = self.receipts_by_key.get(key)
        if receipt is None:
            receipt = T3ThreadLaunchReceipt(
                thread_id=self._thread_for(key), run_id=f"t3run-{key[:8]}",
                project_id="proj-1", status="running",
                link=f"https://t3.example/thread/{self._thread_for(key)}",
                created_at="2026-11-08T12:00:00+00:00",
                request_namespace=envelope.request_namespace, client_request_id=key,
            )
            self.receipts_by_key[key] = receipt
        return receipt


class ReAuditR1NoRowReplayTests(unittest.IsolatedAsyncioTestCase):
    """Re-audit #3 R1: a pre-durability recovery (store has NO row) must never
    replay under a principal that cannot prove it owns the original thread —
    a replay is a real launch call and would mint a second thread upstream."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    async def _original(self):
        spec = _launch_spec(run_dir=_recovery_run_dir())
        port_a = PrincipalQualifiedT3Port(principal=_PRINCIPAL_A)
        adapter_a = _adapter(_store(self.tmpdir, "a.sqlite3"), port_a)
        ref = await adapter_a.start(spec)
        return spec, port_a, ref, _recovery_binding(spec, ref)

    async def test_foreign_principal_is_refused_with_zero_mutating_calls(self) -> None:
        spec, port_a, ref, binding = await self._original()
        port_b = PrincipalQualifiedT3Port(principal="oauth-client-B")
        port_b.receipts_by_key.update(port_a.receipts_by_key)  # upstream knows A's thread
        adapter_b = _adapter(SQLiteT3AdapterStateStore(self.tmpdir / "lost-row.sqlite3"), port_b)
        with self.assertRaises(T3NamespaceAttestationError) as ctx:
            await adapter_b.reattach(spec, binding)
        self.assertEqual(ctx.exception.reason, "PRINCIPAL_MISMATCH")
        self.assertEqual((port_b.launch_count, port_b.replay_count), (0, 0))
        self.assertEqual(len(port_a.receipts_by_key), 1)  # upstream still has ONE thread
        self.assertIsNone(adapter_b.retained_original_ref(spec.run_id))

    async def test_port_without_derivation_is_refused_before_any_call(self) -> None:
        spec, port_a, ref, binding = await self._original()
        class Underivable(PrincipalQualifiedT3Port):
            expected_launch_thread_id = None  # type: ignore[assignment]
        port = Underivable(principal=_PRINCIPAL_A)
        port.receipts_by_key.update(port_a.receipts_by_key)
        adapter = _adapter(SQLiteT3AdapterStateStore(self.tmpdir / "lost-row2.sqlite3"), port)
        with self.assertRaises(T3NamespaceAttestationError) as ctx:
            await adapter.reattach(spec, binding)
        self.assertEqual(ctx.exception.reason, "PRINCIPAL_UNPROVABLE")
        self.assertEqual((port.launch_count, port.replay_count), (0, 0))

    async def test_original_principal_still_replays_and_adopts(self) -> None:
        spec, port_a, ref, binding = await self._original()
        port_a2 = PrincipalQualifiedT3Port(principal=_PRINCIPAL_A)
        port_a2.receipts_by_key.update(port_a.receipts_by_key)
        adapter = _adapter(SQLiteT3AdapterStateStore(self.tmpdir / "lost-row3.sqlite3"), port_a2)
        adopted = await adapter.reattach(spec, binding)
        self.assertEqual(adopted.provider_session_id, ref.provider_session_id)
        self.assertEqual((port_a2.launch_count, port_a2.replay_count), (0, 1))
        self.assertEqual(len(port_a.receipts_by_key), 1)
