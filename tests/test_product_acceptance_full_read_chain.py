"""One local authenticated request through actual socket/custody/receipt owners.

JWT keys, source/Relay and Control Room inputs are fixtures. This deliberately
does not claim installed-account, live Context or browser acceptance.
"""
import asyncio
import os

import httpx
import pytest

from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_executive_ceo_ingress import _FakeGrounding, _FakeSupervisor, _config, short_socket_root
from tests.test_product_acceptance_basis_continuity import restamp
from tests.test_product_acceptance_read_projection import case
from tests.test_product_acceptance_workspace_read import provider
from tests.test_workspace_read_app import NOW, _authenticator, _workspace_token, rsa_key


@pytest.mark.parametrize('state', ['accepted', 'pending_parent', 'missing_consumption', 'corrected_source'])
def test_authenticated_full_read_chain_requires_current_original_parent_consumption(
    tmp_path, monkeypatch, short_socket_root, rsa_key, state,
):
    with case(tmp_path, monkeypatch, complete=state != 'pending_parent',
              consume=state != 'missing_consumption') as (runtime, owner, target, basis, selected, _):
        if state == 'corrected_source':
            basis.entry['current_intent_revision'] = 'corrected-direction'
            restamp(basis.entry)
        seen = []

        def factory(actual_runtime):
            assert actual_runtime is service.runtime
            bound = service._namespace_custody.bound_runtime(actual_runtime)
            assert bound.store.read_binding is not None
            value, _, _ = provider(tmp_path, actual_runtime, owner.reader, selected, bound)
            seen.append(actual_runtime)
            return value

        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root, runtime_root=runtime.store.root),
            runtime_factory=lambda root: runtime,
            supervisor_factory=lambda actual_runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / 'ceo.sock',
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False,
                grounding_provider=_FakeGrounding(), workspace_read_provider_factory=factory),
        )

        async def run():
            await service.start()
            try:
                events = runtime.events.list_events()
                app = create_workspace_app(WorkspaceAppConfig(
                    authenticator=_authenticator(rsa_key), now=lambda: NOW,
                    authorize_principal=lambda principal: True,
                    client=CeoIngressWorkspaceClient(service.ceo_ingress_socket_path)))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                        base_url='https://mcp.mastermind-x.com') as client:
                    route = '/workspace/mission/v4/current'
                    refused = await client.get(route, params=selected)
                    assert refused.status_code == 401 and not seen
                    response = await client.get(route, params=selected,
                        headers={'Authorization': 'Bearer ' + _workspace_token(rsa_key)})
                assert response.status_code == 200, response.text
                assert response.headers['Cache-Control'] == 'no-store'
                value = response.json()
                assert value['mission']['read_state']['state'] == 'CURRENT'
                assert value['mission']['acceptance']['state'] == 'NOT_PROJECTED'
                acceptance = value['product_acceptance']
                assert acceptance['selection'] == selected
                if state == 'accepted':
                    assert acceptance['state'] == 'ACCEPTED'
                    assert acceptance['receipt']['subject_job_id'] == target.job_id
                    assert acceptance['receipt']['parent_job_id'] == selected['root_job_id']
                else:
                    reason = {'pending_parent': 'PARENT_RETURN_UNVERIFIED',
                              'missing_consumption': 'PARENT_CONSUMPTION_UNPROVEN',
                              'corrected_source': 'SOURCE_CHANGED'}[state]
                    assert acceptance['state'] == 'UNAVAILABLE'
                    assert acceptance['reason_codes'] == [reason]
                    assert acceptance['receipt'] is None
                assert seen == [service.runtime]
                assert runtime.events.list_events() == events
            finally:
                await service.close()

        asyncio.run(run())
