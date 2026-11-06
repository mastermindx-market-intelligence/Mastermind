"""Project chat turns are explicit new roots linked to canonical completed results."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from common import project_execution_private_contract as wire
from common.executive_principal_namespace import principal_scope_from_identity
from control_plane import project_execution_admission as source_owner
from control_plane.executive_runtime import JobStatus, StateConflict
from tests.test_project_execution_factory import invoke
from tests.test_project_execution_service import composed
from tests.test_executive_service import _FakeSupervisor
from tests.test_executive_coo_hierarchy_service import _plan_body, _complete
from tests.test_executive_coo_hierarchy_cycle import finish_result


def scope_for(principal):
    return principal_scope_from_identity(issuer_digest=principal.issuer_digest,
        subject_digest=principal.subject_digest,client_ref=principal.client_ref,resource=principal.resource)


async def finish_project(factory, principal, args, monkeypatch):
    result = await invoke(factory,principal,args,raise_errors=True)
    service = factory.service
    root = service.runtime.jobs.get_job(result["data"]["receipt"]["job_id"])
    supervisor = factory._supervisor()
    physical = _FakeSupervisor(service.runtime)
    async def start(job_id, *, command_id):
        actual = service.runtime.jobs.get_job(job_id)
        retained = json.loads(source_owner.input_for_job(supervisor,actual))
        assert retained["request"] == args
        return await physical.start_cycle_job(job_id,command_id=command_id)
    async def finish(active):
        dispatch = SimpleNamespace(attempt=active.lease.attempt,lease_token=active.lease.lease_token)
        job = service.runtime.jobs.get_job(dispatch.attempt.job_id)
        if job.orchestration_role == "plan":
            parent = service.runtime.jobs.get_job(job.parent_job_id)
            return _complete(service.runtime,dispatch,_plan_body(dispatch,parent,delegation=None))[1]
        return finish_result(service.runtime,dispatch)
    monkeypatch.setattr(supervisor,"start_cycle_job",start)
    monkeypatch.setattr(supervisor,"finish_job",finish)
    for _ in range(30):
        outcome = await service._run_coo_cycle(root.job_id)
        assert outcome.action not in {"BLOCKED","RECONCILIATION_REQUIRED"},outcome
        tasks = tuple(service._dispatch_tasks.values())
        if tasks: await asyncio.gather(*tasks)
        if service.runtime.jobs.get_job(root.job_id).status is JobStatus.COMPLETED:
            return service.runtime.jobs.get_job(root.job_id)
    pytest.fail("Project team failed to return a canonical result")


def test_follow_up_is_new_project_root_with_original_result_and_single_successor(tmp_path,monkeypatch):
    async def run():
        factory, principal, args, _ = composed(tmp_path,monkeypatch)
        runtime = factory.service.runtime
        first = await finish_project(factory,principal,args,monkeypatch)
        scope = scope_for(principal)
        prior = source_owner.completed_run(factory._supervisor(),first.job_id,args["work_ref"],scope)
        witness = prior["witness"]
        assert wire.validate_previous_run(witness) == witness
        assert prior["objective"] == args["objective"]
        assert prior["handoff_text"] == args["handoff_text"]
        first_event = runtime.store.unique_root_created_event(first.job_id).to_dict()
        follow = {**args,"objective":"Explain the verified result and finish the next step",
            "handoff_text":"Keep the original acceptance conditions","previous_run":witness}
        follow["operation_key"] = wire.operation_key(scope,follow)
        preview_args = dict(work_ref=args["work_ref"],expected_context=args["expected_context"],
            previous_run=witness,operation_key="mmos-project-preview-"+"b"*40)
        preview = await invoke(factory,principal,preview_args,"preview")
        assert preview["ok"],preview
        assert preview["data"]["previous_run"] == witness
        assert preview["data"]["execution_scope"]["commit"] == first.constraints["base_sha"]
        assert len([j for j in runtime.jobs.list_jobs() if j.parent_job_id is None]) == 1
        second = await finish_project(factory,principal,follow,monkeypatch)
        assert second.job_id != first.job_id and second.parent_job_id is None
        assert second.root_job_id == second.job_id and first.root_job_id == first.job_id
        assert runtime.store.unique_root_created_event(first.job_id).to_dict() == first_event
        assert runtime.jobs.get_job(first.job_id).status is JobStatus.COMPLETED
        material = source_owner.read_source(runtime,second)
        assert material["work_ref"] == args["work_ref"] and material["previous_run"] == witness
        retained = json.loads(source_owner.read_original_input(factory._supervisor(),material))
        assert retained["previous_run"] == prior
        assert runtime.store.unique_root_created_event(second.job_id).payload["project_execution_admission"]["source"]["previous_run"] == witness
        # Lost-response replay is resolved before the now-used parent check.
        replay = await invoke(factory,principal,follow)
        assert replay["ok"] and replay["data"]["receipt"]["job_id"] == second.job_id
        conflict = {**follow,"objective":"A competing different turn"}
        conflict["operation_key"] = wire.operation_key(scope,conflict)
        refused = await invoke(factory,principal,conflict)
        assert not refused["ok"] and refused["error"]["code"] == "previous_run_already_continued"
        assert len([j for j in runtime.jobs.list_jobs() if j.parent_job_id is None]) == 2
        # The next explicit turn consumes the second result, preserving the chain.
        second_prior = source_owner.completed_run(factory._supervisor(),second.job_id,args["work_ref"],scope)
        third = {**follow,"objective":"Continue from the second result","previous_run":second_prior["witness"]}
        third["operation_key"] = wire.operation_key(scope,third)
        submitted = await invoke(factory,principal,third,raise_errors=True)
        third_root = runtime.jobs.get_job(submitted["data"]["receipt"]["job_id"])
        assert third_root.job_id not in {first.job_id,second.job_id}
        assert source_owner.read_source(runtime,third_root)["previous_run"] == second_prior["witness"]
    asyncio.run(run())


def test_active_or_forged_or_foreign_result_never_authorizes_a_follow_up(tmp_path,monkeypatch):
    async def run():
        factory, principal, args, _ = composed(tmp_path,monkeypatch)
        scope = scope_for(principal)
        admitted = await invoke(factory,principal,args,raise_errors=True)
        root_id = admitted["data"]["receipt"]["job_id"]
        with pytest.raises(StateConflict):
            source_owner.completed_run(factory._supervisor(),root_id,args["work_ref"],scope)
        first = await finish_project(factory,principal,args,monkeypatch)
        prior = source_owner.completed_run(factory._supervisor(),first.job_id,args["work_ref"],scope)
        for foreign_work,foreign_scope in ((args["work_ref"],"f"*64),("WS:FOREIGN",scope)):
            with pytest.raises(StateConflict):
                source_owner.completed_run(factory._supervisor(),first.job_id,foreign_work,foreign_scope)
        bad = copy.deepcopy(prior["witness"]);bad["result_envelope_sha256"] = "a"*64
        request = {**args,"previous_run":bad,"objective":"Use an altered result"}
        request["operation_key"] = wire.operation_key(scope,request)
        refused = await invoke(factory,principal,request)
        assert not refused["ok"] and refused["error"]["code"] == "context_changed"
        assert len([j for j in factory.service.runtime.jobs.list_jobs() if j.parent_job_id is None]) == 1
    asyncio.run(run())

def test_concurrent_different_turns_cannot_fork_one_completed_parent(tmp_path,monkeypatch):
    async def run():
        factory, principal, args, _ = composed(tmp_path,monkeypatch)
        first = await finish_project(factory,principal,args,monkeypatch)
        scope = scope_for(principal)
        witness = source_owner.completed_run(factory._supervisor(),first.job_id,args["work_ref"],scope)["witness"]
        requests = []
        for objective in ("First competing follow-up","Second competing follow-up"):
            request = {**args,"previous_run":witness,"objective":objective}
            request["operation_key"] = wire.operation_key(scope,request)
            requests.append(request)
        outcomes = await asyncio.gather(*(invoke(factory,principal,request) for request in requests))
        assert sum(result["ok"] for result in outcomes) == 1,outcomes
        roots = [job for job in factory.service.runtime.jobs.list_jobs() if job.parent_job_id is None]
        assert len(roots) == 2
        winner = next(result for result in outcomes if result["ok"])
        assert winner["data"]["receipt"]["job_id"] != first.job_id
        assert factory.service.runtime.jobs.get_job(first.job_id).status is JobStatus.COMPLETED
    asyncio.run(run())
