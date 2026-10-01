"""Authenticated Session Bridge composition through the existing Executive MCP host."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
finally:
    sys.path.pop(0)

from integrations.executive_mcp import server as transport
from integrations.executive_mcp.web_ceo_sessions import (
    WEB_CEO_SESSIONS_SERVER_VERSION,
    web_ceo_sessions_tool_names,
)
from integrations.session_bridge.server import build_mcp_server as build_legacy_bridge_server

rsa_key = fixture.rsa_key
short_socket_root = fixture.short_socket_root


class Sink:
    def __init__(self): self.events = []
    def emit(self, event): self.events.append(event)


@pytest.fixture
def settings(rsa_key, tmp_path, short_socket_root):
    mastermind = tmp_path / "mastermind"; macro = tmp_path / "macro"
    fixture._git_repo(mastermind)
    (macro / "scripts").mkdir(parents=True)
    (macro / "scripts" / "agentos.py").write_text("")
    (macro / "agentos").mkdir(); (macro / "agentos" / ".keep").write_text("")
    fixture._git_repo(macro)
    return fixture._real_app_settings(
        rsa_key, mastermind_root=mastermind, macro_root=macro,
        ceo_ingress_socket_path=short_socket_root / "ceo-ingress.sock",
    )


def headers(token):
    return {
        "authorization": f"Bearer {token}",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18",
    }


async def rpc(client, token, method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None: request["params"] = params
    return await client.post("/mcp", headers=headers(token), json=request)


async def call(client, token, name, arguments):
    response = await rpc(client, token, "tools/call", {"name": name, "arguments": arguments})
    body = response.json()
    if response.status_code != 200 or "result" not in body:
        return response, body
    result = body["result"]
    return response, json.loads(result["content"][0]["text"])


class Owners:
    def __init__(self): self.reply_calls = []; self.summon_calls = []
    async def reply(self, principal, arguments):
        self.reply_calls.append((principal.subject_digest, dict(arguments)))
        return {"reply_committed": True, "target_ref": arguments["target_ref"]}
    async def summon(self, principal, arguments):
        self.summon_calls.append((principal.subject_digest, dict(arguments)))
        return {"admission_requested": True, "operation_key": arguments["operation_key"]}


class Projector:
    def __init__(self): self.calls = []
    async def __call__(self, principal, kind):
        self.calls.append((principal.subject_digest, kind))
        rows = [
            {"target_ref": "codex:BIND-1", "kind": "codex", "generation": 3},
            {"target_ref": "claude:SESSION-1", "kind": "claude", "generation": 4},
        ]
        return [row for row in rows if kind is None or row["kind"] == kind]


async def app_client(settings, owners, projector):
    app = transport.build_web_ceo_sessions_mcp_app(
        settings, audit_sink=Sink(), session_target_projector=projector,
        session_reply_handler=owners.reply, session_summon_handler=owners.summon,
    )
    return app


def test_standalone_bridge_server_is_disabled():
    with pytest.raises(RuntimeError, match="authenticated Executive MCP host"):
        build_legacy_bridge_server(object())


def test_profile_lists_bridge_tools_without_changing_prior_profiles(settings, rsa_key):
    async def run():
        owners, projector = Owners(), Projector()
        app = await app_client(settings, owners, projector)
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response = await rpc(client, fixture._read_token(rsa_key), "tools/list")
                assert response.status_code == 200, response.text
                names = tuple(tool["name"] for tool in response.json()["result"]["tools"])
                assert names == web_ceo_sessions_tool_names()
                assert {"session_targets", "session_send", "session_summon"} <= set(names)
                versions = {tool["name"]: tool.get("securitySchemes") for tool in response.json()["result"]["tools"]}
                assert versions["session_targets"] != versions["session_send"]
        assert not owners.reply_calls and not owners.summon_calls and not projector.calls
    asyncio.run(run())


def test_read_scope_can_list_targets_but_cannot_send(settings, rsa_key):
    async def run():
        owners, projector = Owners(), Projector()
        app = await app_client(settings, owners, projector)
        token = fixture._read_token(rsa_key)
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response, payload = await call(client, token, "session_targets", {"kind": "codex"})
                assert response.status_code == 200 and payload["ok"] is True, payload
                assert payload["server_version"] == "0.2.0"
                assert payload["data"] == [{"target_ref": "codex:BIND-1", "kind": "codex", "generation": 3}]
                response, _payload = await call(client, token, "session_send", {
                    "target_ref": "codex:BIND-1", "instruction": "continue",
                    "stop_condition": "return result", "operation_key": "bridge-auth-1",
                })
                assert response.status_code == 200
                result = response.json()["result"]
                assert result["isError"] is True
                assert "mcp/www_authenticate" in result.get("_meta", {})
        assert owners.reply_calls == [] and owners.summon_calls == []
        assert len(projector.calls) == 1
    asyncio.run(run())


def test_submit_scope_can_send_only_to_trusted_projection(settings, rsa_key):
    async def run():
        owners, projector = Owners(), Projector()
        app = await app_client(settings, owners, projector)
        token = fixture._submit_token(rsa_key)
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                _response, denied = await call(client, token, "session_send", {
                    "target_ref": "codex:NOT-PROJECTED", "instruction": "continue",
                    "stop_condition": "return result", "operation_key": "bridge-auth-2",
                })
                assert denied["ok"] is False and denied["error"]["code"] == "authority_refused"
                assert owners.reply_calls == [] and owners.summon_calls == []
                _response, allowed = await call(client, token, "session_send", {
                    "target_ref": "codex:BIND-1", "instruction": "continue",
                    "stop_condition": "return result", "operation_key": "bridge-auth-3",
                })
                assert allowed["ok"] is True, allowed
                _response, summoned = await call(client, token, "session_summon", {
                    "objective": "bounded task", "execution_profile": "research_only",
                    "operation_key": "bridge-auth-5",
                })
                assert summoned["ok"] is True, summoned
        assert len(owners.reply_calls) == 1
        assert owners.reply_calls[0][1] == {
            "target_ref": "codex:BIND-1", "instruction": "continue",
            "stop_condition": "return result", "operation_key": "bridge-auth-3",
        }
        assert [kind for _principal, kind in projector.calls] == ["codex", "codex"]
        # Admission receives the same verified principal directly; no model field can impersonate it.
        assert len(owners.summon_calls) == 1
        assert owners.summon_calls[0][1]["operation_key"] == "bridge-auth-5"
        assert owners.summon_calls[0][0] == owners.reply_calls[0][0]
    asyncio.run(run())


@pytest.mark.parametrize("mutation", ["wrong_issuer", "wrong_resource", "duplicate_authorization"])
def test_auth_refusal_happens_before_bridge_backend(settings, rsa_key, mutation):
    async def run():
        owners, projector = Owners(), Projector()
        app = await app_client(settings, owners, projector)
        token = fixture._submit_token(rsa_key)
        if mutation == "wrong_issuer": token = fixture._submit_token(rsa_key, iss="https://issuer.invalid/")
        if mutation == "wrong_resource": token = fixture._submit_token(rsa_key, aud="https://resource.invalid/")
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "session_summon", "arguments": {
                "objective": "bounded task", "execution_profile": "research_only", "operation_key": "bridge-auth-4"
            }}}
        base = [("accept", "application/json, text/event-stream"), ("mcp-protocol-version", "2025-06-18")]
        auth = [("authorization", f"Bearer {token}")]
        if mutation == "duplicate_authorization": auth.append(("authorization", f"Bearer {token}"))
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response = await client.post("/mcp", headers=base + auth, json=request)
                assert response.status_code in (200, 401, 403), response.text
                if response.status_code == 200:
                    assert response.json()["result"]["isError"] is True
        assert owners.reply_calls == [] and owners.summon_calls == [] and projector.calls == []
    asyncio.run(run())
