"""Real issued collector/isolated child → existing private/Event/Git owner.

Only the credential qualifier and PR API use explicit local inert test owners.
No installed grant, company Git write, source selection or Job is activated.
"""
import copy
import time
from pathlib import Path

import pytest
from control_plane.installed_project_knowledge_compiler import InstalledProjectKnowledgeCompiler
from integrations.executive_mcp.installed import InstalledBootPacketCollector
from integrations.mastermind_workspace_app.knowledge_recipe_adapter import ProjectKnowledgeRecipeAdapter
from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService
from integrations.mastermind_workspace_app.source_operation_http import _preview
from integrations.mastermind_workspace_app.contract import principal_frame
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope
from ops.executive_os.capacity_source_contract import PYTHON_BINARY
from common.workspace_source_operation_wire import FRAME_SCHEMA
from tests.test_knowledge_source_service import owner, env, isolated_git_env, inspection, selection
from tests.test_workspace_project_git_publisher import git, rev_parse

_REAL_READ = InstalledProjectKnowledgeCompiler._read
ROOT = Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(not Path(PYTHON_BINARY).is_file(),reason='native CF1 qualification runtime unavailable')


def install_actual_compiler(o, tmp_path, monkeypatch):
    # Undo only the upstream adapter fixture's explicit facade seam. The
    # nominal installed issuer below and its physical child remain unmocked.
    monkeypatch.setattr(InstalledProjectKnowledgeCompiler, '_read', _REAL_READ)
    source = tmp_path / 'sealed-mastermind-source'
    source.mkdir(); (source / 'README.md').write_text('Synthetic installation source identity\n')
    git(source, 'init', '-q'); git(source, 'add', '.'); git(source, 'commit', '-m', 'Source identity')
    collector = InstalledBootPacketCollector(source_root=source, macro_root=o['env'].clone,
        code_root=ROOT, python_executable=Path(PYTHON_BINARY), expected_source_sha=rev_parse(source, 'HEAD'))
    compiler = collector.project_knowledge_recipe_reader(macro_root=o['env'].clone)
    o['service']._adapter = ProjectKnowledgeRecipeAdapter(compiler)
    return collector, compiler


@pytest.mark.parametrize('preference', [False, True])
def test_actual_issued_child_private_dispatcher_and_original_status(owner, tmp_path, monkeypatch, preference):
    o = owner
    collector, compiler = install_actual_compiler(o, tmp_path, monkeypatch)
    request = copy.deepcopy(o['request'])
    if preference:
        request = {key: value for key, value in request.items() if key not in {'schema','request_id','file'}} | {
            'schema': 'mastermind.project_preference_set_request.v1',
            'request_id': 'mmos-project-preference-set-' + 'b' * 40,
            'expected_preference_revision': None, 'value': 'Keep replies concise. 保留原文。'}
    action = 'set_project_communication_preference' if preference else 'add_project_file'
    dispatcher = WorkspaceSourceOperationService(knowledge_owner=o['service'])
    frame = {'schema': 'mastermind.workspace_source_operation.v1', 'operation': 'prepare',
        'principal': principal_frame(o['who']), 'verified_expires_at': int(time.time()) + 300,
        'request': {'action': action, 'request': request}}
    # Use the fixed frame schema constant, never a guessed transport variant.
    from common.workspace_source_operation_wire import FRAME_SCHEMA
    frame['schema'] = FRAME_SCHEMA
    preview = dispatcher.handle(frame, peer_guard=lambda: True)
    assert _preview(preview, frame['request'], source_principal_scope(o['who'])) == preview
    assert preview['preview']['state'] == 'DRAFT_ONLY'
    assert o['events'].original(selection(preview), source_principal_scope(o['who']), guard=lambda: True)
    assert o['runtime'].jobs.list_jobs() == []
    submit = frame | {'operation': 'submit', 'request': {**preview['selection'], 'preview_witness': preview['preview_witness']}}
    status = dispatcher.handle(submit, peer_guard=lambda: True)
    assert status['disposition'] == 'unknown' and status['receipt']['kind'] == 'PROPOSAL_OBSERVED'
    assert o['pr'].create_calls == 1
    # Original observation survives compiler-source withdrawal and never
    # recaptures user content or publishes a second PR.
    monkeypatch.setattr(compiler, '_read', lambda **kw: pytest.fail('status attempted compiler capture'))
    read = frame | {'operation': 'read', 'request': inspection(preview)}
    assert dispatcher.handle(read, peer_guard=lambda: True)['receipt'] == status['receipt']
    with pytest.raises((PermissionError, ValueError)):
        dispatcher.handle(read, peer_guard=lambda: False)
    assert o['pr'].create_calls == 1

from tests.test_workspace_read_app import rsa_key
from tests.test_executive_workspace_mount import settings


@pytest.mark.parametrize('case', ['file', 'preference', 'grant_withdrawn', 'maximum_file'])
def test_signed_outer_http_socket_issued_knowledge_owner(owner, tmp_path, monkeypatch, rsa_key, short_socket_root, settings, case):
    import asyncio
    import json
    import os
    import httpx
    from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
    from integrations.mastermind_workspace_app.contract import workspace_authorizers
    from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
    from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
    from integrations.mastermind_workspace_app.knowledge_publisher_events import KnowledgePublisherEvents
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
    from tests.test_executive_ceo_ingress import _FakeGrounding, _config
    from tests.test_workspace_read_app import _authenticator, _workspace_token, NOW
    from tests.test_workspace_project_authoring_grant import project_bindings
    from integrations.executive_mcp import server
    from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
    from tests.test_executive_mcp_app_composition import Sink
    o = owner
    collector, compiler = install_actual_compiler(o, tmp_path, monkeypatch)
    async def run():
        auth, token = _authenticator(rsa_key), _workspace_token(rsa_key)
        who = await auth.verify_authorization_header('Bearer ' + token, now=NOW)
        _, document = project_bindings(selected=None)
        for slot in document['profiles'].values():
            slot['enabled'], slot['binding'] = False, None
        slot = document['profiles'][document['primary_profile']]
        slot['enabled'] = True
        slot['binding'] = dict(principal_frame(who), permission_digest='a' * 64)
        slot['project_file_add'] = {'work_ref':'WS:ALPHA', 'permission_digest':'3'*64}
        slot['project_preference_set'] = {'work_ref':'WS:ALPHA', 'permission_digest':'4'*64}
        o['bindings'].clear(); o['bindings'].update(document)
        permissions = WorkspaceSourceOperationContextFactory(policy=auth.policy,
            load_bindings=lambda: o['bindings'], now=lambda: NOW)
        o['service']._permissions = permissions
        o['service']._publisher_events = KnowledgePublisherEvents(events=o['events'], contexts=permissions)
        dispatcher = WorkspaceSourceOperationService(knowledge_owner=o['service'])
        host = ExecutiveControlService(_config(o['env'].tmp_path/'knowledge-http-host', socket_root=short_socket_root,
            runtime_root=o['runtime'].store.root), runtime_factory=lambda _: o['runtime'],
            supervisor_factory=lambda _: o['private'].supervisor, ceo_ingress_socket_path=short_socket_root/'knowledge.sock',
            ceo_ingress_peer_uid=os.geteuid()+1000, ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False,
                grounding_provider=_FakeGrounding(), source_operation_provider_factory=lambda rt,su: dispatcher.installed_binding()))
        await host.start()
        try:
            gate,_ = workspace_authorizers(policy=auth.policy, load_bindings=lambda: legacy_workspace_document(o['bindings'],auth.policy))
            app = create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda: NOW,authorize_principal=gate,
                client=CeoIngressWorkspaceClient(host.ceo_ingress_socket_path),source_operation_context=permissions))
            sink = Sink()
            verifier = MastermindTokenVerifier(authenticator=auth,policy=auth.policy,now=lambda: NOW,audit_sink=sink)
            app = server.build_executive_mcp_app(settings,audit_sink=sink,workspace_app=server.AuditedWorkspaceApp(app,verifier))
            headers={'Authorization':'Bearer '+token}
            request=copy.deepcopy(o['request'])
            action='add_project_file'
            if case=='maximum_file':
                request['file']['content_utf8']='"\t\\\r\n'*6553+'abc'
                request['file']['display_name']='"'*125+'.md'
                assert len(request['file']['content_utf8'].encode('utf-8'))==32768
                encoded=json.dumps({'action':action,'request':request},ensure_ascii=False).encode('utf-8')
                assert 32768<len(encoded)<98304
            if case=='preference':
                request={k:v for k,v in request.items() if k not in {'schema','request_id','file'}} | {
                    'schema':'mastermind.project_preference_set_request.v1','request_id':'mmos-project-preference-set-'+'b'*40,
                    'expected_preference_revision':None,'value':'Keep literal 中文 preference.'}
                action='set_project_communication_preference'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com') as client:
                response=await client.post('/workspace/source-operation/prepare',headers=headers,json={'action':action,'request':request})
                assert response.status_code==200,response.text
                preview=response.json()
                if case=='grant_withdrawn':slot['project_file_add']=None
                submitted=await client.post('/workspace/source-operation/submit',headers=headers,
                    json=preview['selection']|{'preview_witness':preview['preview_witness']})
                if case=='grant_withdrawn':
                    assert submitted.status_code==403 and o['pr'].create_calls==0
                    assert [e.payload['kind'] for e in o['runtime'].store.list_events()]==['INTENT']
                    return
                assert submitted.status_code==200,submitted.text
                assert submitted.json()['receipt']['kind']=='PROPOSAL_OBSERVED' and o['pr'].create_calls==1
                params={k:('null' if v is None else v) for k,v in inspection(preview).items()}
                before=len(o['runtime'].store.list_events())
                observed=await client.get('/workspace/source-operation/operation',headers=headers,params=params)
                assert observed.status_code==200 and observed.json()==submitted.json(),observed.text
                assert observed.headers['cache-control']=='no-store' and len(o['runtime'].store.list_events())==before
                bad=await client.get('/workspace/source-operation/operation',headers=headers,params=params|{'request_sha256':'0'*64})
                assert bad.status_code in {400,503} and o['pr'].create_calls==1
                assert o['runtime'].jobs.list_jobs()==[]
        finally:
            await host.close()
    asyncio.run(run())


def test_safe_http_preview_refuses_foreign_source_path_digest_or_change(owner):
    o=owner
    preview=o['service'].prepare(o['request'],o['who'])
    wire={'action':'add_project_file','request':o['request']}
    scope=source_principal_scope(o['who'])
    assert _preview(preview,wire,scope)==preview
    for mutation in ('scope','source','path','hash','change','duplicate','extra','selection'):
        body=copy.deepcopy(preview)
        if mutation=='scope':body['owner_context']['principal_scope']='0'*64
        elif mutation=='source':body['preview']['source_commit']='0'*40
        elif mutation=='path':body['preview']['postimages'][0]['path']='agentos/workstreams/WS-FOREIGN.md'
        elif mutation=='hash':
            image=next(i for i in body['preview']['postimages'] if i['path'].startswith('agentos/project-files/'))
            image['content_sha256']='0'*64
        elif mutation=='change':body['preview']['change']['size_bytes']+=1
        elif mutation=='duplicate':body['preview']['postimages'][1]=body['preview']['postimages'][0]
        elif mutation=='extra':body['preview']['private_input']='forbidden'
        else:body['selection']['work_ref']='WS:FOREIGN'
        with pytest.raises(ValueError):_preview(body,wire,scope)


def test_source_socket_buffer_does_not_widen_legacy_or_release_protocol(owner,short_socket_root):
    import asyncio
    import json
    import os
    from control_plane.executive_service import ExecutiveControlService,CeoIngressAppBinding
    from control_plane.executive_release_ingress import MAX_FRAME_BYTES,FRAME_SCHEMA as RELEASE_SCHEMA
    from tests.test_executive_ceo_ingress import _FakeGrounding,_config
    o=owner
    dispatcher=WorkspaceSourceOperationService(knowledge_owner=o['service'])
    async def run():
        host=ExecutiveControlService(_config(o['env'].tmp_path/'source-cap-host',socket_root=short_socket_root,
            runtime_root=o['runtime'].store.root),runtime_factory=lambda _:o['runtime'],
            supervisor_factory=lambda _:o['private'].supervisor,ceo_ingress_socket_path=short_socket_root/'source-cap.sock',
            ceo_ingress_peer_uid=os.geteuid()+1000,ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=False,
                grounding_provider=_FakeGrounding(),source_operation_provider_factory=lambda r,s:dispatcher.installed_binding()))
        await host.start()
        try:
            assert host._ceo_ingress_stream_ceiling()==98304
            for schema,size in [('unselected-legacy',9000),(RELEASE_SCHEMA,MAX_FRAME_BYTES+1),
                                (FRAME_SCHEMA,98305)]:
                reader,writer=await asyncio.open_unix_connection(str(host.ceo_ingress_socket_path))
                raw=json.dumps({'schema':schema}).encode()
                writer.write(raw+b' '*(size-len(raw))+b'\n');await writer.drain()
                answer=json.loads(await asyncio.wait_for(reader.readline(),5))
                assert answer['error']['code']=='request_too_large',answer
                writer.close();await writer.wait_closed()
            assert o['runtime'].store.list_events()==[] and o['pr'].create_calls==0
        finally:await host.close()
    asyncio.run(run())
