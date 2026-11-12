"""The selected-child fixture proves its actual Mission and original claim.

No socket, provider or installed grant is substituted here. This exercises the
fixture's non-transport preconditions under a real disposable namespace owner;
the existing selected-child service suite retains its native transport checks.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from control_plane import ceo_intent, executive_runtime as er
from control_plane.executive_service import ExecutiveControlService
from tests.selected_child_mission import SelectedChildMission, WORK_REF, continuation_source
from tests.test_coo_transaction_authority import namespace_owner
from tests.test_executive_coo_ready_frontier_service import _register_peer
from tests.test_executive_service import _capture_projection, _config, _coo_intent
from tests.test_hermes_selected_child_dispatch import _admit_work_child


@pytest.fixture
def continuation_owner(tmp_path):
    config, source = continuation_source(_config(tmp_path, coo_autonomy_armed=True,
        coo_tick_interval_seconds=3600.0))
    planner_returns = []
    service = ExecutiveControlService(config, autonomy_guard=lambda: None,
        terminal_return_projector=lambda candidate: _capture_projection(planner_returns, candidate),
        ceo_ingress_dialogue_source_provider=lambda _intent, _work: source)
    runtime = service.runtime = er.Runtime.at(config.runtime_root)
    service._register_worker()
    _register_peer(service)
    intent = _coo_intent(config, "selected-mission")
    intent["workstream"] = WORK_REF
    receipt = ceo_intent.submit_intent(runtime, intent,
        workspace_root=config.proof_workspace_root,
        execution_binding=service._require_current_coo_binding(), dialogue_source=source)
    root = runtime.jobs.get_job(receipt["job_id"])
    directory = tmp_path / "selected-child-authority"
    directory.mkdir()
    with namespace_owner(runtime) as namespace:
        service._namespace_custody = namespace
        mission = service._selected_child_mission = SelectedChildMission(service, root, directory)
        yield SimpleNamespace(service=service, runtime=runtime, mission=mission,
            namespace=namespace, root=root, planner_returns=planner_returns)
        assert not runtime.store._write_connections


@pytest.fixture
def continuation(continuation_owner):
    f = continuation_owner
    f.child = asyncio.run(_admit_work_child(f.service, f.root))
    f.command = f"coo-cycle:{f.child.parent_job_id}:dispatch:{f.child.job_id}:attempt:1"
    assert len(f.planner_returns) == 1
    assert f.runtime.jobs.get_job(f.planner_returns[0].job_id).orchestration_role == "plan"
    return f


def _claim(f, guard):
    child = f.child
    selection = er.ExpectedChildSelection(root_job_id=child.root_job_id,
        parent_job_id=child.parent_job_id, job_id=child.job_id,
        plan_attempt_id=child.plan_attempt_id, plan_digest=child.plan_digest,
        plan_step_id=child.plan_step_id, repair_round=child.repair_round,
        expected_current_attempt_id=child.current_attempt_id,
        command_id=f.command, attempt_ordinal=1)
    with er.expected_child_selection(selection, admission_guard=guard,
            requester_context=f.mission.facts["context"],
            requester_capability_profile_digest=f.mission.facts["capability_profile_digest"]):
        return f.runtime.attempts.dispatch_cycle_job(child.job_id,
            command_id=f.command, worker_id=f.service.config.worker_id)


def test_current_continuation_uses_same_runtime_for_public_mission_and_live_claim(continuation):
    f = continuation
    assert f.mission.workspace.runtime is f.runtime
    assert f.mission.require_current().owner_observation_state == "SAME"
    observations = []
    def guard():
        state = f.mission.workspace._coo_guard_mission_state(WORK_REF)
        assert state.read_state == state.owner_observation_state == "LIVE_TRANSACTION"
        assert state.qualified and state.root_job_id == f.root.job_id
        f.mission.provider.guard_dialogue(**f.mission.facts)
        observations.append(state)
    result = _claim(f, guard)
    assert isinstance(result, er.OrchestrationDispatchOutcome)
    assert result.attempt.job_id == f.child.job_id and len(observations) == 2
    assert f.runtime.jobs.get_job(f.child.job_id).attempt_count == 1
    assert er._current_coo_write_authority(f.runtime.store) is None


@pytest.mark.parametrize("depth", [1, 2])
def test_multiple_completed_planners_preserve_original_candidate_conflict(continuation_owner, tmp_path, depth):
    from control_plane.coo_principal_mandate import _mission_state
    from tests.test_hermes_nested_selected_child import _nested
    from tests.test_joint_api_project_owner import publish_planner_return_async
    f = continuation_owner
    nested = _nested(f.service, f.root, tmp_path, coordinator_depth=depth)
    f.child = nested.leaf
    f.command = f"coo-cycle:{f.child.parent_job_id}:dispatch:{f.child.job_id}:attempt:1"
    planners = [job for job in f.runtime.jobs.list_jobs()
                if job.root_job_id == f.root.job_id and job.orchestration_role == "plan"
                and job.status.value == "COMPLETED"]
    assert len(planners) == depth + 1
    root_planner = next(job for job in planners if job.parent_job_id == f.root.job_id)
    asyncio.run(publish_planner_return_async(f.service, root_planner))
    f.mission.publish()
    card = next(row for row in f.mission.cache.snapshot().document["autonomy"]["responsibilities"]
                if row["responsibility_ref"] == WORK_REF)
    assert card["dispatch"]["evidence"]["w3c_reason"] == "W3C_CANDIDATE_CONFLICT"
    state = _mission_state(f.mission.workspace.read_mission_for_work_ref(WORK_REF),
        expected_work_ref=WORK_REF)
    assert not state.qualified and state.reconciliation_required
    with pytest.raises(ValueError, match="installed COO authority unavailable"):
        _claim(f, lambda: f.mission.provider.guard_dialogue(**f.mission.facts))
    assert f.runtime.jobs.get_job(f.child.job_id).attempt_count == 0
    assert f.runtime.store.get_event_by_command_id(f.command) is None


@pytest.mark.parametrize("change", ["source_revoked", "cache_stopping", "namespace_release"])
def test_continuation_owner_change_after_allocation_rolls_back_original_claim(continuation, change):
    f = continuation
    seen = []
    def guard():
        scope = er._current_coo_write_authority(f.runtime.store)
        snapshot, _ = scope.read_root()
        current = next(row for row in snapshot.jobs if row.job_id == f.child.job_id)
        seen.append(current.attempt_count)
        if current.attempt_count:
            if change == "source_revoked":
                f.mission.config["missions"][0]["enabled"] = False
            elif change == "cache_stopping":
                f.mission.owner.state_stopping = True
            else:
                f.namespace._closing = True
        f.mission.provider.guard_dialogue(**f.mission.facts)
    with pytest.raises(ValueError, match="installed COO authority unavailable"):
        _claim(f, guard)
    assert seen == [0, 1]
    assert f.runtime.jobs.get_job(f.child.job_id).attempt_count == 0
    assert f.runtime.store.get_event_by_command_id(f.command) is None
    assert er._current_coo_write_authority(f.runtime.store) is None
