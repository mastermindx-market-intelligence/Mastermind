"""Native JSON-RPC with real JWT verification; synthetic owner facts only."""
import asyncio
import copy
import dataclasses
import hashlib
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from control_plane import executive_release_contract as contract
from control_plane import executive_release_ingress as ingress
from integrations.executive_mcp import release_control as profile, server
from integrations.mastermind_executive_app import app as app_module
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, CeoIngressResponse, TRANSPORT_SENT_OK,
    TRANSPORT_NOT_SENT, TRANSPORT_SENT_UNKNOWN,
)
from tests import test_executive_mcp_app_composition as native
from tests.test_executive_release_consumer import installed, inputs, approve_arguments, counts

rsa_key = native.rsa_key
short_socket_root = native.short_socket_root
settings = native.settings
KEY = "release-mcp-proof-001"
ARGS = {
    "approve_release_transition": {"operation_key": KEY, "action": "executive.release.upgrade", "transition_digest": "a" * 64},
    "prepare_release_transition": {"operation_key": KEY, "approved_transition_ref": contract.approval_ref_for(KEY)},
    "commit_prepared_release_transition": {"prepared_token": "inert-test-token"},
    "reconcile_release_transition": {"operation_key": KEY},
}


def valid(operation):
    result = {"schema": ingress.RESPONSE_SCHEMA, "operation": operation, "ok": True}
    if operation == "approve_release_transition":
        result.update(approved_transition_ref=contract.approval_ref_for(KEY), approval_evidence_digest="b" * 64)
    elif operation == "prepare_release_transition":
        result.update(preview={"action": "executive.release.upgrade", "target_ref": "c" * 64,
                              "from_release": "d" * 40, "to_release": "e" * 40},
                      prepared_token="inert-token", expires_at_ms=123456789)
    elif operation == "reconcile_release_transition":
        result.update(approval=None, broker_status=None)
    else:
        result.update(ok=False, error={"code": "RELEASE_COMMIT_DISARMED"})
    return result


@asynccontextmanager
async def connection(settings):
    app = server.build_release_control_mcp_app(
        dataclasses.replace(settings, read_from_ceo_ingress=True), audit_sink=native.Sink())
    async with app._app.router.lifespan_context(app._app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            yield client


def test_discovery_auth_and_closed_routes(settings, rsa_key, monkeypatch):
    frames = []
    async def send(self, path, frame):
        frames.append(frame)
        return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=valid(frame["operation"]))
    monkeypatch.setattr(CeoIngressClient, "send_frame", send)
    async def exercise():
        async with connection(settings) as client:
            token = native.fixture._submit_token(rsa_key)
            tools = (await native.rpc(client, token, "tools/list"))["tools"]
            assert [t["name"] for t in tools] == list(ARGS)
            for t in tools:
                assert t["annotations"]["readOnlyHint"] is (t["name"] in ("prepare_release_transition", "reconcile_release_transition"))
                assert t["securitySchemes"][0]["scopes"] == list(settings.policies.submit.required_scopes)
            for denied in (None, native.fixture._read_token(rsa_key),
                           native.fixture._submit_token(rsa_key, iat=native.fixture.NOW-800, exp=native.fixture.NOW-100)):
                headers = native.headers(denied) if denied else {"accept": "application/json, text/event-stream"}
                response = await client.post("/mcp", headers=headers,
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                        "name": "approve_release_transition", "arguments": ARGS["approve_release_transition"]}})
                assert response.status_code in (401, 403)
                assert "www-authenticate" in response.headers
            assert not frames
            for name, args in (("executive_state", {}), ("approve_release_transition", {**ARGS["approve_release_transition"], "principal": {}}),
                               ("approve_release_transition", {**ARGS["approve_release_transition"], "action": []})):
                _, result = await native.call(client, token, name, args)
                assert result["ok"] is False
            assert not frames
            for route in ("/v1/tools/submit_ceo_intent/reconcile", "/workspace/programs/current", "/os"):
                assert (await client.post(route, headers=native.headers(token), json={})).status_code == 404
    asyncio.run(exercise())


@pytest.mark.parametrize("operation", list(ARGS))
def test_valid_calls_forward_once_with_authenticated_projection(settings, rsa_key, monkeypatch, operation):
    frames = []
    async def send(self, path, frame):
        frames.append(frame)
        return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=valid(operation))
    monkeypatch.setattr(CeoIngressClient, "send_frame", send)
    async def exercise():
        token = native.fixture._submit_token(rsa_key)
        async with connection(settings) as client:
            _, result = await native.call(client, token, operation, ARGS[operation])
            assert result == valid(operation)
        assert len(frames) == 1 and frames[0]["operation"] == operation
        assert frames[0]["arguments"] == ARGS[operation]
        assert frames[0]["principal"]["subject_digest"]
        assert token not in str(frames) and "jti_digest" not in frames[0]["principal"]
    asyncio.run(exercise())


@pytest.mark.parametrize("transport,expected", [(TRANSPORT_NOT_SENT, {"ok": False, "error": {"code": "RELEASE_TRANSPORT_UNAVAILABLE"}, "effect": "NONE"}),
                                                (TRANSPORT_SENT_UNKNOWN, profile.unknown_release_result())])
def test_transport_effects_are_preserved(settings, rsa_key, monkeypatch, transport, expected):
    calls = []
    async def send(self, *args):
        calls.append(1)
        return CeoIngressResponse(transport=transport, ok=False)
    monkeypatch.setattr(CeoIngressClient, "send_frame", send)
    async def exercise():
        async with connection(settings) as client:
            _, result = await native.call(client, native.fixture._submit_token(rsa_key), "approve_release_transition", ARGS["approve_release_transition"])
            assert result == expected
        assert len(calls) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("operation", list(ARGS))
def test_transport_rejects_bad_inner_app_results(settings, rsa_key, monkeypatch, operation):
    # Replace only the App reply, below real outer JWT verification, so this
    # specifically tests the MCP boundary rather than the App's own validator.
    original = valid(operation)
    bad = [{**original, "private": "PRIVATE_SENTINEL"}, {**original, "operation": "wrong"},
           {"ok": False, "error": {"code": "PRIVATE_SENTINEL"}},
           {**original, "ok": True, "private": "x" * 300000}]
    if operation == "approve_release_transition":
        bad += [{**original, "approved_transition_ref": "wrong"}, {**original, "approval_evidence_digest": {}}]
    if operation == "prepare_release_transition":
        bad += [{**original, "expires_at_ms": True}, {**original, "prepared_token": {}},
                {**original, "preview": {**original["preview"], "target_ref": "bad"}}]
    if operation == "commit_prepared_release_transition":
        bad += [{"schema": ingress.RESPONSE_SCHEMA, "operation": operation, "ok": True}]
    async def exercise():
        for value in bad:
            class Inner:
                async def __call__(self, scope, receive, send):
                    from starlette.responses import JSONResponse
                    await JSONResponse(value)(scope, receive, send)
                async def aclose(self):
                    pass
            monkeypatch.setattr(app_module, "create_release_control_app", lambda settings: Inner())
            async with connection(settings) as client:
                _, result = await native.call(client, native.fixture._submit_token(rsa_key), operation, ARGS[operation])
                assert result == profile.unknown_release_result()
                assert "PRIVATE_SENTINEL" not in str(result)
    asyncio.run(exercise())


def test_selector_and_optional_mounts_preserve_defaults():
    from integrations.executive_mcp import web_ceo, web_ceo_v3
    from ops.executive_os import executive_mcp_entry as entry
    assert web_ceo_v3.validate_installed_mcp_profile_current() == "legacy"
    assert web_ceo_v3.validate_installed_mcp_profile_current(profile.RELEASE_CONTROL_PROFILE) == profile.RELEASE_CONTROL_PROFILE
    with pytest.raises(ValueError):
        web_ceo.validate_installed_mcp_profile(profile.RELEASE_CONTROL_PROFILE)
    raw = {"schema": entry.CONFIG_SCHEMA, "release_sha": "a" * 40, "service_uid": 458,
           "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock", "port": 8444,
           "policies": {}, "audit_root": "/var/log/mastermind-executive/mcp-auth"}
    assert entry.validate_document(raw) == raw
    selected = {**raw, "executive_mcp_profile": profile.RELEASE_CONTROL_PROFILE}
    assert entry.validate_document(selected) == selected
    for name in ("workspace", "steward"):
        with pytest.raises(ValueError, match="refuses optional mounts"):
            entry.validate_document({**selected, name: {}})


@pytest.mark.parametrize("history_state", [
    "NOT_FOUND", "STARTED", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING",
    "SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED",
])
def test_durable_approval_lost_readback_and_typed_history_over_native_mcp(
        installed, rsa_key, tmp_path, short_socket_root, monkeypatch, history_state):
    from control_plane import executive_release_consumer as consumer
    from control_plane.executive_authority import ReleaseControllerPolicy
    from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
    from integrations.business_mcp_auth.principal_projection import principal_projection
    from integrations.mastermind_executive_app.gateway import make_jwt_authenticators
    from tests.test_executive_release_controller_policy import source
    web = native.fixture
    async def exercise():
        installed["now"][0] = web.NOW * 1000
        settings = dataclasses.replace(web._real_app_settings(rsa_key, mastermind_root=tmp_path,
            macro_root=tmp_path, ceo_ingress_socket_path=short_socket_root / "mcp-release.sock"),
            read_from_ceo_ingress=True, clock=lambda: installed["now"][0] // 1000)
        token = web._submit_token(rsa_key)
        _, verifier = make_jwt_authenticators(settings.policies, jwks_cache=settings.jwks_cache)
        principal = principal_projection(await verifier.verify_authorization_header("Bearer " + token, now=web.NOW))
        prior = installed["states"][0]
        policy = ReleaseControllerPolicy.from_bytes(source({
            "schema": "mastermind.executive_release_controller_policy/v1", "policy_id": principal.policy_id,
            "generation": 1, "enabled": True, "issuer_digest": principal.issuer_digest,
            "resource_digest": hashlib.sha256(principal.resource.encode()).hexdigest(),
            "subject_digests": [principal.subject_digest], "client_refs": [principal.client_ref],
            "required_scopes": list(principal.scopes), "actions": [prior.effect["action"]],
            "target_refs": [prior.target_ref], "installer_profile_digests": [prior.effect["installer_profile_digest"]],
            "source_policy_modes": [prior.effect["source_policy_mode"]],
            "max_approval_lifetime_seconds": 300, "confirmation_requirement": "delegated"}))
        installed["states"][0] = dataclasses.replace(prior, policy=policy,
            preconditions={**prior.preconditions, "authority_policy_hash": policy.sha256})
        class NoReads:
            def observe(self):
                pytest.fail("no read gateway required")
            async def call(self, *args):
                pytest.fail("no read gateway required")
            async def aclose(self):
                pass
        readers = NoReads()
        service = ExecutiveControlService(web._service_config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda _: web._NoExecutionSupervisor(), service_state="READY",
            ceo_ingress_socket_path=settings.ceo_ingress_socket_path,
            ceo_ingress_peer_uid=os.geteuid() + 1000, ceo_ingress_grounding_provider=readers,
            ceo_ingress_armed=False, ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=False, grounding_provider=readers, read_provider=readers))
        # These two future producer/registry seams are synthetic. JWT, Unix
        # transport, original approval Event and read-only consumer are real.
        from tests.test_executive_release_consumer import typed_history
        projected, admission_reads = [], []
        def project_history(approval):
            status = typed_history(approval, history_state, installed["states"][0].preconditions)
            projected.append(status)
            return status
        installed["history_projection"][0] = project_history
        def read_admission(connection, *, approved_transition_ref, request_fingerprint):
            status = projected[-1]
            assert approved_transition_ref == status["approved_transition_ref"]
            assert request_fingerprint == status["request_fingerprint"]
            connection.execute("SELECT 1").fetchone()
            admission_reads.append(approved_transition_ref)
            return copy.deepcopy(status["admission"])
        original_read, lost = consumer.ReleaseControlConsumer._read, []
        def lose_once(self, key):
            value = original_read(self, key)
            if value is not None and not lost:
                lost.append(True)
                return None
            return value
        monkeypatch.setattr(consumer.ReleaseControlConsumer, "_read", lose_once)
        await service.start()
        try:
            monkeypatch.setattr(service.runtime.release_maintenance, "read_admission", read_admission, raising=False)
            before = counts(service.runtime)
            args = approve_arguments(installed)
            async with connection(settings) as client:
                _, result = await native.call(client, token, "approve_release_transition", args)
                assert result["error"]["code"] == "RELEASE_APPROVAL_READBACK_UNKNOWN"
                assert result["effect"] == "EFFECT_UNKNOWN"
                _, history = await native.call(client, token, "reconcile_release_transition", {"operation_key": args["operation_key"]})
                if history_state in {"STARTED", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING"}:
                    assert history["ok"] is False and history["effect"] == "EFFECT_UNKNOWN"
                    assert history["error"]["code"] == "RELEASE_EFFECT_IN_PROGRESS"
                else:
                    assert history["ok"] and history["approval"]["operation_key"] == args["operation_key"]
                    assert history["broker_status"]["state"] == history_state
                assert len(admission_reads) == (0 if history_state == "NOT_FOUND" else 1)
                _, prepared = await native.call(client, token, "prepare_release_transition", {
                    "operation_key": args["operation_key"], "approved_transition_ref": contract.approval_ref_for(args["operation_key"])})
                assert prepared["ok"]
                _, refused = await native.call(client, token, "commit_prepared_release_transition", {"prepared_token": prepared["prepared_token"]})
                assert refused["error"]["code"] == "RELEASE_COMMIT_DISARMED"
            assert counts(service.runtime) == (before[0] + 1, before[1], before[2])
            assert installed["root_broker"]._executor.calls == []
        finally:
            await service.close()
    asyncio.run(exercise())
