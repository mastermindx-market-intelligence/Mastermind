"""Inert real membership/Runtime/cache owners, without public route or live effect."""
import copy
from dataclasses import replace

import pytest
from common import executive_workspace_contract as workspace
from common import workspace_project_admission_contract as wire
from control_plane.executive_runtime import Runtime
from control_plane.workspace_project_admission import project_admission_request, read_project_admission_state
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.contract import workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.mastermind_workspace_app.project_admission_permissions import project_admission_permissions
from tests.test_workspace_project_suspend_grant import fixture as grant_fixture
from tests.test_workspace_member_bindings import principal
from tests.test_workspace_read_service import cache_fixture
from tests.test_mission_workspace import _owner_observation_inputs
from scripts import chairman_control_room as ccr

WORK="WS:ONE"

def setup(tmp_path,*,runtime_work=WORK):
    policy,bindings=grant_fixture()
    bindings["profiles"]["member-0"]["project_admission_suspend"]["work_ref"]=WORK
    runtime=Runtime.at(tmp_path/"runtime")
    root=runtime.jobs.create_job("actual inert root",provenance={"workstream":runtime_work},command_id="create-root")
    owners,clock,cache=cache_fixture(tmp_path)
    doc=copy.deepcopy(_owner_observation_inputs()["control_room"])
    import json
    doc=json.loads(json.dumps(doc).replace("JOB-1",root.job_id).replace("2026-09-20","2026-09-21"))
    doc["generated_at"]=owners[0].state_cache["doc"]["generated_at"]
    doc["autonomy"]["generated_at"]=doc["generated_at"]
    doc["autonomy"]["schema"]="mastermind.autonomy_control_room.v1"
    row=doc["autonomy"]["responsibilities"][0]
    row["freshness"]="current"
    row["validity"]=owners[0].state_cache["doc"]["autonomy"]["responsibilities"][0]["validity"]
    owners[0].state_cache["doc"]=doc
    owners[0].state_cache.pop("source_validity_bounds",None)
    with owners[0].state_lock: ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
    read_authorize=workspace_authorizers(policy=policy,load_bindings=lambda:legacy_workspace_document(bindings,policy))[1]
    service=WorkspaceReadService(cache=cache,runtime=runtime,authorize=read_authorize,armed={},runtime_identity={"db_present":True},
        project_admission_permissions=project_admission_permissions(policy=policy,load_bindings=lambda:bindings))
    frame={"schema":wire.FRAME_SCHEMA,"operation":wire.OPERATION,
        "selection":{"work_ref":WORK,"root_job_id":root.job_id,"command_id":"project-pause-original"},
        "principal":principal(bindings),"admission_expires_at":1000}
    def call(*,status=False,state=False,value=None,host_ready=lambda:True):
        request=copy.deepcopy(frame if value is None else value)
        if state:
            from common import workspace_project_admission_state_contract as state_wire
            request.update(schema=state_wire.FRAME_SCHEMA,operation=state_wire.OPERATION)
            request["selection"]={key:request["selection"][key] for key in ("work_ref","root_job_id")}
            return read_project_admission_state(service,request,permissions=service._project_admission_permissions,host_ready=host_ready,now=lambda:500)
        if status: request.update(schema=wire.STATUS_FRAME_SCHEMA,operation=wire.STATUS_OPERATION)
        return project_admission_request(service,request,permissions=service._project_admission_permissions,host_ready=host_ready,now=lambda:500,status=status)
    return runtime,service,bindings,frame,call

def count(runtime):
    with runtime.store.read() as connection: return connection.execute("SELECT count(*) FROM events").fetchone()[0]

def test_real_scoped_grant_commits_once_and_status_reads_only_original_command(tmp_path):
    runtime,_,_,frame,call=setup(tmp_path);before=count(runtime)
    committed=call()["result"]
    assert committed["disposition"]=="COMMITTED" and committed["receipt"]["state"]=="PAUSED"
    assert committed["selection"]==frame["selection"]
    assert count(runtime)==before+1
    assert call()["result"]["receipt"]==committed["receipt"]
    assert count(runtime)==before+1
    status=call(status=True)["result"]
    assert status["state"]=="OBSERVED" and status["receipt"]==committed["receipt"]
    absent=copy.deepcopy(frame);absent["selection"]["command_id"]="not-observed"
    result=call(status=True,value=absent)["result"]
    assert result["state"]=="NOT_OBSERVED" and result["receipt"] is None and result["reason_codes"]==[]
    assert count(runtime)==before+1

@pytest.mark.parametrize("kind",["read_only","foreign_project","revoked","read_receipt_reuse"])
def test_read_or_source_authoring_is_not_a_suspension_grant(tmp_path,kind):
    runtime,_,bindings,_,call=setup(tmp_path);slot=bindings["profiles"]["member-0"]
    if kind in {"read_only","revoked"}: slot["project_admission_suspend"]=None
    elif kind=="foreign_project":slot["project_admission_suspend"]["work_ref"]="WS:OTHER"
    else:slot["project_admission_suspend"]["permission_digest"]=slot["binding"]["permission_digest"]
    before=count(runtime);result=call()["result"]
    assert result["disposition"]=="NOT_DISPATCHED" and result["receipt"] is None
    assert count(runtime)==before

@pytest.mark.parametrize("kind",["foreign_root","wrong_runtime_work","expired","host_not_ready","unknown_field"])
def test_scope_identity_and_host_predicates_refuse_before_effect(tmp_path,kind):
    runtime,_,_,frame,call=setup(tmp_path,runtime_work="WS:OTHER" if kind=="wrong_runtime_work" else WORK)
    if kind=="foreign_root":frame["selection"]["root_job_id"]="JOB-999"
    elif kind=="expired":frame["admission_expires_at"]=499
    elif kind=="unknown_field":frame["actor"]="caller-cannot-name-actor"
    before=count(runtime)
    result=call(value=frame,host_ready=lambda:kind!="host_not_ready")
    if kind=="unknown_field": assert result==workspace.error("invalid_input",400)
    else: assert result["result"]["disposition"]=="NOT_DISPATCHED"
    assert count(runtime)==before

def test_permission_loss_inside_commit_rolls_back_but_caller_retains_original_unknown(tmp_path,monkeypatch):
    runtime,_,bindings,_,call=setup(tmp_path);slot=bindings["profiles"]["member-0"];grant=copy.deepcopy(slot["project_admission_suspend"])
    original=runtime.store.append_event;before=count(runtime)
    def revoke(connection,**kwargs):
        original(connection,**kwargs)
        if kwargs["event_type"]=="WORKSTREAM_ADMISSION_SUSPENDED":slot["project_admission_suspend"]=None
    monkeypatch.setattr(runtime.store,"append_event",revoke)
    result=call()["result"]
    assert result["disposition"]=="EFFECT_UNKNOWN" and result["receipt"] is None
    assert count(runtime)==before
    slot["project_admission_suspend"]=grant
    assert call(status=True)["result"]["state"]=="NOT_OBSERVED"
    assert count(runtime)==before

@pytest.mark.parametrize("kind",["revoked_after_commit","transport_after_commit"])
def test_post_commit_loss_withholds_receipt_and_recovers_same_command_only(tmp_path,monkeypatch,kind):
    runtime,_,bindings,_,call=setup(tmp_path);slot=bindings["profiles"]["member-0"];grant=copy.deepcopy(slot["project_admission_suspend"])
    original=runtime.jobs.pause_workstream_admission;before=count(runtime)
    def lost(*args,**kwargs):
        receipt=original(*args,**kwargs)
        if kind=="transport_after_commit":raise RuntimeError("private transport detail")
        slot["project_admission_suspend"]=None
        return receipt
    monkeypatch.setattr(runtime.jobs,"pause_workstream_admission",lost)
    result=call()["result"]
    assert result["disposition"]=="EFFECT_UNKNOWN" and result["receipt"] is None
    assert count(runtime)==before+1 and "private" not in str(result)
    slot["project_admission_suspend"]=grant
    status=call(status=True)["result"]
    assert status["state"]=="OBSERVED" and status["receipt"]["state"]=="PAUSED"
    assert count(runtime)==before+1

def test_publication_drift_in_commit_rolls_back_without_claiming_no_effect(tmp_path,monkeypatch):
    runtime,service,_,_,call=setup(tmp_path);original=runtime.store.append_event;snapshot=service.cache.snapshot;changed=[False]
    def sample():
        value=snapshot()
        return replace(value,publication=value.publication+1) if changed[0] else value
    monkeypatch.setattr(service.cache,"snapshot",sample)
    def drift(connection,**kwargs):
        original(connection,**kwargs)
        if kwargs["event_type"]=="WORKSTREAM_ADMISSION_SUSPENDED":changed[0]=True
    monkeypatch.setattr(runtime.store,"append_event",drift);before=count(runtime)
    assert call()["result"]["disposition"]=="EFFECT_UNKNOWN"
    assert count(runtime)==before


def test_actual_state_read_qualifies_capability_but_does_not_pause_or_infer_running_work(tmp_path):
 runtime,_,_,_,call=setup(tmp_path);before=count(runtime)
 body=call(state=True)["result"]
 assert body["availability"]=="AVAILABLE" and body["state"]=="NOT_SUSPENDED"
 assert body["current_receipt"] is None and body["capability"]["can_pause"] is True
 assert body["capability"]["target_ref"].startswith("project_admission:")
 assert count(runtime)==before
 committed=call()["result"]["receipt"]
 after=call(state=True)["result"]
 assert after["state"]=="PAUSED" and after["capability"]["can_pause"] is False
 assert after["current_receipt"]==committed and count(runtime)==before+1

def test_state_read_requires_the_real_project_grant_not_just_a_method_or_read_login(tmp_path):
 runtime,_,bindings,_,call=setup(tmp_path);before=count(runtime)
 bindings["profiles"]["member-0"]["project_admission_suspend"]=None
 body=call(state=True)["result"]
 assert body["availability"]=="UNAVAILABLE" and body["state"] is None
 assert body["capability"] is None and body["current_receipt"] is None
 assert count(runtime)==before

def test_state_read_withholds_a_pause_race_without_publishing_stale_capability(tmp_path,monkeypatch):
 runtime,_,_,_,call=setup(tmp_path);read=runtime.jobs.read_workstream_admission_suspension;calls=[]
 def raced(work):
  value=read(work);calls.append(True)
  if len(calls)==1:runtime.jobs.pause_workstream_admission(WORK,command_id="other-user-pause",actor="test-race")
  return value
 monkeypatch.setattr(runtime.jobs,"read_workstream_admission_suspension",raced)
 body=call(state=True)["result"]
 assert body["availability"]=="UNAVAILABLE" and body["reason_codes"]==["SOURCE_CHANGED"]
 assert body["capability"] is None and body["current_receipt"] is None
