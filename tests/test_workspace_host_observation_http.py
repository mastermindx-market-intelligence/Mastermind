"""Signed HTTP -> one actual Unix exchange -> original source/Runtime fixture.

Mounts the new route module explicitly. Shared Executive/outer registration is
owned by Release and remains a separate integration check, not claimed here.
"""
import asyncio
import copy
import json
import tempfile
from types import SimpleNamespace
import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from common import workspace_host_observation_contract as wire
from control_plane.workspace_host_observation_read import handle_host_observation_frame
from integrations.mastermind_workspace_app.host_observation import ROUTE, host_observation_current
from integrations.mastermind_workspace_app.host_observation_client import request_host_observation
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from integrations.mastermind_executive_app.coo_binding import _digest
from tests.test_workspace_host_observation_read import host_owner
from tests.test_workspace_read_app import _authenticator, _workspace_token, rsa_key, NOW


@pytest.fixture
def owner(tmp_path, monkeypatch, request):
    if request.node.callspec.params.get("case") == "missing_capture":
        from control_plane import physical_capacity_capture_owner as capture
        monkeypatch.setattr(capture, "mint_capacity_capture", lambda *args, **kwargs: None)
    with host_owner(tmp_path, monkeypatch) as value:
        yield value


@pytest.mark.parametrize("case", ["available", "coo_revoked", "read_revoked", "expired", "wrong_attempt", "foreign_body", "missing_capture"])
def test_actual_signed_route_socket_and_retained_source(owner, rsa_key, monkeypatch, case):
    auth = _authenticator(rsa_key)
    token = _workspace_token(rsa_key)
    async def run():
        principal = await auth.verify_authorization_header("Bearer " + token, now=NOW)
        frame = principal_frame(principal)
        slots = {"schema": BINDINGS_SCHEMA, "profiles": {
            "web": {"enabled": True, "binding": {**frame, "permission_digest": "a" * 64}},
            "mac": {"enabled": False, "binding": None}}}
        upper, lower = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
        owner["service"].authorize = lower
        mutable = owner["mutable"]
        mutable["policy"]["issuer"] = auth.policy.issuer
        mutable["policy"]["authorization_servers"] = [auth.policy.issuer]
        mutable["policy"]["jwks_uri"] = auth.policy.issuer + "/.well-known/jwks.json"
        mutable["policy"]["allowed_subject_digests"] = [frame["subject_digest"]]
        enrolled = mutable["binding"]["binding"]
        for key in ("issuer_digest", "subject_digest", "client_ref"): enrolled[key] = frame[key]
        mutable["missions"][0]["principal_binding_digest"] = _digest(enrolled)
        clock = [NOW]
        sent = []
        from control_plane import workspace_host_observation_read as source
        original = source.read_host_observation
        def observed(*args):
            result = original(*args)
            if case == "coo_revoked": mutable["missions"][0]["enabled"] = False
            return result
        monkeypatch.setattr(source, "read_host_observation", observed)
        with tempfile.TemporaryDirectory(prefix="hobs-", dir="/tmp") as directory:
            path = directory + "/s"
            async def dispatch(reader, writer):
                try:
                    request = json.loads(await reader.readline()); sent.append(request)
                    result = await handle_host_observation_frame(owner["service"], request)
                    if case == "foreign_body" and result.get("ok") is True:
                        result["result"]["observation"]["snapshot"]["private_account"] = "SECRET"
                    writer.write(json.dumps(result).encode() + b"\n"); await writer.drain()
                finally:
                    writer.close(); await writer.wait_closed()
            server = await asyncio.start_unix_server(dispatch, path=path)
            class Client:
                async def request(self, request):
                    result = await request_host_observation(SimpleNamespace(socket_path=path, timeout_seconds=10), request)
                    if case == "read_revoked": slots["profiles"]["web"]["enabled"] = False
                    if case == "expired": clock[0] = principal.expires_at
                    return result
            config = WorkspaceAppConfig(authenticator=auth, now=lambda: clock[0], authorize_principal=upper, client=Client())
            async def endpoint(request): return await host_observation_current(request, config=config)
            app = Starlette(routes=[Route(ROUTE, endpoint, methods=["GET"])])
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.mastermind-x.com") as http:
                    selected = dict(owner["selected"])
                    if case == "wrong_attempt": selected["attempt_id"] = "ATT-" + "9" * 32
                    response = await http.get(ROUTE, params=selected, headers={"Authorization": "Bearer " + token})
                    if case in ("coo_revoked", "read_revoked", "expired"):
                        assert response.status_code == 403, response.text
                    elif case in ("wrong_attempt", "missing_capture", "foreign_body"):
                        assert response.status_code == 503, response.text
                    else:
                        assert response.status_code == 200, response.text
                        body = response.json(); wire.validate_result(body, selected)
                        assert body["observation"]["observed_host_role"] == "PHYSICAL_RESOURCE_HOST"
                        assert body["source_observation"]["runtime"]["state"] == "SAME"
                        assert response.headers["cache-control"] == "no-store"
                    assert "SECRET" not in response.text
                    assert len(sent) == 1
            finally:
                server.close(); await server.wait_closed()
    asyncio.run(run())
