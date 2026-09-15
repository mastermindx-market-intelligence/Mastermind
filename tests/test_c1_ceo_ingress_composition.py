from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


RELAY_UID = 452
APP_READ_PYTHON = Path("/Library/Application Support/MastermindExecutive/network-runtimes/" + "a" * 64 + "/bin/python")


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


def test_app_config_is_explicit_and_keeps_c1_unarmed(tmp_path):
    module = _module()
    raw = _raw(tmp_path)
    raw.update(ceo_ingress_app_peer_uid=os.geteuid()+10,
               ceo_ingress_app_armed=True, ceo_ingress_app_macro_root=tmp_path/'macro',
               ceo_ingress_app_read_python=APP_READ_PYTHON)
    loaded = module.load_control_config(_write_config(tmp_path, raw))
    assert loaded['ceo_ingress_app_peer_uid'] != loaded['ceo_ingress_peer_uid']
    assert loaded['ceo_ingress_app_armed'] is True
    assert loaded['ceo_ingress_app_read_python'] == APP_READ_PYTHON
    assert 'ceo_ingress_armed' not in loaded


@pytest.mark.parametrize('change', [
    {'ceo_ingress_app_peer_uid': RELAY_UID},
    {'ceo_ingress_app_peer_uid': os.geteuid()},
    {'ceo_ingress_app_peer_uid': True},
    {'ceo_ingress_app_armed': 1},
    {'ceo_ingress_app_macro_root': 'relative/path'},
    {'ceo_ingress_app_read_python': '/tmp/network-python'},
    {'ceo_ingress_app_read_python': 'relative/network-python'},
])
def test_app_config_refuses_identity_or_capability_ambiguity(tmp_path, change):
    module = _module()
    raw = _raw(tmp_path)
    raw.update(ceo_ingress_app_peer_uid=os.geteuid()+10,
               ceo_ingress_app_armed=True, ceo_ingress_app_macro_root=tmp_path/'macro',
               ceo_ingress_app_read_python=APP_READ_PYTHON)
    raw.update(change)
    with pytest.raises(module.ServiceError):
        module.load_control_config(_write_config(tmp_path, raw))


def test_partial_app_config_is_refused(tmp_path):
    module = _module()
    raw = _raw(tmp_path)
    raw['ceo_ingress_app_peer_uid'] = os.geteuid()+10
    with pytest.raises(module.ServiceError):
        module.load_control_config(_write_config(tmp_path, raw))


def test_service_composes_app_reader_with_dependency_python(monkeypatch, tmp_path):
    module = _module()
    raw = _raw(tmp_path)
    raw.update(
        ceo_ingress_app_peer_uid=os.geteuid() + 10,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=tmp_path / "macro",
        ceo_ingress_app_read_python=APP_READ_PYTHON,
    )
    captured_reader: dict[str, object] = {}
    captured_service: dict[str, object] = {}
    installed = importlib.import_module("integrations.executive_mcp.installed")

    class FakeReaders:
        def __init__(self, **kwargs):
            captured_reader.update(kwargs)

        def observe(self):
            return {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40,
                    "boot_packet_schema": "mastermind.ceo_boot_packet.v1"}

        async def call(self, _name, _arguments):
            return {"ok": True}

    class FakeService:
        def __init__(self, config, **kwargs):
            captured_service.update(kwargs)

    monkeypatch.setattr(installed, "InstalledExecutiveReaders", FakeReaders)
    monkeypatch.setattr(module, "ExecutiveControlService", FakeService)
    monkeypatch.setattr(module, "activate_launchd_socket", lambda _name: object())
    monkeypatch.setattr(
        importlib.import_module("control_plane.executive_worker_broker"),
        "WorkerBrokerClient", lambda *_args, **_kwargs: object(),
    )

    module._service_from_config(raw)

    assert captured_reader["repo_root"] == raw["proof_source_repository"]
    assert captured_reader["macro_root"] == raw["ceo_ingress_app_macro_root"]
    assert captured_reader["runtime_root"] == raw["runtime_root"]
    assert captured_reader["packet_python"] == raw["ceo_ingress_app_read_python"]
    binding = captured_service["ceo_ingress_app_binding"]
    assert binding.armed is True
