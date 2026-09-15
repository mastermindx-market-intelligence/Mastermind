from __future__ import annotations

import ast
import importlib
import json
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
PHASE1C = ROOT / "scripts" / "executive_os_phase1c.py"
TEMPLATE = ROOT / "ops" / "executive_os" / "control.json.template"


def _raw(tmp_path: Path, **extra: object) -> dict[str, object]:
    uid = os.geteuid()
    raw: dict[str, object] = {
        "schema_version": "mastermind.executive_control_config/v1",
        "runtime_root": str(tmp_path / "runtime"),
        "control_socket_path": str(tmp_path / "control.sock"),
        "launchd_socket_name": "Operator",
        "worker_broker_socket_path": str(tmp_path / "worker.sock"),
        "worker_provider_home": str(tmp_path / "provider-home"),
        "worker_runs_root": str(tmp_path / "runs"),
        "receipts_root": str(tmp_path / "receipts"),
        "proof_source_repository": str(tmp_path / "repo"),
        "proof_workspace_root": str(tmp_path / "workspace"),
        "proof_base_sha": "a" * 40,
        "backup_root": str(tmp_path / "backups"),
        "control_uid": uid,
        "worker_uid": uid + 1,
        "worker_gid": uid + 1,
        "worker_user": "_mastermind_worker",
        "shared_run_gid": uid + 2,
        "allowed_peer_uids": [uid],
        "secret_canary_receipt_path": str(tmp_path / "canary.json"),
        "control_environment_attestation_path": str(tmp_path / "attestation.json"),
    }
    raw.update(extra)
    return raw


def _write(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / "control.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    path.chmod(0o600)
    return path


def _module():
    return importlib.import_module("scripts.executive_os.phase1c") if False else importlib.import_module("scripts.executive_os_phase1c")


def test_d1_closed_value_is_loaded_passed_through_and_unarmed(tmp_path, monkeypatch):
    module = _module()
    raw = _raw(tmp_path, ceo_submit_armed=False)
    loaded = module.load_control_config(_write(tmp_path, raw))
    captured: dict[str, object] = {}

    broker = importlib.import_module("control_plane.executive_worker_broker")
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *a, **k: object())
    monkeypatch.setattr(module, "activate_launchd_socket", lambda _name: object())

    class FakeService:
        def __init__(self, config, **kwargs):
            captured["config"] = config
            captured.update(kwargs)

    monkeypatch.setattr(module, "ExecutiveControlService", FakeService)
    module._service_from_config(loaded)
    assert captured["config"].ceo_submit_armed is False
    service_source = (ROOT / "control_plane" / "executive_service.py").read_text(encoding="utf-8")
    assert "and not self.config.ceo_submit_armed" in service_source


def test_d2_peer_admission_precedes_request_body_read():
    source = (ROOT / "control_plane" / "executive_service.py").read_text(encoding="utf-8")
    handler = source[source.index("async def _handle_ceo_ingress_connection"):]
    assert handler.index("peer_denied") < handler.index("readuntil")


def test_d3_app_458_is_independent_of_c1_and_submit_arms():
    source = PHASE1C.read_text(encoding="utf-8")
    assert '"ceo_ingress_armed": False' in source
    assert 'armed=raw["ceo_ingress_app_armed"]' in source
    assert "CeoIngressAppBinding" in source
    assert "ceo_submit_armed=raw.get(\"ceo_submit_armed\", False)," in source


@pytest.mark.parametrize("value", ["true", 1, 0, None])
def test_d4_submit_arm_is_strict_boolean(tmp_path, value):
    module = _module()
    with pytest.raises(module.ServiceError, match="ceo_submit_armed must be boolean"):
        module.load_control_config(_write(tmp_path, _raw(tmp_path, ceo_submit_armed=value)))


def test_d4_unknown_fields_remain_closed(tmp_path):
    module = _module()
    with pytest.raises(module.ServiceError, match="unknown=.*not_admitted"):
        module.load_control_config(_write(tmp_path, _raw(tmp_path, not_admitted=False)))


def test_d5_existing_sink_retains_fingerprint_reconciliation():
    source = (ROOT / "control_plane" / "ceo_intent.py").read_text(encoding="utf-8")
    assert "intent_fingerprint" in source
    assert "CeoIntentConflict" in source
    assert "different envelope" in source
    assert "if fingerprint is not None and recorded != fingerprint" in source


def test_d6_no_new_transport_and_all_arm_defaults_are_false():
    source = PHASE1C.read_text(encoding="utf-8")
    assert 'ceo_submit_armed: bool = False' in (ROOT / "control_plane" / "executive_service.py").read_text(encoding="utf-8")
    assert '"ceo_submit_armed": false' in TEMPLATE.read_text(encoding="utf-8")
    assert source.count("class CeoIngressClient") == 0
    tree = ast.parse(source)
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) and any(alias.name == "socket" for alias in node.names) for node in tree.body)


def test_d7_diff_and_module_have_no_dispatch_or_provider_import():
    tree = ast.parse(PHASE1C.read_text(encoding="utf-8"))
    imports = {alias.name for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    assert "subprocess" not in imports
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"dispatch", "spawn", "claim_job"} for node in ast.walk(tree))


@pytest.mark.parametrize("app_uid", [452, 501])
def test_d8_c1_and_worker_uids_are_not_app_peer(tmp_path, app_uid):
    module = _module()
    raw = _raw(
        tmp_path,
        ceo_ingress_socket_path=str(tmp_path / "ingress.sock"),
        ceo_ingress_launchd_socket_name="CeoIngress",
        ceo_ingress_peer_uid=452,
        ceo_ingress_app_peer_uid=app_uid,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=str(tmp_path / "macro"),
    )
    with pytest.raises(module.ServiceError, match="App peer must be distinct"):
        module.load_control_config(_write(tmp_path, raw))


def test_d8_template_topology_and_protected_defaults():
    value = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert value["allowed_peer_uids"] == [450, 501]
    assert value["ceo_ingress_peer_uid"] == 452
    assert value["ceo_ingress_app_peer_uid"] == 458
    assert value["ceo_ingress_app_armed"] is False
