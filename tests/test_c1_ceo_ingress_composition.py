from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


RELAY_UID = 452


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
