"""Real signed Workspace principal/READ owner; no account or Runtime effect."""
import asyncio
import json
from types import SimpleNamespace
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.native_draft_identity import ROUTE, SCHEMA, native_draft_identity_current
from integrations.mastermind_workspace_app.owner_context import workspace_principal_scope
from tests.test_workspace_read_app import _authenticator, _workspace_policy, _workspace_token, _FakeWorkspaceClient, rsa_key, NOW, ISSUER
from integrations.business_mcp_auth.contracts import subject_digest
from tests.test_executive_workspace_mount import settings


def owner(rsa_key, subject=None):
    policy = _workspace_policy(allowed_subject_digests=[subject_digest(issuer=ISSUER, subject=subject)]) if subject else None
    auth = _authenticator(rsa_key, policy=policy); token = _workspace_token(rsa_key, **({"sub": subject} if subject else {}))
    principal = asyncio.run(auth.verify_authorization_header("Bearer " + token, now=NOW))
    slots = {"schema": BINDINGS_SCHEMA, "profiles": {
        "web": {"enabled": True, "binding": {**principal_frame(principal), "permission_digest": "a" * 64}},
        "mac": {"enabled": False, "binding": None}}}
    authorize, _ = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
    clock = [NOW]; source = _FakeWorkspaceClient()
    config = WorkspaceAppConfig(authenticator=auth, authorize_principal=authorize, now=lambda: clock[0], client=source)
    async def endpoint(request): return await native_draft_identity_current(request, config=config)
    app = Starlette(routes=[Route(ROUTE, endpoint, methods=["GET"])])
    return SimpleNamespace(http=TestClient(app), token=token, principal=principal, slots=slots, clock=clock, source=source, config=config)


def test_actual_signed_current_read_returns_only_six_field_principal_hash_and_expiry(rsa_key):
    s = owner(rsa_key)
    response = s.http.get(ROUTE, headers={"Authorization": "Bearer " + s.token})
    assert response.status_code == 200, response.text
    assert response.json() == {"schema": SCHEMA, "principal_scope": workspace_principal_scope(s.principal),
                               "expires_at_ms": s.principal.expires_at * 1000}
    assert response.headers["cache-control"] == "no-store"
    assert "token" not in response.text and "permission_digest" not in response.text
    assert s.source.calls == []


def test_two_actual_allowed_principals_never_share_draft_scope(rsa_key):
    first, other = owner(rsa_key), owner(rsa_key, "different-allowed-synthetic-native-user")
    a = first.http.get(ROUTE, headers={"Authorization": "Bearer " + first.token}).json()
    b = other.http.get(ROUTE, headers={"Authorization": "Bearer " + other.token}).json()
    assert a["schema"] == b["schema"] == SCHEMA
    assert a["principal_scope"] != b["principal_scope"]


@pytest.mark.parametrize("case", ["unsigned", "foreign", "revoked", "expired", "body", "query", "path", "method"])
def test_unqualified_identity_has_no_continuity_observation(rsa_key, case):
    s = owner(rsa_key); headers = {"Authorization": "Bearer " + s.token}; path = ROUTE
    if case == "unsigned": headers = {}
    elif case == "foreign": headers = {"Authorization": "Bearer " + _workspace_token(rsa_key, sub="foreign")}
    elif case == "revoked": s.slots["profiles"]["web"]["enabled"] = False
    elif case == "expired": s.clock[0] = s.principal.expires_at
    elif case == "query": path += "?principal_scope=foreign"
    elif case == "path": path = path.replace("native-draft", "%6eative-draft")
    response = s.http.request("HEAD" if case == "method" else "GET", path,
        headers=headers, content=b'{}' if case == "body" else None)
    assert response.status_code != 200
    assert "principal_scope" not in response.text and s.source.calls == []


@pytest.mark.parametrize("case", ["revoke", "stamp", "expiry", "owner"])
def test_identity_permission_and_actual_owner_rechecked_after_receive(rsa_key, monkeypatch, case):
    s = owner(rsa_key)
    from integrations.mastermind_workspace_app import native_draft_identity as module
    original = module._reject_any_body
    async def changed(request):
        result = await original(request)
        if case == "revoke": s.slots["profiles"]["web"]["enabled"] = False
        elif case == "stamp": s.slots["profiles"]["web"]["binding"]["permission_digest"] = "b" * 64
        elif case == "expiry": s.clock[0] = s.principal.expires_at
        else: object.__setattr__(s.config, "authorize_principal", lambda _: True)
        return result
    monkeypatch.setattr(module, "_reject_any_body", changed)
    response = s.http.get(ROUTE, headers={"Authorization": "Bearer " + s.token})
    assert response.status_code == 403 and "principal_scope" not in response.text
    assert s.source.calls == []


def test_real_registered_outer_to_signed_owner_is_zero_selector_and_non_effectful(rsa_key, settings):
    from integrations.executive_mcp import server
    from integrations.mastermind_workspace_app.app import create_workspace_app
    from tests.test_executive_workspace_mount import existing
    s = owner(rsa_key)
    inner = create_workspace_app(s.config)
    outer = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(), workspace_app=inner)
    with TestClient(outer, base_url="https://mcp.mastermind-x.com") as client:
        headers={"Authorization": "Bearer " + s.token}
        response = client.get(ROUTE, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["principal_scope"] == workspace_principal_scope(s.principal)
        for path, method, h in [(ROUTE+"?principal_scope=forged", "GET", headers),
                                (ROUTE,"HEAD",headers), (ROUTE,"POST",headers),
                                (ROUTE+"/","GET",headers),
                                (ROUTE.replace("native-draft","%6eative-draft"),"GET",headers),
                                (ROUTE,"GET",{}),
                                (ROUTE,"GET",{**headers,"Origin":"https://unrelated.example"})]:
            refused=client.request(method,path,headers=h)
            assert refused.status_code in (400,401,403,404,405)
            assert "principal_scope" not in refused.text
        assert s.source.calls == []
        s.slots["profiles"]["web"]["enabled"]=False
        assert client.get(ROUTE,headers=headers).status_code == 403
    from ops.executive_os.os_public_edge import (
        GET_ROUTES, POST_ROUTES, TRANSITION_ROUTE_PROFILES,
        PRE_NATIVE_DRAFT_GET_ROUTES, PRE_NATIVE_DRAFT_POST_ROUTES,
        PRE_NATIVE_SESSION_SEND_GET_ROUTES, PRE_NATIVE_SESSION_SEND_POST_ROUTES,
        PRE_BYOK_ROLES_GET_ROUTES, PRE_BYOK_ROLES_POST_ROUTES,
        PRE_PROJECT_EXECUTION_POST_ROUTES, PROJECT_EXECUTION_POST_ROUTES,
        PRE_DIRECT_NATIVE_GET_ROUTES, PRE_DIRECT_NATIVE_POST_ROUTES,
        PRE_COMPANY_PRIORITIES_POST_ROUTES, PRE_MODEL_CONFIGURATION_GET_ROUTES,
    )
    # This native identity addition was GET-only. Later SEND, BYOK, project
    # and direct-native routes preserve the exact before/after profile of that cut.
    assert PRE_NATIVE_SESSION_SEND_GET_ROUTES == PRE_NATIVE_DRAFT_GET_ROUTES + (ROUTE,)
    assert PRE_NATIVE_SESSION_SEND_POST_ROUTES == PRE_NATIVE_DRAFT_POST_ROUTES
    assert PRE_BYOK_ROLES_GET_ROUTES == PRE_NATIVE_SESSION_SEND_GET_ROUTES
    assert PRE_BYOK_ROLES_POST_ROUTES == PRE_NATIVE_SESSION_SEND_POST_ROUTES + ('/os/executive/session/send',)
    assert PRE_MODEL_CONFIGURATION_GET_ROUTES == PRE_BYOK_ROLES_GET_ROUTES + ("/workspace/byok/roles/current",)
    assert GET_ROUTES == PRE_MODEL_CONFIGURATION_GET_ROUTES + ("/workspace/resources/models/current",)
    assert PRE_PROJECT_EXECUTION_POST_ROUTES == PRE_BYOK_ROLES_POST_ROUTES
    assert PRE_DIRECT_NATIVE_POST_ROUTES == PRE_PROJECT_EXECUTION_POST_ROUTES + PROJECT_EXECUTION_POST_ROUTES
    assert PRE_COMPANY_PRIORITIES_POST_ROUTES == PRE_DIRECT_NATIVE_POST_ROUTES + (
        "/os/executive/direct-native/result", "/os/executive/direct-native/consume",
        "/os/executive/direct-native/correction",
    )
    assert POST_ROUTES == PRE_COMPANY_PRIORITIES_POST_ROUTES + ("/os/executive/company-priorities",)
    assert (PRE_MODEL_CONFIGURATION_GET_ROUTES, PRE_COMPANY_PRIORITIES_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert (PRE_DIRECT_NATIVE_GET_ROUTES, PRE_DIRECT_NATIVE_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert ROUTE in GET_ROUTES and ROUTE not in POST_ROUTES
    assert (PRE_NATIVE_DRAFT_GET_ROUTES, PRE_NATIVE_DRAFT_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert (PRE_NATIVE_SESSION_SEND_GET_ROUTES, PRE_NATIVE_SESSION_SEND_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert (PRE_BYOK_ROLES_GET_ROUTES, PRE_BYOK_ROLES_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
