from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


RELAY_UID = 452
APP_BOOT_PYTHON = Path(
    "/Library/Application Support/MastermindExecutive/capacity-runtimes/"
    "cf1-pyyaml-6.0.3-cp312-arm64/bin/python3.12"
)


def _module():
    return importlib.import_module("scripts.executive_os_phase1c")


def _raw(tmp_path: Path) -> dict[str, object]:
    euid = os.geteuid()
    return {
        "schema_version": "mastermind.executive_control_config/v1",
        "runtime_root": tmp_path / "runtime",
        "control_socket_path": tmp_path / "control.sock",
        "launchd_socket_name": "Operator",
        "ceo_ingress_socket_path": tmp_path / "ceo-ingress.sock",
        "ceo_ingress_launchd_socket_name": "CeoIngress",
        "ceo_ingress_peer_uid": RELAY_UID,
        "worker_broker_socket_path": tmp_path / "worker-broker.sock",
        "worker_provider_home": tmp_path / "worker-home",
        "worker_runs_root": tmp_path / "worker-runs",
        "receipts_root": tmp_path / "receipts",
        "proof_source_repository": tmp_path / "repo",
        "proof_workspace_root": tmp_path / "workspaces",
        "proof_base_sha": "a" * 40,
        "backup_root": tmp_path / "backups",
        "control_uid": euid,
        "worker_uid": euid + 1,
        "worker_gid": euid + 1,
        "worker_user": "_mastermind_worker_fixture",
        "shared_run_gid": euid + 2,
        "allowed_peer_uids": (euid,),
        "secret_canary_receipt_path": tmp_path / "canary.json",
        "control_environment_attestation_path": tmp_path / "attestation.json",
    }


def test_load_control_config_accepts_required_c1_state_listener_fields(tmp_path: Path):
    module = _module()
    raw = _raw(tmp_path)
    document = {
        key: (str(value) if isinstance(value, Path) else value)
        for key, value in raw.items()
    }
    document["allowed_peer_uids"] = list(document["allowed_peer_uids"])
    path = tmp_path / "control.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    path.chmod(0o600)

    loaded = module.load_control_config(path)

    assert loaded["ceo_ingress_socket_path"] == raw["ceo_ingress_socket_path"]
    assert loaded["ceo_ingress_launchd_socket_name"] == "CeoIngress"
    assert loaded["ceo_ingress_peer_uid"] == RELAY_UID
    assert "ceo_ingress_armed" not in loaded


def test_service_composes_second_launchd_listener_unarmed_and_state_only(monkeypatch, tmp_path: Path):
    module = _module()
    raw = _raw(tmp_path)
    activated: list[str] = []
    fake_sockets = {"Operator": object(), "CeoIngress": object()}
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        importlib.import_module("control_plane.executive_worker_broker"),
        "WorkerBrokerClient",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        module,
        "activate_launchd_socket",
        lambda name: activated.append(name) or fake_sockets[name],
    )

    class FakeService:
        def __init__(self, config, **kwargs):
            captured["config"] = config
            captured.update(kwargs)

    monkeypatch.setattr(module, "ExecutiveControlService", FakeService)

    service = module._service_from_config(raw)

    assert isinstance(service, FakeService)
    assert activated == ["Operator", "CeoIngress"]
    assert captured["activated_socket"] is fake_sockets["Operator"]
    assert captured["ceo_ingress_activated_socket"] is fake_sockets["CeoIngress"]
    assert captured["ceo_ingress_socket_path"] == raw["ceo_ingress_socket_path"]
    assert captured["ceo_ingress_peer_uid"] == RELAY_UID
    assert captured["ceo_ingress_armed"] is False
    provider = captured["ceo_ingress_grounding_provider"]
    with pytest.raises(RuntimeError, match="C1_GROUNDING_UNAVAILABLE"):
        provider.observe()


def _write_config(tmp_path, raw):
    path = tmp_path/'control-app.json'
    path.write_text(json.dumps({k: str(v) if isinstance(v, Path) else list(v) if isinstance(v, tuple) else v for k,v in raw.items()}))
    path.chmod(0o600)
    return path


def test_app_boot_python_uses_capacity_runtime_attestor(monkeypatch, tmp_path):
    module = _module()
    observed: list[Path] = []
    monkeypatch.setattr(module, "_sealed_root_executable", lambda value, _name: Path(value))
    monkeypatch.setattr(
        module, "_attest_app_boot_runtime",
        lambda path: observed.append(Path(path)) or Path(path),
    )
    raw = _raw(tmp_path)
    raw.update(
        ceo_ingress_app_peer_uid=os.geteuid() + 10,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=tmp_path / "macro",
        ceo_ingress_app_boot_python=APP_BOOT_PYTHON,
    )
    loaded = module.load_control_config(_write_config(tmp_path, raw))
    assert observed == [APP_BOOT_PYTHON]
    assert loaded["ceo_ingress_app_boot_python"] == APP_BOOT_PYTHON


def test_service_composes_hardened_app_reader(monkeypatch, tmp_path):
    module = _module()
    raw = _raw(tmp_path)
    raw.update(
        ceo_ingress_app_peer_uid=os.geteuid() + 10,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=tmp_path / "macro",
        ceo_ingress_app_boot_python=APP_BOOT_PYTHON,
    )
    captured_reader: dict[str, object] = {}
    captured_service: dict[str, object] = {}
    installed = importlib.import_module("integrations.executive_mcp.installed")
    class FakeReaders:
        def __init__(self, **kwargs): captured_reader.update(kwargs)
        def observe(self):
            return {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40,
                    "boot_packet_schema": "mastermind.ceo_boot_packet.v1"}
    class FakeService:
        def __init__(self, _config, **kwargs): captured_service.update(kwargs)
    monkeypatch.setattr(installed, "InstalledExecutiveReaders", FakeReaders)
    monkeypatch.setattr(module, "ExecutiveControlService", FakeService)
    monkeypatch.setattr(module, "activate_launchd_socket", lambda _name: object())
    monkeypatch.setattr(importlib.import_module("control_plane.executive_worker_broker"),
                        "WorkerBrokerClient", lambda *_args, **_kwargs: object())
    module._service_from_config(raw)
    assert captured_reader["repo_root"] == raw["proof_source_repository"]
    assert captured_reader["macro_root"] == raw["ceo_ingress_app_macro_root"]
    assert captured_reader["runtime_root"] == raw["runtime_root"]
    assert captured_reader["boot_python"] == APP_BOOT_PYTHON
    assert captured_reader["code_root"] == Path(module.__file__).resolve().parents[1]
    assert captured_reader["expected_source_sha"] == raw["proof_base_sha"]
    assert captured_service["ceo_ingress_app_binding"].armed is True


def test_app_config_is_explicit_and_keeps_c1_unarmed(tmp_path):
    module = _module()
    raw = _raw(tmp_path)
    raw.update(ceo_ingress_app_peer_uid=os.geteuid()+10,
               ceo_ingress_app_armed=True, ceo_ingress_app_macro_root=tmp_path/'macro')
    loaded = module.load_control_config(_write_config(tmp_path, raw))
    assert loaded['ceo_ingress_app_peer_uid'] != loaded['ceo_ingress_peer_uid']
    assert loaded['ceo_ingress_app_armed'] is True
    assert 'ceo_ingress_armed' not in loaded


@pytest.mark.parametrize('change', [
    {'ceo_ingress_app_peer_uid': RELAY_UID},
    {'ceo_ingress_app_peer_uid': os.geteuid()},
    {'ceo_ingress_app_peer_uid': True},
    {'ceo_ingress_app_armed': 1},
    {'ceo_ingress_app_macro_root': 'relative/path'},
])
def test_app_config_refuses_identity_or_capability_ambiguity(tmp_path, change):
    module = _module()
    raw = _raw(tmp_path)
    raw.update(ceo_ingress_app_peer_uid=os.geteuid()+10,
               ceo_ingress_app_armed=True, ceo_ingress_app_macro_root=tmp_path/'macro')
    raw.update(change)
    with pytest.raises(module.ServiceError):
        module.load_control_config(_write_config(tmp_path, raw))


def test_partial_app_config_is_refused(tmp_path):
    module = _module()
    raw = _raw(tmp_path)
    raw['ceo_ingress_app_peer_uid'] = os.geteuid()+10
    with pytest.raises(module.ServiceError):
        module.load_control_config(_write_config(tmp_path, raw))


def test_app_boot_python_is_optional_but_sealed_when_present(tmp_path):
    module = _module()
    raw = _raw(tmp_path)
    raw.update(
        ceo_ingress_app_peer_uid=os.geteuid()+10,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=tmp_path/'macro',
    )
    # Backward-compatible rollout: absence keeps the prior degraded read path.
    loaded = module.load_control_config(_write_config(tmp_path, raw))
    assert 'ceo_ingress_app_boot_python' not in loaded

    raw['ceo_ingress_app_boot_python'] = 'relative/python'
    with pytest.raises(module.ServiceError):
        module.load_control_config(_write_config(tmp_path, raw))

    mutable = tmp_path / 'python3.12'
    mutable.write_text('#!/bin/sh\nexit 0\n')
    mutable.chmod(0o755)
    raw['ceo_ingress_app_boot_python'] = str(mutable)
    with pytest.raises(module.ServiceError, match='root-owned'):
        module.load_control_config(_write_config(tmp_path, raw))


def test_app_boot_python_without_app_binding_is_refused(tmp_path):
    module = _module()
    raw = _raw(tmp_path)
    raw['ceo_ingress_app_boot_python'] = '/Library/Application Support/MastermindExecutive/capacity-runtimes/example/bin/python3.12'
    with pytest.raises(module.ServiceError, match='complete App binding'):
        module.load_control_config(_write_config(tmp_path, raw))


@pytest.mark.parametrize("armed", [None, False, True])
def test_terminal_return_factory_selects_v2_only_when_explicitly_armed(
    monkeypatch, tmp_path, armed,
):
    """Exercise the production composition without starting a service or sending."""
    from integrations.slack_agent_dialogue import executive_terminal_return_projector as projection
    from tests.test_slack_agent_dialogue_executive_terminal_return_projector import (
        _binding, _candidate,
    )

    module = _module()
    raw = _raw(tmp_path)
    if armed is not None:
        raw["terminal_return_armed"] = armed
        raw["terminal_return_socket_path"] = module._CANONICAL_AGENT_RELAY_SOCKET
    captured = {}
    monkeypatch.setattr(
        importlib.import_module("control_plane.executive_worker_broker"),
        "WorkerBrokerClient", lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(module, "activate_launchd_socket", lambda _name: object())

    class CapturedService:
        def __init__(self, config, **kwargs):
            captured["config"] = config
            captured.update(kwargs)

    monkeypatch.setattr(module, "ExecutiveControlService", CapturedService)
    module._service_from_config(raw)
    assert captured["config"].terminal_return_armed is (armed is True)
    assert captured["config"].ceo_submit_armed is False
    assert captured["config"].coo_autonomy_armed is False
    assert captured["ceo_ingress_armed"] is False
    if armed is not True:
        assert "terminal_return_projector_factory" not in captured
        return

    candidate = _candidate()
    provider_calls = []
    runtime_marker = object()

    def runtime_provider():
        provider_calls.append(True)
        return runtime_marker

    projector = captured["terminal_return_projector_factory"](
        runtime_provider, raw["terminal_return_socket_path"],
    )
    assert type(projector) is projection.ExecutiveTerminalReturnProjector
    assert type(projector._binding_resolver) is projection.RuntimeTerminalReturnBindingResolver
    assert projector._socket_path == module._CANONICAL_AGENT_RELAY_SOCKET
    assert provider_calls == []  # Construction is inert.

    def resolve_fixture(resolver, observed):
        assert observed is candidate
        assert resolver._runtime_provider() is runtime_marker
        return _binding(candidate)

    monkeypatch.setattr(projection.RuntimeTerminalReturnBindingResolver, "resolve", resolve_fixture)
    _context, _thread, message = projector._resolve(candidate)
    payload = json.loads(message["body"]["result"])
    assert payload["schema"] == "mastermind.executive_terminal_result_synopsis/v2"
    assert payload["root_job_id"] == candidate.root_job_id
    assert message["message_key"] == candidate.message_key
    assert provider_calls == [True]


INVALID_INSTALLED_PROFILES = (
    None, False, True, 0, 1, 3.14, [], {}, "", " ", "\t", "legacy ", " legacy",
    "Legacy", "LEGACY", "web_ceo_v1", "web_ceo_v2 ", "WEB_CEO_V2",
    "mastermind.executive_ceo_ingress_app_read.v1",
    "mastermind.executive_ceo_ingress_app_read.v3",
    "unknown",
)


def _app_raw(tmp_path: Path) -> dict[str, object]:
    raw = _raw(tmp_path)
    raw.update(
        ceo_ingress_app_peer_uid=os.geteuid() + 10,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=tmp_path / "macro",
        ceo_ingress_app_boot_python=APP_BOOT_PYTHON,
    )
    return raw


def _capture_service(module, monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        importlib.import_module("control_plane.executive_worker_broker"),
        "WorkerBrokerClient", lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(module, "activate_launchd_socket", lambda _name: object())

    class FakeService:
        def __init__(self, _config, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(module, "ExecutiveControlService", FakeService)
    return captured


def test_omitted_and_explicit_legacy_profile_keep_installed_reader(monkeypatch, tmp_path):
    from control_plane.executive_service import CEO_APP_READ_SCHEMA
    from integrations.executive_mcp.adapter import ExecutiveMcpGateway
    from integrations.executive_mcp.installed import InstalledExecutiveReaders

    module = _module()
    binds: list[object] = []
    original = ExecutiveMcpGateway.bind_fabric_source

    def tracking(self, **kwargs):
        binds.append(self)
        return original(self, **kwargs)

    monkeypatch.setattr(ExecutiveMcpGateway, "bind_fabric_source", tracking)
    for profile in (None, "legacy"):
        raw = _app_raw(tmp_path)
        if profile is not None:
            raw["executive_mcp_profile"] = profile
        captured = _capture_service(module, monkeypatch)
        binds.clear()
        module._service_from_config(raw)
        binding = captured["ceo_ingress_app_binding"]
        assert type(binding.read_provider) is InstalledExecutiveReaders
        assert binding.read_schema == CEO_APP_READ_SCHEMA
        assert binding.read_provider is binding.grounding_provider
        assert binds == []
        assert captured["ceo_ingress_armed"] is False


def test_exact_v2_profile_selects_accepted_reader_and_inert_bind(monkeypatch, tmp_path):
    from control_plane.executive_service import CEO_WEB_CEO_V2_READ_SCHEMA
    from control_plane.fabric_job_view import ARM_KEYS
    from integrations.executive_mcp.web_ceo import WebCeoV2InstalledExecutiveReaders

    module = _module()
    raw = _app_raw(tmp_path)
    raw["executive_mcp_profile"] = "web_ceo_v2"
    captured = _capture_service(module, monkeypatch)
    module._service_from_config(raw)
    binding = captured["ceo_ingress_app_binding"]
    readers = binding.read_provider
    assert type(readers) is WebCeoV2InstalledExecutiveReaders
    assert binding.read_schema == CEO_WEB_CEO_V2_READ_SCHEMA
    assert readers._fabric_source_binding is not None
    getter, armed, identity = readers._fabric_source_binding
    assert callable(getter)
    assert identity == {"root": None, "db_present": True, "identity": None}
    assert armed["source"] == "control.json"
    assert armed["ceo_ingress_app_armed"] is True
    for key in ARM_KEYS:
        if key != "ceo_ingress_app_armed":
            assert armed[key] is None
    with pytest.raises((AttributeError, TypeError)):
        getter()
    assert captured["ceo_ingress_armed"] is False


def test_v2_profile_does_not_require_workspace(monkeypatch, tmp_path):
    from integrations.executive_mcp.web_ceo import WebCeoV2InstalledExecutiveReaders

    module = _module()
    raw = _app_raw(tmp_path)
    raw["executive_mcp_profile"] = "web_ceo_v2"
    assert "workspace_acquisition" not in raw
    captured = _capture_service(module, monkeypatch)
    module._service_from_config(raw)
    assert type(captured["ceo_ingress_app_binding"].read_provider) is WebCeoV2InstalledExecutiveReaders
    assert captured.get("workspace_control_room") is None


@pytest.mark.parametrize("value", INVALID_INSTALLED_PROFILES)
def test_control_config_refuses_invalid_installed_profile(tmp_path, value):
    module = _module()
    raw = _app_raw(tmp_path)
    raw["executive_mcp_profile"] = value
    with pytest.raises(module.ServiceError, match="installed Executive MCP profile is invalid"):
        module.load_control_config(_write_config(tmp_path, raw))


def test_present_profile_without_app_group_is_refused_before_source(tmp_path, monkeypatch):
    module = _module()
    raw = _raw(tmp_path)
    raw["executive_mcp_profile"] = "legacy"
    with pytest.raises(module.ServiceError, match="App binding requires all App"):
        module.load_control_config(_write_config(tmp_path, raw))
    captured = _capture_service(module, monkeypatch)
    with pytest.raises(module.ServiceError, match="App binding requires all App"):
        module._service_from_config(raw)
    assert captured == {}


def test_omitted_profile_does_not_manufacture_app_binding(tmp_path):
    module = _module()
    loaded = module.load_control_config(_write_config(tmp_path, _raw(tmp_path)))
    assert "executive_mcp_profile" not in loaded
    assert "ceo_ingress_app_peer_uid" not in loaded
