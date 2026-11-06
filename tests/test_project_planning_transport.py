"""Two actual signed resources -> real temporary Unix peer -> canonical Runtime.

Only physical worker dispatch is inert. No installed service or credentials are
read, and every socket, private artifact and Runtime row belongs to this test.
"""
import asyncio
import dataclasses
import json
from pathlib import Path
import tempfile
import time
import os
import fcntl

import httpx
import jwt
import pytest

from test_project_planning_factory import fixture
from test_mastermind_executive_app_asgi import rsa_key, _FakeJwksCache, KID
from control_plane.executive_service import CeoIngressAppBinding
from integrations.mastermind_executive_app.project_planning_factory import build_ingress_owner
from integrations.mastermind_executive_app.os_transport import OsExecutiveTransportApp
from integrations.mastermind_executive_app.direct_native import DirectNativeResultClient
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from integrations.executive_mcp.server import AuditedWorkspaceApp
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier


class Audit:
    def __init__(self): self.events=[]
    def emit(self,event): self.events.append(event)


def composition(tmp_path,monkeypatch,key):
    factory,args,armed,observed=fixture(tmp_path,monkeypatch)
    clock=[int(time.time())]
    audit=Audit()
    def pair(policy):
        auth=JwtAuthenticator(policy=policy,jwks_cache=_FakeJwksCache(key))
        return auth,MastermindTokenVerifier(authenticator=auth,policy=policy,now=lambda:clock[0],audit_sink=audit)
    auth,verifier=pair(factory.policies.submit)
    wauth,wverifier=pair(factory.workspace_policy)
    async def inner(scope,receive,send): raise AssertionError('no generic forwarding')
    workspace=AuditedWorkspaceApp(inner,wverifier,authenticator=wauth,authorize_principal=factory._authorize_workspace)
    calls=[]
    async def inert(job_id,*,access):
        access.check()
        calls.append(job_id)
        return None
    monkeypatch.setattr(factory.service,'_dispatch_direct_native',inert)
    app=dataclasses.replace(factory.app_binding,project_planning_provider_factory=lambda runtime:build_ingress_owner(factory))
    factory.app_binding=app;factory.service._ceo_ingress_app_binding=app
    def bearer(policy,**overrides):
        claims=dict(iss=policy.issuer,sub='inert-chairman',aud=policy.resource,client_id='inert-client',
            scope=' '.join(policy.required_scopes),iat=clock[0]-5,nbf=clock[0]-5,exp=clock[0]+600)
        claims.update(overrides)
        return jwt.encode(claims,key,algorithm='RS256',headers={'kid':KID,'typ':'at+jwt'})
    return factory,args,clock,audit,calls,auth,verifier,workspace,bearer,armed,observed


async def exercise(parts,action):
    factory,args,clock,audit,calls,auth,verifier,workspace,bearer,*_=parts
    with tempfile.TemporaryDirectory(prefix='mm-plan-',dir='/tmp') as short:
        from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody
        runtime=factory.service.runtime;directory=runtime.store.path.parent
        lock=directory/'executive-service.lock';fd=os.open(lock,os.O_CREAT|os.O_RDWR,0o600)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        marker=directory/'executive-service.running'
        marker.write_text(json.dumps(dict(instance_id='planning-test',pid=os.getpid())));marker.chmod(0o600)
        custody=ServiceRuntimeNamespaceCustody(runtime=runtime,service_lock_fd=fd,lock_path=lock,marker_path=marker,instance_id='planning-test')
        custody.start();factory.service._namespace_custody=custody
        sock=Path(short)/'ceo.sock'
        server=await asyncio.start_unix_server(factory.service._handle_ceo_ingress_connection,path=str(sock),limit=73728)
        edge=OsExecutiveTransportApp(lambda *args:None,submit_authenticator=auth,submit_verifier=verifier,
            clock=lambda:clock[0],workspace_app=workspace,
            direct_result_client=DirectNativeResultClient(sock,CeoIngressClient(read_timeout=5)))
        token=bearer(factory.policies.submit);second=bearer(factory.workspace_policy)
        headers=[('authorization','Bearer '+token),('x-mastermind-workspace-authorization','Bearer '+second)]
        arguments={k:v for k,v in args.items() if k!='principal'}
        arguments['private_request']=arguments['private_request'].decode()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=edge),base_url='https://mcp.mastermind-x.com') as client:
                await action(client,headers,arguments,token,second)
        finally:
            server.close();await server.wait_closed()
            tasks=list(factory.service._ceo_ingress_tasks)
            if tasks:await asyncio.wait_for(asyncio.gather(*tasks,return_exceptions=True),5)
            custody.close();os.close(fd)


def test_signed_two_resource_peer_admission_and_original_read_no_redispatch(tmp_path,monkeypatch,rsa_key):
    parts=composition(tmp_path,monkeypatch,rsa_key)
    async def action(client,headers,args,*tokens):
        first=await client.post('/os/executive/project-planning/submit',headers=headers,json={'arguments':args})
        assert first.status_code==200,first.text
        data=first.json()['data'];job=data['job_id']
        again=await client.post('/os/executive/project-planning/submit',headers=headers,json={'arguments':args})
        assert again.status_code==200,again.text
        assert again.json()['data']['duplicate'] is True
        base={k:args[k] for k in ('operation_key','work_ref')}
        status=await client.post('/os/executive/project-planning/status',headers=headers,json={'arguments':base})
        assert status.status_code==200,status.text
        assert status.json()['data']['job_id']==job
        result=await client.post('/os/executive/project-planning/result',headers=headers,json={'arguments':base})
        assert result.status_code==200,result.text
        assert result.json()['data']['availability']!='AVAILABLE'
        assert parts[4]==[job]
        assert len(parts[0].service.runtime.jobs.list_jobs())==1
        assert parts[0].service.runtime.attempts.list_attempts()==[]
        public=repr(parts[0].service.runtime.store.list_events())
        assert args['private_request'] not in public and 'Canonical private goal.' not in public
        for token in tokens:assert token not in first.text+again.text+status.text+result.text+public+repr(parts[3].events)
    asyncio.run(exercise(parts,action))


def test_signed_peer_drives_existing_managed_worker_to_retained_result_and_consumption(tmp_path,monkeypatch,rsa_key):
    from tests.test_direct_native_supervisor_runtime_join import make_direct_supervisor
    from control_plane.executive_service import ExecutiveControlService
    parts=composition(tmp_path,monkeypatch,rsa_key)
    factory=parts[0];service=factory.service;runtime=service.runtime
    service.supervisor=make_direct_supervisor(runtime,workspace_root=service.config.proof_workspace_root,
        runs_root=service.supervisor.runs_root,provider_home=tmp_path/'provider-home')
    failures=[]
    async def dispatch(job_id,*,access):
        try:return await ExecutiveControlService._dispatch_direct_native(service,job_id,access=access)
        except Exception as exc:failures.append(type(exc).__name__+': '+str(exc));raise
    original_wait=service._await_foreground_dispatch
    async def wait(*args,**kwargs):
        try:return await original_wait(*args,**kwargs)
        except Exception as exc:failures.append(type(exc).__name__+': '+str(exc));raise
    monkeypatch.setattr(service,'_await_foreground_dispatch',wait)
    monkeypatch.setattr(service,'_dispatch_direct_native',dispatch)
    def register(*,direct_native_access):
        direct_native_access.check()
        binding=runtime.jobs.direct_native_provenance(runtime.jobs.list_jobs()[0].job_id)['binding']
        metadata={key:binding[key] for key in ('routing_policy_version','execution_profile_id','execution_profile_digest','capability_policy_version','capability_policy_digest')}
        metadata['adapter_id']='codex-cli'
        runtime.workers.register_worker(binding['worker_id'],provider='codex',account_label='inert-planning',worker_type='codex-cli',
            capabilities=['read','research'],quota_classes={'default':dict(provider='codex',model=binding['model'],effort=binding['effort'],cost_class=binding['cost_class'],capabilities=['read','research'],metadata=metadata)})
    monkeypatch.setattr(service,'_register_worker',register)
    async def action(client,headers,args,*tokens):
        response=await client.post('/os/executive/project-planning/submit',headers=headers,json={'arguments':args})
        assert response.status_code==200,(response.text,failures,service._dispatch_errors)
        job_id=response.json()['data']['job_id']
        assert runtime.jobs.get_job(job_id).status.value=='COMPLETED'
        assert service.supervisor.adapter.start_count==1 and service._dispatch_tasks=={}
        spec=service.supervisor.adapter.spec
        assert spec.timeout_seconds==300 and spec.max_artifacts==0
        assert 'Private first request.' in spec.prompt and 'Canonical private goal.' in spec.prompt
        base={key:args[key] for key in ('operation_key','work_ref')}
        result=await client.post('/os/executive/project-planning/result',headers=headers,json={'arguments':base})
        assert result.status_code==200,result.text
        view=result.json()['data'];assert view['availability']=='AVAILABLE'
        consume={**base,'attempt_id':view['selection']['attempt_id'],'result_digest':view['result']['result_digest'],'consumption_operation_key':'explicit-original-consume'}
        for _ in range(2):
            acknowledged=await client.post('/os/executive/project-planning/consume',headers=headers,json={'arguments':consume})
            assert acknowledged.status_code==200,acknowledged.text
            assert acknowledged.json()['data']['consumption']['state']=='CONSUMED'
        duplicate=await client.post('/os/executive/project-planning/submit',headers=headers,json={'arguments':args})
        assert duplicate.status_code==200 and duplicate.json()['data']['duplicate'] is True
        assert service.supervisor.adapter.start_count==1 and len(runtime.attempts.list_attempts())==1
    asyncio.run(exercise(parts,action))


@pytest.mark.parametrize('change',['missing-second','duplicate-second','duplicate-first','wrong-resource','cross-account','cross-client','expired-second','denied-read','unarmed','stale-source'])
def test_two_resource_failures_never_create_or_dispatch(tmp_path,monkeypatch,rsa_key,change):
    parts=composition(tmp_path,monkeypatch,rsa_key)
    async def action(client,headers,args,*tokens):
        if change=='missing-second':headers=headers[:1]
        if change=='duplicate-second':headers=headers+[headers[1]]
        if change=='duplicate-first':headers=headers+[headers[0]]
        overrides={'wrong-resource':dict(aud=parts[0].policies.submit.resource),'cross-account':dict(sub='another-account'),
            'cross-client':dict(client_id='another-client'),'expired-second':dict(iat=parts[2][0]-800,nbf=parts[2][0]-800,exp=parts[2][0]-100)}
        if change in overrides:
            headers=[headers[0],(headers[1][0],'Bearer '+parts[8](parts[0].workspace_policy,**overrides[change]))]
        if change=='denied-read':parts[0]._test_bindings[0]['profiles']['member-0']['enabled']=False
        if change=='unarmed':parts[9][0]=False
        if change=='stale-source':parts[10][0]['content_sha256']='f'*64
        response=await client.post('/os/executive/project-planning/submit',headers=headers,json={'arguments':args})
        assert response.status_code in (401,403,503),response.text
        assert parts[4]==[] and parts[0].service.runtime.jobs.list_jobs()==[]
        for token in tokens:assert token not in response.text+repr(parts[3].events)
    asyncio.run(exercise(parts,action))


def test_second_original_expiry_is_requalified_at_actual_control_action(tmp_path,monkeypatch,rsa_key):
    parts=composition(tmp_path,monkeypatch,rsa_key)
    async def action(client,headers,args,*tokens):
        headers=[headers[0],(headers[1][0],'Bearer '+parts[8](parts[0].workspace_policy,exp=parts[2][0]+1))]
        # Control's clock advances past only the secondary expiry. HTTP has
        # independently authenticated the still-live original signed token.
        parts[0].clock=lambda:parts[2][0]+2
        response=await client.post('/os/executive/project-planning/submit',headers=headers,json={'arguments':args})
        assert response.status_code==403,response.text
        assert parts[4]==[] and parts[0].service.runtime.jobs.list_jobs()==[]
    asyncio.run(exercise(parts,action))


def test_post_commit_dispatch_failure_remains_original_unknown_and_status_never_replays(tmp_path,monkeypatch,rsa_key):
    parts=composition(tmp_path,monkeypatch,rsa_key)
    calls=[]
    async def failed(job_id,*,access):
        access.check();calls.append(job_id)
        raise RuntimeError('inert post-admission failure')
    monkeypatch.setattr(parts[0].service,'_dispatch_direct_native',failed)
    async def action(client,headers,args,*tokens):
        first=await client.post('/os/executive/project-planning/submit',headers=headers,json={'arguments':args})
        assert first.status_code==202 and first.json()['error']['code']=='effect_unknown',first.text
        original=await client.post('/os/executive/project-planning/status',headers=headers,json={'arguments':{key:args[key] for key in ('operation_key','work_ref')}})
        assert original.status_code==200 and original.json()['data']['job_id']==calls[0],original.text
        duplicate=await client.post('/os/executive/project-planning/submit',headers=headers,json={'arguments':args})
        assert duplicate.status_code==200 and duplicate.json()['data']['duplicate'] is True,duplicate.text
        assert len(calls)==1 and len(parts[0].service.runtime.jobs.list_jobs())==1
        assert parts[0].service.runtime.attempts.list_attempts()==[]
    asyncio.run(exercise(parts,action))


def test_secondary_header_is_not_forwarded_to_other_os_routes(tmp_path,monkeypatch,rsa_key):
    parts=composition(tmp_path,monkeypatch,rsa_key)
    async def action(client,headers,args,*tokens):
        response=await client.post('/os/executive/context',headers=headers,json={})
        assert response.status_code==403
        assert parts[4]==[] and parts[0].service.runtime.jobs.list_jobs()==[]
    asyncio.run(exercise(parts,action))


@pytest.mark.parametrize('name',['Authorization','X-Mastermind-Workspace-Authorization'])
@pytest.mark.parametrize('template',['{}: Bearer short-private','{{"{}":"Bearer short-private"}}',"{{'{}': 'Bearer short-private'}}"])
def test_both_resource_headers_redact_before_diagnostic_truncation(name,template):
    from common.redaction import sanitize_external_text
    text=sanitize_external_text(template.format(name),include_environment=False)
    assert 'short-private' not in text and '<redacted>' in text
