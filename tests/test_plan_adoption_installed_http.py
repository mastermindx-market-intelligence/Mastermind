"""Signed Workspace HTTP -> real AF_UNIX peer -> installed ADOPT owner.

Disposable Git/Runtime/private owners only. The existing fixture explicitly
supplies an inert root seal, credential qualification and PR API. No CREATE,
provider call, installed service or company publication is exercised here.
"""
import asyncio
import copy
import json
import os
from pathlib import Path

import httpx

from tests.test_project_source_installed_registry import actual_adoption_installed
from tests.test_workspace_plan_adoption_git_publisher import isolated_git_env
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW
from tests.test_executive_workspace_mount import settings
from tests.test_executive_ceo_ingress import _FakeGrounding, _config
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_project_authoring_grant import project_bindings
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import SCHEMA_V5, legacy_workspace_document
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp import server
from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
from control_plane.workspace_source_operations import SourceOperationEvents
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_executive_mcp_app_composition import Sink
from tests.test_project_discovery_installed_plan import actual_child


def test_signed_installed_adoption_two_phases_and_current_compare(
        actual_adoption_installed, tmp_path, monkeypatch, rsa_key, short_socket_root, settings):
    j = actual_adoption_installed
    f = j.f
    # actual_child qualifies the selected interpreter under real -I before use.
    # Reuse the supplier's declared synthetic Mastermind-seal fixture
    # normalization. It preserves REAL Macro generation and the literal
    # installed materialization/isolated Plan child, never a reader override.
    _, children = actual_child({'collector': j.collector}, monkeypatch)

    async def run():
        auth, token = _authenticator(rsa_key), _workspace_token(rsa_key)
        who = await auth.verify_authorization_header('Bearer ' + token, now=NOW)
        _, document = project_bindings(selected=None)
        document['schema'] = SCHEMA_V5
        for slot in document['profiles'].values():
            slot['enabled'], slot['binding'] = False, None
            slot['project_plan_proposal_publish'] = None
            slot['project_canonical_data_read'] = None
            slot['plan_adoption'] = None
        slot = document['profiles'][document['primary_profile']]
        slot['enabled'] = True
        slot['binding'] = dict(principal_frame(who), permission_digest='a' * 64)
        slot['plan_adoption'] = dict(work_ref=f.work, permission_digest='8' * 64)
        slot['project_canonical_data_read'] = '6' * 64
        f.bindings.clear(); f.bindings.update(document)
        loader = lambda: f.bindings
        verified, frame_gate = workspace_authorizers(policy=auth.policy,
            load_bindings=lambda: legacy_workspace_document(loader(), auth.policy))
        factory = InstalledWorkspaceSourceOperations(collector=j.collector, policy=auth.policy,
            load_bindings=loader, git_identity=j.identity, runtime_guard=lambda rt: rt is f.runtime)
        factory._permissions._now = lambda: NOW
        data = InstalledCanonicalProjectData(collector=j.collector, policy=auth.policy,
            load_bindings=loader, git_identity=j.identity, events=SourceOperationEvents(f.runtime.store),
            runtime_guard=lambda: True)
        owners, clock, cache = cache_fixture(tmp_path / 'http-cache')
        doc = json.loads(json.dumps(owners[0].state_cache['doc']).replace('WS:ONE', f.work))
        doc['sources'] = {'macro_sha': j.code}
        owners[0].state_cache['doc'] = doc
        from scripts import chairman_control_room as ccr
        with owners[0].state_lock:
            ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
        read_provider = lambda rt: WorkspaceReadService(cache=cache, runtime=rt,
            authorize=frame_gate, armed={}, runtime_identity={},
            canonical_project_data=data.installed_binding(),
            project_plan_reader=j.collector.project_plan_reader(macro_root=j.collector._macro_root))
        host = ExecutiveControlService(_config(tmp_path / 'http-host', socket_root=short_socket_root,
            runtime_root=f.runtime.store.root), runtime_factory=lambda _: f.runtime,
            supervisor_factory=lambda _: f.private.supervisor,
            ceo_ingress_socket_path=short_socket_root / 'adopt.sock',
            ceo_ingress_peer_uid=os.geteuid() + 1000, ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False,
                grounding_provider=_FakeGrounding(), workspace_read_provider_factory=read_provider,
                source_operation_provider_factory=factory))
        await host.start()
        try:
            app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: NOW,
                authorize_principal=verified, client=CeoIngressWorkspaceClient(host.ceo_ingress_socket_path),
                source_operation_context=factory._permissions))
            sink = Sink()
            verifier = MastermindTokenVerifier(authenticator=auth, policy=auth.policy,
                now=lambda: NOW, audit_sink=sink)
            app = server.build_executive_mcp_app(settings, audit_sink=sink,
                workspace_app=server.AuditedWorkspaceApp(app, verifier))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                    base_url='https://mcp.mastermind-x.com', headers={'Authorization': 'Bearer ' + token}) as client:
                async def post(operation, body):
                    response = await client.post('/workspace/source-operation/' + operation, json=body)
                    assert response.status_code == 200, (operation, response.text)
                    return response.json()
                lookup = copy.deepcopy(f.lookup)
                params = {k: v for k, v in lookup.items() if k != 'schema'}
                before = len(f.runtime.store.list_events())
                foreign = await client.get('/workspace/source-operation/operation',
                    params=params | {'work_ref': 'WS:FOREIGN'})
                assert foreign.status_code == 403
                assert len(f.runtime.store.list_events()) == before
                context = await client.get('/workspace/source-operation/context',
                    params={'action': 'ADOPT_PLAN', 'work_ref': f.work})
                assert context.status_code == 200, context.text
                initial = await client.get('/workspace/project-plan/current', params={'work_ref': f.work})
                assert initial.status_code == 200, initial.text
                assert initial.json()['continuity']['adoption']['decision_ref'] == 'DEC:PLAN-FIRST'
                preview = await post('prepare', dict(action='ADOPT_PLAN', request=j.request))
                assert preview['preview']['record_body_changed'] is False
                pending = await post('submit', preview['selection'] | {'preview_witness': preview['preview_witness']})
                assert pending['receipt']['kind'] == 'PROPOSAL_OBSERVED'
                before = len(f.runtime.store.list_events())
                observed = await client.get('/workspace/source-operation/operation', params=params)
                assert observed.status_code == 200 and observed.json() == pending, observed.text
                assert len(f.runtime.store.list_events()) == before
                f.merge(pending)
                ready = await post('reconcile', lookup)
                assert ready['reason'] == 'READY_FOR_ADVANCE'
                before = len(f.runtime.store.list_events())
                slot['plan_adoption'] = None
                hidden = await client.get('/workspace/source-operation/operation', params=params)
                assert hidden.status_code == 403
                refused = await client.post('/workspace/source-operation/advance', json=dict(
                    schema='mastermind.workspace_source_operation_advance.v1', **params, **ready['advance']))
                assert refused.status_code == 403 and f.pr.create_calls == 1
                assert len(f.runtime.store.list_events()) == before
                slot['plan_adoption'] = dict(work_ref=f.work, permission_digest='8' * 64)
                decision = await post('advance', dict(schema='mastermind.workspace_source_operation_advance.v1',
                    **params, **ready['advance']))
                f.merge(decision)
                accepted = await post('reconcile', lookup)
                assert accepted['disposition'] == 'accepted' and accepted['phase'] == 'ADOPTION'
                assert len(accepted['receipt']['sources']) == 3
                before = len(f.runtime.store.list_events())
                with monkeypatch.context() as scoped:
                    def no_source_capture(*args, **kwargs):
                        raise AssertionError('original status must not acquire current Macro')
                    scoped.setattr(j.collector, '_snapshot_pair', no_source_capture)
                    status = await client.get('/workspace/source-operation/operation', params=params)
                    assert status.status_code == 200 and status.json() == accepted, status.text
                assert len(f.runtime.store.list_events()) == before
                # Optional caller-selected proof output contains ONLY safe
                # synthetic fixture wire/Events, never JWT/private input bytes.
                destination = os.environ.get('MM_ADOPT_HTTP_FIXTURE')
                proof = dict(request=j.request, context=context.json(), initial_read=initial.json(),
                    preview=preview, pending_candidate=pending, ready=ready,
                    pending_adoption=decision, status=accepted,
                    events=[event.to_dict() for event in f.runtime.store.list_events()])
                if destination:
                    Path(destination).write_text(json.dumps(proof, ensure_ascii=False, sort_keys=True))
                reopened = await client.get('/workspace/project-plan/current', params={'work_ref': f.work})
                assert reopened.status_code == 200, reopened.text
                body = reopened.json()
                assert body['availability'] == 'AVAILABLE', body
                assert body['continuity']['adoption']['adoption']['predecessor'] == 'DEC:PLAN-FIRST'
                item = body['continuity']['proposals']['items'][0]
                assert item['adoption_relation'] == 'CURRENT_DECISION_REFERENCES_PROPOSAL'
                assert item['comparison']['candidate_text'].encode() == j.candidate
                # Plan v2 exposes its authentic record revision, not the
                # Knowledge-only data_observation fields. Installed cache
                # remains pinned to C while this exact READ resolves N.
                assert body['source']['commit'] == f.repo['head'] != j.code
                assert len(children) >= 2
                child = children[-1]
                assert child[1:3] == ['-I', '-B']
                assert child[child.index('--code-root') + 1] == str(j.collector._macro_root)
                assert child[child.index('--code-commit') + 1] == j.code
                assert child[child.index('--expected-macro-sha') + 1] == f.repo['head']
                assert f.pr.create_calls == 2 and f.runtime.jobs.list_jobs() == []
                if destination:
                    Path(destination).write_text(json.dumps(proof | {'body': body},
                        ensure_ascii=False, sort_keys=True))
        finally:
            await host.close()
    asyncio.run(run())
