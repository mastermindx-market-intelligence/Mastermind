"""Synthetic-only evidence for the closed offline v5 -> v6 transition."""

from __future__ import annotations

import fcntl
import json
import sqlite3
from pathlib import Path

import pytest

from control_plane import executive_backup as backup
from control_plane import executive_runtime as runtime
from test_executive_backup import (
    _exact_v4,
    _populate_v4_evidence,
    _upgrade_test_release_and_census,
)


def _exact_v5(path: Path) -> Path:
    _exact_v4(path)
    _populate_v4_evidence(path)
    with sqlite3.connect(path) as connection:
        version, name, statements = runtime._MIGRATIONS[4]
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations VALUES(?,?,?,?)",
            (version, name, runtime._migration_checksum(statements), -5005),
        )
    return path


def _history(path: Path):
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT version,name,checksum,typeof(applied_at_ms),applied_at_ms "
            "FROM schema_migrations ORDER BY version"
        ).fetchall()


def _content(path: Path):
    with backup._readonly_database(path) as connection:
        return backup.full_v4_content_digest(connection)


@pytest.fixture
def source(tmp_path, monkeypatch):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v5(tmp_path / "runtime" / "executive.sqlite3")
    return database, release, tmp_path / "backups"


def _upgrade(source):
    database, release, destination = source
    return backup.upgrade_v5_to_v6(database, destination, release_sha=release)


def test_v6_upgrade_preserves_rows_history_and_verifiable_backups(source):
    database, release, _ = source
    before_content, before_history = _content(database), _history(database)
    inode = database.stat().st_ino
    receipt = _upgrade(source)
    assert isinstance(receipt, backup.SchemaUpgradeV5ToV6Receipt)
    assert (receipt.source_schema_version, receipt.target_schema_version) == (5, 6)
    assert receipt.release_sha == release
    assert receipt.database_identity["inode"] == inode == database.stat().st_ino
    assert receipt.pre_full_v4_content_digest == before_content
    assert receipt.post_full_v4_content_digest == before_content == _content(database)
    assert receipt.full_v4_content_equal is True
    assert _history(database)[:5] == before_history
    verified = backup.verify_backup(database, expected_schema_version=6)
    assert [m.version for m in verified.migrations] == [1, 2, 3, 4, 5, 6]
    assert verified.normalized_schema_digest == (
        "4ed21db1880afe43bdab58ea07da335c2db60a218ccdedee44eaefd1d2175c05"
    )
    for version in (5, 6):
        path = getattr(receipt, f"v{version}_backup_path")
        manifest = getattr(receipt, f"v{version}_backup_manifest_path")
        checked = backup.verify_backup(path, manifest, expected_schema_version=version)
        drill = backup.verify_restore_drill(path, manifest, expected_schema_version=version)
        assert checked.legacy_content_digest == drill.legacy_content_digest
        assert _content(Path(path)) == before_content
        assert _history(Path(path))[:5] == before_history
    completion = json.loads(Path(receipt.completion_receipt_path).read_text())
    assert (completion["source_schema_version"], completion["target_schema_version"]) == (5, 6)
    assert completion["full_v4_content_equal"] is True
    assert not (database.parent / backup._UPGRADE_BARRIER_NAME).exists()
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="already exists"):
        _upgrade(source)


@pytest.mark.parametrize("phase", [
    "exclusive_v5_verified",
    *[f"after_m6_statement:{i:02d}" for i in range(1, 8)],
    "after_m6_receipt", "before_v6_commit",
])
def test_precommit_fault_rolls_back_all_v6_ddl_and_receipt(source, monkeypatch, phase):
    database, _, _ = source
    before = backup.verify_backup(database, expected_schema_version=5).to_dict()
    history, content = _history(database), _content(database)

    reached = []

    def fail(observed):
        if observed == phase:
            reached.append(observed)
            raise RuntimeError("synthetic precommit fault")

    monkeypatch.setattr(backup, "_SCHEMA_UPGRADE_TEST_HOOK", fail)
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="rolled back"):
        _upgrade(source)
    assert backup.verify_backup(database, expected_schema_version=5).to_dict() == before
    assert reached == [phase]
    assert _history(database) == history
    assert _content(database) == content
    assert not (database.parent / backup._UPGRADE_BARRIER_NAME).exists()
    assert not (database.parent / backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME).exists()


@pytest.mark.parametrize("phase", [
    "after_v6_commit_before_checkpoint", "after_v6_checkpoint", "completion_persisted",
])
def test_postcommit_fault_retains_v6_and_quarantine(source, monkeypatch, phase):
    database, _, _ = source
    content = _content(database)

    def fail(observed):
        if observed == phase:
            raise RuntimeError("synthetic postcommit fault")

    monkeypatch.setattr(backup, "_SCHEMA_UPGRADE_TEST_HOOK", fail)
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="committed but completion failed"):
        _upgrade(source)
    assert _history(database)[-1][0] == 6
    assert _content(database) == content
    assert (database.parent / backup._UPGRADE_BARRIER_NAME).exists()
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="already exists"):
        _upgrade(source)


@pytest.mark.parametrize("target", ["source_backup", "target_backup", "migration5_timestamp", "completion"])
def test_final_tampering_keeps_quarantine(source, monkeypatch, target):
    database, _, _ = source

    def tamper(phase):
        if phase != "before_barrier_unlink":
            return
        preflight = database.parent / backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME
        completion = database.parent / backup._UPGRADE_V5_TO_V6_COMPLETION_NAME
        if target in {"source_backup", "target_backup"}:
            receipt = json.loads((preflight if target == "source_backup" else completion).read_text())
            key = "v5_backup" if target == "source_backup" else "v6_backup"
            with Path(receipt[key]["database_path"]).open("ab") as handle:
                handle.write(b"synthetic corruption")
        elif target == "migration5_timestamp":
            with sqlite3.connect(database) as connection:
                connection.execute("UPDATE schema_migrations SET applied_at_ms=-5006 WHERE version=5")
        else:
            completion.write_text("{}")

    monkeypatch.setattr(backup, "_SCHEMA_UPGRADE_TEST_HOOK", tamper)
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="committed but completion failed"):
        _upgrade(source)
    assert (database.parent / backup._UPGRADE_BARRIER_NAME).exists()


def test_migration5_timestamp_change_inside_transaction_rolls_back(source, monkeypatch):
    database, _, _ = source
    history = _history(database)
    migrations = list(backup._MIGRATIONS)
    version, name, statements = migrations[5]
    migrations[5] = (version, name, (*statements,
        "UPDATE schema_migrations SET applied_at_ms=-5006 WHERE version=5"))
    monkeypatch.setattr(backup, "_MIGRATIONS", tuple(migrations))
    with pytest.raises(backup.ExecutiveSchemaUpgradeError, match="rolled back"):
        _upgrade(source)
    assert _history(database) == history
    assert not (database.parent / backup._UPGRADE_BARRIER_NAME).exists()


@pytest.mark.parametrize("occupied", ["marker", "lock"])
def test_active_service_refuses_before_barrier_creation(source, occupied):
    database, _, _ = source
    lock = database.parent / backup.DEFAULT_SERVICE_LOCK_NAME
    if occupied == "marker":
        (database.parent / backup.DEFAULT_SERVICE_MARKER_NAME).touch(mode=0o600)
    with lock.open("rb") as handle:
        if occupied == "lock":
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(backup.RestoreSafetyError):
            _upgrade(source)
    assert not (database.parent / backup._UPGRADE_BARRIER_NAME).exists()
    assert _history(database)[-1][0] == 5


def test_v4_upgrade_receipts_survive_v5_to_v6(tmp_path, monkeypatch):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v4(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v4_evidence(database)
    first = backup.upgrade_v4_to_v5(database, tmp_path / "backups", release_sha=release)
    artifacts = {Path(p): Path(p).read_bytes() for p in
        (first.preflight_receipt_path, first.completion_receipt_path)}
    _upgrade((database, release, tmp_path / "backups"))
    assert all(p.read_bytes() == content for p, content in artifacts.items())
    assert _history(database)[-1][0] == 6


def test_v4_is_not_accepted_as_v5_source(tmp_path, monkeypatch):
    release = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v4(tmp_path / "runtime" / "executive.sqlite3")
    before = database.read_bytes()
    with pytest.raises(backup.ExecutiveSchemaUpgradeError):
        _upgrade((database, release, tmp_path / "backups"))
    assert database.read_bytes() == before
    assert _history(database)[-1][0] == 4


def test_v6_exact_backup_refuses_unrecognized_schema_extension(source):
    database, _, _ = source
    _upgrade(source)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE INDEX unreviewed_extra_index ON jobs(status)")
    with pytest.raises(backup.BackupVerificationError, match="normalized schema"):
        backup.verify_backup(database, expected_schema_version=6)
