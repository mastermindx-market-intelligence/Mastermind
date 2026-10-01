"""Authenticated Web-CEO composition for Session Bridge tools."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import httpx

from integrations.executive_mcp import server as transport
from integrations.session_bridge.gateway import SessionBridgeGateway
from tests import test_executive_mcp_web_ceo_app as old

rsa_key = old.rsa_key
short_socket_root = old.short_socket_root
settings = old.settings


class Calls:
    def __init__(self):
        self.values = []

    def read(self, kind):
        self.values.append(("read", kind))
        return [{"target_ref": "codex:binding-1"}]

    def send(self, *args):
        self.values.append(("send", args))
        return {"reply_committed": True, "action": "POSTED"}

    def summon(self, args):
        self.values.append(("summon", dict(args)))
        return {"accepted": True, "dispatched": False}


@asynccontextmanager
async def connection(settings, calls):
    gateway = SessionBridgeGateway(
        target_reader=calls.read,
        reply_sender=calls.send,
        summoner=calls.summon,
    )
    app = transport.build_web_ceo_session_mcp_app(
        settings,
        audit_sink=old.Sink(),
        session_gateway=gateway,
    )
    async with app._app.router.lifespan_context(app._app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
        ) as client:
            yield client


def run(value):
    return asyncio.run(value)


def test_session_profile_is_static_and_read_scope_cannot_modify(settings, rsa_key):
    async def exercise():
        calls = Calls()
        async with connection(settings, calls) as client:
            listed = await old.rpc(client, old.fixture._read_token(rsa_key), "tools/list")
            names = {tool["name"] for tool in listed["tools"]}
            assert {"session_targets", "session_send", "session_summon"} <= names

            _, targets = await old.call(
                client, old.fixture._read_token(rsa_key), "session_targets", {}
            )
            assert targets["ok"] is True
            assert calls.values == [("read", None)]

            for name, arguments in (
                ("session_send", {
                    "target_ref": "codex:binding-1",
                    "instruction": "Continue one bounded task.",
                    "stop_condition": "Stop after one result.",
                    "operation_key": "session-auth-read-refuse-001",
                }),
                ("session_summon", {
                    "objective": "Inspect one bounded issue.",
                    "execution_profile": "research_only",
                    "operation_key": "session-auth-read-refuse-002",
                }),
            ):
                reply, payload = await old.call(
                    client, old.fixture._read_token(rsa_key), name, arguments
                )
                assert reply["isError"] is True
                assert payload["error"]["code"] == "scope_refused"
            assert calls.values == [("read", None)]

    run(exercise())


def test_submit_scope_enters_exact_session_handlers(settings, rsa_key):
    async def exercise():
        calls = Calls()
        token = old.fixture._submit_token(rsa_key)
        async with connection(settings, calls) as client:
            _, send = await old.call(client, token, "session_send", {
                "target_ref": "codex:binding-1",
                "instruction": "Continue one bounded task.",
                "stop_condition": "Stop after one result.",
                "operation_key": "session-auth-submit-001",
            })
            assert send["ok"] is True
            _, summon = await old.call(client, token, "session_summon", {
                "objective": "Inspect one bounded issue.",
                "execution_profile": "research_only",
                "operation_key": "session-auth-submit-002",
            })
            assert summon["ok"] is True
        assert [item[0] for item in calls.values] == ["send", "summon"]

    run(exercise())


def test_standalone_session_bridge_network_edge_is_refused():
    from integrations.session_bridge import server

    gateway = SessionBridgeGateway(
        target_reader=lambda _kind: [],
        reply_sender=lambda *_: None,
        summoner=lambda _args: None,
    )
    try:
        server.build_mcp_server(gateway)
    except RuntimeError as exc:
        assert "authenticated Executive MCP host" in str(exc)
    else:
        raise AssertionError("standalone unauthenticated bridge must be refused")
