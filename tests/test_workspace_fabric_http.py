"""Authenticated HTTP boundary tests for optional fail-closed M2 Fabric status."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from tests.test_workspace_read_app import (
    NOW, _FakeWorkspaceClient, _authenticator, _workspace_token,
)
from tests.test_workspace_fabric_authorized import Fixture, STAMP
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app


class Authorize:
    def __init__(self):
        self.allowed = True
        self.stamp = STAMP
    def __call__(self, principal):
        return self.allowed
    def binding_digest(self, principal):
        return self.stamp


@pytest.fixture
def build(rsa_key):
    def make(*, owner=True, effect=None):
        f = Fixture()
        f.effect = effect
        authz = Authorize()
        cfg = WorkspaceAppConfig(
            authenticator=_authenticator(rsa_key), now=lambda: NOW,
            authorize_principal=authz, client=_FakeWorkspaceClient(),
            fabric_status_owner=f.owner() if owner else None,
        )
        return TestClient(create_workspace_app(cfg)), f, authz
    return make


@pytest.fixture
def rsa_key():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def url():
    return "/workspace/fabric/status/current?root_id=fabric-root-01&run_id=fabric-run-01"


def headers(rsa_key):
    return {"Authorization": "Bearer " + _workspace_token(rsa_key)}


def test_unconfigured_owner_fails_before_m2(build, rsa_key):
    client, fixture, _ = build(owner=False)
    assert client.get(url(), headers=headers(rsa_key)).status_code == 503
    assert not fixture.calls


def test_authenticated_owner_scoped_and_sanitized(build, rsa_key):
    client, fixture, _ = build()
    reply = client.get(url(), headers=headers(rsa_key))
    assert reply.status_code == 200, reply.text
    assert reply.json()["run_id"] == "fabric-run-01"
    assert "prompt" not in reply.json()
    assert reply.headers["cache-control"] == "no-store"
    assert [call[0] for call in fixture.calls] == ["executive", "agent", "m2", "executive", "agent"]


def test_missing_bearer_cannot_touch_m2(build):
    client, fixture, _ = build()
    assert client.get(url()).status_code in (401, 403)
    assert not fixture.calls


def test_revoke_during_m2_acquisition_denies_return(build, rsa_key):
    def revoke(f):
        f.gr["enabled"] = False
    client, fixture, _ = build(effect=revoke)
    assert client.get(url(), headers=headers(rsa_key)).status_code == 403
    assert [c[0] for c in fixture.calls].count("m2") == 1


def test_bad_query_and_body_do_not_dispatch(build, rsa_key):
    client, fixture, _ = build()
    for bad in [url() + "&run_id=other", url().replace("fabric-run-01", "bad/run"),
                url() + "&admin=true", "/workspace/fabric/status/current"]:
        assert client.get(bad, headers=headers(rsa_key)).status_code == 400
    assert client.request("GET", url(), content=b"request body", headers=headers(rsa_key)).status_code == 400
    assert not fixture.calls


def test_base_permission_revoked_before_machine_read(build, rsa_key):
    client, fixture, authz = build()
    authz.allowed = False
    assert client.get(url(), headers=headers(rsa_key)).status_code == 403
    assert not fixture.calls


def test_base_permission_rotated_during_acquisition(build, rsa_key):
    client, fixture, authz = build()
    fixture.effect = lambda f: setattr(authz, "stamp", "f" * 64)
    assert client.get(url(), headers=headers(rsa_key)).status_code == 403


def test_wrong_method_never_dispatches(build, rsa_key):
    client, fixture, _ = build()
    assert client.post(url(), headers=headers(rsa_key)).status_code == 405
    assert not fixture.calls
