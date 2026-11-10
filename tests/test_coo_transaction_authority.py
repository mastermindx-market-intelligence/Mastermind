"""Original Runtime guard custody, real SQLite budgets and service namespace.

No model, host grant, caller-native identity, or public SAME receipt is inferred.
The real claim/result/ACK owners run; only the incumbent provider is inert.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import copy_context
import fcntl
import json
import os
import sqlite3

import pytest

from control_plane import executive_runtime as er
from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody, _coo_write_namespace
from tests.test_coo_requester_return import _fixture, _claim, _finish, _read, _ack, _events


@contextmanager
def namespace_owner(runtime):
    directory = runtime.store.path.parent
    lock, marker = directory / "executive-service.lock", directory / "executive-service.running"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    marker.write_text(json.dumps({"instance_id": "coo-transaction-test", "pid": os.getpid()}))
    marker.chmod(0o600)
    owner = ServiceRuntimeNamespaceCustody(runtime=runtime, service_lock_fd=descriptor,
        lock_path=lock, marker_path=marker, instance_id="coo-transaction-test")
    try:
        owner.start()
        yield owner
    finally:
        owner.close()
        os.close(descriptor)


def assert_unclaimed(f):
    assert f.runtime.store.get_event_by_command_id(f.command) is None
    child = f.runtime.jobs.get_job(f.child.job_id)
    assert child.attempt_count == 0 and child.current_attempt_id is None
    assert not _events(f)
    assert not f.runtime.store._write_connections and not f.runtime.store._coo_write_progress
    assert er._current_coo_write_authority(f.runtime.store) is None


def test_original_claim_sees_its_own_mutation_and_expires_every_guard(tmp_path):
    f = _fixture(tmp_path)
    seen, scopes, budgets = [], [], []
    with namespace_owner(f.runtime) as owner:
        enters = []
        original_enter = owner._enter
        def counted_enter(capability):
            enters.append(capability)
            return original_enter(capability)
        owner._enter = counted_enter
        def guard():
            scope = er._current_coo_write_authority(f.runtime.store)
            assert scope.root_job_id == f.root.job_id and scope.command_id == f.command
            assert not hasattr(scope, "receipt")
            capability = _coo_write_namespace(owner.bound_runtime(f.runtime), f.runtime, scope)
            snapshot, creation = scope.read_root()
            assert creation.job_id == snapshot.root_job_id == f.root.job_id
            child = next(row for row in snapshot.jobs if row.job_id == f.child.job_id)
            seen.append(child.attempt_count)
            scopes.append(scope)
            budgets.append(scope._require_lexical())
            assert not budgets[-1]._active and not budgets[-1]._removed
            capability.validate(owner.database_path)
        dispatch = _claim(f, guard=guard)
        assert seen == [0, 1] and enters == []
        assert dispatch.attempt.job_id == f.child.job_id
        assert all(item._removed and not item._active for item in budgets)
        for scope in scopes:
            with pytest.raises(er.StateConflict, match="scope is unavailable"):
                scope.read_root()
        # The public path still uses a separate genuine namespace reservation
        # and only produces SAME after that physical reader has closed.
        reader = owner.bound_runtime(f.runtime)
        with reader.observe_bounded_read() as observation:
            observation.read_job_root_bounded(f.root.job_id)
        assert observation.receipt.state == "SAME" and len(enters) == 1


def test_ack_rechecks_original_completed_result_inside_original_writer(tmp_path):
    f = _fixture(tmp_path)
    _finish(f, _claim(f))
    original = _read(f)
    seen = []
    with namespace_owner(f.runtime) as owner:
        def guard():
            scope = er._current_coo_write_authority(f.runtime.store)
            if scope is None:
                return
            _coo_write_namespace(owner.bound_runtime(f.runtime), f.runtime, scope)
            snapshot, _ = scope.read_root()
            child = next(row for row in snapshot.jobs if row.job_id == f.child.job_id)
            assert child.status.value == "COMPLETED"
            seen.append(scope)
        result = _ack(f, {"action": "acknowledge_result", "command": f.command, "result": original},
            currentness_guard=guard)
    assert len(seen) == 3 and result["consumption"] is not None
    assert len(_events(f)) == 1
    assert all(not scope._active for scope in seen)


@pytest.mark.parametrize("boundary", ["foreign_store", "foreign_thread", "changed_identity", "cancel"])
def test_live_scope_cannot_be_transferred_or_replace_original_identity(tmp_path, boundary):
    f = _fixture(tmp_path)
    foreign = er.Runtime.at(f.runtime.store.root, create=False)
    def guard():
        scope = er._current_coo_write_authority(f.runtime.store)
        if boundary == "foreign_store":
            er._current_coo_write_authority(foreign.store)
        elif boundary == "foreign_thread":
            context = copy_context()
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(context.run, scope.require_current, f.runtime.store).result()
        elif boundary == "changed_identity":
            scope.root_job_id = "JOB-999"
        else:
            scope.read_root()
            raise asyncio.CancelledError()
    expected = asyncio.CancelledError if boundary == "cancel" else AttributeError if boundary == "changed_identity" else er.StateConflict
    with pytest.raises(expected):
        _claim(f, guard=guard)
    assert_unclaimed(f)


def test_plain_or_foreign_connection_never_becomes_a_coo_write_scope(tmp_path):
    f = _fixture(tmp_path)
    with f.runtime.store.read() as connection:
        with pytest.raises(er.StateConflict, match="scope is unavailable"):
            with er._coo_write_authority_scope(f.runtime.store, connection, f.root.job_id, f.command):
                pytest.fail("ordinary read became write authority")
    with f.runtime.store.transaction() as connection:
        with pytest.raises(er.StateConflict, match="budget is unavailable"):
            with er._coo_write_authority_scope(f.runtime.store, connection, f.root.job_id, f.command):
                pytest.fail("unqualified writer became guarded authority")
    assert_unclaimed(f)


def test_vm_budget_interrupts_actual_sql_and_rolls_back_original_claim(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    budgets = []
    def over_budget(loader, root):
        loader.execute("SELECT SUM(x) FROM (WITH RECURSIVE many(x) AS "
            "(SELECT 1 UNION ALL SELECT x+1 FROM many WHERE x<1000000) SELECT x FROM many)").fetchone()
        pytest.fail("unbounded SQL bypassed the original VM ceiling")
    monkeypatch.setattr(er, "_accounted_root_snapshot", over_budget)
    def guard():
        scope = er._current_coo_write_authority(f.runtime.store)
        budgets.append(scope._require_lexical())
        scope.read_root()
    with pytest.raises(er.RuntimeRoleResultOverBudget):
        _claim(f, guard=guard)
    assert budgets[0].tripped and budgets[0]._removed and not budgets[0]._active
    assert_unclaimed(f)


def test_raw_cell_budget_refuses_before_decoding_runtime_material(tmp_path):
    f = _fixture(tmp_path)
    with f.runtime.store.transaction() as connection:
        connection.execute("UPDATE jobs SET objective=? WHERE job_id=?",
            ("x" * (er.BOUNDED_ROLE_RESULT_MAX_CELL_BYTES + 1), f.root.job_id))
    def guard():
        er._current_coo_write_authority(f.runtime.store).read_root()
    with pytest.raises(er.RuntimeRoleResultOverBudget):
        _claim(f, guard=guard)
    assert_unclaimed(f)


def test_guard_budget_is_inert_for_later_sql_and_removed_only_by_original_owner(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    installed = []
    original = er._CooWriteReadProgressGuard._install_fresh
    def record(self, connection):
        installed.append((self, connection))
        return original(self, connection)
    monkeypatch.setattr(er._CooWriteReadProgressGuard, "_install_fresh", record)
    with f.runtime.store.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] > 0
    assert installed == []
    with f.runtime.store.transaction(_coo_guarded=True) as connection:
        budget = installed[0][0]
        with er._coo_write_authority_scope(f.runtime.store, connection, f.root.job_id, f.command) as scope:
            scope.read_root()
        steps = budget.steps
        assert not budget._active and not budget._removed
        result = connection.execute("WITH RECURSIVE many(x) AS "
            "(SELECT 1 UNION ALL SELECT x+1 FROM many WHERE x<1000000) SELECT SUM(x) FROM many").fetchone()[0]
        assert result == 500000500000 and budget.steps == steps
    assert budget._removed and not budget._active
    assert_unclaimed(f)


def test_namespace_revocation_after_read_is_rechecked_before_original_guard_exits(tmp_path):
    f = _fixture(tmp_path)
    with namespace_owner(f.runtime) as owner:
        def guard():
            scope = er._current_coo_write_authority(f.runtime.store)
            _coo_write_namespace(owner.bound_runtime(f.runtime), f.runtime, scope)
            scope.read_root()
            owner._marker_path.write_text(json.dumps({"instance_id": "foreign", "pid": os.getpid()}))
        with pytest.raises(er.RuntimeReadUnavailable):
            _claim(f, guard=guard)
    assert_unclaimed(f)


def test_precommit_revocation_after_own_attempt_creation_rolls_back_every_effect(tmp_path):
    f = _fixture(tmp_path)
    seen = []
    def guard():
        scope = er._current_coo_write_authority(f.runtime.store)
        snapshot, _ = scope.read_root()
        child = next(row for row in snapshot.jobs if row.job_id == f.child.job_id)
        seen.append(child.attempt_count)
        if child.attempt_count:
            raise er.StateConflict("original permission revoked before commit")
    with pytest.raises(er.StateConflict, match="permission revoked"):
        _claim(f, guard=guard)
    assert seen == [0, 1]
    assert_unclaimed(f)


@pytest.mark.parametrize("close_fails", [False, True])
def test_guard_closes_actual_read_cursors_and_leaves_writer_cleanup_to_runtime(tmp_path, monkeypatch, close_fails):
    f = _fixture(tmp_path)
    cursors = []
    failed = []
    capture = [False]
    class ReadCursor(sqlite3.Cursor):
        def close(self):
            if close_fails and self in cursors and not failed:
                failed.append(self)
                raise OSError("disposable cursor close response lost")
            return super().close()
    class ReadConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            cursor = self.cursor(factory=ReadCursor)
            result = cursor.execute(sql, parameters)
            if capture[0] and sql.lstrip().upper().startswith("SELECT "):
                cursors.append(cursor)
            return result
    connect = er.sqlite3.connect
    def original_connection(*args, **options):
        return connect(*args, **{**options, "factory": ReadConnection})
    monkeypatch.setattr(er.sqlite3, "connect", original_connection)
    def guard():
        scope = er._current_coo_write_authority(f.runtime.store)
        capture[0] = True
        try:
            scope.read_root()
        finally:
            capture[0] = False
        for cursor in cursors:
            with pytest.raises(sqlite3.ProgrammingError):
                cursor.fetchone()
        scope.require_current(f.runtime.store)
    if close_fails:
        with pytest.raises(er.RuntimeReadUnavailable, match="cursor close failed"):
            _claim(f, guard=guard)
        assert failed
        assert_unclaimed(f)
    else:
        assert _claim(f, guard=guard).attempt.job_id == f.child.job_id
    assert cursors
    for cursor in cursors:
        with pytest.raises(sqlite3.ProgrammingError):
            cursor.fetchone()
