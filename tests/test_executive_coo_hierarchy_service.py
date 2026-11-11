"""Exercise retained nested coordination through the service dispatch owner.

Only physical provider execution is inert. Job/Attempt claims, typed result seals,
plan admission, hierarchy budgets and terminal command recovery use Runtime.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import JobStatus, Runtime, StateConflict
from control_plane.executive_service import ServiceError
from control_plane.executive_supervisor import _planner_routing_options
from tests.test_executive_coo_hierarchy_cycle import finish_result
from tests.test_executive_coo_ready_frontier_service import _register_peer
from tests.test_executive_os_phase1fc import _complete_ohf_role, _review_body
from tests.test_executive_service import (
    _config, _coo_intent, _request, _service, short_socket_root,
)


@asynccontextmanager
async def _bound_service(tmp_path, short_socket_root, *, name, material=False):
    config = _config(
        tmp_path, socket_root=short_socket_root, coo_autonomy_armed=True,
        coo_tick_interval_seconds=3600.0,
    )
    service, holder = _service(tmp_path, config=config)
    await service.start()
    try:
        assert (await _request(service, "register-worker"))["ok"] is True
        _register_peer(service)
        intent = _coo_intent(config, name)
        if material:
            intent["business_impact"] = "material"
        receipt = service._submit_service_intent(intent)
        root = service.runtime.jobs.get_job(receipt["job_id"])
        yield service, holder["supervisor"], root
    finally:
        await service.close()


def _plan_body(dispatch, coordinator, *, delegation=None, placement=None):
    step = {
        "ordinal": 0, "step_id": "STEP-0", "objective": "Complete the bounded outcome",
        "business_impact": "routine", "review_required": False,
        "requested_authorities": ["READ"], "allowed_write_paths": [],
        "validation_ids": [], "attempt_limit": 1, "cost_class": "small",
        "prerequisite_step_ids": [], "delegation": delegation,
    }
    if placement is not None:
        step["placement"] = placement
    return {
        "schema_version": "mastermind.execution_plan/v5",
        "root_job_id": coordinator.root_job_id,
        "coordinator_job_id": coordinator.job_id,
        "plan_attempt_id": dispatch.attempt.attempt_id,
        "steps": [step],
    }


def _complete(runtime, dispatch, body):
    return _complete_ohf_role(
        runtime, dispatch, body,
        identity_seed=30000 + int(dispatch.attempt.job_id.split("-")[1]),
    )


def _admit_coordinator(service, root):
    runtime = service.runtime
    planner = runtime.jobs.create_cycle_planner(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0"
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id=service.config.worker_id,
    )
    _complete(runtime, dispatch, _plan_body(
        dispatch, root, delegation={"descendant_limit": 14, "max_depth": 3},
    ))
    children = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{dispatch.attempt.attempt_id}",
    )
    return children[0]


def _nested_planner(service, coordinator):
    return service.runtime.jobs.create_cycle_planner(
        coordinator.job_id,
        command_id=f"coo-cycle:{coordinator.job_id}:create-planner:0",
    )


@pytest.mark.parametrize("material,explicit_placement", [(False, False), (True, True)])
def test_service_completes_nested_project_and_recovers_terminal_commands(
    tmp_path, short_socket_root, material, explicit_placement,
):
    async def exercise():
        async with _bound_service(
            tmp_path, short_socket_root, name="nested-service", material=material,
        ) as (service, supervisor, root):
            runtime = service.runtime
            seals, dispatch_commands, observed_pools = {}, {}, []
            binding = service._require_current_coo_binding()
            placement = ({
                "provider_realm": binding["provider"],
                "quota_class": service.config.coo_quota_class,
                "model": binding["model"],
            } if explicit_placement else None)

            async def finish(active):
                dispatch = SimpleNamespace(
                    attempt=active.lease.attempt, lease_token=active.lease.lease_token,
                )
                job = runtime.jobs.get_job(dispatch.attempt.job_id)
                if job.orchestration_role == "plan":
                    parent = runtime.jobs.get_job(job.parent_job_id)
                    options = _planner_routing_options(runtime, job)
                    assert options["hierarchy"]["root_job_id"] == root.job_id
                    assert options["hierarchy"]["coordinator_job_id"] == parent.job_id
                    assert options["degraded"] == [] and options["pools"]
                    observed_pools.append(options["pools"])
                    if parent.parent_job_id is not None:
                        assert parent.constraints["work_placement_union"] == root.constraints["work_placement_union"]
                        assert service._require_bound_coo_job(parent).job_id == root.job_id
                    delegation = (
                        {"descendant_limit": 14 - 2 * parent.depth, "max_depth": 3}
                        if parent.depth < 2 else None
                    )
                    body = _plan_body(
                        dispatch, parent, delegation=delegation, placement=placement,
                    )
                elif job.orchestration_role == "aggregation":
                    assert runtime.jobs.get_cycle_handoff(job.job_id) is not None
                    finish_result(runtime, dispatch)
                    return
                elif job.orchestration_role == "review":
                    target = runtime.jobs.get_job(job.reviews_job_id)
                    body = _review_body(
                        root_id=root.job_id, plan_attempt_id=job.plan_attempt_id,
                        plan_digest=job.plan_digest, plan_step_id=job.plan_step_id,
                        target_job_id=target.job_id,
                        target_attempt_id=target.current_attempt_id,
                        target_result_digest=seals[target.job_id]["role_result_digest"],
                        repair_round=job.repair_round,
                        verdict="reject" if job.repair_round == 0 else "approve",
                    )
                else:
                    body = {
                        "schema_version": (
                            "mastermind.repair_result/v1"
                            if job.orchestration_role == "repair"
                            else "mastermind.work_result/v1"
                        ),
                        "root_job_id": root.job_id,
                        "plan_attempt_id": job.plan_attempt_id,
                        "plan_digest": job.plan_digest, "plan_step_id": job.plan_step_id,
                        "repair_round": job.repair_round,
                        "artifacts": [], "evidence_digests": [],
                    }
                    if job.orchestration_role == "repair":
                        rejected = next(
                            candidate for candidate in runtime.jobs.list_jobs()
                            if candidate.orchestration_role == "review"
                            and candidate.reviews_job_id == job.supersedes_job_id
                        )
                        body.update(
                            supersedes_job_id=job.supersedes_job_id,
                            rejected_review_job_id=rejected.job_id,
                            rejected_review_result_digest=seals[rejected.job_id]["role_result_digest"],
                        )
                seals[job.job_id], terminal = _complete(runtime, dispatch, body)
                return terminal

            supervisor.finish_job = finish
            for _ in range(90):
                outcome = await service._run_coo_cycle_once(root.job_id)
                assert outcome.root_job_id == root.job_id
                if outcome.action in {"BLOCKED", "RECONCILIATION_REQUIRED"}:
                    pytest.fail(json.dumps(outcome.to_dict(), sort_keys=True))
                if outcome.action == "DISPATCHED":
                    dispatch_commands[outcome.selected_job_id] = outcome.command_id
                tasks = tuple(service._dispatch_tasks.values())
                if tasks:
                    await asyncio.gather(*tasks)
                assert service.service_state != "QUARANTINED", service._dispatch_errors
                if runtime.jobs.get_job(root.job_id).status is JobStatus.COMPLETED:
                    break
            else:
                pytest.fail(f"nested service cycle did not settle: {outcome}")

            jobs = runtime.jobs.list_jobs()
            assert {job.depth for job in jobs} == {0, 1, 2, 3}
            assert {job.root_job_id for job in jobs} == {root.job_id}
            assert all(job.status is JobStatus.COMPLETED for job in jobs)
            assert len(observed_pools) == 3
            assert len(supervisor.started_jobs) == len(jobs) == len(dispatch_commands)
            if material:
                assert {job.orchestration_role for job in jobs} == {
                    "aggregation", "plan", "work", "review", "repair",
                }
                for review in (job for job in jobs if job.orchestration_role == "review"):
                    target = runtime.jobs.get_job(review.reviews_job_id)
                    assert review.assigned_worker_id != target.assigned_worker_id
            if explicit_placement:
                for job in jobs:
                    if job.orchestration_role in {"aggregation", "work"} and job.parent_job_id:
                        assert job.constraints["eligible_quota_classes"] == [
                            service.config.coo_quota_class
                        ]
                        assert job.constraints["model"] == binding["model"]
                        assert "manual_model_override" in job.constraints["routing_reason_codes"]

            # Terminal binding observation must not require admission-open.
            # A known completion alone is not authority to replay a dispatch.
            service.runtime = Runtime.at(service.config.runtime_root)
            before = list(supervisor.started_jobs)
            for job_id, command_id in dispatch_commands.items():
                retained = service.runtime.jobs.get_job(job_id)
                assert service._require_bound_coo_job(retained).job_id == root.job_id
                with pytest.raises(StateConflict, match="exact lost-return marker"):
                    await service._dispatch_cycle_job_exact(job_id, command_id)
            assert supervisor.started_jobs == before
            assert (await service._run_coo_cycle_once(root.job_id)).action == "NO_ACTION"

    asyncio.run(exercise())


@pytest.mark.parametrize("field,value", [
    ("parent_job_id", "JOB-999999"), ("depth", 1), ("orchestration_role", "work"),
    ("authority_policy_hash", "f" * 64), ("branch", "codex/foreign"),
    ("constraints", {}), ("requested_authorities", ["READ", "WRITE"]),
])
def test_service_refuses_changed_nested_job_identity(
    tmp_path, short_socket_root, field, value,
):
    async def exercise():
        async with _bound_service(
            tmp_path, short_socket_root, name="nested-identity",
        ) as (service, _supervisor, root):
            coordinator = _admit_coordinator(service, root)
            planner = _nested_planner(service, coordinator)
            with pytest.raises(StateConflict, match="binding drifted"):
                service._require_bound_coo_job(dataclasses.replace(planner, **{field: value}))
            assert service.runtime.jobs.get_job(planner.job_id).attempt_count == 0

    asyncio.run(exercise())


def test_nested_planner_keeps_evolved_workspace_but_initial_planner_requires_clean_base(
    tmp_path, short_socket_root,
):
    async def exercise():
        async with _bound_service(
            tmp_path, short_socket_root, name="nested-workspace",
        ) as (service, _supervisor, root):
            coordinator = _admit_coordinator(service, root)
            planner = _nested_planner(service, coordinator)
            (Path(root.worktree) / "README.md").write_text("Retained prior work\n")
            assert service._require_coo_workspace(planner)["launch_clean"] is False
            other_receipt = service._submit_service_intent(
                _coo_intent(service.config, "fresh-workspace")
            )
            other = service.runtime.jobs.get_job(other_receipt["job_id"])
            initial = _nested_planner(service, other)
            (Path(other.worktree) / "README.md").write_text("Unexpected initial change\n")
            with pytest.raises(ServiceError, match="initial COO planner"):
                service._require_coo_workspace(initial)

    asyncio.run(exercise())


def test_new_coordinator_binding_does_not_grant_early_aggregate_dispatch(
    tmp_path, short_socket_root,
):
    async def exercise():
        async with _bound_service(
            tmp_path, short_socket_root, name="nested-handoff",
        ) as (service, supervisor, root):
            coordinator = _admit_coordinator(service, root)
            assert service._require_bound_coo_job(coordinator).job_id == root.job_id
            with pytest.raises(StateConflict, match="handoff|admitted plan"):
                await service._dispatch_cycle_job_exact(
                    coordinator.job_id,
                    f"coo-cycle:{coordinator.job_id}:dispatch:{coordinator.job_id}:attempt:1",
                )
            assert service.runtime.jobs.get_job(coordinator.job_id).attempt_count == 0
            assert supervisor.started_jobs == []

    asyncio.run(exercise())


def _replace_constraints(runtime, job_id, constraints):
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET constraints_json=? WHERE job_id=?",
            (json.dumps(constraints, sort_keys=True, separators=(",", ":")), job_id),
        )


@pytest.mark.parametrize("fault", ["empty", "widened", "malformed"])
def test_nested_coordinator_cannot_change_inherited_pool_choices(
    tmp_path, short_socket_root, fault,
):
    async def exercise():
        async with _bound_service(
            tmp_path, short_socket_root, name="nested-pools",
        ) as (service, _supervisor, root):
            coordinator = _admit_coordinator(service, root)
            constraints = copy.deepcopy(coordinator.constraints)
            if fault == "empty":
                constraints["work_placement_union"] = []
            elif fault == "widened":
                constraints["work_placement_union"].append(
                    {"provider_realm": "claude-code", "quota_class": "unadmitted"}
                )
            else:
                constraints["work_placement_union"] = "not-a-pool-grant"
            _replace_constraints(service.runtime, coordinator.job_id, constraints)
            with pytest.raises((StateConflict, ValueError)):
                changed = service.runtime.jobs.get_job(coordinator.job_id)
                service._require_bound_coo_job(changed)
            assert service.runtime.jobs.get_job(root.job_id).attempt_count == 0

    asyncio.run(exercise())


def test_legacy_nested_coordinator_without_pools_replays_without_promoting_authority(
    tmp_path, short_socket_root,
):
    async def exercise():
        async with _bound_service(
            tmp_path, short_socket_root, name="nested-legacy",
        ) as (service, _supervisor, root):
            coordinator = _admit_coordinator(service, root)
            constraints = dict(coordinator.constraints)
            del constraints["work_placement_union"]
            _replace_constraints(service.runtime, coordinator.job_id, constraints)
            service.runtime = Runtime.at(service.config.runtime_root)
            legacy = service.runtime.jobs.get_job(coordinator.job_id)
            assert service._require_bound_coo_job(legacy).job_id == root.job_id
            planner = _nested_planner(service, legacy)
            options = _planner_routing_options(service.runtime, planner)
            assert options["pools"] == []
            assert options["degraded"] == ["work_placement_union_unavailable"]
            assert _nested_planner(service, legacy).job_id == planner.job_id
            assert "work_placement_union" not in service.runtime.jobs.get_job(legacy.job_id).constraints
            assert service.runtime.jobs.get_job(root.job_id).constraints["work_placement_union"]

    asyncio.run(exercise())


def test_foreground_nested_admission_uses_original_request_authority(
    tmp_path, short_socket_root, monkeypatch,
):
    async def exercise():
        async with _bound_service(
            tmp_path, short_socket_root, name="nested-foreground",
        ) as (service, _supervisor, root):
            coordinator = _admit_coordinator(service, root)
            service.config = dataclasses.replace(service.config, coo_foreground_only=True)
            guarded_roots, observed_coordinators = [], []

            def guard(root_id, **_kwargs):
                assert root_id == root.job_id
                guarded_roots.append(root_id)

            original = service._require_coo_coordinator_source

            def observe(original_root_id, coordinator_id):
                observed_coordinators.append(coordinator_id)
                original(original_root_id, coordinator_id)

            monkeypatch.setattr(service, "_require_foreground_only_source", guard)
            monkeypatch.setattr(service, "_require_coo_coordinator_source", observe)
            outcome = await service._run_coo_cycle_once(root.job_id)
            assert outcome.action == "PLANNER_CREATED"
            assert coordinator.job_id in observed_coordinators
            assert guarded_roots and set(guarded_roots) == {root.job_id}
            with pytest.raises(StateConflict, match="original foreground root"):
                original(root.job_id, outcome.selected_job_id)
            other_receipt = service._submit_service_intent(
                _coo_intent(service.config, "foreign-foreground")
            )
            with pytest.raises(StateConflict, match="original foreground root"):
                original(root.job_id, other_receipt["job_id"])

    asyncio.run(exercise())


def test_missing_nested_union_refuses_existing_explicit_placement_without_fallback(
    tmp_path, short_socket_root,
):
    async def exercise():
        async with _bound_service(
            tmp_path, short_socket_root, name="nested-no-fallback",
        ) as (service, _supervisor, root):
            runtime = service.runtime
            coordinator = _admit_coordinator(service, root)
            planner = _nested_planner(service, coordinator)
            dispatch = runtime.attempts.dispatch_cycle_job(
                planner.job_id,
                command_id=f"coo-cycle:{coordinator.job_id}:dispatch:{planner.job_id}:attempt:1",
                worker_id=service.config.worker_id,
            )
            binding = service._require_current_coo_binding()
            _complete(runtime, dispatch, _plan_body(
                dispatch, coordinator, placement={
                    "provider_realm": binding["provider"],
                    "quota_class": service.config.coo_quota_class,
                    "model": binding["model"],
                },
            ))
            children = runtime.jobs.admit_cycle_plan(
                coordinator.job_id,
                command_id=f"coo-cycle:{coordinator.job_id}:admit-plan:{dispatch.attempt.attempt_id}",
            )
            leaf = children[0]
            before = copy.deepcopy(leaf.constraints)
            constraints = dict(coordinator.constraints)
            del constraints["work_placement_union"]
            _replace_constraints(runtime, coordinator.job_id, constraints)
            with pytest.raises(StateConflict):
                service._require_bound_coo_job(runtime.jobs.get_job(leaf.job_id))
            retained = runtime.jobs.get_job(leaf.job_id)
            assert retained.constraints == before
            assert retained.attempt_count == 0
            assert "manual_model_override" in retained.constraints["routing_reason_codes"]

    asyncio.run(exercise())


def test_nested_lost_return_recovers_exact_terminal_attempt_after_restart(
    tmp_path, short_socket_root,
):
    async def exercise():
        async with _bound_service(
            tmp_path, short_socket_root, name="nested-recovery",
        ) as (service, supervisor, root):
            runtime = service.runtime
            coordinator = _admit_coordinator(service, root)
            planner = _nested_planner(service, coordinator)
            gate = asyncio.Event()

            async def finish(active):
                await gate.wait()
                dispatch = SimpleNamespace(
                    attempt=active.lease.attempt, lease_token=active.lease.lease_token,
                )
                _complete(runtime, dispatch, _plan_body(dispatch, coordinator))

            supervisor.finish_job = finish
            command = f"coo-cycle:{coordinator.job_id}:dispatch:{planner.job_id}:attempt:1"
            started = await service._dispatch_cycle_job_exact(planner.job_id, command)
            marker = runtime.jobs.record_cycle_dispatch_effect_unknown(
                coordinator.job_id, selected_job_id=planner.job_id,
                dispatch_command_id=command,
            )
            assert marker["root_job_id"] == root.job_id
            assert marker["coordinator_job_id"] == coordinator.job_id
            tasks = tuple(service._dispatch_tasks.values())
            gate.set()
            await asyncio.gather(*tasks)
            assert service.service_state == "READY", service._dispatch_errors
            service.runtime = Runtime.at(service.config.runtime_root)
            replay = await service._dispatch_cycle_job_exact(planner.job_id, command)
            assert replay.outcome == "TERMINAL"
            assert replay.attempt.attempt_id == started.attempt.attempt_id
            service.runtime.jobs.reconcile_cycle_dispatch_effect(
                coordinator.job_id, selected_job_id=planner.job_id,
                dispatch_command_id=command, receipt=replay,
            )
            assert service.runtime.jobs.pending_cycle_dispatch_effect_unknown(coordinator.job_id) is None
            assert service.runtime.jobs.get_job(planner.job_id).attempt_count == 1
            assert supervisor.started_jobs == [planner.job_id]

    asyncio.run(exercise())


def test_deferred_coordinator_requires_exact_inherited_grant(
    tmp_path, short_socket_root, monkeypatch,
):
    import control_plane.executive_service as service_module
    from control_plane.executive_orchestration_principal import digest

    async def exercise():
        async with _bound_service(
            tmp_path, short_socket_root, name="nested-deferred",
        ) as (service, _supervisor, root):
            runtime = service.runtime
            planner = _nested_planner(service, root)
            dispatch = runtime.attempts.dispatch_cycle_job(
                planner.job_id,
                command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
                worker_id=service.config.worker_id,
            )
            body = _plan_body(dispatch, root)
            dependent = dict(
                body["steps"][0], ordinal=1, step_id="STEP-1",
                prerequisite_step_ids=["STEP-0"],
                delegation={"descendant_limit": 12, "max_depth": 3},
            )
            body["steps"].append(dependent)
            _complete(runtime, dispatch, body)
            initial, = runtime.jobs.admit_cycle_plan(
                root.job_id,
                command_id=f"coo-cycle:{root.job_id}:admit-plan:{dispatch.attempt.attempt_id}",
            )
            first = runtime.attempts.dispatch_cycle_job(
                initial.job_id,
                command_id=f"coo-cycle:{root.job_id}:dispatch:{initial.job_id}:attempt:1",
                worker_id=service.config.worker_id,
            )
            finish_result(runtime, first)
            created = await service._run_coo_cycle_once(root.job_id)
            assert created.action == "WORK_CREATED", created
            coordinator = runtime.jobs.get_job(created.selected_job_id)
            assert coordinator.orchestration_role == "aggregation"
            assert service._require_bound_coo_job(coordinator).job_id == root.job_id
            cycle = copy.deepcopy(coordinator.orchestration_provenance)
            cycle["hierarchy_grant"]["descendant_limit"] = 10
            hostile = dataclasses.replace(
                coordinator, orchestration_provenance=cycle,
                orchestration_provenance_digest=digest(cycle),
            )
            real_hierarchy = service_module._hierarchy_material

            def corrupt_observation(connection, root_row):
                rows, grants = real_hierarchy(connection, root_row)
                row = dict(rows[coordinator.job_id])
                row["orchestration_provenance_json"] = json.dumps(
                    cycle, sort_keys=True, separators=(",", ":"),
                )
                row["orchestration_provenance_digest"] = digest(cycle)
                rows[coordinator.job_id] = row
                grants[coordinator.job_id] = cycle["hierarchy_grant"]
                return rows, grants

            monkeypatch.setattr(service_module, "_hierarchy_material", corrupt_observation)
            with pytest.raises(StateConflict, match="inherited grant"):
                service._require_bound_coo_job(hostile)
            assert runtime.jobs.get_job(coordinator.job_id).attempt_count == 0

    asyncio.run(exercise())
