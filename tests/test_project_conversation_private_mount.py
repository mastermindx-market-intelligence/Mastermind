"""Signed leaf through actual Unix App peer to nominal Runtime READ owners.

Uses the existing disposable service/provider fixture, never an installed host.
"""
import asyncio
import dataclasses
import hashlib
import tempfile
import time
from pathlib import Path

from control_plane.fresh_conversation import FreshConversationOwner
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from integrations.mastermind_executive_app.project_conversation_transport import (
    ProjectConversationReadClient, ProjectConversationTransportApp,
)
from integrations.session_bridge.installed import build_runtime_project_conversation_reader
from tests import test_mastermind_executive_app_asgi as auth
from tests import test_mastermind_os_session_transport as session
from tests.test_fresh_conversation_http import mounted, post, rsa_key
from tests.test_fresh_conversation import cleanup
from tests.test_project_conversation_transport import exchange
from tests.test_executive_mcp_public_audience import settings, short_socket_root, fake_jwks


def test_signed_project_read_reaches_real_private_sources_and_rejects_revocation(tmp_path, rsa_key, monkeypatch):
    async def run():
        initial, token, workspace, service, runtime, request, adapters, _, _ = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            code, preview = await post(initial, 'preview', request, token, workspace)
            assert code == 200 and preview['ok']
            code, created = await post(initial, 'create', {**request, 'preview_digest': preview['data']['preview']['digest']}, token, workspace)
            assert code == 200 and created['data']['state'] == 'CREATED'
            auth_owner, _, clock, _ = session.make_app(rsa_key)
            clock[0] = int(time.time())
            policies = AppPolicies(read=auth._read_policy(), submit=auth._submit_policy())
            submit = policies.submit
            expected = (submit.policy_id, hashlib.sha256(submit.issuer.encode()).hexdigest(), submit.resource)
            current = True
            def old_factory(selected):
                if selected is not runtime or not current:
                    raise ValueError('fixture source withdrawn')
                return build_runtime_project_conversation_reader(runtime,
                    dialogue_socket_path=Path('/no-live-dialogue.sock'), codex_owner_configured=lambda: False,
                    authorized_policies=policies, reference_cursor_key=b'k' * 32)
            def fresh_factory(selected):
                if selected is not runtime or not current:
                    raise ValueError('fixture source withdrawn')
                return FreshConversationOwner(service, expected_policy=expected, authorized_policies=policies)
            service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding,
                project_conversation_read_provider_factory=old_factory,
                fresh_conversation_provider_factory=fresh_factory)
            read_token = auth._read_token(rsa_key, iat=clock[0]-1, nbf=clock[0]-1, exp=clock[0]+600)
            before = runtime.events.list_events()
            with tempfile.TemporaryDirectory(prefix='project-read-private-', dir='/tmp') as directory:
                socket = Path(directory) / 's'
                server = await asyncio.start_unix_server(service._handle_ceo_ingress_connection, path=socket)
                leaf = ProjectConversationTransportApp(ProjectConversationReadClient(socket, client=CeoIngressClient()), auth_owner=auth_owner)
                try:
                    code, old = await exchange(leaf, read_token, 'catalogue', {'work_ref': request['work_ref']})
                    assert code == 200 and old['conversations'] == []
                    code, catalogue = await exchange(leaf, read_token, 'fresh_references', {'work_ref': request['work_ref']})
                    assert code == 200 and len(catalogue['entries']) == 1
                    reference = catalogue['entries'][0]['reference']
                    code, result = await exchange(leaf, read_token, 'fresh_read', reference)
                    assert code == 200 and result['reference'] == reference and result['initial_result']
                    assert result['can_send'] is False
                    current = False
                    code, _ = await exchange(leaf, read_token, 'fresh_read', reference)
                    assert code == 503
                    current = True
                    service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding, armed=False)
                    code, _ = await exchange(leaf, read_token, 'catalogue', {'work_ref': request['work_ref']})
                    assert code == 503
                    assert runtime.events.list_events() == before
                    assert len(adapters) == 1 and adapters[0].begin_turn_calls == 1
                finally:
                    server.close()
                    await server.wait_closed()
        finally:
            await cleanup(service)
            if service._ceo_ingress_tasks:
                await asyncio.wait_for(asyncio.gather(*service._ceo_ingress_tasks), 5)
    asyncio.run(run())


def test_installed_v3_factory_registers_all_four_reads_with_incumbent_auth_owner(tmp_path, rsa_key, monkeypatch, settings):
    from integrations.executive_mcp import server as gateway
    from tests.test_executive_mcp_public_audience import FixedMdm, _assets
    from integrations.mastermind_executive_app.project_conversation_transport import ROUTES
    async def run():
        original, _, _, service, runtime, _, _, _, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        config = original._workspace
        workspace = gateway.AuditedWorkspaceApp(original._inner, original._workspace_verifier,
            authenticator=config.authenticator, authorize_principal=config.authorize_principal,
            fresh_workspace_config=config)
        installed = dataclasses.replace(settings, clock=lambda: int(time.time()), read_from_ceo_ingress=True)
        app = gateway.build_web_ceo_v3_mcp_app(installed, audit_sink=sink, mdm_reader=FixedMdm(),
            session_target_projector=lambda *_: [], session_reply_handler=lambda *_: {},
            session_summon_handler=lambda *_: {}, workspace_app=workspace, os_app=_assets(),
            os_session_bridge_client=__import__("integrations.session_bridge.installed",fromlist=["InstalledSessionBridgeClient"]).InstalledSessionBridgeClient(installed.ceo_ingress_socket_path),
            enable_os_executive_transport=True, os_executive_resource=installed.policies.submit.resource)
        try:
            assert type(app.project_conversation_transport) is ProjectConversationTransportApp
            assert app.project_conversation_transport._owner is app.os_session_transport
            before = runtime.events.list_events()
            for operation in ROUTES.values():
                code, _ = await exchange(app, 'invalid-token', operation)
                assert code == 401
            assert runtime.events.list_events() == before
        finally:
            await cleanup(service)
    asyncio.run(run())
