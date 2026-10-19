"""Source qualification of opt-in launcher selection; no installed mutation."""
import asyncio
import copy
import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from control_plane.principal_ruling_target import PrincipalRulingTarget
from integrations.executive_mcp import server
from integrations.executive_mcp.coo import COO_TOOL_NAMES
from ops.executive_os import executive_mcp_entry as entry
from tests import test_executive_coo_host as host
from tests import test_executive_coo_install_binding as install
from tests import test_principal_ruling_mcp_producer as producer

rsa_key = producer.rsa_key


def document(tmp_path):
    _, coo, _, _ = host.setup(tmp_path)
    raw = install.base_document()
    raw.update(coo=coo, executive_mcp_profile="web_ceo_v2")
    raw["principal_ruling_target"] = dict(work_ref=coo["missions"][0]["work_ref"],
        obligation_id=producer.target().obligation_id, reasoning_surface="qualified-host")
    return raw


@pytest.mark.parametrize("fault", ["none", "absent", "extra", "null", "invalid", "foreign_work", "no_mission", "wrong_profile"])
def test_closed_sealed_target_selection(tmp_path, fault):
    raw = document(tmp_path)
    if fault == "absent": del raw["principal_ruling_target"]
    elif fault == "extra": raw["principal_ruling_target"]["caller"] = {}
    elif fault == "null": raw["principal_ruling_target"] = None
    elif fault == "invalid": raw["principal_ruling_target"]["obligation_id"] = "newest"
    elif fault == "foreign_work": raw["principal_ruling_target"]["work_ref"] = "WS:FOREIGN"
    elif fault == "no_mission": raw["coo"]["missions"] = []
    elif fault == "wrong_profile": raw["executive_mcp_profile"] = "legacy"
    if fault in {"none", "absent"}:
        entry.validate_document(raw)
        target = entry.build_installed_principal_ruling_target(raw)
        assert target is None if fault == "absent" else dataclasses.asdict(target) == raw["principal_ruling_target"]
    else:
        with pytest.raises(ValueError): entry.validate_document(raw)


def test_selected_target_is_stdlib_only_in_control_config_reader(tmp_path):
    raw = document(tmp_path)
    code = ("import sys,json;sys.path.insert(0," + repr(str(Path(__file__).parents[1])) + ");"
        "from ops.executive_os import executive_mcp_entry as e;"
        "e.validate_document(json.loads(sys.stdin.read()));"
        "assert not {'mcp','httpx','jwt','starlette'}.intersection(sys.modules);print('OK')")
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code],
        input=json.dumps(raw), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


@pytest.mark.parametrize("change", ["obligation_id", "reasoning_surface", "withdraw"])
def test_running_principal_cannot_follow_target_rotation(tmp_path, monkeypatch, change):
    raw = document(tmp_path)
    source = tmp_path / raw["release_sha"]
    source.mkdir()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw))
    monkeypatch.setattr(entry, "require_sealed_path", lambda *a, **kw: None)
    monkeypatch.setattr(entry.os, "geteuid", lambda: 458)
    loader = entry.current_projection_loader(path, source, raw, "coo", "binding")
    assert loader() == raw["coo"]["binding"]
    altered = copy.deepcopy(raw)
    if change == "withdraw": del altered["principal_ruling_target"]
    elif change == "obligation_id": altered["principal_ruling_target"][change] = "WAKE-" + "b"*32
    else: altered["principal_ruling_target"][change] = "another-host"
    path.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="configuration changed"): loader()


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("selected", [False, True])
def test_same_listener_selection_preserves_coo_profile_and_owns_lifecycle(rsa_key, tmp_path, version, selected):
    _, token, _, settings = producer.fixture.setup_principal(rsa_key, tmp_path)
    kwargs = dict(coo_settings=settings, audit_sink=producer.fixture.fixture.Sink(),
        principal_ruling_target=producer.target() if selected else None)
    if version == 2:
        app = server.build_web_ceo_v2_with_coo_mcp_app(settings.executive, **kwargs)
    else:
        async def unused(*a, **kw): raise AssertionError("listing must not access effects")
        class Mdm:
            list_macos_devices = unused
            device = unused
        app = server.build_web_ceo_v3_with_coo_mcp_app(settings.executive, **kwargs,
            mdm_reader=Mdm(), session_target_projector=unused,
            session_reply_handler=unused, session_summon_handler=unused)
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                result = await client.post("/mcp/coo", headers=producer.headers(token), json=producer.rpc("tools/list"))
                assert tuple(t["name"] for t in result.json()["result"]["tools"]) == COO_TOOL_NAMES
                ruling = await client.post(producer.PATH, headers=producer.headers(token), json=producer.rpc("tools/list"))
                if selected:
                    assert ruling.status_code == 200, ruling.text
                    assert [t["name"] for t in ruling.json()["result"]["tools"]] == ["ruling"]
                else:
                    assert ruling.status_code == 404
                assert (await client.post(producer.PATH+"/", headers=producer.headers(token), json=producer.rpc("tools/list"))).status_code == 404
    asyncio.run(exercise())


@pytest.mark.parametrize("lose_response", [False, True])
def test_selected_composition_reaches_original_worker(tmp_path, monkeypatch, rsa_key, lose_response):
    def composed(core, *, target):
        return server.build_web_ceo_v2_with_coo_mcp_app(core.settings.executive,
            coo_settings=core.settings, audit_sink=core._audit_sink, principal_ruling_target=target)
    monkeypatch.setattr(producer, "build_principal_ruling_mcp_app", composed)
    producer.test_signed_mcp_consumption_and_original_response_recovery(
        tmp_path, monkeypatch, rsa_key, lose_response, True)


def test_unselected_prefix_retains_existing_metadata_semantics(rsa_key, tmp_path):
    _, token, _, settings = producer.fixture.setup_principal(rsa_key, tmp_path)
    from integrations.mastermind_executive_app.gateway import AppPolicies
    path = "https://mcp.mastermind-x.com" + producer.PATH
    policies = AppPolicies(dataclasses.replace(settings.executive.policies.read, resource_metadata_url=path),
        dataclasses.replace(settings.executive.policies.submit, resource_metadata_url=path))
    base = dataclasses.replace(settings.executive, policies=policies)
    selected = dataclasses.replace(settings, executive=base,
        policy=dataclasses.replace(settings.policy, resource_metadata_url=path))
    app = server.build_web_ceo_v2_with_coo_mcp_app(base, coo_settings=selected,
        audit_sink=producer.fixture.fixture.Sink())
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            assert (await client.get(producer.PATH)).status_code == 200
    asyncio.run(exercise())
    with pytest.raises(ValueError, match="metadata route"):
        server.build_web_ceo_v2_with_coo_mcp_app(base, coo_settings=selected,
            audit_sink=producer.fixture.fixture.Sink(), principal_ruling_target=producer.target())


@pytest.mark.parametrize("principal,dialogue,valid", [(False, False, True), (True, False, True),
    (True, True, True), (False, True, False), (True, 1, False), (True, "true", False)])
def test_control_dialogue_selection_requires_separate_exact_opt_in(principal, dialogue, valid):
    from ops.executive_os.coo_principal_host import validate_control_coo
    raw = dict(coo_principal_armed=principal, coo_principal_dialogue_armed=dialogue,
        executive_mcp_profile="web_ceo_v2", workspace_acquisition={}, workspace_resource_policy={},
        workspace_control_room={"transport": "unix",
                                "socket_path": "/var/run/mastermind-executive/workspace-control-room.sock",
                                "launchd_socket_name": "WorkspaceControlRoom",
                                "allowed_peer_uids": [os.geteuid()]}, ceo_ingress_app_peer_uid=458)
    if valid: assert validate_control_coo(raw) is principal
    else:
        with pytest.raises(ValueError): validate_control_coo(raw)


@pytest.mark.parametrize("selected", [False, True])
def test_control_launcher_selects_same_service_runtime_without_observation_socket(tmp_path, monkeypatch, selected):
    from types import SimpleNamespace
    from scripts import executive_os_phase1c as cli
    from tests.test_c1_ceo_ingress_composition import _raw
    from tests.test_workspace_read_app import _workspace_policy
    from control_plane import executive_worker_broker, workspace_source_join
    from control_plane.executive_runtime import Runtime
    from integrations.mastermind_company_principal_app_receiver import PrincipalDialogueAppReceiver
    from integrations.slack_agent_dialogue.host_local_observation import HostLocalDialogueObservationReader
    owner, _, _, _ = host.setup(tmp_path)
    raw = _raw(tmp_path)
    raw.update(ceo_ingress_app_peer_uid=458, ceo_ingress_app_armed=False,
        ceo_ingress_app_macro_root=tmp_path/"macro",
        workspace_control_room={"transport": "unix",
                                "socket_path": "/var/run/mastermind-executive/workspace-control-room.sock",
                                "launchd_socket_name": "WorkspaceControlRoom",
                                "allowed_peer_uids": [raw["control_uid"]]},
        workspace_acquisition={}, workspace_resource_policy=json.loads(json.dumps(dataclasses.asdict(_workspace_policy()))),
        ceo_ingress_app_boot_python=tmp_path/"sealed-python", executive_mcp_profile="web_ceo_v2",
        coo_principal_armed=True, coo_principal_dialogue_armed=selected)
    authority = {"schema": "mastermind.workspace_acquisition_bindings.v1", "profiles": {
        key: {"enabled": False, "binding": None} for key in ("web", "mac")}}
    monkeypatch.setattr(cli, "_attest_app_boot_runtime", lambda p: p)
    # Real service construction validates AF_UNIX; no listener is started.
    import socket
    from contextlib import ExitStack
    sockets = ExitStack()
    def activated(name):
        value = sockets.enter_context(socket.socket(socket.AF_UNIX))
        value.bind(str(raw["control_socket_path" if name == "Operator" else "ceo_ingress_socket_path"]))
        value.listen()
        return value
    monkeypatch.setattr(cli, "activate_launchd_socket", activated)
    monkeypatch.setattr(executive_worker_broker, "WorkerBrokerClient", lambda *a, **kw: object())
    monkeypatch.setattr(workspace_source_join, "build_workspace_composer", lambda **kw: lambda stamp: {})
    try:
        service = cli._service_from_config(raw, workspace_acquisition_loader=lambda: authority, coo_source=owner.source)
    finally:
        sockets.close()
    binding = service._ceo_ingress_app_binding
    if not selected:
        assert binding.principal_dialogue_provider_factory is None
        return
    runtime = Runtime.at(tmp_path/"fixture-runtime")
    service.runtime = runtime
    custody_calls = []
    def bound(actual):
        assert actual is runtime
        custody_calls.append(actual)
        return actual
    service._namespace_custody = SimpleNamespace(bound_runtime=bound)
    receiver = binding.principal_dialogue_provider_factory(runtime)
    assert type(receiver) is PrincipalDialogueAppReceiver
    assert receiver.runtime is runtime and receiver.authority.workspace.runtime is runtime
    assert type(receiver.observation_client) is HostLocalDialogueObservationReader
    assert receiver.observation_client.service is service
    assert receiver.observation_client.runtime is runtime
    assert receiver.socket_path == cli._CANONICAL_AGENT_RELAY_SOCKET
    assert custody_calls == [runtime]
    assert binding.peer_uid == 458 and binding.armed is False
