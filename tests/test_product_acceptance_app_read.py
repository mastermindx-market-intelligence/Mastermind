"""Real JWT validation and new route framing; retained producer body is a fixture."""
import asyncio
import copy
import json
from pathlib import Path

import httpx
import pytest

from common import product_acceptance_read_contract as contract
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_workspace_read_app import _FakeWorkspaceClient, _make_app, _workspace_token, rsa_key
from tests.test_workspace_read_service import frame
from tests.test_workspace_read_socket import control
from tests.test_executive_ceo_ingress import short_socket_root
from tests.test_workspace_result_mount import _Mount, settings
import test_executive_mcp_app_composition as existing
from integrations.executive_mcp import server

ROUTE = '/workspace/mission/v4/current'
FIXTURE = Path(__file__).parents[1]/'app/mastermind_os/src/fixtures/mission-v4-owner-accepted.json'


def body(): return json.loads(FIXTURE.read_text())
def selection(): return body()['product_acceptance']['selection']
def headers(key): return {'Authorization': 'Bearer '+_workspace_token(key)}


def test_read_route_delivers_exact_original_parent_consumed_receipt(rsa_key):
    fake = _FakeWorkspaceClient(envelope={'ok': True, 'result': body()})
    client, _ = _make_app(rsa_key, client=fake)
    response = client.get(ROUTE, params=selection(), headers=headers(rsa_key))
    assert response.status_code == 200, response.text
    assert response.json()['product_acceptance']['state'] == 'ACCEPTED'
    assert response.headers['Cache-Control'] == 'no-store'
    assert len(fake.calls) == 1
    assert fake.calls[0]['schema'] == contract.FRAME_SCHEMA
    assert fake.calls[0]['selection'] == selection()


@pytest.mark.parametrize('defect', ['key', 'root', 'work', 'partial', 'receipt_extra'])
def test_foreign_or_unqualified_response_is_withheld(rsa_key, defect):
    value = body()
    if defect == 'key': value['product_acceptance']['selection']['request_message_key'] = 'asd-mcp-'+'f'*32
    if defect == 'root': value['mission']['mission']['root_job_id'] = 'JOB-999'
    if defect == 'work': value['mission']['program']['work_ref'] = 'WS:FOREIGN'
    if defect == 'partial': value['mission']['read_state']['state'] = 'PARTIAL'
    if defect == 'receipt_extra': value['product_acceptance']['receipt']['host_path'] = 'private'
    fake = _FakeWorkspaceClient(envelope={'ok': True, 'result': value})
    client, _ = _make_app(rsa_key, client=fake)
    response = client.get(ROUTE, params=selection(), headers=headers(rsa_key))
    assert response.status_code == 503
    assert 'qualified_ruling_digest' not in response.text


@pytest.mark.parametrize('defect', ['missing', 'extra', 'malformed', 'duplicate'])
def test_closed_query_refuses_before_owner(rsa_key, defect):
    client, fake = _make_app(rsa_key)
    params = selection()
    if defect == 'missing': del params['request_message_key']
    if defect == 'extra': params['authority'] = 'accepted'
    if defect == 'malformed': params['request_message_key'] = 'asd-mcp-invalid'
    if defect == 'duplicate': params = list(params.items()) + [('work_ref', params['work_ref'])]
    assert client.get(ROUTE, params=params, headers=headers(rsa_key)).status_code == 400
    assert not fake.calls


def test_permission_rotation_after_read_discards_receipt(rsa_key):
    epoch = [0]
    authorize = lambda _: True
    authorize.binding_digest = lambda _: str(epoch[0])*64
    fake = _FakeWorkspaceClient(envelope={'ok': True, 'result': body()}, on_call=lambda _: epoch.__setitem__(0, 1))
    client, _ = _make_app(rsa_key, client=fake, authorize=authorize)
    response = client.get(ROUTE, params=selection(), headers=headers(rsa_key))
    assert response.status_code == 403 and 'qualified_ruling_digest' not in response.text


def test_actual_app_peer_socket_dispatches_v4_without_arming_submission(tmp_path, short_socket_root):
    captured = []
    class Provider:
        async def handle_frame(self, value):
            captured.append(value)
            return {'ok': True, 'result': body()}
    async def run():
        service = control(tmp_path, short_socket_root, lambda runtime: Provider())
        await service.start()
        try:
            request = {**frame(), 'schema': contract.FRAME_SCHEMA, 'operation': contract.OPERATION,
                       'selection': selection()}
            result = await CeoIngressWorkspaceClient(service.ceo_ingress_socket_path).request(request)
            assert result['result'] == body()
            assert captured == [request]
        finally:
            await service.close()
    asyncio.run(run())


def test_uid458_mount_preserves_method_path_and_header_fences(settings):
    mounted = _Mount()
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(), workspace_app=mounted)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://mcp.mastermind-x.com') as client:
            assert (await client.get(ROUTE, params=selection())).status_code == 200
            assert len(mounted.calls) == 1
            for method, path in [('POST', ROUTE), ('GET', ROUTE+'/'), ('GET', '/workspace%2Fmission/v4/current')]:
                assert (await client.request(method, path)).status_code == 404
            assert (await client.get(ROUTE, headers=[('Authorization','Bearer a'),('Authorization','Bearer b')])).status_code in (400,401)
            assert len(mounted.calls) == 1
    asyncio.run(run())
