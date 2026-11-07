"""Actual Unix exchange against a lawful slow acceptance-source observation."""
import asyncio

import pytest

from common import product_acceptance_read_contract as contract
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_executive_ceo_ingress import short_socket_root
from tests.test_product_acceptance_app_read import body, selection
from tests.test_workspace_read_service import frame
from tests.test_workspace_read_socket import control


def test_default_acceptance_read_survives_work_inside_the_sealed_source_budget(tmp_path, short_socket_root):
    settled = asyncio.Event()
    class Provider:
        async def handle_frame(self, request):
            assert request['schema'] == contract.FRAME_SCHEMA
            # The sealed source owner has a 15-second cumulative deadline.
            # A 10.25-second observation is legal but exceeded the old client default.
            try:
                await asyncio.sleep(10.25)
            finally:
                settled.set()
            return {'ok': True, 'result': body()}

    async def run():
        service = control(tmp_path, short_socket_root, lambda runtime: Provider())
        await service.start()
        try:
            request = {**frame(), 'schema': contract.FRAME_SCHEMA, 'operation': contract.OPERATION,
                       'selection': selection()}
            response = await CeoIngressWorkspaceClient(service.ceo_ingress_socket_path).request(request)
            assert response == {'ok': True, 'result': body()}
        finally:
            await asyncio.wait_for(settled.wait(), 15)
            await service.close()
    asyncio.run(run())


@pytest.mark.parametrize('acceptance', [False, True])
def test_each_read_operation_keeps_its_explicit_short_deadline(tmp_path, short_socket_root, acceptance):
    settled = asyncio.Event()
    class Provider:
        async def handle_frame(self, request):
            try:
                await asyncio.sleep(.3)
            finally:
                settled.set()
            return {'ok': True, 'result': body()}

    async def run():
        service = control(tmp_path, short_socket_root, lambda runtime: Provider())
        await service.start()
        try:
            client = CeoIngressWorkspaceClient(service.ceo_ingress_socket_path,
                timeout_seconds=.1, acceptance_timeout_seconds=.1)
            request = frame()
            if acceptance:
                request.update(schema=contract.FRAME_SCHEMA, operation=contract.OPERATION, selection=selection())
            with pytest.raises(ValueError, match='source_unavailable'):
                await client.request(request)
        finally:
            await asyncio.wait_for(settled.wait(), 2)
            await service.close()
    asyncio.run(run())
