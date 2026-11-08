"""Real factory/service/Runtime/Supervisor collectors; physical providers are inert.

The fixture adapter produces canonical collector bytes and actual local Git/files.
It launches no OS worker, provider, network call, or installed service.
"""
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path

import pytest

from common import project_execution_private_contract as wire
from control_plane import project_execution_admission as source_owner
from control_plane import executive_workspace as workspace_owner
from control_plane.codex_worker import CollectionReceipt, WorkerResult, WorkerRunStatus, _git_snapshot
from control_plane.executive_runtime import JobStatus
from control_plane.executive_supervisor import ExecutiveSupervisor
from tests.test_project_execution_service import composed
from tests.test_project_execution_factory import invoke
from tests.test_project_execution_continuation import scope_for
from tests.test_executive_supervisor import FakeAdapter, FakeInspector, FakeProcessController


class CollectedCodeAdapter(FakeAdapter):
    adapter_id = "codex-cli"

    def __init__(self, runtime):
        super().__init__(FakeInspector())
        self.runtime = runtime
        self.starts = []

    async def start(self, spec):
        baseline = _git_snapshot(Path(spec.workspace_path), require_clean=True)
        assert baseline.head == spec.expected_base_sha
        self.inspector.live = True
        self.inspector.pid += 1
        self.inspector.start_identity = spec.run_id
        ref = await super().start(spec)
        self.ref = dataclasses.replace(ref, base_sha=baseline.head,
            provider_session_id="fixture-session-" + spec.run_id)
        self.starts.append((spec.job_id, spec.expected_base_sha))
        return self.ref

    def launch_attestation(self, ref):
        import stat
        receipt = super().launch_attestation(ref)
        uid, gid = os.geteuid(), os.getegid()
        receipt["worker_identity"] = {
            "requested_user": self.spec.worker_user, "observed_user": self.spec.worker_user,
            "expected_uid": uid, "expected_gid": gid, "effective_uid": uid,
            "effective_gid": gid, "real_uid": uid, "real_gid": gid,
        }
        info = self.provider_home.stat()
        receipt["provider_home_identity"] = {
            "path": str(self.provider_home.resolve()), "device": info.st_dev,
            "inode": info.st_ino, "uid": info.st_uid, "gid": info.st_gid,
            "mode": stat.S_IMODE(info.st_mode), "mtime_ns": info.st_mtime_ns,
        }
        return receipt

    async def collect_result(self, ref):
        job = self.runtime.jobs.get_job(self.spec.job_id)
        root = self.runtime.jobs.get_job(job.root_job_id)
        manifest = []
        if job.orchestration_role == "plan":
            code = "WRITE_BRANCH" in root.requested_authorities
            body = dict(schema_version="mastermind.execution_plan/v5",
                root_job_id=root.job_id, coordinator_job_id=job.parent_job_id,
                plan_attempt_id=self.spec.run_id, steps=[dict(ordinal=0, step_id="BUILD",
                    objective="Implement the declared code file", business_impact="routine",
                    review_required=False, requested_authorities=["READ", "WRITE_BRANCH"] if code else ["READ"],
                    allowed_write_paths=["app/result.txt"] if code else [], validation_ids=[], attempt_limit=1,
                    cost_class="small", prerequisite_step_ids=[], delegation=None)])
        elif job.orchestration_role == "work":
            path = Path(self.spec.workspace_path) / "app/result.txt"
            path.parent.mkdir(exist_ok=True)
            prior = path.read_text() if path.exists() else ""
            if "WRITE_BRANCH" in job.requested_authorities:
                data = (prior + "verified turn\n").encode()
                path.write_bytes(data)
                manifest = [dict(path="app/result.txt", sha256=hashlib.sha256(data).hexdigest(), size=len(data))]
            else:
                assert prior == "verified turn\n"  # The readonly child receives the proven code tree.
            body = dict(schema_version="mastermind.work_result/v1",
                root_job_id=root.job_id, plan_attempt_id=job.plan_attempt_id,
                plan_digest=job.plan_digest, plan_step_id=job.plan_step_id,
                repair_round=job.repair_round,
                artifacts=[dict(path=item["path"], digest=item["sha256"]) for item in manifest],
                evidence_digests=[])
        else:
            assert job.orchestration_role == "aggregation"
            handoff = self.runtime.jobs.get_cycle_handoff(job.job_id)
            keys = {"ordinal", "plan_step_id", "current_job_id", "current_attempt_id",
                    "current_result_digest", "repair_round", "review_required",
                    "qualifying_review_job_id", "qualifying_review_attempt_id",
                    "qualifying_review_result_digest"}
            body = dict(schema_version=handoff["aggregate_result_schema"], coordinator_job_id=job.job_id,
                **{key: handoff[key] for key in ("root_job_id", "handoff_digest", "policy_sha",
                                                "plan_attempt_id", "plan_digest")},
                revisions=[{key: value for key, value in row.items() if key in keys}
                           for row in handoff["revisions"]],
                aggregate_summary="Retained code completed", evidence_digests=[])
        output = dict(schema_version="mastermind.executive_orchestration_result/v1",
            job_id=job.job_id, run_id=self.spec.run_id, worker_id=self.spec.worker_id,
            role=job.orchestration_role, status="COMPLETED", role_result=body,
            summary="Canonical inert code result", current_state="done", next_actions=[],
            errors=[], validations=[])
        result_bytes = wire.canonical(output)
        Path(ref.result_path).write_bytes(result_bytes)
        actual = _git_snapshot(Path(self.spec.workspace_path), require_clean=False)
        result = WorkerResult(job_id=job.job_id, run_id=self.spec.run_id, worker_id=self.spec.worker_id,
            status=WorkerRunStatus.SUCCEEDED, structured_output=output, artifact_manifest=tuple(manifest),
            git_manifest=dict(base_sha=ref.base_sha, head_sha=actual.head,
                changed_paths=[item["path"] for item in manifest],
                status_sha256=hashlib.sha256(actual.status).hexdigest()),
            usage={}, provider_session_id=ref.provider_session_id, exit_code=0,
            started_at=ref.started_at, finished_at="2026-11-06T00:00:00+00:00", error=None)
        self.inspector.live = False
        return CollectionReceipt(process_ref=ref, result=result,
            stdout_sha256=hashlib.sha256(Path(ref.stdout_path).read_bytes()).hexdigest(),
            stderr_sha256=hashlib.sha256(Path(ref.stderr_path).read_bytes()).hexdigest(),
            result_sha256=hashlib.sha256(result_bytes).hexdigest())


def code_factory(tmp_path, monkeypatch, *, mixed=False):
    factory, principal, args, armed = composed(tmp_path, monkeypatch, paid=mixed)
    service = factory.service
    previous = factory._supervisor()
    adapter = CollectedCodeAdapter(service.runtime)
    adapter.provider_home = tmp_path / "inert-provider-home"
    adapter.provider_home.mkdir(mode=0o700)
    os.chown(adapter.provider_home, -1, os.getegid())
    supervisor = ExecutiveSupervisor(service.runtime, adapter, runs_root=previous.runs_root,
        instance_id=previous.instance_id, inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        shared_run_gid=service.config.proof_shared_gid,
        isolation_roots=(service.config.proof_workspace_root, previous.runs_root),
        require_complete_launch_attestation=False)
    service.supervisor = supervisor
    if mixed:
        from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
        class UnselectedPaidAdapter:
            adapter_id = "canonical-paid-fabric"
            async def start(self, *_args, **_kwargs):
                pytest.fail("native code fixture must not invoke a paid physical provider")
        paid_owner = ExecutiveSupervisor(service.runtime, UnselectedPaidAdapter(),
            runs_root=tmp_path / "inert-paid-runs", instance_id=supervisor.instance_id,
            inspector=object(), process_controller=object(), project_input_owner=supervisor)
        service.supervisor = MixedExecutionOwnerSupervisor(supervisor,
            {service.config.worker_id: supervisor,
             service._paid_worker_binding_source.bindings[0].worker_id: paid_owner})
        assert source_owner.input_owner(service.supervisor) is supervisor
    args = {**args, "execution_profile": "bounded_code_change",
        "allowed_write_paths": ["app/result.txt"], "validation": {"git_diff_check": True},
        "execution_binding_sha256": wire.digest(service._require_project_execution_binding("bounded_code_change"))}
    args["operation_key"] = wire.operation_key(scope_for(principal), args)
    return factory, principal, args, adapter, armed


async def finish(factory, root_id):
    service = factory.service
    for _ in range(25):
        result = await service._run_coo_cycle(root_id)
        assert result.action not in {"BLOCKED", "RECONCILIATION_REQUIRED"}, (result, result.receipt,
            service.runtime.jobs.get_job(result.selected_job_id).result if result.selected_job_id else None)
        tasks = tuple(service._dispatch_tasks.values())
        if tasks:
            await asyncio.gather(*tasks)
        assert service.service_state == "READY", service._dispatch_errors
        if service.runtime.jobs.get_job(root_id).status is JobStatus.COMPLETED:
            return service.runtime.jobs.get_job(root_id)
    pytest.fail("Canonical code team failed to complete")


@pytest.mark.parametrize("mixed", [False, True])
def test_sealed_uncommitted_code_reaches_aggregation_and_exact_follow_up(tmp_path, monkeypatch, mixed):
    async def run():
        factory, principal, args, adapter, _ = code_factory(tmp_path, monkeypatch, mixed=mixed)
        if mixed:
            from control_plane.executive_runtime import CHILD_WORKSPACE_POLICY, CHILD_WORKSPACE_POLICY_KEY
            service = factory.service
            research = service._require_project_execution_binding("research_only")
            code = service._require_project_execution_binding("bounded_code_change")
            assert research[CHILD_WORKSPACE_POLICY_KEY] == CHILD_WORKSPACE_POLICY
            assert CHILD_WORKSPACE_POLICY_KEY not in code
            assert research["work_placement_union"] == code["work_placement_union"]
            assert service.runtime.workers.get_quota_class(service.config.worker_id,
                service.config.coo_quota_class).cost_class == "small"
            service._register_worker()  # Same exact enrollment remains idempotent.
            preview = await invoke(factory, principal, dict(work_ref=args["work_ref"],
                expected_context=args["expected_context"],
                operation_key="mmos-project-preview-" + "a" * 40), "preview")
            assert preview["ok"], preview
            assert preview["data"]["execution_profile_bindings"] == {
                "research_only": wire.digest(research), "bounded_code_change": wire.digest(code)}
        first = await invoke(factory, principal, args, raise_errors=True)
        root_id = first["data"]["receipt"]["job_id"]
        root = await finish(factory, root_id)
        original_event = factory.service.runtime.store.unique_root_created_event(root_id).to_dict()
        previous = source_owner.completed_run(factory._supervisor(), root_id, args["work_ref"], scope_for(principal))
        revision = source_owner.completed_workspace_revision(factory._supervisor(), previous)
        assert revision["commit"] != root.constraints["base_sha"]
        assert (Path(root.worktree) / "app/result.txt").read_text() == "verified turn\n"
        assert adapter.starts[-1] == (root_id, revision["commit"])
        assert Path(root.worktree).stat().st_mode & 0o777 == 0o700
        preview = await invoke(factory, principal, dict(work_ref=args["work_ref"],
            expected_context=args["expected_context"], previous_run=previous["witness"],
            operation_key="mmos-project-preview-" + "b" * 40), "preview")
        assert preview["ok"], preview
        assert preview["data"]["execution_scope"]["commit"] == revision["commit"]
        follow = {**args, "objective": "Build on the exact previous code", "previous_run": previous["witness"],
            "execution_binding_sha256": preview["data"]["execution_profile_bindings"]["bounded_code_change"]}
        follow["operation_key"] = wire.operation_key(scope_for(principal), follow)
        second = await invoke(factory, principal, follow, raise_errors=True)
        second_root = factory.service.runtime.jobs.get_job(second["data"]["receipt"]["job_id"])
        assert second_root.constraints["base_sha"] == revision["commit"]
        assert (Path(second_root.worktree) / "app/result.txt").read_text() == "verified turn\n"
        assert source_owner.workspace_base_for_job(factory._supervisor(), second_root) == revision["commit"]
        completed = await finish(factory, second_root.job_id)
        assert (Path(completed.worktree) / "app/result.txt").read_text() == "verified turn\nverified turn\n"
        assert factory.service.runtime.store.unique_root_created_event(root_id).to_dict() == original_event
        assert source_owner.completed_workspace_revision(factory._supervisor(), previous) == revision
        replay = await invoke(factory, principal, follow)
        assert replay["ok"] and replay["data"]["receipt"]["job_id"] == second_root.job_id
        assert len([job for job in factory.service.runtime.jobs.list_jobs() if job.parent_job_id is None]) == 2
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["dirty", "missing", "symlink", "branch", "unproven_commit"])
def test_code_follow_up_refuses_unsafe_prior_workspace_before_admission(tmp_path, monkeypatch, fault):
    async def run():
        factory, principal, args, _, _ = code_factory(tmp_path, monkeypatch)
        admitted = await invoke(factory, principal, args, raise_errors=True)
        root = await finish(factory, admitted["data"]["receipt"]["job_id"])
        previous = source_owner.completed_run(factory._supervisor(), root.job_id, args["work_ref"], scope_for(principal))
        workspace = Path(root.worktree)
        if fault == "dirty":
            (workspace / "app/result.txt").write_text("unsealed change")
        elif fault in {"missing", "symlink"}:
            moved = workspace.with_name("moved-result")
            workspace.rename(moved)
            if fault == "symlink":
                workspace.symlink_to(moved, target_is_directory=True)
        elif fault == "branch":
            workspace_owner._project_git(workspace, "symbolic-ref", "HEAD", "refs/heads/foreign", mutate=True)
        else:
            tree = workspace_owner._project_git(workspace, "rev-parse", "HEAD^{tree}").decode().strip()
            head = workspace_owner._project_git(workspace, "rev-parse", "HEAD").decode().strip()
            commit = workspace_owner._project_git(workspace, "commit-tree", tree, "-p", head,
                data=b"model-provided commit\n", mutate=True).decode().strip()
            workspace_owner._project_git(workspace, "update-ref", "HEAD", commit, head, mutate=True)
        request = {**args, "objective": "Continue the completed result", "previous_run": previous["witness"]}
        request["operation_key"] = wire.operation_key(scope_for(principal), request)
        result = await invoke(factory, principal, request)
        assert not result["ok"] and result["error"]["code"] == "previous_workspace_unavailable", result
        assert len([job for job in factory.service.runtime.jobs.list_jobs() if job.parent_job_id is None]) == 1
    asyncio.run(run())


def test_native_plan_lineage_requires_exact_current_completion_and_digest(tmp_path, monkeypatch):
    from control_plane.executive_runtime import StateConflict, _assert_orchestration_lineage_for_create
    async def run():
        factory, principal, args, _, _ = code_factory(tmp_path, monkeypatch)
        result = await invoke(factory, principal, args, raise_errors=True)
        root_id = result["data"]["receipt"]["job_id"]
        service, runtime = factory.service, factory.service.runtime
        assert (await service._run_coo_cycle(root_id)).action == "PLANNER_CREATED"
        dispatched = await service._run_coo_cycle(root_id)
        await asyncio.gather(*tuple(service._dispatch_tasks.values()))
        planner = runtime.jobs.get_job(dispatched.selected_job_id)
        completed = runtime.validated_role_completion(planner.job_id,
            expected_attempt_id=planner.current_attempt_id)
        with runtime.store.read() as connection:
            parent = connection.execute("SELECT * FROM jobs WHERE job_id=?", (root_id,)).fetchone()
            common = dict(role="work", parent_row=parent, plan_attempt_id=planner.current_attempt_id,
                plan_digest=completed.role_result_digest, plan_step_id="BUILD", repair_round=0,
                reviews_job_id=None, supersedes_job_id=None)
            _assert_orchestration_lineage_for_create(connection, **common)
            for altered in ({"plan_attempt_id": "ATT-FOREIGN"}, {"plan_digest": "f" * 64}):
                with pytest.raises(StateConflict):
                    _assert_orchestration_lineage_for_create(connection, **{**common, **altered})
        # Inert local corruption: a completed but no-longer-current native
        # Attempt must not substitute for the original planner revision.
        with runtime.store.transaction() as connection:
            connection.execute("UPDATE jobs SET status='QUEUED',current_attempt_id=NULL,assigned_worker_id=NULL,assigned_quota_class=NULL WHERE job_id=?", (planner.job_id,))
        with runtime.store.read() as connection:
            with pytest.raises(StateConflict):
                _assert_orchestration_lineage_for_create(connection, **common)
        assert len(runtime.jobs.list_jobs()) == 2
    asyncio.run(run())


def test_readonly_follow_up_clones_exact_code_snapshot_without_changing_readonly_policy(tmp_path, monkeypatch):
    from control_plane.executive_runtime import CHILD_WORKSPACE_POLICY, CHILD_WORKSPACE_POLICY_KEY
    async def run():
        factory, principal, args, _, _ = code_factory(tmp_path, monkeypatch, mixed=True)
        admitted = await invoke(factory, principal, args, raise_errors=True)
        first = await finish(factory, admitted["data"]["receipt"]["job_id"])
        previous = source_owner.completed_run(factory._supervisor(), first.job_id, args["work_ref"], scope_for(principal))
        revision = source_owner.completed_workspace_revision(factory._supervisor(), previous)
        preview = await invoke(factory, principal, dict(work_ref=args["work_ref"],
            expected_context=args["expected_context"], previous_run=previous["witness"],
            operation_key="mmos-project-preview-" + "c" * 40), "preview")
        assert preview["ok"], preview
        follow = {key: value for key, value in args.items() if key not in {"allowed_write_paths", "validation"}}
        follow.update(execution_profile="research_only", objective="Analyze the completed code",
            previous_run=previous["witness"],
            execution_binding_sha256=preview["data"]["execution_profile_bindings"]["research_only"])
        follow["operation_key"] = wire.operation_key(scope_for(principal), follow)
        accepted = await invoke(factory, principal, follow, raise_errors=True)
        second = await finish(factory, accepted["data"]["receipt"]["job_id"])
        assert second.constraints[CHILD_WORKSPACE_POLICY_KEY] == CHILD_WORKSPACE_POLICY
        assert second.constraints["base_sha"] == revision["commit"]
        child = next(job for job in factory.service.runtime.jobs.list_jobs()
                     if job.root_job_id == second.job_id and job.orchestration_role == "work")
        assert child.worktree != second.worktree
        assert child.requested_authorities == ["READ"] and child.allowed_write_paths == []
        assert (Path(child.worktree) / "app/result.txt").read_text() == "verified turn\n"
        # The shared allocator identity is intentionally replaced by terminal
        # sealing after the child returns; inspect the immutable allocation event.
        receipt = factory.service.runtime.store.get_event_by_command_id(
            f"coo-workspace:{child.job_id}:completed").payload
        assert receipt["source_repository"] == second.worktree
        assert Path(child.worktree).stat().st_mode & 0o777 == 0o700
        assert source_owner.completed_workspace_revision(factory._supervisor(),
            source_owner.completed_run(factory._supervisor(), second.job_id, args["work_ref"],
                                       scope_for(principal)))["commit"] == revision["commit"]
    asyncio.run(run())


def test_service_never_transforms_workspace_while_an_actual_attempt_owns_it(tmp_path, monkeypatch):
    from control_plane.executive_runtime import StateConflict, OrchestrationDispatchOutcome
    async def run():
        factory, principal, args, _, _ = code_factory(tmp_path, monkeypatch)
        accepted = await invoke(factory, principal, args, raise_errors=True)
        root_id = accepted["data"]["receipt"]["job_id"]
        service, runtime = factory.service, factory.service.runtime
        assert (await service._run_coo_cycle(root_id)).action == "PLANNER_CREATED"
        assert (await service._run_coo_cycle(root_id)).action == "DISPATCHED"
        await asyncio.gather(*tuple(service._dispatch_tasks.values()))
        assert (await service._run_coo_cycle(root_id)).action == "PLAN_ADMITTED"
        work = next(job for job in runtime.jobs.list_jobs() if job.orchestration_role == "work")
        claim = runtime.attempts.dispatch_cycle_job(work.job_id,
            command_id=f"coo-cycle:{root_id}:dispatch:{work.job_id}:attempt:1",
            worker_id=service.config.worker_id)
        assert isinstance(claim, OrchestrationDispatchOutcome) and claim.claimed_now
        root = runtime.jobs.get_job(root_id)
        before = (Path(root.worktree) / ".git/index").stat()
        def forbidden(*_args, **_kwargs):
            pytest.fail("active Attempt reached allocator mutation")
        monkeypatch.setattr(workspace_owner, "prepare_project_workspace_handoff", forbidden)
        with pytest.raises(StateConflict, match="active attempt owns"):
            await service._prepare_project_cycle_workspace(runtime.jobs.get_job(work.job_id), root)
        after = (Path(root.worktree) / ".git/index").stat()
        assert (before.st_ino, before.st_mode, before.st_mtime_ns) == (
            after.st_ino, after.st_mode, after.st_mtime_ns)
        assert Path(root.worktree).stat().st_mode & 0o777 == 0o700
    asyncio.run(run())
