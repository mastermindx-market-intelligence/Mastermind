"""Combined native transport with real JWT verification and disposable Runtime.

These are source-level proofs; no installed listener, provider or host is used.
"""
import asyncio
from contextlib import asynccontextmanager
import dataclasses
import json
import os
from pathlib import Path

import httpx
import pytest

from integrations.executive_mcp import server, schemas, web_ceo, web_ceo_release
from integrations.executive_mcp import release_control
from integrations.mastermind_executive_app import app as app_module
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from tests import test_executive_mcp_app_composition as native
from tests import test_executive_mcp_release_control as release
from tests.test_executive_release_consumer import installed, inputs, counts

rsa_key = native.rsa_key
short_socket_root = native.short_socket_root
settings = native.settings


@asynccontextmanager
async def connection(settings, **mounts):
    app = server.build_web_ceo_release_mcp_app(
        dataclasses.replace(settings, read_from_ceo_ingress=True), audit_sink=native.Sink(), **mounts)
    async with app._app.router.lifespan_context(app._app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://127.0.0.1") as client:
            yield client


def test_exact_discovery_preserves_contracts_and_per_tool_scopes(settings, rsa_key):
    assert web_ceo_release.WEB_CEO_RELEASE_TOOL_SPECS == (
        web_ceo.WEB_CEO_V2_TOOL_SPECS + release_control.RELEASE_CONTROL_TOOL_SPECS)
    async def exercise():
        async with connection(settings) as client:
            for token in (native.fixture._read_token(rsa_key), native.fixture._submit_token(rsa_key)):
                tools = (await native.rpc(client, token, "tools/list"))["tools"]
                assert len(tools) == 10
                for tool, spec in zip(tools, web_ceo_release.WEB_CEO_RELEASE_TOOL_SPECS):
                    assert tool["name"] == spec.name
                    assert tool["inputSchema"] == spec.input_schema
                    assert tool["annotations"]["readOnlyHint"] == spec.annotations["readOnlyHint"]
                    policy = settings.policies.submit if spec.name in release.ARGS or spec.name == "submit_ceo_intent" else settings.policies.read
                    expected = [{"type": "oauth2", "scopes": list(policy.required_scopes)}]
                    assert tool["securitySchemes"] == tool["_meta"]["securitySchemes"] == expected
            metadata = await client.get(native.fixture.METADATA_PATH)
            assert metadata.json()["scopes_supported"] == list(settings.policies.submit.required_scopes)
    asyncio.run(exercise())


@pytest.mark.parametrize("operation", ["submit_ceo_intent", *release.ARGS])
def test_read_token_cannot_send_any_modifying_scope_frame(settings, rsa_key, monkeypatch, operation):
    async def forbidden(*a, **k):
        pytest.fail("read token reached an ingress socket send")
    monkeypatch.setattr(CeoIngressClient, "send_frame", forbidden)
    async def exercise():
        async with connection(settings) as client:
            reply, value = await native.call(client, native.fixture._read_token(rsa_key), operation,
                                             native.PAYLOAD if operation == "submit_ceo_intent" else release.ARGS[operation])
            assert value["error"]["code"] == "scope_refused"
            assert reply["isError"]
            assert "mastermind.executive.intent.submit" in reply["_meta"]["mcp/www_authenticate"][0]
    asyncio.run(exercise())


@pytest.mark.parametrize("case", ["audience", "issuer", "signature", "duplicate"])
def test_bad_auth_refuses_before_socket(settings, rsa_key, monkeypatch, case):
    async def forbidden(*a, **k):
        pytest.fail("invalid identity reached the ingress")
    monkeypatch.setattr(CeoIngressClient, "send_frame", forbidden)
    async def exercise():
        token = native.fixture._submit_token(rsa_key)
        if case == "audience": token = native.fixture._submit_token(rsa_key, aud="https://wrong.example/mcp")
        if case == "issuer": token = native.fixture._submit_token(rsa_key, iss="https://wrong.example/")
        if case == "signature":
            from cryptography.hazmat.primitives.asymmetric import rsa
            token = native.fixture._submit_token(rsa.generate_private_key(public_exponent=65537, key_size=2048))
        headers = list(native.headers(token).items())
        if case == "duplicate": headers.append(("authorization", "Bearer " + token))
        async with connection(settings) as client:
            response = await client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1,
                "method": "tools/call", "params": {"name": "approve_release_transition",
                                                     "arguments": release.ARGS["approve_release_transition"]}})
            assert response.status_code in (401, 403)
    asyncio.run(exercise())


@pytest.mark.parametrize("operation", list(release.ARGS))
def test_combined_release_dispatch_preserves_existing_closed_contract(settings, rsa_key, monkeypatch, operation):
    monkeypatch.setattr(release, "connection", connection)
    release.test_valid_calls_forward_once_with_authenticated_projection(settings, rsa_key, monkeypatch, operation)


@pytest.mark.parametrize("operation", list(release.ARGS))
def test_combined_release_ambiguity_retains_unknown(settings, rsa_key, monkeypatch, operation):
    monkeypatch.setattr(release, "connection", connection)
    release.test_transport_rejects_bad_inner_app_results(settings, rsa_key, monkeypatch, operation)


@pytest.mark.parametrize("history_state", [
    "NOT_FOUND", "STARTED", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING",
    "SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED",
])
def test_combined_approval_recovers_once_and_commit_stays_disarmed(
    installed, rsa_key, tmp_path, short_socket_root, monkeypatch, history_state,
):
    monkeypatch.setattr(release, "connection", connection)
    release.test_durable_approval_lost_readback_and_typed_history_over_native_mcp(
        installed, rsa_key, tmp_path, short_socket_root, monkeypatch, history_state)


@pytest.mark.parametrize("lost_reply", ["malformed", "oversized", "exception", "wrong_identity"])
def test_combined_submit_unknown_preserves_original_reference(
    settings, rsa_key, monkeypatch, lost_reply,
):
    from control_plane.ceo_request import app_request_ref
    class Damaged:
        async def __call__(self, scope, receive, send):
            if lost_reply == "exception":
                raise OSError("PRIVATE_SENTINEL")
            body = b"{" if lost_reply == "malformed" else b" " * 262145 if lost_reply == "oversized" else json.dumps({
                "status": "accepted", "request_ref": "req-wrong", "private": "PRIVATE_SENTINEL"}).encode()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": body})
        async def aclose(self):
            pass
    monkeypatch.setattr(app_module, "create_release_control_app", lambda _: Damaged())
    async def exercise():
        async with connection(settings) as client:
            reply, result = await native.call(client, native.fixture._submit_token(rsa_key),
                                             "submit_ceo_intent", native.PAYLOAD)
            assert result["status"] == "effect_unknown"
            assert result["request_ref"] == app_request_ref(native.PAYLOAD["operation_key"])
            assert reply["isError"] is True
            assert "PRIVATE_SENTINEL" not in str(reply)
    asyncio.run(exercise())


def test_one_app_client_reads_create_no_lifecycle_and_submit_creates_one_job(
    settings, rsa_key, tmp_path, short_socket_root, monkeypatch,
):
    from control_plane.executive_service import (
        ExecutiveControlService, CeoIngressAppBinding, CEO_WEB_CEO_V2_READ_SCHEMA,
    )
    created = []
    original_init = CeoIngressClient.__init__
    def counted(self, *args, **kwargs):
        created.append(self)
        original_init(self, *args, **kwargs)
    monkeypatch.setattr(CeoIngressClient, "__init__", counted)
    async def exercise():
        readers = web_ceo.WebCeoV2InstalledExecutiveReaders(
            repo_root=Path(settings.mastermind_root), macro_root=Path(settings.macro_root_flag),
            runtime_root=tmp_path / "runtime")
        service = ExecutiveControlService(
            native.fixture._service_config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda _: native.fixture._NoExecutionSupervisor(),
            ceo_ingress_socket_path=settings.ceo_ingress_socket_path,
            ceo_ingress_peer_uid=os.geteuid() + 1000, ceo_ingress_grounding_provider=readers,
            ceo_ingress_armed=False, ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=True, grounding_provider=readers, read_provider=readers,
                read_schema=CEO_WEB_CEO_V2_READ_SCHEMA))
        readers.bind_fabric_source(
            bounded_runtime=lambda: service._namespace_custody.bound_runtime(service._require_runtime()),
            armed={}, runtime_identity={"root": None, "db_present": True, "identity": None})
        await service.start()
        try:
            bound = dataclasses.replace(settings, read_from_ceo_ingress=True,
                mastermind_root=tmp_path / "no-network-checkout", macro_root_flag=None)
            async with connection(bound) as client:
                assert len(created) == 1
                before = counts(service.runtime)
                for token in (native.fixture._read_token(rsa_key), native.fixture._submit_token(rsa_key)):
                    for name, args in (("executive_state", {}), ("executive_inbox", {}),
                                       ("executive_fabric", {"view": "roots"})):
                        _, result = await native.call(client, token, name, args)
                        assert result["ok"] is True, result
                        assert result["server_version"] == "1.2.0"
                assert counts(service.runtime) == before
                token = native.fixture._submit_token(rsa_key)
                _, accepted = await native.call(client, token, "submit_ceo_intent", native.PAYLOAD)
                assert accepted["status"] == "accepted", accepted
                receipt = accepted["receipt"]
                assert receipt["status"] == "QUEUED" and receipt["dispatched"] is False
                after = counts(service.runtime)
                for name, args in (("executive_job", {"job_id": receipt["job_id"]}),
                                   ("ceo_intent_status", {"intent_id": receipt["intent_id"]})):
                    _, result = await native.call(client, token, name, args)
                    assert result["ok"] is True, result
                assert counts(service.runtime) == after
                _, duplicate = await native.call(client, token, "submit_ceo_intent", native.PAYLOAD)
                assert duplicate["receipt"]["duplicate"] is True
                assert duplicate["receipt"]["job_id"] == receipt["job_id"]
                _, conflict = await native.call(client, token, "submit_ceo_intent", {**native.PAYLOAD, "priority": 99})
                assert conflict["status"] == "operation_conflict"
                response = await client.post("/v1/tools/submit_ceo_intent/reconcile", headers=native.headers(token),
                    json={"request_ref": accepted["request_ref"]})
                assert response.status_code == 200
                assert response.json()["receipt"]["job_id"] == receipt["job_id"]
                assert len(service.runtime.jobs.list_jobs()) == 1
                assert service.runtime.attempts.list_attempts() == []
        finally:
            await readers.aclose()
            await service.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("names", [None, [], "approve_release_transition", (1,),
    ("unknown",), ("approve_release_transition",), tuple(release.ARGS) * 2])
def test_generic_helper_refuses_unqualified_release_inventory(settings, names):
    def forbidden(_):
        pytest.fail("invalid static inventory constructed an App")
    with pytest.raises(ValueError, match="release tool names"):
        server._build_profile_mcp_app(settings, audit_sink=native.Sink(),
            profile_server_name="test", profile_server_version="1.2.0", profile_tools=(),
            profile_validator=lambda *a: {}, profile_create_app=forbidden, release_tool_names=names)


@pytest.mark.parametrize("name,args", [
    ("dispatch_job", {}),
    ("executive_state", {"principal": {}}),
    ("approve_release_transition", {**release.ARGS["approve_release_transition"], "principal": {}}),
    ("submit_ceo_intent", {**native.PAYLOAD, "profile": "release_control_v1"}),
])
def test_combined_arguments_never_select_authority(settings, rsa_key, monkeypatch, name, args):
    async def forbidden(*a, **k):
        pytest.fail("caller-authored authority reached ingress")
    monkeypatch.setattr(CeoIngressClient, "send_frame", forbidden)
    async def exercise():
        async with connection(settings) as client:
            _, value = await native.call(client, native.fixture._submit_token(rsa_key), name, args)
            assert value["ok"] is False
    asyncio.run(exercise())


@pytest.mark.parametrize("status,body", [
    (401, release.valid("approve_release_transition")),
    (403, {"ok": False, "error": {"code": "scope_refused", "message": "PRIVATE_SENTINEL"}}),
    (401, {"ok": False, "error": {"code": "not-a-public-auth-code"}}),
])
def test_release_contradictory_auth_cannot_become_no_effect(settings, rsa_key, monkeypatch, status, body):
    from starlette.responses import JSONResponse
    class Contradictory:
        async def __call__(self, scope, receive, send):
            await JSONResponse(body, status_code=status,
                headers={"www-authenticate": "PRIVATE_SENTINEL"})(scope, receive, send)
        async def aclose(self):
            pass
    monkeypatch.setattr(app_module, "create_release_control_app", lambda _: Contradictory())
    async def exercise():
        async with connection(settings) as client:
            reply, value = await native.call(client, native.fixture._submit_token(rsa_key),
                "approve_release_transition", release.ARGS["approve_release_transition"])
            assert value == release_control.unknown_release_result()
            assert "PRIVATE_SENTINEL" not in str(reply)
            assert "_meta" not in reply or not reply["_meta"]
    asyncio.run(exercise())


def test_combined_transport_keeps_literal_routes_and_preauth_bounds(settings, rsa_key, monkeypatch):
    def combined(configuration, *, audit_sink, **mounts):
        return server.build_web_ceo_release_mcp_app(
            dataclasses.replace(configuration, read_from_ceo_ingress=True),
            audit_sink=audit_sink, **mounts)
    monkeypatch.setattr(server, "build_executive_mcp_app", combined)
    native.test_native_routes_are_literal_private_and_bounded(settings, rsa_key)
    native.test_native_empty_post_guard_before_auth_and_http_contract(settings, rsa_key, monkeypatch)
