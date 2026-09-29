"""Host composition over the original supervisor. All provider/model work is fake."""
from __future__ import annotations
import asyncio
import copy
import dataclasses
import hashlib
import importlib
import json
import os
from pathlib import Path
import pytest
from test_chairman_coordination import bundle_fixture, digest, refresh
from tests.test_executive_os_phase1fc import _v2_intent, _complete_ohf_role
from tests.test_executive_os_sqlite import _hf1b_issue
from tests.test_executive_supervisor import Hf1bResultAdapter, FakeInspector, FakeProcessController
from tests.test_executive_terminal_return import _SEALED_WORKER_SECRET_CANARY
from tests.test_fabric_result_projection import _bound_reader, _release
from control_plane.ceo_intent import submit_intent
from control_plane.executive_runtime import Runtime, JobStatus, AttemptStatus
from control_plane.executive_supervisor import ExecutiveSupervisor, SupervisorError
from control_plane.executive_orchestration_result import canonical_bytes, canonical_digest
from control_plane.worker_execution_contract import ArtifactReceipt

ARTIFACT = "research/proof.md"


def host_module():
    spec = importlib.util.find_spec("control_plane.chairman_coordination_host")
    assert spec is not None, "coordination host composition is missing"
    return importlib.import_module("control_plane.chairman_coordination_host")


class DecisionAdapter(Hf1bResultAdapter):
    """Only fake execution: no CLI, provider, service, network or credentials."""
    async def collect_result(self, ref):
        original = await super().collect_result(ref)
        artifact = Path(self.spec.workspace_path) / ARTIFACT
        artifact.parent.mkdir(exist_ok=True)
        self.candidate_bytes = canonical_bytes(self.proposal)
        artifact.write_bytes(self.candidate_bytes)
        output = json.loads(Path(ref.result_path).read_text())
        output["role_result"]["artifacts"] = [{"path":ARTIFACT,"digest":hashlib.sha256(self.candidate_bytes).hexdigest()}]
        raw = canonical_bytes(output); Path(ref.result_path).write_bytes(raw)
        result = dataclasses.replace(original.result, structured_output=output,
            artifact_manifest=(ArtifactReceipt(ARTIFACT, hashlib.sha256(self.candidate_bytes).hexdigest(), len(self.candidate_bytes)),))
        self.inspector.live = False  # Explicit fixture terminal observation, not a process action.
        return dataclasses.replace(original, result=result, result_sha256=hashlib.sha256(raw).hexdigest())


@pytest.fixture
def host(tmp_path):
    p,x,c,b=bundle_fixture(); runtime=Runtime.at(tmp_path/"runtime")
    runtime.workers.register_worker("worker-a",provider="codex",account_label="host-fixture",worker_type="mock",capabilities=["read","research"],quota_classes={"default":{"provider":"codex","capabilities":["read","research"],"cost_class":"small","model":"gpt-5.6-sol","effort":"xhigh"}})
    workspace=tmp_path/"workspaces"/"project";workspace.mkdir(parents=True,mode=0o700)
    intent=_v2_intent(intent_id="CEO-COORDINATION-HOST",workstream=x["project_ref"],business_impact="routine",execution_contract={"requested_authorities":["READ","WRITE_BRANCH"],"allowed_write_paths":[ARTIFACT],"worktree":str(workspace.resolve()),"attempt_limit":2,"constraints":{"base_sha":"b"*40}})
    root=runtime.jobs.get_job(submit_intent(runtime,intent,workspace_root=workspace.parent)["job_id"])
    planner=runtime.jobs.create_cycle_planner(root.job_id,command_id=f"coo-cycle:{root.job_id}:create-planner:0")
    planning=runtime.attempts.dispatch_cycle_job(planner.job_id,command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",worker_id="worker-a",quota_class="default")
    plan={"schema_version":"mastermind.execution_plan/v1","root_job_id":root.job_id,"plan_attempt_id":planning.attempt.attempt_id,"steps":[{"ordinal":0,"step_id":"coordination-1","objective":"Produce one source-grounded next-step proposal.","business_impact":"routine","review_required":True,"requested_authorities":["READ","WRITE_BRANCH"],"allowed_write_paths":[ARTIFACT],"validation_ids":[],"attempt_limit":1,"cost_class":"small"}]}
    _complete_ohf_role(runtime,planning,plan,identity_seed=13201)
    runtime.jobs.admit_cycle_plan(root.job_id,command_id=f"coo-cycle:{root.job_id}:admit-plan:{planning.attempt.attempt_id}")
    work=next(j for j in runtime.jobs.list_jobs() if j.root_job_id==root.job_id and j.orchestration_role=="work")
    now=runtime.store.now_ms()
    definition={"schema_version":"mastermind.exact_worker_claim_target/v1","operation_key":root.orchestration_provenance["source_id"],"root_job_id":root.job_id,"job_id":work.job_id,"worker_id":"worker-a","quota_class":"default","expected_provider":"codex","expected_account_label":"host-fixture","expected_model":"gpt-5.6-sol","expected_effort":"xhigh","expected_cost_class":"small","expected_capabilities":["read","research"],"excluded_worker_ids":[],"source_owner":"executive-control","source_generation":"fixture-generation","authority_policy_hash":work.authority_policy_hash,"expires_at_ms":now+60000}
    target=_hf1b_issue(definition,{"schema_version":"mastermind.exact_worker_target_observation/v1","source_sha256":"d"*64,"control_attestation_sha256":"e"*64,"observed_at_ms":now,"max_age_ms":30000})
    keeper,namespace,binding,reader=_bound_reader(runtime)
    adapter=DecisionAdapter(FakeInspector(),runtime,work);adapter.proposal=c
    home=tmp_path/"provider-home";home.mkdir(mode=0o700);adapter.provider_home=home
    calls=[]
    def sources(job,attempt):
        calls.append((job.job_id,attempt.attempt_id))
        return host_module().CoordinationWorkSources(document=p,context=x,context_bundle=b,bundle_source_ref="SRC-BUNDLE",artifact_path=ARTIFACT,revalidate=lambda:None)
    config=dict(coordination_job_id=work.job_id,coordination_sources=sources,coordination_runtime=reader,
        runs_root=tmp_path/"runs",isolation_roots=(workspace.parent,tmp_path/"runs"),
        worker_user=__import__('pwd').getpwuid(os.geteuid()).pw_name,worker_uid=os.geteuid(),worker_gid=os.getegid(),
        heartbeat_interval_seconds=0.01,inspector=adapter.inspector,process_controller=FakeProcessController(adapter.inspector),
        secret_canary_verdict=_SEALED_WORKER_SECRET_CANARY,require_complete_launch_attestation=True,
        instance_id="coordination-host-fixture",exact_target_provider=lambda job_id:target if job_id==work.job_id else None)
    try:yield dict(p=p,x=x,c=c,b=b,runtime=runtime,reader=reader,root=root,work=work,adapter=adapter,config=config,calls=calls,namespace=namespace)
    finally:_release(keeper,binding)


def supervisor(host, **overrides):
    config={**host["config"],**overrides}
    return host_module().CoordinationWorkSupervisor(host["runtime"],host["adapter"],**config)


def command(host):
    return f"coo-cycle:{host['root'].job_id}:dispatch:{host['work'].job_id}:attempt:1"


def complete(host):
    sup=supervisor(host)
    async def run():
        active=await sup.start_cycle_job(host["work"].job_id,command_id=command(host))
        host["adapter"].inspector.live=False
        return await sup.finish_job(active)
    receipt=asyncio.run(run())
    return sup,receipt


def test_host_preserves_inherited_lifecycle_and_never_starts_on_construction(host):
    sup=supervisor(host)
    for name in ("start_cycle_job","_start_claimed_job","finish_job","run_cycle_once","reconcile_startup"):
        if hasattr(ExecutiveSupervisor,name):assert getattr(type(sup),name) is getattr(ExecutiveSupervisor,name)
    assert host["adapter"].start_count==0 and host["calls"]==[]
    assert host["runtime"].jobs.get_job(host["work"].job_id).status is JobStatus.QUEUED


def test_actual_supervisor_launch_contains_original_contract_and_coordination_task(host):
    sup,receipt=complete(host);adapter=host["adapter"]
    assert adapter.start_count==1 and len(host["calls"])==1
    assert receipt.job.status is JobStatus.COMPLETED and receipt.attempt.status is AttemptStatus.COMPLETED
    assert "one-shot Mastermind Executive worker" in adapter.spec.prompt
    assert "candidate_template" in adapter.spec.prompt and "do not execute its next_step" in adapter.spec.prompt
    schema=json.loads(Path(adapter.spec.result_schema_path).read_text())
    assert schema["properties"]["role"]["const"]=="work"
    assert receipt.collection.result.structured_output["role"]=="work"
    assert Path(receipt.assignment_seal_receipt_path).is_file()
    assert host["runtime"].jobs.get_job(host["root"].job_id).status is not JobStatus.COMPLETED
    assert host["adapter"].direct_validation_calls==[]


def test_completed_duplicate_command_uses_existing_runtime_without_rereasoning(host):
    sup,receipt=complete(host)
    replay=asyncio.run(sup.run_cycle_once(host["work"].job_id,command_id=command(host)))
    assert replay.outcome=="TERMINAL"
    assert replay.attempt.attempt_id==receipt.attempt.attempt_id
    assert host["adapter"].start_count==1 and len(host["calls"])==1


@pytest.mark.parametrize("failure",["missing","wrong_type","wrong_project","stale_bundle","ungranted_path","source_error","revalidation_error"])
def test_source_failure_stops_before_adapter_and_never_falls_back(host,failure):
    def broken(job,attempt):
        if failure=="missing":return None
        if failure=="wrong_type":return dict(context=host["x"])
        if failure=="source_error":raise RuntimeError("private-provider-detail")
        source=host["config"]["coordination_sources"](job,attempt)
        if failure=="wrong_project":return dataclasses.replace(source,context={**source.context,"project_ref":"WS:OTHER"})
        if failure=="stale_bundle":return dataclasses.replace(source,context_bundle={**source.context_bundle,"token_estimate":999})
        if failure=="ungranted_path":return dataclasses.replace(source,artifact_path="research/other.json")
        def changed():raise RuntimeError("private-source-change")
        return dataclasses.replace(source,revalidate=changed)
    sup=supervisor(host,coordination_sources=broken)
    with pytest.raises(SupervisorError) as error:asyncio.run(sup.start_cycle_job(host["work"].job_id,command_id=command(host)))
    assert "private-" not in str(error.value)
    assert host["adapter"].start_count==0


def test_fresh_source_revalidation_occurs_before_launch(host):
    observed=[]
    def sources(job,attempt):
        value=host["config"]["coordination_sources"](job,attempt)
        return dataclasses.replace(value,revalidate=lambda:observed.append(host["adapter"].start_count))
    sup=supervisor(host,coordination_sources=sources)
    async def run():
        active=await sup.start_cycle_job(host["work"].job_id,command_id=command(host))
        host["adapter"].inspector.live=False;await sup.finish_job(active)
    asyncio.run(run());assert observed and all(n==0 for n in observed)


def test_no_coordination_context_is_injected_into_unselected_job(host):
    sup=supervisor(host,coordination_job_id="JOB-999")
    async def run():
        active=await sup.start_cycle_job(host["work"].job_id,command_id=command(host))
        host["adapter"].inspector.live=False;await sup.finish_job(active)
    asyncio.run(run())
    assert host["calls"]==[] and "candidate_template" not in host["adapter"].spec.prompt


def test_return_fetches_exact_artifact_only_after_canonical_completion(host):
    sup,receipt=complete(host);calls=[]
    source=host["config"]["coordination_sources"](receipt.job,receipt.attempt)
    def artifact_reader(job,attempt,path,*,expected_sha256,max_bytes):
        calls.append((job.job_id,attempt.attempt_id,path,expected_sha256,max_bytes))
        assert not host["namespace"].active
        return host["adapter"].candidate_bytes
    before=host["runtime"].jobs.get_job(receipt.job.job_id).to_dict()
    result=host_module().consume_coordination_completion(receipt,sources=source,runtime=host["reader"],artifact_reader=artifact_reader)
    assert result["eligible_for_owner_revalidation"] and result["execution_authority_granted"] is False
    assert result["candidate_digest"]==digest(host["c"])
    assert len(calls)==1 and calls[0][:3]==(receipt.job.job_id,receipt.attempt.attempt_id,ARTIFACT)
    assert host["runtime"].jobs.get_job(receipt.job.job_id).to_dict()==before


@pytest.mark.parametrize("failure",["wrong_job","wrong_attempt","bad_digest","not_completed","artifact_changed","artifact_error","missing_reader"])
def test_return_refuses_mismatch_without_execution_or_fallback(host,failure):
    _,receipt=complete(host);source=host["config"]["coordination_sources"](receipt.job,receipt.attempt);calls=[]
    def read(job,attempt,path,**kwargs):
        calls.append(path)
        if failure=="artifact_error":raise RuntimeError("private-reader-detail")
        return b"changed" if failure=="artifact_changed" else host["adapter"].candidate_bytes
    if failure=="wrong_job":receipt=dataclasses.replace(receipt,job=dataclasses.replace(receipt.job,job_id="JOB-999"))
    if failure=="wrong_attempt":receipt=dataclasses.replace(receipt,attempt=dataclasses.replace(receipt.attempt,attempt_id="ATT-OTHER"))
    if failure=="bad_digest":receipt=dataclasses.replace(receipt,job=dataclasses.replace(receipt.job,result={**receipt.job.result,"result_envelope_digest":"a"*64}))
    if failure=="not_completed":receipt=dataclasses.replace(receipt,job=dataclasses.replace(receipt.job,status=JobStatus.RUNNING))
    with pytest.raises(SupervisorError) as error:
        host_module().consume_coordination_completion(receipt,sources=source,runtime=host["reader"],artifact_reader=None if failure=="missing_reader" else read)
    assert "private-" not in str(error.value)
    if failure not in {"artifact_changed","artifact_error"}:assert calls==[]
    assert host["adapter"].start_count==1


@pytest.mark.parametrize("value",[False,True,"CURRENT",{},0])
def test_revalidator_must_follow_void_or_raise_contract_not_truthy_claims(host,value):
    def source(job,attempt):
        return dataclasses.replace(host["config"]["coordination_sources"](job,attempt),revalidate=lambda:value)
    sup=supervisor(host,coordination_sources=source)
    with pytest.raises(SupervisorError):asyncio.run(sup.start_cycle_job(host["work"].job_id,command_id=command(host)))
    assert host["adapter"].start_count==0


def test_changed_source_during_artifact_acquisition_holds_return(host):
    _,receipt=complete(host);source=host["config"]["coordination_sources"](receipt.job,receipt.attempt)
    changed=False
    def revalidate():
        if changed:raise ValueError("current intent changed")
    source=dataclasses.replace(source,revalidate=revalidate)
    def read(*args,**kwargs):
        nonlocal changed
        changed=True
        return host["adapter"].candidate_bytes
    with pytest.raises(SupervisorError):host_module().consume_coordination_completion(receipt,sources=source,runtime=host["reader"],artifact_reader=read)
    assert host["adapter"].start_count==1


def test_return_namespace_loss_after_artifact_read_is_not_reacquired_or_retargeted(host):
    _,receipt=complete(host);source=host["config"]["coordination_sources"](receipt.job,receipt.attempt);calls=[]
    def read(*args,**kwargs):
        calls.append(1);host["namespace"].invalid=True
        return host["adapter"].candidate_bytes
    with pytest.raises(SupervisorError):host_module().consume_coordination_completion(receipt,sources=source,runtime=host["reader"],artifact_reader=read)
    assert calls==[1] and host["adapter"].start_count==1


def test_existing_private_recovery_prompt_contains_exact_composed_task(host):
    _,receipt=complete(host)
    prompt_path=Path(host["adapter"].spec.result_schema_path).parent/"worker-prompt.txt"
    assert prompt_path.read_text()==host["adapter"].spec.prompt
    assert "candidate_template" in prompt_path.read_text()


def test_second_delivery_while_start_is_inflight_does_not_recompose_or_launch(host):
    sup=supervisor(host);adapter=host["adapter"]
    async def run():
        adapter.entered=asyncio.Event();adapter.continue_start=asyncio.Event()
        first=asyncio.create_task(sup.start_cycle_job(host["work"].job_id,command_id=command(host)))
        await asyncio.wait_for(adapter.entered.wait(),timeout=5)
        duplicate=await sup.start_cycle_job(host["work"].job_id,command_id=command(host))
        assert not duplicate.claimed_now and adapter.start_count==1 and len(host["calls"])==1
        adapter.continue_start.set();active=await asyncio.wait_for(first,timeout=5)
        adapter.inspector.live=False;await sup.finish_job(active)
    asyncio.run(run())


def test_host_requires_existing_exact_target_owner_instead_of_default_placement(host):
    with pytest.raises(SupervisorError):supervisor(host,exact_target_provider=None)
    assert host["adapter"].start_count==0 and host["calls"]==[]


def test_selected_job_missing_target_refuses_before_claim_not_wildcard_fallback(host):
    sup=supervisor(host,exact_target_provider=lambda _job:None)
    with pytest.raises(SupervisorError):asyncio.run(sup.start_cycle_job(host["work"].job_id,command_id=command(host)))
    assert host["runtime"].jobs.get_job(host["work"].job_id).status is JobStatus.QUEUED
    assert host["adapter"].start_count==0 and host["calls"]==[]


def test_replaced_provider_target_does_not_change_original_operation(host):
    sup,receipt=complete(host)
    provider_calls=[]
    def absent(_job):provider_calls.append(_job);return None
    replacement=supervisor(host,exact_target_provider=absent)
    with pytest.raises(SupervisorError):asyncio.run(replacement.start_cycle_job(host["work"].job_id,command_id=command(host)))
    assert provider_calls==[host["work"].job_id]
    assert host["adapter"].start_count==1
    assert host["runtime"].jobs.get_job(host["work"].job_id).current_attempt_id==receipt.attempt.attempt_id



def run_review(host, sup=None, reader=None):
    sup=sup or supervisor(host)
    method=getattr(sup,"run_coordination_once",None)
    assert callable(method), "one bounded supervisor-to-review step is missing"
    read=reader or (lambda *args,**kwargs:host["adapter"].candidate_bytes)
    return asyncio.run(method(command_id=command(host),artifact_reader=read))


def test_one_host_call_executes_original_work_and_returns_review_without_next_action_execution(host):
    execution,review=run_review(host)
    assert execution.job.status is JobStatus.COMPLETED
    assert review["candidate_digest"]==digest(host["c"])
    assert review["eligible_for_owner_revalidation"] and not review["execution_authority_granted"]
    assert len(host["calls"])==2 and host["adapter"].start_count==1
    assert len(host["runtime"].attempts.list_attempts(host["work"].job_id))==1
    assert host["runtime"].jobs.get_job(host["root"].job_id).status is not JobStatus.COMPLETED


def test_same_command_recovers_completed_review_without_relaunch_or_replanning(host):
    sup=supervisor(host);first,review=run_review(host,sup)
    replay,recovered=run_review(host,sup)
    assert replay.outcome=="TERMINAL" and replay.attempt.attempt_id==first.attempt.attempt_id
    assert recovered["candidate_digest"]==review["candidate_digest"]
    assert recovered["runtime_result_evidence"]["result_envelope_digest"]==review["runtime_result_evidence"]["result_envelope_digest"]
    assert host["adapter"].start_count==1 and len(host["calls"])==3


def test_missing_artifact_reader_is_rejected_before_any_work_is_claimed(host):
    sup=supervisor(host);method=getattr(sup,"run_coordination_once",None)
    assert callable(method), "one bounded supervisor-to-review step is missing"
    with pytest.raises(SupervisorError):asyncio.run(method(command_id=command(host),artifact_reader=None))
    assert host["runtime"].jobs.get_job(host["work"].job_id).status is JobStatus.QUEUED
    assert host["adapter"].start_count==0 and host["calls"]==[]


def test_new_chairman_intent_at_completion_holds_old_candidate_not_a_second_turn(host):
    resolves=0
    def sources(job,attempt):
        nonlocal resolves
        resolves+=1
        if resolves==2:
            next(r for r in host["p"]["source_receipts"] if r["source_ref"]=="SRC-CHAIRMAN")["revision"]="new-chairman-intent"
            refresh(host["p"],host["x"],host["c"])
        return host["config"]["coordination_sources"](job,attempt)
    sup=supervisor(host,coordination_sources=sources)
    execution,review=run_review(host,sup)
    assert execution.job.status is JobStatus.COMPLETED
    assert not review["eligible_for_owner_revalidation"] and "INTENT_CHANGED" in review["reasons"]
    assert host["adapter"].start_count==1 and resolves==2


def test_collection_error_preserves_completed_runtime_result_for_explicit_recovery(host):
    sup=supervisor(host)
    def failed(*a,**k):raise RuntimeError("artifact temporarily unavailable")
    with pytest.raises(SupervisorError):run_review(host,sup,failed)
    assert host["runtime"].jobs.get_job(host["work"].job_id).status is JobStatus.COMPLETED
    execution,review=run_review(host,sup)
    assert execution.outcome=="TERMINAL" and review["eligible_for_owner_revalidation"]
    assert host["adapter"].start_count==1



def test_active_duplicate_returns_original_outcome_without_second_review(host):
    sup=supervisor(host);adapter=host["adapter"];reads=[]
    def read(*args,**kwargs):reads.append(1);return adapter.candidate_bytes
    async def run():
        adapter.entered=asyncio.Event();adapter.continue_start=asyncio.Event()
        pending=asyncio.create_task(sup.run_coordination_once(command_id=command(host),artifact_reader=read))
        await asyncio.wait_for(adapter.entered.wait(),timeout=5)
        second,review=await sup.run_coordination_once(command_id=command(host),artifact_reader=read)
        assert second.outcome=="ACTIVE" and review is None
        assert reads==[] and len(host["calls"])==1 and adapter.start_count==1
        adapter.continue_start.set()
        first,review=await asyncio.wait_for(pending,timeout=5)
        assert review["eligible_for_owner_revalidation"] and len(reads)==1
    asyncio.run(run())


def test_actual_granted_artifact_bytes_flow_through_host_reader_after_sealing(host):
    reads=[]
    def reader(job,attempt,path,*,expected_sha256,max_bytes):
        # The fixture supplies an authorized exact-path reader; production uses
        # its existing artifact owner, never this unguarded test convenience.
        data=(Path(job.worktree)/path).read_bytes()
        assert len(data)<=max_bytes and hashlib.sha256(data).hexdigest()==expected_sha256
        reads.append((job.job_id,attempt.attempt_id,path))
        return data
    execution,review=run_review(host,reader=reader)
    assert reads==[(execution.job.job_id,execution.attempt.attempt_id,ARTIFACT)]
    assert review["candidate_digest"]==digest(host["c"])


def test_malformed_artifact_is_not_reinterpreted_as_a_continue_message(host):
    sup=supervisor(host)
    def wrong(*args,**kwargs):return b"continue next turn"
    with pytest.raises(SupervisorError):run_review(host,sup,wrong)
    assert host["adapter"].start_count==1
    assert host["runtime"].jobs.get_job(host["work"].job_id).status is JobStatus.COMPLETED


def test_post_completion_source_outage_does_not_repeat_worker_when_source_returns(host):
    calls=0
    def source(job,attempt):
        nonlocal calls
        calls+=1
        if calls==2:raise RuntimeError("source temporarily unavailable")
        return host["config"]["coordination_sources"](job,attempt)
    sup=supervisor(host,coordination_sources=source)
    with pytest.raises(SupervisorError):run_review(host,sup)
    execution,review=run_review(host,sup)
    assert execution.outcome=="TERMINAL" and review["eligible_for_owner_revalidation"]
    assert host["adapter"].start_count==1 and calls==3



def test_target_provider_error_is_bounded_and_has_no_claim_effect(host):
    def failed(_job):raise RuntimeError("private-target-owner-detail")
    sup=supervisor(host,exact_target_provider=failed)
    with pytest.raises(SupervisorError) as error:asyncio.run(sup.start_cycle_job(host["work"].job_id,command_id=command(host)))
    assert "private-" not in str(error.value)
    assert host["runtime"].jobs.get_job(host["work"].job_id).status is JobStatus.QUEUED
    assert host["adapter"].start_count==0


def test_failed_native_execution_is_not_a_coordination_review_or_acceptance(host):
    from control_plane.worker_execution_contract import WorkerRunStatus
    original=host["adapter"].collect_result
    async def failed(ref):
        receipt=await original(ref)
        result=dataclasses.replace(receipt.result,status=WorkerRunStatus.FAILED,exit_code=1,error="fixture failure")
        return dataclasses.replace(receipt,result=result)
    host["adapter"].collect_result=failed
    reads=[]
    execution,review=run_review(host,reader=lambda *a,**k:reads.append(1))
    assert execution.job.status is JobStatus.FAILED and review is None
    assert reads==[] and len(host["calls"])==1 and host["adapter"].start_count==1
