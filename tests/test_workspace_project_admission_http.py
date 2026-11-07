"""Fixed HTTP composition; real Runtime/grants, injected verified auth boundary.

JWT verifier is unchanged and covered by its incumbent suite; this file does
not label injection as authenticated live or signed-socket installation proof.
"""
import copy
from integrations.mastermind_workspace_app.project_admission_permissions import project_admission_permissions
import json
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import pytest

from common import workspace_project_admission_control_contract as control
from control_plane.workspace_project_admission import project_admission_request, read_project_admission_control
from integrations.mastermind_workspace_app import app as owner
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig
from integrations.mastermind_workspace_app.project_admission import project_admission_http
from integrations.mastermind_workspace_app.contract import workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from tests.test_workspace_project_authoring_grant import verified
from tests.test_workspace_project_suspend_grant import fixture as grant_fixture
from tests.test_workspace_member_bindings import principal
from tests.test_workspace_project_admission import setup, count, WORK
from tests.test_workspace_read_app import rsa_key, _FakeJwksCache

PAUSE="mmos-project-pause-"+"a"*40
RESUME="mmos-project-resume-"+"b"*40


def endpoint(tmp_path,monkeypatch,rsa_key,*,real_jwt=False):
    runtime,service,bindings,base,_,=setup(tmp_path)
    policy=grant_fixture()[0]
    bindings["profiles"]["member-0"]["project_admission_resume"]={"work_ref":WORK,"permission_digest":"4"*64}
    who=verified(policy,principal(bindings));seen=[];after=[None]
    instant=500;headers={}
    authenticator=JwtAuthenticator(policy=policy,jwks_cache=_FakeJwksCache(rsa_key))
    if real_jwt:
        import asyncio
        from dataclasses import replace
        from tests.test_workspace_read_app import _workspace_policy, _workspace_token, NOW
        from integrations.mastermind_workspace_app.contract import principal_frame
        actual_policy=_workspace_policy()
        policy=replace(policy,allowed_subject_digests=tuple(sorted(set(policy.allowed_subject_digests)|set(actual_policy.allowed_subject_digests))))
        authenticator=JwtAuthenticator(policy=policy,jwks_cache=_FakeJwksCache(rsa_key))
        encoded=_workspace_token(rsa_key)
        who=asyncio.run(authenticator.verify_authorization_header("Bearer "+encoded,now=NOW))
        bindings["profiles"]["member-0"]["binding"].update(principal_frame(who))
        service.authorize=workspace_authorizers(policy=policy,load_bindings=lambda:legacy_workspace_document(bindings,policy))[1]
        instant=NOW;headers={"Authorization":"Bearer "+encoded}
    service._project_admission_permissions=project_admission_permissions(policy=policy,load_bindings=lambda:bindings)
    async def authenticate(*args,**kwargs):return who
    if not real_jwt:monkeypatch.setattr(owner,"_authenticate",authenticate)
    class Client:
        async def request(self,frame):
            seen.append(copy.deepcopy(frame))
            kwargs=dict(permissions=service._project_admission_permissions,host_ready=lambda:True,now=lambda:instant)
            if frame["schema"]==control.FRAME_SCHEMA:value=read_project_admission_control(service,frame,**kwargs)
            else:value=project_admission_request(service,frame,**kwargs,status=frame["operation"].startswith("read_"),resume="resumption" in frame["schema"])
            if after[0]:after[0](value)
            return value
    read_auth=workspace_authorizers(policy=policy,load_bindings=lambda:legacy_workspace_document(bindings,policy))[0]
    config=WorkspaceAppConfig(authenticator=authenticator,
        authorize_principal=read_auth,client=Client(),now=lambda:instant)
    routes=[]
    for mode in ["current","status","pause","resume"]:
        async def handler(request,mode=mode):return await project_admission_http(request,config=config,load_bindings=lambda:bindings,mode=mode)
        routes.append(Route('/'+mode,handler,methods=["GET","POST"]))
    client=TestClient(Starlette(routes=routes),headers=headers)
    return runtime,bindings,base["selection"],seen,after,client


def test_http_to_actual_runtime_return_and_original_status_join(tmp_path,monkeypatch,rsa_key):
    runtime,_,selected,seen,_,client=endpoint(tmp_path,monkeypatch,rsa_key)
    project={key:value for key,value in selected.items() if key!="command_id"}
    query=project
    with client:
        body=client.get('/current',params=query).json()
        assert body["availability"]=="AVAILABLE" and body["permissions"]=={"pause":True,"resume":True}
        response=client.post('/pause',json={"selection":project,"command_id":PAUSE})
        assert response.headers['cache-control']=='no-store'
        assert response.json()["disposition"]=="COMMITTED"
        paused=client.get('/current',params=query).json()
        resumed=client.post('/resume',json={"selection":project,"command_id":RESUME,"pause_token":paused["pause_token"]}).json()
        assert resumed["disposition"]=="COMMITTED"
        original=client.get('/status',params={**query,"command_id":PAUSE,"kind":"project_pause"}).json()
        assert original["receipt"]["state"]=="PAUSED"
        assert client.get('/current',params=query).json()["state"]=="RESUMED"
    assert count(runtime)==3 and all('actor' not in frame for frame in seen)

@pytest.mark.parametrize("change",["caller_principal","unknown_root","query_action","wrong_prefix","duplicate_json","wrong_content_type","oversize"])
def test_fixed_public_payload_refuses_before_owner_dispatch(tmp_path,monkeypatch,rsa_key,change):
    runtime,_,selected,seen,_,client=endpoint(tmp_path,monkeypatch,rsa_key)
    project={key:value for key,value in selected.items() if key!="command_id"}
    payload={"selection":project,"command_id":PAUSE};kwargs={"json":payload};url='/pause'
    if change=="caller_principal":payload["principal"]={}
    elif change=="unknown_root":project["runtime_path"]="/private"
    elif change=="query_action":url+='?action=resume'
    elif change=="wrong_prefix":payload["command_id"]=RESUME
    elif change=="duplicate_json":kwargs={"content":'{"selection":'+json.dumps(project)+',"command_id":"'+PAUSE+'","command_id":"'+PAUSE+'"}',"headers":{"content-type":"application/json"}}
    elif change=="wrong_content_type":kwargs={"content":json.dumps(payload),"headers":{"content-type":"text/plain"}}
    elif change=="oversize":kwargs={"content":" "*16385,"headers":{"content-type":"application/json"}}
    with client:result=client.post(url,**kwargs)
    assert result.status_code==400 and seen==[] and count(runtime)==1

@pytest.mark.parametrize("change",["revoke_after_commit","transport_after_commit","foreign_scope"])
def test_post_dispatch_loss_never_claims_not_dispatched_or_exposes_foreign_scope(tmp_path,monkeypatch,rsa_key,change):
    runtime,bindings,selected,seen,after,client=endpoint(tmp_path,monkeypatch,rsa_key)
    project={key:value for key,value in selected.items() if key!="command_id"}
    slot=bindings["profiles"]["member-0"];grant=copy.deepcopy(slot["project_admission_suspend"])
    def mutate(value):
        if change=="revoke_after_commit":slot["project_admission_suspend"]=None
        elif change=="transport_after_commit":raise RuntimeError("private")
        elif value.get("ok") and value["result"].get("owner_context"):value["result"]["owner_context"]["principal_scope"]="e"*64
    after[0]=mutate
    with client:
        if change=="foreign_scope":
            result=client.get('/current',params=project).json()
            assert result["availability"]=="UNAVAILABLE" and result["owner_context"] is None and count(runtime)==1
        else:
            result=client.post('/pause',json={"selection":project,"command_id":PAUSE}).json()
            assert result["disposition"]=="EFFECT_UNKNOWN" and result["receipt"] is None and count(runtime)==2
            slot["project_admission_suspend"]=grant;after[0]=None
            status=client.get('/status',params={**project,"command_id":PAUSE,"kind":"project_pause"}).json()
            assert status["state"]=="OBSERVED" and status["receipt"]["state"]=="PAUSED"


def test_actual_jwt_authenticator_refuses_missing_bearer_before_client_or_effect(tmp_path,monkeypatch,rsa_key):
    runtime,_,selected,seen,_,client=endpoint(tmp_path,monkeypatch,rsa_key)
    from integrations.mastermind_executive_app.app import _authenticate as actual_authenticate
    monkeypatch.setattr(owner,"_authenticate",actual_authenticate)
    project={key:value for key,value in selected.items() if key!="command_id"}
    with client:result=client.post('/pause',json={"selection":project,"command_id":PAUSE})
    assert result.status_code==401 and seen==[] and count(runtime)==1


def test_actual_signed_jwt_real_grants_and_runtime_round_trip(tmp_path,monkeypatch,rsa_key):
    runtime,_,selected,seen,_,client=endpoint(tmp_path,monkeypatch,rsa_key,real_jwt=True)
    project={key:value for key,value in selected.items() if key!="command_id"}
    with client:
        current=client.get('/current',params=project)
        assert current.status_code==200 and current.json()["availability"]=="AVAILABLE"
        result=client.post('/pause',json={"selection":project,"command_id":PAUSE}).json()
        assert result["disposition"]=="COMMITTED"
        paused=client.get('/current',params=project).json()
        resumed=client.post('/resume',json={"selection":project,"command_id":RESUME,"pause_token":paused["pause_token"]}).json()
        assert resumed["disposition"]=="COMMITTED"
        assert client.get('/status',params={**project,"kind":"project_resume","command_id":RESUME}).json()["state"]=="OBSERVED"
        assert client.get('/current',params=project).json()["state"]=="RESUMED"
    assert count(runtime)==3 and len(seen)==6
