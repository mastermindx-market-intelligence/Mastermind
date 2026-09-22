import asyncio
import json
import tempfile
from pathlib import Path
from integrations.mastermind_steward_app.installed import CeoIngressContentClient, InstalledWindowSource
from integrations.executive_content_contract import ACCESS_SCHEMA, PAGE_SCHEMA
from test_executive_content_observer import profile


def test_real_unix_framing_allows_large_content_only(tmp_path):
    async def run():
        directory=tempfile.TemporaryDirectory(prefix='mmcontent-',dir='/tmp')
        path=Path(directory.name)/'read.sock'
        async def handle(reader,writer):
            frame=json.loads(await reader.readline())
            response={'ok':True,'page':{'content':'x'*40000}} if frame['schema']==PAGE_SCHEMA else {'ok':True,'access':{'content':'x'*40000}}
            writer.write(json.dumps(response).encode()+b'\n')
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        server=await asyncio.start_unix_server(handle,path=str(path))
        async with server:
            client=CeoIngressContentClient(path)
            assert len((await client.request({'schema':PAGE_SCHEMA}))['page']['content'])==40000
            try:
                await client.request({'schema':ACCESS_SCHEMA})
            except ValueError:
                pass
            else:
                raise AssertionError('legacy-size access reply must be refused')
    asyncio.run(run())


def test_fixed_installed_source_refuses_wrong_principal_before_transport():
    from integrations.business_mcp_auth.contracts import VerifiedPrincipal
    class Client:
        async def request(self,frame):
            raise AssertionError('wrong viewer must not reach control')
    p=profile()
    source=InstalledWindowSource(profile=p,client=Client(),now=lambda:1789977600)
    principal=VerifiedPrincipal(p.policy_id,'https://issuer',p.issuer_digest,'https://app/content',p.subject_digest,'wrong',('mastermind.workspace.content.read',),1,2000000000,None)
    assert asyncio.run(source.current_access(principal,p.source_ref)) is None
