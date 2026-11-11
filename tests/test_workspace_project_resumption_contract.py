"""Closed Resume wire checked against actual Runtime-owned receipts."""
import copy
import json
import pytest
from common import workspace_project_resumption_contract as wire
from common import workspace_project_admission_contract as pause
from common import workspace_project_admission_control_contract as control
from control_plane.executive_runtime import Runtime
from control_plane.workstream_resumption_contract import pause_receipt_digest
from tests.test_workspace_project_suspend_grant import fixture
from tests.test_workspace_member_bindings import principal

WORK="WS:ONE"
@pytest.fixture(scope="module")
def source(tmp_path_factory):
    runtime=Runtime.at(tmp_path_factory.mktemp("resume-wire"))
    stopped=runtime.jobs.pause_workstream_admission(WORK,command_id="pause-original",actor="source-test")
    token={"event_id":stopped["event_id"],"receipt_digest":pause_receipt_digest(stopped)}
    returned=runtime.jobs.resume_workstream_admission(WORK,command_id="resume-original",actor="source-test",
        expected_pause_event_id=token["event_id"],expected_pause_receipt_digest=token["receipt_digest"])
    frame={"schema":wire.FRAME_SCHEMA,"operation":wire.OPERATION,
        "selection":{"work_ref":WORK,"command_id":"resume-original"},
        "principal":principal(fixture()[1]),"admission_expires_at":1000,"pause_token":token}
    body={"schema":wire.ACTION_RESULT_SCHEMA,"selection":copy.deepcopy(frame["selection"]),"disposition":"COMMITTED","receipt":returned,"reason_codes":[]}
    return frame,body,stopped


def test_actual_runtime_receipt_and_rootless_or_explicit_root_are_closed_and_detached(source):
    frame,body,_=map(copy.deepcopy,source)
    for root in [None,"JOB-001"]:
        if root:
            frame["selection"]["root_job_id"]=root;body["selection"]["root_job_id"]=root
        assert wire.validate_frame(frame)==frame
        assert wire.validate_action_result(body,frame["selection"])==body
        assert json.loads(wire.canonical_request_bytes(frame))==frame
        result=wire.validate_action_result(body,frame["selection"])
        result["receipt"]["state"]="tampered"
        assert body["receipt"]["state"]=="RESUMED"
    status=copy.deepcopy(frame);status.update(schema=wire.STATUS_FRAME_SCHEMA,operation=wire.STATUS_OPERATION);status.pop("pause_token")
    assert wire.validate_frame(status,status=True)==status

@pytest.mark.parametrize("path,value",[
    (("schema",),"unknown"),(("operation",),"pause_workstream_admission"),(("actor",),"caller"),
    (("selection","work_ref"),"WS:../PRIVATE"),(("selection","work_ref"),"WS:Other"),
    (("selection","root_job_id"),None),(("selection","root_job_id"),"JOB-1\n"),
    (("selection","command_id"),"x"*129),(("selection","command_id"),True),
    (("principal","scopes"),["workspace.write"]),(("principal","account"),"private"),
    (("pause_token","event_id"),True),(("pause_token","event_id"),0),(("pause_token","event_id"),1.0),
    (("pause_token","receipt_digest"),"A"*64),(("pause_token","receipt_digest"),True),
    (("pause_token","extra"),None),(("admission_expires_at",),True),(("admission_expires_at",),float("nan")),
])
def test_action_frame_rejects_unknown_fields_bad_selection_private_principal_and_invalid_pause_token(source,path,value):
    frame=copy.deepcopy(source[0]);target=frame
    for key in path[:-1]:target=target[key]
    target[path[-1]]=value
    with pytest.raises((ValueError,TypeError)):wire.validate_frame(frame)

@pytest.mark.parametrize("path,value",[
    (("schema",),pause.ACTION_RESULT_SCHEMA),(("extra",),None),(("selection","work_ref"),"WS:OTHER"),
    (("receipt","work_ref"),"WS:OTHER"),(("receipt","command_id"),"other-command"),
    (("receipt","state"),"PAUSED"),(("receipt","extra"),None),(("receipt","event_id"),True),
    (("receipt","pause_event_id"),True),(("receipt","pause_event_id"),999),(("receipt","committed_at_ms"),False),
    (("receipt","pause_receipt_digest"),"A"*64),(("receipt","request_digest"),"short"),
    (("receipt",),None),(("reason_codes",),["SOURCE_UNAVAILABLE"]),(("disposition",),"OBSERVED"),
])
def test_resume_result_never_accepts_foreign_receipt_unknown_schema_or_type_promotion(source,path,value):
    frame,body,_=map(copy.deepcopy,source);target=body
    for key in path[:-1]:target=target[key]
    target[path[-1]]=value
    with pytest.raises((ValueError,TypeError)):wire.validate_action_result(body,frame["selection"])


def test_unknown_and_not_observed_are_distinct_and_no_receipt_can_leak(source):
    frame,body,_=map(copy.deepcopy,source)
    body.update(disposition="EFFECT_UNKNOWN",receipt=None,reason_codes=["OWNER_OUTCOME_UNCONFIRMED"])
    assert wire.validate_action_result(body,frame["selection"])==body
    body["reason_codes"]=["SOURCE_UNAVAILABLE"]
    with pytest.raises(ValueError):wire.validate_action_result(body,frame["selection"])
    status={"schema":wire.STATUS_RESULT_SCHEMA,"selection":frame["selection"],"state":"NOT_OBSERVED","receipt":None,"reason_codes":[]}
    assert wire.validate_status_result(status,frame["selection"])==status
    status["receipt"]=source[1]["receipt"]
    with pytest.raises(ValueError):wire.validate_status_result(status,frame["selection"])


def test_all_validation_entrypoints_enforce_wire_size_and_status_has_no_resume_token(source,monkeypatch):
    frame,body,_=map(copy.deepcopy,source)
    monkeypatch.setattr(wire,"MAX_REQUEST_BYTES",1)
    with pytest.raises(ValueError):wire.validate_frame(frame)
    monkeypatch.setattr(wire,"MAX_RESPONSE_BYTES",1)
    with pytest.raises(ValueError):wire.validate_action_result(body,frame["selection"])
    frame.update(schema=wire.STATUS_FRAME_SCHEMA,operation=wire.STATUS_OPERATION)
    with pytest.raises(ValueError):wire.validate_frame(frame,status=True)

@pytest.mark.parametrize("state",["NOT_SUSPENDED","PAUSED","RESUMED","UNAVAILABLE"])
def test_control_read_projects_actual_closed_transition_and_independent_permissions(source,state):
    frame,action,stopped=map(copy.deepcopy,source)
    receipt={"PAUSED":stopped,"RESUMED":action["receipt"]}.get(state)
    body={"schema":control.BODY_SCHEMA,"selection":{"work_ref":WORK},
        "availability":"UNAVAILABLE" if state=="UNAVAILABLE" else "AVAILABLE","state":None if state=="UNAVAILABLE" else state,
        "permissions":None if state=="UNAVAILABLE" else {"pause":True,"resume":False},
        "owner_context":None if state=="UNAVAILABLE" else {"principal_scope":"a"*64},"current_receipt":receipt,
        "pause_token":frame["pause_token"] if state=="PAUSED" else None,
        "reason_codes":["SOURCE_UNAVAILABLE"] if state=="UNAVAILABLE" else []}
    assert control.validate_body(body,body["selection"])==body
    if state=="PAUSED":
        body["pause_token"]["event_id"]=True
        with pytest.raises(ValueError):control.validate_body(body,body["selection"])
    elif state!="UNAVAILABLE":
        body["permissions"]={"pause":False,"resume":False}
        with pytest.raises(ValueError):control.validate_body(body,body["selection"])
    else:
        body["owner_context"]={"principal_scope":"a"*64}
        with pytest.raises(ValueError):control.validate_body(body,body["selection"])
