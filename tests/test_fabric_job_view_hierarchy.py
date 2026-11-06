"""Original-root Fabric tracking follows real nested Runtime coordination."""
from __future__ import annotations

import dataclasses

import pytest

from control_plane import fabric_job_view as view
from control_plane.ceo_intent import submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import Runtime, JobStatus, orchestration_digest
from test_executive_coo_hierarchy_cycle import plan_result, finish_result
from test_executive_os_phase1fc import _v2_intent, _register
from test_fabric_job_view_bounded import _snapshot_with_jobs, _use_runtime


def harness(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime)
    root = runtime.jobs.get_job(submit_intent(runtime, _v2_intent(
        business_impact="routine", workstream="WS:FABRIC-HIERARCHY"))["job_id"])
    dispatches = []

    def dispatch(job_id, command_id):
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-1")
        dispatches.append(outcome)
        return outcome

    return runtime, root, CooCycle(runtime, dispatcher=dispatch), dispatches


def _settled_tree(tmp_path):
    runtime, root, cycle, dispatches = harness(tmp_path)
    for _ in range(90):
        outcome = cycle.run_once(root.job_id)
        assert outcome.action not in {"BLOCKED", "RECONCILIATION_REQUIRED"}, outcome
        if outcome.action == "DISPATCHED":
            dispatch = dispatches[-1]
            job = runtime.jobs.get_job(dispatch.attempt.job_id)
            if job.orchestration_role == "plan":
                parent = runtime.jobs.get_job(job.parent_job_id)
                delegation = ({"descendant_limit": 14 - 2 * parent.depth, "max_depth": 3}
                              if parent.depth < 2 else None)
                plan_result(runtime, dispatch, parent, delegation=delegation,
                            count=2 if parent.depth == 2 else 1)
            else:
                finish_result(runtime, dispatch)
        if runtime.jobs.get_job(root.job_id).status == JobStatus.COMPLETED:
            return runtime, runtime.jobs.get_job(root.job_id), runtime.jobs.list_jobs()
    pytest.fail(f"nested cycle did not settle: {outcome}")


def _view(runtime, root):
    return view.read_fabric_view_v3_from_runtime(
        runtime, root.job_id, armed={}, runtime_identity={"db_present": True})["fabric_view"]


def test_completed_nested_tree_keeps_every_job_attempt_and_parent(monkeypatch, tmp_path):
    runtime, root, jobs = _settled_tree(tmp_path)
    _use_runtime(monkeypatch, runtime)
    doc = _view(runtime, root)
    cards = {card["job_id"]: card for card in doc["children"]}
    assert set(cards) == {job.job_id for job in jobs if job.job_id != root.job_id}
    assert doc["unjoined_job_ids"] == []
    assert doc["runtime"]["acquisition"]["provenance"]["state"] == "COMPLETE"
    assert {job.depth for job in jobs} == {0, 1, 2, 3}
    for job in jobs:
        if job.job_id == root.job_id:
            continue
        card = cards[job.job_id]
        assert (card["parent_job_id"], card["root_job_id"], card["depth"]) == (
            job.parent_job_id, root.job_id, job.depth)
        assert card["status"] == "COMPLETED"
        assert job.current_attempt_id in {item["attempt_id"] for item in card["attempts"]}


def test_sibling_coordinators_have_independent_planner_identity(monkeypatch, tmp_path):
    runtime, root, cycle, dispatches = harness(tmp_path)
    assert cycle.run_once(root.job_id).action == "PLANNER_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    plan_result(runtime, dispatches[-1], root, count=2,
                delegation={"descendant_limit": 6, "max_depth": 3})
    admitted = cycle.run_once(root.job_id)
    assert admitted.action == "PLAN_ADMITTED"
    for coordinator_id in admitted.receipt["work_job_ids"]:
        runtime.jobs.create_cycle_planner(
            coordinator_id, command_id=f"coo-cycle:{coordinator_id}:create-planner:0")
    jobs = runtime.jobs.list_jobs()
    _use_runtime(monkeypatch, runtime)
    doc = _view(runtime, root)
    assert doc["unjoined_job_ids"] == []
    planners = [card for card in doc["children"] if card["orchestration_role"] == "plan"]
    assert len(planners) == 3
    assert len({card["parent_job_id"] for card in planners}) == 3
    assert len(doc["children"]) == len(jobs) - 1


@pytest.mark.parametrize("fault", [
    "widen_limit", "widen_depth", "policy", "missing_grant", "extra_field",
    "wrong_source", "v1_coordinator", "retained_limit", "retained_depth",
])
def test_invalid_coordinator_cannot_join_its_descendants(monkeypatch, tmp_path, fault):
    runtime, root, jobs = _settled_tree(tmp_path)
    coordinator = next(job for job in jobs if job.depth == 1
                       and job.orchestration_role == "aggregation")
    cycle = dict(coordinator.orchestration_provenance)
    cycle["hierarchy_grant"] = dict(cycle["hierarchy_grant"])
    if fault == "widen_limit":
        cycle["hierarchy_grant"]["descendant_limit"] = 16
    elif fault == "widen_depth":
        cycle["hierarchy_grant"]["max_depth"] = 4
    elif fault == "policy":
        cycle["hierarchy_grant"]["policy_sha256"] = "f" * 64
    elif fault == "retained_limit":
        cycle["hierarchy_grant"]["descendant_limit"] = 2
    elif fault == "retained_depth":
        cycle["hierarchy_grant"]["max_depth"] = 2
    elif fault == "missing_grant":
        del cycle["hierarchy_grant"]
    elif fault == "extra_field":
        cycle["unrecognized"] = True
    elif fault == "wrong_source":
        cycle["source_id"] = "JOB-999"
    else:
        cycle["schema_version"] = "mastermind.executive_orchestration_provenance/v1"
        del cycle["hierarchy_grant"]
    hostile = dataclasses.replace(
        coordinator, orchestration_provenance=cycle,
        orchestration_provenance_digest=orchestration_digest(cycle))
    _snapshot_with_jobs(monkeypatch, [
        hostile if job.job_id == coordinator.job_id else job for job in jobs])
    _use_runtime(monkeypatch, runtime)
    doc = _view(runtime, root)
    assert {card["orchestration_role"] for card in doc["children"]} == {"plan"}
    assert set(doc["unjoined_job_ids"]) == {
        job.job_id for job in jobs if job.job_id != root.job_id
        and not (job.orchestration_role == "plan" and job.depth == 1)}
    assert doc["capability"]["state"] == "PARTIAL"


@pytest.mark.parametrize("fault", ["orphan", "cycle", "wrong_depth"])
def test_invalid_retained_ancestry_is_explicitly_unjoined(monkeypatch, tmp_path, fault):
    runtime, root, jobs = _settled_tree(tmp_path)
    leaf = next(job for job in jobs if job.depth == 3 and job.orchestration_role == "work")
    changes = ({"parent_job_id": "JOB-999"} if fault == "orphan" else
               {"parent_job_id": leaf.job_id} if fault == "cycle" else {"depth": 4})
    hostile = dataclasses.replace(leaf, **changes)
    _snapshot_with_jobs(monkeypatch, [
        hostile if job.job_id == leaf.job_id else job for job in jobs])
    _use_runtime(monkeypatch, runtime)
    doc = _view(runtime, root)
    assert doc["root"]["job_id"] == root.job_id
    assert doc["children"] == []
    assert set(doc["unjoined_job_ids"]) == {job.job_id for job in jobs if job.job_id != root.job_id}
    assert doc["capability"]["state"] == "PARTIAL"


@pytest.mark.parametrize("role", ["review", "repair"])
def test_related_results_cannot_cross_coordinator_plan_scope(tmp_path, role):
    runtime, root, jobs = _settled_tree(tmp_path)
    leaf = next(job for job in jobs if job.depth == 3 and job.orchestration_role == "work")
    coordinator = next(job for job in jobs if job.job_id == leaf.parent_job_id)
    # The ordinary result relation is valid in one coordinator. Changing only
    # its parent to another same-root coordinator must not join it by step ID.
    foreign_parent = next(job for job in jobs if job.depth == 1
                          and job.orchestration_role == "aggregation")
    reviewed = dataclasses.replace(leaf, job_id="JOB-991")
    rejection = dataclasses.replace(
        leaf, job_id="JOB-992", orchestration_role="review", reviews_job_id=reviewed.job_id)
    cycle = dict(leaf.orchestration_provenance)
    cycle.update(job_id="JOB-993", role=role, source_id=(
        reviewed.job_id if role == "review" else rejection.job_id))
    selected = dataclasses.replace(
        leaf, job_id="JOB-993", orchestration_role=role,
        reviews_job_id=reviewed.job_id if role == "review" else None,
        supersedes_job_id=reviewed.job_id if role == "repair" else None,
        orchestration_provenance=cycle,
        orchestration_provenance_digest=orchestration_digest(cycle))
    relation = {reviewed.job_id: reviewed, rejection.job_id: rejection}
    accepted, _ = view._bounded_cycle_child(
        selected, root=root, root_validated=True,
        coordinator=coordinator, jobs_by_id=relation)
    assert accepted is selected
    relation[reviewed.job_id] = dataclasses.replace(
        reviewed, parent_job_id=foreign_parent.job_id)
    accepted, warning = view._bounded_cycle_child(
        selected, root=root, root_validated=True,
        coordinator=coordinator, jobs_by_id=relation)
    assert accepted is None and "source invalid" in warning
