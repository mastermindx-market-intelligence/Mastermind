"""Adversarial offline-restore assertions for OHF TX-9 staged invalidation."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from control_plane.executive_backup import create_online_backup, restore_backup_offline
from control_plane.executive_runtime import Runtime


def _active_ohf(runtime: Runtime) -> str:
    runtime.workers.register_worker(
        "worker-01", provider="codex", account_label="one", worker_type="test"
    )
    job = runtime.jobs.create_job("restore adversarial")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    aid = lease.attempt.attempt_id
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE attempts SET execution_mode='OPERATOR_HARNESS',requested_execution_profile_json='{}',requested_execution_profile_digest='digest' WHERE attempt_id=?",
            (aid,),
        )
        connection.execute(
            "INSERT INTO harness_session_epochs(session_epoch_id,attempt_id,worker_id,epoch_number,provider_session_id,state,created_at_ms) VALUES('epoch',?,?,1,'S1','CURRENT',1)",
            (aid, lease.attempt.worker_id),
        )
        connection.execute(
            "INSERT INTO process_generations(process_generation_id,session_epoch_id,worker_id,provider_session_id,generation_number,started_at_ms,executive_writer_held,provider_writer_state,created_at_ms) VALUES('generation','epoch',?,'S1',1,1,1,'HELD',1)",
            (lease.attempt.worker_id,),
        )
    return aid


def test_staged_tx9_leaves_main_file_self_contained_and_lifecycle_coherent(tmp_path):
    root = tmp_path / "runtime"
    runtime = Runtime.at(root)
    aid = _active_ohf(runtime)
    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    runtime.jobs.create_job("force a replacement")
    restored = restore_backup_offline(
        runtime.store, receipt.database_path, receipt.manifest_path
    )
    assert restored.source_backup_sha256 == receipt.database_sha256
    assert restored.final_runtime_sha256 == restored.restored_sha256
    assert restored.source_backup_sha256 != restored.final_runtime_sha256
    # A copy of only the replaced main DB must carry TX-9; it may not rely on WAL.
    main_only = tmp_path / "main-only.sqlite3"
    shutil.copyfile(runtime.store.path, main_only)
    with sqlite3.connect(main_only) as connection:
        assert (
            connection.execute(
                "SELECT status FROM attempts WHERE attempt_id=?", (aid,)
            ).fetchone()[0]
            == "LOST"
        )
        assert (
            connection.execute(
                "SELECT state FROM harness_session_epochs WHERE session_epoch_id='epoch'"
            ).fetchone()[0]
            == "ABANDONED"
        )
        assert (
            connection.execute(
                "SELECT executive_writer_held FROM process_generations WHERE process_generation_id='generation'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT status,held_attempt_id FROM worker_quota_classes WHERE worker_id='worker-01'"
            ).fetchone()[0]
            == "ERROR"
        )
    reopened = Runtime.at(root)
    assert reopened.attempts.get_attempt(aid).status.value == "LOST"  # type: ignore[union-attr]
