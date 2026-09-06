"""R0 tests use genuine disposable Runtime databases, never installed state."""
from __future__ import annotations

from contextlib import contextmanager
import importlib
import importlib.util
import json
import sqlite3

import pytest

from control_plane.executive_runtime import Runtime


def observer():
    name = "control_plane.executive_lane_observation"
    assert importlib.util.find_spec(name) is not None, "R0 observer is not implemented"
    return importlib.import_module(name)


def seed(root):
    writer = Runtime.at(root)
    parent = writer.jobs.create_job("PRIVATE_PROMPT_SENTINEL")
    first = writer.jobs.create_job("first child", parent_job_id=parent.job_id)
    second = writer.jobs.create_job("second child", parent_job_id=parent.job_id)
    writer.workers.register_worker("fixture-a", provider="codex",
        account_label="private-account-sentinel", worker_type="fixture",
        capabilities=["research"], metadata={"secret": "PRIVATE_METADATA_SENTINEL"})
    lease = writer.attempts.claim_job(first.job_id, worker_id="fixture-a")
    assert lease is not None
    return writer, parent, first, second, lease


def test_parallel_children_and_exact_current_attempt_are_visible(tmp_path):
    module = observer()
    writer, parent, first, second, lease = seed(tmp_path)
    before = writer.store.snapshot()
    result = module.observe_root_lanes(Runtime.at(tmp_path, create=False), parent.job_id)
    assert result["status"] == "OBSERVED"
    assert result["coverage"]["completeness"] == "complete"
    rows = {row["job_id"]: row for row in result["lanes"]}
    assert set(rows) == {parent.job_id, first.job_id, second.job_id}
    assert rows[first.job_id]["parent_job_id"] == parent.job_id
    assert rows[second.job_id]["parent_job_id"] == parent.job_id
    assert rows[first.job_id]["current_attempt"]["attempt_id"] == lease.attempt.attempt_id
    assert rows[first.job_id]["current_attempt"]["status"] == "CLAIMED"
    assert rows[second.job_id]["current_attempt"] is None
    assert result["current_permission"] == "NOT_EVALUATED"
    assert result["coverage"]["native_helpers"] == "not_observed"
    assert writer.store.snapshot() == before
    encoded = json.dumps(result)
    assert "PRIVATE_" not in encoded
    assert "private-account-sentinel" not in encoded
    assert lease.lease_token not in encoded
    assert "stdout_path" not in encoded and "provider_session_id" not in encoded


@pytest.mark.parametrize("limit", [1, 2])
def test_truncated_root_is_not_a_complete_fleet(tmp_path, limit):
    module = observer()
    _, parent, *_ = seed(tmp_path)
    result = module.observe_root_lanes(Runtime.at(tmp_path, create=False), parent.job_id, max_rows=limit)
    assert result["status"] == "PARTIAL"
    assert result["coverage"]["completeness"] == "truncated"
    assert len(result["lanes"]) == limit
    assert result["lanes"][0]["job_id"] == parent.job_id


@pytest.mark.parametrize("limit", [0, -1, 129, True, "2", None])
def test_invalid_row_limits_refuse(tmp_path, limit):
    module = observer()
    runtime = Runtime.at(tmp_path)
    result = module.observe_root_lanes(runtime, "JOB-001", max_rows=limit)
    assert result["status"] == "REFUSED"
    assert result["issues"] == ["INVALID_ROW_LIMIT"]
    assert result["lanes"] is None


@pytest.mark.parametrize("root", ["", "../secret", "x" * 129, None])
def test_invalid_root_is_not_echoed_or_queried(root):
    result = observer().observe_root_lanes(None, root)
    assert result["root_job_id"] is None
    assert result["lanes"] is None
    assert result["issues"] == ["INVALID_ROOT"]


def test_writable_runtime_is_refused_before_query(tmp_path):
    writer = Runtime.at(tmp_path)
    result = observer().observe_root_lanes(writer, "JOB-001")
    assert result["issues"] == ["READ_ONLY_RUNTIME_REQUIRED"]
    assert result["lanes"] is None


def test_missing_root_and_child_as_root_never_mean_empty_office(tmp_path):
    _, parent, first, *_ = seed(tmp_path)
    reader = Runtime.at(tmp_path, create=False)
    absent = observer().observe_root_lanes(reader, "JOB-999999")
    assert absent["status"] == "UNAVAILABLE" and absent["lanes"] is None
    assert absent["coverage"]["returned_count"] is None
    child = observer().observe_root_lanes(reader, first.job_id)
    assert child["issues"] == ["NOT_AN_EXACT_ROOT"]


def test_one_snapshot_does_not_mix_a_concurrent_child_commit(tmp_path, monkeypatch):
    writer, parent, *_ = seed(tmp_path)
    reader = Runtime.at(tmp_path, create=False)
    real_read = reader.store.read
    statements, contexts = [], []

    @contextmanager
    def instrumented():
        contexts.append(True)
        with real_read() as connection:
            class ReadConnection:
                def __getattr__(self, name):
                    return getattr(connection, name)

                def execute(self, sql, parameters=()):
                    statements.append(sql)
                    if len(statements) == 2:
                        writer.jobs.create_job("concurrent child", parent_job_id=parent.job_id)
                    return connection.execute(sql, parameters)
            yield ReadConnection()

    monkeypatch.setattr(reader.store, "read", instrumented)
    first = observer().observe_root_lanes(reader, parent.job_id)
    assert len(contexts) == 1 and len(statements) == 2
    assert len(first["lanes"]) == 3
    second = observer().observe_root_lanes(reader, parent.job_id)
    assert len(second["lanes"]) == 4
    assert all(statement.lstrip().startswith("SELECT") for statement in statements)


def test_read_failure_is_unknown_and_does_not_leak_exception_text(tmp_path, monkeypatch):
    _, parent, *_ = seed(tmp_path)
    reader = Runtime.at(tmp_path, create=False)

    @contextmanager
    def failed_read():
        raise OSError("PRIVATE_PATH_AND_CREDENTIAL_SENTINEL")
        yield  # pragma: no cover

    monkeypatch.setattr(reader.store, "read", failed_read)
    result = observer().observe_root_lanes(reader, parent.job_id)
    assert result["status"] == "UNAVAILABLE" and result["lanes"] is None
    assert "PRIVATE_" not in json.dumps(result)
    assert result["coverage"]["completeness"] == "unknown"


@pytest.mark.parametrize("constant,limit,code", [
    ("MAX_SQL_STEPS", 1, "QUERY_BUDGET_EXCEEDED"),
    ("MAX_RESPONSE_BYTES", 1024, "RESPONSE_LIMIT_REACHED"),
])
def test_resource_exhaustion_has_an_explicit_bounded_failure(tmp_path, monkeypatch, constant, limit, code):
    module = observer()
    _, parent, *_ = seed(tmp_path)
    monkeypatch.setattr(module, constant, limit)
    result = module.observe_root_lanes(Runtime.at(tmp_path, create=False), parent.job_id)
    assert result["issues"] == [code]
    assert result["lanes"] is None
    assert len(json.dumps(result).encode()) < 1024


def test_source_times_are_not_refreshed_or_interpreted_as_liveness(tmp_path, monkeypatch):
    writer, parent, first, *_ = seed(tmp_path)
    reader = Runtime.at(tmp_path, create=False)
    native = writer.attempts.get_attempt(writer.jobs.get_job(first.job_id).current_attempt_id)
    def no_clock():
        raise AssertionError("observation must not manufacture a freshness clock")
    monkeypatch.setattr(reader.store, "now_ms", no_clock)
    result = observer().observe_root_lanes(reader, parent.job_id)
    row = next(x for x in result["lanes"] if x["job_id"] == first.job_id)
    assert row["current_attempt"]["checkpoint_sequence"] == native.checkpoint_sequence
    assert "is_alive" not in json.dumps(result) and "is_actionable" not in json.dumps(result)
    assert result["current_permission"] == "NOT_EVALUATED"


def test_cli_is_a_working_fixture_consumer_and_has_no_installed_selector(capsys):
    name = "scripts.executive_lane_observation"
    assert importlib.util.find_spec(name) is not None, "R0 CLI is not implemented"
    cli = importlib.import_module(name)
    assert cli.main(["demo", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["proof_class"] == "FIXTURE_ONLY_NO_PROVIDER_EXECUTION"
    assert len(payload["observation"]["lanes"]) == 3
    assert cli.main(["demo", "--format", "text"]) == 0
    assert "CLAIMED" in capsys.readouterr().out
    with pytest.raises(SystemExit) as refused:
        cli.main(["demo", "--runtime-root", "/var/db/mastermind-executive"])
    assert refused.value.code == 2


def test_queued_job_does_not_reuse_history_and_new_claim_uses_exact_pointer(tmp_path):
    from control_plane.executive_runtime import JobPayload
    writer, parent, first, _, old = seed(tmp_path)
    writer.attempts.fail_attempt(old.attempt.attempt_id,
        fence_generation=old.attempt.fence_generation, lease_token=old.lease_token,
        payload=JobPayload(summary="fixture retry", errors=["synthetic failure"]))
    writer.jobs.requeue_job(first.job_id)
    reader = Runtime.at(tmp_path, create=False)
    queued = observer().observe_root_lanes(reader, parent.job_id)
    row = next(x for x in queued["lanes"] if x["job_id"] == first.job_id)
    assert row["job_status"] == "QUEUED" and row["current_attempt"] is None
    new = writer.attempts.claim_job(first.job_id, worker_id="fixture-a")
    assert new is not None
    later = observer().observe_root_lanes(reader, parent.job_id)
    row = next(x for x in later["lanes"] if x["job_id"] == first.job_id)
    assert row["current_attempt"]["attempt_id"] == new.attempt.attempt_id
    assert old.attempt.attempt_id not in json.dumps(later)


def test_cross_root_attempt_corruption_is_not_disclosed_or_selected(tmp_path):
    from control_plane.executive_runtime import JobPayload
    writer, parent, first, *_ = seed(tmp_path)
    writer.jobs.complete_job(first.job_id, JobPayload(summary="synthetic completed"))
    foreign = writer.jobs.create_job("foreign root")
    foreign_lease = writer.attempts.claim_job(foreign.job_id, worker_id="fixture-a")
    assert foreign_lease is not None
    # Deliberately corrupt ONLY this disposable fixture; production APIs are unchanged.
    with sqlite3.connect(writer.store.path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("UPDATE jobs SET current_attempt_id=? WHERE job_id=?",
                           (foreign_lease.attempt.attempt_id, first.job_id))
    result = observer().observe_root_lanes(Runtime.at(tmp_path, create=False), parent.job_id)
    row = next(x for x in result["lanes"] if x["job_id"] == first.job_id)
    assert row["current_attempt"] is None
    assert row["issues"] == ["CURRENT_ATTEMPT_JOIN_UNAVAILABLE"]
    assert result["status"] == "PARTIAL"
    assert foreign_lease.attempt.attempt_id not in json.dumps(result)
    assert foreign.job_id not in json.dumps(result)


@pytest.mark.parametrize("field,value", [("parent_job_id", "JOB-foreign"),
    ("root_job_id", "JOB-foreign"), ("depth", 99)])
def test_lineage_disagreement_cannot_become_an_inventory_join(tmp_path, field, value):
    module = observer()
    _, parent, *_ = seed(tmp_path)
    result = module.observe_root_lanes(Runtime.at(tmp_path, create=False), parent.job_id)
    rows = result["lanes"]
    rows[1][field] = value
    assert module._valid_graph(rows, parent.job_id) is False


def test_demo_failure_is_nonzero_and_opaque(monkeypatch, capsys):
    cli = importlib.import_module("scripts.executive_lane_observation")
    def fail():
        raise OSError("PRIVATE_EXCEPTION_SENTINEL")
    monkeypatch.setattr(cli, "demonstration", fail)
    assert cli.main(["demo"]) == 1
    assert "PRIVATE_" not in capsys.readouterr().out
