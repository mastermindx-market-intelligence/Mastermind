"""Static same-listener CEO/COO MCP composition; real JWT verification."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_executive_coo_app as fixture
finally:
    sys.path.pop(0)

from integrations.executive_mcp import server
from integrations.executive_mcp.coo import COO_TOOL_NAMES
from integrations.mastermind_executive_app.coo_binding import BINDING_SCHEMA

rsa_key = fixture.rsa_key


async def rpc(client, token, path, method="tools/list", params=None):
    headers = {"authorization": "Bearer " + token, "accept": "application/json, text/event-stream",
               "mcp-protocol-version": "2025-06-18"}
    data = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        data["params"] = params
    return await client.post(path, headers=headers, json=data)


def test_same_process_preserves_ceo_surface_and_separates_coo(rsa_key, tmp_path):
    _, token, current, settings = fixture.setup(rsa_key, tmp_path)
    app = server.build_web_ceo_v2_with_coo_mcp_app(settings.executive,
        coo_settings=settings, audit_sink=fixture.Sink())
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                result = await rpc(client, token, "/mcp/coo")
                assert result.status_code == 200, result.text
                tools = result.json()["result"]["tools"]
                assert tuple(t["name"] for t in tools) == COO_TOOL_NAMES
                assert all(t["securitySchemes"][0]["scopes"] == list(settings.policy.required_scopes) for t in tools)
                reader = fixture.fixture._read_token(rsa_key)
                legacy = await rpc(client, reader, "/mcp")
                assert legacy.status_code == 200, legacy.text
                assert "submit_ceo_intent" in {t["name"] for t in legacy.json()["result"]["tools"]}
                assert (await rpc(client, reader, "/mcp/coo")).status_code in (401, 403)
                assert (await rpc(client, token, "/mcp")).status_code in (401, 403)
                current["binding"] = {"schema": BINDING_SCHEMA, "enabled": False, "binding": None}
                assert (await rpc(client, token, "/mcp/coo")).status_code in (401, 403)
    asyncio.run(exercise())


def test_signed_mcp_request_reaches_real_socket_and_one_durable_job(rsa_key, tmp_path):
    import dataclasses
    import tempfile
    import runpy
    from control_plane.executive_runtime import Runtime
    host_fixture = runpy.run_path(str(Path(__file__).with_name("test_executive_principal_ingress.py")))
    _, token, current, settings = fixture.setup(rsa_key, tmp_path)
    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-coo-api-", dir="/tmp") as directory:
            socket_root = Path(directory)
            host = host_fixture["service"](tmp_path, socket_root)
            base = dataclasses.replace(settings.executive, ceo_ingress_socket_path=socket_root / "principal.sock")
            selected = dataclasses.replace(settings, executive=base)
            app = server.build_web_ceo_v2_with_coo_mcp_app(base, coo_settings=selected, audit_sink=fixture.Sink())
            await host.start()
            try:
                async with app._app.router.lifespan_context(app._app):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                        async def call(tool, arguments):
                            response = await rpc(client, token, "/mcp/coo", "tools/call", {"name": tool, "arguments": arguments})
                            assert response.status_code == 200, response.text
                            return json.loads(response.json()["result"]["content"][0]["text"])
                        first = await call("submit_principal_intent", fixture.payload())
                        assert first["ok"] is True, first
                        assert first["receipt"]["principal"]["seat"] == "coo"
                        assert first["receipt"]["dispatched"] is False
                        duplicate = await call("submit_principal_intent", fixture.payload())
                        assert duplicate["receipt"]["duplicate"] is True
                        assert duplicate["receipt"]["job_id"] == first["receipt"]["job_id"]
                        host._ceo_ingress_app_binding = dataclasses.replace(host._ceo_ingress_app_binding, principal_admission_armed=False)
                        current["mission"] = None  # status must not reacquire current dynamic state
                        status = await call("principal_intent_status", {"request_ref": first["request_ref"], "work_ref": "WS:ONE"})
                        assert status["receipt"]["job_id"] == first["receipt"]["job_id"]
                        conflict = await call("submit_principal_intent", {**fixture.payload(), "objective": "Different semantic request"})
                        assert conflict["status"] == "operation_conflict"
                        jobs = Runtime.at(tmp_path / "runtime").jobs.list_jobs()
                        assert len(jobs) == 1 and jobs[0].attempt_count == 0
            finally:
                await host.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("path", ["/mcp/coo/", "/mcp/coo?x=1", "/mcp%2Fcoo", "/mcp/coo/extra"])
def test_coo_path_aliases_are_not_new_authority_routes(rsa_key, tmp_path, path):
    _, token, _, settings = fixture.setup(rsa_key, tmp_path)
    app = server.build_web_ceo_v2_with_coo_mcp_app(settings.executive,
        coo_settings=settings, audit_sink=fixture.Sink())
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response = await rpc(client, token, path)
                assert response.status_code == 404
    asyncio.run(exercise())


def test_duplicate_headers_are_refused_before_jwt_selection(rsa_key, tmp_path):
    _, token, _, settings = fixture.setup(rsa_key, tmp_path)
    app = server.build_web_ceo_v2_with_coo_mcp_app(settings.executive,
        coo_settings=settings, audit_sink=fixture.Sink())
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                result = await client.post("/mcp/coo", headers=[("authorization", "Bearer " + token),
                    ("authorization", "Bearer bad")], json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
                assert result.status_code == 401
    asyncio.run(exercise())


def test_shared_metadata_advertises_roles_without_changing_legacy_builder(rsa_key, tmp_path):
    _, token, _, settings = fixture.setup(rsa_key, tmp_path)
    app = server.build_web_ceo_v2_with_coo_mcp_app(settings.executive,
        coo_settings=settings, audit_sink=fixture.Sink())
    from urllib.parse import urlsplit
    path = urlsplit(settings.policy.resource_metadata_url).path
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response = await client.get(path)
                assert response.status_code == 200
                assert response.json()["resource"] == settings.policy.resource
                assert set(response.json()["scopes_supported"]) == {"mastermind.executive.read",
                    "mastermind.executive.intent.submit", "mastermind.executive.coo.act"}
                assert (await client.get(path + "?unexpected=1")).status_code == 404
    asyncio.run(exercise())


def test_metadata_cannot_shadow_static_coo_route(rsa_key, tmp_path):
    import dataclasses
    _, _, _, settings = fixture.setup(rsa_key, tmp_path)
    path = "https://executive-app.mastermind.example.test/mcp/coo"
    policies = fixture.AppPolicies(dataclasses.replace(settings.executive.policies.read, resource_metadata_url=path),
                                   dataclasses.replace(settings.executive.policies.submit, resource_metadata_url=path))
    base = dataclasses.replace(settings.executive, policies=policies)
    selected = dataclasses.replace(settings, executive=base, policy=dataclasses.replace(settings.policy, resource_metadata_url=path))
    with pytest.raises(ValueError, match="metadata"):
        server.build_web_ceo_v2_with_coo_mcp_app(base, coo_settings=selected, audit_sink=fixture.Sink())
