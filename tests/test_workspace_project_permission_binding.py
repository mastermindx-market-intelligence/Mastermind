"""Actual upper grant owner through one private nominal composition source."""
import dataclasses
import types
import pytest
from common.workspace_project_admission_contract import OPERATION as PAUSE
from common.workspace_project_resumption_contract import OPERATION as RESUME
from common.executive_workspace_contract import permission_stamp
from control_plane.workspace_project_permission_binding import ProjectAdmissionPermissions,ProjectPermissionSourceUnavailable
from integrations.mastermind_workspace_app.project_admission_permissions import project_admission_permissions
from integrations.mastermind_workspace_app import project_authoring_grant as grant
from tests.test_workspace_project_suspend_grant import fixture
from tests.test_workspace_member_bindings import principal
from tests.test_workspace_project_admission import setup


def source():
    policy,bindings=fixture();bindings['profiles']['member-0']['project_admission_resume']={'work_ref':'WS:SYNTHETIC-PROJECT','permission_digest':'4'*64}
    return policy,bindings,project_admission_permissions(policy=policy,load_bindings=lambda:bindings)


def test_each_incumbent_grant_stamp_and_scope_is_unchanged_and_current():
    policy,bindings,issued=source();who=principal(bindings)
    for action in [PAUSE,RESUME]:
        actual=issued.authorizer(action=action,work_ref='WS:SYNTHETIC-PROJECT')
        expected=grant.workspace_project_authorizers(policy=policy,load_bindings=lambda:bindings,action=action,work_ref='WS:SYNTHETIC-PROJECT')[1]
        assert actual(who) is True and permission_stamp(actual,who)==permission_stamp(expected,who)
        assert issued.authorizer(action=action,work_ref='WS:FOREIGN')(who) is False
    bindings['profiles']['member-0']['project_admission_suspend']=None
    assert issued.authorizer(action=PAUSE,work_ref='WS:SYNTHETIC-PROJECT')(who) is False
    assert issued.authorizer(action=RESUME,work_ref='WS:SYNTHETIC-PROJECT')(who) is True
    with pytest.raises(ValueError):issued.authorizer(action='ADOPT_PLAN',work_ref='WS:SYNTHETIC-PROJECT')


@pytest.mark.parametrize('change',['loader','policy','factory','method','policy_fields','binding_context','callback_owner'])
def test_rebound_owner_context_never_yields_an_authorizer(monkeypatch,change):
    policy,bindings,issued=source();owner=issued._owner
    if change=='loader':object.__setattr__(owner,'_load_bindings',lambda:bindings)
    elif change=='policy':object.__setattr__(owner,'_policy',dataclasses.replace(policy))
    elif change=='factory':object.__setattr__(owner,'_factory',lambda **kw:(lambda x:True,lambda x:True))
    elif change=='method':monkeypatch.setattr(type(owner),'_authorizer',lambda *a,**kw:lambda x:True)
    elif change=='policy_fields':object.__setattr__(policy,'policy_id',policy.policy_id+'-changed')
    elif change=='binding_context':object.__setattr__(issued,'_context',())
    else:object.__setattr__(issued,'_callback',source()[2]._callback)
    with pytest.raises(ProjectPermissionSourceUnavailable):issued.authorizer(action=PAUSE,work_ref='WS:SYNTHETIC-PROJECT')


def test_labels_unissued_objects_and_lookalike_callbacks_cannot_create_owner(tmp_path):
    policy,bindings,issued=source()
    with pytest.raises(ProjectPermissionSourceUnavailable):ProjectAdmissionPermissions(object(),issued._owner,issued._context,issued._callback,issued._qualified_owner)
    with pytest.raises(ValueError):project_admission_permissions(policy=types.SimpleNamespace(resource=policy.resource,required_scopes=policy.required_scopes),load_bindings=lambda:bindings)
    runtime,service,_,_,call=setup(tmp_path);before=len(runtime.jobs.list_jobs())
    service._project_admission_permissions=types.SimpleNamespace(authorizer=lambda **kw:lambda p:True)
    assert call()['result']['disposition']=='NOT_DISPATCHED' and len(runtime.jobs.list_jobs())==before


def test_detaching_service_source_during_commit_withholds_and_rolls_back(tmp_path,monkeypatch):
    runtime,service,_,_,call=setup(tmp_path);append=runtime.store.append_event
    def detach(connection,**kwargs):
        append(connection,**kwargs)
        if kwargs['event_type']=='WORKSTREAM_ADMISSION_SUSPENDED':service._project_admission_permissions=None
    monkeypatch.setattr(runtime.store,'append_event',detach)
    result=call()['result'];assert result['disposition']=='EFFECT_UNKNOWN' and result['receipt'] is None
    assert runtime.jobs.read_workstream_admission_suspension('WS:ONE') is None
