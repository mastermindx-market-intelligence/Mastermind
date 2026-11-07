"""Project admission composition against actual canonical parser and Runtime."""
import copy
from pathlib import Path

import pytest
from common import workspace_project_admission_control_contract as wire
from control_plane.agentos_project_plan import AgentOsProjectPlanReader
from control_plane.workspace_project_admission import read_project_admission_control
from control_plane.executive_runtime import Runtime
from scripts import chairman_control_room as ccr
from tests.test_workspace_project_admission import setup, count, WORK
from tests.test_agentos_project_plan_source import source_git, read, SHA


def fixture(tmp_path, monkeypatch, *, source_git=None, rootless=False, resume_grant=True):
    runtime, service, bindings, action, call = setup(tmp_path)
    slot = bindings["profiles"]["member-0"]
    if resume_grant:
        slot["project_admission_resume"] = {"work_ref": WORK, "permission_digest": "4" * 64}
    frame = copy.deepcopy(action)
    frame.update(schema=wire.FRAME_SCHEMA, operation=wire.OPERATION)
    del frame["selection"]["command_id"]
    if rootless:
        runtime = Runtime.at(tmp_path/"empty-runtime")
        service.runtime = runtime
        del action["selection"]["root_job_id"]
        del frame["selection"]["root_job_id"]
        doc = service.cache.snapshot().document
        doc["sources"] = {"macro_sha": SHA}
        row = doc["autonomy"]["responsibilities"][0]
        row.update(root_job_id=None, root_job_candidates=[], root_job_ambiguous=False, runtime_root_state="UNKNOWN")
        owner = service.cache._owner()
        with owner.state_lock:
            owner.state_cache["doc"] = doc
            ccr._publish_source_validity(owner, doc, owner.validity_sample_fn(), owner.validity_sample_fn())
        reader = AgentOsProjectPlanReader(macro_root=Path("/qualified/macro"))
        runner, _ = source_git
        monkeypatch.setattr(AgentOsProjectPlanReader, "read", lambda self, *, work_ref: read(runner))
        service._project_plan_reader = reader
    def read_control():
        policy = __import__('tests.test_workspace_project_suspend_grant', fromlist=['fixture']).fixture()[0]
        return read_project_admission_control(service,frame,permissions=service._project_admission_permissions,host_ready=lambda:True,now=lambda:500)
    return runtime,service,bindings,action,call,frame,read_control


def test_each_action_grant_is_independent_and_current_gate_is_not_readiness(tmp_path,monkeypatch):
    runtime,_,bindings,_,call,_,current=fixture(tmp_path,monkeypatch)
    body=current()["result"]
    assert body["state"]=="NOT_SUSPENDED" and body["permissions"]=={"pause":True,"resume":True}
    assert len(body["owner_context"]["principal_scope"])==64 and count(runtime)==1
    receipt=call()["result"]["receipt"]
    assert current()["result"]["current_receipt"]==receipt
    slot=bindings["profiles"]["member-0"]
    slot["project_admission_suspend"]=None
    assert current()["result"]["permissions"]=={"pause":False,"resume":True}
    slot["project_admission_resume"]=None
    body=current()["result"]
    assert body["availability"]=="UNAVAILABLE" and body["permissions"] is None and body["owner_context"] is None


def test_explicit_retained_member_works_without_relaxing_singleton_navigation(tmp_path,monkeypatch):
    runtime,service,_,action,call,_,current=fixture(tmp_path,monkeypatch)
    other=runtime.jobs.create_job("another actual root",provenance={"workstream":WORK},command_id="other-root")
    snapshot=service.cache.snapshot();doc=snapshot.document;row=doc["autonomy"]["responsibilities"][0]
    row.update(root_job_id=None,root_job_candidates=sorted([other.job_id,action["selection"]["root_job_id"]]),root_job_ambiguous=True,runtime_root_state="CONFLICT",disagreements=[])
    owner=service.cache._owner()
    with owner.state_lock:
        owner.state_cache["doc"]=doc
        ccr._publish_source_validity(owner,doc,owner.validity_sample_fn(),owner.validity_sample_fn())
    from control_plane.workspace_read_service import _join
    with pytest.raises(LookupError):_join(doc,{"work_ref":WORK,"root_job_id":row["root_job_candidates"][0]})
    assert current()["result"]["availability"]=="AVAILABLE"
    assert call()["result"]["disposition"]=="COMMITTED"


def test_rootless_canonical_project_can_pause_before_any_job(tmp_path,monkeypatch,source_git):
    runtime,_,_,action,call,_,current=fixture(tmp_path,monkeypatch,rootless=True,source_git=source_git)
    assert count(runtime)==0
    assert current()["result"]["state"]=="NOT_SUSPENDED"
    result=call(value=action)["result"]
    assert result["disposition"]=="COMMITTED" and result["receipt"]["state"]=="PAUSED"
    assert count(runtime)==1
    with runtime.store.read() as connection:
        assert connection.execute("SELECT count(*) FROM jobs").fetchone()[0]==0
    assert current()["result"]["state"]=="PAUSED"

@pytest.mark.parametrize("change",["no_reader","no_project","stale_cache","source_commit","foreign_grant"])
def test_rootless_requires_actual_project_current_source_and_exact_grant(tmp_path,monkeypatch,source_git,change):
    runtime,service,bindings,action,call,_,current=fixture(tmp_path,monkeypatch,rootless=True,source_git=source_git)
    if change=="no_reader":service._project_plan_reader=None
    elif change=="foreign_grant":
        for key in ("project_admission_suspend","project_admission_resume"):bindings["profiles"]["member-0"][key]["work_ref"]="WS:OTHER"
    else:
        owner=service.cache._owner()
        if change=="no_project":owner.state_cache["doc"]["work"]=[]
        elif change=="stale_cache":owner.state_cache["composed_monotonic"]=-1000
        elif change=="source_commit":owner.state_cache["doc"]["sources"]["macro_sha"]="b"*40
    assert current()["result"]["availability"]=="UNAVAILABLE"
    assert call(value=action)["result"]["disposition"]=="NOT_DISPATCHED"
    assert count(runtime)==0


def test_rootless_source_change_inside_commit_rolls_back_and_retains_unknown_original(tmp_path,monkeypatch,source_git):
    runtime,service,_,action,call,_,_=fixture(tmp_path,monkeypatch,rootless=True,source_git=source_git)
    append=runtime.store.append_event
    def change(connection,**kwargs):
        append(connection,**kwargs)
        if kwargs["event_type"]=="WORKSTREAM_ADMISSION_SUSPENDED":
            service.cache._owner().state_cache["doc"]["sources"]["macro_sha"]="f"*40
    monkeypatch.setattr(runtime.store,"append_event",change)
    result=call(value=action)["result"]
    assert result["disposition"]=="EFFECT_UNKNOWN" and result["receipt"] is None and count(runtime)==0


def resume_call(service,bindings,action,pause_token,*,status=False):
    from common import workspace_project_resumption_contract as resume
    from control_plane.workspace_project_admission import project_admission_request
    from tests.test_workspace_project_suspend_grant import fixture as grant_fixture
    frame=copy.deepcopy(action)
    frame.update(schema=resume.STATUS_FRAME_SCHEMA if status else resume.FRAME_SCHEMA,
                 operation=resume.STATUS_OPERATION if status else resume.OPERATION)
    frame["selection"]["command_id"]="project-resume-original"
    if not status:frame["pause_token"]=pause_token
    return project_admission_request(service,frame,permissions=service._project_admission_permissions,
        host_ready=lambda:True,now=lambda:500,status=status,resume=True)

@pytest.mark.parametrize("rootless",[False,True])
def test_full_pause_resume_status_and_current_read_journey(tmp_path,monkeypatch,source_git,rootless):
    runtime,service,bindings,action,call,_,current=fixture(tmp_path,monkeypatch,rootless=rootless,source_git=source_git)
    paused=call(value=action)["result"]["receipt"]
    body=current()["result"]
    assert body["state"]=="PAUSED" and body["current_receipt"]==paused
    token=body["pause_token"]
    committed=resume_call(service,bindings,action,token)["result"]
    assert committed["disposition"]=="COMMITTED" and committed["receipt"]["state"]=="RESUMED"
    before=count(runtime)
    assert resume_call(service,bindings,action,token)["result"]==committed and count(runtime)==before
    assert resume_call(service,bindings,action,None,status=True)["result"]["receipt"]==committed["receipt"]
    after=current()["result"]
    assert after["state"]=="RESUMED" and after["pause_token"] is None
    assert after["current_receipt"]==committed["receipt"]
    assert call(status=True,value=action)["result"]["receipt"]==paused

@pytest.mark.parametrize("change",["no_resume_grant","foreign_resume_grant","stale_pause","bad_digest","revoke_inside","transport_after"])
def test_resume_requires_own_grant_current_token_and_original_unknown_recovery(tmp_path,monkeypatch,change):
    runtime,service,bindings,action,call,_,current=fixture(tmp_path,monkeypatch)
    call(value=action);token=current()["result"]["pause_token"];slot=bindings["profiles"]["member-0"]
    grant=copy.deepcopy(slot["project_admission_resume"])
    if change=="no_resume_grant":slot["project_admission_resume"]=None
    elif change=="foreign_resume_grant":slot["project_admission_resume"]["work_ref"]="WS:OTHER"
    elif change=="stale_pause":runtime.jobs.pause_workstream_admission(WORK,command_id="newer-pause",actor="other-user")
    elif change=="bad_digest":token["receipt_digest"]="e"*64
    elif change=="revoke_inside":
        original=runtime.store.append_event
        def revoke(connection,**kwargs):
            original(connection,**kwargs)
            if kwargs["event_type"]=="WORKSTREAM_ADMISSION_RESUMED":slot["project_admission_resume"]=None
        monkeypatch.setattr(runtime.store,"append_event",revoke)
    elif change=="transport_after":
        original=runtime.jobs.resume_workstream_admission
        def lost(*args,**kwargs):original(*args,**kwargs);raise RuntimeError("private transport detail")
        monkeypatch.setattr(runtime.jobs,"resume_workstream_admission",lost)
    before=count(runtime);result=resume_call(service,bindings,action,token)["result"]
    assert result["disposition"]==("NOT_DISPATCHED" if change in {"no_resume_grant","foreign_resume_grant"} else "EFFECT_UNKNOWN")
    assert result["receipt"] is None and "private" not in str(result)
    assert count(runtime)==before+(change=="transport_after")
    slot["project_admission_resume"]=grant
    status=resume_call(service,bindings,action,None,status=True)["result"]
    assert status["state"]==("OBSERVED" if change=="transport_after" else "NOT_OBSERVED")


def test_rootless_current_read_has_two_request_local_captures_and_rechecks_each_permission(tmp_path,monkeypatch,source_git):
    _,service,bindings,_,_,_,current=fixture(tmp_path,monkeypatch,rootless=True,source_git=source_git)
    original=service._read_project_plan;captures=[]
    def capture(selected):
        captures.append(dict(selected));return original(selected)
    monkeypatch.setattr(service,'_read_project_plan',capture)
    assert current()['result']['permissions']=={'pause':True,'resume':True}
    assert len(captures)==2
    # No cross-request source cache: another explicit read captures afresh.
    assert current()['result']['availability']=='AVAILABLE' and len(captures)==4
    bindings['profiles']['member-0']['project_admission_suspend']=None
    assert current()['result']['permissions']=={'pause':False,'resume':True} and len(captures)==6


@pytest.mark.parametrize('change',['revoke_pause','grant_resume','source'])
def test_rootless_shared_read_proof_never_publishes_late_grant_or_source_change(tmp_path,monkeypatch,source_git,change):
    runtime,service,bindings,_,_,_,current=fixture(tmp_path,monkeypatch,rootless=True,source_git=source_git,resume_grant=change!='grant_resume')
    original=runtime.jobs.read_workstream_admission_transition;observations=[]
    def observe(work):
        value=original(work);observations.append(True)
        if len(observations)==1:
            slot=bindings['profiles']['member-0']
            if change=='revoke_pause':slot['project_admission_suspend']=None
            elif change=='grant_resume':slot['project_admission_resume']={'work_ref':WORK,'permission_digest':'4'*64}
            else:service.cache._owner().state_cache['doc']['sources']['macro_sha']='f'*40
        return value
    monkeypatch.setattr(runtime.jobs,'read_workstream_admission_transition',observe)
    result=current()['result']
    assert result['availability']=='UNAVAILABLE' and result['permissions'] is None and result['owner_context'] is None
    assert count(runtime)==0
