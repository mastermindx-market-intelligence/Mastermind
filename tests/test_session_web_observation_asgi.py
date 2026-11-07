"""Real authenticated MCP transport with synthetic, read-only owner ports.

These tests prove the optional host path, not enrolled browser or Hermes service
installation. No network listener is opened and no live browser is queried.
"""
from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

import test_executive_mcp_web_ceo_sessions as host
import test_mastermind_executive_app_asgi as auth
from test_session_web_observation import receipt, agentos, scope
from integrations.executive_mcp import server
from integrations.session_bridge.web_observation_tools import (
    CONTINUITY_TOOL, OBSERVE_TOOL, WebSessionReadTools,
)

rsa_key = host.rsa_key
short_socket_root = host.short_socket_root
settings = host.settings


def compose(settings, *, census=True, continuity=True, configured=True):
    calls = []
    owners, targets = host.Owners(), host.Projector()

    async def scopes(principal):
        calls.append(("scope", principal.subject_digest))
        policy = settings.policies.read
        if (principal.subject_digest not in policy.allowed_subject_digests
                or principal.resource != policy.resource):
            raise PermissionError("not this read owner")
        return scope()

    async def observations(principal, adapters):
        calls.append(("census", adapters))
        return [receipt()]

    async def context(principal, workstream):
        calls.append(("continuity", workstream))
        return agentos()

    async def unused(**kwargs):
        raise AssertionError("a session read cannot call MDM")

    reads = (WebSessionReadTools(scope_reader=scopes,
        census_reader=observations if census else None,
        continuity_reader=context if continuity else None,
        clock=lambda: datetime.fromtimestamp(settings.clock(), tz=timezone.utc))
        if configured else None)
    app = server.build_web_ceo_v3_mcp_app(
        dataclasses.replace(settings, read_from_ceo_ingress=True),
        audit_sink=host.Sink(),
        mdm_reader=SimpleNamespace(list_macos_devices=unused, device=unused),
        session_target_projector=targets, session_reply_handler=owners.reply,
        session_summon_handler=owners.summon, session_web_read_tools=reads,
    )
    return app, calls, owners, targets


@pytest.mark.parametrize("census,continuity", [(True, False), (False, True), (True, True)])
def test_optional_reads_are_independently_advertised(settings, rsa_key, census, continuity):
    app, calls, owners, targets = compose(settings, census=census, continuity=continuity)

    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://127.0.0.1") as client:
                response = await host.rpc(client, auth._read_token(rsa_key), "tools/list")
                assert response.status_code == 200
                tools = response.json()["result"]["tools"]
                names = {t["name"] for t in tools}
                assert (OBSERVE_TOOL in names) is census
                assert (CONTINUITY_TOOL in names) is continuity
                for tool in tools:
                    if tool["name"] in (OBSERVE_TOOL, CONTINUITY_TOOL):
                        assert tool["annotations"]["readOnlyHint"] is True
                        assert tool["annotations"]["destructiveHint"] is False
        assert calls == []
        assert owners.reply_calls == owners.summon_calls == targets.calls == []
    asyncio.run(run())


def test_default_off_preserves_existing_v3_tool_inventory(settings, rsa_key):
    app, calls, owners, targets = compose(settings, configured=False)

    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://127.0.0.1") as client:
                response = await host.rpc(client, auth._read_token(rsa_key), "tools/list")
                assert response.status_code == 200
                assert [t["name"] for t in response.json()["result"]["tools"]] == [
                    t.name for t in server.build_web_ceo_v3_tools()]
        assert calls == []
    asyncio.run(run())


def test_real_read_scope_returns_census_and_independent_continuity(settings, rsa_key):
    app, calls, owners, targets = compose(settings)

    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://127.0.0.1") as client:
                response, result = await host.call(client, auth._read_token(rsa_key),
                                                   OBSERVE_TOOL, {})
                assert response.status_code == 200 and result["ok"] is True
                assert result["data"]["account_history_coverage"] == "UNKNOWN"
                assert result["data"]["sources"][0]["rows"][0]["runtime_status"] == "UNKNOWN"
                response, continuity = await host.call(client, auth._read_token(rsa_key),
                    CONTINUITY_TOOL, {"workstream": "WS:TARGET"})
                assert response.status_code == 200 and continuity["ok"] is True
                assert continuity["data"]["continuity"]["agentos_source_sha"] == "e" * 40
                assert continuity["data"]["session_relationship"] == "UNVERIFIED"
                response, denied = await host.call(client, auth._read_token(rsa_key),
                    CONTINUITY_TOOL, {"workstream": "WS:PRIVATE"})
                assert response.status_code == 200 and denied["ok"] is False
                assert denied["error"]["code"] == "scope_refused" and denied["data"] is None
        assert not owners.reply_calls and not owners.summon_calls and not targets.calls
        assert ("continuity", "WS:PRIVATE") not in calls
    asyncio.run(run())


def test_missing_auth_reaches_no_owner(settings):
    app, calls, owners, targets = compose(settings)

    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://127.0.0.1") as client:
                response = await client.post("/mcp",
                    headers={"accept": "application/json, text/event-stream"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": OBSERVE_TOOL, "arguments": {}}})
                assert response.status_code == 401
        assert calls == []
        assert not owners.reply_calls and not owners.summon_calls and not targets.calls
    asyncio.run(run())


def test_read_permission_does_not_enable_send(settings, rsa_key):
    app, calls, owners, targets = compose(settings)

    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://127.0.0.1") as client:
                response, result = await host.call(client, auth._read_token(rsa_key),
                    "session_send", {"target_ref": "codex:BIND-1",
                        "instruction": "must not run", "stop_condition": "never",
                        "operation_key": "synthetic-no-send"})
                assert response.status_code in (200, 403)
                assert result.get("ok") is not True
        assert calls == []
        assert not owners.reply_calls and not owners.summon_calls and not targets.calls
    asyncio.run(run())
