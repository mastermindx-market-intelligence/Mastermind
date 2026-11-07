"""Actual signed BFF -> real owned Unix socket/kernel App peer -> Control branch.

Reuses explicit synthetic installed policy/host readiness and inert provider
premises from the accepted component fixture. No installed host/provider effect.
"""
import asyncio
import dataclasses
import hashlib
import os
from pathlib import Path
import tempfile

from tests.test_fresh_conversation_http import mounted, post, rsa_key
from tests.test_fresh_conversation import cleanup
from tests import test_mastermind_executive_app_asgi as auth
from control_plane.fresh_conversation import FreshConversationOwner
from integrations.mastermind_executive_app.fresh_conversation_transport import (
    FreshConversationTransportApp, InstalledFreshConversationClient,
)
from integrations.mastermind_executive_app.gateway import CeoIngressClient


def test_real_private_kernel_peer_and_foreground_creation_mount(tmp_path, rsa_key, monkeypatch):
    async def run():
        original, token, workspace_token, service, runtime, request, adapters, _, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        # This is the fixture's trusted policy source, not incoming frame data.
        policy = auth._submit_policy()
        expected = (policy.policy_id, hashlib.sha256(policy.issuer.encode()).hexdigest(), policy.resource)
        current = True
        def provider(selected_runtime):
            if selected_runtime is not runtime or not current:
                raise ValueError("fixture current policy/namespace unavailable")
            return FreshConversationOwner(service, expected_policy=expected)
        service._ceo_ingress_app_binding = dataclasses.replace(
            service._ceo_ingress_app_binding, fresh_conversation_provider_factory=provider)
        with tempfile.TemporaryDirectory(prefix="fresh-ingress-", dir="/tmp") as directory:
            path = Path(directory) / "app.sock"
            server = await asyncio.start_unix_server(service._handle_ceo_ingress_connection, path=path)
            client = CeoIngressClient()
            app = FreshConversationTransportApp(original._inner, executive=original._executive,
                workspace_config=original._workspace, workspace_verifier=original._workspace_verifier,
                client=InstalledFreshConversationClient(path, client))
            try:
                code, preview = await post(app, "preview", request, token, workspace_token)
                assert code == 200 and preview["ok"] is True
                create = {**request, "preview_digest": preview["data"]["preview"]["digest"]}
                code, result = await post(app, "create", create, token, workspace_token)
                assert code == 200 and result["ok"] is True and result["data"]["state"] == "CREATED"
                selected = {name: request[name] for name in ("work_ref", "operation_key")}
                code, read = await post(app, "read", selected, token)
                assert code == 200 and read["ok"] is True and read["data"]["result"]
                initial_digest = read["data"]["result"]["digest"]
                consume = {**selected, "initial_digest": initial_digest}
                code, consumed = await post(app, "consume", consume, token, workspace_token)
                assert code == 200 and consumed["ok"] and consumed["data"]["state"] == "CONSUMED"
                code, consumption_status = await post(app, "consume_status", consume, token)
                assert code == 200 and consumption_status["ok"] and consumption_status["data"]["state"] == "CONSUMED"
                assert consumption_status["data"]["can_send"] is False
                turn = {**consume, "turn_key": "owned-private-turn-1", "message": "Explain this bounded result."}
                code, preflight = await post(app, "turn_preview", turn, token, workspace_token)
                assert code == 200 and preflight["ok"] and preflight["data"]["state"] == "TURN_READY"
                turn = {**turn, "preview_digest": preflight["data"]["preview_digest"]}
                code, second = await post(app, "turn", turn, token, workspace_token)
                assert code == 200 and second["ok"] and second["data"]["state"] == "RECORDED"
                original_turn = {**selected, "turn_key": turn["turn_key"]}
                for operation in ("turn_status", "turn_read"):
                    code, retained = await post(app, operation, original_turn, token)
                    assert code == 200 and retained["ok"] and retained["data"]["state"] == "RECORDED"
                assert adapters[0].begin_turn_calls == 2
                count = len(runtime.jobs.list_jobs())
                before = runtime.events.list_events()
                duplicate_trace = []

                def exception_trace(exc):
                    # Keep only bounded type/code/location evidence, never messages
                    # or locals. Explicit context survives ``raise ... from None``.
                    pending, seen, chain = [("raised", exc)], set(), []
                    while pending and len(chain) < 8:
                        relation, current_exc = pending.pop(0)
                        if id(current_exc) in seen:
                            continue
                        seen.add(id(current_exc))
                        frames, tb = [], current_exc.__traceback__
                        while tb is not None:
                            frames.append({"file": tb.tb_frame.f_code.co_filename,
                                "function": tb.tb_frame.f_code.co_name, "line": tb.tb_lineno})
                            frames = frames[-12:]
                            tb = tb.tb_next
                        item = {"relation": relation,
                            "type": f"{type(current_exc).__module__}.{type(current_exc).__qualname__}",
                            "frames": frames}
                        if type(current_exc).__name__ in {"ConversationRefusal", "CeoIngressError"}:
                            item["code"] = getattr(current_exc, "code", None)
                            item["effect"] = getattr(current_exc, "effect", None)
                        chain.append(item)
                        for name in ("__cause__", "__context__"):
                            related = getattr(current_exc, name, None)
                            if related is not None:
                                pending.append((relation + "." + name, related))
                    return chain

                original_send_frame = client._send_frame
                original_create = FreshConversationOwner.create

                async def traced_send_frame(socket_path, frame, *, keep_write_open, foreground_source=None):
                    duplicate_trace.append({"owner": "transport", "event": "entered"})
                    try:
                        response = await original_send_frame(socket_path, frame,
                            keep_write_open=keep_write_open, foreground_source=foreground_source)
                    except BaseException as exc:
                        duplicate_trace.append({"owner": "transport", "event": "raised",
                            "exceptions": exception_trace(exc)})
                        raise
                    nested = response.result if isinstance(response.result, dict) else {}
                    nested_error = nested.get("error")
                    duplicate_trace.append({"owner": "transport", "event": "returned",
                        "transport": response.transport, "ok": response.ok, "detail": response.detail,
                        "error_code": response.error.get("code") if isinstance(response.error, dict) else None,
                        "result_ok": nested.get("ok"),
                        "result_error_code": nested_error.get("code") if isinstance(nested_error, dict) else None})
                    return response

                async def traced_create(owner, principal, request, *, workspace_principal):
                    duplicate_trace.append({"owner": "create", "event": "entered"})
                    try:
                        value = await original_create(owner, principal, request,
                            workspace_principal=workspace_principal)
                    except BaseException as exc:
                        duplicate_trace.append({"owner": "create", "event": "raised",
                            "exceptions": exception_trace(exc)})
                        raise
                    duplicate_trace.append({"owner": "create", "event": "returned",
                        "state": value.get("state"), "effect": value.get("effect")})
                    return value

                with monkeypatch.context() as trace_patch:
                    trace_patch.setattr(client, "_send_frame", traced_send_frame)
                    trace_patch.setattr(FreshConversationOwner, "create", traced_create)
                    code, duplicate = await post(app, "create", create, token, workspace_token)
                assert code == 200 and duplicate["ok"] is True, {
                    "status": code, "response": duplicate, "duplicate_trace": duplicate_trace,
                }
                assert len(runtime.jobs.list_jobs()) == count and runtime.events.list_events() == before
                assert len(adapters) == 1 and adapters[0].start_calls == 1
                current = False
                code, _ = await post(app, "status", selected, token)
                assert code == 503 and len(runtime.jobs.list_jobs()) == count
                current = True
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding, peer_uid=os.geteuid() + 1)
                code, _ = await post(app, "status", selected, token)
                assert code == 503 and len(runtime.jobs.list_jobs()) == count
            finally:
                server.close()
                await server.wait_closed()
                await cleanup(service)
                if service._ceo_ingress_tasks:
                    await asyncio.wait_for(asyncio.gather(*service._ceo_ingress_tasks), 5)
    asyncio.run(run())

# These are existing disposable Git/settings/JWKS fixtures. They read no
# installed policy, private configuration, credential or provider source.
from tests.test_executive_mcp_public_audience import settings, short_socket_root, fake_jwks


def test_actual_v3_factory_mounts_fixed_fresh_routes_with_same_workspace_owner(tmp_path, rsa_key, monkeypatch, settings):
    from integrations.executive_mcp import server as gateway
    from tests.test_executive_mcp_public_audience import FixedMdm, _assets
    from common import fresh_conversation_contract as wire
    import time
    async def run():
        original, token, workspace_token, service, runtime, request, _, _, sink = await mounted(tmp_path / "source", rsa_key, monkeypatch)
        config = original._workspace
        workspace = gateway.AuditedWorkspaceApp(original._inner, original._workspace_verifier,
            authenticator=config.authenticator, authorize_principal=config.authorize_principal,
            fresh_workspace_config=config)
        installed = dataclasses.replace(settings, clock=lambda: int(time.time()), read_from_ceo_ingress=True)
        app = gateway.build_web_ceo_v3_mcp_app(installed, audit_sink=sink, mdm_reader=FixedMdm(),
            session_target_projector=lambda *_: [], session_reply_handler=lambda *_: {},
            session_summon_handler=lambda *_: {}, workspace_app=workspace, os_app=_assets(),
            enable_os_executive_transport=True, os_executive_resource=installed.policies.submit.resource)
        try:
            assert type(app.fresh_conversation_transport) is FreshConversationTransportApp
            assert set(gateway._OS_FRESH_CONVERSATION_ROUTES) == set(wire.ROUTES)
            assert app.fresh_conversation_transport._workspace is config
            assert app.fresh_conversation_transport._workspace_verifier is original._workspace_verifier
            # All literal routes pass the actual outer route fence. Without a
            # credential they stop at authentication, never the socket/Runtime.
            jobs, events = runtime.jobs.list_jobs(), runtime.events.list_events()
            for operation in wire.ROUTES.values():
                code, _ = await post(app, operation, {}, "not-a-jwt")
                assert code == 401
            for change in ({"query_string": b"unexpected=1"}, {"method": "GET"},
                    {"headers": [(b"host", b"foreign.example")]}, {"scheme": "http"},
                    {"headers": [(b"host", b"mcp.mastermind-x.com"), (b"origin", b"https://foreign.example")]}):
                code, _ = await post(app, "preview", request, token, workspace_token, change=change)
                # The outer MCP middleware may reject malformed framing at
                # 400 before the fixed route fence's 403/404. Every case must
                # remain a client refusal, never an accepted/source request.
                assert 400 <= code < 500
            assert runtime.jobs.list_jobs() == jobs and runtime.events.list_events() == events
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_fresh_fixed_routes_retain_public_host_origin_method_and_query_fence():
    from integrations.executive_mcp import server as gateway
    from starlette.responses import JSONResponse
    async def run():
        reached = []
        async def inner(scope, receive, send):
            reached.append(scope["path"])
            await JSONResponse({"inert_handler_boundary": True}, status_code=418)(scope, receive, send)
        app = gateway._ExecutivePathFence(inner, "/metadata", fresh_conversation_transport=object())
        for operation in ("preview", "create", "status", "read", "consume", "turn", "turn_status", "turn_read"):
            code, _ = await post(app, operation, {}, "inert-token")
            assert code == 418
            for change, expected in (({"query_string": b"unlisted=1"}, 404), ({"method": "GET"}, 404),
                    ({"scheme": "http"}, 403), ({"headers": [(b"host", b"foreign.example")]}, 403),
                    ({"headers": [(b"host", b"mcp.mastermind-x.com"), (b"origin", b"https://foreign.example")]}, 403)):
                count = len(reached)
                code, _ = await post(app, operation, {}, "inert-token", change=change)
                assert code == expected and len(reached) == count
        assert len(reached) == 8
    asyncio.run(run())
