"""Only the new instruction literals; actual signed owner chain is separate."""
import asyncio
import httpx
import pytest
from integrations.executive_mcp import server
from tests.test_executive_workspace_mount import Mount,settings,existing,rsa_key,short_socket_root


@pytest.mark.parametrize('path',['/workspace/project-instructions/current','/workspace/instruction-admission/current','/workspace/instruction-admission/operation'])
def test_instruction_get_routes_remain_exact_query_gets(settings,path):
    mount=Mount();app=server.build_executive_mcp_app(settings,audit_sink=existing.Sink(),workspace_app=mount)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com') as client:
            query='work_ref=WS%3AONE&instruction_ref=INS%3ADAILY-ONE'
            assert (await client.get(path+'?'+query)).status_code==200
            assert mount.calls==[(path,query.encode())]
            for method,url in [('POST',path),('HEAD',path),('GET',path+'/'),('GET',path.replace('/workspace/','/workspace%2f'))]:
                assert (await client.request(method,url)).status_code in (400,403,404)
            assert len(mount.calls)==1
    asyncio.run(run())


def test_instruction_pause_is_one_literal_post_with_incumbent_public_fences(settings):
    mount=Mount();app=server.build_executive_mcp_app(settings,audit_sink=existing.Sink(),workspace_app=mount)
    absent=server.build_executive_mcp_app(settings,audit_sink=existing.Sink())
    async def run():
        path='/workspace/instruction-admission/pause'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com') as client:
            assert (await client.post(path,json={'inner_fixture_only':True})).status_code==200
            for method,url,headers in [('GET',path,{}),('POST',path+'?x=1',{}),('POST',path+'/',{}),('POST',path,{'Origin':'https://foreign.example'})]:
                assert (await client.request(method,url,headers=headers)).status_code in (400,403,404)
            assert len(mount.calls)==1
            assert (await client.post('/workspace/instruction-admission/resume')).status_code==404
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=absent),base_url='https://mcp.mastermind-x.com') as client:
            assert (await client.post(path)).status_code==404
    asyncio.run(run())
