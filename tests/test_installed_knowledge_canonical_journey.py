"""Signed App/socket → installed owners → private Events/Git → same READ.

Only root-owned credential/config sealing and the remote PR API are explicit
local fixtures. Canonical landing is a separate temporary upstream actor. No
installed grant, real credential, company publication, Job or provider runs.
"""
import asyncio
import copy
import hashlib
import json
import os

import httpx
import pytest

from tests.test_installed_source_git_identity import identity
from tests.test_knowledge_installed_source_join import owner, env, isolated_git_env, install_actual_compiler, rsa_key, settings
from tests.test_workspace_read_socket import short_socket_root
from tests.test_workspace_project_git_publisher import git, rev_parse
from control_plane.workspace_project_git_publisher import PublisherBinding
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_read_app import _authenticator, _workspace_token, NOW
from tests.test_workspace_project_authoring_grant import project_bindings
from integrations.mastermind_workspace_app.contract import principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document, SCHEMA_V5
from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData
from control_plane.workspace_source_operations import SourceOperationEvents
from control_plane.workspace_read_service import WorkspaceReadService
from pathlib import Path
from ops.executive_os.capacity_source_contract import PYTHON_BINARY

pytestmark=pytest.mark.skipif(not Path(PYTHON_BINARY).is_file(),reason='native CF1 qualification runtime unavailable')


def configured(o, identity, tmp_path, monkeypatch, *, python_executable=None):
    # Separate immutable CODE clone from the configured service publisher.
    code = tmp_path/'configured-code'
    git(tmp_path, 'clone', str(o['env'].origin), str(code))
    o['env'].clone, writer = code, o['env'].clone
    collector, _ = install_actual_compiler(o, tmp_path, monkeypatch,
        python_executable=python_executable)
    o['env'].clone = writer
    git_owner = identity[0]
    git_owner.binding = PublisherBinding(worktree=str(writer), expected_origin=str(o['env'].origin),
        default_branch='main', publisher_identity='synthetic-fixed-service-identity')
    monkeypatch.setattr(git_owner, 'qualify', lambda binding: binding == git_owner.binding)
    monkeypatch.setattr(git_owner, 'find', o['pr'].find)
    monkeypatch.setattr(git_owner, 'create', o['pr'].create)
    return collector, git_owner


@pytest.mark.parametrize('mode', ['full', 'first_unrelated', 'first_unqualified_data', 'read_only', 'write_only', 'v4_write', 'late_revoke', 'revoke_during_write'])
def test_signed_installed_publication_same_reader_and_second_edit(owner, identity, tmp_path,
        monkeypatch, rsa_key, short_socket_root, settings, mode):
    from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
    from tests.test_executive_ceo_ingress import _FakeGrounding, _config
    from integrations.executive_mcp import server
    from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
    from tests.test_executive_mcp_app_composition import Sink
    o=owner
    collector, git_owner = configured(o,identity,tmp_path,monkeypatch)
    if os.environ.get('MM_KNOWLEDGE_FIRST_USE_TRACE'):
        import time,traceback
        from control_plane import project_canonical_data as traced
        from control_plane.workspace_project_git_publisher import FixedProjectGitPublisher
        counters={'publisher_git':[0,0.0],'collector_git':[0,0.0],'collector_child':[0,0.0]}
        actual_git=FixedProjectGitPublisher._git
        def trace_git(self,*args,**kwargs):
            start=time.monotonic()
            try:return actual_git(self,*args,**kwargs)
            finally:
                counters['publisher_git'][0]+=1;counters['publisher_git'][1]+=time.monotonic()-start
        monkeypatch.setattr(FixedProjectGitPublisher,'_git',trace_git)
        actual_runner=collector._runner
        def trace_runner(argv,**kwargs):
            start=time.monotonic();kind='collector_git' if str(argv[0])=='git' else 'collector_child'
            try:return actual_runner(argv,**kwargs)
            finally:
                counters[kind][0]+=1;counters[kind][1]+=time.monotonic()-start
        monkeypatch.setattr(collector,'_runner',trace_runner)
        fail=traced._fail
        def trace_fail():
            traceback.print_stack(limit=12)
            return fail()
        monkeypatch.setattr(traced,'_fail',trace_fail)
        actual_read=InstalledCanonicalProjectData.read_knowledge
        def trace_read(self,*args,**kwargs):
            start=time.monotonic()
            baseline={k:list(v) for k,v in counters.items()}
            try:
                result=actual_read(self,*args,**kwargs)
                print('ACTUAL_DATA_READ',kwargs.get('operation'),time.monotonic()-start,
                    None if result is None else result[0].get('availability'),flush=True)
                return result
            except Exception:
                print('ACTUAL_DATA_READ_FAILED',kwargs.get('operation'),time.monotonic()-start,flush=True)
                traceback.print_exc();raise
            finally:
                print('ACTUAL_DATA_COMPONENTS',kwargs.get('operation'),
                    {k:[v[0]-baseline[k][0],round(v[1]-baseline[k][1],4)] for k,v in counters.items()},flush=True)
        monkeypatch.setattr(InstalledCanonicalProjectData,'read_knowledge',trace_read)
    async def run():
        auth, token = _authenticator(rsa_key), _workspace_token(rsa_key)
        who=await auth.verify_authorization_header('Bearer '+token,now=NOW)
        _, document=project_bindings(selected=None)
        document['schema']=SCHEMA_V5
        for slot in document['profiles'].values():
            slot['enabled'],slot['binding']=False,None
            slot['project_plan_proposal_publish']=None
            slot['project_canonical_data_read']=None
        slot=document['profiles'][document['primary_profile']]
        slot['enabled']=True
        slot['binding']=dict(principal_frame(who),permission_digest='a'*64)
        slot['project_file_add']={'work_ref':'WS:ALPHA','permission_digest':'3'*64}
        slot['project_preference_set']={'work_ref':'WS:ALPHA','permission_digest':'4'*64}
        slot['project_canonical_data_read']='5'*64
        o['bindings'].clear();o['bindings'].update(document)
        loader=lambda:o['bindings']
        read_verified,read_frame=workspace_authorizers(policy=auth.policy,
            load_bindings=lambda:legacy_workspace_document(loader(),auth.policy))
        factory=InstalledWorkspaceSourceOperations(collector=collector,policy=auth.policy,
            load_bindings=loader,git_identity=git_owner,runtime_guard=lambda rt:rt is o['runtime'])
        factory._permissions._now=lambda:NOW
        data=InstalledCanonicalProjectData(collector=collector,policy=auth.policy,load_bindings=loader,
            git_identity=git_owner,events=SourceOperationEvents(o['runtime'].store),runtime_guard=lambda:True)
        owners,clock,cache=cache_fixture(tmp_path/'cache')
        doc=json.loads(json.dumps(owners[0].state_cache['doc']).replace('WS:ONE','WS:ALPHA'))
        doc['sources']={'macro_sha':o['request']['source_commit']}
        owners[0].state_cache['doc']=doc
        from scripts import chairman_control_room as ccr
        with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
        readers=dict(project_knowledge_catalogue_reader=collector.project_knowledge_catalogue_reader(macro_root=collector._macro_root),
            project_knowledge_source_reader=collector.project_knowledge_source_reader(macro_root=collector._macro_root),
            project_knowledge_memory_reader=collector.project_knowledge_memory_reader(macro_root=collector._macro_root))
        provider=lambda rt:WorkspaceReadService(cache=cache,runtime=rt,authorize=read_frame,
            armed={},runtime_identity={},canonical_project_data=data.installed_binding(),**readers)
        host=ExecutiveControlService(_config(o['env'].tmp_path/'canonical-host',socket_root=short_socket_root,
            runtime_root=o['runtime'].store.root),runtime_factory=lambda _:o['runtime'],
            supervisor_factory=lambda _:o['private'].supervisor,ceo_ingress_socket_path=short_socket_root/'canonical.sock',
            ceo_ingress_peer_uid=os.geteuid()+1000,ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=False,
                grounding_provider=_FakeGrounding(),workspace_read_provider_factory=provider,
                source_operation_provider_factory=factory))
        await host.start()
        try:
            app=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:NOW,
                authorize_principal=read_verified,client=CeoIngressWorkspaceClient(host.ceo_ingress_socket_path),
                source_operation_context=factory._permissions))
            sink=Sink();verifier=MastermindTokenVerifier(authenticator=auth,policy=auth.policy,now=lambda:NOW,audit_sink=sink)
            app=server.build_executive_mcp_app(settings,audit_sink=sink,workspace_app=server.AuditedWorkspaceApp(app,verifier))
            headers={'Authorization':'Bearer '+token}
            settlements=[]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com',headers=headers) as client:
                async def catalogue(*,allow_unavailable=False):
                    response=await client.get('/workspace/project-knowledge/current',params={'work_ref':'WS:ALPHA'})
                    assert response.status_code==200 or allow_unavailable and response.status_code==503,response.text
                    return response.json()
                async def prepare(request,action='add_project_file'):
                    return await client.post('/workspace/source-operation/prepare',json={'action':action,'request':request})
                async def submit(preview):
                    response=await client.post('/workspace/source-operation/submit',json=preview['selection']|{'preview_witness':preview['preview_witness']})
                    assert response.status_code==200,response.text
                    assert response.json()['receipt']['kind']=='PROPOSAL_OBSERVED',response.text
                    return response.json()
                async def land(preview,status):
                    root=tmp_path/('integrator-'+str(o['pr'].create_calls))
                    git(tmp_path,'clone',str(o['env'].origin),str(root))
                    git(root,'fetch','origin',status['receipt']['proposal']['head_branch'])
                    git(root,'merge','--no-ff','--no-edit','FETCH_HEAD');git(root,'push','origin','main')
                    from tests.test_knowledge_source_service import inspection
                    result=await client.post('/workspace/source-operation/reconcile',json=inspection(preview))
                    assert result.status_code==200,result.text
                    assert result.json()['disposition']=='accepted',result.text
                    settlements.append(result.json())
                    return rev_parse(root,'HEAD')
                initial=await catalogue()
                first_request=copy.deepcopy(o['request'])
                unrelated_commit=None
                if mode in {'first_unrelated','first_unqualified_data'}:
                    root=tmp_path/'unrelated-integrator'
                    git(tmp_path,'clone',str(o['env'].origin),str(root))
                    path=root/'docs'/'unrelated-first-use.md'
                    if mode=='first_unqualified_data':
                        path=root/'agentos'/'workstreams'/'WS-ALPHA.md'
                        path.write_text(path.read_text()+'\nUnproved selected project change.\n')
                    else:
                        path.parent.mkdir(parents=True,exist_ok=True)
                        path.write_text('Unrelated canonical documentation before first Knowledge publication.\n')
                    git(root,'add',str(path.relative_to(root)))
                    git(root,'commit','-m','Canonical movement before first project publication')
                    git(root,'push','origin','main')
                    unrelated_commit=rev_parse(root,'HEAD')
                    assert all(event.payload.get('kind')!='SOURCE_OBSERVED' for event in o['runtime'].store.list_events())
                    first_request['source_commit']=unrelated_commit
                before=await catalogue(allow_unavailable=mode=='first_unqualified_data') if unrelated_commit else initial
                if mode=='first_unqualified_data':
                    assert before.get('availability')=='UNAVAILABLE',before
                    refused=await prepare(first_request)
                    assert refused.status_code!=200 or refused.json().get('preview',{}).get('state')!='DRAFT_ONLY',refused.text
                    assert o['pr'].create_calls==0 and o['runtime'].jobs.list_jobs()==[]
                    return
                assert before['code_context']['executable_macro_commit']==o['request']['source_commit']
                before_memory=None;before_source=None
                if mode=='first_unrelated':
                    assert before['availability']=='AVAILABLE' and before['source']['commit']==unrelated_commit,before
                    observation=before['data_observation']
                    assert observation['canonical_data_commit']==unrelated_commit
                    assert observation['source_operation'] is None and observation['publication_recorded_at_ms'] is None
                    assert observation['publication_time'] is None and initial['source']['commit']!=unrelated_commit
                    memory_response=await client.get('/workspace/project-memory/current',params={'work_ref':'WS:ALPHA'})
                    assert memory_response.status_code==200,memory_response.text
                    before_memory=memory_response.json()
                    selected=next(row for row in before['project']['records'] if row['kind']=='WORKSTREAM')
                    source_response=await client.get('/workspace/project-source/current',params={'work_ref':'WS:ALPHA',
                        'source_ref':selected['source_ref'],'expected_revision':selected['revision']})
                    assert source_response.status_code==200,source_response.text
                    before_source=source_response.json()
                    assert before_source['source']['commit']==unrelated_commit
                context=await client.get('/workspace/source-operation/context',params={'action':'add_project_file','work_ref':'WS:ALPHA'})
                assert context.status_code==200,context.text
                context=context.json()
                assert context['can_inspect'] is True and context['selection']=={'action':'add_project_file','work_ref':'WS:ALPHA'}
                prepared=await prepare(first_request);assert prepared.status_code==200,prepared.text
                preview=prepared.json()
                assert preview['preview']['source_commit']==first_request['source_commit']
                if mode=='revoke_during_write':
                    original_create=git_owner.create
                    def revoke_after_pr(*args,**kwargs):
                        result=original_create(*args,**kwargs)
                        slot['project_canonical_data_read']=None
                        return result
                    monkeypatch.setattr(git_owner,'create',revoke_after_pr)
                    attempted=await client.post('/workspace/source-operation/submit',json=preview['selection']|{'preview_witness':preview['preview_witness']})
                    assert attempted.status_code==403,attempted.text
                    from tests.test_knowledge_source_service import inspection
                    params={key:'null' if value is None else value for key,value in inspection(preview).items()}
                    observed=await client.get('/workspace/source-operation/operation',params=params)
                    assert observed.status_code==200,observed.text
                    assert observed.json()['disposition']=='unknown' and observed.json()['receipt']['kind']=='PHASE_ATTEMPTED',observed.text
                    assert o['pr'].create_calls==1 and o['runtime'].jobs.list_jobs()==[]
                    return
                status=await submit(preview)
                pending=await catalogue()
                assert pending['source']['commit']==before['source']['commit']
                first=await land(preview,status)
                if mode=='v4_write':
                    o['bindings']['schema']='mastermind.workspace_acquisition_bindings.v4'
                    for value in o['bindings']['profiles'].values():
                        value.pop('project_plan_proposal_publish');value.pop('project_canonical_data_read')
                elif mode=='write_only':slot['project_canonical_data_read']=None
                if mode in {'v4_write','write_only'}:
                    fixed=await catalogue();assert fixed['source']['commit']==before['source']['commit']
                    request=copy.deepcopy(o['request']);request['request_id']='mmos-project-file-add-'+'b'*40
                    request['source_commit']=first
                    response=await prepare(request)
                    assert response.status_code!=200 or response.json().get('preview',{}).get('state')!='DRAFT_ONLY',response.text
                    assert o['pr'].create_calls==1
                    return
                after=await catalogue()
                assert after['source']['commit']==first and after['code_context']==before['code_context']
                assert after['data_observation']['canonical_data_commit']==first
                if mode=='first_unrelated':
                    assert after['data_observation']['source_operation']['selection']['request_id']==first_request['request_id']
                    assert after['data_observation']['publication_recorded_at_ms']==settlements[0]['receipt']['recorded_at_ms']
                row=next(r for r in after['project']['files'] if r['display_name']=='Notes.md')
                opened=await client.get('/workspace/project-source/current',params={'work_ref':'WS:ALPHA',
                    'source_ref':row['source_ref'],'expected_revision':row['revision']})
                assert opened.status_code==200,opened.text
                assert opened.json()['document']['content_utf8']==o['request']['file']['content_utf8']
                assert (await catalogue())['source']['commit']==first
                request=copy.deepcopy(o['request']);request['request_id']='mmos-project-file-add-'+'b'*40
                request['source_commit']=first;request['base_revision']=after['source']['workstream_sha256']
                request['file']['display_name']='Second.md';request['file']['content_utf8']='Second genuine edit from DATA N. 中文'
                if mode=='read_only':
                    slot['project_file_add']=None
                    response=await prepare(request);assert response.status_code==403,response.text
                    assert o['pr'].create_calls==1
                    return
                if mode=='late_revoke':
                    original=collector._runner
                    def revoked(argv,**kwargs):
                        result=original(argv,**kwargs)
                        if str(argv[0])!='git' and 'agentos_project_knowledge_entry.py' in str(argv[3]):
                            slot['project_canonical_data_read']=None
                        return result
                    monkeypatch.setattr(collector,'_runner',revoked)
                    response=await client.get('/workspace/project-knowledge/current',params={'work_ref':'WS:ALPHA'})
                    assert response.status_code==403 or response.json().get('availability')=='UNAVAILABLE',response.text
                    return
                second_preview=await prepare(request);assert second_preview.status_code==200,second_preview.text
                second_preview=second_preview.json();second_status=await submit(second_preview)
                second=await land(second_preview,second_status)
                reopened=await catalogue()
                assert reopened['source']['commit']==second and reopened['code_context']==before['code_context']
                assert {'Notes.md','Second.md'} <= {r['display_name'] for r in reopened['project']['files']}
                second_row=next(row for row in reopened['project']['files'] if row['display_name']=='Second.md')
                second_source=await client.get('/workspace/project-source/current',params={'work_ref':'WS:ALPHA',
                    'source_ref':second_row['source_ref'],'expected_revision':second_row['revision']})
                assert second_source.status_code==200,second_source.text
                assert second_source.json()['document']['content_utf8']==request['file']['content_utf8']
                stale=copy.deepcopy(request);stale['request_id']='mmos-project-file-add-'+'c'*40
                stale_response=await prepare(stale)
                assert stale_response.status_code!=200,stale_response.text
                assert o['pr'].create_calls==2 and o['runtime'].jobs.list_jobs()==[]
                assert rev_parse(collector._macro_root,'HEAD')==o['request']['source_commit']
                output=os.environ.get('MM_KNOWLEDGE_SIGNED_JOURNEY_OUTPUT')
                if output:
                    from pathlib import Path
                    Path(output).write_text(json.dumps({'schema':'mastermind.knowledge_signed_journey_fixture.v1',
                        'scope':'DISPOSABLE_SOURCE_ONLY_CREDENTIAL_CONFIG_SEAL_AND_PR_SEAMS_INERT',
                        'context':context,'request':first_request,'initial':initial,'unrelated_commit':unrelated_commit,
                        'before':before,'before_memory':before_memory,'before_source':before_source,'preview':preview,'proposal_status':status,
                        'pr_only_catalogue':pending,'accepted_status':settlements[0],
                        'after':after,'source':opened.json(),'second_request':request,
                        'second_preview':second_preview,'second_proposal_status':second_status,
                        'second_accepted_status':settlements[1],'reopened':reopened,'second_source':second_source.json(),
                        'stale_status':stale_response.status_code},ensure_ascii=False,indent=2)+'\n')
        finally:await host.close()
    asyncio.run(run())
