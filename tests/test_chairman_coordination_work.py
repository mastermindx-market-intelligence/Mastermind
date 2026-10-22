"""Coordination over existing work-role and bounded Runtime owners; fixtures only."""
from __future__ import annotations
import copy
import dataclasses
import hashlib
import importlib
import json
from pathlib import Path
import pytest
from test_chairman_coordination import fixture, bundle_fixture, refresh, digest
from tests.test_executive_os_phase1fc import _register, _v2_intent, _complete_ohf_role
from tests.test_fabric_result_projection import _bound_reader, _release
from tests.test_executive_supervisor import _p2_grant_fixture
from control_plane.ceo_intent import submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import Runtime, JobStatus
from control_plane.executive_orchestration_result import canonical_bytes, canonical_digest, parse_and_validate_envelope
from control_plane.chairman_cognition import ChairmanCognitionError

ARTIFACT = "research/proof.md"


def function(name):
    spec = importlib.util.find_spec("control_plane.chairman_coordination_work")
    assert spec is not None, "work-role integration is missing"
    found = getattr(importlib.import_module("control_plane.chairman_coordination_work"), name, None)
    assert callable(found), name + " is missing"
    return found


def work_fixture(directory, policy, context, proposal, *, completed=True, writable=False):
    runtime=Runtime.at(directory);_register(runtime,"worker-a");_register(runtime,"worker-b")
    contract = {"requested_authorities":["READ"], "attempt_limit":2}
    if writable:
        workspace = directory / "workspace"; workspace.mkdir()
        contract.update(requested_authorities=["READ","WRITE_BRANCH"], allowed_write_paths=[ARTIFACT], worktree=str(workspace.resolve()))
    receipt=submit_intent(runtime,_v2_intent(intent_id="CEO-COORDINATION-WORK",workstream=context["project_ref"],execution_contract=contract),workspace_root=directory if writable else None)
    root=runtime.jobs.get_job(receipt["job_id"]); dispatches=[]
    def dispatch(job_id, command_id):
        result=runtime.attempts.dispatch_cycle_job(job_id,command_id=command_id,worker_id="worker-a")
        assert result is not None;dispatches.append(result);return result
    cycle=CooCycle(runtime,dispatcher=dispatch)
    assert cycle.run_once(root.job_id).action=="PLANNER_CREATED"
    assert cycle.run_once(root.job_id).action=="DISPATCHED"
    planner=dispatches[-1]
    plan={"schema_version":"mastermind.execution_plan/v1","root_job_id":root.job_id,"plan_attempt_id":planner.attempt.attempt_id,"steps":[{"ordinal":0,"step_id":"coordination-1","objective":"Read the existing scoped decision artifact.","business_impact":"routine","review_required":True,"requested_authorities":["READ"],"allowed_write_paths":[],"validation_ids":[],"attempt_limit":1,"cost_class":"small"}]}
    if writable:
        plan["steps"][0].update(requested_authorities=["READ","WRITE_BRANCH"], allowed_write_paths=[ARTIFACT])
    _complete_ohf_role(runtime,planner,plan,identity_seed=12301)
    assert cycle.run_once(root.job_id).action=="PLAN_ADMITTED"
    assert cycle.run_once(root.job_id).action=="DISPATCHED"
    work=dispatches[-1];blob=canonical_bytes(proposal)
    body={"schema_version":"mastermind.work_result/v1","root_job_id":root.job_id,"plan_attempt_id":planner.attempt.attempt_id,"plan_digest":canonical_digest(plan),"plan_step_id":"coordination-1","repair_round":0,"artifacts":[{"path":ARTIFACT,"digest":hashlib.sha256(blob).hexdigest()}],"evidence_digests":[]}
    if not completed:
        keeper,namespace,binding,reader=_bound_reader(runtime)
        return runtime,root,work,keeper,namespace,binding,reader
    seal,terminal=_complete_ohf_role(runtime,work,body,identity_seed=12302)
    completion=runtime.validated_role_completion(work.attempt.job_id,expected_attempt_id=work.attempt.attempt_id)
    assert completion.result_envelope["role"]=="work"
    parse_and_validate_envelope(canonical_bytes(completion.result_envelope).decode(),expected_job_id=completion.job.job_id,expected_run_id=completion.attempt.attempt_id,expected_worker_id=completion.attempt.worker_id,expected_role="work",expected_root_job_id=root.job_id)
    keeper,namespace,binding,reader=_bound_reader(runtime)
    return runtime,root,completion,keeper,namespace,binding,reader,blob


@pytest.fixture
def completed(tmp_path_factory):
    p,x,c=fixture();value=work_fixture(tmp_path_factory.mktemp("coordination-work"),p,x,c)
    try:yield p,x,c,value
    finally:_release(value[3],value[5])


def read(p,x,value,**overrides):
    runtime,root,completion,_,_,_,reader,blob=value
    args=dict(context=x,runtime=reader,root_job_id=root.job_id,job_id=completion.job.job_id,expected_attempt_id=completion.attempt.attempt_id,expected_result_envelope_digest=completion.result_digest,artifact_path=ARTIFACT,artifact_bytes=blob)
    args.update(overrides)
    return function("read_coordination_work_return")(p,**args)


def test_real_runtime_result_is_read_through_existing_owner_without_new_effect(completed):
    p,x,c,value=completed;runtime,root,completion,*_=value
    before=runtime.jobs.get_job(root.job_id).to_dict(),runtime.jobs.get_job(completion.job.job_id).to_dict()
    out=read(p,x,value)
    assert out["eligible_for_owner_revalidation"]
    assert out["candidate_digest"]==digest(c)
    assert out["runtime_result_evidence"]["job_id"]==completion.job.job_id
    assert out["runtime_result_evidence"]["role"]=="work"
    assert out["runtime_result_evidence"]["artifact_digest"]==hashlib.sha256(value[-1]).hexdigest()
    assert out["runtime_result_evidence"]["source_state"]=="SAME"
    assert out["execution_authority_granted"] is False
    assert out["acceptance_granted"] is False
    assert before==(runtime.jobs.get_job(root.job_id).to_dict(),runtime.jobs.get_job(completion.job.job_id).to_dict())


@pytest.mark.parametrize("key,value",[("root_job_id","JOB-999"),("job_id","JOB-999"),("expected_attempt_id","wrong-attempt"),("expected_result_envelope_digest","0"*64)])
def test_expected_selector_never_follows_a_newer_or_other_result(completed,key,value):
    p,x,_,parts=completed
    with pytest.raises(ChairmanCognitionError):read(p,x,parts,**{key:value})


@pytest.mark.parametrize("blob",[b"{}",b"",b"\xff",b"x"*(128*1024+1)],ids=["wrong-digest","empty","invalid-utf8","over-limit"])
def test_changed_or_unbounded_artifact_bytes_are_refused(completed,blob):
    p,x,_,parts=completed
    with pytest.raises(ChairmanCognitionError):read(p,x,parts,artifact_bytes=blob)


@pytest.mark.parametrize("path",["research/other.json","../proof.md","/tmp/proof.md","research/./proof.md","research/proof.md/"])
def test_artifact_does_not_retarget_or_normalize_a_foreign_path(completed,path):
    p,x,_,parts=completed
    with pytest.raises(ChairmanCognitionError):read(p,x,parts,artifact_path=path)


def test_owning_workstream_must_match_context_not_only_return_text(completed):
    p,x,_,parts=completed;x=copy.deepcopy(x);x["project_ref"]="WS:FOREIGN"
    with pytest.raises(ChairmanCognitionError):read(p,x,parts)


def test_unbound_runtime_is_not_a_live_source_substitute(completed):
    p,x,_,parts=completed
    with pytest.raises(ChairmanCognitionError):read(p,x,parts,runtime=parts[0])


def test_invalid_native_namespace_refuses_without_reacquisition(tmp_path,monkeypatch):
    p,x,c=fixture();parts=work_fixture(tmp_path,p,x,c);ns=parts[4]
    try:
        monkeypatch.setattr(ns,"invalid",True)
        with pytest.raises(ChairmanCognitionError):read(p,x,parts)
    finally:_release(parts[3],parts[5])


def test_current_chairman_change_holds_a_completed_old_proposal(completed):
    p,x,c,parts=completed;p,x,c=copy.deepcopy((p,x,c))
    next(r for r in p["source_receipts"] if r["source_ref"]=="SRC-CHAIRMAN")["revision"]="new-intent"
    refresh(p,x,c);out=read(p,x,parts)
    assert "INTENT_CHANGED" in out["reasons"]
    assert not out["eligible_for_owner_revalidation"]


def prompt_fixture(tmp_path):
    p,x,c,b=bundle_fixture();job,attempt,decision=_p2_grant_fixture(tmp_path)
    job=dataclasses.replace(job,plan_attempt_id="plan-attempt",plan_digest="a"*64,plan_step_id="coordination-1",repair_round=0)
    return p,x,b,job,attempt,decision


def prompt(p,x,b,job,attempt,decision,**overrides):
    args=dict(context=x,context_bundle=b,bundle_source_ref="SRC-BUNDLE",job=job,attempt=attempt,authority_decision=decision,artifact_path=ARTIFACT)
    args.update(overrides)
    return function("render_coordination_work_request")(p,**args)


def test_work_prompt_preserves_existing_role_schema_and_grant(tmp_path):
    p,x,b,job,attempt,decision=prompt_fixture(tmp_path)
    out=prompt(p,x,b,job,attempt,decision)
    from control_plane.executive_supervisor import worker_result_schema
    expected=worker_result_schema(job_id=job.job_id,run_id=attempt.attempt_id,worker_id=attempt.worker_id,effective_grant_digest=attempt.effective_grant_digest,orchestration_role="work",root_job_id=job.root_job_id)
    assert out["result_schema"]==expected
    assert out["artifact_path"]==ARTIFACT
    assert out["execution_authority_granted"] is False
    assert "role_result" in out["prompt"]
    assert "candidate_template" in out["prompt"]
    assert "do not replace" in out["prompt"].lower()
    assert out["job_id"]==job.job_id and out["attempt_id"]==attempt.attempt_id


@pytest.mark.parametrize("role",["plan","aggregation","review",None])
def test_prompt_does_not_widen_fixed_native_roles(tmp_path,role):
    p,x,b,job,attempt,decision=prompt_fixture(tmp_path);job=dataclasses.replace(job,orchestration_role=role)
    with pytest.raises(ChairmanCognitionError):prompt(p,x,b,job,attempt,decision)


def test_prompt_refuses_ungranted_artifact_write(tmp_path):
    p,x,b,job,attempt,decision=prompt_fixture(tmp_path)
    with pytest.raises(ChairmanCognitionError):prompt(p,x,b,job,attempt,decision,artifact_path="other.json")


def test_prompt_refuses_changed_attempt(tmp_path):
    p,x,b,job,attempt,decision=prompt_fixture(tmp_path);attempt=dataclasses.replace(attempt,attempt_id="foreign-attempt")
    with pytest.raises(ChairmanCognitionError):prompt(p,x,b,job,attempt,decision)


def test_prompt_refuses_widened_effective_grant(tmp_path):
    p,x,b,job,attempt,decision=prompt_fixture(tmp_path);attempt=dataclasses.replace(attempt,effective_grant={**attempt.effective_grant,"authorities":["DEPLOY"]})
    with pytest.raises(ChairmanCognitionError):prompt(p,x,b,job,attempt,decision)


@pytest.fixture
def active_work(tmp_path):
    p,x,c,b=bundle_fixture();value=work_fixture(tmp_path,p,x,c,completed=False,writable=True)
    try:yield p,x,c,b,value
    finally:_release(value[3],value[5])


def load(p,x,b,value,**overrides):
    runtime,root,dispatch,_,_,_,reader=value
    job=runtime.jobs.get_job(dispatch.attempt.job_id)
    from control_plane.executive_supervisor import ExecutiveSupervisor
    decision=ExecutiveSupervisor._revalidate_authority(job,dispatch.attempt)
    args=dict(context=x,context_bundle=b,bundle_source_ref="SRC-BUNDLE",runtime=reader,root_job_id=root.job_id,job_id=job.job_id,expected_attempt_id=dispatch.attempt.attempt_id,authority_decision=decision,artifact_path=ARTIFACT)
    args.update(overrides)
    return function("read_coordination_work_request")(p,**args)


def test_request_uses_canonical_root_membership_and_current_attempt(active_work):
    p,x,c,b,value=active_work
    before=value[0].jobs.get_job(value[2].attempt.job_id).to_dict()
    out=load(p,x,b,value)
    assert out["project_ref"]==x["project_ref"]
    assert out["source_generation"]["state"]=="SAME"
    assert out["attempt_id"]==value[2].attempt.attempt_id
    assert out["execution_authority_granted"] is False
    assert value[0].jobs.get_job(value[2].attempt.job_id).to_dict()==before


@pytest.mark.parametrize("field,bad",[("root_job_id","JOB-999"),("job_id","JOB-999"),("expected_attempt_id","foreign-attempt")])
def test_request_acquisition_never_infers_replacement_target(active_work,field,bad):
    p,x,_,b,value=active_work
    with pytest.raises(ChairmanCognitionError):load(p,x,b,value,**{field:bad})


def test_request_acquisition_blocks_cross_project_context_before_prompt(active_work):
    p,x,c,b,value=active_work;x=copy.deepcopy(x);x["project_ref"]="WS:FOREIGN"
    with pytest.raises(ChairmanCognitionError):load(p,x,b,value)


def test_request_acquisition_rejects_unbound_native_reader(active_work):
    p,x,_,b,value=active_work
    with pytest.raises(ChairmanCognitionError):load(p,x,b,value,runtime=value[0])



def test_request_to_artifact_to_canonical_completion_round_trip(active_work):
    p,x,c,b,value=active_work;runtime,root,dispatch,keeper,namespace,binding,reader=value
    request=load(p,x,b,value)
    task=json.loads(request["prompt"].split("\n\n",1)[1])
    source=json.loads(task["coordination_brief"]["messages"][1]["content"])
    proposal=source["candidate_template"]
    proposal.update(option_id="OPT-A",decision="CONTINUE",target_ref=x["target_ref"],consumed_return_refs=list(x["required_return_refs"]),evidence_refs=["SRC-PLAN","SRC-PROOF"],rationale="Fixture reasoning: the completed investigation resolves the accepted dependency.",next_step="Implement only the accepted isolated slice and return its discriminating proof; do not repeat the design.")
    blob=canonical_bytes(proposal)
    job=runtime.jobs.get_job(dispatch.attempt.job_id)
    target=Path(job.worktree)/ARTIFACT;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
    body={"schema_version":"mastermind.work_result/v1","root_job_id":root.job_id,"plan_attempt_id":job.plan_attempt_id,"plan_digest":job.plan_digest,"plan_step_id":job.plan_step_id,"repair_round":0,"artifacts":[{"path":ARTIFACT,"digest":hashlib.sha256(blob).hexdigest()}],"evidence_digests":[]}
    _complete_ohf_role(runtime,dispatch,body,identity_seed=12303)
    completion=runtime.validated_role_completion(job.job_id,expected_attempt_id=dispatch.attempt.attempt_id)
    # A new read namespace is acquired normally for a later independent read;
    # the prior request receipt never claims freshness across completion writes.
    other_keeper,other_namespace,other_binding,other_reader=_bound_reader(runtime)
    try:
        result=function("read_coordination_work_return")(p,context=x,runtime=other_reader,root_job_id=root.job_id,job_id=job.job_id,expected_attempt_id=dispatch.attempt.attempt_id,expected_result_envelope_digest=completion.result_digest,artifact_path=ARTIFACT,artifact_bytes=target.read_bytes())
        assert result["eligible_for_owner_revalidation"]
        assert result["candidate_digest"]==digest(proposal)
        assert result["runtime_result_evidence"]["job_id"]==request["job_id"]
        assert result["execution_authority_granted"] is False
        assert result["acceptance_granted"] is False
        assert result["runtime_result_evidence"]["runtime_acceptance"]=="NOT_PROJECTED"
    finally:_release(other_keeper,other_binding)


@pytest.mark.parametrize("change",["worker","current_attempt","plan","status"])
def test_prompt_current_assignment_and_lineage_are_required(tmp_path,change):
    p,x,b,job,attempt,decision=prompt_fixture(tmp_path)
    if change=="worker":job=dataclasses.replace(job,assigned_worker_id="other-worker")
    if change=="current_attempt":job=dataclasses.replace(job,current_attempt_id="older-attempt")
    if change=="plan":job=dataclasses.replace(job,plan_digest=None)
    if change=="status":job=dataclasses.replace(job,status=type(job.status).COMPLETED)
    with pytest.raises(ChairmanCognitionError):prompt(p,x,b,job,attempt,decision)


def test_bounded_return_closes_namespace_before_candidate_review(completed,monkeypatch):
    p,x,_,parts=completed
    module=importlib.import_module("control_plane.chairman_coordination_work")
    original=module.evaluate_coordination_candidate;called=[];ns=parts[4];entries=ns.entries
    def observed(*a,**kw):
        assert not ns.active
        called.append(True)
        return original(*a,**kw)
    monkeypatch.setattr(module,"evaluate_coordination_candidate",observed)
    read(p,x,parts)
    assert called==[True] and ns.entries==entries+1 and ns.exits==ns.entries


def test_assignment_cancelled_during_request_rendering_is_not_returned_as_current(
    active_work, monkeypatch,
):
    p, x, _, b, value = active_work
    runtime, _, dispatch, _, _, _, _ = value
    module = importlib.import_module("control_plane.chairman_coordination_work")
    original = module.render_coordination_work_request
    def cancelled(*args, **kwargs):
        result = original(*args, **kwargs)
        runtime.jobs.cancel_job(dispatch.attempt.job_id)
        return result
    monkeypatch.setattr(module, "render_coordination_work_request", cancelled)
    with pytest.raises(ChairmanCognitionError):
        load(p, x, b, value)
    assert runtime.jobs.get_job(dispatch.attempt.job_id).status is JobStatus.CANCEL_REQUESTED


def test_current_work_request_binds_complete_assignment_without_changing_runtime(active_work):
    p, x, _, b, value = active_work
    runtime, _, dispatch, _, namespace, _, _ = value
    job = runtime.jobs.get_job(dispatch.attempt.job_id)
    before = job.to_dict()
    request = load(p, x, b, value)
    module = importlib.import_module("control_plane.chairman_coordination_work")
    review = importlib.import_module("control_plane.chairman_coordination_review")
    assert request["assignment_digest"] == module._assignment_digest(job, dispatch.attempt)
    assert review._assignment_digest is module._assignment_digest
    body = dict(request)
    claimed_digest = body.pop("request_digest")
    assert claimed_digest == hashlib.sha256(canonical_bytes(body)).hexdigest()
    assert runtime.jobs.get_job(job.job_id).to_dict() == before
    assert not namespace.active and namespace.entries == namespace.exits


def test_read_namespace_loss_during_request_rendering_is_not_reacquired(active_work, monkeypatch):
    p, x, _, b, value = active_work
    module = importlib.import_module("control_plane.chairman_coordination_work")
    original = module.render_coordination_work_request
    renders = []
    def invalidated(*args, **kwargs):
        result = original(*args, **kwargs)
        renders.append(True)
        value[4].invalid = True
        return result
    monkeypatch.setattr(module, "render_coordination_work_request", invalidated)
    with pytest.raises(ChairmanCognitionError):
        load(p, x, b, value)
    assert renders == [True]
    assert value[0].jobs.get_job(value[2].attempt.job_id).status is JobStatus.RUNNING
