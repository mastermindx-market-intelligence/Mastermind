"""Real optional-App composition from a changing sealed-projection fixture."""
import asyncio
import dataclasses
import hashlib
import json

import pytest
from starlette.testclient import TestClient

from common import workspace_control_room_action_contract as wire
from integrations.mastermind_workspace_app import app as workspace_app, contract
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_executive_app import gateway
from ops.executive_os import executive_mcp_entry as entry
from ops.executive_os.workspace_owner_enrollment import compile_control_room_action_bindings
from tests import test_workspace_read_app as fixture
from tests import test_workspace_control_room_action_http as action
from tests.test_executive_workspace_mount import document
from tests.test_executive_mcp_app_composition import Sink

rsa_key = fixture.rsa_key


@pytest.fixture
def composed(tmp_path, monkeypatch, rsa_key):
    policy = fixture._workspace_policy()
    token = fixture._workspace_token(rsa_key)
    principal = asyncio.run(fixture._authenticator(rsa_key).verify_token(token, now=fixture.NOW))
    membership = {
        "schema": contract.MEMBER_BINDINGS_SCHEMA, "primary_profile": "member-0",
        "profiles": {"member-0": {"enabled": True, "binding": dict(
            contract.principal_frame(principal),
            permission_digest=hashlib.sha256(b"fixture-member-receipt").hexdigest(),
        )}},
    }
    selected = compile_control_room_action_bindings(policy, membership, {
        "member-0": {name: ("fixture-action:" + name).encode()
                     for name in contract.CONTROL_ROOM_ACTIONS},
    })
    raw = document()
    raw["workspace"] = {"policy": json.loads(json.dumps(dataclasses.asdict(policy))),
                        "bindings": selected}
    source = tmp_path / raw["release_sha"]
    source.mkdir()
    path = tmp_path / "app.json"
    path.write_text(json.dumps(raw))
    entry.validate_document(raw)
    seals, calls, captures = [], [], []
    monkeypatch.setattr(entry, "require_sealed_path", lambda p, **kw: seals.append(p))
    monkeypatch.setattr(entry.os, "geteuid", lambda: 458)
    monkeypatch.setattr(entry.time, "time", lambda: fixture.NOW)
    monkeypatch.setattr(gateway, "_default_jwks_cache", lambda _p: fixture._FakeJwksCache(rsa_key))
    real_factory = workspace_app.create_workspace_app
    def capture(config):
        captures.append(config)
        return real_factory(config)
    monkeypatch.setattr(workspace_app, "create_workspace_app", capture)
    async def request(_self, frame):
        calls.append(frame)
        body = (action.result(frame["operation"])
                if frame["schema"] == wire.FRAME_SCHEMA else {"probe": frame["operation"]})
        return {"ok": True, "result": body}
    monkeypatch.setattr(CeoIngressWorkspaceClient, "request", request)
    sink = Sink()
    mounts = entry.build_optional_apps(raw, source, path, sink)
    assert set(mounts) == {"workspace_app"} and len(captures) == 1
    return {"config": captures[0], "app": mounts["workspace_app"], "raw": raw,
            "path": path, "source": source, "seals": seals, "calls": calls,
            "principal": principal, "membership": membership, "token": token, "sink": sink}


def save(value):
    value["path"].write_text(json.dumps(value["raw"]))


def test_real_factory_selects_public_stamped_adapters_and_one_client(composed):
    config, principal = composed["config"], composed["principal"]
    assert config.authorize_principal(principal)
    assert config.authorize_discovery(principal)
    assert set(config.authorize_actions) == wire.OPERATIONS
    for callback in (config.authorize_discovery, *config.authorize_actions.values()):
        assert callback(principal) is True
        assert contract.permission_stamp(callback, principal) is not None
        assert callback(contract.principal_frame(principal)) is False
    assert composed["calls"] == []
    assert composed["path"] in composed["seals"]


def test_actual_composed_app_uses_each_fixed_route_and_selected_grant(composed, rsa_key):
    with TestClient(composed["app"], base_url=entry.PUBLIC_ORIGIN) as client:
        for operation in ("state", "discover"):
            response = client.get("/workspace/control-room/" + operation + "/current",
                                  headers=action.headers(rsa_key))
            assert response.status_code == 200
        for operation in action.OPERATIONS:
            response = client.post("/workspace/control-room/" + operation,
                                   headers=action.headers(rsa_key), json=action.payload(operation))
            assert response.status_code == 200
            assert response.json() == action.result(operation)
    assert [frame["operation"] for frame in composed["calls"]] == [
        "state", "discover", *action.OPERATIONS]
    assert composed["sink"].events


def test_rotating_or_withdrawing_one_sealed_grant_preserves_read_and_siblings(composed, rsa_key):
    config, principal = composed["config"], composed["principal"]
    before = {name: contract.permission_stamp(callback, principal)
              for name, callback in config.authorize_actions.items()}
    read_stamp = contract.permission_stamp(config.authorize_principal, principal)
    selected = composed["raw"]["workspace"]["bindings"]["profiles"]["member-0"]["control_room_actions"]
    selected["open"] = "e" * 64
    save(composed)
    assert contract.permission_stamp(config.authorize_actions["open"], principal) != before["open"]
    assert contract.permission_stamp(config.authorize_actions["bind"], principal) == before["bind"]
    selected["open"] = None
    save(composed)
    with TestClient(composed["app"], base_url=entry.PUBLIC_ORIGIN) as client:
        assert client.post("/workspace/control-room/open", headers=action.headers(rsa_key),
                           json=action.payload("open")).status_code == 403
        assert composed["calls"] == []
        assert client.post("/workspace/control-room/bind", headers=action.headers(rsa_key),
                           json=action.payload("bind")).status_code == 200
    assert contract.permission_stamp(config.authorize_principal, principal) == read_stamp
    assert config.authorize_discovery(principal)


@pytest.mark.parametrize("schema", ["v1", "v2"])
def test_live_legacy_read_membership_never_becomes_selected_action_authority(composed, rsa_key, schema):
    source = composed["membership"]
    if schema == "v1":
        source = {"schema": contract.BINDINGS_SCHEMA, "profiles": {
            "web": source["profiles"]["member-0"], "mac": {"enabled": False, "binding": None},
        }}
    composed["raw"]["workspace"]["bindings"] = source
    save(composed)
    with TestClient(composed["app"], base_url=entry.PUBLIC_ORIGIN) as client:
        assert client.get("/workspace/control-room/state/current",
                          headers=action.headers(rsa_key)).status_code == 200
        for name in ("discover", *action.OPERATIONS):
            route = "/workspace/control-room/" + name
            response = (client.get(route + "/current", headers=action.headers(rsa_key))
                        if name == "discover" else client.post(
                            route, headers=action.headers(rsa_key), json=action.payload(name)))
            assert response.status_code == 403
    assert [frame["operation"] for frame in composed["calls"]] == ["state"]


@pytest.mark.parametrize("fault", ["policy", "release", "identity", "seal"])
def test_current_projection_failure_does_not_reuse_an_old_grant(composed, monkeypatch, fault):
    config, principal = composed["config"], composed["principal"]
    assert config.authorize_actions["open"](principal)
    if fault == "policy":
        composed["raw"]["workspace"]["policy"]["policy_id"] = "rotated-policy"
    elif fault == "release":
        composed["raw"]["release_sha"] = "2" * 40
    elif fault == "identity":
        monkeypatch.setattr(entry.os, "geteuid", lambda: 459)
    else:
        def denied(*args, **kwargs):
            raise ValueError("fixture seal unavailable")
        monkeypatch.setattr(entry, "require_sealed_path", denied)
    save(composed)
    assert config.authorize_actions["open"](principal) is False
    assert config.authorize_discovery(principal) is False
    assert config.authorize_principal(principal) is False
    assert composed["calls"] == []
