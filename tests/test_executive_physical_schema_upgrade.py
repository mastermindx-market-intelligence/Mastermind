"""Offline schema-7 preservation and physical-history restore adversaries.

All databases, policy observations, release/census seams and resource effects in
these tests are fixture-owned. No installed Runtime, service or provider is used.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from control_plane import executive_backup as backup
from control_plane import executive_runtime as rt
from tests.test_executive_backup import (
    _exact_v4, _populate_v4_evidence, _upgrade_test_release_and_census,
)
from tests.test_executive_os_sqlite import m2_store, _m2_reserve, _m2_envelope


def _exact_v6(path: Path) -> Path:
    _exact_v4(path)
    _populate_v4_evidence(path)
    with sqlite3.connect(path) as connection:
        for version, name, statements in rt._MIGRATIONS[4:6]:
            for statement in statements:
                connection.execute(statement)
            connection.execute("INSERT INTO schema_migrations VALUES(?,?,?,?)",
                               (version, name, rt._migration_checksum(statements), -101 * version))
    return path


def _full_v6(path: Path) -> str:
    with backup._readonly_database(path) as connection:
        return backup.full_v6_content_digest(connection)


def _history(path: Path) -> str:
    with backup._readonly_database(path) as connection:
        return backup.physical_history_digest(connection)


def _file_set(path: Path):
    return {
        p.name: (p.lstat().st_mode, p.lstat().st_ino,
                 hashlib.sha256(p.read_bytes()).hexdigest())
        for p in path.parent.iterdir() if p.is_file()
    }


def test_normal_v6_open_refuses_before_writable_sqlite_or_metadata_change(tmp_path, monkeypatch):
    path = _exact_v6(tmp_path / "runtime" / "executive.sqlite3")
    path.chmod(0o400)
    before = _file_set(path)
    connect = sqlite3.connect
    calls = []

    def readonly_only(database, *args, **kwargs):
        calls.append(str(database))
        assert "mode=ro" in str(database) and "immutable=1" in str(database)
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(rt.sqlite3, "connect", readonly_only)
    with pytest.raises(rt.ExecutiveSchemaUpgradeRequired, match="upgrade_v6_to_v7"):
        rt.RuntimeStore(path.parent, database_path=path)
    assert calls and _file_set(path) == before


def test_upgrade_preserves_all_v6_cells_timestamps_and_empty_physical_history(tmp_path, monkeypatch):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    path = _exact_v6(tmp_path / "runtime" / "executive.sqlite3")
    before = _full_v6(path)
    receipt = backup.upgrade_v6_to_v7(path, tmp_path / "backups", release_sha=release)
    assert receipt.source_schema_version == 6 and receipt.target_schema_version == 7
    assert receipt.pre_full_v6_content_digest == before == receipt.post_full_v6_content_digest
    assert receipt.full_v6_content_equal is True
    assert _full_v6(path) == before
    assert receipt.physical_history_digest == _history(path)
    with backup._readonly_database(path) as connection:
        assert connection.execute("SELECT applied_at_ms FROM schema_migrations WHERE version=6").fetchone()[0] == -606
        assert connection.execute("SELECT COUNT(*) FROM physical_resource_commitments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM physical_resource_demands").fetchone()[0] == 0
    for version, database, manifest in (
        (6, receipt.v6_backup_path, receipt.v6_backup_manifest_path),
        (7, receipt.v7_backup_path, receipt.v7_backup_manifest_path),
    ):
        assert _full_v6(Path(database)) == before
        proof = backup.verify_restore_drill(database, manifest, expected_schema_version=version)
        assert proof.runtime_schema_version == version
    completion = json.loads(Path(receipt.completion_receipt_path).read_text())
    assert completion["initial_physical_tables_empty"] is True
    assert completion["physical_history_digest"] == receipt.physical_history_digest
    assert not (path.parent / backup._UPGRADE_BARRIER_NAME).exists()
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="already exists"):
        backup.upgrade_v6_to_v7(path, tmp_path / "again", release_sha=release)


@pytest.mark.parametrize("phase", [
    "preflight_persisted", "exclusive_v6_verified",
    *[f"after_m7_statement:{n:02d}" for n in range(1, len(rt._MIGRATIONS[6][2]) + 1)],
    "after_m7_receipt", "before_v7_commit",
])
def test_every_precommit_fault_preserves_exact_v6_and_cleans_only_proven_barrier(tmp_path, monkeypatch, phase):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    path = _exact_v6(tmp_path / "runtime" / "executive.sqlite3")
    before = _full_v6(path)

    def fail(observed):
        if observed == phase:
            raise RuntimeError("fixture migration fault")

    monkeypatch.setattr(backup, "_SCHEMA_UPGRADE_TEST_HOOK", fail)
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="rolled back"):
        backup.upgrade_v6_to_v7(path, tmp_path / "backups", release_sha=release)
    backup.verify_backup(path, expected_schema_version=6)
    assert _full_v6(path) == before
    assert not (path.parent / backup._UPGRADE_BARRIER_NAME).exists()
    assert not (path.parent / backup._UPGRADE_V6_TO_V7_PREFLIGHT_NAME).exists()


@pytest.mark.parametrize("phase", [
    "after_v7_commit_before_checkpoint", "after_v7_checkpoint",
    "completion_persisted", "before_barrier_unlink",
])
def test_postcommit_failure_retains_v7_and_quarantines_normal_writers(tmp_path, monkeypatch, phase):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    path = _exact_v6(tmp_path / "runtime" / "executive.sqlite3")
    before = _full_v6(path)

    def fail(observed):
        if observed == phase:
            raise RuntimeError("fixture postcommit fault")

    monkeypatch.setattr(backup, "_SCHEMA_UPGRADE_TEST_HOOK", fail)
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="forward fix"):
        backup.upgrade_v6_to_v7(path, tmp_path / "backups", release_sha=release)
    backup.verify_backup(path, expected_schema_version=7)
    assert _full_v6(path) == before
    assert (path.parent / backup._UPGRADE_BARRIER_NAME).exists()
    with pytest.raises(rt.PersistenceError, match="barrier"):
        rt.RuntimeStore(path.parent, database_path=path)


@pytest.mark.parametrize("migration_version", range(1, 7))
def test_prior_migration_timestamp_drift_is_detected_inside_exclusive_transaction(
        tmp_path, monkeypatch, migration_version):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    path = _exact_v6(tmp_path / "runtime" / "executive.sqlite3")
    before = _full_v6(path)
    original = backup._verify_connection
    changed = False

    def drift(connection, **kwargs):
        nonlocal changed
        value = original(connection, **kwargs)
        if kwargs.get("expected_schema_version") == 7 and connection.in_transaction and not changed:
            connection.execute("UPDATE schema_migrations SET applied_at_ms=12345 WHERE version=?",
                               (migration_version,))
            changed = True
        return value

    monkeypatch.setattr(backup, "_verify_connection", drift)
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="rolled back"):
        backup.upgrade_v6_to_v7(path, tmp_path / "backups", release_sha=release)
    assert changed and _full_v6(path) == before
    backup.verify_backup(path, expected_schema_version=6)


@pytest.mark.parametrize("aggregate,event_type", [
    ("physical_resource_operation", "FIXTURE_REFUSAL"),
    ("fixture", "PHYSICAL_RESOURCE_REFUSED"),
])
def test_v6_with_physical_event_semantics_cannot_be_promoted_as_initial(tmp_path, monkeypatch, aggregate, event_type):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    path = _exact_v6(tmp_path / "runtime" / "executive.sqlite3")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO events(aggregate_type,aggregate_id,sequence,event_type,command_id,actor,payload_json,created_at_ms)"
            " VALUES(?,?,1,?,'fixture:physical-event','fixture','{}',1)",
            (aggregate, "fixture", event_type),
        )
    before = _full_v6(path)
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="rolled back"):
        backup.upgrade_v6_to_v7(path, tmp_path / "backups", release_sha=release)
    assert _full_v6(path) == before
    backup.verify_backup(path, expected_schema_version=6)


def test_full_v6_digest_sees_migration_six_timestamp_where_full_v5_does_not(tmp_path):
    path = _exact_v6(tmp_path / "runtime" / "executive.sqlite3")
    with backup._readonly_database(path) as connection:
        prior_v5 = backup.full_v5_content_digest(connection)
        prior_v6 = backup.full_v6_content_digest(connection)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE schema_migrations SET applied_at_ms=applied_at_ms+1 WHERE version=6")
    with backup._readonly_database(path) as connection:
        assert backup.full_v5_content_digest(connection) == prior_v5
        assert backup.full_v6_content_digest(connection) != prior_v6


def _physical_state(runtime, request, state):
    outcome = _m2_reserve(runtime, request)
    assert outcome["admitted"]
    if state == "ABANDONED_NO_EFFECT":
        outcome = runtime.broker.settle_physical(_m2_envelope(
            request, outcome, "abandon", evidence={
                "terminal_effect_state": "NO_EFFECT", "positive_no_effect": True, "pools": {},
            }), caller_context=None)
    elif state != "RESERVED":
        outcome = runtime.broker.begin_physical(_m2_envelope(request, outcome, "begin"), caller_context=None)
        assert outcome["fresh_begin"] is True
        if state == "ACTIVE":
            outcome = runtime.broker.observe_physical(_m2_envelope(
                request, outcome, "active", evidence={
                    "usage": {"memory": 1}, "attribution_id": "fixture-memory", "baseline_id": "base-1",
                }), caller_context=None)
        elif state == "RECONCILIATION_REQUIRED":
            outcome = runtime.broker.observe_physical(_m2_envelope(
                request, outcome, "overrun", evidence={
                    "usage": {"memory": 150}, "attribution_id": "fixture-overrun", "baseline_id": "base-1",
                }), caller_context=None)
    assert outcome["receipt"]["commitments"][0]["state"] == state
    return outcome


@pytest.mark.parametrize("state", [
    "RESERVED", "EFFECT_MAY_HAVE_BEGUN", "ACTIVE", "RECONCILIATION_REQUIRED", "ABANDONED_NO_EFFECT",
])
def test_backup_drill_and_equal_history_restore_conserve_each_physical_state(m2_store, tmp_path, state):
    runtime, _, request, _ = m2_store()
    outcome = _physical_state(runtime, request, state)
    before = _history(runtime.store.path)
    saved = backup.create_online_backup(runtime.store, tmp_path / "backups")
    assert _history(Path(saved.database_path)) == before
    backup.verify_restore_drill(saved.database_path, saved.manifest_path)
    runtime.jobs.create_job("unrelated post-backup state")
    restored = backup.restore_backup_offline(runtime.store, saved.database_path, saved.manifest_path)
    assert restored.physical_history_digest == before == _history(runtime.store.path)
    # Restore changes the inode. The old Runtime must not silently retarget;
    # actual physical policy qualification remains a separate owner decision.
    with pytest.raises(rt.PersistenceError, match="inode changed"):
        runtime.broker.physical_status({"reservation": request}, caller_context=None)
    assert not (runtime.store.path.parent / backup._UPGRADE_BARRIER_NAME).exists()


@pytest.mark.parametrize("state", [
    "RESERVED", "EFFECT_MAY_HAVE_BEGUN", "ACTIVE", "RECONCILIATION_REQUIRED", "ABANDONED_NO_EFFECT",
])
def test_older_backup_cannot_erase_physical_history_or_terminal_tombstones(m2_store, tmp_path, state):
    runtime, _, request, _ = m2_store()
    saved = backup.create_online_backup(runtime.store, tmp_path / "backups")
    _physical_state(runtime, request, state)
    before = _file_set(runtime.store.path)
    before_history = _history(runtime.store.path)
    with pytest.raises(backup.RestoreSafetyError, match="retained physical history"):
        backup.restore_backup_offline(runtime.store, saved.database_path, saved.manifest_path)
    after = _file_set(runtime.store.path)
    for name, value in before.items():
        assert after[name] == value
    assert _history(runtime.store.path) == before_history
    assert not list(runtime.store.path.parent.glob("*.pre-restore-*"))


def test_older_backup_cannot_erase_refusal_only_event_with_no_debit(m2_store, tmp_path):
    runtime, _, request, context = m2_store()
    saved = backup.create_online_backup(runtime.store, tmp_path / "backups")
    context["observations"]["pools"]["memory"]["available"] = 0
    refused = _m2_reserve(runtime, request)
    assert refused["code"] == "INSUFFICIENT_CAPACITY"
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM physical_resource_commitments").fetchone()[0] == 0
    before = _history(runtime.store.path)
    with pytest.raises(backup.RestoreSafetyError, match="retained physical history"):
        backup.restore_backup_offline(runtime.store, saved.database_path, saved.manifest_path)
    assert _history(runtime.store.path) == before


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_sidecars_refuse_without_removal_or_main_file_change(m2_store, tmp_path, suffix):
    runtime, _, request, _ = m2_store()
    _m2_reserve(runtime, request)
    saved = backup.create_online_backup(runtime.store, tmp_path / "backups")
    sidecar = runtime.store.path.with_name(runtime.store.path.name + suffix)
    sidecar.write_bytes(b"unqualified physical history sidecar")
    sidecar.chmod(0o600)
    before = _file_set(runtime.store.path)
    with pytest.raises(backup.RestoreSafetyError, match="sidecar-free"):
        backup.restore_backup_offline(runtime.store, saved.database_path, saved.manifest_path)
    for name, value in before.items():
        assert _file_set(runtime.store.path)[name] == value


def test_restore_rechecks_live_history_after_rollback_copy(m2_store, tmp_path, monkeypatch):
    runtime, _, request, _ = m2_store()
    saved = backup.create_online_backup(runtime.store, tmp_path / "backups")
    original = backup._preserve_rollback_set
    changed_history = []

    def move(target, rollback):
        paths = original(target, rollback)
        _m2_reserve(runtime, request)
        changed_history.append(_history(runtime.store.path))
        return paths

    monkeypatch.setattr(backup, "_preserve_rollback_set", move)
    with pytest.raises(backup.RestoreSafetyError, match="changed before database replacement"):
        backup.restore_backup_offline(runtime.store, saved.database_path, saved.manifest_path)
    assert _history(runtime.store.path) == changed_history[0]
    assert not list(runtime.store.path.parent.glob("*.pre-restore-*"))


def test_cli_transition_is_closed_and_default_preserves_historical_entry():
    from scripts import executive_os_migrate as cli
    parser = cli._parser()
    base = ["--database", "/fixture/db", "--backup-directory", "/fixture/backups",
            "--release-sha", "a" * 40]
    assert parser.parse_args(base).transition == "v3-to-v4"
    assert parser.parse_args([*base, "--transition", "v6-to-v7"]).transition == "v6-to-v7"
    with pytest.raises(SystemExit):
        parser.parse_args([*base, "--transition", "auto"])


@pytest.mark.parametrize("when,version", [
    ("preflight_persisted", 6), ("before_barrier_unlink", 6), ("before_barrier_unlink", 7),
])
@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
@pytest.mark.parametrize("kind", ["file", "dangling_symlink"])
def test_late_retained_backup_sidecars_never_qualify_completion(
        tmp_path, monkeypatch, when, version, suffix, kind):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    path = _exact_v6(tmp_path / "runtime" / "executive.sqlite3")
    sidecars = []

    def tamper(phase):
        if phase != when:
            return
        receipt_name = (backup._UPGRADE_V6_TO_V7_PREFLIGHT_NAME if version == 6
                        else backup._UPGRADE_V6_TO_V7_COMPLETION_NAME)
        receipt = json.loads((path.parent / receipt_name).read_text())
        source = Path(receipt[f"v{version}_backup"]["database_path"])
        sidecar = source.with_name(source.name + suffix)
        if kind == "file":
            sidecar.write_bytes(b"late unqualified SQLite sidecar")
            sidecar.chmod(0o600)
        else:
            sidecar.symlink_to(tmp_path / "missing-sidecar-target")
        sidecars.append(sidecar)

    monkeypatch.setattr(backup, "_SCHEMA_UPGRADE_TEST_HOOK", tamper)
    match = "rolled back" if when == "preflight_persisted" else "forward fix"
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match=match):
        backup.upgrade_v6_to_v7(path, tmp_path / "backups", release_sha=release)
    assert sidecars and os.path.lexists(sidecars[0])
    assert (path.parent / backup._UPGRADE_BARRIER_NAME).exists() == (when != "preflight_persisted")


def test_equal_total_charge_with_different_commitment_identity_refuses_restore(m2_store, tmp_path):
    first, _, first_request, _ = m2_store("first")
    second, _, second_request, _ = m2_store("second")
    second_request["operation_key"] = "different-operation"
    second_request["command_id"] = "physical:different-operation"
    left = _m2_reserve(first, first_request)
    right = _m2_reserve(second, second_request)
    assert sum(d["remaining_charge"] for d in left["receipt"]["commitments"][0]["demands"]) == sum(
        d["remaining_charge"] for d in right["receipt"]["commitments"][0]["demands"])
    saved = backup.create_online_backup(second.store, tmp_path / "backups")
    before = _history(first.store.path)
    with pytest.raises(backup.RestoreSafetyError, match="retained physical history"):
        backup.restore_backup_offline(first.store, saved.database_path, saved.manifest_path)
    assert _history(first.store.path) == before


def test_real_live_wal_with_new_physical_event_is_preserved_on_refusal(m2_store, tmp_path):
    runtime, _, request, _ = m2_store()
    _m2_reserve(runtime, request)
    saved = backup.create_online_backup(runtime.store, tmp_path / "backups")
    connection = sqlite3.connect(runtime.store.path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "INSERT INTO events(aggregate_type,aggregate_id,sequence,event_type,command_id,actor,payload_json,created_at_ms)"
            " VALUES('physical_resource_operation','wal-only',1,'PHYSICAL_RESOURCE_REFUSED','fixture:wal-only','fixture','{}',1)"
        )
        connection.commit()
        assert runtime.store.path.with_name(runtime.store.path.name + "-wal").exists()
        before = _file_set(runtime.store.path)
        with pytest.raises(backup.RestoreSafetyError, match="sidecar-free"):
            backup.restore_backup_offline(runtime.store, saved.database_path, saved.manifest_path)
        for name, state in before.items():
            assert _file_set(runtime.store.path)[name] == state
    finally:
        connection.close()


@pytest.mark.parametrize("failure", ["rollback_missing", "rollback_fails", "lock_replaced", "barrier_replaced"])
def test_post_swap_uncertainty_retains_writer_barrier_and_never_uses_unowned_rollback(
        m2_store, tmp_path, monkeypatch, failure):
    runtime, _, request, _ = m2_store()
    _m2_reserve(runtime, request)
    saved = backup.create_online_backup(runtime.store, tmp_path / "backups")
    target = runtime.store.path.resolve()
    barrier = target.parent / backup._UPGRADE_BARRIER_NAME
    lock = target.parent / backup.DEFAULT_SERVICE_LOCK_NAME
    replace = backup.os.replace
    restore = backup._restore_rollback_set
    recovery_calls = []
    mutated = False

    def recover(*args):
        recovery_calls.append(args)
        if failure == "rollback_fails":
            raise OSError("fixture rollback failure")
        return restore(*args)

    def swap(source, destination):
        nonlocal mutated
        result = replace(source, destination)
        if Path(destination) == target and ".restore-" in Path(source).name and not mutated:
            mutated = True
            payload = json.loads(barrier.read_text())
            assert payload["schema_version"] == backup.RESTORE_BARRIER_SCHEMA
            if failure == "rollback_missing":
                Path(payload["rollback_path"]).unlink()
            elif failure == "lock_replaced":
                lock.rename(lock.with_name(lock.name + ".displaced"))
                lock.write_text("")
                lock.chmod(0o600)
            elif failure == "barrier_replaced":
                raw = barrier.read_bytes()
                barrier.rename(barrier.with_name(barrier.name + ".displaced"))
                barrier.write_bytes(raw)
                barrier.chmod(0o600)
            raise OSError("fixture failure after live swap")
        return result

    monkeypatch.setattr(backup, "_restore_rollback_set", recover)
    monkeypatch.setattr(backup.os, "replace", swap)
    with pytest.raises(backup.RestoreRollbackError, match="remains unknown"):
        backup.restore_backup_offline(runtime.store, saved.database_path, saved.manifest_path)
    assert mutated and barrier.exists()
    assert len(recovery_calls) == (1 if failure == "rollback_fails" else 0)
    with pytest.raises(rt.PersistenceError, match="barrier"):
        rt.Runtime.at(runtime.store.root)
    if failure != "rollback_missing":
        assert Path(json.loads(barrier.read_text())["rollback_path"]).exists()


def test_partial_restore_barrier_stays_occupied_without_live_mutation(m2_store, tmp_path, monkeypatch):
    runtime, _, request, _ = m2_store()
    _m2_reserve(runtime, request)
    saved = backup.create_online_backup(runtime.store, tmp_path / "backups")
    target = runtime.store.path
    before = target.read_bytes()
    barrier = target.parent / backup._UPGRADE_BARRIER_NAME
    write = backup._write_private_json

    def partial(path, payload):
        if path == barrier:
            path.write_bytes(b"{")
            path.chmod(0o600)
            raise OSError("fixture interrupted barrier write")
        return write(path, payload)

    monkeypatch.setattr(backup, "_write_private_json", partial)
    with pytest.raises(backup.RestoreRollbackError, match="remains unknown"):
        backup.restore_backup_offline(runtime.store, saved.database_path, saved.manifest_path)
    assert barrier.read_bytes() == b"{"
    assert target.read_bytes() == before
    assert list(target.parent.glob("*.pre-restore-*"))
    assert list(target.parent.glob(".*.restore-*.tmp"))


def test_controller_crash_after_barrier_retains_stage_rollback_and_quarantine(m2_store, tmp_path, monkeypatch):
    class ControllerCrash(BaseException):
        pass

    runtime, _, request, _ = m2_store()
    _m2_reserve(runtime, request)
    saved = backup.create_online_backup(runtime.store, tmp_path / "backups")
    target = runtime.store.path
    before = target.read_bytes()
    replace = backup.os.replace

    def crash(source, destination):
        if Path(destination) == target and ".restore-" in Path(source).name:
            raise ControllerCrash()
        return replace(source, destination)

    monkeypatch.setattr(backup.os, "replace", crash)
    with pytest.raises(ControllerCrash):
        backup.restore_backup_offline(runtime.store, saved.database_path, saved.manifest_path)
    barrier = target.parent / backup._UPGRADE_BARRIER_NAME
    payload = json.loads(barrier.read_text())
    assert Path(payload["staged_path"]).exists()
    assert Path(payload["rollback_path"]).exists()
    assert target.read_bytes() == before
    with pytest.raises(rt.PersistenceError, match="barrier"):
        rt.Runtime.at(runtime.store.root)


def test_explicit_hierarchy_then_physical_upgrade_retains_both_receipt_chains(tmp_path, monkeypatch):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    path = _exact_v4(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v4_evidence(path)
    backups = tmp_path / "backups"
    finite = backup.upgrade_v4_to_v5(path, backups, release_sha=release)
    hierarchy = backup.upgrade_v5_to_v6(path, backups, release_sha=release)
    assert (hierarchy.source_schema_version, hierarchy.target_schema_version) == (5, 6)
    retained = {
        Path(receipt_path): Path(receipt_path).read_bytes()
        for receipt in (finite, hierarchy)
        for receipt_path in (receipt.preflight_receipt_path, receipt.completion_receipt_path)
    }
    before = _full_v6(path)
    with pytest.raises(rt.ExecutiveSchemaUpgradeRequired, match="upgrade_v6_to_v7"):
        rt.RuntimeStore(path.parent, database_path=path)
    backup.verify_backup(path, expected_schema_version=6)
    physical = backup.upgrade_v6_to_v7(path, backups, release_sha=release)
    assert (physical.source_schema_version, physical.target_schema_version) == (6, 7)
    assert physical.pre_full_v6_content_digest == before == physical.post_full_v6_content_digest
    assert all(p.read_bytes() == body for p, body in retained.items())
    verified = backup.verify_backup(path, expected_schema_version=7)
    assert [(m.version, m.name) for m in verified.migrations][-2:] == [
        (6, "executive_nested_coordinator_contract"),
        (7, "executive_physical_resource_contract"),
    ]
    with backup._readonly_database(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM physical_resource_commitments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM physical_resource_demands").fetchone()[0] == 0
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='jobs_one_coordinator_per_step'"
        ).fetchone() is not None
    rt.RuntimeStore(path.parent, database_path=path, create=False, existing_writable=True)


def test_displaced_physical_v6_lineage_refuses_without_mutating_existing_store(tmp_path, monkeypatch):
    path = _exact_v4(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v4_evidence(path)
    legacy_vector = (
        rt._MIGRATIONS[4],
        (6, "executive_physical_resource_contract", rt._PHYSICAL_RESOURCE_SCHEMA_CANDIDATE),
    )
    with sqlite3.connect(path) as connection:
        for version, name, statements in legacy_vector:
            for statement in statements:
                connection.execute(statement)
            connection.execute("INSERT INTO schema_migrations VALUES(?,?,?,?)",
                               (version, name, rt._migration_checksum(statements), -101 * version))
    path.chmod(0o400)
    before = _file_set(path)
    original_connect = sqlite3.connect

    def immutable_only(database, *args, **kwargs):
        assert "mode=ro" in str(database) and "immutable=1" in str(database)
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(rt.sqlite3, "connect", immutable_only)
    with pytest.raises(rt.PersistenceError, match="migration 6 checksum/name"):
        rt.RuntimeStore(path.parent, database_path=path)
    assert _file_set(path) == before


def test_cli_source_alias_is_closed_and_cannot_conflict_with_transition():
    from scripts import executive_os_migrate as cli
    parser = cli._parser()
    base = ["--database", "/fixture/db", "--backup-directory", "/fixture/backups",
            "--release-sha", "a" * 40]
    for version in (3, 4, 5, 6):
        assert parser.parse_args([*base, "--from-version", str(version)]).from_version == version
    with pytest.raises(SystemExit):
        parser.parse_args([*base, "--from-version", "7"])
    with pytest.raises(SystemExit):
        parser.parse_args([*base, "--from-version", "5", "--transition", "v6-to-v7"])
