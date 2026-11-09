"""Actual RS256 verifier/current permission owners; inert native/source boundary.

No account, credential, provider, service, source body or Runtime effect.
"""
import asyncio
import json
from types import SimpleNamespace
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
from integrations.mastermind_workspace_app.app import create_workspace_app
from integrations.mastermind_workspace_app.native_authorization_identity import identity_routes, content_identity_endpoint
from integrations.mastermind_window_reader.owner_read_resource import from_existing_business_owner, NativeOutputReadResource
from integrations.mastermind_steward_app.live_window import LiveWindowDispatch
from common import native_authorization_identity_contract as wire
from tests.test_native_draft_identity import owner
from tests.test_executive_workspace_mount import settings
from tests.test_workspace_read_app import rsa_key, _workspace_policy, _authenticator, _workspace_token, NOW, ISSUER, SUBJECT
from integrations.business_mcp_auth.contracts import subject_digest

ORIGIN = "https://mcp.mastermind-x.com"

def composition(rsa_key, *, content_subject=SUBJECT, client="workspace-read-test-client"):
    acquired = owner(rsa_key)
    policy = _workspace_policy(policy_id="content-identity-fixture", resource=wire.RESOURCES["CONTENT"],
        resource_metadata_url=wire.RESOURCES["CONTENT"] + "/.well-known/oauth-protected-resource",
        required_scopes=["mastermind.workspace.content.read"],
        allowed_subject_digests=[subject_digest(issuer=ISSUER, subject=content_subject)])
    auth = _authenticator(rsa_key, policy=policy)
    token = _workspace_token(rsa_key, resource=wire.RESOURCES["CONTENT"], scope="mastermind.workspace.content.read",
                             sub=content_subject, client_id=client)
    state = {"allowed": True, "stamp": "fixture-content-current", "reads": 0, "checks": 0,
             "now": NOW, "after": None, "audit": []}
    async def current(principal, ref):
        assert ref == "managed-window:fixture"
        assert principal.resource == wire.RESOURCES["CONTENT"]
        state["checks"] += 1
        if state["after"]: state["after"]()
        if state.get("pause"):
            await asyncio.sleep(state["pause"])
        return (state["stamp"],) if state["allowed"] else None
    async def read():
        state["reads"] += 1
        raise AssertionError("Identity must never read a private window")
    class Audit:
        def emit(self, event): state["audit"].append(event)
    reader = from_existing_business_owner(authenticator=auth, policy=policy, current_access=current,
        read_source=read, source_ref="managed-window:fixture", now=lambda: state["now"],
        allowed_origin=ORIGIN, audit_sink=Audit(), source_kind="live-window")
    http = TestClient(Starlette(routes=identity_routes(acquisition_config=acquired.config, content_reader=reader)), base_url=ORIGIN)
    return SimpleNamespace(http=http, acquired=acquired, content_token=token, reader=reader, auth=auth, state=state)


def get(s, kind, token=None, **kwargs):
    access = token if token is not None else s.acquired.token if kind == "ACQUISITION" else s.content_token
    return s.http.get(wire.ROUTES[kind], headers={"Authorization": "Bearer " + access}, **kwargs)


def test_actual_signed_same_account_resource_proofs_are_comparable_without_content(rsa_key):
    s = composition(rsa_key)
    a, c = get(s, "ACQUISITION"), get(s, "CONTENT")
    assert a.status_code == c.status_code == 200
    first, other = a.json(), c.json()
    assert set(first) == {"schema", "resource", "account_digest", "expires_at_ms"}
    assert first["account_digest"] == other["account_digest"]
    assert first["resource"] != other["resource"]
    assert first["expires_at_ms"] == other["expires_at_ms"] == (NOW + 300) * 1000
    assert s.state["reads"] == 0 and s.acquired.source.calls == []
    for r in (a, c):
        assert r.headers["cache-control"] == "no-store"
        assert SUBJECT not in r.text and s.content_token not in r.text and s.acquired.token not in r.text


@pytest.mark.parametrize("change", ["account", "client"])
def test_verified_other_account_or_client_never_matches_acquisition(rsa_key, change):
    s = composition(rsa_key, content_subject="another-allowed-synthetic-account" if change == "account" else SUBJECT,
                    client="different-client" if change == "client" else "workspace-read-test-client")
    a, c = get(s, "ACQUISITION"), get(s, "CONTENT")
    assert a.status_code == c.status_code == 200
    assert a.json()["account_digest"] != c.json()["account_digest"]
    assert s.state["reads"] == 0


@pytest.mark.parametrize("kind", ["ACQUISITION", "CONTENT"])
@pytest.mark.parametrize("bad", ["wrong_resource", "foreign_subject", "expired", "unsigned", "query", "body", "method", "path", "http", "duplicate"])
def test_fixed_metadata_refusals_do_not_disclose_identity(rsa_key, kind, bad):
    s = composition(rsa_key); route = wire.ROUTES[kind]
    token = s.acquired.token if kind == "ACQUISITION" else s.content_token
    headers = [("Authorization", "Bearer " + token)]
    if bad == "wrong_resource": headers = [("Authorization", "Bearer " + (s.content_token if kind == "ACQUISITION" else s.acquired.token))]
    if bad == "foreign_subject": headers = [("Authorization", "Bearer " + _workspace_token(rsa_key, sub="foreign"))]
    if bad == "expired":
        s.acquired.clock[0] = NOW + 300; s.state["now"] = NOW + 300
    if bad == "unsigned": headers = []
    if bad == "query": route += "?resource=EXECUTIVE"
    if bad == "path": route = route.replace("native-authorization", "%6eative-authorization")
    if bad == "duplicate": headers *= 2
    url = "http://mcp.mastermind-x.com" + route if bad == "http" else route
    response = s.http.request("HEAD" if bad == "method" else "GET", url, headers=headers, content=b"{}" if bad == "body" else None)
    assert response.status_code != 200
    assert "account_digest" not in response.text and s.state["reads"] == 0 and s.acquired.source.calls == []


@pytest.mark.parametrize("change", ["revoke", "stamp", "policy", "clock", "reader"])
def test_content_actual_owner_rechecks_currentness_around_body_read(rsa_key, change):
    s = composition(rsa_key)
    async def request(scope, receive, send):
        from starlette.requests import Request
        endpoint = content_identity_endpoint(s.reader)
        response = await endpoint(Request(scope, receive))
        await response(scope, receive, send)
    async def run():
        messages = []; done = False
        async def receive():
            nonlocal done
            if not done:
                done = True
                if change == "revoke": s.state["allowed"] = False
                elif change == "stamp": s.state["stamp"] = "changed"
                elif change == "policy": s.auth._policy = _workspace_policy()
                elif change == "clock": s.state["now"] = NOW + 300
                elif change == "reader": s.reader._owner = object()
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message): messages.append(message)
        await request({"type": "http", "method": "GET", "scheme": "https", "root_path": "", "query_string": b"",
          "path": wire.ROUTES["CONTENT"], "raw_path": wire.ROUTES["CONTENT"].encode(),
          "headers": [(b"host", b"mcp.mastermind-x.com"), (b"authorization", ("Bearer " + s.content_token).encode())]}, receive, send)
        return messages
    messages = asyncio.run(run())
    assert messages[0]["status"] == 403
    assert b"account_digest" not in messages[1]["body"] and s.state["reads"] == 0


def test_registered_acquisition_route_reuses_real_workspace_app_without_changing_s35(rsa_key):
    s = composition(rsa_key)
    http = TestClient(create_workspace_app(s.acquired.config), base_url=ORIGIN)
    response = http.get(wire.ROUTES["ACQUISITION"], headers={"Authorization": "Bearer " + s.acquired.token})
    assert response.status_code == 200 and response.json()["resource"] == "ACQUISITION"
    old = http.get("/workspace/native-draft-identity/current", headers={"Authorization": "Bearer " + s.acquired.token})
    assert old.status_code == 200 and set(old.json()) == {"schema", "principal_scope", "expires_at_ms"}


def test_content_dispatch_mounts_only_actual_issued_owner_and_reads_no_window(rsa_key):
    s = composition(rsa_key)
    async def unavailable(scope, receive, send):
        from starlette.responses import JSONResponse
        await JSONResponse({"error": "not_found"}, status_code=404)(scope, receive, send)
    app = LiveWindowDispatch(unavailable, reader=s.reader, path=b"/workspace/window/current", canonical_raw_path=lambda scope: scope["raw_path"])
    response = TestClient(app, base_url=ORIGIN).get(wire.ROUTES["CONTENT"], headers={"Authorization": "Bearer " + s.content_token})
    assert response.status_code == 200 and s.state["reads"] == 0
    fake = NativeOutputReadResource(owner=SimpleNamespace(authorize=lambda *a: None, read=lambda *a: None),
        resource=wire.RESOURCES["CONTENT"], source_ref="managed-window:fixture", allowed_origin=ORIGIN, source_kind="live-window")
    with pytest.raises(TypeError): content_identity_endpoint(fake)


def test_content_identity_uses_existing_read_owner_timeout(rsa_key):
    s = composition(rsa_key)
    s.reader._timeout = 0.001
    s.state["pause"] = 60
    response = get(s, "CONTENT")
    assert response.status_code == 403 and "account_digest" not in response.text
    assert s.state["reads"] == 0


@pytest.mark.parametrize("change", ["revoke", "stamp", "expiry", "owner"])
def test_acquisition_owner_rechecks_after_body(rsa_key, monkeypatch, change):
    from integrations.mastermind_workspace_app import native_authorization_identity as module
    s = composition(rsa_key)
    original = module._empty_body
    async def changed(request):
        result = await original(request)
        if change == "revoke": s.acquired.slots["profiles"]["web"]["enabled"] = False
        elif change == "stamp": s.acquired.slots["profiles"]["web"]["binding"]["permission_digest"] = "b" * 64
        elif change == "expiry": s.acquired.clock[0] = s.acquired.principal.expires_at
        else: object.__setattr__(s.acquired.config, "authorize_principal", lambda _: True)
        return result
    monkeypatch.setattr(module, "_empty_body", changed)
    response = get(s, "ACQUISITION")
    assert response.status_code == 403 and "account_digest" not in response.text
    assert s.acquired.source.calls == []


def test_actual_outer_pair_registers_only_nominal_fixed_read_owners(rsa_key, settings):
    from integrations.executive_mcp import server
    from tests.test_executive_workspace_mount import existing
    from integrations.mastermind_steward_app.live_window import supports_native_content_identity
    s = composition(rsa_key)
    async def absent(scope, receive, send):
        from starlette.responses import JSONResponse
        await JSONResponse({"error": "not_found"}, status_code=404)(scope, receive, send)
    content = LiveWindowDispatch(Starlette(), reader=s.reader, path=b"/workspace/window/current",
        canonical_raw_path=lambda scope: scope["raw_path"])
    assert supports_native_content_identity(content)
    assert not supports_native_content_identity(SimpleNamespace(native_identity=lambda: True))
    outer = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(),
        workspace_app=create_workspace_app(s.acquired.config), content_app=content)
    with TestClient(outer, base_url=ORIGIN) as client:
        for kind, token in [("ACQUISITION", s.acquired.token), ("CONTENT", s.content_token)]:
            path = wire.ROUTES[kind]; headers = {"Authorization": "Bearer " + token}
            response = client.get(path, headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()["resource"] == kind
            for bad_path, method, bad_headers in [
                (path + "?resource=EXECUTIVE", "GET", headers),
                (path, "HEAD", headers), (path, "POST", headers),
                (path + "/", "GET", headers),
                (path.replace("native-authorization", "%6eative-authorization"), "GET", headers),
                (path, "GET", {}), (path, "GET", {**headers, "Origin": "https://foreign.example"})]:
                refused = client.request(method, bad_path, headers=bad_headers)
                assert refused.status_code in (400, 401, 403, 404, 405)
                assert "account_digest" not in refused.text
        s.state["allowed"] = False
        assert client.get(wire.ROUTES["CONTENT"], headers={"Authorization": "Bearer " + s.content_token}).status_code == 403
        assert s.state["reads"] == 0 and s.acquired.source.calls == []


def test_edge_addition_preserves_exact_predecessors_and_no_partial_upgrade():
    from ops.executive_os.os_public_edge import (
        GET_ROUTES, POST_ROUTES, TRANSITION_ROUTE_PROFILES,
        PRE_AUTHORIZATION_IDENTITY_GET_ROUTES, PRE_COMPANY_PRIORITIES_POST_ROUTES,
        AUTHORIZATION_IDENTITY_GET_ROUTES)
    assert AUTHORIZATION_IDENTITY_GET_ROUTES == (wire.ROUTES["ACQUISITION"], wire.ROUTES["CONTENT"])
    assert GET_ROUTES == PRE_AUTHORIZATION_IDENTITY_GET_ROUTES + AUTHORIZATION_IDENTITY_GET_ROUTES
    assert (PRE_AUTHORIZATION_IDENTITY_GET_ROUTES, PRE_COMPANY_PRIORITIES_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert (PRE_AUTHORIZATION_IDENTITY_GET_ROUTES, POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert (GET_ROUTES, POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    for path in AUTHORIZATION_IDENTITY_GET_ROUTES:
        assert path not in POST_ROUTES
        assert (PRE_AUTHORIZATION_IDENTITY_GET_ROUTES + (path,), POST_ROUTES) not in TRANSITION_ROUTE_PROFILES
