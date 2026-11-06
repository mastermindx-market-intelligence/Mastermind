"""Actual installed compiler/publisher/READ Memory edit, one coherent fixture.

Temporary Git/Runtime/socket only. Existing root source seal, credential/PR owner
and Workspace enrollment are inert. The explicit physical-child interpreter is
this test's Python, not evidence of an installed native CF1 runtime. Projection
rows and DTOs are never rewritten.
"""
import asyncio
import copy
import json
import os
import sys
from pathlib import Path

import httpx
import pytest
from tests import test_knowledge_installed_source_join as installed_fixture
from tests.test_installed_knowledge_canonical_journey import configured,owner,env,isolated_git_env,identity,rsa_key,short_socket_root,settings
from tests.test_workspace_read_app import _authenticator,_workspace_token,NOW
from tests.test_workspace_project_authoring_grant import project_bindings
from tests.test_workspace_project_git_publisher import git,rev_parse
from tests.test_knowledge_source_service import inspection
from tests.fresh_conversation_full_cache import CanonicalFixtureCache
from integrations.mastermind_workspace_app.contract import principal_frame,workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document,SCHEMA_V5
from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig,create_workspace_app
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.executive_service import ExecutiveControlService,CeoIngressAppBinding
from tests.test_executive_ceo_ingress import _FakeGrounding,_config


@pytest.mark.parametrize('runtime_kind', ['portable', 'missing_interpreter'])
def test_actual_memory_edit_published_and_reopened_by_same_installed_readers(owner,identity,tmp_path,monkeypatch,rsa_key,short_socket_root,settings,runtime_kind):
    o=owner
    # Complete the input record's pre-existing DEC reference before pinning C;
    # no projected row/source identity is altered after qualification.
    from tests.test_agentos_project_knowledge import canonical_decision
    record=o['env'].clone/'agentos/decisions/DEC-EARLIER-CALL.md'
    record.parent.mkdir(parents=True,exist_ok=True);record.write_text(canonical_decision())
    git(o['env'].clone,'add',str(record.relative_to(o['env'].clone)))
    git(o['env'].clone,'commit','-m','Complete canonical fixture decision association')
    git(o['env'].clone,'push','origin','main')
    o['request']['source_commit']=rev_parse(o['env'].clone,'HEAD')
    # The donor fixture's native-runtime skip mark is not inherited here.
    # Force the hosted branch and qualify this test's interpreter with the
    # existing isolated-import check before issuing the compiler/collector.
    # A selected interpreter failure must not switch to another runtime.
    from ops.executive_os import capacity_source_contract
    from tests.test_project_discovery_installed_plan import _qualified_source_python
    missing = tmp_path/'absent-native-runtime'/'bin'/'python3.12'
    assert not missing.exists()
    monkeypatch.setattr(capacity_source_contract, 'PYTHON_BINARY', missing)
    python = missing if runtime_kind == 'missing_interpreter' else _qualified_source_python()
    if runtime_kind == 'portable':
        assert python == Path(sys.executable).absolute()
    monkeypatch.setattr(installed_fixture, 'PYTHON_BINARY', python)
    collector,git_owner=configured(o,identity,tmp_path,monkeypatch)
    assert collector._python == python
    original_runner, children, failures = collector._runner, [], []
    def observe_child(argv, **options):
        if any(str(value).endswith(('/scripts/agentos_project_knowledge_entry.py',
                                   '/scripts/agentos_project_knowledge_recipe_entry.py')) for value in argv):
            assert argv[:3] == [str(python), '-I', '-B']
            children.append(tuple(argv))
        try:
            return original_runner(argv, **options)
        except FileNotFoundError:
            failures.append((str(argv[0]), 'FileNotFoundError'))
            raise
    monkeypatch.setattr(collector, '_runner', observe_child)
    async def run():
        auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
        who=await auth.verify_authorization_header('Bearer '+token,now=NOW)
        _,document=project_bindings(selected=None);document['schema']=SCHEMA_V5
        for value in document['profiles'].values():
            value.update(enabled=False,binding=None,project_plan_proposal_publish=None,project_canonical_data_read=None)
        slot=document['profiles'][document['primary_profile']]
        slot.update(enabled=True,binding=dict(principal_frame(who),permission_digest='a'*64),project_canonical_data_read='5'*64,
            project_file_add={'work_ref':'WS:ALPHA','permission_digest':'3'*64},
            project_preference_set={'work_ref':'WS:ALPHA','permission_digest':'4'*64})
        o['bindings'].clear();o['bindings'].update(document);loader=lambda:o['bindings']
        app_auth,frame_auth=workspace_authorizers(policy=auth.policy,load_bindings=lambda:legacy_workspace_document(loader(),auth.policy))
        factory=InstalledWorkspaceSourceOperations(collector=collector,policy=auth.policy,load_bindings=loader,
            git_identity=git_owner,runtime_guard=lambda rt:rt is o['runtime'])
        factory._permissions._now=lambda:NOW
        canonical=CanonicalFixtureCache(collector._macro_root,tmp_path/'full-canonical',mastermind_revision=rev_parse(collector._source_root,'HEAD'))
        readers=dict(project_knowledge_catalogue_reader=collector.project_knowledge_catalogue_reader(macro_root=collector._macro_root),
            project_knowledge_source_reader=collector.project_knowledge_source_reader(macro_root=collector._macro_root),
            project_knowledge_memory_reader=collector.project_knowledge_memory_reader(macro_root=collector._macro_root))
        def provider(rt):
            data,discovery=factory.read_bindings(rt)
            return WorkspaceReadService(cache=canonical.cache,runtime=rt,authorize=frame_auth,armed={},runtime_identity={},
                canonical_project_data=data,project_discovery=discovery,**readers)
        host=ExecutiveControlService(_config(tmp_path/'host',socket_root=short_socket_root,runtime_root=o['runtime'].store.root),
            runtime_factory=lambda _:o['runtime'],supervisor_factory=lambda _:o['private'].supervisor,
            ceo_ingress_socket_path=short_socket_root/'memory.sock',ceo_ingress_peer_uid=os.geteuid()+1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=False,
                grounding_provider=_FakeGrounding(),workspace_read_provider_factory=provider,source_operation_provider_factory=factory))
        await host.start()
        try:
            app=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:NOW,authorize_principal=app_auth,
                client=CeoIngressWorkspaceClient(host.ceo_ingress_socket_path),source_operation_context=factory._permissions))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com',headers={'Authorization':'Bearer '+token}) as client:
                async def get(path,**query):
                    r=await client.get(path,params=query);assert r.status_code==200,r.text;return r.json()
                async def post(path,body):
                    r=await client.post(path,json=body);assert r.status_code==200,r.text;return r.json()
                async def catalogue():return await get('/workspace/project-knowledge/current',work_ref='WS:ALPHA')
                async def memory():return await get('/workspace/project-memory/current',work_ref='WS:ALPHA')
                async def prepare(request,action='set_project_communication_preference'):return await post('/workspace/source-operation/prepare',{'action':action,'request':request})
                async def submit(preview):return await post('/workspace/source-operation/submit',preview['selection']|{'preview_witness':preview['preview_witness']})
                async def land(preview,status):
                    root=tmp_path/('landing-'+str(o['pr'].create_calls));git(tmp_path,'clone',str(o['env'].origin),str(root))
                    git(root,'fetch','origin',status['receipt']['proposal']['head_branch']);git(root,'merge','--no-ff','--no-edit','FETCH_HEAD');git(root,'push','origin','main')
                    accepted=await post('/workspace/source-operation/reconcile',inspection(preview));assert accepted['disposition']=='accepted',accepted
                    return accepted
                programs=await get('/workspace/programs/current')
                assert any(row['work_ref']=='WS:ALPHA' for row in programs['control_room']['work'])
                if runtime_kind == 'missing_interpreter':
                    events_before=o['runtime'].events.list_events()
                    refused=await client.get('/workspace/project-knowledge/current',params={'work_ref':'WS:ALPHA'})
                    assert refused.status_code==503,refused.text
                    assert refused.json()['reason_codes']==['SOURCE_UNAVAILABLE']
                    assert refused.json()['project'] is None and refused.json()['source'] is None
                    assert len(children)==1 and o['pr'].create_calls==0
                    assert failures and all(item==(str(python),'FileNotFoundError') for item in failures)
                    assert o['runtime'].jobs.list_jobs()==[]
                    assert o['runtime'].events.list_events()==events_before
                    return
                initial=await catalogue()
                file_request=copy.deepcopy(o['request'])
                file_preview=await prepare(file_request,'add_project_file');file_proposal=await submit(file_preview)
                await land(file_preview,file_proposal)
                file_catalogue=await catalogue()
                seed={k:copy.deepcopy(v) for k,v in o['request'].items() if k not in ('schema','request_id','file')}
                seed.update(schema='mastermind.project_preference_set_request.v1',request_id='mmos-project-preference-set-'+'a'*40,
                    expected_preference_revision=None,value='Use brief replies. 中文\nKeep exact line breaks.',
                    source_commit=file_catalogue['source']['commit'],base_revision=file_catalogue['source']['workstream_sha256'])
                first_preview=await prepare(seed);first_status=await submit(first_preview);await land(first_preview,first_status)
                before=await catalogue();before_memory=await memory()
                assert before_memory['memory']['value']==seed['value']
                before_ref=before['project']['memory']
                source_before=await get('/workspace/project-source/current',work_ref='WS:ALPHA',source_ref=before_ref['source_ref'],expected_revision=before_ref['revision'])
                file_row=next(row for row in before['project']['files'] if row['display_name']==file_request['file']['display_name'])
                file_before=await get('/workspace/project-source/current',work_ref='WS:ALPHA',source_ref=file_row['source_ref'],expected_revision=file_row['revision'])
                request=copy.deepcopy(seed);request.update(request_id='mmos-project-preference-set-'+'b'*40,
                    source_commit=before['source']['commit'],base_revision=before['source']['workstream_sha256'],
                    expected_preference_revision=before_memory['source']['content_sha256'],value='Keep the answer short. 中文\nPreserve this exact second edit.')
                context=await get('/workspace/source-operation/context',action='set_project_communication_preference',work_ref='WS:ALPHA')
                file_context=await get('/workspace/source-operation/context',action='add_project_file',work_ref='WS:ALPHA')
                preview=await prepare(request);proposal=await submit(preview)
                pr_only=await catalogue();assert pr_only['source']['commit']==before['source']['commit']
                accepted=await land(preview,proposal);after=await catalogue();after_memory=await memory()
                assert after_memory['memory']['value']==request['value']
                assert after_memory['source']['revision']!=before_memory['source']['revision']
                assert after['code_context']==before['code_context']
                row=after['project']['memory'];source=await get('/workspace/project-source/current',work_ref='WS:ALPHA',source_ref=row['source_ref'],expected_revision=row['revision'])
                reopened=await memory();assert reopened['memory']==after_memory['memory']
                current_file_row=next(row for row in after['project']['files'] if row['display_name']==file_request['file']['display_name'])
                file_after=await get('/workspace/project-source/current',work_ref='WS:ALPHA',source_ref=current_file_row['source_ref'],expected_revision=current_file_row['revision'])
                assert file_after['document']['content_utf8']==file_request['file']['content_utf8']
                assert o['pr'].create_calls==3 and o['runtime'].jobs.list_jobs()==[]
                # References bind the canonical commit and blob. The old
                # reference is no longer a member; even the new reference must
                # refuse the old revision before opening a body.
                assert row['source_ref']!=before_ref['source_ref']
                old_ref=await client.get('/workspace/project-source/current',params={'work_ref':'WS:ALPHA',
                    'source_ref':before_ref['source_ref'],'expected_revision':before_ref['revision']})
                assert old_ref.status_code==503 and old_ref.json()['reason_codes']==['RECORD_NOT_FOUND'],old_ref.text
                stale=await client.get('/workspace/project-source/current',params={'work_ref':'WS:ALPHA',
                    'source_ref':row['source_ref'],'expected_revision':before_ref['revision']})
                assert stale.status_code==503 and stale.json()['reason_codes']==['SOURCE_CHANGED'],stale.text
                # Revocation denies before another isolated reader is invoked.
                before_denial=len(children);slot['enabled']=False
                denied=await client.get('/workspace/project-memory/current',params={'work_ref':'WS:ALPHA'})
                assert denied.status_code==403,denied.text
                assert len(children)==before_denial
                slot['enabled']=True
                assert {Path(argv[3]).name for argv in children}=={
                    'agentos_project_knowledge_entry.py','agentos_project_knowledge_recipe_entry.py'}
                output={'programs':programs,'context':context,'file_context':file_context,'before':before,'memory_before':before_memory,
                    'request':request,'preview':preview,'proposal_status':proposal,'pr_only_catalogue':pr_only,'accepted_status':accepted,
                    'after':after,'memory_after':after_memory,'source_after':source,'source_before':source_before,
                    'file_request':file_request,'file_before':file_before,'file_after':file_after,'source':canonical.provenance()}
                destination=os.environ.get('MMOS_MEMORY_APP_FIXTURE')
                if destination:Path(destination).write_text(json.dumps(output,ensure_ascii=False,sort_keys=True))
        finally:await host.close()
    asyncio.run(run())


@pytest.mark.parametrize('configured_present',[True,False])
def test_memory_source_selected_interpreter_failure_never_falls_back(tmp_path,monkeypatch,configured_present):
    import subprocess
    from ops.executive_os import capacity_source_contract
    from tests.test_project_discovery_installed_plan import _qualified_source_python
    failed=tmp_path/'selected-python'
    failed.write_text('#!/bin/sh\nexit 7\n');failed.chmod(0o700)
    monkeypatch.setattr(capacity_source_contract,'PYTHON_BINARY',failed if configured_present else tmp_path/'absent-cf1')
    if not configured_present:monkeypatch.setattr(sys,'executable',str(failed))
    with pytest.raises(subprocess.CalledProcessError) as error:_qualified_source_python()
    assert error.value.returncode==7 and error.value.cmd[0]==str(failed)
