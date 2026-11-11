"""Canonical parser→Workspace→real fixture Unix socket→authenticated mounted HTTP.

All source/process/auth fixtures are isolated; no installed service or provider effect.
"""
import asyncio

import httpx
import pytest

from common import executive_workspace_contract as wire
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from integrations.executive_mcp.server import AuditedWorkspaceApp, build_executive_mcp_app, _mounted_lifespan
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.gateway import AppPolicies
from tests.test_workspace_project_plan_read import provider, request, ROUTE
from tests.test_agentos_project_plan_source import source_git
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW
from tests.test_workspace_result_socket import control, short_socket_root, _FakeProvider
from tests.test_mastermind_executive_app_asgi import _read_policy, _submit_policy, _FakeJwksCache


@pytest.mark.parametrize("revocation", [None, "after_source", "after_socket"])
def test_mounted_signed_route_real_socket_and_source_fences(tmp_path, monkeypatch, source_git, rsa_key, short_socket_root, revocation):
    async def run():
        auth = _authenticator(rsa_key)
        token = _workspace_token(rsa_key)
        principal = await auth.verify_authorization_header("Bearer " + token, now=NOW)
        slots = {"schema": BINDINGS_SCHEMA, "profiles": {
            "web": {"enabled": True, "binding": dict(principal_frame(principal), permission_digest="a" * 64)},
            "mac": {"enabled": False, "binding": None}}}
        app_auth, control_auth = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
        def revoke(_): slots["profiles"]["web"]["enabled"] = False
        source, _, calls = provider(tmp_path, monkeypatch, source_git, authorize=control_auth,
            after=revoke if revocation == "after_source" else None)
        svc = control(tmp_path / "service", short_socket_root, lambda _: source)
        await svc.start()
        peer = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
        class AppClient:
            async def request(self, value):
                result = await peer.request(value)
                if revocation == "after_socket": revoke(None)
                return result
        app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: NOW,
            authorize_principal=app_auth, client=AppClient()))
        class Sink:
            def emit(self, _): pass
        sink = Sink()
        verifier = MastermindTokenVerifier(authenticator=auth, policy=auth.policy, now=lambda: NOW, audit_sink=sink)
        mounted = build_executive_mcp_app(AppSettings(policies=AppPolicies(read=_read_policy(), submit=_submit_policy()),
            mastermind_root=tmp_path, macro_root_flag=None, environ={}, ceo_ingress_socket_path=svc.ceo_ingress_socket_path,
            read_from_ceo_ingress=True, jwks_cache=_FakeJwksCache(rsa_key), clock=lambda: NOW),
            audit_sink=sink, workspace_app=AuditedWorkspaceApp(app, verifier))
        try:
            async with _mounted_lifespan(mounted):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mounted), base_url="https://mcp.mastermind-x.com") as client:
                    result = await client.get(ROUTE, params={"work_ref": "WS:ONE"}, headers={"Authorization": "Bearer " + token})
                    assert calls
                    if revocation:
                        assert result.status_code == 403, result.text
                        assert "Deliver the real" not in result.text
                    else:
                        assert result.status_code == 200, result.text
                        assert result.json()["plan"]["objective"] == "Deliver the real owner content."
                        assert result.json()["selection"] == {"work_ref": "WS:ONE"}
                        assert "no-store" in result.headers["cache-control"]
        finally: await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize("size", [131071, 131072, 131073])
def test_exact_socket_whole_utf8_envelope_and_lf_cap(tmp_path, short_socket_root, size):
    envelope = {"ok": True, "result": {"padding": "漢"}}
    envelope["result"]["padding"] += "x" * (size - len(wire.canonical(envelope)) - 1)
    async def run():
        svc = control(tmp_path, short_socket_root, lambda _: _FakeProvider(envelope))
        await svc.start()
        try:
            result = await CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path).request(request())
            assert result == (envelope if size <= 131072 else wire.error("source_unavailable", 503))
        finally: await svc.close()
    asyncio.run(run())


def test_malformed_plan_frame_refuses_before_socket(monkeypatch):
    async def forbidden(*a, **kw): pytest.fail("malformed selector opened a socket")
    monkeypatch.setattr(asyncio, "open_unix_connection", forbidden)
    value = request(); value["selection"]["root_job_id"] = "JOB-1"
    with pytest.raises(ValueError):
        asyncio.run(CeoIngressWorkspaceClient("/tmp/not-opened.sock").request(value))
