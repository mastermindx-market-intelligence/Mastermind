"""G8 bounded Runtime acquisition: SQL-bounded owner reads before projection."""

from __future__ import annotations

from contextlib import contextmanager
import threading

import pytest

from control_plane import executive_runtime as er
from control_plane.executive_runtime import JobPayload, Runtime, StateConflict


def _runtime(tmp_path):
    root = tmp_path / "runtime"
    root.mkdir()
    return root, Runtime.at(root)


def _register_worker(runtime: Runtime) -> None:
    runtime.workers.register_worker(
        "worker-01",
        provider="codex",
        account_label="primary",
        worker_type="mock",
        capabilities=["code", "research"],
    )


def _make_attempts(runtime: Runtime, job_id: str, count: int) -> None:
    _register_worker(runtime)
    for index in range(count):
        lease = runtime.attempts.claim_job(job_id)
        assert lease is not None
        runtime.jobs.fail_job(
            job_id,
            JobPayload(errors=[f"fixture attempt {index + 1}"]),
        )
        if index + 1 < count:
            runtime.jobs.requeue_job(job_id)


def test_bounded_ceilings_track_existing_owner_policy():
    from control_plane.ceo_intent import MAX_ATTEMPT_LIMIT
    from control_plane.executive_coo_policy import CooCyclePolicy

    policy = CooCyclePolicy.load()
    assert er.BOUNDED_RUNTIME_ROOT_MAX_CHILDREN == policy.max_children_total
    assert er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS == MAX_ATTEMPT_LIMIT
    assert er.BOUNDED_RUNTIME_ROOT_MAX_ATTEMPTS_TOTAL == (
        (1 + policy.max_children_total) * MAX_ATTEMPT_LIMIT
    )


def test_bounded_queries_put_sentinel_limits_in_sqlite(tmp_path, monkeypatch):
    _root, runtime = _runtime(tmp_path)
    root = runtime.jobs.create_job("root")
    runtime.jobs.create_job("child", parent_job_id=root.job_id)

    traces = []
    original_connect = er.sqlite3.connect

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connection.set_trace_callback(traces.append)
        return connection

    monkeypatch.setattr(er.sqlite3, "connect", connect)
    runtime.discover_job_roots_bounded()
    runtime.read_job_root_bounded(root.job_id)

    normalized = [" ".join(sql.split()) for sql in traces]
    assert any(
        "WITH RECURSIVE bounded_root_ids" in sql
        and f"LIMIT {er.BOUNDED_RUNTIME_ROOT_DISCOVERY_MAX_ROOTS + 1}" in sql
        for sql in normalized
    )
    assert any(
        "WHERE (root_job_id=" in sql
        and "ORDER BY depth,created_at_ms,job_id" in sql
        and f"LIMIT {er.BOUNDED_RUNTIME_ROOT_MAX_CHILDREN + 2}" in sql
        for sql in normalized
    )
    assert any(
        "FROM attempts" in sql
        and "job_id IN" in sql
        and f"LIMIT {er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS + 1}" in sql
        for sql in normalized
    )


def test_root_discovery_is_sql_bounded_before_job_conversion(tmp_path, monkeypatch):
    _root, runtime = _runtime(tmp_path)
    for index in range(er.BOUNDED_RUNTIME_ROOT_DISCOVERY_MAX_ROOTS + 3):
        runtime.jobs.create_job(f"root {index:03d}")

    converted = []
    original = er._job_from_row

    def spy(row):
        converted.append(str(row["job_id"]))
        return original(row)

    monkeypatch.setattr(er, "_job_from_row", spy)
    observed = runtime.discover_job_roots_bounded()

    assert observed.schema_version == er.BOUNDED_RUNTIME_DISCOVERY_SCHEMA
    assert len(observed.roots) == er.BOUNDED_RUNTIME_ROOT_DISCOVERY_MAX_ROOTS
    assert observed.truncated is True
    assert len(converted) == er.BOUNDED_RUNTIME_ROOT_DISCOVERY_MAX_ROOTS
    assert observed.snapshot_digest == runtime.discover_job_roots_bounded().snapshot_digest


def test_exact_root_snapshot_materializes_only_root_plus_closed_child_budget(
    tmp_path, monkeypatch
):
    _root, runtime = _runtime(tmp_path)
    root = runtime.jobs.create_job("root")
    children = [
        runtime.jobs.create_job(f"child {index:03d}", parent_job_id=root.job_id)
        for index in range(er.BOUNDED_RUNTIME_ROOT_MAX_CHILDREN + 2)
    ]

    converted = []
    original = er._job_from_row

    def spy(row):
        converted.append(str(row["job_id"]))
        return original(row)

    monkeypatch.setattr(er, "_job_from_row", spy)
    observed = runtime.read_job_root_bounded(root.job_id)

    assert observed.schema_version == er.BOUNDED_RUNTIME_ROOT_SNAPSHOT_SCHEMA
    assert observed.root_job_id == root.job_id
    assert observed.jobs[0].job_id == root.job_id
    assert len(observed.jobs) == 1 + er.BOUNDED_RUNTIME_ROOT_MAX_CHILDREN
    assert observed.jobs_truncated is True
    assert len(converted) == 1 + er.BOUNDED_RUNTIME_ROOT_MAX_CHILDREN
    assert set(job.job_id for job in observed.jobs[1:]).issubset(
        {child.job_id for child in children}
    )
    # Legacy registry behavior is deliberately unchanged and still sees everything.
    assert len(runtime.jobs.list_jobs()) == 1 + len(children)


def test_attempts_are_bounded_per_job_before_attempt_conversion(tmp_path, monkeypatch):
    _root, runtime = _runtime(tmp_path)
    root = runtime.jobs.create_job("root")
    child = runtime.jobs.create_job(
        "attempt-heavy child",
        parent_job_id=root.job_id,
        attempt_limit=er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS + 1,
    )
    _make_attempts(runtime, child.job_id, er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS + 1)

    converted = []
    original = er._attempt_from_row

    def spy(row):
        converted.append(str(row["attempt_id"]))
        return original(row)

    monkeypatch.setattr(er, "_attempt_from_row", spy)
    observed = runtime.read_job_root_bounded(root.job_id)

    assert len(observed.attempts) == er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS
    assert observed.attempts_truncated_job_ids == (child.job_id,)
    assert len(converted) == er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS
    assert all(attempt.job_id == child.job_id for attempt in observed.attempts)
    assert len(runtime.attempts.list_attempts(child.job_id)) == (
        er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS + 1
    )


def test_root_snapshot_refuses_nonroot_and_never_leaks_another_root(tmp_path):
    _root, runtime = _runtime(tmp_path)
    first = runtime.jobs.create_job("first root")
    first_child = runtime.jobs.create_job("first child", parent_job_id=first.job_id)
    second = runtime.jobs.create_job("second root")
    second_child = runtime.jobs.create_job("second child", parent_job_id=second.job_id)

    with pytest.raises(StateConflict, match="exact root"):
        runtime.read_job_root_bounded(first_child.job_id)

    observed = runtime.read_job_root_bounded(first.job_id)
    assert {job.job_id for job in observed.jobs} == {first.job_id, first_child.job_id}
    assert second.job_id not in {job.job_id for job in observed.jobs}
    assert second_child.job_id not in {job.job_id for job in observed.jobs}


def test_snapshot_digest_is_content_addressed_and_changes_with_runtime_state(tmp_path):
    _root, runtime = _runtime(tmp_path)
    root = runtime.jobs.create_job("root")
    first = runtime.read_job_root_bounded(root.job_id)
    again = runtime.read_job_root_bounded(root.job_id)
    assert first.snapshot_digest == again.snapshot_digest

    runtime.jobs.create_job("new child", parent_job_id=root.job_id)
    changed = runtime.read_job_root_bounded(root.job_id)
    assert changed.snapshot_digest != first.snapshot_digest


def test_bounded_snapshot_composes_with_existing_runtime_read_binding(tmp_path):
    root_path, writer = _runtime(tmp_path)
    root = writer.jobs.create_job("root")
    writer.jobs.create_job("child", parent_job_id=root.job_id)

    class Namespace(er.RuntimeNamespaceCapability):
        def __init__(self):
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
            return None

    provider = Namespace()
    binding = er.RuntimeReadBinding(provider)
    observed = Runtime.read_bound(
        root_path,
        binding=binding,
        reader=lambda runtime: runtime.read_job_root_bounded(root.job_id),
    )

    assert observed.root_job_id == root.job_id
    assert [job.objective for job in observed.jobs] == ["root", "child"]
    assert provider.entries == provider.exits == 1
