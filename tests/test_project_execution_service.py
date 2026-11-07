"""Real project factory + existing service/COO/Runtime; inert physical provider."""
import asyncio
import dataclasses
import json
from types import SimpleNamespace

import pytest

from common import project_execution_private_contract as wire
from common.executive_principal_namespace import principal_scope_from_identity
from control_plane import project_execution_admission as source_owner
from control_plane.executive_runtime import JobStatus, Runtime, StateConflict
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.executive_service import ExecutiveControlService, ServiceError
from integrations.mastermind_executive_app.project_execution_factory import ProjectExecutionAppFactory
from tests.test_project_execution_factory import fixture, invoke
from tests.test_executive_service import _FakeSupervisor
from tests.test_executive_coo_hierarchy_service import _plan_body, _complete
from tests.test_executive_coo_hierarchy_cycle import finish_result


def composed(tmp_path, monkeypatch, *, mode="DURABLE", paid=False):
    factory, principal, args, armed, _ = fixture(tmp_path,monkeypatch,mode=mode)
    service = factory.service
    if paid:
        from tests.test_foreground_paid_placements import paid_fixture
        paid_path = tmp_path / "paid-source-fixture"
        paid_path.mkdir()
        _, source, placements, _, _ = paid_fixture(paid_path, monkeypatch, runtime=service.runtime)
        service.config = dataclasses.replace(service.config, coo_paid_work_placements=placements)
        service._paid_worker_binding_source = source
        monkeypatch.setattr(service, "_paid_subject_review_registration",
            ExecutiveControlService._paid_subject_review_registration.__get__(service))
    # Restore actual installed-binding qualification and workspace methods.
    service._coo_execution_binding = service._load_coo_execution_binding()
    monkeypatch.setattr(service,"_require_project_execution_binding",
        ExecutiveControlService._require_project_execution_binding.__get__(service))
    monkeypatch.setattr(service,"_coo_binding_for_root",
        ExecutiveControlService._coo_binding_for_root.__get__(service))
    monkeypatch.setattr(factory,"_prepare_workspace",ProjectExecutionAppFactory._prepare_workspace.__get__(factory))
    service._register_worker()
    binding = service._require_project_execution_binding()
    args["execution_binding_sha256"] = wire.digest(binding)
    scope = principal_scope_from_identity(issuer_digest=principal.issuer_digest,
        subject_digest=principal.subject_digest,client_ref=principal.client_ref,resource=principal.resource)
    args["operation_key"] = wire.operation_key(scope,args)
    return factory, principal, args, armed


def test_new_project_background_service_completes_nested_team_after_request_closes(tmp_path,monkeypatch):
    async def run():
        factory, principal, args, _ = composed(tmp_path,monkeypatch)
        service = factory.service
        result = await invoke(factory,principal,args,raise_errors=True)
        root = service.runtime.jobs.get_job(result["data"]["receipt"]["job_id"])
        assert service._foreground_cycle_owner is None
        assert service._next_bound_coo_root() == root.job_id
        assert service.runtime.attempts.list_attempts() == []
        supervisor = factory._supervisor()
        physical = _FakeSupervisor(service.runtime)
        async def start(job_id, *, command_id):
            job = service.runtime.jobs.get_job(job_id)
            original = json.loads(source_owner.input_for_job(supervisor,job))
            assert original["request"]["handoff_text"] == args["handoff_text"]
            assert job.root_job_id == root.job_id
            return await physical.start_cycle_job(job_id,command_id=command_id)
        async def finish(active):
            runtime = service.runtime
            dispatch = SimpleNamespace(attempt=active.lease.attempt,lease_token=active.lease.lease_token)
            job = runtime.jobs.get_job(dispatch.attempt.job_id)
            if job.orchestration_role == "plan":
                parent = runtime.jobs.get_job(job.parent_job_id)
                delegation = {"descendant_limit":14-2*parent.depth,"max_depth":3} if parent.depth < 2 else None
                return _complete(runtime,dispatch,_plan_body(dispatch,parent,delegation=delegation))[1]
            return finish_result(runtime,dispatch)
        monkeypatch.setattr(supervisor,"start_cycle_job",start)
        monkeypatch.setattr(supervisor,"finish_job",finish)
        for _ in range(60):
            outcome = await service._run_coo_cycle(root.job_id)
            assert outcome.action not in {"BLOCKED","RECONCILIATION_REQUIRED"},outcome
            tasks = tuple(service._dispatch_tasks.values())
            if tasks: await asyncio.gather(*tasks)
            assert service.service_state == "READY",service._dispatch_errors
            if service.runtime.jobs.get_job(root.job_id).status is JobStatus.COMPLETED:
                break
        else: pytest.fail("Nested team did not settle")
        jobs = service.runtime.jobs.list_jobs()
        assert {job.depth for job in jobs} == {0,1,2,3}
        assert {job.root_job_id for job in jobs} == {root.job_id}
        assert all(job.status is JobStatus.COMPLETED for job in jobs)
        assert len(physical.started_jobs) == len(set(physical.started_jobs)) == len(jobs)
        assert (await service._run_coo_cycle(root.job_id)).action == "NO_ACTION"
        status = await invoke(factory,principal,{k:args[k] for k in ("operation_key","work_ref")},"status")
        assert status["ok"] and status["data"]["receipt"]["job_id"] == root.job_id
        assert service.runtime.jobs.get_cycle_handoff(root.job_id) is not None
    asyncio.run(run())


@pytest.mark.parametrize("destination",["absent","clean","partial","symlink","dirty","foreign_branch"])
def test_original_workspace_recovery_never_replaces_foreign_or_partial_destination(tmp_path,monkeypatch,destination):
    async def run():
        import subprocess
        factory, principal, args, _ = composed(tmp_path,monkeypatch)
        service = factory.service
        async def interrupted(*_): raise RuntimeError("service ended after root commit")
        monkeypatch.setattr(factory,"_prepare_workspace",interrupted)
        result = await invoke(factory,principal,args)
        assert result["error"]["code"] == "effect_unknown"
        root = service.runtime.jobs.list_jobs()[0]
        from pathlib import Path
        workspace = Path(root.worktree)
        allocations = []
        from control_plane import executive_service as module
        allocate = module.prepare_credentialless_clone
        def observed(*a,**kw):
            allocations.append(kw["job_id"])
            return allocate(*a,**kw)
        monkeypatch.setattr(module,"prepare_credentialless_clone",observed)
        if destination in {"clean","dirty","foreign_branch"}:
            await service._prepare_project_root_workspace(root)
            if destination == "dirty": (workspace/"untracked.txt").write_text("keep me")
            if destination == "foreign_branch":
                subprocess.run(["git","-C",str(workspace),"checkout","-qb","codex/foreign"],check=True)
        elif destination == "partial":
            workspace.mkdir();(workspace/"retained.txt").write_text("keep me")
        elif destination == "symlink":
            foreign = tmp_path/"foreign";foreign.mkdir();workspace.symlink_to(foreign,target_is_directory=True)
        if destination in {"absent","clean"}:
            assert service._next_bound_coo_root() == root.job_id
            await service._prepare_project_root_workspace(root)
            await service._prepare_project_root_workspace(root)
            assert len(allocations) == 1
        else:
            with pytest.raises((ServiceError,StateConflict,OSError)):
                await service._prepare_project_root_workspace(root)
            assert workspace.exists()
            assert len(allocations) == (1 if destination in {"dirty","foreign_branch"} else 0)
        assert service.runtime.attempts.list_attempts() == []
    asyncio.run(run())


def _reopen_project_service(original):
    """Reconstruct durable owners; no listener, installed service or provider."""
    assert original._foreground_cycle_owner is None
    assert not original._dispatch_tasks
    runtime = Runtime.at(original.runtime.store.root, create=False, existing_writable=True)
    assert runtime is not original.runtime and runtime.store is not original.runtime.store
    assert runtime.store.path == original.runtime.store.path
    supervisor = ExecutiveSupervisor(runtime, object(), runs_root=original.supervisor.runs_root,
        inspector=object(), process_controller=object(), instance_id=original.supervisor.instance_id)
    service = ExecutiveControlService(original.config, autonomy_guard=original._autonomy_guard,
        ceo_submit_admission_guard=original._ceo_submit_admission_guard,
        ceo_ingress_app_binding=original._ceo_ingress_app_binding,
        ceo_ingress_socket_path=original.ceo_ingress_socket_path,
        ceo_ingress_peer_uid=original._ceo_ingress_peer_uid,
        ceo_ingress_grounding_provider=original._ceo_ingress_grounding_provider)
    service.runtime = runtime
    service.supervisor = supervisor
    service._register_worker()
    assert service is not original and supervisor is not original.supervisor
    assert supervisor.runs_root == original.supervisor.runs_root
    assert supervisor.instance_id == original.supervisor.instance_id
    # Completed pre-restart attempts need neither requeue nor a physical probe.
    assert supervisor.reconcile_restart(requeue_lost=False) == []
    original._closing = True
    return service


def _inert_project_workers(service, monkeypatch, *, root_id, original_handoff):
    """Keep real claims, seals and source reads; replace only physical execution."""
    runtime, supervisor = service.runtime, service.supervisor
    physical = _FakeSupervisor(runtime)
    async def start(job_id, *, command_id):
        job = runtime.jobs.get_job(job_id)
        private = json.loads(source_owner.input_for_job(supervisor, job))
        assert private["request"]["handoff_text"] == original_handoff
        assert job.root_job_id == root_id
        return await physical.start_cycle_job(job_id, command_id=command_id)
    async def finish(active):
        dispatch = SimpleNamespace(attempt=active.lease.attempt, lease_token=active.lease.lease_token)
        job = runtime.jobs.get_job(dispatch.attempt.job_id)
        if job.orchestration_role == "plan":
            parent = runtime.jobs.get_job(job.parent_job_id)
            return _complete(runtime, dispatch, _plan_body(dispatch, parent))[1]
        return finish_result(runtime, dispatch)
    monkeypatch.setattr(supervisor, "start_cycle_job", start)
    monkeypatch.setattr(supervisor, "finish_job", finish)
    return physical


async def _project_tick(service, root_id):
    outcome = await service._run_coo_cycle(root_id)
    assert outcome.action not in {"BLOCKED", "RECONCILIATION_REQUIRED"}, outcome
    tasks = tuple(service._dispatch_tasks.values())
    if tasks:
        await asyncio.gather(*tasks)
    assert service.service_state == "READY", service._dispatch_errors
    return outcome


def test_new_runtime_and_service_resume_original_project_after_completed_planner(tmp_path, monkeypatch):
    async def run():
        factory, principal, args, _ = composed(tmp_path, monkeypatch)
        original = factory.service
        receipt = (await invoke(factory, principal, args, raise_errors=True))["data"]["receipt"]
        root_id = receipt["job_id"]
        root = original.runtime.jobs.get_job(root_id)
        source = source_owner.read_source(original.runtime, root)
        event = original.runtime.store.find_event_by_command_id(source["command_id"])
        private = source_owner.input_for_job(original.supervisor, root)
        first_workers = _inert_project_workers(original, monkeypatch,
            root_id=root_id, original_handoff=args["handoff_text"])
        for _ in range(12):
            await _project_tick(original, root_id)
            if original.runtime.attempts.list_attempts():
                break
        else:
            pytest.fail("Original planner was not dispatched")
        attempts = original.runtime.attempts.list_attempts()
        assert len(attempts) == 1
        planner = original.runtime.jobs.get_job(attempts[0].job_id)
        assert planner.orchestration_role == "plan" and planner.status is JobStatus.COMPLETED
        assert original.runtime.jobs.get_job(root_id).status is not JobStatus.COMPLETED
        before = {item.attempt_id: item for item in attempts}

        restarted = _reopen_project_service(original)
        resumed_root = restarted.runtime.jobs.get_job(root_id)
        assert source_owner.read_source(restarted.runtime, resumed_root) == source
        assert restarted.runtime.store.find_event_by_command_id(source["command_id"]) == event
        assert source_owner.input_for_job(restarted.supervisor, resumed_root) == private
        assert restarted._next_bound_coo_root() == root_id
        second_workers = _inert_project_workers(restarted, monkeypatch,
            root_id=root_id, original_handoff=args["handoff_text"])
        for _ in range(24):
            await _project_tick(restarted, root_id)
            if restarted.runtime.jobs.get_job(root_id).status is JobStatus.COMPLETED:
                break
        else:
            pytest.fail("Reopened project did not complete")
        jobs = restarted.runtime.jobs.list_jobs()
        assert [job.job_id for job in jobs if job.parent_job_id is None] == [root_id]
        assert all(job.root_job_id == root_id and job.status is JobStatus.COMPLETED for job in jobs)
        started = first_workers.started_jobs + second_workers.started_jobs
        assert len(started) == len(set(started)) == len(jobs)
        assert planner.job_id not in second_workers.started_jobs
        final_attempts = restarted.runtime.attempts.list_attempts()
        assert len(final_attempts) == len({item.job_id for item in final_attempts}) == len(jobs)
        assert {item.attempt_id: item for item in final_attempts if item.attempt_id in before} == before
        assert restarted.runtime.store.find_event_by_command_id(source["command_id"]) == event
        assert restarted._next_bound_coo_root() is None
        assert (await _project_tick(restarted, root_id)).action == "NO_ACTION"
        assert len(restarted.runtime.attempts.list_attempts()) == len(final_attempts)
    asyncio.run(run())


def test_closed_attended_root_cannot_starve_a_later_durable_project_after_restart(tmp_path, monkeypatch):
    async def run():
        factory, principal, attended_args, _ = composed(tmp_path, monkeypatch, mode="ATTENDED")
        original = factory.service
        async def request_closed(*_):
            raise RuntimeError("attended request closed after durable root admission")
        monkeypatch.setattr(factory, "_prepare_workspace", request_closed)
        result = await invoke(factory, principal, attended_args)
        assert result["error"]["code"] == "effect_unknown"
        attended = original.runtime.jobs.list_jobs()[0]
        assert source_owner.read_source(original.runtime, attended)["continuation_mode"] == "ATTENDED"
        assert original.runtime.attempts.list_attempts() == []

        original.config = dataclasses.replace(original.config, coo_foreground_only=False)
        monkeypatch.setattr(factory, "_prepare_workspace", ProjectExecutionAppFactory._prepare_workspace.__get__(factory))
        durable_args = {**attended_args, "continuation_mode": "DURABLE",
            "objective": "Complete the later durable project"}
        scope = principal_scope_from_identity(issuer_digest=principal.issuer_digest,
            subject_digest=principal.subject_digest, client_ref=principal.client_ref, resource=principal.resource)
        durable_args["operation_key"] = wire.operation_key(scope, durable_args)
        receipt = (await invoke(factory, principal, durable_args, raise_errors=True))["data"]["receipt"]
        durable_id = receipt["job_id"]
        assert durable_id != attended.job_id
        assert original._next_bound_coo_root() == durable_id

        restarted = _reopen_project_service(original)
        assert restarted._next_bound_coo_root() == durable_id
        with pytest.raises(StateConflict, match="original request unavailable"):
            restarted._require_project_execution_root(restarted.runtime.jobs.get_job(attended.job_id))
        physical = _inert_project_workers(restarted, monkeypatch,
            root_id=durable_id, original_handoff=durable_args["handoff_text"])
        for _ in range(24):
            assert restarted._next_bound_coo_root() == durable_id
            await _project_tick(restarted, durable_id)
            if restarted.runtime.jobs.get_job(durable_id).status is JobStatus.COMPLETED:
                break
        else:
            pytest.fail("Closed attended root starved the durable project")
        retained = restarted.runtime.jobs.get_job(attended.job_id)
        assert retained.status is JobStatus.QUEUED and retained.attempt_count == 0
        assert source_owner.read_source(restarted.runtime, retained)["continuation_mode"] == "ATTENDED"
        assert attended.job_id not in physical.started_jobs
        assert all(item.job_id != attended.job_id for item in restarted.runtime.attempts.list_attempts())
        assert restarted._next_bound_coo_root() is None
        assert len([job for job in restarted.runtime.jobs.list_jobs() if job.parent_job_id is None]) == 2
    asyncio.run(run())
