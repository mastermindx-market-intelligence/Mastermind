"""Actual captured Git/parser -> issued READ -> Unix socket -> authenticated HTTP.

All source and auth are isolated fixtures, without installed service/provider effects.
"""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from control_plane import agentos_project_plan as plan
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.executive_mcp.installed import _default_packet_runner
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_agentos_plan_continuity_capture import repository
from tests.test_installed_product_acceptance_context import fixture
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_result_socket import control, short_socket_root


@pytest.mark.parametrize('revocation', [None, 'after_source', 'after_socket'])
def test_v2_actual_git_issued_collector_authenticated_http(tmp_path, monkeypatch, repository, rsa_key, short_socket_root, revocation):
    async def run():
        repo = repository
        auth = _authenticator(rsa_key); token = _workspace_token(rsa_key)
        principal = await auth.verify_authorization_header('Bearer ' + token, now=NOW)
        bindings = {'schema': BINDINGS_SCHEMA, 'profiles': {
            'web': {'enabled': True, 'binding': dict(principal_frame(principal), permission_digest='a' * 64)},
            'mac': {'enabled': False, 'binding': None}}}
        app_auth, frame_auth = workspace_authorizers(policy=auth.policy, load_bindings=lambda: bindings)
        def revoke(): bindings['profiles']['web']['enabled'] = False
        source_area = tmp_path / 'source-context'; source_area.mkdir()
        collector, _, seen = fixture(source_area)
        # Build this isolated nominal collector's actual source binding before issuance.
        collector._macro_root = repo['root'].resolve()
        monkeypatch.setattr(plan, '_SOURCE_ROOT', seen['code'])
        calls = []
        def runner(argv, **limits):
            calls.append(argv)
            if argv[0] == 'git': return _default_packet_runner(argv, **limits)
            assert '--continuity' in argv
            child = Path(argv[argv.index('--macro-root') + 1])
            value = plan.read_from_macro_owner(macro_root=child,
                expected_macro_sha=argv[argv.index('--expected-macro-sha') + 1],
                work_ref=argv[argv.index('--work-ref') + 1], include_continuity=True,
                timeout=float(argv[-1]))
            if revocation == 'after_source': revoke()
            return dict(code=0, stdout=json.dumps(value), timed_out=False, limit_exceeded=False, invalid_utf8=False)
        collector._runner = runner
        reader = collector.project_plan_reader(macro_root=repo['root'])
        owners, clock, cache = cache_fixture(tmp_path)
        owners[0].state_cache['doc']['work'][0]['work_ref'] = 'WS:PLAN-TEST'
        owners[0].state_cache['doc']['sources'] = {'macro_sha': repo['head']}
        owners[0].state_cache['doc']['autonomy']['responsibilities'][0]['responsibility_ref'] = 'WS:PLAN-TEST'
        from scripts import chairman_control_room as ccr
        with owners[0].state_lock:
            ccr._publish_source_validity(owners[0], owners[0].state_cache['doc'], tuple(clock), tuple(clock))
        class RuntimeForbidden:
            def __getattr__(self, name): pytest.fail('Plan READ must not touch Runtime')
        source = WorkspaceReadService(cache=cache, runtime=RuntimeForbidden(), authorize=frame_auth,
            armed={}, runtime_identity={}, project_plan_reader=reader)
        svc = control(tmp_path / 'service', short_socket_root, lambda _: source)
        await svc.start()
        peer = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
        class Client:
            async def request(self, frame):
                value = await peer.request(frame)
                if revocation == 'after_socket': revoke()
                return value
        app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: NOW,
            authorize_principal=app_auth, client=Client()))
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://mcp.mastermind-x.com') as client:
                result = await client.get('/workspace/project-plan/current', params={'work_ref': 'WS:PLAN-TEST'},
                    headers={'Authorization': 'Bearer ' + token})
            assert calls, (result.status_code, result.text)
            if revocation:
                assert result.status_code == 403, result.text
                assert 'Improved candidate' not in result.text and 'base_text' not in result.text
            else:
                assert result.status_code == 200, result.text
                body = result.json()
                assert body['schema'] == 'mastermind.workspace_project_plan.v2'
                comparison = body['continuity']['proposals']['items'][0]['comparison']
                assert comparison['base_text'].encode() == repo['baseline_bytes']
                assert comparison['candidate_text'].encode() == repo['candidate']
                assert body['source']['commit'] == repo['head']
                assert 'no-store' in result.headers['cache-control']
        finally: await svc.close()
    asyncio.run(run())
