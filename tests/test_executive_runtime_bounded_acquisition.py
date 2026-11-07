"""G8 proof for SQL-bounded Executive Runtime Job/Attempt acquisition."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import control_plane.executive_runtime as executive_runtime
from control_plane.executive_runtime import (
    AttemptStatus,
    JobPayload,
    JobStatus,
    PersistenceError,
    Runtime,
    StateConflict,
)


def _runtime(tmp_path: Path) -> Runtime:
    return Runtime.at(tmp_path)


def _register_default(runtime: Runtime) -> None:
    runtime.workers.register_worker(
        "worker-01",
        provider="codex",
        account_label="primary",
        worker_type="mock",
        capabilities=["code"],
    )


def _failed_attempt(runtime: Runtime, *, objective: str = "attempted work"):
    job = runtime.jobs.create_job(objective, attempt_limit=200_000)
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    runtime.jobs.fail_job(job.job_id, JobPayload(errors=["expected test failure"]))
    runtime.jobs.requeue_job(job.job_id)
    return job, lease.attempt


def _clone_table_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    template_query: str,
    template_parameters: tuple[Any, ...],
    count: int,
    mutate: Any,
) -> None:
    template = connection.execute(template_query, template_parameters).fetchone()
    assert template is not None
    columns = tuple(template.keys())
    quoted_columns = ",".join(f'"{name}"' for name in columns)
    placeholders = ",".join("?" for _ in columns)
    statement = f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})'

    def rows() -> Iterator[tuple[Any, ...]]:
        base = dict(template)
        for index in range(count):
            value = dict(base)
            mutate(value, index)
            yield tuple(value[name] for name in columns)

    connection.executemany(statement, rows())


def _seed_jobs(
    runtime: Runtime,
    *,
    count: int,
    prefix: str = "JOB-HISTORY",
    start_ms: int = 1_700_000_000_000,
    constant_order: bool = False,
) -> list[str]:
    template = runtime.jobs.create_job("job seed")
    identifiers = [f"{prefix}-{index:06d}" for index in range(count)]

    def mutate(row: dict[str, Any], index: int) -> None:
        job_id = identifiers[index]
        timestamp = start_ms if constant_order else start_ms + index
        row.update(
            job_id=job_id,
            objective=f"historical job {index}",
            status=JobStatus.QUEUED.value,
            assigned_worker_id=None,
            assigned_quota_class=None,
            current_attempt_id=None,
            checkpoint_json=None,
            result_json=None,
            attempt_count=0,
            available_at_ms=timestamp,
            cancel_requested_at_ms=None,
            created_at_ms=timestamp,
            updated_at_ms=timestamp,
            version=1,
            parent_job_id=None,
            root_job_id=job_id,
            depth=0,
            reviews_job_id=None,
            orchestration_role=None,
            orchestration_provenance_json=None,
            orchestration_provenance_digest=None,
            plan_attempt_id=None,
            plan_digest=None,
            plan_step_id=None,
            repair_round=None,
            supersedes_job_id=None,
        )

    with runtime.store.transaction() as connection:
        _clone_table_rows(
            connection,
            table="jobs",
            template_query="SELECT * FROM jobs WHERE job_id=?",
            template_parameters=(template.job_id,),
            count=count,
            mutate=mutate,
        )
    return identifiers


def _seed_attempts(
    runtime: Runtime,
    *,
    count: int,
    start_ms: int = 1_800_000_000_000,
    constant_lease: bool = False,
) -> tuple[str, list[str]]:
    _register_default(runtime)
    job, template = _failed_attempt(runtime)
    identifiers = [f"ATT-HISTORY-{index:06d}" for index in range(count)]

    def mutate(row: dict[str, Any], index: int) -> None:
        timestamp = start_ms + index
        lease_timestamp = start_ms if constant_lease else timestamp
        row.update(
            attempt_id=identifiers[index],
            job_id=job.job_id,
            attempt_number=index + 2,
            status=AttemptStatus.FAILED.value,
            lease_token=None,
            lease_expires_at_ms=lease_timestamp,
            heartbeat_at_ms=timestamp,
            checkpoint_sequence=0,
            checkpoint_json=None,
            result_json=None,
            error_json='{"errors":["historical"]}',
            pid=None,
            pgid=None,
            process_start_identity=None,
            boot_id=None,
            provider_session_id=None,
            stdout_path=None,
            stderr_path=None,
            result_path=None,
            exit_code=1,
            launch_metadata_json="{}",
            started_at_ms=timestamp,
            finished_at_ms=timestamp,
            created_at_ms=timestamp,
            updated_at_ms=timestamp,
            version=1,
            execution_mode=None,
            requested_execution_profile_json=None,
            requested_execution_profile_digest=None,
            effective_grant_json=None,
            effective_grant_digest=None,
            placement_snapshot_json=None,
            placement_snapshot_digest=None,
            execution_principal_snapshot_json=None,
            execution_principal_snapshot_digest=None,
        )

    with runtime.store.transaction() as connection:
        _clone_table_rows(
            connection,
            table="attempts",
            template_query="SELECT * FROM attempts WHERE attempt_id=?",
            template_parameters=(template.attempt_id,),
            count=count,
            mutate=mutate,
        )
    return job.job_id, identifiers


def _all_job_ids(acquisition: Any, *, limit: int = 17) -> list[str]:
    values: list[str] = []
    cursor = None
    while True:
        page = acquisition.list_jobs(limit=limit, cursor=cursor)
        values.extend(job.job_id for job in page.items)
        if page.next_cursor is None:
            return values
        cursor = page.next_cursor


def test_bounded_acquisition_filters_exact_root_ids_and_attempts(tmp_path):
    runtime = _runtime(tmp_path)
    root = runtime.jobs.create_job("root")
    child = runtime.jobs.create_job("child", parent_job_id=root.job_id)
    grandchild = runtime.jobs.create_job("grandchild", parent_job_id=child.job_id)
    unrelated = runtime.jobs.create_job("unrelated root")
    _register_default(runtime)
    grandchild_attempt = runtime.attempts.claim_job(grandchild.job_id)
    assert grandchild_attempt is not None

    with runtime.bounded_acquisition() as acquisition:
        tree = acquisition.list_jobs(limit=10, root_job_id=root.job_id)
        exact = acquisition.list_jobs(
            limit=10, job_ids=[grandchild.job_id, root.job_id]
        )
        roots = acquisition.list_jobs(limit=10, roots_only=True)
        attempts = acquisition.list_attempts(
            limit=10, job_ids=[grandchild.job_id, unrelated.job_id]
        )

    assert isinstance(tree.items, tuple)
    assert [job.job_id for job in tree.items] == [
        root.job_id,
        child.job_id,
        grandchild.job_id,
    ]
    assert tree.next_cursor is None
    assert [job.job_id for job in exact.items] == sorted(
        [root.job_id, grandchild.job_id]
    )
    assert [job.job_id for job in roots.items] == sorted(
        [root.job_id, unrelated.job_id]
    )
    assert [attempt.job_id for attempt in attempts.items] == [grandchild.job_id]


def test_limits_filters_and_query_modes_fail_closed(tmp_path):
    runtime = _runtime(tmp_path)
    job = runtime.jobs.create_job("one")
    maximum = executive_runtime.MAX_RUNTIME_ACQUISITION_LIMIT
    assert maximum == 512

    with runtime.bounded_acquisition() as acquisition:
        for invalid in (True, 0, -1, maximum + 1):
            with pytest.raises(StateConflict, match="limit"):
                acquisition.list_jobs(limit=invalid)
        with pytest.raises(StateConflict, match="identifier"):
            acquisition.list_jobs(limit=1, root_job_id=" ")
        with pytest.raises(StateConflict, match="duplicate"):
            acquisition.list_jobs(limit=1, job_ids=[job.job_id, job.job_id])
        with pytest.raises(StateConflict, match="mutually exclusive"):
            acquisition.list_jobs(
                limit=1, root_job_id=job.job_id, job_ids=[job.job_id]
            )
        statements: list[str] = []
        connection = acquisition._connection
        assert isinstance(connection, sqlite3.Connection)
        connection.set_trace_callback(statements.append)
        try:
            with pytest.raises(
                StateConflict, match="cannot combine root_job_id and statuses"
            ):
                acquisition.list_jobs(
                    limit=1,
                    root_job_id=job.job_id,
                    statuses=[JobStatus.QUEUED],
                )
        finally:
            connection.set_trace_callback(None)
        assert [
            " ".join(statement.upper().split()) for statement in statements
        ] == ["PRAGMA DATABASE_LIST"]
        with pytest.raises(StateConflict, match="roots_only"):
            acquisition.list_jobs(
                limit=1, roots_only=True, statuses=[JobStatus.QUEUED]
            )
        with pytest.raises(StateConflict, match="status"):
            acquisition.list_jobs(limit=1, statuses=[])
        with pytest.raises(StateConflict, match="status"):
            acquisition.list_attempts(limit=1, statuses=["NOT_A_STATUS"])
        with pytest.raises(StateConflict, match="cannot combine"):
            acquisition.list_attempts(
                limit=1,
                job_ids=[job.job_id],
                statuses=[AttemptStatus.FAILED],
            )
        for invalid in (True, 0, -1, maximum + 1):
            with pytest.raises(StateConflict, match="limit"):
                acquisition.list_attempts(limit=invalid)
        with pytest.raises(StateConflict, match="duplicate"):
            acquisition.list_attempts(
                limit=1, job_ids=[job.job_id, job.job_id]
            )
        oversized_ids = [f"JOB-FILTER-{index:03d}" for index in range(129)]
        with pytest.raises(StateConflict, match="bounded sequence"):
            acquisition.list_jobs(limit=1, job_ids=oversized_ids)
        with pytest.raises(StateConflict, match="bounded sequence"):
            acquisition.list_attempts(limit=1, job_ids=oversized_ids)


def test_cursor_is_snapshot_and_query_bound_and_tamper_evident(tmp_path):
    runtime = _runtime(tmp_path)
    for index in range(8):
        runtime.jobs.create_job(f"job {index}")

    with runtime.bounded_acquisition() as first:
        page = first.list_jobs(limit=2)
        assert page.next_cursor is not None
        cursor = page.next_cursor

        resumed = first.list_jobs(limit=3, cursor=cursor)
        assert resumed.items

        with pytest.raises(StateConflict, match="cursor"):
            first.list_jobs(
                limit=2,
                cursor=cursor,
                statuses=[JobStatus.QUEUED],
            )
        replacement = ("A" if cursor[0] != "A" else "B") + cursor[1:]
        with pytest.raises(StateConflict, match="cursor"):
            first.list_jobs(limit=2, cursor=replacement)

    with pytest.raises(StateConflict, match="closed"):
        first.list_jobs(limit=2, cursor=cursor)

    with runtime.bounded_acquisition() as second:
        with pytest.raises(StateConflict, match="cursor"):
            second.list_jobs(limit=2, cursor=cursor)


def test_fixed_snapshot_pagination_has_no_duplicate_skip_or_late_insert(tmp_path):
    runtime = _runtime(tmp_path)
    originals = {
        runtime.jobs.create_job(f"job {index}").job_id for index in range(137)
    }

    with runtime.bounded_acquisition() as acquisition:
        first = acquisition.list_jobs(limit=11)
        seen = [job.job_id for job in first.items]
        cursor = first.next_cursor
        late = Runtime.at(tmp_path).jobs.create_job("late insert")
        while cursor is not None:
            page = acquisition.list_jobs(limit=11, cursor=cursor)
            seen.extend(job.job_id for job in page.items)
            cursor = page.next_cursor

    assert len(seen) == len(set(seen))
    assert set(seen) == originals
    assert late.job_id not in seen
    with runtime.bounded_acquisition() as fresh:
        assert late.job_id in _all_job_ids(fresh)


def test_corrupt_row_outside_window_is_not_decoded_or_claimed_inspected(
    tmp_path, monkeypatch
):
    runtime = _runtime(tmp_path)
    identifiers = _seed_jobs(runtime, count=4, prefix="JOB-CORRUPT")
    corrupt_id = identifiers[-1]
    raw = sqlite3.connect(runtime.store.path)
    try:
        raw.execute("PRAGMA ignore_check_constraints=ON")
        raw.execute(
            "UPDATE jobs SET constraints_json='not-json' WHERE job_id=?",
            (corrupt_id,),
        )
        raw.commit()
    finally:
        raw.close()

    decoded: list[str] = []
    original = executive_runtime._job_from_row

    def observed(row):
        decoded.append(str(row["job_id"]))
        return original(row)

    monkeypatch.setattr(executive_runtime, "_job_from_row", observed)
    with runtime.bounded_acquisition() as acquisition:
        cursor = None
        returned: list[str] = []
        while True:
            try:
                page = acquisition.list_jobs(
                    limit=1,
                    cursor=cursor,
                    statuses=[JobStatus.QUEUED],
                )
            except PersistenceError:
                break
            returned.extend(job.job_id for job in page.items)
            cursor = page.next_cursor
            assert cursor is not None

    assert returned
    assert corrupt_id not in returned
    assert corrupt_id in decoded
    assert decoded[-1] == corrupt_id


def test_bounded_acquisition_excludes_population_unbounded_status_aggregates(
    tmp_path,
):
    runtime = _runtime(tmp_path)
    with runtime.bounded_acquisition() as acquisition:
        assert not hasattr(acquisition, "job_status_counts")
        assert not hasattr(acquisition, "attempt_status_counts")
    assert "RuntimeStatusCounts" not in executive_runtime.__all__


def test_existing_point_and_per_job_attempt_reads_remain_compatible(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    job = runtime.jobs.create_job("compatible")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    before_job = runtime.jobs.get_job(job.job_id)
    before_attempts = runtime.attempts.list_attempts(job.job_id)

    with runtime.bounded_acquisition() as acquisition:
        page = acquisition.list_jobs(limit=1, job_ids=[job.job_id])
        attempt_page = acquisition.list_attempts(limit=1, job_ids=[job.job_id])

    assert page.items == (before_job,)
    assert attempt_page.items == tuple(before_attempts)
    assert runtime.jobs.get_job(job.job_id) == before_job
    assert runtime.attempts.list_attempts(job.job_id) == before_attempts
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id) == lease.attempt



def test_attempt_pagination_is_stable_without_duplicates_skips_or_late_insert(
    tmp_path,
):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    job = runtime.jobs.create_job("many attempts", attempt_limit=100)
    original_ids: set[str] = set()
    for index in range(37):
        lease = runtime.attempts.claim_job(job.job_id)
        assert lease is not None
        original_ids.add(lease.attempt.attempt_id)
        runtime.jobs.fail_job(
            job.job_id, JobPayload(errors=[f"expected failure {index}"])
        )
        if index < 36:
            runtime.jobs.requeue_job(job.job_id)

    with runtime.bounded_acquisition() as acquisition:
        first = acquisition.list_attempts(limit=7, job_ids=[job.job_id])
        seen = [attempt.attempt_id for attempt in first.items]
        cursor = first.next_cursor

        writer = Runtime.at(tmp_path)
        writer.jobs.requeue_job(job.job_id)
        late_lease = writer.attempts.claim_job(job.job_id)
        assert late_lease is not None

        while cursor is not None:
            page = acquisition.list_attempts(
                limit=7,
                cursor=cursor,
                job_ids=[job.job_id],
            )
            seen.extend(attempt.attempt_id for attempt in page.items)
            cursor = page.next_cursor

    assert len(seen) == len(set(seen))
    assert set(seen) == original_ids
    assert late_lease.attempt.attempt_id not in seen
    with runtime.bounded_acquisition() as fresh:
        fresh_ids: list[str] = []
        cursor = None
        while True:
            page = fresh.list_attempts(
                limit=9,
                cursor=cursor,
                job_ids=[job.job_id],
            )
            fresh_ids.extend(attempt.attempt_id for attempt in page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
    assert set(fresh_ids) == original_ids | {late_lease.attempt.attempt_id}


def test_corrupt_attempt_outside_window_is_not_decoded_until_reached(
    tmp_path, monkeypatch
):
    runtime = _runtime(tmp_path)
    job_id, identifiers = _seed_attempts(
        runtime, count=3, start_ms=1_810_000_000_000
    )
    corrupt_id = "ATT-HISTORY-CORRUPT"
    raw = sqlite3.connect(runtime.store.path)
    raw.row_factory = sqlite3.Row
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("PRAGMA ignore_check_constraints=ON")

        def corrupt(row: dict[str, Any], _index: int) -> None:
            row.update(
                attempt_id=corrupt_id,
                attempt_number=10_000,
                error_json="not-json",
                lease_expires_at_ms=1_820_000_000_000,
                heartbeat_at_ms=1_820_000_000_000,
                started_at_ms=1_820_000_000_000,
                finished_at_ms=1_820_000_000_000,
                created_at_ms=1_820_000_000_000,
                updated_at_ms=1_820_000_000_000,
            )

        _clone_table_rows(
            raw,
            table="attempts",
            template_query="SELECT * FROM attempts WHERE attempt_id=?",
            template_parameters=(identifiers[-1],),
            count=1,
            mutate=corrupt,
        )
        raw.commit()
    finally:
        raw.close()

    decoded: list[str] = []
    original = executive_runtime._attempt_from_row

    def observed(row):
        decoded.append(str(row["attempt_id"]))
        return original(row)

    monkeypatch.setattr(executive_runtime, "_attempt_from_row", observed)
    returned: list[str] = []
    with runtime.bounded_acquisition() as acquisition:
        cursor = None
        while True:
            try:
                page = acquisition.list_attempts(
                    limit=1,
                    cursor=cursor,
                    job_ids=[job_id],
                )
            except PersistenceError:
                break
            returned.extend(attempt.attempt_id for attempt in page.items)
            cursor = page.next_cursor
            assert cursor is not None

    assert returned
    assert corrupt_id not in returned
    assert corrupt_id in decoded
    assert decoded[-1] == corrupt_id


def test_sql_limit_is_applied_before_job_and_attempt_materialization(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    job = runtime.jobs.create_job("bounded SQL")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    statements: list[str] = []

    with runtime.bounded_acquisition() as acquisition:
        connection = acquisition._connection
        assert isinstance(connection, sqlite3.Connection)
        connection.set_trace_callback(statements.append)
        acquisition.list_jobs(limit=3, statuses=[JobStatus.RUNNING])
        acquisition.list_attempts(limit=2, job_ids=[job.job_id])
        connection.set_trace_callback(None)

    normalized = [" ".join(statement.upper().split()) for statement in statements]
    assert any(
        statement.startswith("SELECT * FROM JOBS") and statement.endswith("LIMIT 4")
        for statement in normalized
    )
    assert any(
        statement.startswith("SELECT * FROM ATTEMPTS")
        and statement.endswith("LIMIT 3")
        for statement in normalized
    )


def test_query_plans_use_existing_runtime_indexes(tmp_path):
    runtime = _runtime(tmp_path)
    root = runtime.jobs.create_job("root")
    child = runtime.jobs.create_job("child", parent_job_id=root.job_id)
    _register_default(runtime)
    lease = runtime.attempts.claim_job(child.job_id)
    assert lease is not None

    with runtime.store.read() as connection:
        plans = {
            "jobs_global": connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT * FROM jobs WHERE status IN (?)
                ORDER BY status,available_at_ms,priority DESC,created_at_ms,job_id
                LIMIT ?
                """,
                (JobStatus.RUNNING.value, 26),
            ).fetchall(),
            "jobs_tree": connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT * FROM jobs WHERE root_job_id=?
                ORDER BY depth,created_at_ms,job_id LIMIT ?
                """,
                (root.job_id, 26),
            ).fetchall(),
            "roots": connection.execute(
                """
                EXPLAIN QUERY PLAN
                WITH RECURSIVE bounded_root_ids(root_job_id) AS (
                    SELECT MIN(root_job_id) FROM jobs WHERE root_job_id>?
                    UNION ALL
                    SELECT (
                        SELECT MIN(root_job_id) FROM jobs
                        WHERE root_job_id>bounded_root_ids.root_job_id
                    )
                    FROM bounded_root_ids
                    WHERE root_job_id IS NOT NULL
                    LIMIT ?
                )
                SELECT root_job_id FROM bounded_root_ids
                WHERE root_job_id IS NOT NULL
                """,
                ("", 26),
            ).fetchall(),
            "attempts_global": connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT rowid,* FROM attempts WHERE status IN (?)
                ORDER BY status,lease_expires_at_ms,rowid LIMIT ?
                """,
                (AttemptStatus.CLAIMED.value, 26),
            ).fetchall(),
            "attempts_job": connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT * FROM attempts WHERE job_id IN (?)
                ORDER BY job_id,attempt_number LIMIT ?
                """,
                (child.job_id, 26),
            ).fetchall(),
        }

    details = {
        name: " | ".join(str(row[3]).upper() for row in rows)
        for name, rows in plans.items()
    }
    assert "JOBS_DISPATCH_ORDER" in details["jobs_global"]
    assert "JOBS_ROOT_ORDER" in details["jobs_tree"]
    assert "JOBS_ROOT_ORDER" in details["roots"]
    assert "ATTEMPTS_EXPIRY" in details["attempts_global"]
    assert "INDEX" in details["attempts_job"]
    assert "SCAN ATTEMPTS" not in details["attempts_job"]


def test_bounded_acquisition_operates_through_read_only_runtime(tmp_path):
    writable = _runtime(tmp_path)
    job = writable.jobs.create_job("read-only projection")
    reader = Runtime.at(tmp_path, create=False)

    with reader.bounded_acquisition() as acquisition:
        page = acquisition.list_jobs(limit=1, job_ids=[job.job_id])

    assert page.items == (job,)
    with pytest.raises(StateConflict, match="read-only store"):
        reader.jobs.create_job("forbidden mutation")



def test_bounded_acquisition_composes_with_runtime_read_binding(tmp_path):
    from contextlib import contextmanager
    import threading

    writer = _runtime(tmp_path)
    root = writer.jobs.create_job("bound root")
    child = writer.jobs.create_job("bound child", parent_job_id=root.job_id)

    class Namespace(executive_runtime.RuntimeNamespaceCapability):
        def __init__(self) -> None:
            self.lock = threading.Lock()
            self.entries = 0
            self.exits = 0

        @contextmanager
        def namespace(self, database_path):
            assert self.lock.acquire(timeout=1)
            self.entries += 1
            try:
                yield
            finally:
                self.exits += 1
                self.lock.release()

        def validate(self, database_path):
            assert database_path == writer.store.path

    namespace = Namespace()
    binding = executive_runtime.RuntimeReadBinding(namespace)

    def read(runtime: Runtime) -> dict[str, Any]:
        with runtime.bounded_acquisition() as acquisition:
            roots = acquisition.list_jobs(limit=5, roots_only=True)
            tree = acquisition.list_jobs(limit=5, root_job_id=root.job_id)
            return {
                "roots": [job.job_id for job in roots.items],
                "tree": [job.job_id for job in tree.items],
            }

    result = Runtime.read_bound(tmp_path, binding=binding, reader=read)
    assert result == {
        "roots": [root.job_id],
        "tree": [root.job_id, child.job_id],
    }
    assert namespace.entries == namespace.exits == 1


def test_100k_histories_decode_only_requested_window(tmp_path, monkeypatch, capsys):
    runtime = _runtime(tmp_path)
    _seed_jobs(runtime, count=100_000)
    attempt_job_id, _attempt_ids = _seed_attempts(runtime, count=100_000)

    job_decodes = 0
    attempt_decodes = 0
    original_job = executive_runtime._job_from_row
    original_attempt = executive_runtime._attempt_from_row

    def observed_job(row):
        nonlocal job_decodes
        job_decodes += 1
        return original_job(row)

    def observed_attempt(row):
        nonlocal attempt_decodes
        attempt_decodes += 1
        return original_attempt(row)

    monkeypatch.setattr(executive_runtime, "_job_from_row", observed_job)
    monkeypatch.setattr(executive_runtime, "_attempt_from_row", observed_attempt)

    started = time.perf_counter()
    with runtime.bounded_acquisition() as acquisition:
        jobs = acquisition.list_jobs(
            limit=23, statuses=[JobStatus.QUEUED]
        )
        attempts = acquisition.list_attempts(
            limit=19,
            job_ids=[attempt_job_id],
        )
    elapsed = time.perf_counter() - started

    assert len(jobs.items) == 23
    assert jobs.next_cursor is not None
    assert job_decodes == 23
    assert len(attempts.items) == 19
    assert attempts.next_cursor is not None
    assert attempt_decodes == 19
    print(
        json.dumps(
            {
                "history_jobs": 100_000,
                "history_attempts": 100_000,
                "requested_jobs": 23,
                "requested_attempts": 19,
                "decoded_jobs": job_decodes,
                "decoded_attempts": attempt_decodes,
                "elapsed_seconds": elapsed,
            },
            sort_keys=True,
        )
    )
    assert capsys.readouterr().out



def _vm_steps(connection: sqlite3.Connection, action: Any) -> tuple[Any, int]:
    callbacks = 0
    granularity = 100

    def progress() -> int:
        nonlocal callbacks
        callbacks += 1
        return 0

    connection.set_progress_handler(progress, granularity)
    try:
        result = action()
    finally:
        connection.set_progress_handler(None, 0)
    return result, callbacks * granularity


def _deep_page_vm_profile(root: Path, history: int) -> dict[str, int]:
    runtime = _runtime(root)
    start_jobs = 1_700_000_000_000
    job_ids = _seed_jobs(
        runtime,
        count=history,
        start_ms=start_jobs,
        constant_order=True,
    )
    attempt_job_id, attempt_ids = _seed_attempts(
        runtime,
        count=history,
        constant_lease=True,
    )
    deep_index = history - 101

    with runtime.bounded_acquisition() as acquisition:
        connection = acquisition._connection
        assert isinstance(connection, sqlite3.Connection)
        roots, root_steps = _vm_steps(
            connection,
            lambda: acquisition.list_jobs(limit=23, roots_only=True),
        )
        assert len(roots.items) == 23
        assert roots.next_cursor is not None

        job_row = connection.execute(
            """SELECT status,available_at_ms,priority,created_at_ms,job_id
               FROM jobs WHERE job_id=?""",
            (job_ids[deep_index],),
        ).fetchone()
        assert job_row is not None
        job_query = {
            "mode": "global",
            "root_job_id": None,
            "job_ids": [],
            "statuses": [],
        }
        job_cursor = acquisition._encode_cursor(
            kind="jobs",
            query=job_query,
            position=(
                str(job_row["status"]),
                int(job_row["available_at_ms"]),
                int(job_row["priority"]),
                int(job_row["created_at_ms"]),
                str(job_row["job_id"]),
            ),
        )
        jobs, job_steps = _vm_steps(
            connection,
            lambda: acquisition.list_jobs(limit=23, cursor=job_cursor),
        )
        assert [job.job_id for job in jobs.items] == job_ids[
            deep_index + 1 : deep_index + 24
        ]
        assert jobs.next_cursor is not None

        attempt_row = connection.execute(
            """SELECT rowid AS acquisition_rowid,status,lease_expires_at_ms,
                      job_id,attempt_number
               FROM attempts WHERE attempt_id=?""",
            (attempt_ids[deep_index],),
        ).fetchone()
        assert attempt_row is not None
        global_attempt_query = {
            "mode": "global",
            "job_ids": [],
            "statuses": [AttemptStatus.FAILED.value],
        }
        global_attempt_cursor = acquisition._encode_cursor(
            kind="attempts",
            query=global_attempt_query,
            position=(
                str(attempt_row["status"]),
                int(attempt_row["lease_expires_at_ms"]),
                int(attempt_row["acquisition_rowid"]),
            ),
        )
        global_attempts, global_attempt_steps = _vm_steps(
            connection,
            lambda: acquisition.list_attempts(
                limit=19,
                cursor=global_attempt_cursor,
                statuses=[AttemptStatus.FAILED],
            ),
        )
        assert [attempt.attempt_id for attempt in global_attempts.items] == (
            attempt_ids[deep_index + 1 : deep_index + 20]
        )
        assert global_attempts.next_cursor is not None

        job_attempt_query = {
            "mode": "job_ids",
            "job_ids": [attempt_job_id],
            "statuses": [],
        }
        job_attempt_cursor = acquisition._encode_cursor(
            kind="attempts",
            query=job_attempt_query,
            position=(
                str(attempt_row["job_id"]),
                int(attempt_row["attempt_number"]),
            ),
        )
        job_attempts, job_attempt_steps = _vm_steps(
            connection,
            lambda: acquisition.list_attempts(
                limit=19,
                cursor=job_attempt_cursor,
                job_ids=[attempt_job_id],
            ),
        )
        assert [attempt.attempt_id for attempt in job_attempts.items] == (
            attempt_ids[deep_index + 1 : deep_index + 20]
        )
        assert job_attempts.next_cursor is not None

    return {
        "roots": root_steps,
        "jobs": job_steps,
        "attempts_global": global_attempt_steps,
        "attempts_job": job_attempt_steps,
    }


def test_vm_work_remains_bounded_as_job_and_attempt_history_grows(tmp_path):
    small = _deep_page_vm_profile(tmp_path / "small", 1_000)
    large = _deep_page_vm_profile(tmp_path / "large", 100_000)
    print(json.dumps({"small": small, "large": large}, sort_keys=True))

    for query_kind in sorted(small):
        assert large[query_kind] <= max(
            small[query_kind] * 4,
            small[query_kind] + 2_000,
        ), (query_kind, small, large)
