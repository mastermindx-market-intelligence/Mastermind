"""Real current-C Mission and source grant reproof in original COO writes."""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from control_plane import executive_runtime as er
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.coo_principal_mandate import _mission_state
from integrations.mastermind_executive_app.coo_binding import principal_frame
from tests.test_coo_project_help_authority import full_joined, owner, env, isolated_git_env, identity
from tests.test_coo_requester_return import _finish, _read, _ack, _events
from tests.test_coo_transaction_authority import namespace_owner, assert_unclaimed
from tests.test_joint_api_project_owner import current_joint_project


def claim_fixture(f):
    context = PrincipalAdmissionContext(**f.frame["principal_context"])
    captured = f.provider.capture_selected_child_target(principal=principal_frame(f.principal),
        context=context, work_ref=f.work, root_job_id=f.root, child_job_ids=[f.work_child.job_id])
    selection = er.ExpectedChildSelection(**captured["children"][0])
    return SimpleNamespace(runtime=f.j["runtime"], root=f.root_job, child=f.work_child,
        selection=selection, command=selection.command_id, context=context,
        capability=f.profile.profile_digest, worker=f.service.config.worker_id)


def claim_actual(c, guard):
    with er.expected_child_selection(c.selection, admission_guard=guard,
            requester_context=c.context, requester_capability_profile_digest=c.capability):
        result = c.runtime.attempts.dispatch_cycle_job(c.child.job_id,
            command_id=c.command, worker_id=c.worker)
    assert isinstance(result, er.OrchestrationDispatchOutcome), result
    return result


def test_actual_mission_and_grant_can_claim_then_ack_under_original_namespace(current_joint_project):
    f = current_joint_project
    c = claim_fixture(f)
    previous = f.workspace._bounded_runtime
    states = []
    with namespace_owner(c.runtime) as namespace:
        # Same closure-shaped producer as the installed phase1c factory.
        f.workspace._bounded_runtime = lambda actual: namespace.bound_runtime(actual)
        try:
            public = _mission_state(f.workspace.read_mission_for_work_ref(f.work), expected_work_ref=f.work)
            assert public.qualified is True
            def guard():
                state = f.workspace._coo_guard_mission_state(f.work)
                assert state.read_state == state.owner_observation_state == "LIVE_TRANSACTION"
                assert dataclasses.replace(state, read_state=public.read_state,
                    owner_observation_state=public.owner_observation_state) == public
                states.append(state)
                f.provider.guard_dialogue(context=c.context, root_job_id=f.root,
                    capability_profile_digest=c.capability)
            dispatch = claim_actual(c, guard)
            assert len(states) == 2
            _finish(c, dispatch)
            original = _read(c)
            def acknowledge_current():
                row, principal, authority = f.provider.source.for_principal(principal_frame(f.principal), f.work)
                f.provider._require_selected_child_project_scope(row, f.work, f.root)
                state = f.workspace._coo_guard_mission_state(f.work)
                assert state.work_ref == f.work and state.root_job_id == f.root
                assert authority.capability_profile_digest == c.capability
                assert "acknowledge_selected_child_result" in authority.principal_actions
                # Explicit receipt currentness is association-only. The
                # production service also preserves this narrower contract.
            result = _ack(c, {"action": "acknowledge_result", "command": c.command, "result": original},
                currentness_guard=acknowledge_current)
            assert result["consumption"] is not None and len(_events(c)) == 1
            after = f.workspace.read_mission_for_work_ref(f.work)
            assert after["source"]["owner_observation"]["state"] == "SAME"
            assert not c.runtime.store._write_connections
        finally:
            f.workspace._bounded_runtime = previous


@pytest.mark.parametrize("boundary", ["source_revoked", "stale_cache", "namespace_release"])
def test_actual_owner_change_after_attempt_allocation_prevents_commit(current_joint_project, monkeypatch, boundary):
    f = current_joint_project
    c = claim_fixture(f)
    previous = f.workspace._bounded_runtime
    seen = []
    with namespace_owner(c.runtime) as namespace:
        f.workspace._bounded_runtime = lambda actual: namespace.bound_runtime(actual)
        original = f.workspace._coo_guard_mission_state
        def observe_then_change(work):
            state = original(work)
            scope = er._current_coo_write_authority(c.runtime.store)
            snapshot, _ = scope.read_root()
            child = next(row for row in snapshot.jobs if row.job_id == c.child.job_id)
            seen.append(child.attempt_count)
            if child.attempt_count:
                if boundary == "source_revoked":
                    f.coo["missions"][0]["enabled"] = False
                elif boundary == "stale_cache":
                    f.cache.owner.state_stopping = True
                else:
                    namespace._closing = True
            return state
        monkeypatch.setattr(f.workspace, "_coo_guard_mission_state", observe_then_change)
        def guard():
            f.provider.guard_dialogue(context=c.context, root_job_id=f.root,
                capability_profile_digest=c.capability)
        try:
            with pytest.raises(ValueError, match="installed COO authority unavailable"):
                claim_actual(c, guard)
            assert 1 in seen
            assert_unclaimed(c)
        finally:
            f.workspace._bounded_runtime = previous
