"""Service composition for the bounded same-root COO ready frontier."""
from __future__ import annotations

import asyncio

from control_plane.executive_runtime import OrchestrationDispatchOutcome
from control_plane.model_router import ModelRouter
from tests.test_executive_os_phase1fc import _complete_ohf_role
from tests.test_executive_service import (
    _config,
    _coo_intent,
    _request,
    _service,
)


def _register_peer(service, worker_id: str = "codex-02") -> None:
    runtime = service._require_runtime()
    binding = service._require_current_coo_binding()
    alias = ModelRouter.load().model_aliases[service.config.coo_model_alias]
    capabilities = list(alias.capabilities)
    metadata = {
        "service_managed": True,
        "purpose": "executive-coo-cycle",
        "model_alias": service.config.coo_model_alias,
        "routing_policy_version": binding["routing_policy_version"],
        "execution_profile_id": binding["execution_profile_id"],
        "execution_profile_digest": binding["execution_profile_digest"],
        "capability_policy_version": binding["capability_policy_version"],
        "capability_policy_digest": binding["capability_policy_digest"],
    }
    default_metadata = dict(metadata)
    default_metadata.pop("model_alias", None)
    default_metadata["capacity_variant"] = "default"
    runtime.workers.register_worker(
        worker_id,
        provider=str(binding["provider"]),
        account_label=f"{worker_id}@company",
        worker_type=service.config.worker_type,
        capabilities=capabilities,
        quota_classes={
            service.config.coo_quota_class: {
                "provider": binding["provider"],
                "model": binding["model"],
                "effort": binding["effort"],
                "cost_class": binding["cost_class"],
                "capabilities": capabilities,
                "metadata": metadata,
            },
            service.config.coo_default_quota_class: {
                "provider": binding["provider"],
                "model": binding["model"],
                "effort": binding["effort"],
                "cost_class": "default",
                "capabilities": capabilities,
                "metadata": default_metadata,
            },
        },
        metadata={"service_managed": True},
    )


def _admit_pair(service, *, name: str):
    runtime = service._require_runtime()
    receipt = service._submit_service_intent(_coo_intent(service.config, name))
    root = runtime.jobs.get_job(str(receipt["job_id"]))
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    planner_dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id=service.config.worker_id,
        quota_class=service.config.coo_quota_class,
    )
    assert isinstance(planner_dispatch, OrchestrationDispatchOutcome)
    plan_body = {
        "schema_version": "mastermind.execution_plan/v3",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner_dispatch.attempt.attempt_id,
        "steps": [
            {
                "ordinal": 0,
                "step_id": "step-0",
                "objective": "Keep one exact read-only work item live.",
                "business_impact": "routine",
                "review_required": False,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
            },
            {
                "ordinal": 1,
                "step_id": "step-1",
                "objective": "Advance one independent ready read-only sibling.",
                "business_impact": "routine",
                "review_required": False,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
            },
        ],
    }
    binding = service._require_current_coo_binding()
    for step in plan_body["steps"]:
        step["prerequisite_step_ids"] = []
        step["placement"] = {"provider_realm": str(binding["provider"]), "quota_class": service.config.coo_quota_class}
    _complete_ohf_role(
        runtime,
        planner_dispatch,
        plan_body,
        identity_seed=7901,
    )
    admitted = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:admit-plan:"
            f"{planner_dispatch.attempt.attempt_id}"
        ),
    )
    by_step = {job.plan_step_id: job for job in admitted}
    return root, by_step["step-0"], by_step["step-1"]


def _park_first(service, job, gate: asyncio.Event):
    runtime = service._require_runtime()
    started = runtime.attempts.dispatch_cycle_job(
        job.job_id,
        command_id=f"coo-cycle:{job.root_job_id}:dispatch:{job.job_id}:attempt:1",
        worker_id=service.config.worker_id,
        quota_class=service.config.coo_quota_class,
        lease_owner="service-ready-frontier-fixture",
    )
    assert isinstance(started, OrchestrationDispatchOutcome)

    async def parked() -> None:
        await gate.wait()

    task = asyncio.create_task(
        parked(),
        name=f"executive-cycle-finish-{job.job_id}",
    )
    service._dispatch_tasks[job.job_id] = task
    return started, task


async def _cleanup(service, first, first_task, first_gate, finish_gate) -> None:
    first_gate.set()
    if first_task is not None:
        await first_task
        service._dispatch_tasks.pop(first.job_id, None)
    finish_gate.set()
    await asyncio.sleep(0)
    await service.close()


def test_service_allows_coo_selected_same_root_ready_sibling(
    tmp_path,
    short_socket_root,
) -> None:
    async def exercise() -> None:
        finish_gate = asyncio.Event()
        first_gate = asyncio.Event()
        config = _config(
            tmp_path,
            socket_root=short_socket_root,
            coo_autonomy_armed=True,
            coo_tick_interval_seconds=3600.0,
        )
        service, holder = _service(
            tmp_path,
            finish_gate=finish_gate,
            config=config,
        )
        await service.start()
        first = first_task = None
        try:
            assert (await _request(service, "register-worker"))["ok"] is True
            _register_peer(service)
            root, first, second = _admit_pair(service, name="same-root-overlap")
            _started, first_task = _park_first(service, first, first_gate)

            outcome = await service._run_coo_cycle_once(root.job_id)

            assert outcome.action == "DISPATCHED"
            assert outcome.selected_job_id == second.job_id
            assert holder["supervisor"].started_jobs == [second.job_id]
            assert service.runtime.jobs.get_job(first.job_id).attempt_count == 1
            assert service.runtime.jobs.get_job(second.job_id).attempt_count == 1
            assert {
                service.runtime.jobs.get_job(first.job_id).assigned_worker_id,
                service.runtime.jobs.get_job(second.job_id).assigned_worker_id,
            } == {service.config.worker_id, "codex-02"}
        finally:
            if first is not None:
                await _cleanup(
                    service, first, first_task, first_gate, finish_gate
                )
            else:
                await service.close()

    asyncio.run(exercise())


def test_service_tick_revisits_root_that_already_owns_live_coo_work(
    tmp_path,
    short_socket_root,
) -> None:
    async def exercise() -> None:
        finish_gate = asyncio.Event()
        first_gate = asyncio.Event()
        config = _config(
            tmp_path,
            socket_root=short_socket_root,
            coo_autonomy_armed=True,
            coo_tick_interval_seconds=1.0,
        )
        service, _holder = _service(
            tmp_path,
            finish_gate=finish_gate,
            config=config,
        )
        await service.start()
        first = first_task = None
        try:
            assert (await _request(service, "register-worker"))["ok"] is True
            _register_peer(service)
            root, first, second = _admit_pair(
                service, name="tick-same-root-overlap"
            )
            _started, first_task = _park_first(service, first, first_gate)

            deadline = asyncio.get_running_loop().time() + 2.5
            while asyncio.get_running_loop().time() < deadline:
                current = service.runtime.jobs.get_job(second.job_id)
                assert current is not None
                if (
                    current.attempt_count == 1
                    and service._coo_last_tick_at is not None
                    and service._coo_last_outcome is not None
                ):
                    break
                await asyncio.sleep(0.05)

            current = service.runtime.jobs.get_job(second.job_id)
            assert current is not None
            assert current.attempt_count == 1
            assert service._coo_last_tick_at is not None
            assert service._coo_last_outcome is not None
            assert service._coo_last_outcome["selected_job_id"] == second.job_id
            assert service.runtime.jobs.get_job(root.job_id) is not None
        finally:
            if first is not None:
                await _cleanup(
                    service, first, first_task, first_gate, finish_gate
                )
            else:
                await service.close()

    asyncio.run(exercise())


def test_host_v3_binding_preserves_exact_reviewed_placement_set(tmp_path, short_socket_root):
    config = _config(tmp_path, socket_root=short_socket_root)
    service, _holder = _service(tmp_path, finish_gate=asyncio.Event(), config=config)
    binding = service._load_coo_execution_binding()
    provider = ModelRouter.load().model_aliases[config.coo_model_alias].provider_alias
    assert binding.get("host_execution_binding_version") == "mastermind.host_execution_binding/v3"
    assert binding["work_placement_union"] == [
        {"provider_realm": provider, "quota_class": quota}
        for quota in sorted({config.coo_quota_class, config.coo_default_quota_class})
    ]


def test_v3_bound_service_rejects_root_and_child_placement_drift(tmp_path, short_socket_root):
    import dataclasses
    import pytest
    from control_plane.executive_runtime import StateConflict

    async def exercise():
        config = _config(tmp_path, socket_root=short_socket_root)
        service, _holder = _service(tmp_path, finish_gate=asyncio.Event(), config=config)
        await service.start()
        try:
            assert (await _request(service, "register-worker"))["ok"] is True
            _register_peer(service)
            root, _first, second = _admit_pair(service, name="v3-placement-drift")
            assert service._is_bound_coo_root(root)
            assert service._require_bound_coo_job(second).job_id == root.job_id
            foreign = [{"provider_realm": "foreign", "quota_class": config.coo_quota_class}]
            bad_root = dataclasses.replace(root, constraints={**root.constraints, "work_placement_union": foreign})
            assert not service._is_bound_coo_root(bad_root)
            for changes in ({"eligible_quota_classes": [config.coo_default_quota_class]}, {"provider": "foreign"}):
                bad_child = dataclasses.replace(second, constraints={**second.constraints, **changes})
                with pytest.raises(StateConflict, match="host binding drifted"):
                    service._require_bound_coo_job(bad_child)
        finally:
            await service.close()
    asyncio.run(exercise())
