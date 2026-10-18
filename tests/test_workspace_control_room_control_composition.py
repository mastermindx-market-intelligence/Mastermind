"""Control production composition with explicit topology and existing grants.

Only fixture configuration, inert dependencies and the original isolated cache.
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
from integrations.mastermind_workspace_app import contract
from tests.test_c1_ceo_ingress_composition import _raw, _write_config, _capture_service
from tests.test_workspace_control_room_action_grants import compile_source
from tests.test_workspace_member_bindings import principal

ACTIONS = ("open", "bind", "unbind", "refresh-builds")


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


@pytest.mark.parametrize("use_path", [False, True])
def test_control_config_accepts_explicit_cache_only(tmp_path, use_path):
    selected = str(tmp_path / "selected-bindings.json") if use_path else None
    raw, _ = workspace_raw(tmp_path, {"mode": "cache_only", "bindings_path": selected})
    loaded = cli.load_control_config(_write_config(tmp_path, raw))
    assert loaded["workspace_control_room"] == {"mode": "cache_only", "bindings_path": selected}


@pytest.mark.parametrize("port", [1, 8787, 65535])
def test_control_config_preserves_exact_legacy_topology(tmp_path, port):
    raw, _ = workspace_raw(tmp_path, {"port": port})
    assert cli.load_control_config(_write_config(tmp_path, raw))["workspace_control_room"] == {"port": port}


@pytest.mark.parametrize("topology", [
    {}, {"port": True}, {"port": 0}, {"port": 65536},
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
])
def test_control_config_refuses_open_or_mixed_topology(tmp_path, topology):
    raw, _ = workspace_raw(tmp_path, topology)
    with pytest.raises(cli.ServiceError, match="Control Room topology"):
        cli.load_control_config(_write_config(tmp_path, raw))


def capture_composition(tmp_path, monkeypatch, topology):
    raw, authority = workspace_raw(tmp_path, topology)
    raw["ceo_ingress_app_boot_python"] = tmp_path / "fixture-sealed-python"
    monkeypatch.setattr(cli, "_attest_app_boot_runtime", lambda path: path)
    captured = _capture_service(cli, monkeypatch)
    composition, arguments, calls = {}, {}, []
    def composer(**kwargs):
        composition.update(kwargs)
        def compose(now):
            calls.append(now)
            return {"schema": "mastermind.chairman_control_room.v1", "generated_at": now,
                    "work": [], "autonomy": {"generated_at": now, "responsibilities": []}}
        return compose
    monkeypatch.setattr(join, "build_workspace_composer", composer)
    monkeypatch.setattr(publisher.capability, "census", lambda **kwargs: {})
    original_factory = workspace_read_service.workspace_provider_factory
    def factory(**kwargs):
        arguments.update(kwargs)
        return original_factory(**kwargs)
    monkeypatch.setattr(workspace_read_service, "workspace_provider_factory", factory)
    current = {"authority": authority, "loads": 0}
    def loader():
        current["loads"] += 1
        return current["authority"]
    return SimpleNamespace(raw=raw, authority=authority, current=current, loader=loader,
                           captured=captured, composition=composition,
                           arguments=arguments, calls=calls)


@pytest.mark.parametrize("use_path", [False, True])
def test_production_selects_one_config_path_without_an_injected_argument(tmp_path, monkeypatch, use_path):
    selected = tmp_path / "selected-bindings.json" if use_path else None
    fx = capture_composition(tmp_path, monkeypatch, {
        "mode": "cache_only", "bindings_path": str(selected) if selected else None,
    })
    cli._service_from_config(fx.raw, workspace_acquisition_loader=fx.loader)
    host = fx.captured["workspace_control_room"]
    assert host.cache_only is True and host.config.port == 0
    assert host.config.bindings_path == fx.composition["bindings_path"] == selected
    assert fx.arguments["control_room"] is host
    assert host.current_owner() is None
    assert host._server is host._server_thread is None
    assert fx.calls == []
    if selected:
        assert not selected.exists()


@pytest.mark.parametrize("configured", [None, "absolute"])
def test_conflicting_trusted_path_refuses_before_any_host_activation(tmp_path, monkeypatch, configured):
    selected = str(tmp_path / "selected-bindings.json") if configured else None
    fx = capture_composition(tmp_path, monkeypatch, {"mode": "cache_only", "bindings_path": selected})
    from integrations.executive_mcp import installed
    def forbidden(*args, **kwargs):
        raise AssertionError("conflict reached a constructor or listener activation")
    monkeypatch.setattr(cli, "activate_launchd_socket", forbidden)
    monkeypatch.setattr(installed, "InstalledBootPacketCollector", forbidden)
    monkeypatch.setattr(join, "build_workspace_composer", forbidden)
    with pytest.raises(cli.ServiceError, match="bindings"):
        cli._service_from_config(
            fx.raw, workspace_acquisition_loader=fx.loader,
            workspace_bindings_path=tmp_path / "different-bindings.json",
        )
    assert fx.captured == fx.arguments == fx.composition == {}


def test_real_control_factory_uses_current_frame_side_action_grants(tmp_path, monkeypatch):
    fx = capture_composition(tmp_path, monkeypatch, {"mode": "cache_only", "bindings_path": None})
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
    fx = capture_composition(tmp_path, monkeypatch, {"mode": "cache_only", "bindings_path": None})
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


def test_selected_cache_only_start_never_constructs_an_http_server(tmp_path, monkeypatch):
    fx = capture_composition(tmp_path, monkeypatch, {"mode": "cache_only", "bindings_path": None})
    def forbidden_tcp(*args, **kwargs):
        raise AssertionError("ControlRoomServer must not be constructed")
    monkeypatch.setattr(publisher, "ControlRoomServer", forbidden_tcp)
    cli._service_from_config(fx.raw, workspace_acquisition_loader=fx.loader)
    host = fx.captured["workspace_control_room"]
    host.config.state_ttl = 30.0
    async def run():
        await host.start()
        try:
            assert host.current_owner() is host.config
            assert host._server is host._server_thread is None
            assert host.config.state_published_seq == 1
            assert host.config.workspace_refresh_on_read is False
            assert len(fx.calls) == 1
        finally:
            await host.close()
        assert host.current_owner() is None
        assert not host._refresh_thread.is_alive()
    asyncio.run(run())
