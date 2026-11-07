"""Authenticated same-/mcp MCP Events adapter, opt-in only. No external HTTP."""
from __future__ import annotations
import asyncio
import dataclasses
import json
from types import SimpleNamespace

import httpx
import pytest

import test_executive_mcp_web_ceo_sessions as host
import test_mastermind_executive_app_asgi as auth
from integrations.executive_mcp import server as executive
from integrations.session_bridge.web_reply_event_rpc import (
    WebReplyEventRpc, EventSubscriptionReceipt, EventUnsubscribeReceipt,
)

rsa_key = host.rsa_key
short_socket_root = host.short_socket_root
settings = host.settings

NOW = auth.NOW
SECRET = "whsec_" + __import__("base64").b64encode(b"s"*32).decode()
URL = "https://receiver.example.com/mcp-events/callback_123"
EVENT = "session.reply_committed"


class Owner:
    def __init__(self):
        self.calls = []
        self.store = {}

    async def can_discover(self,principal):
        self.calls.append(("list",principal.subject_digest))
        return True

    async def subscribe(self,principal,requested):
        self.calls.append(("subscribe",principal.subject_digest,requested.request_ref))
        if requested.request_ref != "request-001":
            raise RuntimeError("unauthorized original request")
        self.store[(principal.subject_digest,requested.request_ref,requested.callback_url)] = True
        return EventSubscriptionReceipt("sub_original001",NOW+1800,True,True,True)

    async def unsubscribe(self,principal,requested):
        self.calls.append(("unsubscribe",principal.subject_digest,requested.request_ref))
        self.store.pop((principal.subject_digest,requested.request_ref,requested.callback_url),None)
        return EventUnsubscribeReceipt(True,True)


def mkapp(settings):
    installed=dataclasses.replace(settings, read_from_ceo_ingress=True)
    async def unused(**kw):
        raise AssertionError("no MDM reader must be called")
    owner=Owner()
    rpc=WebReplyEventRpc(owner,clock=installed.clock)
    from test_session_bridge_return_tools import tool as canonical_read_tool
    reply_reader, _ = canonical_read_tool()
    orchestrator=host.Owners()
    app=executive.build_web_ceo_v3_mcp_app(
        installed, audit_sink=host.Sink(),
        mdm_reader=SimpleNamespace(list_macos_devices=unused,device=unused),
        session_target_projector=host.Projector(),
        session_reply_handler=orchestrator.reply,
        session_summon_handler=orchestrator.summon,
        session_reply_read_tool=reply_reader,
        reply_event_rpc=rpc,
    )
    return app,owner


def wire(token):
    return {
        "authorization":"Bearer "+token,
        "accept":"application/json, text/event-stream",
        "content-type":"application/json",
        "mcp-protocol-version":"2026-07-28",
    }


def request(method,params=None):
    result={"jsonrpc":"2.0","id":2,"method":method}
    if params is not None:result["params"]=params
    return result


def subscription():
    return {"name":EVENT,"arguments":{"request_ref":"request-001"},
            "delivery":{"mode":"webhook","url":URL,"secret":SECRET},
            "cursor":None}


def test_installed_host_default_has_no_event_parameter_or_protocol_claim(settings,rsa_key):
    installed=dataclasses.replace(settings,read_from_ceo_ingress=True)
    async def unused(**kw): raise AssertionError
    app=executive.build_web_ceo_v3_mcp_app(installed, audit_sink=host.Sink(),
        mdm_reader=SimpleNamespace(list_macos_devices=unused,device=unused),
        session_target_projector=host.Projector(),
        session_reply_handler=host.Owners().reply,
        session_summon_handler=host.Owners().summon)
    # No installed default opt-in or session data store appears.
    assert app is not None


def test_real_bearer_mcp_endpoint_routes_events_and_preserves_legacy_tools(settings,rsa_key):
    app,owner=mkapp(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
                token=auth._read_token(rsa_key)
                listed=await client.post("/mcp",headers=wire(token),json=request("events/list",{}))
                assert listed.status_code==200,listed.text
                assert listed.json()["result"]["events"][0]["name"]==EVENT
                assert len(owner.calls)==1
                added=await client.post("/mcp",headers=wire(token),json=request("events/subscribe",subscription()))
                assert added.status_code==200,added.text
                assert added.json()["result"]["id"]=="sub_original001"
                assert added.json()["result"]["cursor"] is None
                assert "whsec_" not in added.text
                assert len(owner.store)==1
                unsub={key:value for key,value in subscription().items() if key!="cursor"}
                unsub["delivery"]={"mode":"webhook","url":URL}
                dropped=await client.post("/mcp",headers=wire(token),json=request("events/unsubscribe",unsub))
                assert dropped.status_code==200 and dropped.json()["result"]=={}
                assert not owner.store
                legacy=await host.rpc(client, token, "tools/list")
                assert legacy.status_code==200 and "tools" in legacy.json()["result"]
                modern=await client.post("/mcp",headers=wire(token),json=request("tools/list",{}))
                assert modern.status_code==200 and "tools" in modern.json()["result"]
    asyncio.run(run())


@pytest.mark.parametrize("changes",[
    {"iss":"https://foreign.example.test/"},
    {"aud":"https://foreign.example.test/mcp"},
    {"sub":"foreign-subject"},
    {"exp":auth.NOW-1},
])
def test_bad_bearer_does_not_reach_owner(settings,rsa_key,changes):
    app,owner=mkapp(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
                response=await client.post("/mcp",headers=wire(auth._read_token(rsa_key,**changes)),
                                           json=request("events/subscribe",subscription()))
                assert response.status_code in (401,403),response.text
    asyncio.run(run())
    assert not owner.calls


def test_wrong_protocol_version_and_direct_rpc_actor_injection_refused(settings,rsa_key):
    app,owner=mkapp(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
                token=auth._read_token(rsa_key)
                bad={**wire(token),"mcp-protocol-version":"2025-06-18"}
                denied=await client.post("/mcp",headers=bad,json=request("events/subscribe",subscription()))
                assert denied.json()["error"]["code"]==-32600
                forged=request("events/subscribe",subscription())
                forged["actor"]={"scopes":["mastermind.executive.read"]}
                denied=await client.post("/mcp",headers=wire(token),json=forged)
                assert denied.json()["error"]["code"]==-32600
                assert not owner.store
    asyncio.run(run())


def test_malformed_duplicate_rpc_method_never_dispatches_owner_or_legacy_tool(settings,rsa_key):
    app,owner=mkapp(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://127.0.0.1") as client:
                token=auth._read_token(rsa_key)
                raw=b'{"jsonrpc":"2.0","id":2,"method":"events/subscribe","method":"tools/call","params":{"name":"session_summon","arguments":{}}}'
                denied=await client.post("/mcp",headers=wire(token),content=raw)
                assert denied.json()["error"]["code"]==-32600
    asyncio.run(run())
    assert not owner.calls


def test_mcp2_discovery_advertises_events_only_on_explicit_authenticated_host(settings,rsa_key):
    app,owner=mkapp(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url="http://127.0.0.1") as client:
                token=auth._read_token(rsa_key)
                found=await client.post("/mcp",headers=wire(token),
                                        json=request("server/discover",{}))
                assert found.status_code==200,found.text
                payload=found.json()["result"]
                assert payload["resultType"]=="complete"
                assert payload["supportedVersions"]==["2026-07-28"]
                assert payload["capabilities"]=={"tools":{},"events":{}}
                assert owner.calls and owner.calls[-1][0]=="list"
    asyncio.run(run())


def test_mcp2_tools_call_routes_through_identical_existing_executive_policy(settings,rsa_key):
    app,owner=mkapp(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url="http://127.0.0.1") as client:
                token=auth._read_token(rsa_key)
                args={"name":"session_reply_read","arguments":{"read_ref":"unavailable-ref"}}
                legacy=await host.rpc(client,token,"tools/call",args)
                modern=await client.post("/mcp",headers=wire(token),json=request("tools/call",args))
                assert modern.status_code==200,modern.text
                assert legacy.status_code==200
                assert modern.json()["result"]==legacy.json()["result"]
                assert not any(x[0]=="subscribe" for x in owner.calls)
    asyncio.run(run())


def test_mcp2_cannot_upgrade_to_submit_scope_or_enable_callback_from_tool_body(settings,rsa_key):
    app,owner=mkapp(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url="http://127.0.0.1") as client:
                token=auth._read_token(rsa_key)
                req=request("tools/call",{"name":"session_reply_read","arguments":{
                    "read_ref":"unavailable-ref","callback_url":"https://foreign.example/hook"
                }})
                result=await client.post("/mcp",headers=wire(token),json=req)
                assert result.status_code==200
                body=json.dumps(result.json())
                assert "callback_url" not in body
                assert "isError" in body or "error" in body
                assert not owner.store
    asyncio.run(run())


@pytest.mark.parametrize("method", [[], {"name":"events/subscribe"}, 123, True])
def test_malformed_method_never_500_or_dispatch_original_owner(settings, rsa_key, method):
    app, owner = mkapp(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://127.0.0.1") as client:
                result=await client.post("/mcp",
                    headers=wire(auth._read_token(rsa_key)),
                    json={"jsonrpc":"2.0","id":2,"method":method,
                          "params":subscription()})
                assert result.status_code in (200,400),result.text
                assert "error" in result.json(),result.text
                assert "server-error" not in result.text
    asyncio.run(run())
    assert not owner.calls


def test_modern_read_scoped_token_cannot_invoke_original_submit(settings, rsa_key):
    app,owner=mkapp(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url="http://127.0.0.1") as client:
                token=auth._read_token(rsa_key)
                args={"name":"session_summon","arguments":{
                    "operation_key":"cross-client-read-scope-deny-001",
                    "objective":"Do not create a Job from a read scope",
                    "department":"executive-infrastructure",
                    "priority":0,"execution_profile":"research_only",
                    "workstream":"WS:EXECUTIVE-CAPACITY-FABRIC"
                }}
                response=await client.post("/mcp",headers=wire(token),
                                           json=request("tools/call",args))
                assert response.status_code==200,response.text
                body=response.json()
                assert body.get("error") or body["result"].get("isError")
    asyncio.run(run())
    assert not owner.store


def test_modern_duplicate_authorization_is_refused_before_owner(settings,rsa_key):
    app, owner=mkapp(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url="http://127.0.0.1") as client:
                token=auth._read_token(rsa_key)
                headers=[("authorization","Bearer "+token),
                         ("authorization","Bearer "+token),
                         ("mcp-protocol-version","2026-07-28"),
                         ("accept","application/json, text/event-stream")]
                response=await client.post("/mcp",headers=headers,
                                           json=request("events/subscribe",subscription()))
                assert response.status_code==401,response.text
    asyncio.run(run())
    assert not owner.calls
