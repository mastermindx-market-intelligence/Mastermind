"""Authenticated Web-CEO Executive MCP profile composition."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import dataclasses
import json
import os
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
finally:
    sys.path.pop(0)

from control_plane.executive_service import (
    CEO_WEB_CEO_READ_SCHEMA,
    CeoIngressAppBinding,
    ExecutiveControlService,
)
from integrations.executive_mcp import server as transport
from integrations.executive_mcp.web_ceo import WebCeoInstalledExecutiveReaders

rsa_key = fixture.rsa_key
short_socket_root = fixture.short_socket_root

PAYLOAD = {
    "operation_key": "web-ceo-fabric-canary-001",
    "objective": "Prove the versioned Web CEO can inspect its admitted Fabric root.",
    "department": "executive-infrastructure",
    "priority": 5,
    "execution_profile": "research_only",
}


class Sink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


@pytest.fixture
def settings(rsa_key, tmp_path, short_socket_root):
    mastermind = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    fixture._git_repo(mastermind)
    (macro / "scripts").mkdir(parents=True)
    (macro / "scripts" / "agentos.py").write_text("")
    (macro / "agentos").mkdir()
    fixture._git_repo(macro)
    return fixture._real_app_settings(
        rsa_key,
        mastermind_root=mastermind,
        macro_root=macro,
        ceo_ingress_socket_path=short_socket_root / "ceo-ingress.sock",
    )


@asynccontextmanager
async def connection(settings):
    app = transport.build_web_ceo_mcp_app(settings, audit_sink=Sink())
    async with app._app.router.lifespan_context(app._app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
        ) as client:
            yield client


def headers(token):
    return {
        "authorization": f"Bearer {token}",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18",
    }


async def rpc(client, token, method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        request["params"] = params
    response = await client.post("/mcp", headers=headers(token), json=request)
    assert response.status_code == 200, response.text
    assert "error" not in response.json(), response.text
    return response.json()["result"]


async def call(client, token, name, arguments):
    result = await rpc(
        client,
        token,
        "tools/call",
        {"name": name, "arguments": arguments},
    )
    return result, json.loads(result["content"][0]["text"])


def test_legacy_and_web_ceo_builders_have_distinct_static_surfaces(
    settings, rsa_key
):
    async def exercise():
        legacy = transport.build_executive_mcp_app(settings, audit_sink=Sink())
        web = transport.build_web_ceo_mcp_app(settings, audit_sink=Sink())
        try:
            async with legacy._app.router.lifespan_context(legacy._app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=legacy),
                    base_url="http://127.0.0.1",
                ) as client:
                    listed = await rpc(
                        client, fixture._read_token(rsa_key), "tools/list"
                    )
                    assert {t["name"] for t in listed["tools"]} == {
                        "executive_state",
                        "executive_inbox",
                        "executive_job",
                        "ceo_intent_status",
                        "submit_ceo_intent",
                    }
            async with web._app.router.lifespan_context(web._app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=web),
                    base_url="http://127.0.0.1",
                ) as client:
                    listed = await rpc(
                        client, fixture._read_token(rsa_key), "tools/list"
                    )
                    assert {t["name"] for t in listed["tools"]} == {
                        "executive_state",
                        "executive_inbox",
                        "executive_job",
                        "executive_fabric",
                        "ceo_intent_status",
                        "submit_ceo_intent",
                    }
        finally:
            pass

    asyncio.run(exercise())


def test_authenticated_web_ceo_reads_its_admitted_fabric_root(
    settings, rsa_key, tmp_path, short_socket_root
):
    async def exercise():
        base_service = fixture._real_service(
            tmp_path,
            socket_root=short_socket_root,
            mastermind_root=Path(settings.mastermind_root),
            macro_root=Path(settings.macro_root_flag),
        )
        readers = WebCeoInstalledExecutiveReaders(
            repo_root=Path(settings.mastermind_root),
            macro_root=Path(settings.macro_root_flag),
            runtime_root=base_service.config.runtime_root,
        )
        service = ExecutiveControlService(
            base_service.config,
            supervisor_factory=lambda runtime: fixture._NoExecutionSupervisor(),
            ceo_ingress_socket_path=settings.ceo_ingress_socket_path,
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=readers,
            ceo_ingress_armed=False,
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(),
                armed=True,
                grounding_provider=readers,
                read_provider=readers,
                read_schema=CEO_WEB_CEO_READ_SCHEMA,
            ),
        )
        await service.start()
        try:
            bound = dataclasses.replace(
                settings,
                read_from_ceo_ingress=True,
                mastermind_root=tmp_path / "no-network-process-checkout",
                macro_root_flag=None,
            )
            async with connection(bound) as client:
                token = fixture._submit_token(rsa_key)
                _, submitted = await call(
                    client, token, "submit_ceo_intent", PAYLOAD
                )
                assert submitted["status"] == "accepted", submitted
                job_id = submitted["receipt"]["job_id"]
                assert submitted["receipt"]["dispatched"] is False

                _, fabric = await call(
                    client,
                    token,
                    "executive_fabric",
                    {"view": "root", "root_job_id": job_id},
                )
                assert fabric["ok"] is True, fabric
                assert fabric["server_version"] == "1.1.0"
                assert fabric["data"]["schema"] == "mastermind.fabric_job_view.v1"
                assert fabric["data"]["root"]["job_id"] == job_id
                assert (
                    fabric["data"]["runtime"]["root"]
                    == "readonly:installed-executive-runtime"
                )
                assert str(base_service.config.runtime_root) not in json.dumps(
                    fabric, sort_keys=True
                )
                assert service.runtime.attempts.list_attempts() == []
                assert service.runtime.workers.list_workers() == []
        finally:
            await service.close()
            await readers.aclose()

    asyncio.run(exercise())
