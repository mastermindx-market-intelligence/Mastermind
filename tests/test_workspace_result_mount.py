"""Mount coverage for the v2 routes through the existing UID458 outer dispatcher.

This is a parent-owned unapplied test that exercises the
``build_executive_mcp_app`` route table, the path fence, and the duplicated
authorization guard — confirming both new routes are registered, GET-only,
public, and refuse before any cache/Runtime seam.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import test_executive_mcp_app_composition as existing
from test_executive_mcp_app_composition import settings, rsa_key, short_socket_root
from integrations.executive_mcp import server


class _Mount:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    async def __call__(self, scope, receive, send):
        self.calls.append((scope["path"], scope.get("query_string", b"")))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"owned mount"})


def test_v2_routes_present_through_uid458_dispatcher(settings):
    workspace = _Mount()
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(),
                                          workspace_app=workspace)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                      base_url="https://mcp.mastermind-x.com") as client:
            response = await client.get(
                "/workspace/result/current?work_ref=WS:AA1&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64)
            assert response.status_code == 200, response.text
            response = await client.get(
                "/workspace/mission/v3/current?work_ref=WS:AA1&root_job_id=JOB-1")
            assert response.status_code == 200, response.text
            assert any(call[0] == "/workspace/result/current" for call in workspace.calls)
            assert any(call[0] == "/workspace/mission/v3/current" for call in workspace.calls)
    asyncio.run(check())


def test_v2_routes_get_only_via_path_fence(settings):
    workspace = _Mount()
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(),
                                          workspace_app=workspace)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                      base_url="https://mcp.mastermind-x.com") as client:
            # POST / PUT / DELETE all refuse through the fence.
            for method in ("post", "put", "delete"):
                response = await client.request(method,
                    "/workspace/result/current?work_ref=WS:AA1&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64)
                assert response.status_code == 404, (method, response.status_code)
            # Trailing-slash / encoded-separator aliases refuse too.
            for url in ("/workspace/result/current/",
                         "/workspace%2Fresult/current",
                         "/workspace/mission/v3/current/"):
                response = await client.get(url)
                assert response.status_code == 404, (url, response.status_code)
    asyncio.run(check())


def test_v2_routes_duplicate_authorization_header_refuses(settings):
    workspace = _Mount()
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(),
                                          workspace_app=workspace)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                      base_url="https://mcp.mastermind-x.com") as client:
            headers = [("Authorization", "Bearer a"), ("Authorization", "Bearer b")]
            response = await client.get(
                "/workspace/result/current?work_ref=WS:AA1&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64,
                headers=headers)
            assert response.status_code in (400, 401), response.status_code
            assert all(call[0] != "/workspace/result/current" for call in workspace.calls)
    asyncio.run(check())


def test_absent_workspace_app_does_not_register_v2_routes(settings):
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink())
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                      base_url="https://mcp.mastermind-x.com") as client:
            response = await client.get(
                "/workspace/result/current?work_ref=WS:AA1&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64)
            assert response.status_code == 404
            response = await client.get("/workspace/mission/v3/current?work_ref=WS:AA1&root_job_id=JOB-1")
            assert response.status_code == 404
    asyncio.run(check())