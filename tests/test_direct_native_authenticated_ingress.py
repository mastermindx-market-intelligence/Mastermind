"""Signed real App/HTTP/private Unix/Runtime join; no physical worker here.

This fixture qualifies actual admission and custody before the independently
joined sealed Supervisor completion. The no-execution adapter deliberately
cannot launch; its error never rewrites a durable Job as a no-effect refusal.
"""
import asyncio
import dataclasses
import hashlib
import os
import pytest
from control_plane import executive_runtime as er
from control_plane.executive_service import ExecutiveControlService,CeoIngressAppBinding
from integrations.executive_mcp.web_ceo import WebCeoV2InstalledExecutiveReaders
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.mastermind_executive_app.os_commission_client import StudioCommissionClient,PreparationResult
from tests import test_paid_authenticated_launch_producer as app
from tests.test_mastermind_os_executive_transport import headers
from tests import test_mastermind_executive_app_asgi as auth
rsa_key=auth.rsa_key
short_socket_root=auth.short_socket_root


def test_actual_native_ts_authenticated_http_unix_admits_one_role_null_job(rsa_key,tmp_path,short_socket_root,monkeypatch):
    mastermind=tmp_path/'mastermind';macro=tmp_path/'macro'
    commit=auth._git_repo(mastermind)
    (macro/'scripts').mkdir(parents=True);(macro/'scripts'/'agentos.py').write_text('')
    (macro/'agentos').mkdir();auth._git_repo(macro)
    source=dict(schema_version=er.EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,work_ref=app.MANIFEST_PROJECTION['workstream'],
        commission_ref=dict(repository='mastermindx-market-intelligence/Mastermind',commit=commit,path='README.md',
            content_sha256=hashlib.sha256((mastermind/'README.md').read_bytes()).hexdigest()),watch_mode=None)
    async def exercise():
        base=auth._real_service(tmp_path,socket_root=short_socket_root,mastermind_root=mastermind,macro_root=macro)
        config=dataclasses.replace(base.config,proof_source_repository=mastermind,proof_base_sha=commit,
            proof_shared_gid=os.getegid(),ceo_submit_armed=True)
        config.proof_workspace_root.mkdir(parents=True)
        grounding=auth._RealGitGroundingProvider(mastermind_root=mastermind,macro_root=macro)
        readers=WebCeoV2InstalledExecutiveReaders(repo_root=mastermind,macro_root=macro,runtime_root=config.runtime_root)
        service=ExecutiveControlService(config,supervisor_factory=lambda _:auth._NoExecutionSupervisor(),
            ceo_submit_admission_guard=lambda:None,direct_native_generation_provider=lambda:'a'*64,
            ceo_ingress_socket_path=short_socket_root/'native-http.sock',ceo_ingress_peer_uid=os.geteuid()+1000,
            ceo_ingress_armed=False,ceo_ingress_grounding_provider=grounding,
            ceo_ingress_dialogue_source_provider=lambda _intent,_work:source,
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,grounding_provider=grounding,read_provider=readers))
        await service.start()
        try:
            settings=auth._real_app_settings(rsa_key,mastermind_root=mastermind,macro_root=macro,ceo_ingress_socket_path=service.ceo_ingress_socket_path)
            kwargs=dict(resource=app.OS_RESOURCE,resource_metadata_url=app.OS_RESOURCE+'/.well-known/oauth-protected-resource')
            settings=dataclasses.replace(settings,read_from_ceo_ingress=True,policies=AppPolicies(read=auth._read_policy(**kwargs),submit=auth._submit_policy(**kwargs)))
            token=auth._submit_token(rsa_key,aud=app.OS_RESOURCE)
            async def publication(self,*,arguments,bearer,principal_scope):
                assert bearer==token
                return PreparationResult('prepared',arguments['operation_key'],commit,source['commission_ref']['content_sha256'])
            monkeypatch.setattr(StudioCommissionClient,'prepare',publication)
            async with app.launch_http(settings,StudioCommissionClient(port=45025)) as http:
                context=await http.post('/os/executive/context',headers=headers(token),json={})
                assert context.status_code==200,context.text
                manifest=dict(app.MANIFEST_PROJECTION,profiles=[*app.MANIFEST_PROJECTION['profiles'],dict(ref='native_research_only',label='Native research only')])
                payload=app.actual_launch_payload(tmp_path,context.json()['principal_scope'],profile_ref='native_research_only',manifest_projection=manifest)
                response=await http.post('/os/executive/submit',headers=headers(token),json={'arguments':payload})
                assert response.status_code==200,response.text
                result=response.json();assert result['status']=='accepted',result
                receipt=result['receipt'];assert receipt['schema']=='mastermind.ceo_direct_native_receipt.v1'
                job=service.runtime.jobs.get_job(receipt['job_id'])
                assert job.orchestration_role is None and job.parent_job_id is None and job.root_job_id==job.job_id
                assert job.attempt_limit==1 and job.allowed_write_paths==[] and job.validation_commands==[]
                assert job.constraints['execution_profile_id']=='sealed.worker.readonly.no-extensions.v1'
                assert len(service.runtime.jobs.list_jobs())==1 and service.runtime.attempts.list_attempts()==[]
                assert 'original direct dispatch unavailable' in service._dispatch_errors[job.job_id]
                repeated=await http.post('/os/executive/submit',headers=headers(token),json={'arguments':payload})
                assert repeated.status_code==200,repeated.text
                assert repeated.json()['receipt']['duplicate'] is True
                assert len(service.runtime.jobs.list_jobs())==1
                found=await http.post('/os/executive/direct-native/result',headers=headers(token),json=dict(work_ref=source['work_ref'],job_id=job.job_id,attempt_id=None))
                assert found.status_code==200,found.text
                assert found.json()['availability']=='UNAVAILABLE' and found.json()['reason_codes']==['NOT_TERMINAL'],found.text
        finally:await service.close()
    asyncio.run(exercise())
