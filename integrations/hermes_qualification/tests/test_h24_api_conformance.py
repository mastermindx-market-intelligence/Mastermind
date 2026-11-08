"""H24-04: real incumbent entrypoints, disposable signatures and Unix owners.

No network OAuth, provider, live worker, installation or production service is
used. The temporary Executive fixture has a non-dispatching supervisor. Existing
test fixtures supply owner data; no handler/auth implementation is copied here.
"""
from __future__ import annotations

import sys
import unittest

# The existing lightweight Hermes CI profile uses stdlib unittest discovery.
# These integration functions require pytest and its explicit dependency profile;
# unittest cannot execute them. Do not conceal missing imports in a pytest run.
if "pytest" not in sys.modules:
    raise unittest.SkipTest(
        "H24-04 is a pytest-only integration suite; run python -m pytest "
        "integrations/hermes_qualification/tests/test_h24_api_conformance.py"
    )

import asyncio
import copy
import dataclasses
import hashlib
import json
import subprocess
from pathlib import Path
from contextlib import asynccontextmanager

import httpx
import jwt
import pytest

from control_plane import executive_ceo_ingress as ingress
from control_plane.coo_principal_request import (
    normalize_principal_request, principal_request_ref,
)
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.executive_runtime import Runtime, RuntimeReadBinding
from integrations.business_mcp_auth.contracts import AuthError
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp.coo import COO_TOOL_SPECS, validate_coo_tool_arguments
from integrations.executive_mcp import e1_http as http_boundary
from integrations.executive_mcp import server as mcp_server
from integrations.executive_mcp.server import (
    AuditedWorkspaceApp, _mounted_lifespan, build_executive_mcp_app,
    build_coo_mcp_app, build_web_ceo_v2_with_coo_mcp_app,
    build_principal_ruling_mcp_app,
)
from integrations.executive_mcp.schemas import GatewayError
from integrations.hermes_qualification.api_conformance import (
    CEO_RESOURCE, COO_RESOURCE, FIXTURE_ISSUER, FIXTURE_NOW, MISSION_PATH,
    FixtureAudit, FixtureIdentity, FixturePublicKeys, ObservedAsgiTransport,
    authenticator, fixture_policy, permission_receipt, route_resource_matrix,
    rpc, rpc_headers, signed_asgi_client, tool_payload,
)
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.coo import CooAppSettings, create_coo_app
from integrations.mastermind_executive_app.coo_binding import (
    BINDING_SCHEMA, COO_BINDING_SCHEMA_V2, COO_SCOPES, _digest, principal_frame as coo_frame,
    validate_coo_binding,
)
from integrations.mastermind_executive_app.gateway import AppPolicies, CeoIngressClient, CeoIngressResponse
from integrations.mastermind_executive_app.principal_ruling_http import PrincipalRulingTarget
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import (
    MEMBER_BINDINGS_SCHEMA, principal_frame, workspace_authorizers,
)
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.secretary_team_access.client import SecretaryAccessClient
from tests import test_coo_principal_mandate as mandate_fixture
from tests import test_executive_coo_host as host_fixture
from tests import test_executive_principal_ingress as ingress_fixture
from tests import test_executive_principal_dialogue_forward as ruling_fixture
from tests import test_mission_workspace as mission_fixture
from tests import test_principal_current_reader as current_source_fixture
from tests import test_principal_decision_source_fence as decision_fence_fixture
from tests.test_workspace_read_socket import control, short_socket_root  # noqa: F401
from tests.test_executive_runtime_bounded_read import ObservationNamespace
from tests.test_workspace_mission_result_service import mission_owner as result_owner  # noqa: F401


@pytest.fixture(scope="module")
def identities():
    return (FixtureIdentity.generate("gb1"), FixtureIdentity.generate("secretary"))


def request_body(**changes):
    return {"operation_key": "h24-original-operation", "objective": "Inspect the assigned mission.",
            "department": "executive", "priority": 1, "execution_profile": "research_only",
            "workstream": "WS:ONE", **changes}


def original_ref(payload=None):
    value = request_body() if payload is None else payload
    return principal_request_ref(normalize_principal_request(
        value, expected_work_ref=value["workstream"]))


def executive_settings(tmp_path, identities, keys, socket_path):
    return AppSettings(
        policies=AppPolicies(fixture_policy(identities, facet="ceo_read"),
                             fixture_policy(identities, facet="ceo_submit")),
        mastermind_root=tmp_path, macro_root_flag=None, environ={},
        ceo_ingress_socket_path=socket_path, read_from_ceo_ingress=True,
        jwks_cache=keys, clock=lambda: FIXTURE_NOW,
    )


@asynccontextmanager
async def workspace_surface(owner, identities, tmp_path, socket_root, *, after_read=None):
    keys = FixturePublicKeys(identities)
    policy = fixture_policy(identities, facet="workspace")
    auth = authenticator(policy, keys)
    tokens = {i.label: i.token(policy) for i in identities}
    principals = {i.label: await auth.verify_token(tokens[i.label], now=FIXTURE_NOW)
                  for i in identities}
    bindings = {"schema": MEMBER_BINDINGS_SCHEMA, "primary_profile": "gb1", "profiles": {
        label: {"enabled": True, "binding": {
            **principal_frame(principal), "permission_digest": permission_receipt(label)}}
        for label, principal in principals.items()
    }}
    app_auth, control_auth = workspace_authorizers(policy=policy, load_bindings=lambda: bindings)
    frames = []

    def bounded_reader(actual):
        assert actual is owner["writer"]
        # Each concurrent acquisition needs its own exclusive namespace binding.
        # The existing owner fixture keeps the SQLite/WAL namespace stable.
        return Runtime.at(actual.store.root, create=False, read_binding=RuntimeReadBinding(
            ObservationNamespace(actual.store.path)))

    def factory(actual):
        assert actual is owner["writer"]
        service = WorkspaceReadService(
            cache=owner["cache"], runtime=actual, authorize=control_auth,
            armed={}, runtime_identity={"db_present": True},
            bounded_runtime=bounded_reader,
        )
        if after_read is not None:
            original = service._read_mission_v3

            def observe(frame):
                result = original(frame)
                after_read(bindings)
                return result

            service._read_mission_v3 = observe
        return service

    service = control(tmp_path, socket_root, factory)
    service._runtime_factory = lambda path: owner["writer"]
    await service.start()
    actual_client = CeoIngressWorkspaceClient(service.ceo_ingress_socket_path)

    class ObservedClient:
        async def request(self, frame):
            frames.append(copy.deepcopy(frame))
            return await actual_client.request(frame)

    workspace = create_workspace_app(WorkspaceAppConfig(
        authenticator=auth, now=lambda: FIXTURE_NOW, authorize_principal=app_auth,
        client=ObservedClient(),
    ))
    audit = FixtureAudit()
    verifier = MastermindTokenVerifier(authenticator=auth, policy=policy,
                                      now=lambda: FIXTURE_NOW, audit_sink=audit)
    mounted = build_executive_mcp_app(
        executive_settings(tmp_path, identities, keys, service.ceo_ingress_socket_path),
        audit_sink=audit, workspace_app=AuditedWorkspaceApp(workspace, verifier))
    try:
        async with _mounted_lifespan(mounted):
            yield mounted, tokens, principals, bindings, frames, keys
    finally:
        await service.close()


@asynccontextmanager
async def coo_surface(tmp_path, identities, *, member=0, socket_path=None, after_read=None):
    keys = FixturePublicKeys(identities)
    policy = fixture_policy(identities, facet="coo_legacy")
    token = identities[member].token(policy)
    principal = await authenticator(policy, keys).verify_token(token, now=FIXTURE_NOW)
    state = {
        "binding": {"schema": BINDING_SCHEMA, "enabled": True, "binding": {
            **coo_frame(principal), "permission_digest": permission_receipt(identities[member].label)}},
        "authority": mandate_fixture.authority(work_ref="WS:ONE"),
        "mission": mandate_fixture._real_owner_mission(),
    }
    def mission_provider(principal, work):
        document = copy.deepcopy(state["mission"])
        if after_read is not None:
            after_read(state)
        return document

    settings = CooAppSettings(
        executive=executive_settings(tmp_path, identities, keys, socket_path or tmp_path / "absent.sock"),
        policy=policy, load_binding=lambda: state["binding"],
        authority_provider=lambda p, work: state["authority"],
        mission_provider=mission_provider,
    )
    core = create_coo_app(settings, audit_sink=FixtureAudit())
    try:
        yield core, settings, token, state, keys
    finally:
        await core.aclose()


@asynccontextmanager
async def ruling_surface(tmp_path, identities, *, member=0, response=None):
    async with coo_surface(tmp_path, identities, member=member) as data:
        core, _, token, state, _ = data
        state["authority"] = dataclasses.replace(state["authority"],
            principal_actions=("bounded_intent", "governed_orchestration"))
        # Reuse existing owner inputs and the real reducer. The ruling grammar
        # requires JOB-001, whereas the generic Mission fixture starts at JOB-1.
        args = mission_fixture._current_args_for_wrapper(
            mission_fixture._v3_inputs()["fabric_view"])
        args = json.loads(json.dumps(args).replace('"JOB-1"', '"JOB-001"'))
        responsibility = args["control_room"]["autonomy"]["responsibilities"][0]
        responsibility["accountable_seat"] = responsibility["owed_turn"]["seat"] = "coo"
        mission_fixture._refresh_observation_digests(args)
        state["mission"] = mandate_fixture.mw.compose_mission_workspace_v3(**args)
        recorder = ruling_fixture.Client(response=response)
        core._client = recorder
        target = PrincipalRulingTarget("WS:ONE", ruling_fixture.obligation_id(), ruling_fixture.SURFACE)
        app = build_principal_ruling_mcp_app(core, target=target)
        async with _mounted_lifespan(app):
            yield app, token, recorder, state


async def coo_call(core, token, tool, arguments):
    async with signed_asgi_client(core, token) as client:
        return await client.post("/v1/tools/" + tool, json={"arguments": arguments})


def test_two_keys_subjects_and_clients_really_differ(identities):
    async def run():
        policy = fixture_policy(identities, facet="workspace")
        keys = FixturePublicKeys(identities)
        auth = authenticator(policy, keys)
        principals = [await auth.verify_token(i.token(policy), now=FIXTURE_NOW) for i in identities]
        assert len({p.subject_digest for p in principals}) == 2
        assert len({p.client_ref for p in principals}) == 2
        assert len({i.public_jwk()["n"] for i in identities}) == 2
        assert all(p.issuer_digest == hashlib.sha256(FIXTURE_ISSUER.encode()).hexdigest()
                   for p in principals)
        # A valid-looking subject/client with the wrong cryptographic signature fails.
        claims = jwt.decode(identities[0].token(policy), options={"verify_signature": False})
        forged = jwt.encode(claims, identities[1]._key, algorithm="RS256",
                            headers={"kid": identities[0].kid, "typ": "at+jwt"})
        with pytest.raises(AuthError):
            await auth.verify_token(forged, now=FIXTURE_NOW)
    asyncio.run(run())


def test_distinct_signed_clients_concurrently_read_one_mission_and_revoke_independently(
    result_owner, identities, tmp_path, short_socket_root,
):
    owner = result_owner
    selected = {k: owner["selection"][k] for k in ("work_ref", "root_job_id")}

    async def run():
        async with workspace_surface(owner, identities, tmp_path, short_socket_root) as data:
            app, tokens, principals, bindings, frames, keys = data
            async with signed_asgi_client(app, tokens["gb1"], workspace=True) as gb1, signed_asgi_client(
                app, tokens["secretary"], workspace=True
            ) as secretary:
                before = len(owner["writer"].jobs.list_jobs())
                responses = await asyncio.gather(
                    gb1.get(MISSION_PATH, params=selected),
                    secretary.get(MISSION_PATH, params=selected))
                for response in responses:
                    assert response.status_code == 200, response.text
                    body = response.json()
                    assert body["schema"] == "mastermind.mission_workspace.v3"
                    assert body["read_state"]["state"] == "CURRENT", json.dumps({
                        "read_state": body["read_state"], "source": body["source"]})
                    assert body["program"]["work_ref"] == selected["work_ref"]
                    assert body["mission"]["root_job_id"] == selected["root_job_id"]
                    assert response.headers["cache-control"] == "no-store"
                refs = [response.json()["result_refs"] for response in responses]
                # Each acquisition has its own observation identity; compare the
                # actual results and require a stable generation within each read.
                results = [{k: v for k, v in value.items() if k != "generation"}
                           for value in refs]
                assert results[0] == results[1]
                for value in refs:
                    receipt = value["generation"]
                    assert receipt["before"] == receipt["after"]
                    assert receipt["source_identity"]

                assert {f["principal"]["subject_digest"] for f in frames} == {
                    p.subject_digest for p in principals.values()}
                assert {f["principal"]["client_ref"] for f in frames} == {
                    p.client_ref for p in principals.values()}
                assert all(f["principal"]["scopes"] == ["mastermind.workspace.read"] for f in frames)
                assert set(keys.calls) == {i.kid for i in identities}
                bindings["profiles"]["gb1"]["enabled"] = False
                denied = await gb1.get(MISSION_PATH, params=selected)
                assert denied.status_code == 403
                assert denied.json()["error"]["code"] == "access_denied"
                survivor = await secretary.get(MISSION_PATH, params=selected)
                assert survivor.status_code == 200, survivor.text
                assert len(owner["writer"].jobs.list_jobs()) == before
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["permission", "subject", "disable"])
def test_mid_read_same_subject_and_permission_continuity(
    result_owner, identities, tmp_path, short_socket_root, fault,
):
    changed = []

    def mutate(bindings):
        changed.append(fault)
        slot = bindings["profiles"]["secretary"]
        if fault == "permission":
            slot["binding"]["permission_digest"] = permission_receipt("rotated")
        elif fault == "subject":
            slot["binding"]["subject_digest"] = bindings["profiles"]["gb1"]["binding"]["subject_digest"]
        else:
            slot["enabled"] = False

    async def run():
        async with workspace_surface(result_owner, identities, tmp_path, short_socket_root,
                                     after_read=mutate) as data:
            app, tokens, *_ = data
            async with signed_asgi_client(app, tokens["secretary"], workspace=True) as client:
                response = await client.get(MISSION_PATH, params={
                    k: result_owner["selection"][k] for k in ("work_ref", "root_job_id")})
                assert changed == [fault]
                assert response.status_code == 403, response.text
                assert response.json()["error"]["code"] == "access_denied"
                assert "mission_workspace" not in response.text
    asyncio.run(run())


@pytest.mark.parametrize("selection_change", [
    {"work_ref": "WS:FOREIGN"}, {"root_job_id": "JOB-ffffffffffff"},
    {"actor": "gb1"}, {"principal": "secretary"}, {"target_digest": "0" * 64},
])
def test_workspace_selection_cannot_choose_authority(
    result_owner, identities, tmp_path, short_socket_root, selection_change,
):
    async def run():
        async with workspace_surface(result_owner, identities, tmp_path, short_socket_root) as data:
            app, tokens, _, _, _, _ = data
            async with signed_asgi_client(app, tokens["secretary"], workspace=True) as client:
                selected = {k: result_owner["selection"][k] for k in ("work_ref", "root_job_id")}
                selected.update(selection_change)
                response = await client.get(MISSION_PATH, params=selected)
                assert response.status_code in (400, 404), response.text
                assert "mission_workspace" not in response.text
                posted = await client.post(MISSION_PATH, json={})
                assert posted.status_code in (400, 404, 405)
    asyncio.run(run())


@pytest.mark.parametrize("claims", [
    {"iss": "https://foreign.example.test"}, {"aud": COO_RESOURCE},
    {"aud": "https://mcp.mastermind-x.com/mcp"},
    {"scope": ""}, {"scope": "mastermind.executive.read"}, {"sub": "foreign-subject"},
    {"client_id": "foreign-client"}, {"exp": FIXTURE_NOW - 1},
])
def test_coo_authentication_failure_precedes_owner_read(identities, tmp_path, claims):
    async def run():
        async with coo_surface(tmp_path, identities) as (core, settings, _, state, _):
            # A read of this value would produce an error instead of a clean auth refusal.
            state["mission"] = None
            token = identities[0].token(settings.policy, **claims)
            response = await coo_call(core, token, "executive_mandate", {"work_ref": "WS:ONE"})
            assert response.status_code in (401, 403), response.text
    asyncio.run(run())


def test_coo_v1_isolation_and_canonical_v2_binding_compatibility(identities, tmp_path):
    async def run():
        async with coo_surface(tmp_path, identities, member=0) as a, coo_surface(
            tmp_path, identities, member=1
        ) as b:
            for own, other in ((a, b), (b, a)):
                core, settings, token, state, _ = own
                assert (await coo_call(core, token, "executive_mandate",
                                      {"work_ref": "WS:ONE"})).status_code == 200
                assert (await coo_call(core, other[2], "executive_mandate",
                                      {"work_ref": "WS:ONE"})).status_code == 403
            a[3]["binding"]["enabled"] = False
            assert (await coo_call(a[0], a[2], "executive_mandate", {"work_ref": "WS:ONE"})).status_code == 403
            assert (await coo_call(b[0], b[2], "executive_mandate", {"work_ref": "WS:ONE"})).status_code == 200
            records = sorted(
                [a[3]["binding"]["binding"], b[3]["binding"]["binding"]], key=_digest,
            )
            document = {"schema": COO_BINDING_SCHEMA_V2, "enabled": True,
                        "bindings": records}
            assert validate_coo_binding(document, a[1].policy) == document
            # Reject the deliberately wrong order, not the supported v2 schema.
            with pytest.raises(ValueError, match="access_denied"):
                validate_coo_binding({**document, "bindings": list(reversed(records))},
                                     a[1].policy)
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["permission", "subject", "disable"])
def test_coo_mandate_rechecks_same_subject_and_permission(identities, tmp_path, fault):
    reads = []

    def change(state):
        reads.append(fault)
        if fault == "permission":
            state["binding"]["binding"]["permission_digest"] = permission_receipt("rotated")
        elif fault == "subject":
            state["binding"]["binding"]["subject_digest"] = "e" * 64
        else:
            state["binding"]["enabled"] = False

    async def run():
        async with coo_surface(tmp_path, identities, after_read=change) as (core, _, token, _, _):
            response = await coo_call(core, token, "executive_mandate", {"work_ref": "WS:ONE"})
            assert reads == [fault]
            assert response.status_code == 403, response.text
            assert "mastermind.coo_principal_mandate" not in response.text
    asyncio.run(run())


@pytest.mark.parametrize("extra", [
    {"principal": "gb1"}, {"actor": "coo"}, {"target_digest": "0" * 64},
    {"approval": {"id": "unknown", "state": "approved"}},
    {"approval": {"id": "old", "expires_at": FIXTURE_NOW - 1}},
    {"authority_generation_digest": "0" * 64}, {"root_job_id": "JOB-001"},
])
def test_unknown_approval_and_model_selected_target_are_not_public_authority(
    identities, tmp_path, extra,
):
    async def run():
        async with coo_surface(tmp_path, identities) as (core, _, token, _, _):
            calls = []

            async def never_send(path, frame):
                calls.append(frame)
                raise AssertionError("invalid public fields reached the Unix client")

            core._client.send_frame = never_send
            response = await coo_call(core, token, "submit_principal_intent", {
                **request_body(), **extra})
            assert response.status_code == 400, response.text
            assert response.json()["error"]["code"] == "invalid_input"
            assert calls == []
    asyncio.run(run())


@pytest.mark.parametrize("surface", ["coo_http", "coo_mcp", "ruling"])
@pytest.mark.parametrize("second_member", [0, 1], ids=["same-token", "different-principal"])
def test_ambiguous_authorization_never_selects_a_principal(identities, tmp_path, surface, second_member):
    async def request(app, token, path, body):
        other = identities[second_member].token(fixture_policy(identities, facet="coo_legacy"))
        headers = [("authorization", "Bearer " + token), ("authorization", "Bearer " + other),
                   *rpc_headers().items()]
        async with signed_asgi_client(app, token) as client:
            response = await client.post(path, json=body, headers=headers)
            assert response.status_code == 401, response.text

    async def run():
        if surface == "ruling":
            async with ruling_surface(tmp_path, identities) as (app, token, recorder, _):
                await request(app, token, "/mcp/principal-ruling",
                    rpc("tools/call", name="ruling", arguments=dict(ruling_fixture.RULING)))
                assert recorder.frames == []
        else:
            async with coo_surface(tmp_path, identities) as (core, settings, token, state, _):
                state["mission"] = None  # auth refusal must precede owner data
                if surface == "coo_http":
                    await request(core, token, "/v1/tools/executive_mandate",
                                  {"arguments": {"work_ref": "WS:ONE"}})
                else:
                    app = build_coo_mcp_app(settings, audit_sink=FixtureAudit())
                    async with _mounted_lifespan(app):
                        await request(app, token, "/mcp/coo", rpc())
    asyncio.run(run())


@pytest.mark.parametrize("raw,expected", [
    (b"{", 400),
    (b'{"arguments":{"work_ref":"WS:ONE"},"arguments":{"work_ref":"WS:ONE"}}', 400),
    (b'{"arguments":{"work_ref":"WS:ONE","work_ref":"WS:ONE"}}', 400),
    (b'{"arguments":{"work_ref":NaN}}', 400),
    (b" " * 65537, 413),
    (b'{"arguments":{"work_ref":"WS:ONE","wo\\u0072k_ref":"WS:ONE"}}', 400),
    (b'{"arguments":{"work_ref":Infinity}}', 400),
    (b'{"arguments":{"work_ref":-Infinity}}', 400),
    (b'{"arguments":{"work_ref":1e999}}', 400),
    (b'{"arguments":{"work_ref":"\xff"}}', 400),
    (b'{"arguments":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}", 400),
], ids=["truncated", "duplicate-root", "duplicate-nested", "nonfinite", "oversized",
        "escaped-duplicate", "infinity", "negative-infinity", "exponent-overflow",
        "invalid-utf8", "excessive-nesting"])
def test_malformed_duplicate_nonfinite_and_oversized_json_refuse(identities, tmp_path, raw, expected):
    async def run():
        async with coo_surface(tmp_path, identities) as (core, _, token, _, _):
            calls = []

            async def never_send(path, frame):
                calls.append(frame)
                raise AssertionError("bad JSON reached a changing owner")

            core._client.send_frame = never_send
            async with signed_asgi_client(core, token) as client:
                response = await client.post("/v1/tools/executive_mandate",
                                             content=raw, headers={"content-type": "application/json"})
            assert response.status_code == expected, response.text
            assert calls == []
    asyncio.run(run())


def test_actual_mcp_catalog_scope_separation_and_shared_resource_gap(identities, tmp_path):
    async def run():
        async with coo_surface(tmp_path, identities) as (_, settings, token, _, _):
            app = build_web_ceo_v2_with_coo_mcp_app(
                settings.executive, coo_settings=settings, audit_sink=FixtureAudit())
            ceo = identities[0].token(settings.executive.policies.read)
            async with _mounted_lifespan(app):
                async with signed_asgi_client(app, token) as client:
                    listed = await client.post("/mcp/coo", json=rpc(), headers=rpc_headers())
                    assert listed.status_code == 200, listed.text
                    tools = listed.json()["result"]["tools"]
                    assert {t["name"] for t in tools} == {s.name for s in COO_TOOL_SPECS}
                    by_name = {s.name: s for s in COO_TOOL_SPECS}
                    for tool in tools:
                        assert tool["inputSchema"] == by_name[tool["name"]].input_schema
                        assert tool["securitySchemes"][0]["scopes"] == list(COO_SCOPES)
                    wrong_coo = await client.post("/mcp/coo", json=rpc(),
                        headers={**rpc_headers(), "authorization": "Bearer " + ceo})
                    wrong_ceo = await client.post("/mcp", json=rpc(), headers=rpc_headers())
                    assert wrong_coo.status_code == 401
                    assert wrong_ceo.status_code == 401  # exact scope policies still isolate legacy roles
                    good_ceo = await client.post("/mcp", json=rpc(),
                        headers={**rpc_headers(), "authorization": "Bearer " + ceo})
                    assert good_ceo.status_code == 200
                    malformed = await client.post("/mcp/coo", json=rpc("tools/call",
                        name="submit_principal_intent",
                        arguments={**request_body(), "target_digest": "bogus"}), headers=rpc_headers())
                    assert tool_payload(malformed)["error"]["code"] == "invalid_input"
    asyncio.run(run())


@pytest.mark.parametrize("raw,expected", [
    (b"{", 400),
    (b'{"jsonrpc":"2.0","id":1,"id":1,"method":"tools/list"}', 400),
    (b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"executive_mandate","arguments":{"work_ref":"WS:ONE","work_ref":"WS:ONE"}}}', 400),
    (b'{"jsonrpc":"2.0","id":NaN,"method":"tools/list"}', 400),
    (b" " * 65537, 413),
    (b'{"jsonrpc":"2.0","id":1,"\\u0069d":1,"method":"tools/list"}', 400),
    (b'{"jsonrpc":"2.0","id":Infinity,"method":"tools/list"}', 400),
    (b'{"jsonrpc":"2.0","id":-Infinity,"method":"tools/list"}', 400),
    (b'{"jsonrpc":"2.0","id":1e999,"method":"tools/list"}', 400),
    (b'{"jsonrpc":"2.0","id":"\xff","method":"tools/list"}', 400),
    (b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":' +
     b"[" * 2000 + b"0" + b"]" * 2000 + b"}", 400),
], ids=["truncated", "duplicate-root", "duplicate-nested", "nonfinite", "oversized",
        "escaped-duplicate", "infinity", "negative-infinity", "exponent-overflow",
        "invalid-utf8", "excessive-nesting"])
def test_coo_mcp_strict_json_requirement(identities, tmp_path, raw, expected):
    async def run():
        async with coo_surface(tmp_path, identities) as (_, settings, token, _, _):
            app = build_coo_mcp_app(settings, audit_sink=FixtureAudit())
            async with _mounted_lifespan(app):
                async with signed_asgi_client(app, token) as client:
                    response = await client.post("/mcp/coo", content=raw,
                        headers={**rpc_headers(), "content-type": "application/json"})
                    assert response.status_code == expected, response.text
                    # Deep, syntactically valid JSON may be refused by the SDK
                    # schema; the rejection contract is HTTP 400 in either layer.
    asyncio.run(run())


@pytest.mark.parametrize("path", ["/mcp/coo/", "/mcp/coo?x=1", "/mcp%2Fcoo", "/mcp/coo/other"])
def test_coo_route_is_literal(identities, tmp_path, path):
    async def run():
        async with coo_surface(tmp_path, identities) as (_, settings, token, _, _):
            app = build_coo_mcp_app(settings, audit_sink=FixtureAudit())
            async with _mounted_lifespan(app):
                async with signed_asgi_client(app, token) as client:
                    response = await client.post(path, json=rpc(), headers=rpc_headers())
                    assert response.status_code == 404
    asyncio.run(run())


def test_lost_original_submit_reconciles_after_fresh_admission_closes_without_resend(
    identities, tmp_path, short_socket_root,
):
    async def run():
        guard_calls = []
        host = ingress_fixture.service(tmp_path, short_socket_root, guard=lambda e: guard_calls.append(e))
        await host.start()
        try:
            async with coo_surface(tmp_path, identities, socket_path=host.ceo_ingress_socket_path) as data:
                core, settings, token, state, _ = data
                wire_frames = []
                original_send = core._client.send_frame

                async def observed_send(path, frame):
                    wire_frames.append(copy.deepcopy(frame))
                    return await original_send(path, frame)

                core._client.send_frame = observed_send
                transport = ObservedAsgiTransport(core,
                    lose_response_for="/v1/tools/submit_principal_intent")
                async with signed_asgi_client(core, token, transport=transport) as client:
                    access = SecretaryAccessClient(work_ref="WS:ONE", root_job_id="JOB-001",
                                                   workspace=client, coo=client, clock=lambda: FIXTURE_NOW)
                    expected = original_ref()
                    first = await access.submit_intent(request_body())
                    assert first["state"] == "EFFECT_UNKNOWN"
                    assert first["request_ref"] == expected
                    assert first["replay_authorized"] is False
                    jobs = host.runtime.jobs.list_jobs()
                    assert len(jobs) == 1
                    guards_before_status = copy.deepcopy(guard_calls)
                    assert guards_before_status
                    host._ceo_ingress_app_binding = dataclasses.replace(
                        host._ceo_ingress_app_binding, principal_admission_armed=False)
                    state["mission"] = None  # original status must not read a fresh mandate
                    status = await access.reconcile_intent(expected)
                    assert status["state"] == "ADMISSION_ACCEPTED", status
                    assert status["request_ref"] == expected
                    assert status["job_id"] == jobs[0].job_id
                    assert status["dispatched"] is False
                    assert status["replay_authorized"] is False
                    paths = [r.path for r in transport.requests]
                    assert paths == ["/v1/tools/submit_principal_intent",
                                     "/v1/tools/principal_intent_status"]
                    sent_status = json.loads(transport.requests[-1].body)["arguments"]
                    assert sent_status == {"work_ref": "WS:ONE", "request_ref": expected}
                    submits = [f for f in wire_frames if f["schema"] == ingress.PRINCIPAL_SUBMIT_SCHEMA]
                    statuses = [f for f in wire_frames if f["schema"] == ingress.PRINCIPAL_STATUS_SCHEMA]
                    assert len(submits) == len(statuses) == 1
                    assert submits[0]["request_ref"] == statuses[0]["request_ref"] == expected
                    assert submits[0]["principal_context"] == statuses[0]["principal_context"]
                    assert submits[0]["request"] == normalize_principal_request(
                        request_body(), expected_work_ref="WS:ONE")
                    assert guard_calls == guards_before_status  # status does not re-admit
                    for envelope in guard_calls:
                        assert envelope["principal_binding_digest"] == _digest(state["binding"]["binding"])
                        assert envelope["authority_generation_digest"] == state["authority"].authority_generation_digest
                        assert envelope["workstream"] == "WS:ONE"
                    assert len(host.runtime.jobs.list_jobs()) == 1
                    # Authentication is still mandatory for the original status read.
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=core),
                                                 base_url="http://127.0.0.1", trust_env=False) as unauth:
                        denied = await unauth.post("/v1/tools/principal_intent_status",
                            json={"arguments": sent_status})
                        assert denied.status_code == 401
                    other = identities[1].token(settings.policy)
                    denied = await coo_call(core, other, "principal_intent_status", sent_status)
                    assert denied.status_code == 403
                    state["binding"]["enabled"] = False
                    denied = await coo_call(core, token, "principal_intent_status", sent_status)
                    assert denied.status_code == 403
                    assert len(host.runtime.jobs.list_jobs()) == 1
        finally:
            await host.close()
    asyncio.run(run())


@pytest.mark.parametrize("shared_operation", [True, False], ids=["same-operation", "distinct-operations"])
def test_two_bound_principals_cannot_borrow_original_effects(
    identities, tmp_path, short_socket_root, shared_operation,
):
    async def run():
        host = ingress_fixture.service(tmp_path, short_socket_root)
        await host.start()
        try:
            async with coo_surface(tmp_path, identities, member=0,
                    socket_path=host.ceo_ingress_socket_path) as a, coo_surface(
                    tmp_path, identities, member=1,
                    socket_path=host.ceo_ingress_socket_path) as b:
                surfaces = [a, b]
                wire_frames = []

                def observed_send(label, actual_send):
                    async def send(path, frame):
                        wire_frames.append((label, copy.deepcopy(frame)))
                        return await actual_send(path, frame)
                    return send

                for label, (core, _, _, _, _) in enumerate(surfaces):
                    core._client.send_frame = observed_send(label, core._client.send_frame)
                async with signed_asgi_client(a[0], a[2]) as ca, signed_asgi_client(b[0], b[2]) as cb:
                    access = [SecretaryAccessClient(work_ref="WS:ONE", root_job_id="JOB-001",
                              workspace=client, coo=client, clock=lambda: FIXTURE_NOW)
                              for client in (ca, cb)]
                    requests = [request_body(), request_body(
                        operation_key="h24-original-operation" if shared_operation else "h24-secretary-operation")]
                    expected = [original_ref(body) for body in requests]
                    outcomes = await asyncio.gather(
                        *(client.submit_intent(body) for client, body in zip(access, requests)))
                    assert [outcome["request_ref"] for outcome in outcomes] == expected
                    assert all(outcome["replay_authorized"] is False for outcome in outcomes)
                    accepted = [i for i, outcome in enumerate(outcomes)
                                if outcome["state"] == "ADMISSION_ACCEPTED"]
                    assert len(accepted) == (1 if shared_operation else 2), outcomes
                    if shared_operation:
                        assert expected[0] == expected[1]
                        loser = 1 - accepted[0]
                        assert outcomes[loser]["state"] == "REFUSED", outcomes
                        assert outcomes[loser]["reason_code"] == "operation_conflict"
                        assert outcomes[loser].get("job_id") is None
                    else:
                        assert expected[0] != expected[1]
                        assert outcomes[0]["job_id"] != outcomes[1]["job_id"]
                    assert len(host.runtime.jobs.list_jobs()) == len(accepted)
                    submits = [(label, frame) for label, frame in wire_frames
                               if frame["schema"] == ingress.PRINCIPAL_SUBMIT_SCHEMA]
                    assert [sum(label == i for label, _ in submits) for i in range(2)] == [1, 1]
                    assert len({frame["principal_context"]["principal_binding_digest"]
                                for _, frame in submits}) == 2
                    host._ceo_ingress_app_binding = dataclasses.replace(
                        host._ceo_ingress_app_binding, principal_admission_armed=False)
                    for winner in accepted:
                        own = await access[winner].reconcile_intent(expected[winner])
                        assert own["state"] == "ADMISSION_ACCEPTED", own
                        assert own["job_id"] == outcomes[winner]["job_id"]
                        assert own["dispatched"] is False
                        foreign = await access[1 - winner].reconcile_intent(expected[winner])
                        assert foreign["state"] == "REFUSED", foreign
                        assert foreign["reason_code"] == "operation_conflict"
                        assert foreign.get("job_id") is None
                    assert sum(frame["schema"] == ingress.PRINCIPAL_SUBMIT_SCHEMA
                               for _, frame in wire_frames) == 2
                    assert len(host.runtime.jobs.list_jobs()) == len(accepted)
        finally:
            await host.close()
    asyncio.run(run())


@pytest.mark.parametrize("boundary", ["after_grounding", "after_submit"])
@pytest.mark.parametrize("change", ["disabled", "rotated_receipt"])
def test_permission_change_at_send_boundary_preserves_original_effect(
    identities, tmp_path, short_socket_root, boundary, change,
):
    async def run():
        host = ingress_fixture.service(tmp_path, short_socket_root)
        await host.start()
        try:
            async with coo_surface(tmp_path, identities,
                    socket_path=host.ceo_ingress_socket_path) as (core, _, token, state, _):
                saved_binding = copy.deepcopy(state["binding"])
                original_send = core._client.send_frame
                frames, revocations = [], []

                async def send(path, frame):
                    frames.append(copy.deepcopy(frame))
                    response = await original_send(path, frame)
                    selected = (frame["schema"].endswith("grounding.v1")
                                if boundary == "after_grounding"
                                else frame["schema"] == ingress.PRINCIPAL_SUBMIT_SCHEMA)
                    if selected:
                        if change == "disabled":
                            state["binding"]["enabled"] = False
                        else:
                            state["binding"]["binding"]["permission_digest"] = permission_receipt("rotated")
                        revocations.append(frame["schema"])
                    return response

                core._client.send_frame = send
                transport = ObservedAsgiTransport(core)
                async with signed_asgi_client(core, token, transport=transport) as client:
                    access = SecretaryAccessClient(work_ref="WS:ONE", root_job_id="JOB-001",
                        workspace=client, coo=client, clock=lambda: FIXTURE_NOW)
                    outcome = await access.submit_intent(request_body())
                    expected = original_ref()
                    submitted = boundary == "after_submit"
                    assert len(revocations) == 1
                    assert outcome["state"] == ("EFFECT_UNKNOWN" if submitted else "REFUSED"), outcome
                    assert outcome["request_ref"] == expected
                    assert outcome["replay_authorized"] is False
                    assert outcome.get("job_id") is None
                    assert sum(frame["schema"] == ingress.PRINCIPAL_SUBMIT_SCHEMA for frame in frames) == int(submitted)
                    jobs = host.runtime.jobs.list_jobs()
                    assert len(jobs) == int(submitted)
                    if submitted:
                        refused = await access.reconcile_intent(expected)
                        assert refused["state"] == "REFUSED", refused
                        assert refused["reason_code"] == (
                            "authority_refused" if change == "disabled" else "operation_conflict")
                        assert refused.get("job_id") is None
                        # Fixture restoration uses the exact original receipt;
                        # a rotated receipt must never borrow the old context.
                        state["binding"] = saved_binding
                        host._ceo_ingress_app_binding = dataclasses.replace(
                            host._ceo_ingress_app_binding, principal_admission_armed=False)
                        recovered = await access.reconcile_intent(expected)
                        assert recovered["state"] == "ADMISSION_ACCEPTED", recovered
                        assert recovered["request_ref"] == expected
                        assert recovered["job_id"] == jobs[0].job_id
                        assert recovered["dispatched"] is False
                    assert sum(frame["schema"] == ingress.PRINCIPAL_SUBMIT_SCHEMA for frame in frames) == int(submitted)
                    assert sum(request.path == "/v1/tools/submit_principal_intent"
                               for request in transport.requests) == 1
                    assert len(host.runtime.jobs.list_jobs()) == int(submitted)
        finally:
            await host.close()
    asyncio.run(run())


def test_secretary_retains_uncertainty_for_an_opaque_server_refusal(identities, tmp_path):
    async def run():
        async with coo_surface(tmp_path, identities) as (core, _, token, _, _):
            frames = []

            async def send(path, frame):
                frames.append(copy.deepcopy(frame))
                if frame["schema"].endswith("grounding.v1"):
                    return CeoIngressResponse("sent_ok", ok=True, result=ingress_fixture.GROUNDING)
                return CeoIngressResponse("not_sent")

            core._client.send_frame = send
            async with signed_asgi_client(core, token) as client:
                access = SecretaryAccessClient(work_ref="WS:ONE", root_job_id="JOB-001",
                    workspace=client, coo=client, clock=lambda: FIXTURE_NOW)
                outcome = await access.submit_intent(request_body())
                # COO knows its transport did not send, but the consumer sees
                # HTTP 503 and conservatively retains the original uncertainty.
                assert outcome["state"] == "EFFECT_UNKNOWN"
                assert outcome["request_ref"] == original_ref()
                assert outcome["replay_authorized"] is False
                assert sum(frame["schema"] == ingress.PRINCIPAL_SUBMIT_SCHEMA for frame in frames) == 1
    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["not_sent", "lost", "raised", "bad_receipt"])
def test_pre_and_post_send_outcomes_retain_original_identity(identities, tmp_path, outcome):
    async def run():
        async with coo_surface(tmp_path, identities) as (core, _, token, _, _):
            frames = []

            async def send(path, frame):
                frames.append(copy.deepcopy(frame))
                if frame["schema"].endswith("grounding.v1"):
                    return CeoIngressResponse("sent_ok", ok=True, result=ingress_fixture.GROUNDING)
                if outcome == "raised":
                    raise OSError("PRIVATE_FIXTURE_FAILURE")
                if outcome == "bad_receipt":
                    return CeoIngressResponse("sent_ok", ok=True, result={"accepted": True})
                return CeoIngressResponse("not_sent" if outcome == "not_sent" else "sent_effect_unknown")

            core._client.send_frame = send
            response = await coo_call(core, token, "submit_principal_intent", request_body())
            assert response.status_code == (503 if outcome == "not_sent" else 202)
            assert response.json()["request_ref"] == original_ref()
            if outcome != "not_sent":
                assert response.json()["status"] == "effect_unknown"
            assert sum(f["schema"] == ingress.PRINCIPAL_SUBMIT_SCHEMA for f in frames) == 1
            assert "PRIVATE_FIXTURE" not in response.text
    asyncio.run(run())


def test_original_id_semantics_and_replay_status_policy_use_existing_ingress(tmp_path):
    original = ingress_fixture.frame(tmp_path)
    accepted = ingress_fixture.call(tmp_path, original)
    changed = copy.deepcopy(original)
    changed["request"]["objective"] = "A different semantic request."
    assert original_ref(changed["request"]) == original["request_ref"]
    with pytest.raises(ingress.CeoIngressError) as conflict:
        ingress_fixture.call(tmp_path, changed)
    assert conflict.value.code == "operation_conflict"
    # A closed fresh-effect guard is irrelevant to the existing effect's replay/status.
    def closed(_):
        raise AssertionError("fresh-effect guard must not run")
    replay = ingress_fixture.call(tmp_path, original, guard=closed)
    assert replay == dict(accepted, duplicate=True)
    status = {k: original[k] for k in ("request_ref", "principal_context")}
    status["schema"] = ingress.PRINCIPAL_STATUS_SCHEMA
    assert ingress_fixture.call(tmp_path, status, guard=closed) == accepted
    with pytest.raises(ingress.CeoIngressError):
        ingress_fixture.call(tmp_path, status, peer=False, guard=closed)


@pytest.mark.parametrize("fault", ["unknown_authority", "stale_generation", "permission", "disabled", "stale_mission"])
def test_bounded_authority_owner_refuses_unknown_or_stale_grants(tmp_path, monkeypatch, fault):
    host, config, _, _ = host_fixture.setup(tmp_path)
    mission = host_fixture.mandate.mission_doc()
    monkeypatch.setattr(host.workspace, "read_mission_for_work_ref", lambda work: mission)
    envelope = host_fixture.envelope_for(host, tmp_path)
    assert host.guard(envelope) is None
    if fault == "unknown_authority":
        envelope["mission_authority_ref"] = "authority:unknown"
    elif fault == "stale_generation":
        config["missions"][0]["proof_contract_ref"] = "proof:new-generation"
    elif fault == "permission":
        config["binding"]["binding"]["permission_digest"] = "b" * 64
    elif fault == "disabled":
        config["missions"][0]["enabled"] = False
    else:
        mission["read_state"]["state"] = "HISTORICAL"
    with pytest.raises(ValueError):
        host.guard(envelope)


@pytest.mark.parametrize("extra", [
    {"target_digest": "0" * 64}, {"obligation_id": "WAKE-" + "b" * 32},
    {"work_ref": "WS:OTHER"}, {"principal": "secretary"},
    {"approval": {"state": "approved", "expires_at": FIXTURE_NOW - 1}},
])
def test_ruling_remains_separate_and_host_targeted(identities, tmp_path, extra):
    async def run():
        async with ruling_surface(tmp_path, identities) as (app, token, recorder, _):
            async with signed_asgi_client(app, token) as client:
                response = await client.post("/mcp/principal-ruling",
                    json=rpc("tools/call", name="ruling",
                             arguments={**ruling_fixture.RULING, **extra}),
                    headers=rpc_headers())
                assert tool_payload(response)["error"]["code"] == "invalid_input"
                assert recorder.frames == []
    asyncio.run(run())


@pytest.mark.parametrize("member", [0, 1], ids=["gb1", "secretary"])
def test_signed_ruling_uses_only_the_host_bound_obligation(identities, tmp_path, member):
    async def run():
        accepted = ruling_fixture.sent_ok(ruling_fixture.ruling_envelope())
        async with ruling_surface(tmp_path, identities, member=member, response=accepted) as data:
            app, token, recorder, state = data
            async with signed_asgi_client(app, token) as client:
                response = await client.post("/mcp/principal-ruling",
                    json=rpc("tools/call", name="ruling", arguments=dict(ruling_fixture.RULING)),
                    headers=rpc_headers())
                result = tool_payload(response)
                assert result["ok"] is True, result
                assert result["obligation_id"] == ruling_fixture.obligation_id()
                assert len(recorder.frames) == 1
                frame = recorder.frames[0]
                assert frame["tool"] == "ruling"
                assert frame["obligation_id"] == ruling_fixture.obligation_id()
                assert frame["arguments"] == ruling_fixture.RULING
                caller = frame["caller"]
                assert caller["root_job_id"] == "JOB-001"
                assert caller["admission_context"]["work_ref"] == "WS:ONE"
                assert caller["admission_context"]["principal_binding_digest"] == _digest(state["binding"]["binding"])
                assert caller["admission_context"]["authority_generation_digest"] == state["authority"].authority_generation_digest
    asyncio.run(run())


@pytest.mark.parametrize("raw,expected", [
    (b"{", 400),
    (b'{"jsonrpc":"2.0","id":1,"id":1,"method":"tools/list"}', 400),
    (b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ruling","arguments":{"decision":"a","decision":"b"}}}', 400),
    (b'{"jsonrpc":"2.0","id":NaN,"method":"tools/list"}', 400),
    (b" " * 65537, 413),
], ids=["truncated", "duplicate-root", "duplicate-nested", "nonfinite", "oversized"])
def test_ruling_strict_json_boundary_refuses_before_forwarding(identities, tmp_path, raw, expected):
    async def run():
        async with ruling_surface(tmp_path, identities) as (app, token, recorder, _):
            async with signed_asgi_client(app, token) as client:
                response = await client.post("/mcp/principal-ruling", content=raw,
                    headers={**rpc_headers(), "content-type": "application/json"})
                assert response.status_code == expected, response.text
                assert recorder.frames == []
    asyncio.run(run())


@pytest.mark.parametrize("change", ["none", "mutated", "answered", "authority_revoked", "binding_drift",
                                  "invalid_option", "policy_denied", "policy_revoked_at_commit"])
def test_existing_ruling_source_fence_rechecks_current_unanswered_decision(
    short_socket_root, monkeypatch, change,
):
    # Invoke the existing end-to-end fixture owner unchanged: disposable Runtime,
    # real Unix Relay protocol, in-memory Slack only, and no worker dispatch.
    decision_fence_fixture.test_fresh_source_fence_through_actual_host_runtime_and_relay(
        short_socket_root, monkeypatch, change)


@pytest.mark.parametrize("field,value", [
    ("attempt_id", "ATT-" + "3" * 32), ("worker_id", "foreign-worker"),
    ("root_job_id", "JOB-999"),
], ids=["attempt", "worker", "root"])
def test_current_ruling_target_tuple_cannot_drift(short_socket_root, monkeypatch, field, value):
    facts = current_source_fixture.prepared(monkeypatch)

    def changed(observed):
        return dataclasses.replace(observed, current_worker=dataclasses.replace(
            observed.current_worker, **{field: value}))

    result, calls = current_source_fixture.run(short_socket_root, facts, observer_change=changed)
    assert isinstance(result, current_source_fixture.PrincipalCurrentSourceUnavailable)
    assert len(calls) == 1


def test_request_schema_and_route_matrix_do_not_create_new_authority():
    for field in ("workstream", "operation_key"):
        malformed = request_body()
        del malformed[field]
        with pytest.raises(ValueError):
            normalize_principal_request(malformed, expected_work_ref="WS:ONE")
    for attempt_limit in (0, 3, True):
        with pytest.raises(GatewayError):
            validate_coo_tool_arguments("submit_principal_intent", {
                **request_body(), "attempt_limit": attempt_limit})
    matrix = route_resource_matrix()
    assert len({row["route"] for row in matrix}) == len(matrix)
    coo = next(row for row in matrix if row["route"] == "/mcp/coo")
    assert coo["audience"] == CEO_RESOURCE
    assert coo["integration_gap"] == "C34_SHARED_RESOURCE"
    assert all(row["audience"] == CEO_RESOURCE for row in matrix
               if row["route"] != MISSION_PATH)
    assert COO_RESOURCE.endswith("/mcp/coo")


def test_distinct_resource_verifier_and_missing_c34_composition_are_explicit(identities, tmp_path):
    async def run():
        keys = FixturePublicKeys(identities)
        policy = fixture_policy(identities, facet="coo")
        auth = authenticator(policy, keys)
        assert (await auth.verify_token(identities[0].token(policy), now=FIXTURE_NOW)).resource == COO_RESOURCE
        for resource in (CEO_RESOURCE, "https://mcp.mastermind-x.com/mcp"):
            with pytest.raises(AuthError):
                await auth.verify_token(identities[0].token(policy, aud=resource), now=FIXTURE_NOW)
        async with coo_surface(tmp_path, identities) as (_, settings, _, _, _):
            with pytest.raises(ValueError, match="share the Executive resource"):
                dataclasses.replace(settings, policy=policy)
    asyncio.run(run())


def test_stdlib_discovery_explicitly_separates_the_pytest_profile():
    result = subprocess.run([sys.executable, "-S", "-m", "unittest", "discover", "-v",
        "-s", str(Path(__file__).parent), "-p", Path(__file__).name],
        capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ran 1 test" in result.stderr
    assert "OK (skipped=1)" in result.stderr
    assert "pytest-only integration suite" in result.stderr


@pytest.mark.parametrize("surface", ["coo_http", "coo_mcp"])
@pytest.mark.parametrize("fault", ["duplicate", "escaped_duplicate", "overflow"])
def test_strict_json_blocks_modifying_requests_before_authority_or_send(
    identities, tmp_path, short_socket_root, monkeypatch, surface, fault,
):
    async def run():
        host = ingress_fixture.service(tmp_path, short_socket_root)
        await host.start()
        frames, authority_calls = [], []
        original_send = CeoIngressClient.send_frame

        async def observed_send(client, path, frame):
            frames.append(copy.deepcopy(frame))
            return await original_send(client, path, frame)

        monkeypatch.setattr(CeoIngressClient, "send_frame", observed_send)
        try:
            async with coo_surface(tmp_path, identities,
                    socket_path=host.ceo_ingress_socket_path) as (_, settings, token, state, _):
                def authority(principal, work):
                    authority_calls.append(("authority", work))
                    return state["authority"]

                def mission(principal, work):
                    authority_calls.append(("mission", work))
                    return copy.deepcopy(state["mission"])

                settings = dataclasses.replace(settings, authority_provider=authority,
                                                mission_provider=mission)
                arguments = json.dumps(request_body(), separators=(",", ":"))
                if fault == "overflow":
                    arguments = arguments.replace('"priority":1', '"priority":1e999')
                else:
                    key = "operation_key" if fault == "duplicate" else "oper\\u0061tion_key"
                    arguments = arguments[:-1] + ',"' + key + '":"h24-original-operation"}'
                if surface == "coo_http":
                    raw = ('{"arguments":' + arguments + "}").encode("utf-8")
                    path = "/v1/tools/submit_principal_intent"
                else:
                    raw = ('{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
                           '{"name":"submit_principal_intent","arguments":' +
                           arguments + "}}").encode("utf-8")
                    path = "/mcp/coo"

                async def invoke(app):
                    async with signed_asgi_client(app, token) as client:
                        response = await client.post(path, content=raw,
                            headers={**rpc_headers(), "content-type": "application/json"})
                    assert response.status_code == 400, response.text
                    assert response.json()["error"]["code"] == "invalid_input"

                if surface == "coo_http":
                    app = create_coo_app(settings, audit_sink=FixtureAudit())
                    try:
                        await invoke(app)
                    finally:
                        await app.aclose()
                else:
                    app = build_coo_mcp_app(settings, audit_sink=FixtureAudit())
                    async with _mounted_lifespan(app):
                        await invoke(app)
                assert authority_calls == []
                assert frames == []
                assert host.runtime.jobs.list_jobs() == []
        finally:
            await host.close()
    asyncio.run(run())


@pytest.mark.parametrize("framing", [
    "exact", "overflow", "empty", "disconnect", "deadline", "unexpected_event",
])
def test_coo_raw_body_guard_bounds_received_bytes_before_sdk(
    identities, tmp_path, monkeypatch, framing,
):
    manager_calls, sdk_requests = [], []
    actual_manager = mcp_server.StreamableHTTPSessionManager

    class ObservedManager(actual_manager):
        async def handle_request(self, scope, receive, send):
            manager_calls.append(scope["path"])

            async def observed_receive():
                event = await receive()
                if event.get("type") == "http.request":
                    sdk_requests.append(bytes(event.get("body", b"")))
                return event

            await super().handle_request(scope, observed_receive, send)

    monkeypatch.setattr(mcp_server, "StreamableHTTPSessionManager", ObservedManager)
    monkeypatch.setattr(http_boundary, "PREAUTH_RECEIVE_DEADLINE_SECONDS", 0.02)

    async def run():
        async with coo_surface(tmp_path, identities) as (_, settings, token, _, _):
            app = build_coo_mcp_app(settings, audit_sink=FixtureAudit())
            raw = json.dumps(rpc(), indent=2).encode("utf-8")
            exact = raw + b" " * (http_boundary.MAX_REQUEST_BYTES - len(raw))
            if framing in ("exact", "overflow"):
                body = exact if framing == "exact" else exact + b" "
                events = [
                    {"type": "http.request", "body": body[:17000], "more_body": True},
                    {"type": "http.request", "body": body[17000:], "more_body": False},
                ]
            elif framing == "empty":
                events = [{"type": "http.request", "body": b"", "more_body": False}]
            elif framing == "unexpected_event":
                events = [{"type": "http.response.start", "status": 200}]
            else:
                events = []
            sent = []

            async def receive():
                if events:
                    return events.pop(0)
                if framing == "deadline":
                    await asyncio.Event().wait()
                return {"type": "http.disconnect"}

            async def send(event):
                sent.append(dict(event))

            scope = {
                "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1", "scheme": "http", "method": "POST",
                "path": "/mcp/coo", "raw_path": b"/mcp/coo", "query_string": b"",
                "headers": [(b"host", b"127.0.0.1"),
                    (b"authorization", ("Bearer " + token).encode("ascii")),
                    (b"content-type", b"application/json"), (b"content-length", b"1"),
                    *[(key.encode("ascii"), value.encode("ascii"))
                      for key, value in rpc_headers().items()]],
                "client": ("127.0.0.1", 9000), "server": ("127.0.0.1", 9001),
            }
            async with _mounted_lifespan(app):
                await asyncio.wait_for(app(scope, receive, send), timeout=1.0)
            expected = 200 if framing == "exact" else 413 if framing == "overflow" else 400
            assert sent[0]["status"] == expected, sent
            if framing == "exact":
                assert manager_calls == ["/mcp/coo"]
                assert sdk_requests == [exact]  # unchanged bytes replayed once
            else:
                assert manager_calls == []
                assert sdk_requests == []
                body = b"".join(event.get("body", b"") for event in sent[1:])
                assert json.loads(body)["error"]["code"] == "invalid_input"
    asyncio.run(run())
