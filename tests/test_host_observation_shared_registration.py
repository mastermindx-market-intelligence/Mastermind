"""Exercise shared dispatch against the accepted original source fixture."""
import asyncio
from tests.test_workspace_host_observation_read import owner
from control_plane.coo_principal_host import CooHostProvider
from tests.test_workspace_read_app import rsa_key


def test_shared_read_service_dispatch_and_original_coo_provider_preserve_recorded_read(owner):
    async def run():
        direct = await owner["service"].handle_frame(owner["request"])
        assert direct["ok"] and direct["result"]["availability"] == "AVAILABLE"
        provider = CooHostProvider(owner["coo"].source, owner["service"])
        original = await provider.read_workspace_host_observation(owner["request"])
        assert original["ok"] and original["result"]["availability"] == "AVAILABLE"
        assert original["result"]["selection"] == direct["result"]["selection"] == owner["selected"]
        assert original["result"]["observation"]["observed_host_role"] == "PHYSICAL_RESOURCE_HOST"
    asyncio.run(run())


def test_actual_workspace_factory_and_installed_client_reach_original_coo_source(owner, rsa_key):
    import json, tempfile
    import httpx
    from common.executive_workspace_contract import PRINCIPAL_KEYS
    from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
    from integrations.mastermind_executive_app.coo_binding import _digest
    from tests.test_workspace_read_app import _authenticator, _workspace_token, NOW
    async def run():
        authenticator = _authenticator(rsa_key)
        token = _workspace_token(rsa_key)
        principal = await authenticator.verify_authorization_header("Bearer " + token, now=NOW)
        frame = principal_frame(principal)
        slots = {"schema": BINDINGS_SCHEMA, "profiles": {
            "web": {"enabled": True, "binding": {**frame, "permission_digest": "a" * 64}},
            "mac": {"enabled": False, "binding": None}}}
        upper, lower = workspace_authorizers(policy=authenticator.policy, load_bindings=lambda: slots)
        owner["service"].authorize = lower
        mutable = owner["mutable"]
        mutable["policy"].update(issuer=authenticator.policy.issuer,
            authorization_servers=[authenticator.policy.issuer],
            jwks_uri=authenticator.policy.issuer+"/.well-known/jwks.json",
            allowed_subject_digests=[frame["subject_digest"]])
        enrolled = mutable["binding"]["binding"]
        for key in ("issuer_digest", "subject_digest", "client_ref"): enrolled[key] = frame[key]
        mutable["missions"][0]["principal_binding_digest"] = _digest(enrolled)
        provider = CooHostProvider(owner["coo"].source, owner["service"])
        calls=[]
        with tempfile.TemporaryDirectory(prefix="host-observation-join-",dir="/tmp") as root:
            path=root+"/app.sock"
            async def dispatch(reader,writer):
                try:
                    request=json.loads(await reader.readline());calls.append(request)
                    result=await provider.read_workspace_host_observation(request)
                    writer.write(json.dumps(result).encode()+b"\n");await writer.drain()
                finally:
                    writer.close();await writer.wait_closed()
            server=await asyncio.start_unix_server(dispatch,path=path)
            config=WorkspaceAppConfig(authenticator=authenticator, now=lambda:NOW, authorize_principal=upper,
                client=CeoIngressWorkspaceClient(path))
            app=create_workspace_app(config)
            route="/workspace/resources/host-observation/current"
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="https://mcp.mastermind-x.com") as client:
                    response=await client.get(route,params=owner["selected"],headers={"Authorization":"Bearer "+token})
                    assert response.status_code==200
                    body=response.json();assert body["availability"]=="AVAILABLE"
                    assert body["selection"]==owner["selected"]
                    assert body["observation"]["observed_host_role"]=="PHYSICAL_RESOURCE_HOST"
                    assert response.headers["cache-control"]=="no-store" and len(calls)==1
                    head=await client.head(route,params=owner["selected"],headers={"Authorization":"Bearer "+token})
                    assert head.status_code==405 and len(calls)==1
            finally:
                server.close();await server.wait_closed()
    asyncio.run(run())
