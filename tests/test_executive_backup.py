"""Adversarial backup, restore-drill, and offline-restore tests."""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane import executive_backup
from control_plane import executive_runtime
from control_plane.executive_backup import (
    BackupVerificationError,
    ExecutiveSchemaUpgradeError,
    RestoreRollbackError,
    RestoreSafetyError,
    create_offline_backup,
    create_online_backup,
    restore_backup_offline,
    upgrade_v3_to_v4,
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


def _exact_v3(path: Path) -> Path:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
              version INTEGER PRIMARY KEY,
              name TEXT NOT NULL UNIQUE,
              checksum TEXT NOT NULL,
              applied_at_ms INTEGER NOT NULL
            )
            """
        )
        for version, name, statements in executive_runtime._MIGRATIONS[:3]:
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?,?)",
                (
                    version,
                    name,
                    executive_runtime._migration_checksum(statements),
                    -version,
                ),
            )
        connection.commit()
    finally:
        connection.close()
    path.chmod(0o600)
    return path


def _populate_v3_ohf_evidence(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN")
        connection.execute(
            """
            INSERT INTO workers(
              worker_id,provider,account_label,worker_type,last_seen_at_ms,
              created_at_ms,updated_at_ms
            ) VALUES('worker-v3','codex','company','fixture',1,1,1)
            """
        )
        connection.execute(
            """
            INSERT INTO worker_quota_classes(
              worker_id,quota_class,status,provider,last_seen_at_ms,
              created_at_ms,updated_at_ms
            ) VALUES('worker-v3','default','ERROR','codex',1,1,7)
            """
        )
        connection.execute(
            """
            INSERT INTO jobs(
              job_id,objective,department,status,assigned_worker_id,
              assigned_quota_class,current_attempt_id,authority_level,
              constraints_json,requested_authorities_json,authority_policy_hash,
              available_at_ms,created_at_ms,updated_at_ms,attempt_count,attempt_limit,
              root_job_id,depth
            ) VALUES(
              'JOB-V3','preserve payload','fixture','LOST','worker-v3','default',
              'ATT-V3','A0','{}','["READ"]',
              'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
              1,1,7,1,2,'JOB-V3',0
            )
            """
        )
        connection.execute(
            """
            INSERT INTO attempts(
              attempt_id,job_id,attempt_number,worker_id,quota_class,status,
              fence_generation,authority_policy_hash,lease_owner,
              lease_expires_at_ms,heartbeat_at_ms,started_at_ms,created_at_ms,
              updated_at_ms,finished_at_ms,execution_mode,
              requested_execution_profile_json,requested_execution_profile_digest
            ) VALUES(
              'ATT-V3','JOB-V3',1,'worker-v3','default','LOST',1,
              'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
              'fixture',1,1,1,1,7,7,'OPERATOR_HARNESS','{}','profile'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO harness_session_epochs(
              session_epoch_id,attempt_id,worker_id,epoch_number,
              provider_session_id,state,created_at_ms,ended_at_ms,abandonment_class
            ) VALUES('EPOCH-V3','ATT-V3','worker-v3',1,'SESSION-V3',
                     'ABANDONED',1,7,'RESTORE')
            """
        )
        connection.execute(
            """
            INSERT INTO process_generations(
              process_generation_id,session_epoch_id,worker_id,
              provider_session_id,generation_number,started_at_ms,
              ended_at_ms,termination_class,executive_writer_held,
              provider_writer_state,created_at_ms
            ) VALUES('GEN-V3','EPOCH-V3','worker-v3','SESSION-V3',1,1,7,
                     'RESTORE',0,'RELEASED',1)
            """
        )
        connection.execute(
            """
            INSERT INTO events(
              aggregate_type,aggregate_id,sequence,event_type,command_id,actor,
              job_id,attempt_id,worker_id,quota_class,payload_json,created_at_ms
            ) VALUES('attempt','ATT-V3',1,'OHF_RESTORE_INVALIDATED',
                     'ohf-restore:ATT-V3','restore','JOB-V3','ATT-V3',
                     'worker-v3','default','{"transaction_group":"TX-9"}',7)
            """
        )
        connection.commit()
    finally:
        connection.close()


def _upgrade_census_material(
    database: Path, lock: Path, barrier: Path, lock_fd: int
) -> dict:
    return {
        "schema_version": executive_backup.UPGRADE_CENSUS_SCHEMA,
        "control_uids": sorted(
            set(
                os.getresuid()
                if hasattr(os, "getresuid")
                else (os.getuid(), os.geteuid())
            )
        ),
        "upgrader_pid": os.getpid(),
        "inspected_paths": [
            str(database),
            *(str(database.with_name(database.name + suffix)) for suffix in ("-wal", "-shm", "-journal")),
            str(lock),
            str(barrier),
        ],
        "process_sensor": {
            "binary": "/bin/ps",
            "upgrader_observed": True,
            "sensor_child_observed": True,
        },
        "file_sensor": {
            "binary": "/usr/sbin/lsof",
            "held_lock_observed": True,
        },
        "processes": [],
        "open_files": [
            {
                "pid": os.getpid(),
                "uid": os.geteuid(),
                "fd": str(lock_fd),
                "path": str(lock),
            }
        ],
    }


def _upgrade_test_release_and_census(monkeypatch, tmp_path: Path) -> str:
    release_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    release_root = tmp_path / release_sha
    release_root.mkdir(mode=0o700)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(mode=0o700, exist_ok=True)
    lock = runtime_root / executive_backup.DEFAULT_SERVICE_LOCK_NAME
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    monkeypatch.setattr(
        executive_backup,
        "_SCHEMA_UPGRADE_RELEASE_OBSERVER",
        lambda: {
            "release_root": str(release_root),
            "release_sha": release_sha,
            "release_tree_sha": "b" * 40,
            "release_manifest_sha256": "c" * 64,
        },
    )

    def census(database, lock, barrier, lock_fd):
        return _upgrade_census_material(database, lock, barrier, lock_fd)

    monkeypatch.setattr(
        executive_backup, "_SCHEMA_UPGRADE_CENSUS_OBSERVER", census
    )
    return release_sha


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


def test_frozen_schema_digests_match_test_only_v3_and_v4_references():
    assert executive_backup._NORMALIZED_SCHEMA_DIGESTS == {
        3: executive_backup._reference_normalized_schema_digest_for_tests(3),
        4: executive_backup._reference_normalized_schema_digest_for_tests(4),
    }


def test_exact_v3_offline_backup_and_drill_preserve_full_legacy_projection(tmp_path):
    source = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v3_ohf_evidence(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    source_verified = verify_backup(source, expected_schema_version=3)

    receipt = create_offline_backup(
        source, tmp_path / "backups", expected_schema_version=3
    )
    backup_verified = verify_backup(
        receipt.database_path,
        receipt.manifest_path,
        expected_schema_version=3,
    )
    drill = verify_restore_drill(
        receipt.database_path,
        receipt.manifest_path,
        expected_schema_version=3,
    )

    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert source_verified.normalized_schema_digest == receipt.normalized_schema_digest
    assert source_verified.legacy_content_digest == receipt.legacy_content_digest
    assert backup_verified.legacy_content_digest == drill.legacy_content_digest
    assert backup_verified.normalized_schema_digest == drill.normalized_schema_digest
    assert drill.runtime_schema_version == 3
    assert drill.migration_versions == (1, 2, 3)
    assert not any(
        (source.with_name(source.name + suffix)).exists()
        for suffix in ("-wal", "-shm", "-journal")
    )


def test_exact_v3_verifier_refuses_v4_ddl_leak_and_offline_sidecar(tmp_path):
    source = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    with sqlite3.connect(source) as connection:
        connection.execute("ALTER TABLE jobs ADD COLUMN orchestration_role TEXT")
        connection.commit()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(BackupVerificationError, match="normalized schema"):
        verify_backup(source, expected_schema_version=3)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash

    clean = _exact_v3(tmp_path / "clean" / "executive.sqlite3")
    wal = clean.with_name(clean.name + "-wal")
    wal.write_bytes(b"uncheckpointed")
    wal.chmod(0o600)
    with pytest.raises(BackupVerificationError, match="sidecars"):
        create_offline_backup(clean, tmp_path / "backups", expected_schema_version=3)


@pytest.mark.parametrize(
    "payload",
    [
        {"requeue_kind": "TX9_DETACHED", "tx9_evidence_digest": "a" * 64},
        {"orchestration_role": "plan", "cycle_command_id": "coo-cycle:root:x"},
    ],
)
def test_exact_v3_refuses_v4_semantics_hidden_in_legacy_event_types(tmp_path, payload):
    source = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    with sqlite3.connect(source) as connection:
        connection.execute(
            """
            INSERT INTO events(
              aggregate_type,aggregate_id,sequence,event_type,command_id,actor,
                  payload_json,created_at_ms
                ) VALUES('job','JOB-X',1,'JOB_REQUEUED','legacy-command','coo',
                         ?,1)
            """,
            (json.dumps(payload, sort_keys=True, separators=(",", ":")),),
        )
        connection.commit()
    with pytest.raises(BackupVerificationError, match="v4 semantics"):
        verify_backup(source, expected_schema_version=3)


@pytest.mark.parametrize(
    "event_type",
    [
        "COO_PLAN_ADMITTED",
        "COO_AGGREGATION_HANDOFF_READY",
        "COO_CYCLE_BLOCKED",
        "ORCHESTRATION_WORK_ADMITTED",
        "ORCHESTRATION_ROLE_RESULT_SEALED",
    ],
)
def test_exact_v3_refuses_every_closed_v4_event_type(tmp_path, event_type):
    source = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    with sqlite3.connect(source) as connection:
        connection.execute(
            """
            INSERT INTO events(
              aggregate_type,aggregate_id,sequence,event_type,command_id,actor,
              payload_json,created_at_ms
            ) VALUES('job','JOB-X',1,?,'neutral-command','coo','{}',1)
            """,
            (event_type,),
        )
        connection.commit()
    with pytest.raises(BackupVerificationError, match="Phase 1F-C Event"):
        verify_backup(source, expected_schema_version=3)


def test_explicit_upgrade_preserves_populated_v3_and_writes_completion(
    tmp_path, monkeypatch
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v3_ohf_evidence(database)
    before = verify_backup(database, expected_schema_version=3)

    receipt = upgrade_v3_to_v4(
        database, tmp_path / "backups", release_sha=release_sha
    )

    after = verify_backup(database, expected_schema_version=4)
    assert receipt.pre_v4_legacy_content_digest == before.legacy_content_digest
    assert receipt.post_v4_legacy_content_digest == before.legacy_content_digest
    assert after.legacy_content_digest == before.legacy_content_digest
    assert receipt.release_sha == release_sha
    assert not (database.parent / "executive-schema-upgrade.in-progress.json").exists()
    preflight = json.loads(Path(receipt.preflight_receipt_path).read_text())
    completion = json.loads(Path(receipt.completion_receipt_path).read_text())
    assert preflight["quiesce_writer_census"]["processes"] == []
    assert preflight["quiesce_writer_census_digest"] == hashlib.sha256(
        json.dumps(
            preflight["quiesce_writer_census"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert completion["legacy_content_equal"] is True
    assert completion["release_sha"] == release_sha
    assert verify_restore_drill(
        receipt.v4_backup_path, expected_schema_version=4
    ).legacy_content_digest == before.legacy_content_digest


@pytest.mark.parametrize(
    "phase",
    [
        "exclusive_v3_verified",
        *(f"after_m4_statement:{ordinal:02d}" for ordinal in range(1, len(executive_runtime._MIGRATIONS[3][2]) + 1)),
        "after_m4_receipt",
        "before_v4_commit",
    ],
)
def test_precommit_upgrade_faults_rollback_to_preflight_exact_v3(
    tmp_path, monkeypatch, phase
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v3_ohf_evidence(database)
    before = verify_backup(database, expected_schema_version=3)

    def fail(observed):
        if observed == phase:
            raise RuntimeError("injected precommit fault")

    monkeypatch.setattr(executive_backup, "_SCHEMA_UPGRADE_TEST_HOOK", fail)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="rolled back"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    after = verify_backup(database, expected_schema_version=3)
    assert after.to_dict() == before.to_dict()
    assert not (database.parent / "executive-schema-upgrade.in-progress.json").exists()
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version=4"
        ).fetchone()[0] == 0


def test_rollback_guard_accepts_logically_exact_v3_after_physical_header_rewrite(
    tmp_path, monkeypatch
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v3_ohf_evidence(database)
    before = verify_backup(database, expected_schema_version=3)

    def fault(phase):
        if phase == "before_v4_commit":
            raise RuntimeError("force transactional rollback")
        if phase == "after_precommit_rollback_before_guard":
            # SQLite's user-version header is outside the commissioned logical
            # projection.  A checkpoint/rollback may lawfully rewrite physical
            # bytes while preserving the same v3 authority and evidence.
            with database.open("r+b") as handle:
                handle.seek(60)
                handle.write((7).to_bytes(4, "big"))
                handle.flush()
                os.fsync(handle.fileno())

    monkeypatch.setattr(executive_backup, "_SCHEMA_UPGRADE_TEST_HOOK", fault)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="rolled back"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    after = verify_backup(database, expected_schema_version=3)
    assert after.normalized_schema_digest == before.normalized_schema_digest
    assert after.legacy_content_digest == before.legacy_content_digest
    assert after.database_sha256 != before.database_sha256
    assert not (database.parent / "executive-schema-upgrade.in-progress.json").exists()


def test_preflight_payload_drift_quarantines_and_keeps_barrier(tmp_path, monkeypatch):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v3_ohf_evidence(database)

    def mutate(phase):
        if phase == "preflight_persisted":
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE jobs SET objective='same id changed bytes' WHERE job_id='JOB-V3'"
                )
                connection.commit()

    monkeypatch.setattr(executive_backup, "_SCHEMA_UPGRADE_TEST_HOOK", mutate)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="barrier remains"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    assert (database.parent / "executive-schema-upgrade.in-progress.json").is_file()


@pytest.mark.parametrize("target", ["barrier", "preflight"])
@pytest.mark.parametrize("action", ["remove", "replace"])
def test_upgrade_artifact_tamper_refuses_and_preserves_quarantine(
    tmp_path, monkeypatch, target, action
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v3_ohf_evidence(database)
    barrier = database.parent / "executive-schema-upgrade.in-progress.json"
    preflight = database.parent / "executive-schema-upgrade.preflight.json"

    def tamper(phase):
        if phase != "preflight_persisted":
            return
        selected = barrier if target == "barrier" else preflight
        selected.unlink()
        if action == "replace":
            selected.write_text("{}\n", encoding="utf-8")
            selected.chmod(0o600)

    monkeypatch.setattr(executive_backup, "_SCHEMA_UPGRADE_TEST_HOOK", tamper)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="barrier remains"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    assert os.path.lexists(barrier)
    verify_backup(database, expected_schema_version=3)


def test_writer_census_drift_before_begin_keeps_barrier(tmp_path, monkeypatch):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    calls = 0

    def changing(database, lock, barrier, lock_fd):
        nonlocal calls
        calls += 1
        value = _upgrade_census_material(database, lock, barrier, lock_fd)
        if calls >= 2:
            value["open_files"] = [
                {"pid": os.getpid(), "uid": os.geteuid(), "fd": "999u", "path": str(database)}
            ]
        return value

    monkeypatch.setattr(
        executive_backup, "_SCHEMA_UPGRADE_CENSUS_OBSERVER", changing
    )
    with pytest.raises(ExecutiveSchemaUpgradeError, match="barrier remains"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    assert (database.parent / "executive-schema-upgrade.in-progress.json").is_file()
    verify_backup(database, expected_schema_version=3)


def test_default_upgrade_census_requires_positive_process_and_lock_sentinels(
    tmp_path, monkeypatch
):
    database = tmp_path / "executive.sqlite3"
    lock = tmp_path / executive_backup.DEFAULT_SERVICE_LOCK_NAME
    barrier = tmp_path / "executive-schema-upgrade.in-progress.json"
    for path in (database, lock, barrier):
        path.write_bytes(b"fixture")
        path.chmod(0o600)
    descriptor = os.open(lock, os.O_RDONLY)
    sensor_pid = os.getpid() + 100_000
    uids = (
        os.getresuid()
        if hasattr(os, "getresuid")
        else (os.getuid(), os.geteuid(), os.geteuid())
    )

    def observe(argv):
        if argv[0] == "/bin/ps":
            return (
                0,
                f"{os.getpid()} {uids[0]} {uids[1]} {uids[2]} python-upgrader\n"
                f"{sensor_pid} {uids[0]} {uids[1]} {uids[2]} /bin/ps\n",
                "",
                sensor_pid,
            )
        assert argv[0] == "/usr/sbin/lsof"
        return (
            0,
            f"p{os.getpid()}\nu{os.geteuid()}\nf{descriptor}u\nn{lock}\n",
            "",
            sensor_pid + 1,
        )

    monkeypatch.setattr(executive_backup, "_run_census_command", observe)
    try:
        material = executive_backup._upgrade_census(
            database, lock, barrier, descriptor
        )
    finally:
        os.close(descriptor)
    assert material["process_sensor"] == {
        "binary": "/bin/ps",
        "upgrader_observed": True,
        "sensor_child_observed": True,
    }
    assert material["file_sensor"]["held_lock_observed"] is True
    assert material["open_files"][0]["path"] == str(lock)


@pytest.mark.parametrize("uid_position", [0, 1, 2])
def test_default_upgrade_census_uses_saved_real_and_effective_uid_union(
    tmp_path, monkeypatch, uid_position
):
    database = tmp_path / "executive.sqlite3"
    lock = tmp_path / executive_backup.DEFAULT_SERVICE_LOCK_NAME
    barrier = tmp_path / "executive-schema-upgrade.in-progress.json"
    for path in (database, lock, barrier):
        path.write_bytes(b"fixture")
        path.chmod(0o600)
    descriptor = os.open(lock, os.O_RDONLY)
    sensor_pid = os.getpid() + 100_000
    control_uids = (101, 202, 303)
    foreign = [999, 999, 999]
    foreign[uid_position] = control_uids[uid_position]
    monkeypatch.setattr(
        executive_backup.os, "getresuid", lambda: control_uids, raising=False
    )

    def observe(argv):
        assert argv[0] == "/bin/ps"
        return (
            0,
            f"{os.getpid()} 101 999 999 python-upgrader\n"
            f"{sensor_pid} 999 202 999 /bin/ps\n"
            f"{sensor_pid + 1} {foreign[0]} {foreign[1]} {foreign[2]} writer\n",
            "",
            sensor_pid,
        )

    monkeypatch.setattr(executive_backup, "_run_census_command", observe)
    try:
        with pytest.raises(RestoreSafetyError, match="another control-UID"):
            executive_backup._default_upgrade_census(
                database, lock, barrier, descriptor
            )
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    ("ps_output", "lsof_status", "lsof_output", "match"),
    [
        ("", 0, "", "required sentinel"),
        ("own-only", 0, "", "required sentinel"),
        ("valid", 1, "", "file census failed"),
        ("valid", 0, "", "omitted or duplicated"),
        ("valid", 0, "foreign", "another open runtime file"),
        ("malformed", 0, "", "process census is malformed"),
    ],
)
def test_default_upgrade_census_refuses_blind_malformed_and_foreign_observations(
    tmp_path, monkeypatch, ps_output, lsof_status, lsof_output, match
):
    database = tmp_path / "executive.sqlite3"
    lock = tmp_path / executive_backup.DEFAULT_SERVICE_LOCK_NAME
    barrier = tmp_path / "executive-schema-upgrade.in-progress.json"
    for path in (database, lock, barrier):
        path.write_bytes(b"fixture")
        path.chmod(0o600)
    descriptor = os.open(lock, os.O_RDONLY)
    sensor_pid = os.getpid() + 100_000
    uid = os.geteuid()
    valid = (
        f"{os.getpid()} {uid} {uid} {uid} python-upgrader\n"
        f"{sensor_pid} {uid} {uid} {uid} /bin/ps\n"
    )
    ps_wire = {
        "": "",
        "own-only": f"{os.getpid()} {uid} {uid} {uid} python-upgrader\n",
        "valid": valid,
        "malformed": "not-a-closed-ps-row\n",
    }[ps_output]
    lsof_wire = {
        "": "",
        "foreign": f"p{os.getpid()}\nu{uid}\nf{descriptor}u\nn{database}\n",
    }[lsof_output]

    def observe(argv):
        if argv[0] == "/bin/ps":
            return 0, ps_wire, "", sensor_pid
        return lsof_status, lsof_wire, "", sensor_pid + 1

    monkeypatch.setattr(executive_backup, "_run_census_command", observe)
    try:
        with pytest.raises(RestoreSafetyError, match=match):
            executive_backup._default_upgrade_census(
                database, lock, barrier, descriptor
            )
    finally:
        os.close(descriptor)


def test_census_command_kills_child_on_timeout_and_refuses_oversized_output(
    monkeypatch,
):
    class FakeProcess:
        pid = 12345
        returncode = 0

        def __init__(self, *, timeout: bool):
            self.timeout = timeout
            self.killed = False
            self.waited = False

        def communicate(self, *, timeout):
            if self.timeout:
                raise subprocess.TimeoutExpired(["sensor"], timeout)
            return "x" * (512 * 1024 + 1), ""

        def kill(self):
            self.killed = True

        def wait(self):
            self.waited = True

    timed_out = FakeProcess(timeout=True)
    monkeypatch.setattr(
        executive_backup.subprocess, "Popen", lambda *args, **kwargs: timed_out
    )
    with pytest.raises(subprocess.TimeoutExpired):
        executive_backup._run_census_command(["sensor"])
    assert timed_out.killed is True
    assert timed_out.waited is True

    oversized = FakeProcess(timeout=False)
    monkeypatch.setattr(
        executive_backup.subprocess, "Popen", lambda *args, **kwargs: oversized
    )
    with pytest.raises(RestoreSafetyError, match="output exceeded"):
        executive_backup._run_census_command(["sensor"])


@pytest.mark.parametrize("target", ["database", "manifest"])
@pytest.mark.parametrize("action", ["remove", "tamper"])
def test_v3_backup_or_manifest_change_after_preflight_refuses_before_schema(
    tmp_path, monkeypatch, target, action
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    before = verify_backup(database, expected_schema_version=3)

    def mutate(phase):
        if phase != "preflight_persisted":
            return
        candidates = sorted((tmp_path / "backups").glob("executive-v3-*"))
        selected = next(
            path
            for path in candidates
            if (path.suffix == ".json") == (target == "manifest")
        )
        if action == "remove":
            selected.unlink()
        else:
            selected.write_bytes(selected.read_bytes() + b"tamper")
            selected.chmod(0o600)

    monkeypatch.setattr(executive_backup, "_SCHEMA_UPGRADE_TEST_HOOK", mutate)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="rolled back"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    after = verify_backup(database, expected_schema_version=3)
    assert after.legacy_content_digest == before.legacy_content_digest
    assert not (database.parent / "executive-schema-upgrade.in-progress.json").exists()


def test_service_marker_appearing_after_preflight_keeps_barrier_and_v3(
    tmp_path, monkeypatch
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    marker = database.parent / executive_backup.DEFAULT_SERVICE_MARKER_NAME

    def appear(phase):
        if phase == "preflight_persisted":
            marker.write_text("late service\n", encoding="utf-8")
            marker.chmod(0o600)

    monkeypatch.setattr(executive_backup, "_SCHEMA_UPGRADE_TEST_HOOK", appear)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="barrier remains"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    verify_backup(database, expected_schema_version=3)
    assert (database.parent / "executive-schema-upgrade.in-progress.json").is_file()


def test_missing_canonical_service_lock_refuses_without_mutation(tmp_path, monkeypatch):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    lock = database.parent / executive_backup.DEFAULT_SERVICE_LOCK_NAME
    lock.unlink()
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    with pytest.raises(RestoreSafetyError, match="missing"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert sorted(path.name for path in database.parent.iterdir()) == [database.name]


def test_canonical_lock_name_swap_during_acquisition_refuses_before_barrier(
    tmp_path, monkeypatch
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    lock = database.parent / executive_backup.DEFAULT_SERVICE_LOCK_NAME
    displaced = lock.with_name(lock.name + ".displaced")
    original_flock = executive_backup.fcntl.flock
    swapped = False

    def swap_after_lock(descriptor, operation):
        nonlocal swapped
        result = original_flock(descriptor, operation)
        if operation & fcntl.LOCK_EX and not swapped:
            swapped = True
            lock.rename(displaced)
            lock.write_bytes(b"")
            lock.chmod(0o600)
        return result

    monkeypatch.setattr(executive_backup.fcntl, "flock", swap_after_lock)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    with pytest.raises(RestoreSafetyError, match="changed during acquisition"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert not (database.parent / "executive-schema-upgrade.in-progress.json").exists()


def test_upgrade_refuses_service_marker_and_held_canonical_lock_without_barrier(
    tmp_path, monkeypatch
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    marker = database.parent / executive_backup.DEFAULT_SERVICE_MARKER_NAME
    barrier = database.parent / "executive-schema-upgrade.in-progress.json"
    marker.write_text("running\n", encoding="utf-8")
    marker.chmod(0o600)
    with pytest.raises(RestoreSafetyError, match="service marker exists"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    assert not os.path.lexists(barrier)
    marker.unlink()

    lock = database.parent / executive_backup.DEFAULT_SERVICE_LOCK_NAME
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RestoreSafetyError, match="service lock is held"):
            upgrade_v3_to_v4(
                database, tmp_path / "backups", release_sha=release_sha
            )
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    assert not os.path.lexists(barrier)


@pytest.mark.parametrize(
    "phase", ["after_v4_commit_before_checkpoint", "after_v4_checkpoint", "completion_persisted"]
)
def test_postcommit_fault_keeps_forward_fix_barrier(tmp_path, monkeypatch, phase):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v3_ohf_evidence(database)

    def fail(observed):
        if observed == phase:
            raise RuntimeError("injected postcommit fault")

    monkeypatch.setattr(executive_backup, "_SCHEMA_UPGRADE_TEST_HOOK", fail)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="forward fix"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    assert (database.parent / "executive-schema-upgrade.in-progress.json").is_file()


@pytest.mark.parametrize("failure", ["v4_backup", "v4_drill", "v4_checkpoint"])
def test_postcommit_backup_drill_and_checkpoint_failures_keep_barrier(
    tmp_path, monkeypatch, failure
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v3_ohf_evidence(database)
    original_backup = executive_backup.create_offline_backup
    original_drill = executive_backup.verify_restore_drill
    original_checkpoint = executive_backup._checkpoint_quiesced_wal
    checkpoint_calls = 0

    def backup(*args, **kwargs):
        if failure == "v4_backup" and kwargs.get("expected_schema_version") == 4:
            raise BackupVerificationError("injected v4 backup failure")
        return original_backup(*args, **kwargs)

    def drill(*args, **kwargs):
        if failure == "v4_drill" and kwargs.get("expected_schema_version") == 4:
            raise BackupVerificationError("injected v4 drill failure")
        return original_drill(*args, **kwargs)

    def checkpoint(path):
        nonlocal checkpoint_calls
        checkpoint_calls += 1
        if failure == "v4_checkpoint" and checkpoint_calls == 2:
            raise RestoreSafetyError("injected postcommit checkpoint failure")
        return original_checkpoint(path)

    monkeypatch.setattr(executive_backup, "create_offline_backup", backup)
    monkeypatch.setattr(executive_backup, "verify_restore_drill", drill)
    monkeypatch.setattr(executive_backup, "_checkpoint_quiesced_wal", checkpoint)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="forward fix"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    assert (database.parent / "executive-schema-upgrade.in-progress.json").is_file()


@pytest.mark.parametrize("target", ["authoritative", "backup", "manifest"])
def test_completion_hook_tamper_revalidates_all_v4_evidence_before_unlink(
    tmp_path, monkeypatch, target
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v3_ohf_evidence(database)

    def tamper(phase):
        if phase != "completion_persisted":
            return
        if target == "authoritative":
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE schema_migrations SET applied_at_ms=applied_at_ms+1 WHERE version=4"
                )
                connection.commit()
            return
        candidates = sorted((tmp_path / "backups").glob("executive-v4-*"))
        selected = next(
            path
            for path in candidates
            if (path.suffix == ".json") == (target == "manifest")
        )
        selected.write_bytes(selected.read_bytes() + b"tamper")
        selected.chmod(0o600)

    monkeypatch.setattr(executive_backup, "_SCHEMA_UPGRADE_TEST_HOOK", tamper)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="forward fix"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    assert (database.parent / "executive-schema-upgrade.in-progress.json").is_file()


@pytest.mark.parametrize(
    "target",
    ["authoritative", "backup", "manifest", "marker", "barrier", "completion"],
)
def test_pre_unlink_recheck_catches_late_service_or_artifact_tamper(
    tmp_path, monkeypatch, target
):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    _populate_v3_ohf_evidence(database)
    marker = database.parent / executive_backup.DEFAULT_SERVICE_MARKER_NAME
    barrier = database.parent / "executive-schema-upgrade.in-progress.json"
    completion = database.parent / executive_backup._UPGRADE_COMPLETION_NAME

    def tamper(phase):
        if phase != "before_barrier_unlink":
            return
        if target == "authoritative":
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE schema_migrations "
                    "SET applied_at_ms=applied_at_ms+1 WHERE version=4"
                )
                connection.commit()
            return
        if target in {"backup", "manifest"}:
            candidates = sorted((tmp_path / "backups").glob("executive-v4-*"))
            selected = next(
                path
                for path in candidates
                if (path.suffix == ".json") == (target == "manifest")
            )
            selected.write_bytes(selected.read_bytes() + b"tamper")
            selected.chmod(0o600)
            return
        selected = {"marker": marker, "barrier": barrier, "completion": completion}[
            target
        ]
        selected.write_text("{}\n", encoding="utf-8")
        selected.chmod(0o600)

    monkeypatch.setattr(executive_backup, "_SCHEMA_UPGRADE_TEST_HOOK", tamper)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="forward fix"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    assert os.path.lexists(barrier)


def test_preflight_backup_mismatch_rolls_back_without_schema_touch(tmp_path, monkeypatch):
    release_sha = _upgrade_test_release_and_census(monkeypatch, tmp_path)
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    before = verify_backup(database, expected_schema_version=3)
    original = executive_backup.create_offline_backup

    def mismatch(*args, **kwargs):
        receipt = original(*args, **kwargs)
        if kwargs.get("expected_schema_version") == 3:
            return dataclasses.replace(receipt, legacy_content_digest="f" * 64)
        return receipt

    monkeypatch.setattr(executive_backup, "create_offline_backup", mismatch)
    with pytest.raises(ExecutiveSchemaUpgradeError, match="rolled back"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha=release_sha)
    after = verify_backup(database, expected_schema_version=3)
    assert after.legacy_content_digest == before.legacy_content_digest
    assert not (database.parent / "executive-schema-upgrade.in-progress.json").exists()


def test_upgrade_rejects_unproven_release_and_cli_is_directly_runnable(tmp_path):
    database = _exact_v3(tmp_path / "runtime" / "executive.sqlite3")
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    with pytest.raises(ExecutiveSchemaUpgradeError, match="installed release"):
        upgrade_v3_to_v4(database, tmp_path / "backups", release_sha="a" * 40)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert sorted(item.name for item in database.parent.iterdir()) == [database.name]

    script = Path(__file__).parents[1] / "scripts" / "executive_os_migrate.py"
    help_run = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )
    assert help_run.returncode == 0
    invalid = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )
    assert invalid.returncode == 2
    assert sorted(item.name for item in database.parent.iterdir()) == [database.name]


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
    assert drill.migration_versions == (1, 2, 3, 4)
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


def test_offline_restore_invalidates_ohf_on_staged_copy_before_swap(tmp_path):
    runtime, _lease_token = _runtime_with_claim(tmp_path / "runtime")
    with runtime.store.transaction() as connection:
        attempt = connection.execute("SELECT * FROM attempts").fetchone()
        connection.execute(
            "UPDATE attempts SET execution_mode='OPERATOR_HARNESS',requested_execution_profile_json='{}',requested_execution_profile_digest='digest' WHERE attempt_id=?",
            (attempt["attempt_id"],),
        )
        connection.execute(
            "INSERT INTO harness_session_epochs(session_epoch_id,attempt_id,worker_id,epoch_number,provider_session_id,state,created_at_ms) VALUES('epoch-1',?,?,1,'S1','CURRENT',1)",
            (attempt["attempt_id"], attempt["worker_id"]),
        )
        connection.execute(
            "INSERT INTO process_generations(process_generation_id,session_epoch_id,worker_id,provider_session_id,generation_number,started_at_ms,executive_writer_held,provider_writer_state,created_at_ms) VALUES('generation-1','epoch-1',?,'S1',1,1,1,'HELD',1)",
            (attempt["worker_id"],),
        )
    backup = create_online_backup(runtime.store, tmp_path / "backups")
    # Force a real replacement instead of same-file restoration while preserving
    # the rich active snapshot as the backup source.
    runtime.jobs.create_job("post-backup change")
    restored = restore_backup_offline(
        runtime.store, backup.database_path, backup.manifest_path
    )
    assert restored.ohf_invalidated_attempts == 1
    assert restored.source_backup_sha256 == backup.database_sha256
    assert restored.final_runtime_sha256 == restored.restored_sha256
    assert restored.final_runtime_sha256 != restored.source_backup_sha256
    with Runtime.at(tmp_path / "runtime").store.read() as connection:
        assert connection.execute(
            "SELECT status FROM attempts WHERE attempt_id=?",
            (attempt["attempt_id"],),
        ).fetchone()[0] == "LOST"
        assert connection.execute(
            "SELECT state FROM harness_session_epochs WHERE session_epoch_id='epoch-1'"
        ).fetchone()[0] == "ABANDONED"
        assert connection.execute(
            "SELECT executive_writer_held FROM process_generations WHERE process_generation_id='generation-1'"
        ).fetchone()[0] == 0


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


def test_offline_restore_cannot_bypass_upgrade_barrier_with_alternate_lock(
    tmp_path,
):
    runtime, _lease_token = _runtime_with_claim(tmp_path / "runtime")
    backup = create_online_backup(runtime.store, tmp_path / "backups")
    runtime.jobs.create_job("state retained behind upgrade quarantine")
    runtime_directory = runtime.store.path.parent
    barrier = runtime_directory / "executive-schema-upgrade.in-progress.json"
    barrier.write_text("{}\n", encoding="utf-8")
    barrier.chmod(0o600)

    def inventory():
        observed = {
            ".": (stat.S_IMODE(runtime_directory.stat().st_mode), None)
        }
        for path in sorted(runtime_directory.iterdir()):
            info = path.lstat()
            digest = (
                hashlib.sha256(path.read_bytes()).hexdigest()
                if stat.S_ISREG(info.st_mode)
                else None
            )
            observed[path.name] = (stat.S_IMODE(info.st_mode), digest)
        return observed

    before = inventory()
    with pytest.raises(RestoreSafetyError, match="upgrade barrier"):
        restore_backup_offline(
            runtime.store,
            backup.database_path,
            backup.manifest_path,
            service_marker_path=tmp_path / "decoy.running",
            service_lock_path=tmp_path / "decoy.lock",
        )
    assert inventory() == before


def test_offline_restore_rejects_noncanonical_lock_override_before_mutation(tmp_path):
    runtime, _lease_token = _runtime_with_claim(tmp_path / "runtime")
    backup = create_online_backup(runtime.store, tmp_path / "backups")
    runtime_directory = runtime.store.path.parent
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in runtime_directory.iterdir()
        if path.is_file()
    }
    with pytest.raises(RestoreSafetyError, match="service lock override"):
        restore_backup_offline(
            runtime.store,
            backup.database_path,
            backup.manifest_path,
            service_lock_path=tmp_path / "alternate-service.lock",
        )
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in runtime_directory.iterdir()
        if path.is_file()
    }
    assert after == before


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

    def fail_live_verification(path, **kwargs):
        if Path(path).resolve() == live_database:
            raise BackupVerificationError("simulated post-swap verification failure")
        return original_verify(path, **kwargs)

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
