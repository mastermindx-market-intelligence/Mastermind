"""Hermes binding against actual Executive admission; no providers."""
from contextlib import contextmanager
from dataclasses import replace
import json

import pytest

from control_plane.executive_runtime import PersistenceError, Runtime
from integrations.hermes_delegate.bridge import Bridge
from integrations.hermes_delegate.executive import (
    ExecutiveChildQualification, ExecutiveChildSelection,
)
from integrations.hermes_delegate.tool import dispatch
from test_executive_coo_hierarchy_cycle import harness, plan_result
from test_executive_os_phase1fc import (
    _cycle_through_completed_work, _reviewed_work_reject_and_repair,
)


def selection(job):
    return ExecutiveChildSelection(
        root_job_id=job.root_job_id,
        parent_job_id=job.parent_job_id,
        job_id=job.job_id,
        plan_attempt_id=job.plan_attempt_id,
        plan_digest=job.plan_digest,
        plan_step_id=job.plan_step_id,
        repair_round=job.repair_round,
        expected_current_attempt_id=job.current_attempt_id,
    )


def admitted(tmp_path):
    runtime, root, cycle, dispatches = harness(tmp_path)
    assert cycle.run_once(root.job_id).action == "PLANNER_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    plan_result(runtime, dispatches[-1], root)
    assert cycle.run_once(root.job_id).action == "PLAN_ADMITTED"
    job = next(j for j in runtime.jobs.list_jobs()
               if j.parent_job_id == root.job_id and j.orchestration_role == "work")
    return runtime, root, cycle, dispatches, job


def ledger(runtime):
    with runtime.store.read() as connection:
        return {
            table: tuple(tuple(row) for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY {key}"))
            for table, key in (("jobs", "job_id"), ("attempts", "attempt_id"),
                               ("events", "event_id"))
        }


def fault_read(monkeypatch, runtime, matches, change):
    """Fault only returned rows; keep the real database invariants enabled."""
    original = runtime.store.read

    class FaultCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def row(self, row):
            if row is None:
                return None
            value = dict(row)
            change(value)
            return value

        def fetchone(self):
            return self.row(self.cursor.fetchone())

        def fetchall(self):
            return [self.row(row) for row in self.cursor.fetchall()]

    class FaultConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, parameters=()):
            cursor = self.connection.execute(sql, parameters)
            return FaultCursor(cursor) if matches(sql, parameters) else cursor

        def __getattr__(self, name):
            return getattr(self.connection, name)

    @contextmanager
    def read():
        with original() as connection:
            yield FaultConnection(connection)

    monkeypatch.setattr(runtime.store, "read", read)


def test_host_observes_real_admission_without_creating_or_dispatching(tmp_path):
    runtime, root, _, dispatches, job = admitted(tmp_path)
    chosen = selection(job)
    before = ledger(runtime)
    diagnostic = Bridge(executive_qualification=ExecutiveChildQualification(runtime, chosen))
    observed = diagnostic.inspect_executive_binding()
    assert observed["state"] == "QUALIFIED"
    assert observed["authority"] == "OBSERVATION_ONLY"
    assert observed["live_submit"] is False
    assert observed["root_job_id"] == root.job_id
    assert observed["job_id"] == job.job_id
    assert observed["operation_key"] == f"exec-{job.job_id.lower()}"
    assert observed["session_ref"] == f"asd-session-exec-{job.job_id.lower()}"
    assert observed["current_attempt_id"] is None
    assert observed["attempt_status"] is None
    assert len(dispatches) == 1  # Only the fixture's existing planner.
    assert ledger(runtime) == before

    # No parent-local tracker is populated by qualification, and the model
    # cannot invoke this trusted-host diagnostic or promote it to admission.
    assert diagnostic.status("model-request-0001")["state"] == "NOT_FOUND"
    model_call = json.loads(dispatch({
        "action": "inspect_executive_binding", "idempotency_key": "model-request-0001",
    }, diagnostic))
    assert model_call["state"] == "REFUSED"
    assert diagnostic.submit({})["state"] == "REFUSED"
    assert ledger(runtime) == before

    restarted = Runtime.at(tmp_path)
    assert ExecutiveChildQualification(restarted, chosen).qualify() == observed
    assert ledger(restarted) == before


@pytest.mark.parametrize(("patch", "reason"), [
    ({"root_job_id": "JOB-999"}, "EXECUTIVE_CHILD_NOT_FOUND"),
    ({"parent_job_id": "JOB-999"}, "EXECUTIVE_CHILD_SCOPE_MISMATCH"),
    ({"job_id": "JOB-999"}, "EXECUTIVE_CHILD_NOT_FOUND"),
    ({"plan_attempt_id": "attempt-wrong"}, "EXECUTIVE_PLAN_SELECTION_CHANGED"),
    ({"plan_digest": "0" * 64}, "EXECUTIVE_PLAN_SELECTION_CHANGED"),
    ({"plan_step_id": "STEP-WRONG"}, "EXECUTIVE_PLAN_SELECTION_CHANGED"),
    ({"repair_round": 1}, "EXECUTIVE_PLAN_SELECTION_CHANGED"),
    ({"repair_round": True}, "EXECUTIVE_SELECTION_INVALID"),
    ({"expected_current_attempt_id": "attempt-wrong"}, "EXECUTIVE_CURRENT_ATTEMPT_CHANGED"),
])
def test_changed_host_coordinates_refuse(tmp_path, patch, reason):
    runtime, _, _, _, job = admitted(tmp_path)
    before = ledger(runtime)
    observed = ExecutiveChildQualification(runtime, replace(selection(job), **patch)).qualify()
    assert observed["state"] == "REFUSED"
    assert observed["reason"] == reason
    assert "job_id" not in observed
    assert ledger(runtime) == before


def test_current_attempt_is_owner_identity_and_none_is_not_a_wildcard(tmp_path):
    runtime, _, _, _, _, work, _ = _cycle_through_completed_work(
        tmp_path, intent_id="CEO-HERMES-CURRENT", review_workers=["worker-b"],
    )
    job = runtime.jobs.get_job(work.attempt.job_id)
    observed = ExecutiveChildQualification(runtime, selection(job)).qualify()
    assert observed["state"] == "QUALIFIED"
    assert observed["current_attempt_id"] == work.attempt.attempt_id
    assert observed["attempt_status"] == "COMPLETED"
    assert observed["job_status"] == "COMPLETED"
    stale = replace(selection(job), expected_current_attempt_id=None)
    assert ExecutiveChildQualification(runtime, stale).qualify()["reason"] == (
        "EXECUTIVE_CURRENT_ATTEMPT_CHANGED"
    )


def test_current_repair_observation_refuses_superseded_work(tmp_path):
    runtime, _, _, _, _, work, repair, _, _, _, _ = _reviewed_work_reject_and_repair(
        tmp_path, intent_id="CEO-HERMES-REPAIR", review_workers=["worker-b", "worker-b"],
    )
    old_job = runtime.jobs.get_job(work.attempt.job_id)
    new_job = runtime.jobs.get_job(repair.attempt.job_id)
    before = ledger(runtime)
    assert ExecutiveChildQualification(runtime, selection(old_job)).qualify()["reason"] == (
        "EXECUTIVE_CHILD_SUPERSEDED"
    )
    observed = ExecutiveChildQualification(runtime, selection(new_job)).qualify()
    assert observed["state"] == "QUALIFIED"
    assert observed["observation_kind"] == "CURRENT_PLAN_CHILD"
    assert observed["orchestration_role"] == "repair"
    assert observed["repair_round"] == 1
    assert observed["review_required"] is True
    assert observed["authority"] == "OBSERVATION_ONLY"
    assert "accepted" not in observed
    assert ledger(runtime) == before


def test_corrupt_plan_admission_fails_closed(tmp_path, monkeypatch):
    runtime, _, _, _, job = admitted(tmp_path)
    before = ledger(runtime)
    fault_read(
        monkeypatch, runtime,
        lambda sql, _: "event_type='COO_PLAN_ADMITTED'" in sql,
        lambda row: row.update(payload_json="{}"),
    )
    observed = ExecutiveChildQualification(runtime, selection(job)).qualify()
    assert observed["reason"] == "EXECUTIVE_PLAN_LINEAGE_UNVERIFIED"
    assert "operation_key" not in observed
    assert ledger(runtime) == before


def test_raw_missing_root_cannot_be_normalized_into_a_binding(tmp_path, monkeypatch):
    runtime, root, _, _, job = admitted(tmp_path)
    before = ledger(runtime)
    fault_read(
        monkeypatch, runtime,
        lambda sql, params: sql == "SELECT * FROM jobs WHERE job_id=?"
        and params == (root.job_id,),
        lambda row: row.update(root_job_id=None),
    )
    assert ExecutiveChildQualification(runtime, selection(job)).qualify()["reason"] == (
        "EXECUTIVE_ROOT_UNVERIFIED"
    )
    assert ledger(runtime) == before


def test_wrong_attempt_owner_refuses(tmp_path, monkeypatch):
    runtime, _, _, root, _, work, _ = _cycle_through_completed_work(
        tmp_path, intent_id="CEO-HERMES-ATTEMPT", review_workers=["worker-b"],
    )
    job = runtime.jobs.get_job(work.attempt.job_id)
    before = ledger(runtime)
    fault_read(
        monkeypatch, runtime,
        lambda sql, params: sql == "SELECT * FROM attempts WHERE attempt_id=?"
        and params == (work.attempt.attempt_id,),
        lambda row: row.update(job_id=root.job_id),
    )
    observed = ExecutiveChildQualification(runtime, selection(job)).qualify()
    assert observed["reason"] == "EXECUTIVE_CURRENT_ATTEMPT_UNVERIFIED"
    assert ledger(runtime) == before


def test_failed_read_close_cannot_return_a_success_or_private_text(tmp_path, monkeypatch):
    runtime, _, _, _, job = admitted(tmp_path)
    original = runtime.store.read

    @contextmanager
    def fails_on_exit():
        with original() as connection:
            yield connection
        raise PersistenceError("private principal /private/runtime.sqlite secret")

    monkeypatch.setattr(runtime.store, "read", fails_on_exit)
    observed = ExecutiveChildQualification(runtime, selection(job)).qualify()
    assert observed["state"] == "UNAVAILABLE"
    assert observed["reason"] == "EXECUTIVE_READ_UNAVAILABLE"
    assert "private" not in json.dumps(observed)
    assert "job_id" not in observed


def test_default_host_inspection_remains_unbound():
    observed = Bridge().inspect_executive_binding()
    assert observed["state"] == "REFUSED"
    assert observed["reason"] == "EXECUTIVE_QUALIFICATION_NOT_BOUND"
    assert observed["live_submit"] is False
