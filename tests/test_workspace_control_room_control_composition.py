"""Control production composition with the protected AF_UNIX room topology.

Only fixture configuration, inert dependencies and the original isolated cache.
The composition accepts exactly the protected ``validate_workspace_control_room``
unix stanza: an adopted AF_UNIX launchd listener, no TCP constructor anywhere,
and one explicitly injected workspace bindings path with no config fallback.
"""
import asyncio
import copy
import dataclasses
import json
import os
from types import SimpleNamespace

import pytest

from scripts import executive_os_phase1c as cli
from scripts import chairman_control_room as publisher
from control_plane import workspace_source_join as join, workspace_read_service
import control_plane.workspace_control_room_lifecycle as lifecycle_mod
from integrations.mastermind_workspace_app import contract
from tests.executive_installed_control_fixture import (
    spawn_workspace_room_listener, unix_stanza,
)
from tests.test_c1_ceo_ingress_composition import _raw, _write_config, _capture_service
from tests.test_workspace_control_room_action_grants import compile_source
from tests.test_workspace_member_bindings import principal

ACTIONS = ("open", "bind", "unbind", "refresh-builds")

# Listeners adopted by capture_composition; drained after every test so the
# harmless local AF_UNIX fixture never outlives the test that spawned it.
_LISTENERS = []


@pytest.fixture(autouse=True)
def _drain_fixture_listeners():
    yield
    while _LISTENERS:
        listener, socket_path = _LISTENERS.pop()
        try:
            listener.close()
        except OSError:
            pass
        try:
            os.unlink(socket_path)
        except OSError:
            pass


def workspace_raw(tmp_path, topology):
    policy, _, _, authority = compile_source()
    raw = _raw(tmp_path)
    raw.update(
        ceo_ingress_app_peer_uid=os.geteuid() + 10, ceo_ingress_app_armed=False,
        ceo_ingress_app_macro_root=tmp_path / "macro", workspace_acquisition=authority,
        workspace_resource_policy=json.loads(json.dumps(dataclasses.asdict(policy))),
        workspace_control_room=topology,
    )
    return raw, authority


def test_control_config_accepts_exact_protected_unix_stanza(tmp_path):
    stanza = unix_stanza(os.geteuid())
    raw, _ = workspace_raw(tmp_path, stanza)
    loaded = cli.load_control_config(_write_config(tmp_path, raw))
    assert loaded["workspace_control_room"] == stanza
    assert set(loaded["workspace_control_room"]) == {
        "transport", "socket_path", "launchd_socket_name", "allowed_peer_uids"}


def test_control_config_refuses_removed_legacy_topology(tmp_path):
    for topology in (
        {"port": 1}, {"port": 8787}, {"port": 65535}, {"port": 0}, {"port": True},
        {"port": 8787, "bindings_path": None},
        {"mode": "cache_only"}, {"mode": "cache_only", "bindings_path": "relative.json"},
        {"mode": "cache_only", "bindings_path": "~/bindings.json"},
        {"mode": "cache_only", "bindings_path": ""},
        {"mode": "cache_only", "bindings_path": False},
        {"mode": "cache_only", "bindings_path": []},
        {"mode": "cache_only", "bindings_path": {}, "port": 8787},
        {"mode": "cache-only", "bindings_path": None},
        {"mode": True, "bindings_path": None},
        {"mode": "cache_only", "bindings_path": None, "extra": True},
        {"mode": "cache_only", "bindings_path": None, "port": 8787},
        {"mode": "cache_only", "bindings_path": "/tmp/invalid\x00path"},
    ):
        raw, _ = workspace_raw(tmp_path, topology)
        with pytest.raises(cli.ServiceError, match="Control Room"):
            cli.load_control_config(_write_config(tmp_path, raw))


def test_control_config_refuses_malformed_unix_stanza(tmp_path):
    uid = os.geteuid()
    valid = unix_stanza(uid)
    broken = [{}]
    for key in ("transport", "socket_path", "launchd_socket_name", "allowed_peer_uids"):
        stanza = dict(valid)
        stanza.pop(key)
        broken.append(stanza)
    broken += [
        dict(valid, transport="tcp"),
        dict(valid, transport="unix,tcp"),
        dict(valid, transport=1),
        dict(valid, socket_path="relative.sock"),
        dict(valid, socket_path="/tmp/foreign-room.sock"),
        dict(valid, socket_path=""),
        dict(valid, socket_path=None),
        dict(valid, launchd_socket_name="CeoIngress"),
        dict(valid, launchd_socket_name=""),
        dict(valid, launchd_socket_name=None),
        dict(valid, allowed_peer_uids=[]),
        dict(valid, allowed_peer_uids=[uid, uid]),
        dict(valid, allowed_peer_uids=[str(uid)]),
        dict(valid, allowed_peer_uids=[True]),
        dict(valid, allowed_peer_uids=uid),
        dict(valid, allowed_peer_uids=None),
        dict(valid, bindings_path=str(tmp_path / "bindings.json")),
        dict(valid, mode="cache_only"),
        dict(valid, port=8787),
    ]
    for topology in broken:
        raw, _ = workspace_raw(tmp_path, topology)
        with pytest.raises(cli.ServiceError, match="Control Room"):
            cli.load_control_config(_write_config(tmp_path, raw))


def capture_composition(tmp_path, monkeypatch):
    listener, socket_path = spawn_workspace_room_listener(monkeypatch)
    _LISTENERS.append((listener, socket_path))
    raw, authority = workspace_raw(tmp_path, unix_stanza(os.geteuid()))
    raw["ceo_ingress_app_boot_python"] = tmp_path / "fixture-sealed-python"
    monkeypatch.setattr(cli, "_attest_app_boot_runtime", lambda path: path)
    captured = _capture_service(cli, monkeypatch)
    composition, arguments, calls, activated = {}, {}, [], []

    def composer(**kwargs):
        composition.update(kwargs)

        def compose(now):
            calls.append(now)
            return {"schema": "mastermind.chairman_control_room.v1", "generated_at": now,
                    "work": [], "autonomy": {"generated_at": now, "responsibilities": []}}
        composition["callback"] = compose
        return compose

    monkeypatch.setattr(join, "build_workspace_composer", composer)
    monkeypatch.setattr(publisher.capability, "census", lambda **kwargs: {})
    original_factory = workspace_read_service.workspace_provider_factory

    def factory(**kwargs):
        arguments.update(kwargs)
        return original_factory(**kwargs)

    monkeypatch.setattr(workspace_read_service, "workspace_provider_factory", factory)

    def adopt_listener(name):
        activated.append(name)
        return listener

    monkeypatch.setattr(cli, "activate_launchd_socket", adopt_listener)
    current = {"authority": authority, "loads": 0}

    def loader():
        current["loads"] += 1
        return current["authority"]

    return SimpleNamespace(raw=raw, authority=authority, current=current, loader=loader,
                           captured=captured, composition=composition,
                           arguments=arguments, calls=calls, activated=activated,
                           listener=listener, socket_path=socket_path)


@pytest.mark.parametrize("inject", [False, True])
def test_production_binds_exactly_one_injected_workspace_bindings_path(
        tmp_path, monkeypatch, inject):
    selected = tmp_path / "selected-bindings.json" if inject else None
    fx = capture_composition(tmp_path, monkeypatch)
    cli._service_from_config(fx.raw, workspace_acquisition_loader=fx.loader,
                             workspace_bindings_path=selected)
    host = fx.captured["workspace_control_room"]
    assert type(host) is lifecycle_mod.HostedControlRoom
    assert fx.arguments["control_room"] is host
    assert host.config.compose_inputs is fx.composition["callback"]
    assert host.config.port == 0
    assert host.config.origin == publisher.UNIX_CONTROL_ROOM_ORIGIN
    assert host.config.bindings_path == fx.composition["bindings_path"] == selected
    assert host.socket_path == fx.socket_path
    assert tuple(host.allowed_peer_uids) == (os.geteuid(),)
    assert host._listener is fx.listener
    assert fx.activated == ["Operator", "CeoIngress", cli._WORKSPACE_CONTROL_ROOM_SOCKET_NAME]
    assert host.current_owner() is None
    assert host._server is host._server_thread is None
    assert fx.calls == []
    if selected:
        assert not selected.exists()


@pytest.mark.parametrize("topology", [
    {"port": 8787},
    {"port": 0},
    {"mode": "cache_only", "bindings_path": None},
    dict(unix_stanza(os.geteuid(), socket_path="/tmp/crr-refused.sock"), transport="tcp"),
    {"transport": "unix"},
])
def test_malformed_topology_refuses_before_any_host_activation(tmp_path, monkeypatch, topology):
    from integrations.executive_mcp import installed
    fx = capture_composition(tmp_path, monkeypatch)
    fx.raw = workspace_raw(tmp_path, topology)[0]

    def forbidden(*args, **kwargs):
        raise AssertionError("refusal reached a constructor or listener activation")

    monkeypatch.setattr(cli, "activate_launchd_socket", forbidden)
    monkeypatch.setattr(installed, "InstalledBootPacketCollector", forbidden)
    monkeypatch.setattr(join, "build_workspace_composer", forbidden)
    with pytest.raises(cli.ServiceError, match="Control Room"):
        cli._service_from_config(fx.raw, workspace_acquisition_loader=fx.loader)
    assert fx.captured == fx.arguments == fx.composition == {}
    assert fx.activated == []


def test_real_control_factory_uses_current_frame_side_action_grants(tmp_path, monkeypatch):
    fx = capture_composition(tmp_path, monkeypatch)
    cli._service_from_config(fx.raw, workspace_acquisition_loader=fx.loader)
    read, discovery, actions = (fx.arguments["authorize"], fx.arguments["authorize_discovery"],
                                fx.arguments["authorize_actions"])
    assert set(actions) == set(ACTIONS)
    frame = principal(fx.authority)
    assert read(frame) is True and discovery(frame) is True
    assert all(callback(frame) is True for callback in actions.values())
    read_stamp = contract.permission_stamp(read, frame)
    bind_stamp = contract.permission_stamp(actions["bind"], frame)
    old_open = contract.permission_stamp(actions["open"], frame)
    changed = copy.deepcopy(fx.authority)
    changed["profiles"]["member-0"]["control_room_actions"]["open"] = "e" * 64
    fx.current["authority"] = changed
    assert contract.permission_stamp(actions["open"], frame) != old_open
    changed["profiles"]["member-0"]["control_room_actions"]["open"] = None
    changed["profiles"]["member-0"]["control_room_actions"]["discover"] = None
    assert fx.raw["workspace_acquisition"] is fx.authority
    assert actions["open"](frame) is False and discovery(frame) is False
    assert actions["bind"](frame) is True and read(frame) is True
    assert contract.permission_stamp(actions["bind"], frame) == bind_stamp
    assert contract.permission_stamp(read, frame) == read_stamp


@pytest.mark.parametrize("schema", ["v1", "v2"])
def test_control_production_grants_deny_legacy_read_membership(tmp_path, monkeypatch, schema):
    fx = capture_composition(tmp_path, monkeypatch)
    _, membership, _, _ = compile_source()
    if schema == "v1":
        membership = {"schema": contract.BINDINGS_SCHEMA, "profiles": {
            "web": membership["profiles"]["member-0"], "mac": {"enabled": False, "binding": None}}}
    fx.current["authority"] = membership
    cli._service_from_config(fx.raw, workspace_acquisition_loader=fx.loader)
    frame = principal(membership, "web" if schema == "v1" else "member-0")
    assert fx.arguments["authorize"](frame)
    assert not fx.arguments["authorize_discovery"](frame)
    assert all(not callback(frame) for callback in fx.arguments["authorize_actions"].values())


def test_adopted_unix_room_reuses_config_and_never_constructs_tcp(tmp_path, monkeypatch):
    fx = capture_composition(tmp_path, monkeypatch)

    def forbidden_tcp(*args, **kwargs):
        raise AssertionError("TCP ControlRoomServer must not be constructed")

    monkeypatch.setattr(publisher, "ControlRoomServer", forbidden_tcp)
    cli._service_from_config(fx.raw, workspace_acquisition_loader=fx.loader)
    host = fx.captured["workspace_control_room"]
    host.config.state_ttl = 30.0

    async def run():
        await host.start()
        try:
            assert host.current_owner() is host.config
            assert type(host._server) is publisher.UnixControlRoomServer
            assert host._listener is fx.listener
            assert host.config.state_published_seq == 1
            assert host.config.workspace_refresh_on_read is False
            assert len(fx.calls) == 1
        finally:
            await host.close()
        assert host.current_owner() is None
        assert host._server is None
        assert not host._refresh_thread.is_alive()
        assert fx.activated == ["Operator", "CeoIngress", cli._WORKSPACE_CONTROL_ROOM_SOCKET_NAME]

    asyncio.run(run())


def test_original_executive_host_selects_only_sealed_member_scoped_cross_plane_ports(tmp_path, monkeypatch):
    from control_plane.workspace_cross_plane_enrollment import InstalledCrossPlaneEnrollment
    from tests.test_executive_cross_plane_live import Owners, _scope
    fx = capture_composition(tmp_path, monkeypatch)
    ports = Owners()
    selected = []
    enrollment = InstalledCrossPlaneEnrollment(
        member_scope=lambda member: selected.append(("scope", member["client_ref"])) or _scope(),
        member_ports=lambda member, scope: selected.append(("ports", member["client_ref"])) or ports.ports(),
        stale_after_seconds=600,
    )
    cli._service_from_config(
        fx.raw, workspace_acquisition_loader=fx.loader,
        installed_cross_plane_enrollment=enrollment,
    )
    selector = fx.arguments["cross_plane_context"]
    assert callable(selector)
    assert "cross_plane_context" not in fx.raw
    assert "installed_cross_plane_enrollment" not in fx.raw
    assert fx.arguments["authorize"](principal(fx.authority)) is True
    host = fx.captured["workspace_control_room"]
    context = selector(principal(fx.authority), host.config)
    assert context.scope == _scope()
    assert context.ports == ports.ports()
    assert selected == [("scope", principal(fx.authority)["client_ref"]),
                        ("ports", principal(fx.authority)["client_ref"])]
    assert host.config.port == 0 and host._server is None
    assert fx.activated == ["Operator", "CeoIngress", cli._WORKSPACE_CONTROL_ROOM_SOCKET_NAME]


def test_unenrolled_executive_host_does_not_mint_cross_plane_source(tmp_path, monkeypatch):
    fx = capture_composition(tmp_path, monkeypatch)
    cli._service_from_config(fx.raw, workspace_acquisition_loader=fx.loader)
    assert fx.arguments["cross_plane_context"] is None


def test_invalid_cross_plane_enrollment_is_refused_before_listener_activation(tmp_path, monkeypatch):
    fx = capture_composition(tmp_path, monkeypatch)
    with pytest.raises(cli.ServiceError, match="qualified installed cross-plane owner required"):
        cli._service_from_config(
            fx.raw, workspace_acquisition_loader=fx.loader,
            installed_cross_plane_enrollment={"scope": ["WS:AGENT-OS"], "token": "none"},
        )
    assert fx.activated == []
    assert fx.captured == fx.arguments == {}
