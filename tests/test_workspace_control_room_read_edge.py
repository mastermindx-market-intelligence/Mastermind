"""Signed GET-only Control Room reads over the existing Workspace A1 edge.

Private JWT signing keys and transport are fixtures; never touch live Auth0.
"""
import pytest

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from common.executive_workspace_contract import RESOURCE, SCOPE
from common.workspace_control_room_read_contract import (
    FRAME_SCHEMA, validate_frame,
)
from tests.test_workspace_read_app import (
    _make_app, _workspace_token, _FakeWorkspaceClient, rsa_key,
)


def permitted():
    def authorize(p):
        return (type(p) is VerifiedPrincipal
                and p.policy_id == "bsc-workspace-read-test"
                and p.resource == RESOURCE and p.scopes == (SCOPE,))
    authorize.binding_digest = lambda p: (
        "a" * 64 if authorize(p) else None
    )
    return authorize


def get(client, key, **kwargs):
    return client.get(key, **kwargs)


@pytest.mark.parametrize("operation", ["state", "discover"])
def test_valid_signed_workspace_principal_reaches_only_exact_read_frame(rsa_key, operation):
    payload = {"control_room": {"schema": "mastermind.chairman_control_room.v1"},
               "composed_at": "2026-10-17T00:00:00Z"}
    client, backend = _make_app(rsa_key, client=_FakeWorkspaceClient(
        envelope={"ok": True, "result": payload}), authorize=permitted(),
        authorize_discovery=permitted() if operation == "discover" else None)
    response = get(client, f"/workspace/control-room/{operation}/current", headers={
        "Authorization": "Bearer " + _workspace_token(rsa_key),
    })
    assert response.status_code == 200 and response.json() == payload
    assert backend.calls[-1]["schema"] == FRAME_SCHEMA
    assert backend.calls[-1]["operation"] == operation
    assert backend.calls[-1]["principal"]["scopes"] == ["mastermind.workspace.read"]
    assert "Cache-Control" in response.headers and response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("operation", ["state", "discover"])
def test_no_jwt_never_reaches_host_client(rsa_key, operation):
    app, backend = _make_app(rsa_key, authorize=permitted())
    response = get(app, f"/workspace/control-room/{operation}/current")
    assert response.status_code in {401, 403}
    assert backend.calls == []


@pytest.mark.parametrize("kind", ["unknown_query", "duplicate", "body", "post",
                                    "path_alias", "trailing_slash"])
def test_fences_refuse_before_private_client(rsa_key, kind):
    app, backend = _make_app(rsa_key, authorize=permitted())
    hdrs = {"Authorization": "Bearer " + _workspace_token(rsa_key)}
    route = "/workspace/control-room/state/current"
    if kind == "unknown_query":
        response = app.get(route + "?principal=admin%40mastermind-x.com", headers=hdrs)
    elif kind == "duplicate":
        response = app.get(route + "?x=1&x=2", headers=hdrs)
    elif kind == "body":
        response = app.request("GET", route, headers=hdrs, content=b"forged")
    elif kind == "post":
        response = app.post(route, headers=hdrs, json={"operation": "bind"})
    elif kind == "path_alias":
        response = app.get("/workspace/control-room%2Fstate/current", headers=hdrs)
    else:
        response = app.get(route + "/", headers=hdrs, follow_redirects=False)
    assert response.status_code in {400, 404, 405}
    assert backend.calls == []


def test_revoked_member_refused_even_with_signed_jwt(rsa_key):
    app, backend = _make_app(rsa_key, authorize=lambda _: False)
    result = get(app, "/workspace/control-room/state/current",
                 headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert result.status_code == 403 and backend.calls == []


def test_owner_revocation_during_host_read_refuses_release(rsa_key):
    active = [True]
    def owner(p):
        return active[0]
    owner.binding_digest = lambda p: ("a" * 64 if active[0] else None)
    backend = _FakeWorkspaceClient(on_call=lambda _: active.__setitem__(0, False))
    app, _ = _make_app(rsa_key, client=backend, authorize=owner)
    result = get(app, "/workspace/control-room/state/current",
                 headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert result.status_code == 403 and backend.calls


def test_discovery_remains_dark_without_original_action_grant(rsa_key):
    backend = _FakeWorkspaceClient(envelope={
        "ok": False, "status": 403,
        "error": {"code": "access_denied", "message": "control room unavailable"},
    })
    app, _ = _make_app(rsa_key, client=backend, authorize=permitted())
    response = get(app, "/workspace/control-room/discover/current",
                   headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 403
    assert "candidate" not in str(response.json())


def test_refuse_action_as_read_frame_even_with_valid_member():
    import copy
    from tests.test_workspace_read_service import frame
    p = copy.deepcopy(frame("programs")["principal"])
    for op in ("open", "bind", "unbind", "refresh-builds", "prepare", "state/../bind"):
        with pytest.raises(ValueError):
            validate_frame({"schema": FRAME_SCHEMA, "operation": op, "principal": p})


def test_three_signed_members_share_the_public_client_with_independent_revocation(rsa_key):
    """Real fixture JWT verification + existing sealed v2 owner, not role labels."""
    import asyncio
    import hashlib
    from integrations.business_mcp_auth.contracts import subject_digest
    from integrations.mastermind_workspace_app.contract import (
        MEMBER_BINDINGS_SCHEMA, principal_frame, workspace_authorizers,
    )
    from tests.test_workspace_read_app import ISSUER, NOW, _workspace_policy, _authenticator

    subjects = ["test-admin-opaque", "test-member-one", "test-member-two"]
    policy = _workspace_policy(allowed_subject_digests=sorted(
        subject_digest(issuer=ISSUER, subject=s) for s in subjects))
    authenticator = _authenticator(rsa_key, policy=policy)
    tokens = [_workspace_token(rsa_key, sub=s) for s in subjects]
    principals = [asyncio.run(authenticator.verify_token(token, now=NOW)) for token in tokens]
    assert len({p.client_ref for p in principals}) == 1
    source = {"schema": MEMBER_BINDINGS_SCHEMA, "primary_profile": "member-0", "profiles": {
        f"member-{i}": {"enabled": True, "binding": dict(principal_frame(p),
            permission_digest=hashlib.sha256(f"test-enrollment-{i}".encode()).hexdigest())}
        for i, p in enumerate(principals)
    }}
    authorize, _ = workspace_authorizers(policy=policy, load_bindings=lambda: source)
    app, backend = _make_app(rsa_key, authorize=authorize, policy=policy)
    route = "/workspace/control-room/state/current"
    for token in tokens:
        assert app.get(route, headers={"Authorization": "Bearer " + token}).status_code == 200
    assert len(backend.calls) == 3
    source["profiles"]["member-0"]["enabled"] = False
    assert app.get(route, headers={"Authorization": "Bearer " + tokens[0]}).status_code == 403
    assert len(backend.calls) == 3
    assert app.get(route, headers={"Authorization": "Bearer " + tokens[1]}).status_code == 200
    # A user-controlled email query is never substituted for signed identity.
    assert app.get(route + "?principal=admin%40mastermind-x.com").status_code in {400, 401, 403}
