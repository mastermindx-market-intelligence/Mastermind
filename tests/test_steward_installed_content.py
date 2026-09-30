import asyncio
import json
import tempfile
from pathlib import Path

import pytest

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


def test_installed_constructor_derives_typed_binding_from_canonical_profile():
    from test_mastermind_steward_app_live_window import (
        ORIGIN, WINDOW_RESOURCE, _Sink, _cache, _content_policy, _key,
    )
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    from integrations.mastermind_steward_app.installed import construct_installed_live_window
    from integrations.mastermind_window_reader.owner_read_resource import ObservationBinding
    p=profile(policy_id='mastermind-workspace-window-fixture',content_resource=WINDOW_RESOURCE,
        job_id='JOB-000042',attempt_id='ATT-'+('ab'*16))
    key=_key();policy=_content_policy()
    config=construct_installed_live_window(
        profile=p,authenticator=JwtAuthenticator(policy=policy,jwks_cache=_cache(policy,key)),
        content_policy=policy,audit_sink=_Sink(),ceo_ingress_socket_path=Path('/tmp/unused-installed.sock'),
        now=lambda:1789977600,allowed_origin=ORIGIN,
    )
    assert type(config.observation_binding) is ObservationBinding
    assert config.observation_binding.job_id=='JOB-000042'
    assert config.observation_binding.attempt_id=='ATT-'+('ab'*16)


@pytest.mark.parametrize("changes", [
    {"job_id":"job"},{"attempt_id":"attempt"},
    {"job_id":"JOB-not-canonical"},{"attempt_id":"ATT-invalid"},
    {"job_id":"JOB-"+("0"*10)},
])
def test_noncanonical_installed_profile_is_a_typed_refusal(changes):
    from test_mastermind_steward_app_live_window import (
        ORIGIN, WINDOW_RESOURCE, _Sink, _cache, _content_policy, _key,
    )
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    from integrations.mastermind_steward_app.installed import construct_installed_live_window
    canonical={"policy_id":'mastermind-workspace-window-fixture',"content_resource":WINDOW_RESOURCE,
        "job_id":'JOB-000042',"attempt_id":'ATT-'+('ab'*16)}
    canonical.update(changes)
    p=profile(**canonical)
    key=_key();policy=_content_policy()
    with pytest.raises(ValueError,match='invalid observation binding'):
        construct_installed_live_window(
            profile=p,authenticator=JwtAuthenticator(policy=policy,jwks_cache=_cache(policy,key)),
            content_policy=policy,audit_sink=_Sink(),ceo_ingress_socket_path=Path('/tmp/unused-installed.sock'),
            now=lambda:1789977600,allowed_origin=ORIGIN,
        )
