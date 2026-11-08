"""Outer session READ routing through the real Executive path fence.

The delegated inner ASGI owner is explicit; signed inner owner/socket/source
checks are retained separately. This test proves the previously missing route.
"""
import asyncio
import httpx
import pytest
from integrations.executive_mcp import server
from tests.test_executive_workspace_mount import Mount, settings, existing, rsa_key, short_socket_root


def test_session_read_reaches_existing_workspace_owner_through_actual_outer_fence(settings):
    owner = Mount()
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(), workspace_app=owner)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="https://mcp.mastermind-x.com") as client:
            query = "work_ref=WS%3ATEST&root_job_id=JOB-1"
            result = await client.get("/workspace/project-session/current?" + query)
            assert result.status_code == 200
            assert owner.calls == [("/workspace/project-session/current", query.encode())]
            for path, method in [("/workspace/project-session/current/", "GET"),
                                 ("/workspace%2Fproject-session/current", "GET"),
                                 ("/workspace/project-session/current", "POST")]:
                response = await client.request(method, path)
                assert response.status_code in (400, 403, 404)
            assert len(owner.calls) == 1
    asyncio.run(run())


@pytest.mark.parametrize("path,query", [
    ("/workspace/project-admission/current", "work_ref=WS%3ATEST&root_job_id=JOB-1"),
    ("/workspace/project-admission/operation", "work_ref=WS%3ATEST&kind=project_pause&command_id=mmos-project-pause-" + "a" * 40),
    ("/workspace/fabric/status/current", "work_ref=WS%3ATEST&root_job_id=JOB-1"),
    ("/workspace/project-plan/current", "work_ref=WS%3ATEST"),
    ("/workspace/project-direction/current", "work_ref=WS%3ATEST"),
    ("/workspace/resources/capacity/current", "work_ref=WS%3ATEST&root_job_id=JOB-1&job_id=JOB-2&attempt_id=ATTEMPT-1"),
])
def test_fixed_query_get_family_preserves_exact_query_for_existing_inner_owner(settings, path, query):
    owner = Mount()
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(), workspace_app=owner)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.mastermind-x.com") as client:
            result = await client.get(path + "?" + query)
            assert result.status_code == 200
            assert owner.calls == [(path, query.encode())]
            assert (await client.post(path)).status_code == 404
            assert len(owner.calls) == 1
    asyncio.run(run())


@pytest.mark.parametrize("path", ["/workspace/project-admission/pause", "/workspace/project-admission/resume"])
def test_fixed_action_family_remains_post_only_query_free_and_public_header_fenced(settings, path):
    owner = Mount()
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(), workspace_app=owner)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.mastermind-x.com") as client:
            result = await client.post(path, json={"explicit_inner_owner_fixture": True})
            assert result.status_code == 200 and owner.calls == [(path, b"")]
            for url, method, headers in [(path, "GET", {}), (path + "?x=1", "POST", {}),
                                          (path + "/", "POST", {}),
                                          (path, "POST", {"Origin": "https://unrelated.example"})]:
                response = await client.request(method, url, headers=headers)
                assert response.status_code in (400, 403, 404)
            assert len(owner.calls) == 1
    asyncio.run(run())


def test_catalogue_get_family_stays_query_free_and_absent_mount_stays_closed(settings):
    owner = Mount()
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(), workspace_app=owner)
    absent = server.build_executive_mcp_app(settings, audit_sink=existing.Sink())
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.mastermind-x.com") as client:
            path = "/workspace/fabric/catalog/current"
            assert (await client.get(path)).status_code == 200
            assert (await client.get(path + "?x=1")).status_code == 404
            assert (await client.post(path)).status_code == 404
            assert (await client.post("/workspace/project-admission/new-action")).status_code == 404
            assert owner.calls == [(path, b"")]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=absent), base_url="https://mcp.mastermind-x.com") as client:
            assert (await client.get("/workspace/project-session/current")).status_code == 404
            assert (await client.post("/workspace/project-admission/pause")).status_code == 404
    asyncio.run(run())
