"""Regression: writable-existing Executive preflight must see active WAL.

Only disposable SQLite databases are changed. The production migration and
unknown-effect/retry modules are not touched. Native DB writes here deliberately
simulate a foreign schema mutation to challenge the existing verifier.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from control_plane.executive_runtime import Runtime, PersistenceError


def _active_wal(tmp_path: Path):
    runtime = Runtime.at(tmp_path)
    path = runtime.store.path
    keeper = sqlite3.connect(path, isolation_level=None, timeout=10)
    assert keeper.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    keeper.execute("BEGIN")
    keeper.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
    return runtime, path, keeper


def test_active_wal_foreign_schema_must_not_be_invisible_to_existing_writable_preflight(tmp_path):
    _runtime, path, keeper = _active_wal(tmp_path)
    try:
        with sqlite3.connect(path, timeout=10) as writer:
            writer.execute("CREATE TABLE unexpected_wal_schema(id TEXT)")
        assert Path(str(path) + "-wal").exists()
        assert Path(str(path) + "-shm").exists()
        with pytest.raises(PersistenceError, match="schema|DDL|verified"):
            Runtime.at(tmp_path)
    finally:
        keeper.close()


def test_current_active_wal_schema_can_be_opened_without_false_corruption(tmp_path):
    runtime, path, keeper = _active_wal(tmp_path)
    try:
        before = runtime.jobs.create_job("Current WAL schema write", requested_authorities=["READ"])
        assert Path(str(path) + "-wal").exists()
        reopened = Runtime.at(tmp_path)
        assert reopened.jobs.get_job(before.job_id).job_id == before.job_id
    finally:
        keeper.close()


def test_offline_current_schema_preflight_does_not_invent_wal_sidecars(tmp_path):
    runtime = Runtime.at(tmp_path)
    path = runtime.store.path
    assert not Path(str(path) + "-wal").exists()
    assert not Path(str(path) + "-shm").exists()
    reopened = Runtime.at(tmp_path)
    assert reopened.store.path == path
    assert not Path(str(path) + "-wal").exists()
    assert not Path(str(path) + "-shm").exists()


def test_schema_preflight_itself_must_not_ignore_uncheckpointed_wal_ddl(tmp_path):
    runtime, path, keeper = _active_wal(tmp_path)
    try:
        with sqlite3.connect(path, timeout=10) as writer:
            writer.execute("CREATE TABLE unreviewed_schema_only_in_wal(id TEXT)")
        assert Path(str(path)+"-wal").exists()
        with pytest.raises(PersistenceError, match="schema|DDL|verified"):
            runtime.store._inspect_existing_writable_schema()
    finally:
        keeper.close()


def test_schema_preflight_itself_accepts_current_wal_without_new_sidecars(tmp_path):
    runtime, path, keeper = _active_wal(tmp_path)
    try:
        runtime.jobs.create_job("Legitimate append to current WAL",requested_authorities=["READ"])
        wal=Path(str(path)+"-wal")
        shm=Path(str(path)+"-shm")
        assert wal.exists() and shm.exists()
        before_wal=(wal.stat().st_dev,wal.stat().st_ino)
        before_shm=(shm.stat().st_dev,shm.stat().st_ino)
        runtime.store._inspect_existing_writable_schema()
        assert (wal.stat().st_dev,wal.stat().st_ino)==before_wal
        assert (shm.stat().st_dev,shm.stat().st_ino)==before_shm
    finally:
        keeper.close()


def test_incomplete_wal_sidecars_cannot_let_immutable_preflight_accept_unknown_effect(tmp_path):
    runtime = Runtime.at(tmp_path)
    wal=Path(str(runtime.store.path)+"-wal")
    wal.write_bytes(b"unverified uncheckpointed WAL data")
    try:
        with pytest.raises(PersistenceError, match="WAL|sidecar|verify"):
            runtime.store._inspect_existing_writable_schema()
    finally:
        wal.unlink(missing_ok=True)


def test_many_concurrent_preflights_read_one_unchanged_active_wal_schema(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    runtime, path, keeper = _active_wal(tmp_path)
    try:
        child = runtime.jobs.create_job("Read same schema from many startups",
                                        requested_authorities=["READ"])
        assert Path(str(path)+"-wal").exists() and Path(str(path)+"-shm").exists()
        def open_one(_index):
            another = Runtime.at(tmp_path)
            return another.jobs.get_job(child.job_id).job_id
        with ThreadPoolExecutor(max_workers=4) as executor:
            opened = list(executor.map(open_one, range(30)))
        assert opened == [child.job_id]*30
        with sqlite3.connect(path) as connection:
            assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        keeper.close()


def test_thirty_concurrent_startups_without_pinned_wal_sidecars(tmp_path):
    """Live open/close churn must not manufacture corruption from good v5 DDL."""
    from concurrent.futures import ThreadPoolExecutor
    runtime = Runtime.at(tmp_path)
    child = runtime.jobs.create_job("Ordinary WAL startup contention",
                                    requested_authorities=["READ"])
    def observe(_):
        try:
            another = Runtime.at(tmp_path)
            job = another.jobs.get_job(child.job_id)
            return "OK" if job is not None else "MISSING"
        except Exception as exc:
            return f"{type(exc).__name__}:{exc}"
    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = list(executor.map(observe, range(30)))
    assert outcomes == ["OK"]*30, outcomes


def test_orphan_wal_refusal_preserves_original_sidecar_bytes(tmp_path):
    runtime = Runtime.at(tmp_path)
    wal = Path(str(runtime.store.path) + "-wal")
    shm = Path(str(runtime.store.path) + "-shm")
    original = b"foreign/unverified WAL marker; no valid SQLite header"
    wal.write_bytes(original)
    try:
        with pytest.raises(PersistenceError, match="WAL|sidecar|verify"):
            runtime.store._inspect_existing_writable_schema()
        assert wal.read_bytes() == original
        assert not shm.exists()
    finally:
        wal.unlink(missing_ok=True)


def test_offline_foreign_v5_ddl_refusal_leaves_sidecars_absent(tmp_path):
    runtime = Runtime.at(tmp_path)
    path = runtime.store.path
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE not_in_reviewed_schema(value INTEGER)")
        connection.commit()
    finally:
        connection.close()
    assert not Path(str(path) + "-wal").exists()
    assert not Path(str(path) + "-shm").exists()
    with pytest.raises(PersistenceError, match="schema|DDL|verified"):
        runtime.store._inspect_existing_writable_schema()
    assert not Path(str(path) + "-wal").exists()
    assert not Path(str(path) + "-shm").exists()


def test_live_wal_altered_migration_checksum_is_not_accepted_even_if_ddl_is_same(tmp_path):
    runtime, path, keeper = _active_wal(tmp_path)
    try:
        with sqlite3.connect(path, timeout=10) as writer:
            writer.execute("UPDATE schema_migrations SET checksum=? WHERE version=5", ("f"*64,))
        assert Path(str(path) + "-wal").exists()
        with pytest.raises(PersistenceError, match="migration|checksum"):
            runtime.store._inspect_existing_writable_schema()
    finally:
        keeper.close()


def test_no_schema_preflight_transaction_admits_a_writable_existing_store_without_v5(tmp_path):
    from control_plane.executive_runtime import RuntimeStore
    runtime = Runtime.at(tmp_path)
    path=runtime.store.path
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE schema_migrations SET checksum=? WHERE version=5", ("e"*64,))
        connection.commit()
    finally:
        connection.close()
    assert not Path(str(path) + "-wal").exists()
    with pytest.raises(PersistenceError, match="migration|checksum"):
        RuntimeStore(tmp_path, create=False, existing_writable=True)
    assert not Path(str(path) + "-wal").exists()
