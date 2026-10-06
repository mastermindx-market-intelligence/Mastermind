"""Reply read tools compose into the existing OAuth MCP host, never a new server."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import importlib
import json
import sys
from pathlib import Path

import httpx
import pytest

from integrations.session_bridge.native_read import NativeReplyReader
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.executive_mcp.schemas import GatewayError
from test_session_bridge_native_read import Resolver, PRINCIPAL, NOW, READ_REF

NAME = "session_reply_read"


def api():
    spec = importlib.util.find_spec("integrations.session_bridge.return_tools")
    assert spec is not None, "the authenticated reply reader has no MCP tool composition"
    return importlib.import_module(spec.name)


def tool(resolver=None):
    r = resolver or Resolver()
    reader = NativeReplyReader(r, socket_path=Path("/private/tmp/reply-tools-proof.sock"),
        service_call=r.service, clock=lambda: NOW)
    return api().NativeReplyReadTool(reader), r


def test_closed_read_only_tool_contract():
    t, _ = tool()
    spec = t.tool_spec()
    assert spec.name == NAME and spec.read_only is True
    assert spec.annotations["readOnlyHint"] is True
    assert spec.annotations["destructiveHint"] is False
    assert spec.input_schema == {"type": "object", "properties": {
        "read_ref": {"type": "string", "minLength": 1, "maxLength": 256},
        "operation_key": {"type": "string", "minLength": 1, "maxLength": 256}},
        "oneOf": [{"required": ["read_ref"]}, {"required": ["operation_key"]}],
        "additionalProperties": False}


@pytest.mark.parametrize("args", [{}, {"read_ref": ""}, {"read_ref": "x" * 257},
    {"read_ref": READ_REF, "consume": True}, {"read_ref": READ_REF, "principal": "forged"},
    {"read_ref": READ_REF, "thread_ts": "1787896128.625239"}, {"read_ref": 12}])
def test_invalid_tool_arguments_fail_before_reader(args):
    t, r = tool()
    result = asyncio.run(t.handle(PRINCIPAL, NAME, args))
    assert result["ok"] is False and result["error"]["code"] == "invalid_input"
    assert not r.calls and not r.service.calls


def test_tool_delivers_canonical_reply_but_not_consumption_or_execution():
    t, r = tool()
    result = asyncio.run(t.handle(PRINCIPAL, NAME, {"read_ref": READ_REF}))
    assert result["schema"] == "mastermind.session_reply_read_result.v1"
    assert result["tool"] == NAME and result["ok"] is True and result["error"] is None
    assert result["data"]["reply_committed"] is True and result["data"]["parent_consumed"] is False
    assert result["data"]["read_ref"] == READ_REF
    assert [x["operation"] for x in r.service.calls] == ["read_thread"]


def test_unverified_principal_is_refused_before_canonical_reader():
    t, r = tool()
    result = asyncio.run(t.handle(dataclasses.asdict(PRINCIPAL), NAME, {"read_ref": READ_REF}))
    assert result["error"]["code"] == "reply_unavailable"
    assert not r.calls


def test_foreign_and_missing_reply_have_same_bounded_error():
    t, r = tool()
    foreign = asyncio.run(t.handle(dataclasses.replace(PRINCIPAL, subject_digest="9" * 64), NAME, {"read_ref": READ_REF}))
    r.service.items.pop()
    missing = asyncio.run(t.handle(PRINCIPAL, NAME, {"read_ref": READ_REF}))
    assert foreign == missing and foreign["data"] is None


def test_cancelled_read_is_not_hidden_as_success():
    r = Resolver()
    async def cancelled(*args): raise asyncio.CancelledError()
    reader = NativeReplyReader(r, socket_path=Path("/private/tmp/reply-tools-proof.sock"),
        service_call=cancelled, clock=lambda: NOW)
    t = api().NativeReplyReadTool(reader)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(t.handle(PRINCIPAL, NAME, {"read_ref": READ_REF}))


def test_validator_uses_existing_host_gateway_error_contract():
    t, r = tool()
    with pytest.raises(GatewayError):
        t.validate(NAME, {"read_ref": READ_REF, "authority": "admin"})
    assert not r.calls


def test_extension_preserves_existing_tools_submit_scopes_and_handlers():
    import mcp.types as mt
    t, r = tool()
    calls = []
    old_tool = mt.Tool(name="incumbent_write", description="fixture", inputSchema={"type": "object"})
    def validate(name, args): calls.append(("validate", name)); return dict(args)
    async def handler(principal, name, args): calls.append(("handle", name)); return {"incumbent": True}
    def error(name, code, message): calls.append(("error", name)); return {"incumbent_error": True}
    marker = object()
    original = {"profile_tools": (old_tool,), "profile_validator": validate,
        "direct_tool_names": ("incumbent_write",), "direct_submit_names": ("incumbent_write",),
        "direct_handler": handler, "direct_error_factory": error, "marker": marker}
    extended = t.extend_host_configuration(original)
    assert extended["marker"] is marker
    assert extended["profile_tools"][0] is old_tool and len(original["profile_tools"]) == 1
    assert extended["direct_submit_names"] == ("incumbent_write",)
    assert extended["direct_tool_names"] == ("incumbent_write", NAME)
    assert extended["profile_validator"]("incumbent_write", {}) == {}
    assert asyncio.run(extended["direct_handler"](PRINCIPAL, "incumbent_write", {})) == {"incumbent": True}
    assert extended["direct_error_factory"]("incumbent_write", "x", "secret") == {"incumbent_error": True}
    assert calls == [("validate", "incumbent_write"), ("handle", "incumbent_write"), ("error", "incumbent_write")]
    assert not r.calls


def test_extension_refuses_duplicate_tool_and_noncallable_existing_dispatcher():
    import mcp.types as mt
    t, _ = tool()
    duplicate = mt.Tool(name=NAME, inputSchema={"type": "object"})
    with pytest.raises(ValueError):
        t.extend_host_configuration({"profile_tools": (duplicate,), "profile_validator": lambda n,a:a})
    with pytest.raises(ValueError):
        t.extend_host_configuration({"profile_tools": (), "profile_validator": lambda n,a:a,
            "direct_tool_names": ("old",), "direct_handler": None})


@pytest.mark.parametrize("code", ["backend_unavailable", "output_too_large", "secret:/path", None])
def test_host_error_fallback_does_not_expose_diagnostics(code):
    t, _ = tool()
    result = t.error(NAME, code, "private diagnostic that must not escape")
    assert "private" not in json.dumps(result) and "secret" not in json.dumps(result)
    assert result["ok"] is False and result["data"] is None


# Real OAuth/Bearer + MCP transport, with only the native owner/Slack facts faked.
import test_executive_mcp_web_ceo_sessions as host_fixture
import test_mastermind_executive_app_asgi as auth_fixture
from integrations.executive_mcp import server as transport, web_ceo
from integrations.mastermind_executive_app.app import create_web_ceo_v2_app

rsa_key = host_fixture.rsa_key
short_socket_root = host_fixture.short_socket_root
settings = host_fixture.settings


def app_with_reader(settings, profile="v2"):
    canonical = Resolver()
    calls = []
    class InstalledGrantFixture:
        async def resolve_read(self, *, principal, read_ref):
            calls.append((principal, read_ref))
            policy = settings.policies.read
            if (principal.subject_digest not in policy.allowed_subject_digests
                    or principal.resource != policy.resource or read_ref != READ_REF):
                raise ValueError("not this request owner")
            return dataclasses.replace(canonical.binding, authorized_principal=principal)
    read = NativeReplyReader(InstalledGrantFixture(),
        socket_path=Path("/private/tmp/reply-tools-proof.sock"),
        service_call=canonical.service, clock=settings.clock)
    t = api().NativeReplyReadTool(read)
    if profile in {"v3", "sessions"}:
        from types import SimpleNamespace
        installed = dataclasses.replace(settings, read_from_ceo_ingress=True)
        owners, projector = host_fixture.Owners(), host_fixture.Projector()
        kwargs = dict(audit_sink=host_fixture.Sink(), session_target_projector=projector,
            session_reply_handler=owners.reply, session_summon_handler=owners.summon,
            session_reply_read_tool=t)
        if profile == "v3":
            async def unused(**kwargs):
                raise AssertionError("reply read must not call MDM")
            app = transport.build_web_ceo_v3_mcp_app(installed,
                mdm_reader=SimpleNamespace(list_macos_devices=unused, device=unused), **kwargs)
        else:
            app = transport.build_web_ceo_sessions_mcp_app(installed, **kwargs)
        return app, canonical, calls
    config = t.extend_host_configuration({"settings": settings, "audit_sink": host_fixture.Sink(),
        "profile_server_name": web_ceo.WEB_CEO_V2_SERVER_NAME,
        "profile_server_version": web_ceo.WEB_CEO_V2_SERVER_VERSION,
        "profile_tools": tuple(transport.build_web_ceo_v2_tools()),
        "profile_validator": web_ceo.validate_web_ceo_v2_tool_arguments,
        "profile_create_app": create_web_ceo_v2_app})
    return transport._build_profile_mcp_app(**config), canonical, calls


def test_authenticated_mcp_advertises_existing_tools_plus_read_only_reply_tool(settings, rsa_key):
    app, r, calls = app_with_reader(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response = await host_fixture.rpc(client, auth_fixture._read_token(rsa_key), "tools/list")
                assert response.status_code == 200
                tools = response.json()["result"]["tools"]
                assert [x["name"] for x in tools] == [s.name for s in web_ceo.WEB_CEO_V2_TOOL_SPECS] + [NAME]
                native = tools[-1]
                assert native["annotations"]["readOnlyHint"] is True
                assert native["annotations"]["destructiveHint"] is False
                assert native["inputSchema"]["additionalProperties"] is False
        assert not calls and not r.service.calls
    asyncio.run(run())


def test_authenticated_mcp_read_scope_reaches_exact_canonical_reader(settings, rsa_key):
    app, r, calls = app_with_reader(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response, payload = await host_fixture.call(client, auth_fixture._read_token(rsa_key), NAME, {"read_ref": READ_REF})
                assert response.status_code == 200 and payload["ok"] is True, payload
                assert payload["data"]["read_ref"] == READ_REF
                assert payload["data"]["parent_consumed"] is False
        assert len(calls) == 2
        assert [x["operation"] for x in r.service.calls] == ["read_thread"]
    asyncio.run(run())


@pytest.mark.parametrize("changes", [{"iss": "https://foreign.example.test/"},
    {"aud": "https://foreign.example.test/mcp"}, {"sub": "foreign-subject"},
    {"exp": auth_fixture.NOW - 1}])
def test_mcp_invalid_auth_never_reaches_reply_reader(settings, rsa_key, changes):
    app, r, calls = app_with_reader(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response = await host_fixture.rpc(client, auth_fixture._read_token(rsa_key, **changes),
                    "tools/call", {"name": NAME, "arguments": {"read_ref": READ_REF}})
                assert response.status_code in {401, 403}, response.text
        assert not calls and not r.service.calls
    asyncio.run(run())


def test_mcp_read_tool_cannot_acknowledge_consume_or_choose_carrier(settings, rsa_key):
    app, r, calls = app_with_reader(settings)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response, payload = await host_fixture.call(client, auth_fixture._read_token(rsa_key),
                    NAME, {"read_ref": READ_REF, "consume": True})
                assert response.status_code == 200 and payload["ok"] is False
        assert not calls and not r.service.calls
    asyncio.run(run())


@pytest.mark.parametrize("changes", [{"release_profile": True}, {"release_profile": "false"},
    {"release_tool_names": (NAME,)}])
def test_read_only_extension_cannot_be_promoted_to_release_scope(changes):
    t, _ = tool()
    config = {"profile_tools": (), "profile_validator": lambda name,args: args, **changes}
    with pytest.raises(ValueError):
        t.extend_host_configuration(config)


def test_extension_rejects_ambiguous_existing_tool_catalog():
    import mcp.types as mt
    t, _ = tool()
    item = mt.Tool(name="old_tool", inputSchema={"type": "object"})
    with pytest.raises(ValueError):
        t.extend_host_configuration({"profile_tools": (item, item), "profile_validator": lambda n,a:a})


def test_real_native_reply_event_oauth_mcp_read_has_one_canonical_post(settings, rsa_key, short_socket_root):
    """Actual JWT/MCP and Unix Relay/engine; native identities and Slack are fixtures."""
    import os
    from test_session_bridge_native_reply import Resolver as NativeResolver, NATIVE, ACTOR, request, arguments
    from test_session_bridge_native_roundtrip import WithinCommission, BOT, SOL
    from integrations.session_bridge.native_reply import NativeReplyWriter
    from integrations.session_bridge.native_read import NativeReplyReadBinding
    from integrations.session_bridge.web_reply_events import ReplyEventBinding, CanonicalReplyEventProjector
    from integrations.slack_agent_dialogue.contract_v2 import build_message_v2, render_message_v2
    from integrations.slack_agent_dialogue.engine import DialoguePolicy, DialogueEngine, SlackMessage
    from integrations.slack_agent_dialogue.engine_v2 import DialogueEngineV2
    from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
    from integrations.slack_agent_dialogue.service import AgentDialogueService, ServiceConfig

    async def run():
        native = NativeResolver()
        policy = DialoguePolicy(workspace_id="T0BRD2AQXQV", channel_id="C0BRUL9F2V7",
            relay_bot_user_id=BOT, allowed_sol_user_ids=(SOL,), allowed_parent_user_ids=(SOL,),
            poll_interval_seconds=0, max_wait_attempts=3)
        slack = InMemorySlackClient(relay_bot_user_id=BOT)
        engine = DialogueEngineV2(policy, slack, authority_policy=WithinCommission())
        parent = await engine.ensure_thread(native.binding.context, created_at="2026-10-01T19:59:00Z")
        native.binding = dataclasses.replace(native.binding, thread_ts=parent.thread_ts)
        prior = request(); prior.pop("fingerprint")
        prior.update(message_key="asd-worker-result-0001", message_type="RESULT", actor_ref=ACTOR,
            reply_to_message_key=None, summary="Fixture worker result", body={"status": "PASS", "result": "Fixture only"})
        for author, message in [(BOT, build_message_v2(prior)), (SOL, request())]:
            slack.add_reply(SlackMessage(ts=slack._mint_ts(), author_user_id=author,
                text=render_message_v2(message), thread_ts=parent.thread_ts))
        socket = short_socket_root / "native-return.sock"
        service = AgentDialogueService(ServiceConfig(socket_path=socket, allowed_peer_uids=(os.geteuid(),)),
            DialogueEngine(policy, slack, authority_policy=WithinCommission()), engine_v2=engine)
        await service.start()
        try:
            writer = NativeReplyWriter(native, native_session_id=NATIVE, socket_path=socket)
            receipt = await writer(arguments())
            duplicate = await writer(arguments())
            assert duplicate["action"] == "DUPLICATE" and slack.post_call_count == 1
            view = await engine.read_thread(thread_ts=parent.thread_ts, context=native.binding.context)
            item = next(x for x in view.messages if x.message["message_key"] == receipt["message_key"])
            class EventOwner:
                def resolve_reply(self, **kwargs):
                    return ReplyEventBinding(principal_ref="original-web-001", request_ref="request-001",
                        request_message_key=arguments()["in_reply_to"], thread_ts=parent.thread_ts,
                        context=native.binding.context, reply_message=item.message,
                        reply_primary_ts=item.primary_ts, read_ref=READ_REF, access_current=True)
            event = CanonicalReplyEventProjector(EventOwner()).project(principal_ref="original-web-001",
                arguments={"request_ref": "request-001"}, message_key=receipt["message_key"])
            class ReadOwner:
                async def resolve_read(self, *, principal, read_ref):
                    if (principal.subject_digest not in settings.policies.read.allowed_subject_digests
                            or principal.resource != settings.policies.read.resource or read_ref != READ_REF):
                        raise ValueError
                    return NativeReplyReadBinding(authorized_principal=principal, read_ref=READ_REF,
                        request_ref="request-001", request_message_key=arguments()["in_reply_to"],
                        thread_ts=parent.thread_ts, reply_message_key=receipt["message_key"],
                        reply_fingerprint=receipt["fingerprint"], context=native.binding.context,
                        authorization_revision="current-grant-001")
            t = api().NativeReplyReadTool(NativeReplyReader(ReadOwner(), socket_path=socket, clock=settings.clock))
            config = t.extend_host_configuration({"settings": settings, "audit_sink": host_fixture.Sink(),
                "profile_server_name": web_ceo.WEB_CEO_V2_SERVER_NAME,
                "profile_server_version": web_ceo.WEB_CEO_V2_SERVER_VERSION,
                "profile_tools": tuple(transport.build_web_ceo_v2_tools()),
                "profile_validator": web_ceo.validate_web_ceo_v2_tool_arguments,
                "profile_create_app": create_web_ceo_v2_app})
            app = transport._build_profile_mcp_app(**config)
            async with app._app.router.lifespan_context(app._app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                    for _ in range(2):
                        response, content = await host_fixture.call(client, auth_fixture._read_token(rsa_key),
                            NAME, {"read_ref": event["data"]["read_ref"]})
                        assert response.status_code == 200 and content["ok"] is True, content
                        assert content["data"]["text"] == arguments()["text"]
                        assert content["data"]["fingerprint"] == receipt["fingerprint"]
                        assert content["data"]["parent_consumed"] is False
            assert slack.post_call_count == 1
        finally:
            await service.close()
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["missing", "no_read_scope", "duplicate"])
def test_mcp_missing_scope_or_ambiguous_authorization_never_calls_reader(settings, rsa_key, mode):
    app, r, calls = app_with_reader(settings)
    async def run():
        token = auth_fixture._read_token(rsa_key)
        headers = list(host_fixture.headers(token).items())
        if mode == "missing":
            headers = [(k,v) for k,v in headers if k.lower() != "authorization"]
        elif mode == "no_read_scope":
            headers = list(host_fixture.headers(auth_fixture._token(rsa_key, scope="")).items())
        else:
            headers.append(("authorization", f"Bearer {token}"))
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response = await client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 7,
                    "method": "tools/call", "params": {"name": NAME, "arguments": {"read_ref": READ_REF}}})
                assert response.status_code in {401, 403}, response.text
        assert not calls and not r.service.calls
    asyncio.run(run())


@pytest.mark.parametrize("profile", ["v3", "sessions"])
@pytest.mark.parametrize("auth", ["original-read", "submit-only", "foreign", "expired"])
def test_installed_profiles_keep_native_reply_read_bound_to_original_parent(settings, rsa_key, profile, auth):
    from integrations.executive_mcp import web_ceo_v3
    app, owner, calls = app_with_reader(settings, profile)
    async def run():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                listed = await host_fixture.rpc(client, auth_fixture._read_token(rsa_key), "tools/list")
                tools = listed.json()["result"]["tools"]
                old = (web_ceo_v3.web_ceo_v3_tool_names() if profile == "v3"
                       else tuple(item.name for item in transport.build_web_ceo_sessions_tools()))
                assert tuple(tool["name"] for tool in tools) == old + (NAME,)
                assert tools[-1]["annotations"]["readOnlyHint"] is True
                assert tools[-1]["annotations"]["destructiveHint"] is False
                if auth == "submit-only":
                    token = auth_fixture._token(rsa_key, scope=auth_fixture.SUBMIT_SCOPE)
                else:
                    changes = {"sub": "foreign-subject"} if auth == "foreign" else (
                        {"exp": auth_fixture.NOW - 1} if auth == "expired" else {})
                    token = auth_fixture._read_token(rsa_key, **changes)
                response = await host_fixture.rpc(client, token, "tools/call",
                    {"name": NAME, "arguments": {"read_ref": READ_REF}})
                if auth == "original-read":
                    payload = json.loads(response.json()["result"]["content"][0]["text"])
                    assert payload["ok"] and payload["data"]["parent_consumed"] is False
                else:
                    assert response.status_code in {401, 403}
        if auth == "original-read":
            assert len(calls) == 2
            assert [call["operation"] for call in owner.service.calls] == ["read_thread"]
        else:
            assert calls == [] and owner.service.calls == []
    asyncio.run(run())
