"""Run-once coordination across one original-root hierarchy; no providers."""
import pytest

from control_plane.ceo_intent import submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_coo_policy import HIERARCHY_POLICY_SHA256
from control_plane.executive_runtime import Runtime, JobStatus, OrchestrationDispatchOutcome, StateConflict
from test_executive_os_phase1fc import _v2_intent, _register, _complete_ohf_role


def harness(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime)
    root = runtime.jobs.get_job(submit_intent(
        runtime, _v2_intent(business_impact="routine"))["job_id"])
    dispatches = []

    def dispatch(job_id, command_id):
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-1")
        assert isinstance(outcome, OrchestrationDispatchOutcome)
        dispatches.append(outcome)
        return outcome

    return runtime, root, CooCycle(runtime, dispatcher=dispatch), dispatches


def plan_result(runtime, dispatch, coordinator, *, delegation=None, count=1, dependencies=False):
    steps = [{
        "ordinal": i, "step_id": f"STEP-{i}", "objective": "Bounded read-only outcome",
        "business_impact": "routine", "review_required": False,
        "requested_authorities": ["READ"], "allowed_write_paths": [],
        "validation_ids": [], "attempt_limit": 1, "cost_class": "small",
        "prerequisite_step_ids": ["STEP-0"] if dependencies and i else [],
        "delegation": delegation,
    } for i in range(count)]
    body = {"schema_version": "mastermind.execution_plan/v5",
            "root_job_id": coordinator.root_job_id, "coordinator_job_id": coordinator.job_id,
            "plan_attempt_id": dispatch.attempt.attempt_id, "steps": steps}
    _complete_ohf_role(runtime, dispatch, body,
                       identity_seed=10000 + int(dispatch.attempt.job_id.split("-")[1]))


def finish_result(runtime, dispatch):
    job = runtime.jobs.get_job(dispatch.attempt.job_id)
    if job.orchestration_role == "aggregation":
        handoff = runtime.jobs.get_cycle_handoff(job.job_id)
        keys = {"ordinal", "plan_step_id", "current_job_id", "current_attempt_id",
                "current_result_digest", "repair_round", "review_required",
                "qualifying_review_job_id", "qualifying_review_attempt_id",
                "qualifying_review_result_digest"}
        body = {"schema_version": handoff["aggregate_result_schema"],
                "coordinator_job_id": job.job_id,
                **{k: handoff[k] for k in ("root_job_id", "handoff_digest", "policy_sha",
                                          "plan_attempt_id", "plan_digest")},
                "revisions": [{k: v for k, v in row.items() if k in keys}
                              for row in handoff["revisions"]],
                "aggregate_summary": "Every scoped child returned", "evidence_digests": []}
    else:
        body = {"schema_version": "mastermind.work_result/v1", "root_job_id": job.root_job_id,
                "plan_attempt_id": job.plan_attempt_id, "plan_digest": job.plan_digest,
                "plan_step_id": job.plan_step_id, "repair_round": job.repair_round,
                "artifacts": [], "evidence_digests": []}
    _complete_ohf_role(runtime, dispatch, body,
                       identity_seed=20000 + int(job.job_id.split("-")[1]))


def admit_root_coordinator(runtime, root, cycle, dispatches):
    assert cycle.run_once(root.job_id).action == "PLANNER_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    plan_result(runtime, dispatches[-1], root,
                delegation={"descendant_limit": 14, "max_depth": 3})
    admitted = cycle.run_once(root.job_id)
    assert admitted.action == "PLAN_ADMITTED", admitted
    return runtime.jobs.get_job(admitted.receipt["work_job_ids"][0])


def test_parent_cycle_creates_nested_planner_before_dispatching_coordinator(tmp_path):
    runtime, root, cycle, dispatches = harness(tmp_path)
    coordinator = admit_root_coordinator(runtime, root, cycle, dispatches)
    before = len(dispatches)
    outcome = cycle.run_once(root.job_id)
    assert outcome.action == "PLANNER_CREATED", outcome
    assert len(dispatches) == before
    assert outcome.root_job_id == root.job_id
    assert outcome.receipt["coordinator_job_id"] == coordinator.job_id
    planner = runtime.jobs.get_job(outcome.selected_job_id)
    assert (planner.parent_job_id, planner.root_job_id, planner.depth) == (
        coordinator.job_id, root.job_id, 2)


@pytest.mark.parametrize("dependencies", [False, True])
def test_original_root_cycle_finishes_four_levels_with_pinned_policy(tmp_path, dependencies):
    runtime, root, cycle, dispatches = harness(tmp_path)
    seen_depths = set()
    handoffs = []
    for _ in range(90):
        outcome = cycle.run_once(root.job_id)
        assert outcome.root_job_id == root.job_id
        assert outcome.action not in {"BLOCKED", "RECONCILIATION_REQUIRED"}, outcome
        if outcome.action == "DISPATCHED":
            dispatch = dispatches[-1]
            job = runtime.jobs.get_job(dispatch.attempt.job_id)
            seen_depths.add(job.depth)
            if job.orchestration_role == "plan":
                parent = runtime.jobs.get_job(job.parent_job_id)
                delegation = ({"descendant_limit": 14 - 2 * parent.depth, "max_depth": 3}
                              if parent.depth < 2 else None)
                plan_result(runtime, dispatch, parent, delegation=delegation,
                            count=2 if parent.depth == 2 else 1,
                            dependencies=dependencies and parent.depth == 2)
            else:
                if job.orchestration_role == "aggregation" and job.parent_job_id is not None:
                    # Reconcile the same coordinator command, not a new command
                    # in its parent's namespace or another Attempt.
                    replay = cycle.run_once(root.job_id)
                    assert replay.command_id == outcome.command_id
                    assert dispatches[-1].attempt.attempt_id == dispatch.attempt.attempt_id
                finish_result(runtime, dispatch)
        if outcome.action == "HANDOFF_CREATED":
            handoff = runtime.jobs.get_cycle_handoff(outcome.selected_job_id)
            assert handoff["root_job_id"] == root.job_id
            assert handoff["policy_sha"] == HIERARCHY_POLICY_SHA256
            handoffs.append(outcome.selected_job_id)
        if runtime.jobs.get_job(root.job_id).status == JobStatus.COMPLETED:
            break
    else:
        pytest.fail(f"cycle did not settle: {outcome}")
    assert seen_depths == {0, 1, 2, 3}
    assert len(handoffs) == 3 and handoffs[-1] == root.job_id
    jobs = runtime.jobs.list_jobs()
    assert len(jobs) == 8 and {j.root_job_id for j in jobs} == {root.job_id}
    assert all(j.status == JobStatus.COMPLETED for j in jobs)
    replay = cycle.run_once(root.job_id)
    assert replay.action == "NO_ACTION"
    assert replay.receipt["policy_sha"] == HIERARCHY_POLICY_SHA256
    assert CooCycle(Runtime.at(tmp_path)).run_once(root.job_id).action == "NO_ACTION"


def test_nested_dispatch_unavailable_block_replays_in_original_root(tmp_path):
    runtime, root, cycle, dispatches = harness(tmp_path)
    coordinator = admit_root_coordinator(runtime, root, cycle, dispatches)
    assert cycle.run_once(root.job_id).action == "PLANNER_CREATED"
    inert = CooCycle(runtime)
    outcome = inert.run_once(root.job_id)
    assert outcome.action == "BLOCKED"
    assert outcome.root_job_id == root.job_id
    assert outcome.receipt["coordinator_job_id"] == coordinator.job_id
    assert outcome.receipt["policy_sha"] == HIERARCHY_POLICY_SHA256
    assert inert.run_once(root.job_id) == outcome
    assert runtime.jobs.get_job(root.job_id).attempt_count == 0


def test_nested_uncertain_dispatch_reconciles_same_attempt_before_new_work(tmp_path):
    runtime, root, cycle, dispatches = harness(tmp_path)
    coordinator = admit_root_coordinator(runtime, root, cycle, dispatches)
    planner_created = cycle.run_once(root.job_id)
    assert planner_created.action == "PLANNER_CREATED"

    def lost_return(job_id, command_id):
        cycle.dispatcher(job_id, command_id)
        return None

    with pytest.raises(StateConflict, match="ambiguous"):
        CooCycle(runtime, dispatcher=lost_return).run_once(root.job_id)
    launched = dispatches[-1]
    marker = runtime.jobs.pending_cycle_dispatch_effect_unknown(coordinator.job_id)
    assert marker["root_job_id"] == root.job_id
    assert marker["coordinator_job_id"] == coordinator.job_id
    count = len(runtime.jobs.list_jobs())
    reconciled = cycle.run_once(root.job_id)
    assert reconciled.action == "DISPATCHED"
    assert reconciled.selected_job_id == planner_created.selected_job_id
    assert dispatches[-1].attempt.attempt_id == launched.attempt.attempt_id
    assert len(runtime.jobs.list_jobs()) == count
    assert runtime.jobs.pending_cycle_dispatch_effect_unknown(coordinator.job_id) is None


def test_independent_coordinator_progresses_while_sibling_return_is_unknown(tmp_path):
    runtime, root, cycle, dispatches = harness(tmp_path)
    _register(runtime, "worker-2")
    assert cycle.run_once(root.job_id).action == "PLANNER_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    plan_result(runtime, dispatches[-1], root, count=2,
                delegation={"descendant_limit": 6, "max_depth": 3})
    admitted = cycle.run_once(root.job_id)
    first, second = admitted.receipt["work_job_ids"]
    first_planner = cycle.run_once(root.job_id)
    assert first_planner.action == "PLANNER_CREATED"

    def first_return_lost(job_id, command_id):
        cycle.dispatcher(job_id, command_id)
        return None

    with pytest.raises(StateConflict, match="ambiguous"):
        CooCycle(runtime, dispatcher=first_return_lost).run_once(root.job_id)
    first_attempt = dispatches[-1].attempt.attempt_id
    unknown = runtime.jobs.pending_cycle_dispatch_effect_unknown(first)
    assert unknown is not None
    # The existing original operation stays untouched while the independent
    # reservation gets its first planner and Attempt.
    second_planner = cycle.run_once(root.job_id)
    assert second_planner.action == "PLANNER_CREATED", second_planner
    assert second_planner.receipt["coordinator_job_id"] == second

    def second_dispatch(job_id, command_id):
        assert runtime.jobs.get_job(job_id).parent_job_id == second
        return runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-2")

    dispatched = CooCycle(runtime, dispatcher=second_dispatch).run_once(root.job_id)
    assert dispatched.action == "DISPATCHED"
    assert dispatched.selected_job_id == second_planner.selected_job_id
    assert runtime.jobs.pending_cycle_dispatch_effect_unknown(first) == unknown
    assert runtime.jobs.get_job(first_planner.selected_job_id).current_attempt_id == first_attempt
    assert {j.root_job_id for j in runtime.jobs.list_jobs()} == {root.job_id}
