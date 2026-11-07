"""Two signed resources -> original COO/Workspace owners -> actual C/N child.

The publication fixture uses disposable Git/Runtime and declares inert sealed
host-source/PR/credential seams. HTTP is real ASGI/MCP; the private Control
boundary is an explicit same-process call. No AF_UNIX or installed host is used.
"""
import asyncio
import base64
from copy import deepcopy
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import jwt
import pytest

from common import coo_agentos_context_contract as wire
from control_plane.coo_principal_host import CooHostProvider, MISSION_AUTHORITY_VERSION
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, HERMES_NATIVE_CURRENT_CONTEXT_PROFILE_ID as PROFILE,
)
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp import server, coo as descriptors
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.coo import CooAppSettings, create_coo_app
from integrations.mastermind_executive_app.coo_binding import COO_SCOPES, BINDING_SCHEMA, _digest, principal_frame
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import workspace_authorizers, principal_frame as workspace_frame
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from tests import test_executive_coo_host as host_tests
from tests import test_executive_coo_app as app_tests
from tests.test_installed_current_agentos_context import (
    joined, owner, env, isolated_git_env, identity, context_child,
)

rsa_key = app_tests.rsa_key
ROOT = Path(__file__).parents[1]


@pytest.fixture
def signed(joined, monkeypatch, rsa_key):
    j = joined
    clock = [j["workspace"].issued_at + 5]
    after = [lambda: None]
    collector, calls = context_child(j, monkeypatch, after=lambda: after[0]())
    factory = j["factory"]
    policy = dataclasses.replace(factory.policies.read, policy_id="current-context-coo", required_scopes=COO_SCOPES)
    cache = app_tests.fixture._FakeJwksCache(rsa_key)
    def bearer(selected, **overrides):
        claims = dict(iss=selected.issuer, sub="inert-chairman", aud=selected.resource, client_id="inert-client",
            scope=" ".join(selected.required_scopes), iat=j["workspace"].issued_at,
            nbf=j["workspace"].issued_at, exp=j["workspace"].expires_at)
        claims.update(overrides)
        return jwt.encode(claims, rsa_key, algorithm="RS256", headers={"kid": app_tests.fixture.KID, "typ": "at+jwt"})
    token, second = bearer(policy), bearer(factory.workspace_policy)
    principal = asyncio.run(JwtAuthenticator(policy=policy, jwks_cache=cache).verify_token(token, now=clock[0]))
    host, coo, _, path = host_tests.setup(j["tmp_path"])
    raw = json.loads(path.read_bytes()); raw["profiles"][PROFILE]["enabled"] = True
    path.write_text(json.dumps(raw))
    registry = ExecutionCapabilityRegistry.load(path, source_root=ROOT)
    binding = dict(schema=BINDING_SCHEMA, enabled=True, binding={**principal_frame(principal), "permission_digest": "d" * 64})
    coo.update(policy=json.loads(json.dumps(dataclasses.asdict(policy))), binding=binding)
    work = j["args"]["work_ref"]
    coo["missions"][0].update(work_ref=work, principal_binding_digest=_digest(binding["binding"]),
        capability_profile_id=PROFILE, capability_profile_digest=registry.profiles[PROFILE].profile_digest,
        authority_version=MISSION_AUTHORITY_VERSION, principal_actions=[wire.CURRENT_ACTION])
    authorize, authorize_frame = workspace_authorizers(policy=factory.workspace_policy,
        load_bindings=lambda: legacy_workspace_document(j["document"], factory.workspace_policy))
    workspace_read = WorkspaceReadService(cache=None, runtime=j["runtime"], authorize=authorize_frame,
        armed={}, runtime_identity={}, canonical_project_data=j["data"].installed_binding())
    provider = CooHostProvider(host.source, workspace_read)
    def authority(who, work_ref):
        return provider.source.for_principal(principal_frame(who), work_ref)[2]
    def context(who, workspace, context, digest):
        return provider.read_current_agentos_context(dict(schema=wire.CURRENT_FRAME_SCHEMA,
            principal=principal_frame(who), workspace_principal=workspace_frame(workspace),
            principal_context=dataclasses.asdict(context), capability_profile_digest=digest))
    sink = app_tests.Sink()
    wauth = JwtAuthenticator(policy=factory.workspace_policy, jwks_cache=cache)
    config = WorkspaceAppConfig(authenticator=wauth, now=lambda: clock[0], authorize_principal=authorize,
        client=CeoIngressWorkspaceClient(j["tmp_path"] / "never-opened.sock"))
    verifier = MastermindTokenVerifier(authenticator=wauth, policy=factory.workspace_policy,
        now=config.now, audit_sink=sink)
    workspace_app = server.AuditedWorkspaceApp(create_workspace_app(config), verifier,
        authenticator=wauth, authorize_principal=authorize, fresh_workspace_config=config)
    base = AppSettings(policies=factory.policies, mastermind_root=j["source_root"], macro_root_flag=None,
        environ={}, ceo_ingress_socket_path=j["tmp_path"] / "never-opened.sock", read_from_ceo_ingress=True,
        jwks_cache=cache, clock=lambda: clock[0])
    settings = CooAppSettings(executive=base, policy=policy, load_binding=lambda: coo["binding"],
        authority_provider=authority, mission_provider=lambda *a: pytest.fail("no mission mutation"),
        catalogue_provider=lambda who, work_ref=None: provider.source.catalogue_for_principal(
            principal_frame(who), work_ref=work_ref), agentos_current_context_provider=context)
    app = create_coo_app(settings, audit_sink=sink, workspace_app=workspace_app)
    return locals()


async def request(s, headers=None):
    if headers is None:
        headers = [("authorization", "Bearer " + s["token"]),
                   ("x-mastermind-workspace-authorization", "Bearer " + s["second"])]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s["app"]), base_url="http://127.0.0.1") as client:
        return await client.post("/v1/tools/" + wire.CURRENT_TOOL, headers=headers,
            json={"arguments": {"work_ref": s["work"]}})


def test_signed_current_read_keeps_actual_compiler_bytes_and_canonical_event(signed):
    s = signed; j = s["j"]
    before = j["runtime"].events.list_events()
    response = asyncio.run(request(s))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    raw, receipt = wire.validate_current_result(data, expected_context=data["principal_context"],
        capability_profile_digest=s["registry"].profiles[PROFILE].profile_digest,
        expected_workspace_principal=workspace_frame(j["workspace"]))
    assert raw == s["calls"][0][1]["stdout"].encode()
    assert receipt["compiler_code_commit"] == j["code"] != receipt["data_commit"] == j["current"]
    assert receipt["data_observation"]["source_operation"]["event_id"] == j["status"]["receipt"]["event_id"]
    assert j["runtime"].events.list_events() == before and not j["runtime"].jobs.list_jobs()
    assert all(token not in response.text + repr(s["sink"].events) for token in (s["token"], s["second"]))
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("bad", ["missing", "duplicate", "coo_resource", "scope", "expired", "client", "enrolled_client", "subject", "no_stamp"])
def test_second_resource_refuses_before_the_compiler(signed, monkeypatch, bad):
    s = signed
    second = s["second"]
    if bad == "coo_resource": second = s["token"]
    if bad in {"scope", "expired", "client", "enrolled_client", "subject"}:
        changes = {"scope": {"scope": "mastermind.executive.read"}, "expired": {"exp": s["clock"][0] - 40},
            "client": {"client_id": "different-enrolled-client"}, "enrolled_client": {"client_id": "another-client"},
            "subject": {"sub": "someone-else"}}
        second = s["bearer"](s["factory"].workspace_policy, **changes[bad])
    if bad == "enrolled_client":
        other = asyncio.run(s["wauth"].verify_token(second, now=s["clock"][0]))
        document = s["j"]["document"]
        slot = deepcopy(document["profiles"][document["primary_profile"]])
        slot["binding"] = {**workspace_frame(other), "permission_digest": "f" * 64}
        document["profiles"]["other-member"] = slot
        assert s["authorize"](other) is True
    headers = [("authorization", "Bearer " + s["token"])]
    if bad != "missing": headers.append(("x-mastermind-workspace-authorization", "Bearer " + second))
    if bad == "duplicate": headers.append(headers[-1])
    if bad == "no_stamp": monkeypatch.setattr(s["authorize"], "binding_digest", None)
    response = asyncio.run(request(s, headers))
    assert response.status_code in {403, 503}, response.text
    assert "data" not in response.json() and not s["calls"]


@pytest.mark.parametrize("bad", ["read", "latest", "stamp", "mission", "clock", "workspace_owner", "runtime"])
def test_changed_owner_or_grant_discards_completed_context(signed, monkeypatch, bad):
    s = signed; j = s["j"]
    slot = j["document"]["profiles"][j["document"]["primary_profile"]]
    def after():
        if bad == "read": slot["enabled"] = False
        elif bad == "latest": slot["project_canonical_data_read"] = None
        elif bad == "stamp": slot["binding"]["permission_digest"] = "e" * 64
        elif bad == "mission": s["coo"]["missions"][0]["enabled"] = False
        elif bad == "clock": s["clock"][0] = j["workspace"].expires_at
        elif bad == "workspace_owner": s["app"]._context_workspace_app = None
        elif bad == "runtime": s["workspace_read"].runtime = SimpleNamespace(store=j["runtime"].store)
    s["after"][0] = after
    response = asyncio.run(request(s))
    assert response.status_code in {403, 503}, response.text
    assert "data" not in response.json() and len(s["calls"]) == 1


@pytest.mark.parametrize("bad", ["coo_permission", "expiry"])
def test_last_workspace_await_cannot_release_stale_executive_authority(signed, monkeypatch, bad):
    s = signed
    verify = s["wauth"].verify_token
    async def at_last_await(*args, **kwargs):
        principal = await verify(*args, **kwargs)
        if s["calls"]:
            if bad == "coo_permission":
                s["coo"]["binding"]["binding"]["permission_digest"] = "f" * 64
            else:
                s["clock"][0] = s["principal"].expires_at
        return principal
    monkeypatch.setattr(s["wauth"], "verify_token", at_last_await)
    response = asyncio.run(request(s))
    assert response.status_code in {403, 503} and "data" not in response.json()
    assert len(s["calls"]) == 1


@pytest.mark.parametrize("bad", [None, "workspace_echo", "transport_replaced"])
def test_current_private_wire_retains_original_client_and_neutral_pair(signed, monkeypatch, bad):
    from integrations.mastermind_executive_app.coo_installed import CooFactsClient
    from control_plane.coo_principal_envelope import PrincipalAdmissionContext
    s = signed
    _, fact, authority = s["provider"].source.for_principal(principal_frame(s["principal"]), s["work"])
    context = PrincipalAdmissionContext(s["work"], fact.principal_binding_digest,
        authority.mission_authority_ref, authority.authority_generation_digest)
    client = CooFactsClient(s["j"]["tmp_path"] / "in-memory-only.sock")
    sent, closed, opens = [], [], []
    class Reader:
        async def readuntil(self, separator):
            assert separator == b"\n"
            frame = wire.decode(sent[0], limit=wire.MAX_REQUEST_BYTES)
            value = s["provider"].read_current_agentos_context(frame)
            if bad == "workspace_echo": value["workspace_principal"]["client_ref"] = "f" * 64
            if bad == "transport_replaced": client._client.socket_path = Path("/different-not-opened.sock")
            return wire.encode({"ok": True, "result": value}) + b"\n"
    class Writer:
        def write(self, raw): sent.append(raw)
        async def drain(self): pass
        def close(self): closed.append(True)
        async def wait_closed(self): pass
    async def in_memory(path, *, limit):
        opens.append((path, limit)); return Reader(), Writer()
    monkeypatch.setattr(asyncio, "open_unix_connection", in_memory)
    async def exercise():
        workspace = await s["wauth"].verify_token(s["second"], now=s["clock"][0])
        return await client.agentos_current_context(s["principal"], workspace, context,
            authority.capability_profile_digest)
    if bad is None:
        value = asyncio.run(exercise())
        assert base64.b64decode(value["bundle_base64"]) == s["calls"][0][1]["stdout"].encode()
    else:
        with pytest.raises(ValueError): asyncio.run(exercise())
    assert len(opens) == len(sent) == len(closed) == 1 and opens[0][1] == wire.MAX_RESPONSE_BYTES
    assert all(token.encode() not in sent[0] for token in (s["token"], s["second"]))


def test_original_mcp_mount_transports_both_resources_and_exact_metadata(signed):
    s = signed
    async def unused(*a, **kw): pytest.fail("unrelated owner")
    app = server.build_web_ceo_v3_with_coo_mcp_app(s["base"], coo_settings=s["settings"],
        audit_sink=s["sink"], mdm_reader=SimpleNamespace(list_macos_devices=unused, device=unused),
        session_target_projector=unused, session_reply_handler=unused, session_summon_handler=unused,
        workspace_app=s["workspace_app"])
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                headers = [("authorization", "Bearer " + s["token"]), ("accept", "application/json, text/event-stream"),
                    ("x-mastermind-workspace-authorization", "Bearer " + s["second"])]
                body = dict(jsonrpc="2.0", id=1, method="tools/call",
                    params=dict(name=wire.CURRENT_TOOL, arguments={"work_ref": s["work"]}))
                response = await client.post("/mcp/coo", headers=headers, json=body)
                payload = response.json()["result"]
                assert response.status_code == 200 and payload["isError"] is False, payload
                data = json.loads(payload["content"][0]["text"])["data"]
                assert base64.b64decode(data["bundle_base64"]) == s["calls"][0][1]["stdout"].encode()
                refused = await client.post("/mcp/coo", headers=headers + [headers[-1]], json=body)
                assert refused.json()["result"]["isError"] is True and len(s["calls"]) == 1
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.mastermind-x.com") as client:
                path = urlsplit(s["factory"].workspace_policy.resource_metadata_url).path
                metadata = await client.get(path)
                assert metadata.status_code == 200, metadata.text
                assert metadata.json()["resource"] == s["factory"].workspace_policy.resource
                assert metadata.json()["scopes_supported"] == list(s["factory"].workspace_policy.required_scopes)
                challenge = await client.get("/workspace/native-draft-identity/current")
                assert challenge.status_code == 401
                assert s["factory"].workspace_policy.resource_metadata_url in challenge.headers["www-authenticate"]
                identity = await client.get("/workspace/native-draft-identity/current",
                    headers={"authorization": "Bearer " + s["second"]})
                assert identity.status_code == 200 and identity.json()["schema"] == "mastermind.native_draft_identity.v1"
    asyncio.run(exercise())
