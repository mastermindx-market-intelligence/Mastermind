"""Real OAuth/MCP ASGI + original-request owner adapter; fake persistent port.

Fixture-only: no external callback, production credential store, subscription
activation or ChatGPT Work/dot destination is used by this test.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from types import SimpleNamespace

import httpx

import test_executive_mcp_web_ceo_sessions as host
import test_mastermind_executive_app_asgi as auth
import test_session_bridge_web_reply_event_asgi as wire_fixture
from test_session_bridge_web_reply_subscription_owner import ExistingStore
from integrations.executive_mcp import server as executive
from integrations.session_bridge.web_reply_event_rpc import WebReplyEventRpc
from integrations.session_bridge.web_reply_subscription_owner import (
    OriginalReplyGrant,
    OriginalReplySubscriptionAdapter,
    VerifiedChallengeHTTP,
    owner_key,
)

settings=host.settings
rsa_key=host.rsa_key
short_socket_root=host.short_socket_root
NOW=auth.NOW


class CurrentOriginal:
    def __init__(self):
        self.calls=[]
        self.allowed=True
    async def resolve(self,principal,request_ref):
        self.calls.append((principal.subject_digest,request_ref))
        if not self.allowed or request_ref!="request-001":
            raise ValueError("unavailable original request")
        return OriginalReplyGrant(
            owner_key=owner_key(principal),request_ref=request_ref,
            read_ref="native-return-read-001",revision="incumbent-session-generation-001",
            access_current=True,expires_at=NOW+1800,
        )


class SignedChallengeFixture:
    def __init__(self):
        self.calls=[]
    async def verify(self,url,packet):
        self.calls.append((url,packet))
        challenge=json.loads(packet.body)["challenge"]
        return VerifiedChallengeHTTP(
            status_code=200,
            response_body=json.dumps({"challenge":challenge}).encode(),
        )


def build(settings):
    installed=dataclasses.replace(settings,read_from_ceo_ingress=True)
    original=CurrentOriginal()
    store=ExistingStore()
    callback=SignedChallengeFixture()
    owner=OriginalReplySubscriptionAdapter(
        resolver=original,storage=store,challenge_sender=callback,
        clock=lambda:NOW,enabled=True,
    )
    rpc=WebReplyEventRpc(owner,clock=lambda:NOW)
    from test_session_bridge_return_tools import tool as canonical_reader
    reader,_=canonical_reader()
    existing=host.Owners()
    async def unused(**kw):raise AssertionError("unrelated MDM reader used")
    app=executive.build_web_ceo_v3_mcp_app(
        installed,audit_sink=host.Sink(),
        mdm_reader=SimpleNamespace(list_macos_devices=unused,device=unused),
        session_target_projector=host.Projector(),
        session_reply_handler=existing.reply,
        session_summon_handler=existing.summon,
        session_reply_read_tool=reader,reply_event_rpc=rpc,
    )
    return app,original,store,callback


def test_verified_bearer_original_request_end_to_end_subscription_refresh_unsubscribe(settings,rsa_key):
    app,original,store,callback=build(settings)
    async def sequence():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url="http://127.0.0.1") as client:
                token=auth._read_token(rsa_key)
                assert token
                header=wire_fixture.wire(token)
                discover=await client.post("/mcp",headers=header,
                                           json=wire_fixture.request("server/discover",{}))
                assert discover.status_code==200 and discover.json()["result"]["capabilities"]["events"]=={}
                params=wire_fixture.subscription()
                first=await client.post("/mcp",headers=header,
                                        json=wire_fixture.request("events/subscribe",params))
                assert first.status_code==200,first.text
                first_id=first.json()["result"]["id"]
                assert first_id.startswith("sub_")
                assert len(callback.calls)==1 and len(store.rows)==1
                assert "whsec_" not in first.text
                assert json.loads(callback.calls[0][1].body)["type"]=="verification"
                repeat=await client.post("/mcp",headers=header,
                                         json=wire_fixture.request("events/subscribe",params))
                assert repeat.json()["result"]["id"]==first_id
                assert len(callback.calls)==1 and len(store.rows)==1
                assert [x[0] for x in store.calls].count("commit")==1
                original.allowed=False
                denied=await client.post("/mcp",headers=header,
                                         json=wire_fixture.request("events/subscribe",params))
                assert denied.json()["error"]["code"]==-32010
                assert len(callback.calls)==1
                original.allowed=True
                unsub={k:v for k,v in params.items() if k!="cursor"}
                unsub["delivery"]={"mode":"webhook","url":params["delivery"]["url"]}
                stop=await client.post("/mcp",headers=header,
                                       json=wire_fixture.request("events/unsubscribe",unsub))
                assert stop.json()["result"]=={}
                assert not store.rows and [x[0] for x in store.calls].count("remove")==1
    asyncio.run(sequence())
    assert len(original.calls)>=5


def test_authenticated_but_foreign_request_never_verifies_callback_or_commits(settings,rsa_key):
    app,original,store,callback=build(settings)
    async def sequence():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                        base_url="http://127.0.0.1") as client:
                params=wire_fixture.subscription()
                params["arguments"]={"request_ref":"request-not-owned"}
                response=await client.post("/mcp",
                    headers=wire_fixture.wire(auth._read_token(rsa_key)),
                    json=wire_fixture.request("events/subscribe",params))
                assert response.json()["error"]["code"]==-32010
                assert not callback.calls and not store.rows
    asyncio.run(sequence())
