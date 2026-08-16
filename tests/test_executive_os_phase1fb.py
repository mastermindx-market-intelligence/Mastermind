from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

import control_plane.executive_runtime as executive_runtime
from control_plane.executive_backup import BackupVerificationError, verify_backup
from control_plane.executive_runtime import (
    JobPayload,
    JobStatus,
    Runtime,
    SCHEMA_VERSION,
    StateConflict,
    _MIGRATION_1,
)


def _register(runtime: Runtime, worker_id: str) -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=f"{worker_id}-account",
        worker_type="fixture",
        capabilities=["code", "research", "review"],
    )


def _complete(
    runtime: Runtime,
    job_id: str,
    worker_id: str,
    *,
    verdict: str = "",
) -> None:
    lease = runtime.attempts.claim_job(job_id, worker_id=worker_id)
    assert lease is not None
    runtime.jobs.complete_job(
        job_id,
        JobPayload(summary="fixture complete", current_state="complete", verdict=verdict),
    )


def _seed_v1_database(root: Path) -> Path:
    """Write a populated SCHEMA_VERSION 1 database the current code has never opened."""

    db_path = root / "data" / "control_plane" / "executive.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.parent.chmod(0o700)
    checksum = hashlib.sha256(
        "\n".join(statement.strip() for statement in _MIGRATION_1).encode("utf-8")
    ).hexdigest()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
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
        for statement in _MIGRATION_1:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version,name,checksum,applied_at_ms) VALUES(?,?,?,?)",
            (1, "executive_runtime_core", checksum, 1),
        )
        connection.execute(
            """
            INSERT INTO jobs(
              job_id,objective,department,priority,status,authority_level,
              constraints_json,requested_authorities_json,authority_policy_hash,
              allowed_write_paths_json,validation_commands_json,
              attempt_limit,available_at_ms,created_at_ms,updated_at_ms
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "JOB-001",
                "Legacy childless job",
                "general",
                0,
                "QUEUED",
                "A0",
                "{}",
                '["READ"]',
                "a" * 64,
                "[]",
                "[]",
                10,
                1,
                1,
                1,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    db_path.chmod(0o600)
    return db_path


def test_parent_child_fields_migrate_preserve_and_derive_root_depth(tmp_path):
    runtime = Runtime.at(tmp_path)
    parent = runtime.jobs.create_job("Parent container")
    child = runtime.jobs.create_job("Bounded child", parent_job_id=parent.job_id)

    assert parent.root_job_id == parent.job_id
    assert parent.parent_job_id is None
    assert parent.depth == 0
    assert child.parent_job_id == parent.job_id
    assert child.root_job_id == parent.job_id
    assert child.depth == 1
    assert child.owner_seat == "coo"
    assert child.escalation_target == "coo"
    assert child.business_impact == "routine"
    assert child.review_required is False
    assert child.reviews_job_id is None
    assert Runtime.at(tmp_path).jobs.get_job(child.job_id) == child
    with Runtime.at(tmp_path).store.read() as connection:
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()[0] == 2


def test_v1_populated_store_upgrades_to_v2_and_preserves_legacy_rows(tmp_path):
    db_path = _seed_v1_database(tmp_path)
    with sqlite3.connect(db_path) as connection:
        versions = [
            int(row[0])
            for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(jobs)")
        }
    assert versions == [1]
    assert "parent_job_id" not in columns

    runtime = Runtime.at(tmp_path)
    job = runtime.jobs.get_job("JOB-001")
    assert job is not None
    assert job.objective == "Legacy childless job"
    assert job.parent_job_id is None
    assert job.root_job_id == "JOB-001"
    assert job.depth == 0
    assert job.owner_seat == "coo"
    assert job.escalation_target == "coo"
    assert job.review_required is False
    assert SCHEMA_VERSION == 2
    with runtime.store.read() as connection:
        assert [
            int(row[0])
            for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")
        ] == [1, 2]


def test_opening_an_already_migrated_store_is_idempotent(tmp_path):
    first = Runtime.at(tmp_path)
    created = first.jobs.create_job("Once")
    second = Runtime.at(tmp_path)
    assert second.jobs.get_job(created.job_id) == first.jobs.get_job(created.job_id)
    with second.store.read() as connection:
        assert [
            int(row[0])
            for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")
        ] == [1, 2]


def test_v1_database_restored_into_new_code_keeps_legacy_childless_completion(tmp_path):
    _seed_v1_database(tmp_path)
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    job = runtime.jobs.get_job("JOB-001")
    assert job is not None
    assert runtime.broker.select_worker(job) is not None
    lease = runtime.attempts.claim_job(job.job_id, worker_id="worker-a")
    assert lease is not None
    completed = runtime.jobs.complete_job(
        job.job_id, JobPayload(summary="legacy complete", current_state="complete")
    )
    assert completed.status is JobStatus.COMPLETED
    with runtime.store.read() as connection:
        payload = json.loads(
            connection.execute(
                "SELECT result_json FROM jobs WHERE job_id=?", (job.job_id,)
            ).fetchone()[0]
        )
    assert "verdict" not in payload


def test_v1_backup_manifest_is_refused_by_v2_code(tmp_path):
    runtime = Runtime.at(tmp_path / "live")
    _register(runtime, "worker-a")
    runtime.jobs.create_job("Current")
    from control_plane.executive_backup import create_online_backup

    receipt = create_online_backup(runtime.store, tmp_path / "backups")
    manifest = Path(receipt.manifest_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["runtime_schema_version"] = 1
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    manifest.chmod(0o600)
    with pytest.raises(BackupVerificationError, match="runtime schema version"):
        verify_backup(receipt.database_path, receipt.manifest_path)


def test_parent_with_living_child_is_not_claimable_or_selectable(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    parent = runtime.jobs.create_job("Parent container")
    runtime.jobs.create_job("Living child", parent_job_id=parent.job_id)

    assert runtime.broker.select_worker(parent) is None
    with pytest.raises(StateConflict, match=r"child job\(s\) are living"):
        runtime.attempts.claim_job(parent.job_id)


def test_review_verdict_is_fail_closed(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    job = runtime.jobs.create_job("Review payload")
    lease = runtime.attempts.claim_job(job.job_id, worker_id="worker-a")
    assert lease is not None

    with pytest.raises(StateConflict, match="verdict"):
        runtime.jobs.complete_job(job.job_id, {"summary": "bad", "verdict": "defer"})


def test_same_worker_review_is_void_and_cannot_aggregate_parent(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    _register(runtime, "worker-b")
    parent = runtime.jobs.create_job("Parent container")
    child = runtime.jobs.create_job(
        "Review-required child", parent_job_id=parent.job_id, review_required=True
    )
    review = runtime.jobs.create_job(
        "Independent review slot", parent_job_id=parent.job_id, reviews_job_id=child.job_id
    )

    _complete(runtime, child.job_id, "worker-a")
    _complete(runtime, review.job_id, "worker-a", verdict="approve")
    review_event = runtime.events.list_events(job_id=review.job_id)[-1]
    assert review_event.payload["review"] == {
        "reviews_job_id": child.job_id,
        "status": "VOID",
        "reason": "review_not_independent",
        "voids": runtime.jobs.get_job(child.job_id).current_attempt_id,  # type: ignore[union-attr]
    }

    parent_lease = runtime.attempts.claim_job(parent.job_id, worker_id="worker-b")
    assert parent_lease is not None
    with pytest.raises(StateConflict, match="independent completed review"):
        runtime.jobs.complete_job(parent.job_id, JobPayload(summary="aggregate"))


def test_independent_approved_review_allows_parent_completion(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    _register(runtime, "worker-b")
    parent = runtime.jobs.create_job("Parent container")
    child = runtime.jobs.create_job(
        "Review-required child", parent_job_id=parent.job_id, review_required=True
    )
    review = runtime.jobs.create_job(
        "Independent review slot", parent_job_id=parent.job_id, reviews_job_id=child.job_id
    )

    _complete(runtime, child.job_id, "worker-a")
    _complete(runtime, review.job_id, "worker-b", verdict="approve")
    parent_lease = runtime.attempts.claim_job(parent.job_id, worker_id="worker-a")
    assert parent_lease is not None
    completed = runtime.jobs.complete_job(parent.job_id, JobPayload(summary="aggregate"))
    assert completed.status is JobStatus.COMPLETED


def test_review_pointer_and_parent_are_immutable(tmp_path):
    runtime = Runtime.at(tmp_path)
    parent = runtime.jobs.create_job("Parent")
    other = runtime.jobs.create_job("Other")
    child = runtime.jobs.create_job("Child", parent_job_id=parent.job_id)

    with runtime.store.transaction() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE jobs SET parent_job_id=? WHERE job_id=?",
                (other.job_id, child.job_id),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE jobs SET root_job_id=? WHERE job_id=?",
                (other.job_id, child.job_id),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE jobs SET depth=9 WHERE job_id=?", (child.job_id,)
            )


def test_hierarchy_loop_via_reparent_is_refused(tmp_path):
    runtime = Runtime.at(tmp_path)
    parent = runtime.jobs.create_job("Parent")
    child = runtime.jobs.create_job("Child", parent_job_id=parent.job_id)
    with runtime.store.transaction() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE jobs SET parent_job_id=? WHERE job_id=?",
                (child.job_id, parent.job_id),
            )


def test_missing_parent_and_depth_bound_are_refused(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path)
    with pytest.raises(StateConflict, match="does not exist"):
        runtime.jobs.create_job("Orphan", parent_job_id="JOB-999")

    monkeypatch.setattr(executive_runtime, "_MAX_JOB_DEPTH", 1)
    parent = runtime.jobs.create_job("Root")
    child = runtime.jobs.create_job("Depth one", parent_job_id=parent.job_id)
    assert child.depth == 1
    with pytest.raises(StateConflict, match="hierarchy bound"):
        runtime.jobs.create_job("Too deep", parent_job_id=child.job_id)


def test_review_of_own_parent_and_review_of_review_are_refused(tmp_path):
    runtime = Runtime.at(tmp_path)
    parent = runtime.jobs.create_job("Parent")
    child = runtime.jobs.create_job("Child", parent_job_id=parent.job_id)
    review = runtime.jobs.create_job(
        "Review", parent_job_id=parent.job_id, reviews_job_id=child.job_id
    )
    with pytest.raises(StateConflict, match="own parent"):
        runtime.jobs.create_job(
            "Review the container",
            parent_job_id=parent.job_id,
            reviews_job_id=parent.job_id,
        )
    with pytest.raises(StateConflict, match="cannot itself require review"):
        runtime.jobs.create_job(
            "Review of review",
            parent_job_id=parent.job_id,
            reviews_job_id=review.job_id,
            review_required=True,
        )
    with pytest.raises(StateConflict, match="sibling"):
        runtime.jobs.create_job("Unparented review", reviews_job_id=child.job_id)


def test_child_cannot_widen_authority_paths_or_cost_class(tmp_path):
    runtime = Runtime.at(tmp_path)
    parent = runtime.jobs.create_job(
        "Read parent",
        constraints={"cost_class": "small"},
    )
    with pytest.raises(StateConflict, match="WRITE_BRANCH"):
        runtime.jobs.create_job(
            "Write child",
            parent_job_id=parent.job_id,
            worktree=str(tmp_path / "wt"),
            requested_authorities=["READ", "WRITE_BRANCH"],
            allowed_write_paths=["control_plane/parser.py"],
        )
    with pytest.raises(StateConflict, match="cost_class"):
        runtime.jobs.create_job(
            "Frontier child",
            parent_job_id=parent.job_id,
            constraints={"cost_class": "frontier"},
        )

    writer = runtime.jobs.create_job(
        "Writer parent",
        worktree=str(tmp_path / "wt"),
        requested_authorities=["READ", "WRITE_BRANCH"],
        allowed_write_paths=["control_plane/parser.py"],
    )
    with pytest.raises(StateConflict, match="allowed_write_paths"):
        runtime.jobs.create_job(
            "Other path",
            parent_job_id=writer.job_id,
            worktree=str(tmp_path / "wt"),
            requested_authorities=["READ", "WRITE_BRANCH"],
            allowed_write_paths=["control_plane/other.py"],
        )
    shrunk = runtime.jobs.create_job(
        "Read child of writer",
        parent_job_id=writer.job_id,
        requested_authorities=["READ"],
    )
    assert shrunk.requested_authorities == ["READ"]
    assert shrunk.allowed_write_paths == []


def test_review_job_has_no_authority_bypass(tmp_path):
    runtime = Runtime.at(tmp_path)
    parent = runtime.jobs.create_job(
        "Writer parent",
        worktree=str(tmp_path / "wt"),
        requested_authorities=["READ", "WRITE_BRANCH"],
        allowed_write_paths=["control_plane/parser.py"],
    )
    child = runtime.jobs.create_job(
        "Child",
        parent_job_id=parent.job_id,
        worktree=str(tmp_path / "wt"),
        requested_authorities=["READ", "WRITE_BRANCH"],
        allowed_write_paths=["control_plane/parser.py"],
    )
    with pytest.raises(StateConflict, match="WRITE_BRANCH requires an assigned workspace"):
        runtime.jobs.create_job(
            "Review with write and no workspace",
            parent_job_id=parent.job_id,
            reviews_job_id=child.job_id,
            requested_authorities=["READ", "WRITE_BRANCH"],
            allowed_write_paths=["control_plane/parser.py"],
        )


def test_owner_and_escalation_require_typed_provenance_and_shrink_only(tmp_path):
    runtime = Runtime.at(tmp_path)
    with pytest.raises(StateConflict, match="typed executive provenance"):
        runtime.jobs.create_job("Unproven CEO job", owner_seat="ceo")
    with pytest.raises(StateConflict, match="typed executive provenance"):
        runtime.jobs.create_job(
            "CEO provenance cannot mint chairman",
            escalation_target="chairman",
            provenance={"schema": "mastermind.ceo_intent.v1", "actor": "sol"},
        )

    root = runtime.jobs.create_job(
        "CEO-rooted job",
        owner_seat="ceo",
        escalation_target="ceo",
        provenance={"schema": "mastermind.ceo_intent.v1", "actor": "sol"},
    )
    with pytest.raises(StateConflict, match="shrink"):
        runtime.jobs.create_job(
            "Child tries to elevate",
            parent_job_id=root.job_id,
            escalation_target="chairman",
            provenance={
                "schema": "mastermind.chairman_decision.v1",
                "actor": "chairman",
            },
        )
    child = runtime.jobs.create_job(
        "Child shrinks to COO",
        parent_job_id=root.job_id,
        escalation_target="coo",
    )
    assert child.escalation_target == "coo"


def test_phase1fb_suites_are_wired_into_the_hermetic_governance_gate():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Run repository test gate" in workflow
    assert "scripts/ci_pytest.py" in workflow
    discovered = {
        path.relative_to(root).as_posix()
        for path in (root / "tests").rglob("test_*.py")
        if path.is_file()
    }
    for name in (
        "tests/test_executive_os_phase1fb.py",
        "tests/test_executive_inbox_phase1fb.py",
        "tests/test_executive_os_r1_shadow.py",
    ):
        assert name in discovered, f"{name} must be discovered by the repository test gate"
