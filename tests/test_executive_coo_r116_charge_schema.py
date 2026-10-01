"""Causal checks for the worker-authored v6 charge schema and offline upgrade."""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from control_plane import executive_backup, executive_runtime
from control_plane.executive_runtime import ExecutiveSchemaUpgradeRequired, PersistenceError, Runtime, StateConflict
from tests.test_executive_backup import _upgrade_test_release_and_census
from tests.test_executive_coo_hierarchy import _r7a_seed_active_domain_with_review


CHARGE_COLUMNS = (
    "charge_id", "root_job_id", "job_id", "attempt_id", "worker_id",
    "operation_id", "effect_class", "turn_id", "reservation_identity",
    "event_id", "created_at_ms",
)


def _seed(runtime: Runtime) -> tuple[str, str]:
    runtime.workers.register_worker(
        "worker-schema", provider="codex", account_label="primary",
        worker_type="mock", capabilities=["code"],
    )
    job = runtime.jobs.create_job("v6 charge fixture")
    lease = runtime.attempts.claim_job(job.job_id, worker_id="worker-schema")
    assert lease is not None
    return job.job_id, lease.attempt.attempt_id


def _domain(tmp_path, monkeypatch):
    runtime, root, domain, _adapter, _command = _r7a_seed_active_domain_with_review(
        tmp_path, monkeypatch=monkeypatch,
    )
    assert domain.current_attempt_id is not None
    return runtime, root.job_id, domain.job_id, domain.current_attempt_id


def _charge(
    runtime: Runtime, root: str, job: str, attempt: str, ordinal: int,
    *, effect: str = "ORDINARY", verb: str = "INSERT", operation: str | None = None,
    charge_id: str | None = None, event_id: int | None = None,
    null_charge_id: bool = False, rowid_alias: str | None = None,
) -> None:
    with runtime.store.transaction() as connection:
        attempt_row = connection.execute(
            "SELECT worker_id, quota_class FROM attempts WHERE attempt_id=?", (attempt,)
        ).fetchone()
        assert attempt_row is not None
        worker_id, quota_class = attempt_row
        charge_id = (None if null_charge_id else
                     charge_id if charge_id is not None else f"charge-{ordinal}")
        operation = operation or f"operation-{ordinal}"
        payload = {
            "charge_id": charge_id, "root_job_id": root, "operation_id": operation,
            "effect_class": effect, "turn_id": f"turn-{ordinal}",
            "reservation_identity": f"reservation-{ordinal}",
        }
        if effect == "FINAL":
            payload.update(domain_job_id=job, domain_attempt_id=attempt)
        if event_id is None:
            runtime.store.append_event(
                connection, aggregate_type="job", aggregate_id=job,
                event_type=("COO_DOMAIN_CONSUMPTION_CHARGED" if effect == "FINAL"
                            else "COO_PROVIDER_CHARGE_RECORDED"),
                actor="coo", job_id=job, attempt_id=attempt,
                worker_id=worker_id, quota_class=quota_class, payload=payload,
            )
            event_id = connection.execute("SELECT MAX(event_id) FROM events").fetchone()[0]
        values = (
            charge_id, root, job, attempt, worker_id,
            operation, effect, f"turn-{ordinal}",
            f"reservation-{ordinal}", event_id, ordinal,
        )
        columns = CHARGE_COLUMNS
        if rowid_alias is not None:
            assert rowid_alias in {"rowid", "_rowid_", "oid"}
            columns = (rowid_alias,) + columns
            values = (1,) + values
        connection.execute(
            f"{verb} INTO coo_provider_charges({','.join(columns)}) "
            f"VALUES({','.join('?' for _ in values)})", values,
        )


def _downgrade_empty_charge_table(database: Path) -> None:
    connection = sqlite3.connect(database)
    try:
        connection.execute("DROP TABLE coo_provider_charges")
        connection.execute("DELETE FROM schema_migrations WHERE version=6")
        connection.commit()
    finally:
        connection.close()


def test_fresh_v6_is_exact_and_empty(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    assert executive_runtime.SCHEMA_VERSION == 6
    with runtime.store.read() as connection:
        assert executive_runtime._normalized_schema_digest(connection) == executive_runtime._NORMALIZED_V6_SCHEMA_DIGEST
        assert [row[1] for row in connection.execute("PRAGMA table_info(coo_provider_charges)")] == list(CHARGE_COLUMNS)
        assert connection.execute("PRAGMA table_info(coo_provider_charges)").fetchone()[3] == 1
        assert connection.execute(
            "SELECT wr FROM pragma_table_list WHERE name='coo_provider_charges'"
        ).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM coo_provider_charges").fetchone()[0] == 0


def test_exact_v5_open_refuses_without_mutating_database(tmp_path):
    base = tmp_path / "runtime"
    Runtime.at(base)
    database = base / "data" / "control_plane" / "executive.sqlite3"
    _downgrade_empty_charge_table(database)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    mode = database.stat().st_mode
    with pytest.raises(ExecutiveSchemaUpgradeRequired, match="upgrade_v5_to_v6"):
        Runtime.at(base, create=False, existing_writable=True)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert database.stat().st_mode == mode
    assert not os.path.lexists(database.with_name(database.name + "-wal"))
    assert not os.path.lexists(database.with_name(database.name + "-shm"))


@pytest.mark.parametrize("final_first", [False, True])
def test_root_conserves_31_ordinary_plus_one_final_in_either_order(tmp_path, monkeypatch, final_first):
    runtime, root, domain, attempt = _domain(tmp_path, monkeypatch)
    if final_first:
        _charge(runtime, root, domain, attempt, 32, effect="FINAL")
    for ordinal in range(1, 32):
        _charge(runtime, root, domain, attempt, ordinal)
    if not final_first:
        _charge(runtime, root, domain, attempt, 32, effect="FINAL")
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM coo_provider_charges WHERE root_job_id=?", (root,)).fetchone()[0] == 32
    with pytest.raises(StateConflict, match="ordinary.*ceiling"):
        _charge(runtime, root, domain, attempt, 33)
    with pytest.raises(StateConflict, match="final"):
        _charge(runtime, root, domain, attempt, 34, effect="FINAL")
    with pytest.raises(StateConflict, match="immutable"):
        with runtime.store.transaction() as connection:
            connection.execute("UPDATE coo_provider_charges SET effect_class='FINAL' WHERE charge_id='charge-1'")
    with pytest.raises(StateConflict, match="immutable"):
        with runtime.store.transaction() as connection:
            connection.execute("DELETE FROM coo_provider_charges WHERE charge_id='charge-1'")


def test_replace_and_duplicate_operation_cannot_consume_a_fresh_slot(tmp_path, monkeypatch):
    runtime, root, domain, attempt = _domain(tmp_path, monkeypatch)
    _charge(runtime, root, domain, attempt, 1)
    with pytest.raises(StateConflict, match="duplicate COO provider charge identity"):
        _charge(runtime, root, domain, attempt, 2, verb="INSERT OR REPLACE", charge_id="charge-1")
    with pytest.raises(StateConflict, match="duplicate COO provider charge identity"):
        _charge(runtime, root, domain, attempt, 3, operation="operation-1")
    with runtime.store.read() as connection:
        assert connection.execute("SELECT charge_id FROM coo_provider_charges").fetchall()[0][0] == "charge-1"
        assert connection.execute("SELECT COUNT(*) FROM coo_provider_charges").fetchone()[0] == 1


@pytest.mark.parametrize("rowid_alias", ["rowid", "_rowid_", "oid"])
def test_implicit_rowid_replacement_cannot_erase_charge(tmp_path, monkeypatch, rowid_alias):
    runtime, root, domain, attempt = _domain(tmp_path, monkeypatch)
    _charge(runtime, root, domain, attempt, 1, effect="FINAL")
    with pytest.raises(PersistenceError, match="no column named"):
        _charge(runtime, root, domain, attempt, 2, verb="INSERT OR REPLACE",
                rowid_alias=rowid_alias)
    with pytest.raises(StateConflict, match="final"):
        _charge(runtime, root, domain, attempt, 3, effect="FINAL")
    with runtime.store.read() as connection:
        assert connection.execute(
            "SELECT charge_id, effect_class FROM coo_provider_charges WHERE root_job_id=?", (root,)
        ).fetchall()[0][:] == ("charge-1", "FINAL")


def test_charge_rejects_foreign_event_and_non_domain_final(tmp_path, monkeypatch):
    runtime, root, domain, attempt = _domain(tmp_path, monkeypatch)
    with runtime.store.read() as connection:
        foreign_event = connection.execute(
            "SELECT event_id FROM events WHERE job_id=? ORDER BY event_id LIMIT 1", (root,)
        ).fetchone()[0]
    with pytest.raises(StateConflict, match="Event binding"):
        _charge(runtime, root, domain, attempt, 1, event_id=foreign_event)
    with pytest.raises(StateConflict, match="Event binding|NOT NULL constraint"):
        _charge(runtime, root, domain, attempt, 3, null_charge_id=True)
    ordinary_root, ordinary_attempt = _seed(runtime)
    with pytest.raises(StateConflict, match="hierarchy"):
        _charge(runtime, ordinary_root, ordinary_root, ordinary_attempt, 2, effect="FINAL")
    with pytest.raises(StateConflict, match="hierarchy"):
        _charge(runtime, ordinary_root, ordinary_root, ordinary_attempt, 4)


def test_explicit_offline_v5_to_v6_preserves_nonempty_history_and_backups(tmp_path, monkeypatch):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    base = tmp_path / "runtime"
    runtime = Runtime.at(base)
    _seed(runtime)
    database = base / "data" / "control_plane" / "executive.sqlite3"
    with runtime.store.read() as connection:
        before = executive_backup.full_v4_content_digest(connection)
    _downgrade_empty_charge_table(database)
    service_lock = database.parent / executive_backup.DEFAULT_SERVICE_LOCK_NAME
    service_lock.touch(mode=0o600)
    service_lock.chmod(0o600)
    receipt = executive_backup.upgrade_v5_to_v6(
        database, tmp_path / "backups", release_sha=release_sha,
    )
    assert receipt.source_schema_version == 5
    assert receipt.target_schema_version == 6
    assert receipt.full_v4_content_equal is True
    assert receipt.pre_full_v4_content_digest == before
    assert receipt.post_full_v4_content_digest == before
    assert executive_backup.verify_backup(
        receipt.v5_backup_path, receipt.v5_backup_manifest_path, expected_schema_version=5,
    ).normalized_schema_digest == executive_runtime._NORMALIZED_V5_SCHEMA_DIGEST
    assert executive_backup.verify_backup(
        receipt.v6_backup_path, receipt.v6_backup_manifest_path, expected_schema_version=6,
    ).normalized_schema_digest == executive_runtime._NORMALIZED_V6_SCHEMA_DIGEST
    reopened = Runtime.at(base)
    with reopened.store.read() as connection:
        assert executive_backup.full_v4_content_digest(connection) == before
        assert connection.execute("SELECT COUNT(*) FROM coo_provider_charges").fetchone()[0] == 0


def test_offline_upgrade_rolls_back_historical_receipt_timestamp_drift(tmp_path, monkeypatch):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    base = tmp_path / "runtime"
    runtime = Runtime.at(base)
    _seed(runtime)
    database = base / "data" / "control_plane" / "executive.sqlite3"
    _downgrade_empty_charge_table(database)
    service_lock = database.parent / executive_backup.DEFAULT_SERVICE_LOCK_NAME
    service_lock.touch(mode=0o600)
    service_lock.chmod(0o600)
    before = executive_backup._upgrade_database_state(database, version=5)
    migration = executive_runtime._MIGRATIONS[5]
    poisoned = migration[:2] + (migration[2] + (
        "UPDATE schema_migrations SET applied_at_ms=applied_at_ms+1 WHERE version=5",
    ),)
    migrations = executive_runtime._MIGRATIONS[:5] + (poisoned,)
    monkeypatch.setattr(executive_runtime, "_MIGRATIONS", migrations)
    monkeypatch.setattr(executive_backup, "_MIGRATIONS", migrations)
    with pytest.raises(executive_backup.ExecutiveSchemaUpgradeError, match="rolled back"):
        executive_backup.upgrade_v5_to_v6(
            database, tmp_path / "backups", release_sha=release_sha,
        )
    after = executive_backup._upgrade_database_state(database, version=5)
    assert executive_backup._rollback_reproduces_preflight(after, before)
    assert after["v5_migration_receipts"] == before["v5_migration_receipts"]
    assert not (database.parent / "executive-schema-upgrade.in-progress.json").exists()


@pytest.mark.parametrize("phase", ["after_m6_receipt", "before_v6_commit"])
def test_offline_upgrade_precommit_fault_restores_exact_v5(tmp_path, monkeypatch, phase):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    base = tmp_path / "runtime"
    runtime = Runtime.at(base)
    _seed(runtime)
    database = base / "data" / "control_plane" / "executive.sqlite3"
    _downgrade_empty_charge_table(database)
    service_lock = database.parent / executive_backup.DEFAULT_SERVICE_LOCK_NAME
    service_lock.touch(mode=0o600)
    service_lock.chmod(0o600)
    before = executive_backup._upgrade_database_state(database, version=5)

    def fault(observed):
        if observed == phase:
            raise RuntimeError("injected v6 precommit fault")

    monkeypatch.setattr(executive_backup, "_SCHEMA_UPGRADE_TEST_HOOK", fault)
    with pytest.raises(executive_backup.ExecutiveSchemaUpgradeError, match="rolled back"):
        executive_backup.upgrade_v5_to_v6(
            database, tmp_path / "backups", release_sha=release_sha,
        )
    after = executive_backup._upgrade_database_state(database, version=5)
    assert executive_backup._rollback_reproduces_preflight(after, before)
    assert after["v5_migration_receipts"] == before["v5_migration_receipts"]
    assert not (database.parent / "executive-schema-upgrade.in-progress.json").exists()


def test_v6_online_backup_and_restore_drill_include_charge(tmp_path, monkeypatch):
    runtime, root, domain, attempt = _domain(tmp_path, monkeypatch)
    _charge(runtime, root, domain, attempt, 1)
    receipt = executive_backup.create_online_backup(runtime.store, tmp_path / "backups")
    verified = executive_backup.verify_backup(receipt.database_path, receipt.manifest_path)
    drill = executive_backup.verify_restore_drill(receipt.database_path, receipt.manifest_path)
    assert verified.normalized_schema_digest == executive_runtime._NORMALIZED_V6_SCHEMA_DIGEST
    assert [item.version for item in verified.migrations] == [1, 2, 3, 4, 5, 6]
    assert drill.runtime_schema_version == 6
    assert drill.migration_versions == (1, 2, 3, 4, 5, 6)
