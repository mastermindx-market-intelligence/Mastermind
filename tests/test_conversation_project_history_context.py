"""Actual signed READ/ASGI context; no provider, socket, target or write call."""
import pytest
from tests import test_mastermind_os_session_transport as owner
from tests import test_mastermind_os_session_composition as composition

rsa_key = owner.rsa_key
settings = composition.settings
short_socket_root = composition.short_socket_root
PATH = "/os/executive/session/history-context"


def read(app, token, payload=None, **kwargs):
    return owner.request(app, token, "history_context",
                         {"selection": {"work_ref": owner.WORK}} if payload is None else payload,
                         raw_path=PATH.encode(), scope_changes={"path": PATH}, **kwargs)


@pytest.mark.parametrize("submit", [False, True])
def test_real_read_principal_project_context_has_no_target_or_mutation_authority(rsa_key, submit):
    app, peer, _, _ = owner.make_app(rsa_key)
    token = (owner.auth_fixture._submit_token if submit else owner.auth_fixture._read_token)(rsa_key)
    status, result = read(app, token)
    assert status == 200 and result["ok"] and result["effect"] == "NONE"
    data = result["data"]
    assert set(data) == {"schema", "principal_scope", "verified_expiry", "selection", "capabilities"}
    assert data["schema"] == "mastermind.os.executive.project_history_context.v1"
    assert data["selection"] == {"work_ref": owner.WORK}
    assert len(data["principal_scope"]) == 64 and data["verified_expiry"] > owner.NOW
    assert data["capabilities"] == {"references_read": True, "reply_read": True}
    assert peer.calls == []  # no target/session discovery or history fanout


@pytest.mark.parametrize("selection", [
    {"work_ref": owner.WORK, "root_job_id": owner.ROOT},
    {"work_ref": owner.WORK, "send": True}, {"work_ref": owner.WORK + "\n"},
    {"work_ref": "../foreign"}, {}, {"work_ref": None},
])
def test_closed_rootless_read_input_rejects_borrowed_roots_and_capabilities(rsa_key, selection):
    app, peer, _, _ = owner.make_app(rsa_key)
    status, result = read(app, owner.auth_fixture._read_token(rsa_key), {"selection": selection})
    assert status == 400 and not result["ok"] and result["data"] is None
    assert result["effect"] == "NONE" and not peer.calls


@pytest.mark.parametrize("claims", [
    {"sub": "foreign-subject"}, {"aud": "https://foreign.example/mcp"},
    {"iss": "https://foreign.example"}, {"exp": owner.NOW - 100}, {"scope": ""},
])
def test_foreign_expired_or_revoked_principal_never_receives_context(rsa_key, claims):
    app, peer, _, _ = owner.make_app(rsa_key)
    token = owner.auth_fixture._token(rsa_key, **{"scope": owner.auth_fixture.READ_SCOPE, **claims})
    status, result = read(app, token)
    assert status in (401, 403) and not result["ok"] and result["data"] is None
    assert not peer.calls


def test_expiry_between_pre_and_post_auth_withholds_context(rsa_key):
    app, peer, clock, _ = owner.make_app(rsa_key)
    same = app._same_principal
    calls = []

    async def after_verified(*args):
        result = await same(*args)
        calls.append(result)
        if len(calls) == 1:
            clock[0] += 3600
        return result

    app._same_principal = after_verified
    status, result = read(app, owner.auth_fixture._read_token(rsa_key))
    assert calls == [True, False]
    assert status == 401 and result["data"] is None and result["effect"] == "NONE"
    assert not peer.calls


def test_project_selector_is_not_a_target_lookup_or_foreign_history_disclosure(rsa_key):
    app, peer, _, _ = owner.make_app(rsa_key)
    token = owner.auth_fixture._read_token(rsa_key)
    _, first = read(app, token)
    status, second = read(app, token, {"selection": {"work_ref": "WS:OTHER"}})
    assert status == 200 and second["data"]["selection"] == {"work_ref": "WS:OTHER"}
    assert second["data"]["principal_scope"] == first["data"]["principal_scope"]
    assert not peer.calls  # own references/reply still separately authorize original principal


@pytest.mark.parametrize("coo", [False, True])
def test_exact_route_is_reachable_through_real_installed_v3_factory(settings, rsa_key, coo):
    app, peer, audit, _ = composition.build(settings, coo=coo)
    status, result = read(app, owner.auth_fixture._read_token(rsa_key))
    assert status == 200 and result["effect"] == "NONE"
    assert result["data"]["selection"] == {"work_ref": owner.WORK}
    assert result["data"]["capabilities"] == {"references_read": True, "reply_read": True}
    assert audit.events and not peer.calls


@pytest.mark.parametrize("coo", [False, True])
def test_no_history_route_is_installed_without_actual_bridge_composition(settings, coo):
    app, peer, _, _ = composition.build(settings, coo=coo, supply=False)
    response, _ = composition.raw_request(app, operation="history-context")
    assert response["status"] == 404 and not peer.calls
