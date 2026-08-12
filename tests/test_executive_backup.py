"""Adversarial backup, restore-drill, and offline-restore tests."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import stat
from pathlib import Path

import pytest

from control_plane import executive_backup
from control_plane.executive_backup import (
    BackupVerificationError,
    RestoreRollbackError,
    RestoreSafetyError,
    create_online_backup,
    restore_backup_offline,
    verify_backup,
    verify_restore_drill,
)
from control_plane.executive_runtime import Runtime


def _runtime_with_claim(root: Path) -> tuple[Runtime, str]:
    runtime = Runtime.at(root)
    runtime.workers.register_worker(
        "worker-01",
        provider="codex",
        account_label="primary",
        worker_type="mock",
        capabilities=["code", "research"],
    )
    job = runtime.jobs.create_job("private objective that must not enter the manifest")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    return runtime, lease.lease_token


def _logical_state(runtime: Runtime) -> tuple[list[str], list[str], list[str]]:
    with runtime.store.read() as connection:
        workers = [
            str(row[0])
            for row in connection.execute("SELECT worker_id FROM workers ORDER BY 1")
        ]
        jobs = [
            str(row[0])
            for row in connection.execute("SELECT objective FROM jobs ORDER BY 1")
        ]
        attempts = [
            str(row[0])
            for row in connection.execute("SELECT attempt_id FROM attempts ORDER BY 1")
        ]
    return workers, jobs, attempts


def _private_copy(source: Path, destination: Path) -> Path:
    shutil.copyfile(source, destination)
    destination.chmod(0o600)
    return destination


def test_online_backup_is_private_verified_and_manifest_is_receipt_only(tmp_path):
    runtime, lease_token = _runtime_with_claim(tmp_path / "runtime")

    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    database = Path(receipt.database_path)
    manifest = Path(receipt.manifest_path)
    manifest_text = manifest.read_text(encoding="utf-8")
    payload = json.loads(manifest_text)

    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o600
    assert hashlib.sha256(database.read_bytes()).hexdigest() == receipt.database_sha256
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == receipt.manifest_sha256
    assert set(payload) == {
        "schema_version",
        "backup_id",
        "created_at",
        "runtime_schema_version",
        "database",
        "sqlite",
        "migrations",
    }
    assert payload["sqlite"]["integrity_check"] == "ok"
    assert payload["sqlite"]["foreign_key_check"] == "ok"
    assert "lease_token" not in manifest_text
    assert "private objective that must not enter the manifest" not in manifest_text
    if lease_token in manifest_text:
        pytest.fail("backup manifest contains a live lease credential")

    verified = verify_backup(database, manifest)
    assert verified.database_sha256 == receipt.database_sha256
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_verify_backup_rejects_manifest_tampering_and_public_permissions(tmp_path):
    runtime, _lease_token = _runtime_with_claim(tmp_path / "runtime")
    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    database = Path(receipt.database_path)
    manifest = Path(receipt.manifest_path)

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["unexpected"] = "field"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    manifest.chmod(0o600)
    with pytest.raises(BackupVerificationError, match="unknown or missing"):
        verify_backup(database, manifest)

    symlink = tmp_path / "linked-backup.sqlite3"
    symlink.symlink_to(database)
    with pytest.raises(BackupVerificationError, match="single-link regular file"):
        verify_backup(symlink)

    database.chmod(0o644)
    with pytest.raises(BackupVerificationError, match="group or other"):
        verify_backup(database)


def test_verify_backup_rejects_unknown_migration_and_foreign_key_drift(tmp_path):
    runtime, _lease_token = _runtime_with_claim(tmp_path / "runtime")
    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    source = Path(receipt.database_path)

    migration_drift = _private_copy(source, tmp_path / "migration-drift.sqlite3")
    with sqlite3.connect(migration_drift) as connection:
        connection.execute("UPDATE schema_migrations SET checksum='not-known-to-code'")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    with pytest.raises(
        BackupVerificationError, match="migrations do not exactly match"
    ):
        verify_backup(migration_drift)

    foreign_key_drift = _private_copy(source, tmp_path / "foreign-key-drift.sqlite3")
    with sqlite3.connect(foreign_key_drift) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("UPDATE attempts SET worker_id='missing-worker'")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    with pytest.raises(BackupVerificationError, match="foreign_key_check"):
        verify_backup(foreign_key_drift)


def test_restore_drill_uses_an_isolated_copy_and_leaves_live_state_unchanged(tmp_path):
    runtime, _lease_token = _runtime_with_claim(tmp_path / "runtime")
    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    before = _logical_state(runtime)

    drill = verify_restore_drill(receipt.database_path, receipt.manifest_path)

    assert drill.database_sha256 == receipt.database_sha256
    assert drill.integrity_check == "ok"
    assert drill.foreign_key_check == "ok"
    assert drill.migration_versions == (1,)
    assert _logical_state(runtime) == before


def test_offline_restore_atomically_replaces_live_database_and_keeps_rollback(tmp_path):
    runtime, _lease_token = _runtime_with_claim(tmp_path / "runtime")
    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    backup_state = _logical_state(runtime)
    runtime.workers.register_worker(
        "worker-02",
        provider="codex",
        account_label="secondary",
        worker_type="mock",
    )
    runtime.jobs.create_job("state created after backup")
    assert _logical_state(runtime) != backup_state

    restored = restore_backup_offline(
        runtime.store,
        receipt.database_path,
        receipt.manifest_path,
    )

    assert restored.restored_sha256 == receipt.database_sha256
    assert restored.manifest_sha256 == receipt.manifest_sha256
    rollback = Path(restored.rollback_database_path)
    assert rollback.is_file()
    assert stat.S_IMODE(rollback.stat().st_mode) == 0o600
    assert hashlib.sha256(rollback.read_bytes()).hexdigest() == restored.rollback_sha256
    assert all(Path(path).is_file() for path in restored.rollback_sidecar_paths)
    assert _logical_state(Runtime.at(tmp_path / "runtime")) == backup_state


def test_offline_restore_refuses_service_marker_and_held_lock_without_mutation(
    tmp_path,
):
    runtime, _lease_token = _runtime_with_claim(tmp_path / "runtime")
    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    runtime.jobs.create_job("state that must survive refused restores")
    expected = _logical_state(runtime)
    runtime_directory = runtime.store.path.parent
    marker = runtime_directory / executive_backup.DEFAULT_SERVICE_MARKER_NAME
    lock = runtime_directory / executive_backup.DEFAULT_SERVICE_LOCK_NAME

    marker.write_text("running\n", encoding="utf-8")
    marker.chmod(0o600)
    with pytest.raises(RestoreSafetyError, match="service marker exists"):
        restore_backup_offline(
            runtime.store, receipt.database_path, receipt.manifest_path
        )
    assert _logical_state(runtime) == expected
    marker.unlink()

    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RestoreSafetyError, match="service lock is held"):
            restore_backup_offline(
                runtime.store, receipt.database_path, receipt.manifest_path
            )
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    assert _logical_state(runtime) == expected


def test_failed_post_swap_verification_restores_previous_database(
    tmp_path, monkeypatch
):
    runtime, _lease_token = _runtime_with_claim(tmp_path / "runtime")
    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    runtime.workers.register_worker(
        "worker-02",
        provider="codex",
        account_label="secondary",
        worker_type="mock",
    )
    runtime.jobs.create_job("state that the automatic rollback must preserve")
    expected = _logical_state(runtime)
    original_verify = executive_backup._verify_database_file
    live_database = runtime.store.path.resolve()

    def fail_live_verification(path):
        if Path(path).resolve() == live_database:
            raise BackupVerificationError("simulated post-swap verification failure")
        return original_verify(path)

    monkeypatch.setattr(
        executive_backup, "_verify_database_file", fail_live_verification
    )

    with pytest.raises(
        RestoreRollbackError, match="previous database bytes were restored"
    ):
        restore_backup_offline(
            runtime.store, receipt.database_path, receipt.manifest_path
        )

    assert _logical_state(Runtime.at(tmp_path / "runtime")) == expected


def test_failed_main_replace_restores_sidecars_removed_before_swap(
    tmp_path, monkeypatch
):
    runtime, _lease_token = _runtime_with_claim(tmp_path / "runtime")
    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    runtime.jobs.create_job("state and sidecars that must survive failed replacement")
    expected = _logical_state(runtime)
    target = runtime.store.path.resolve()
    journal = target.with_name(target.name + "-journal")
    journal_bytes = b"phase1c rollback sidecar fixture\n"
    journal.write_bytes(journal_bytes)
    journal.chmod(0o600)
    original_replace = executive_backup.os.replace
    failed = False
    replacements: list[tuple[Path, Path]] = []

    def fail_staged_main_replace(source, destination):
        nonlocal failed
        source_path = Path(source)
        destination_path = Path(destination)
        replacements.append((source_path, destination_path))
        if (
            not failed
            and destination_path == target
            and ".restore-" in source_path.name
        ):
            failed = True
            raise OSError("simulated main database replace failure")
        return original_replace(source, destination)

    monkeypatch.setattr(executive_backup.os, "replace", fail_staged_main_replace)

    with pytest.raises(
        RestoreRollbackError, match="previous database bytes were restored"
    ):
        restore_backup_offline(
            runtime.store, receipt.database_path, receipt.manifest_path
        )

    assert failed is True
    assert any(
        destination == journal and source.name.endswith("-journal")
        for source, destination in replacements
    )
    assert _logical_state(Runtime.at(tmp_path / "runtime")) == expected
