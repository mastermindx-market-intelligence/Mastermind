"""Test-only paired bridge qualification. Real OAuth/ASGI, fixture private peer.

No real service socket, token, callback endpoint, provider or Runtime is used.
"""
from __future__ import annotations
import asyncio
import dataclasses
import json
from types import SimpleNamespace

import httpx
import pytest

import test_session_bridge_web_reply_event_asgi as events
from integrations.executive_mcp import server
from integrations.mastermind_executive_app.gateway import TRANSPORT_SENT_OK
from integrations.session_bridge.installed import (
    InstalledSessionBridgeClient, InstalledSessionBridgeProvider,
)
from integrations.session_bridge.reference_tools import NativeReplyReferencesTool
from integrations.session_bridge.return_tools import NativeReplyReadTool
from integrations.session_bridge.web_reply_event_rpc import WebReplyEventRpc

rsa_key = events.rsa_key
short_socket_root = events.short_socket_root
settings = events.settings


def compose(settings, *, foreign_reference=False, reader_enabled=True):
    frames = []
    def no_effect(*_args, **_kwargs):
        raise AssertionError("a read must not issue a session effect")
    provider = InstalledSessionBridgeProvider(
        target_projector=lambda *_args: [], reply_handler=no_effect,
        summon_handler=no_effect,
        reference_handler=lambda *_args: {
            "schema": "mastermind.session_reply_references.v1",
            "status": "COMPLETE", "references": [], "next_cursor": None,
            "high_water": 0,
        },
    )
    class PrivatePeer:
        async def send_frame(self, _socket, frame):
            frames.append(frame)
            return SimpleNamespace(transport=TRANSPORT_SENT_OK, ok=True,
                                   result=await provider.handle_frame(frame))
    client = InstalledSessionBridgeClient(
        "/private/tmp/paired-mcp-fixture-not-listening.sock", client=PrivatePeer())
    reference_client = InstalledSessionBridgeClient(
        "/private/tmp/foreign-paired-fixture-not-listening.sock", client=PrivatePeer()
    ) if foreign_reference else client
    owner = events.Owner()
    installed = dataclasses.replace(settings, read_from_ceo_ingress=True)
    async def no_mdm(**_kwargs):
        raise AssertionError("unrelated MDM invoked")
    app = server.build_web_ceo_v3_mcp_app(
        installed, audit_sink=events.host.Sink(),
        mdm_reader=SimpleNamespace(list_macos_devices=no_mdm, device=no_mdm),
        session_target_projector=client.targets,
        session_reply_handler=client.send, session_summon_handler=client.summon,
        session_reply_read_tool=NativeReplyReadTool(client) if reader_enabled else None,
        session_reply_references_tool=NativeReplyReferencesTool(reference_client),
        reply_event_rpc=WebReplyEventRpc(owner, clock=installed.clock),
        os_session_bridge_client=client,
        enable_os_executive_transport=True,
        os_executive_resource=installed.policies.submit.resource,
        os_app=__import__("test_mastermind_os_executive_transport")._assets(),
    )
    return app, owner, frames


def payload(response):
    value = response.json()["result"]
    return value.get("structuredContent") or json.loads(value["content"][0]["text"])


@pytest.mark.parametrize("protocol", ["2025-11-25", "2026-07-28"])
def test_history_and_events_coexist_on_one_authenticated_host(settings, rsa_key, protocol):
    app, owner, frames = compose(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://127.0.0.1") as client:
                token = events.auth._read_token(rsa_key)
                headers = {**events.wire(token), "mcp-protocol-version": protocol}
                listed = await client.post("/mcp", headers=headers,
                                           json=events.request("tools/list", {}))
                assert listed.status_code == 200, listed.text
                names = {item["name"] for item in listed.json()["result"]["tools"]}
                assert {"session_reply_read", "session_reply_references"} <= names
                result = await client.post("/mcp", headers=headers,
                    json=events.request("tools/call", {"name": "session_reply_references",
                        "arguments": {"work_ref": "WS:WORKSPACE-AGENT-PROGRAM"}}))
                assert result.status_code == 200, result.text
                assert payload(result)["data"] == {
                    "schema": "mastermind.session_reply_references.v1",
                    "status": "COMPLETE", "references": [], "next_cursor": None,
                    "high_water": 0,
                }
                assert [frame["tool"] for frame in frames] == ["session_reply_references"]
                discovered = await client.post("/mcp", headers=events.wire(token),
                    json=events.request("events/list", {}))
                assert discovered.status_code == 200, discovered.text
                assert discovered.json()["result"]["events"][0]["name"] == events.EVENT
                subscribed = await client.post("/mcp", headers=events.wire(token),
                    json=events.request("events/subscribe", events.subscription()))
                assert subscribed.status_code == 200, subscribed.text
                assert subscribed.json()["result"]["id"] == "sub_original001"
                assert len(owner.store) == 1
                assert [frame["tool"] for frame in frames] == ["session_reply_references"]
    asyncio.run(run())


@pytest.mark.parametrize("bad_scope", ["foreign-subject", "other-subject"])
def test_foreign_bearer_cannot_reach_either_owner(settings, rsa_key, bad_scope):
    app, owner, frames = compose(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://127.0.0.1") as client:
                token = events.auth._read_token(rsa_key, sub=bad_scope)
                for method, args in [
                    ("tools/call", {"name": "session_reply_references",
                                    "arguments": {"work_ref": "WS:WORKSPACE-AGENT-PROGRAM"}}),
                    ("events/subscribe", events.subscription()),
                ]:
                    result = await client.post("/mcp", headers=events.wire(token),
                                               json=events.request(method, args))
                    assert result.status_code in (401, 403), result.text
    asyncio.run(run())
    assert not frames and not owner.calls


def test_foreign_reference_client_refused_at_composition(settings):
    with pytest.raises(TypeError, match="reference discovery must share"):
        compose(settings, foreign_reference=True)


def test_events_still_require_original_reply_reader(settings):
    with pytest.raises(ValueError, match="original-reply reader"):
        compose(settings, reader_enabled=False)
