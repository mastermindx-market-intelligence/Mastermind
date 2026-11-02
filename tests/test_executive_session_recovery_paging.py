"""Root-scoped read-only triage across a real SQLite fleet; no provider launch."""
from __future__ import annotations

import dataclasses

import pytest

from control_plane.ceo_intent import submit_intent
from control_plane.executive_runtime import Runtime
from control_plane.executive_session_recovery import project_root_recovery
from test_executive_quota_rollover_runtime import _fixture, _commit
from test_executive_retry_atomicity import _intent


def _fleet(tmp_path, size=30):
    runtime, root, planner, attempt = _fixture(tmp_path)
    # Materialize a projection fixture only: these rows do not claim or dispatch
    # workers. Existing lifecycle tests independently cover admitted transitions.
    with runtime.store.transaction() as con:
        row = dict(con.execute("SELECT * FROM jobs WHERE job_id=?", (planner.job_id,)).fetchone())
        for index in range(size - 1):
            item = dict(row, job_id=f"PAGING-{index:03d}", status="QUEUED",
                        current_attempt_id=None, assigned_worker_id=None,
                        assigned_quota_class=None, attempt_count=0, checkpoint_json=None,
                        orchestration_role="work", plan_step_id=f"step-{index:03d}",
                        plan_attempt_id=attempt.attempt_id, plan_digest="b" * 64,
                        repair_round=0)
            con.execute(f"INSERT INTO jobs ({','.join(item)}) VALUES ({','.join('?' for _ in item)})",
                        tuple(item.values()))
    return runtime, root, planner, attempt


def test_thirty_logical_jobs_page_once_each_without_another_store(tmp_path):
    runtime, root, planner, attempt = _fleet(tmp_path)
    before = len(runtime.events.list_events())
    cursor = None
    observed = []
    for _ in range(5):
        view = project_root_recovery(runtime, root.job_id, limit=7, after_job_id=cursor)
        assert view["page_consistency"] == "LIVE_KEYSET"
        assert view["total_jobs"] == 30
        assert view["root_status"] == runtime.jobs.get_job(root.job_id).status.value
        assert view["returned_counts_only"] is True
        assert view["observed_event_id"] >= 1
        observed.extend(item["job_id"] for item in view["jobs"])
        cursor = view["next_after_job_id"]
        if not view["has_more"]:
            assert cursor is None
            break
    assert len(observed) == len(set(observed)) == 30
    assert observed == sorted(observed)
    assert planner.job_id in observed
    assert len(runtime.events.list_events()) == before
    assert runtime.jobs.get_job(planner.job_id).current_attempt_id == attempt.attempt_id


def test_queue_wait_preserves_predecessor_pool_state_without_claiming_eligibility(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    assert _commit(runtime, root, job, attempt).action == "REQUEUED"
    item = project_root_recovery(runtime, root.job_id)["jobs"][0]
    assert item["previous_quota_class"] == "default"
    assert item["previous_pool_status"] == "RATE_LIMITED"
    assert item["capacity_assessment"] == "NOT_EVALUATED"
    assert item["attempts_remaining"] == 1
    assert item["parent_job_id"] == root.job_id
    assert item["orchestration_role"] == "plan"
    assert item["queue_position"] is None
    assert item["capacity_eta"] is None


def test_current_attempt_projects_registered_route_without_account_or_host_secrets(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    item = project_root_recovery(runtime, root.job_id)["jobs"][0]
    assert item["current_worker_id"] == "pool-a"
    assert item["current_quota_class"] == "default"
    assert item["current_pool_status"] == "RATE_LIMITED"
    assert item["current_provider"] == "codex"
    assert item["current_model"] is None
    assert item["route_observation_scope"] == "REGISTERED_QUOTA_NOT_SERVED_MODEL"
    assert "account_label" not in item and "provider_session_id" not in item
    assert "lease_token" not in item and "metadata" not in item


def test_foreign_root_cursor_is_refused(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    other = submit_intent(runtime, _intent("PAGING-FOREIGN"))["job_id"]
    other_child = runtime.jobs.create_cycle_planner(other,
        command_id=f"coo-cycle:{other}:create-planner:0")
    with pytest.raises(ValueError, match="cursor"):
        project_root_recovery(runtime, root.job_id, after_job_id=other_child.job_id)


@pytest.mark.parametrize("cursor", ["", " ", "missing", "\n", [], True, 1])
def test_invalid_or_absent_cursor_is_not_a_new_root_or_ignored(cursor, tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    with pytest.raises((ValueError, TypeError)):
        project_root_recovery(runtime, root.job_id, after_job_id=cursor)


def test_root_itself_cannot_be_a_worker_page_cursor(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    with pytest.raises(ValueError, match="cursor"):
        project_root_recovery(runtime, root.job_id, after_job_id=root.job_id)


def test_empty_final_page_is_explicit_and_has_no_next_cursor(tmp_path):
    runtime, root, job, attempt = _fleet(tmp_path, size=3)
    all_jobs = project_root_recovery(runtime, root.job_id)
    page = project_root_recovery(runtime, root.job_id, after_job_id=all_jobs["jobs"][-1]["job_id"])
    assert page["jobs"] == [] and page["included_count"] == 0
    assert page["has_more"] is False and page["next_after_job_id"] is None
    assert page["total_jobs"] == 3


def test_capacity_status_changes_are_observations_not_automatic_restart(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    assert _commit(runtime, root, job, attempt).action == "REQUEUED"
    runtime.workers.release_worker("pool-a", quota_class="default")
    other = runtime.jobs.create_job("Occupy the returned test slot", requested_authorities=["READ"],
        constraints={"required_capabilities": ["read"], "eligible_quota_classes": ["default"]})
    occupied = runtime.attempts.claim_job(other.job_id, worker_id="pool-a", quota_class="default")
    assert occupied is not None
    before = len(runtime.events.list_events())
    item = project_root_recovery(runtime, root.job_id)["jobs"][0]
    assert item["previous_pool_status"] == "BUSY"
    assert item["next_action"] == "WAIT_FOR_EXISTING_SCHEDULER"
    assert item["stop_reason"] == "QUOTA_OR_RATE_LIMIT"
    assert len(runtime.events.list_events()) == before


def test_orphaned_route_observation_stays_unknown_without_hiding_worker(tmp_path):
    runtime, root, job, attempt = _fixture(tmp_path)
    # No alteration of keys/leases: make only the observed provider field empty.
    with runtime.store.transaction() as con:
        con.execute("UPDATE worker_quota_classes SET model=NULL WHERE worker_id='pool-a'")
    item = project_root_recovery(runtime, root.job_id)["jobs"][0]
    assert item["current_model"] is None
    assert item["capacity_assessment"] == "NOT_EVALUATED"


def test_root_diagnostic_reports_existing_reviewed_fanout_without_granting_it(tmp_path):
    runtime, root, planner, attempt = _fixture(tmp_path)
    before = len(runtime.events.list_events())
    view = project_root_recovery(runtime, root.job_id)
    policy = view["reviewed_coo_policy"]
    assert policy["max_fan_out_per_parent"] == 8
    assert policy["max_children_total"] == 16
    assert policy["max_depth"] == 1
    assert policy["direct_children_observed"] == 1
    assert policy["state"] == "WITHIN_REVIEWED_BOUNDS"
    assert policy["capacity_admitted_by_view"] is False
    assert policy["one_root_can_admit_30_workers"] is False
    assert policy["native_fabric_lease_capacity_unchanged"] is True
    assert len(runtime.events.list_events()) == before


def test_thirty_fixture_rows_are_not_claimed_as_thirty_admitted_coo_children(tmp_path):
    runtime, root, planner, attempt = _fleet(tmp_path, size=30)
    before = len(runtime.events.list_events())
    view = project_root_recovery(runtime, root.job_id, limit=30)
    policy = view["reviewed_coo_policy"]
    assert policy["direct_children_observed"] == 30
    assert policy["state"] == "EXCEEDS_REVIEWED_CHILD_CEILING"
    assert policy["max_children_total"] == 16
    assert policy["one_root_can_admit_30_workers"] is False
    assert policy["capacity_admitted_by_view"] is False
    assert view["total_jobs"] == 30
    assert len(runtime.events.list_events()) == before


def test_thirty_under_one_strict_coo_root_is_rejected_by_reviewed_plan_policy():
    from control_plane.executive_coo_policy import CooCyclePolicy, CooCyclePolicyError
    policy = CooCyclePolicy.load()
    assert policy.reserved_children_total((False,) * 8) == 9
    with pytest.raises(CooCyclePolicyError, match="fan-out"):
        policy.reserved_children_total((False,) * 30)
    with pytest.raises(CooCyclePolicyError, match="max_children_total"):
        policy.reserved_children_total((True,) * 2)
