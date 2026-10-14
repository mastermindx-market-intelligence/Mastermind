"""Full V3/COO wrappers, signed JWTs and an injected private peer only.

These checks cover the new composition boundary. They reuse the accepted
leaf's fixtures, without rerunning or changing its accepted behavioral suite.
No installed files, live sockets, provider, grant, or Runtime are contacted.
"""
import asyncio
import dataclasses
import json

import pytest

from tests import test_mastermind_os_session_transport as leaf
from tests import test_mastermind_os_executive_transport as launch
from integrations.executive_mcp import server
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.session_bridge.installed import InstalledSessionBridgeClient
from integrations.session_bridge.return_tools import NativeReplyReadTool

rsa_key = leaf.rsa_key
short_socket_root = launch.short_socket_root
settings = launch.settings
RESOURCE = "https://mcp.mastermind-x.com/os/executive"


def coo_settings(settings):
    from integrations.mastermind_executive_app.coo import CooAppSettings
    from integrations.mastermind_executive_app.coo_binding import COO_SCOPES, BINDING_SCHEMA
    policy = dataclasses.replace(settings.policies.read, policy_id="test-coo",
                                 required_scopes=COO_SCOPES)
    return CooAppSettings(settings, policy,
                         lambda: {"schema": BINDING_SCHEMA, "enabled": False, "binding": None},
                         lambda *_: {}, lambda *_: {})


def build(settings, *, coo=False, enabled=True, supply=True, change=lambda kw: None):
    peer, audit = leaf.Peer(), leaf.Audit()
    bridge = InstalledSessionBridgeClient("/no-live-session-test.sock", client=peer)
    kwargs = dict(audit_sink=audit, mdm_reader=launch.FixedMdm(),
                  session_target_projector=bridge.targets, session_reply_handler=bridge.send,
                  session_summon_handler=bridge.summon,
                  session_reply_read_tool=NativeReplyReadTool(bridge),
                  os_app=launch._assets(), enable_os_executive_transport=enabled,
                  os_executive_resource=settings.policies.submit.resource if enabled else None)
    if supply:
        kwargs["os_session_bridge_client"] = bridge
    if coo:
        kwargs["coo_settings"] = coo_settings(settings)
    change(kwargs)
    factory = server.build_web_ceo_v3_with_coo_mcp_app if coo else server.build_web_ceo_v3_mcp_app
    return factory(settings, **kwargs), peer, audit, bridge


def raw_request(app, token="", *, operation="context", scope_changes=None):
    path = "/os/executive/session/" + operation
    scope = dict(type="http", asgi={"version": "3.0"}, method="POST", scheme="https",
                 path=path, raw_path=path.encode(), query_string=b"",
                 headers=[(b"host", b"mcp.mastermind-x.com"),
                          (b"authorization", ("Bearer " + token).encode()),
                          (b"content-type", b"application/json")])
    scope.update(scope_changes or {})
    events = []
    async def receive():
        return {"type": "http.request", "body": json.dumps({"selection": leaf.SELECTION}).encode()}
    async def send(event):
        events.append(event)
    asyncio.run(app(scope, receive, send))
    assert len([e for e in events if e["type"] == "http.response.start"]) == 1
    return events[0], b"".join(e.get("body", b"") for e in events[1:])


@pytest.mark.parametrize("coo", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_legacy_default_viewer_and_launch_have_no_session_routes(settings, coo, enabled):
    app, peer, _, _ = build(settings, coo=coo, enabled=enabled, supply=False)
    for operation in ("context", "send", "reply"):
        response, _ = raw_request(app, operation=operation)
        assert response["status"] == 404
    ceo = app._ceo if coo else app
    assert ceo.os_session_transport is None
    assert (ceo.os_transport is not None) is enabled
    assert not peer.calls


@pytest.mark.parametrize("coo", [False, True])
def test_default_off_refuses_supplied_session_owner(settings, coo):
    with pytest.raises(ValueError):
        build(settings, coo=coo, enabled=False)


@pytest.mark.parametrize("coo", [False, True])
@pytest.mark.parametrize("path", [None, [], {}])
def test_existing_wrapper_bad_path_fails_closed_without_new_api(settings, coo, path):
    app, peer, _, _ = build(settings, coo=coo, supply=False)
    response, _ = raw_request(app, scope_changes={"path": path})
    assert response["status"] == 404 and not peer.calls


@pytest.mark.parametrize("coo", [False, True])
@pytest.mark.parametrize("submit", [False, True])
def test_full_context_uses_original_client_and_exact_policy(settings, rsa_key, coo, submit):
    app, peer, audit, bridge = build(settings, coo=coo)
    token = (leaf.auth_fixture._submit_token if submit else leaf.auth_fixture._read_token)(rsa_key)
    status, result = leaf.request(app, token)
    assert status == 200 and result["data"]["target"] == leaf.row()
    assert result["data"]["capabilities"] == {"send": submit, "reply_read": True, "stop": False}
    assert len(peer.calls) == 1 and peer.calls[0]["tool"] == "session_targets"
    assert peer.calls[0]["principal"]["policy_id"] == settings.policies.__getattribute__("submit" if submit else "read").policy_id
    assert audit.events
    ceo = app._ceo if coo else app
    assert ceo.os_session_transport is ceo._app.os_session_transport
    assert ceo.os_transport is not None


@pytest.mark.parametrize("coo", [False, True])
@pytest.mark.parametrize("action", ["POSTED", "RECOVERED", "DUPLICATE"])
def test_full_send_and_original_reply_remain_distinct(settings, rsa_key, coo, action):
    app, peer, _, _ = build(settings, coo=coo)
    peer.send_result = leaf.committed(action)
    token = leaf.auth_fixture._submit_token(rsa_key)
    status, result = leaf.request(app, token, "send")
    assert status == 200 and result["effect"] == "CONTINUATION_COMMITTED"
    assert result["data"]["attention"] == {"state": "UNAVAILABLE"}
    status, result = leaf.request(app, token, "reply")
    assert status == 200 and result["data"] == leaf.reply()
    assert [x["tool"] for x in peer.calls] == ["session_send", "session_reply_read"]
    assert peer.calls[-1]["arguments"] == {"operation_key": leaf.KEY}


@pytest.mark.parametrize("operation", ["context", "send", "reply"])
@pytest.mark.parametrize("reason", ["wrong-resource", "wrong-subject", "audit"])
def test_full_auth_refusal_precedes_private_effect(settings, rsa_key, operation, reason):
    app, peer, audit, _ = build(settings)
    overrides = {"resource": RESOURCE} if reason == "wrong-resource" else {"sub": "foreign"} if reason == "wrong-subject" else {}
    audit.fail = reason == "audit"
    status, result = leaf.request(app, leaf.auth_fixture._submit_token(rsa_key, **overrides), operation)
    assert status in (401, 403) and not peer.calls
    assert result["effect"] == ("UNKNOWN" if operation == "reply" else "NONE")


def test_full_read_token_cannot_send(settings, rsa_key):
    app, peer, _, _ = build(settings)
    status, result = leaf.request(app, leaf.auth_fixture._read_token(rsa_key), "send")
    assert status == 401 and result["error"]["code"] == "authentication_required"
    assert result["effect"] == "NONE" and not peer.calls


@pytest.mark.parametrize("operation", ["send", "reply"])
def test_full_entered_error_remains_unknown(settings, rsa_key, operation):
    app, peer, _, _ = build(settings)
    peer.error = "reply_unavailable"
    status, result = leaf.request(app, leaf.auth_fixture._submit_token(rsa_key), operation)
    assert status in (202, 503) and result["effect"] == "UNKNOWN"
    assert result["operation_key"] == leaf.KEY and len(peer.calls) == 1


@pytest.mark.parametrize("coo", [False, True])
@pytest.mark.parametrize("headers", [None, {}, [None], [(b"authorization",)], [(1, b"bad")], [(b"authorization", "bad")]])
def test_full_malformed_headers_keep_leaf_reply_unknown(settings, rsa_key, coo, headers):
    app, peer, _, _ = build(settings, coo=coo)
    status, result = leaf.request(app, leaf.auth_fixture._submit_token(rsa_key), "reply",
                                  scope_changes={"headers": headers})
    assert status in (400, 401, 403) and result["effect"] == "UNKNOWN" and not peer.calls


@pytest.mark.parametrize("coo", [False, True])
@pytest.mark.parametrize("changes", [
    {"path": None}, {"path": []}, {"path": {}}, {"path": 1},
    {"method": "GET"}, {"method": "OPTIONS"},
    {"raw_path": b"/os/executive/session/%63ontext"},
    {"query_string": b"extra=1"},
    {"path": "/os/executive/session/context/"},
    {"path": "/os/executive/session/stop"},
])
def test_full_bad_route_framing_refused_without_private_call(settings, rsa_key, coo, changes):
    app, peer, _, _ = build(settings, coo=coo)
    start, _ = raw_request(app, leaf.auth_fixture._read_token(rsa_key), scope_changes=changes)
    assert start["status"] == 404 and not peer.calls
    if isinstance(changes.get("path", "/os/"), str):
        hs = dict(start["headers"])
        assert hs[b"cache-control"] == b"no-store" and hs[b"referrer-policy"] == b"no-referrer"


@pytest.mark.parametrize("field", ["session_target_projector", "session_reply_handler", "session_summon_handler", "session_reply_read_tool", "os_session_bridge_client"])
def test_split_owner_refused_before_mount(settings, field):
    other = InstalledSessionBridgeClient("/other-never-used.sock", client=leaf.Peer())
    wrong = {"session_target_projector": other.targets, "session_reply_handler": other.send,
             "session_summon_handler": other.summon, "session_reply_read_tool": NativeReplyReadTool(other),
             "os_session_bridge_client": object()}[field]
    with pytest.raises((ValueError, TypeError)):
        build(settings, change=lambda kw: kw.update({field: wrong}))


@pytest.mark.parametrize("field", ["session_target_projector", "session_reply_handler", "session_summon_handler", "session_reply_read_tool"])
def test_same_owner_wrong_method_cannot_cross_bind_callback_roles(settings, field):
    def mutate(kw):
        bridge = kw["os_session_bridge_client"]
        if field == "session_reply_read_tool":
            kw[field]._reader = bridge.targets
        else:
            kw[field] = bridge.targets if field != "session_target_projector" else bridge.send
    with pytest.raises((ValueError, TypeError)):
        build(settings, change=mutate)


@pytest.mark.parametrize("changes", [
    [(b"authorization", b"Bearer duplicate")],
    [(b"authorization", None)],
    [(b"host", b"foreign.invalid")],
    [(b"origin", b"https://foreign.invalid")],
])
def test_full_transport_refusals_do_not_erase_reply_unknown(settings, rsa_key, changes):
    app, peer, _, _ = build(settings)
    status, result = leaf.request(app, leaf.auth_fixture._submit_token(rsa_key), "reply", header_changes=changes)
    assert status in (400, 401, 403) and result["effect"] == "UNKNOWN" and not peer.calls


@pytest.mark.parametrize("submit", [False, True])
def test_selected_additional_resource_uses_its_exact_audited_pair(settings, rsa_key, monkeypatch, submit):
    from integrations.mastermind_executive_app import gateway
    base_read, base_submit = settings.policies.read, settings.policies.submit
    alternate = AppPolicies(
        read=dataclasses.replace(base_read, resource=RESOURCE),
        submit=dataclasses.replace(base_submit, resource=RESOURCE))
    # Hermetic key source only; actual policy construction, RS256 and audited
    # verifiers are used for primary and alternate resources.
    monkeypatch.setattr(gateway, "make_shared_jwks_cache", lambda _: leaf.auth_fixture._FakeJwksCache(rsa_key))
    configured = dataclasses.replace(settings, additional_policies=(alternate,))
    app, peer, audit, _ = build(configured, change=lambda kw: kw.update(os_executive_resource=RESOURCE))
    token = (leaf.auth_fixture._submit_token if submit else leaf.auth_fixture._read_token)(rsa_key, resource=RESOURCE)
    status, result = leaf.request(app, token)
    assert status == 200 and result["data"]["capabilities"]["send"] is submit
    assert peer.calls[0]["principal"]["policy_id"] == (base_submit if submit else base_read).policy_id
    assert peer.calls[0]["principal"]["resource"] == RESOURCE
    assert audit.events and {event.policy_id for event in audit.events} <= {base_read.policy_id, base_submit.policy_id}
    peer.calls.clear()
    status, _ = leaf.request(app, leaf.auth_fixture._submit_token(rsa_key))
    assert status in (401, 403) and not peer.calls


@pytest.mark.parametrize("coo", [False, True])
def test_host_owns_lifespan_and_websocket(settings, coo, monkeypatch):
    app, peer, _, _ = build(settings, coo=coo)
    from integrations.mastermind_executive_app.os_session_transport import OsSessionTransportApp
    async def forbidden(*args):
        pytest.fail("non-HTTP scope reached session leaf")
    monkeypatch.setattr(OsSessionTransportApp, "__call__", forbidden)
    async def exercise():
        incoming, outgoing = asyncio.Queue(), asyncio.Queue()
        task = asyncio.create_task(app({"type": "lifespan", "asgi": {"version": "3.0"}}, incoming.get, outgoing.put))
        await incoming.put({"type": "lifespan.startup"})
        assert (await asyncio.wait_for(outgoing.get(), 5))["type"] == "lifespan.startup.complete"
        await incoming.put({"type": "lifespan.shutdown"})
        assert (await asyncio.wait_for(outgoing.get(), 5))["type"] == "lifespan.shutdown.complete"
        await asyncio.wait_for(task, 5)
        events = []
        async def receive():
            return {"type": "websocket.connect"}
        async def send(event):
            events.append(event)
        await app({"type": "websocket", "path": "/os/executive/session/context", "headers": [], "query_string": b""}, receive, send)
        assert events == [{"type": "websocket.close", "code": 1000, "reason": ""}]
    asyncio.run(exercise())
    assert not peer.calls


@pytest.mark.parametrize("coo", [False, True])
def test_enabled_sessions_preserve_mcp_catalog_scopes_and_launch_context(settings, rsa_key, coo):
    import httpx
    from integrations.executive_mcp import web_ceo_v3 as v3
    from integrations.session_bridge.return_tools import TOOL_NAME
    app, peer, _, _ = build(settings, coo=coo)
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response = await client.post("/mcp", headers={
                    "authorization": "Bearer " + leaf.auth_fixture._read_token(rsa_key),
                    "host": "127.0.0.1", "accept": "application/json, text/event-stream",
                    "mcp-protocol-version": "2025-06-18"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
                assert response.status_code == 200, response.text
                listed = response.json()["result"]["tools"]
                assert {tool["name"] for tool in listed} == set(v3.web_ceo_v3_tool_names()) | {TOOL_NAME}
                for tool in listed:
                    scopes = [launch.SUBMIT_SCOPE, launch.READ_SCOPE] if tool["name"] in {"submit_ceo_intent", "session_send", "session_summon", "reconcile_ceo_request"} else [launch.READ_SCOPE]
                    assert tool["securitySchemes"] == [{"type": "oauth2", "scopes": scopes}]
                response = await client.post("https://mcp.mastermind-x.com/os/executive/context",
                    headers=launch.headers(leaf.auth_fixture._submit_token(rsa_key)), json={})
                assert response.status_code == 200 and response.json()["profile"]["name"] == "web_ceo_v3"
    asyncio.run(exercise())
    assert not peer.calls
