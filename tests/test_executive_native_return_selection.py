"""Host-owned closed Operator selection; no Runtime or provider effects."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.executive_service import ExecutiveControlService, ServiceConfig, ServiceError
from control_plane.model_router import ModelRouter
from integrations.session_bridge.schemas import BridgeError, validate_tool_arguments

NATIVE_PROFILE = "operator.appserver.interactive.native-return.v1"
DOCS_PROFILE = "operator.appserver.readonly.docs-mcp.native-helper.v1"
NATIVE_ALIAS = "coo.operator.native-return.fixture"


def _host(tmp_path, monkeypatch, *, native=True, enabled=True, mutate=None):
    routes = json.loads(Path("config/executive_worker_routes.json").read_text())
    capabilities = json.loads(Path("config/executive_agent_capabilities.json").read_text())
    if native:
        routes["model_aliases"][NATIVE_ALIAS] = {
            **routes["model_aliases"]["coo.operator.readonly"],
            "execution_profile_id": NATIVE_PROFILE,
        }
        capabilities["profiles"][NATIVE_PROFILE]["enabled"] = enabled
    if mutate is not None:
        mutate(routes, capabilities)
    route_path, cap_path = tmp_path / "routes.json", tmp_path / "capabilities.json"
    route_path.write_text(json.dumps(routes))
    cap_path.write_text(json.dumps(capabilities))
    load = ModelRouter.load
    monkeypatch.setattr(ModelRouter, "load", classmethod(
        lambda cls: load(route_path, capability_policy_path=cap_path)))
    config = ServiceConfig(
        runtime_root=tmp_path / "runtime", socket_path=tmp_path / "control.sock",
        proof_source_repository=tmp_path / "source", proof_workspace_root=tmp_path / "workspaces",
        proof_base_sha="a" * 40,
        coo_operator_model_alias=NATIVE_ALIAS if native else "coo.operator.readonly",
    )
    return ExecutiveControlService(config), cap_path


def test_host_selects_enabled_exact_native_return_profile(tmp_path, monkeypatch):
    service, _ = _host(tmp_path, monkeypatch)
    binding = service._require_current_coo_binding()
    assert binding["operator_execution_profile_id"] == NATIVE_PROFILE
    assert binding["execution_profile_id"] == "sealed.worker.write.no-extensions.v1"
    assert binding["operator_provider"] == "codex"
    assert binding["operator_harness_armed"] is False
    assert len(binding["operator_execution_profile_digest"]) == 64
    assert len(binding["operator_capability_policy_digest"]) == 64
    assert service.runtime is None
    assert not service.config.runtime_root.exists()


def test_default_docs_helper_selection_is_unchanged(tmp_path, monkeypatch):
    service, _ = _host(tmp_path, monkeypatch, native=False)
    assert service._require_current_coo_binding()["operator_execution_profile_id"] == DOCS_PROFILE
    assert ModelRouter.load().capability_registry.profiles[NATIVE_PROFILE].enabled is True
    assert service.runtime is None


def test_disabled_native_return_cannot_be_selected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="disabled"):
        _host(tmp_path, monkeypatch, enabled=False)
    assert not (tmp_path / "runtime").exists()


def _field(name, value):
    return lambda routes, caps: caps["profiles"][NATIVE_PROFILE].update({name: value})


def _wrong_profile(routes, caps):
    caps["profiles"]["operator.unreviewed.fixture.v1"] = dict(caps["profiles"][NATIVE_PROFILE])
    routes["model_aliases"][NATIVE_ALIAS]["execution_profile_id"] = "operator.unreviewed.fixture.v1"


def _native_helper(routes, caps):
    native, docs = caps["profiles"][NATIVE_PROFILE], caps["profiles"][DOCS_PROFILE]
    native.update(native_helper_policy=docs["native_helper_policy"], native_helper=docs["native_helper"])


def _wrong_grant(routes, caps):
    caps["mcp_servers"]["native-return-mcp-v1"]["tool_schema_digest"] = "f" * 64


def _write_profile(routes, caps):
    caps["profiles"][NATIVE_PROFILE].update(write_capable=True, sandbox_policy="workspace-write")


def _ineligible_alias(routes, caps):
    routes["model_aliases"][NATIVE_ALIAS]["worker_eligible"] = False


@pytest.mark.parametrize("mutate", [
    _field("auth_realm", "personal-interactive"),
    _field("mcp_servers", ["openai-developer-docs-v1"]),
    _field("mcp_servers", ["native-return-mcp-v1", "openai-developer-docs-v1"]),
    _field("mcp_servers", []),
    _field("plugins", ["unreviewed-plugin"]),
    _field("skills", ["unreviewed-skill"]),
    _field("approval_policy", "on-request"),
    _field("write_capable", True),
    _field("network_policy", "loopback-browser-only"),
    _field("execution_surface", "codex-cli-sealed"),
    _native_helper, _wrong_profile, _wrong_grant, _write_profile, _ineligible_alias,
], ids=["realm", "wrong-mcp", "extra-mcp", "missing-mcp", "plugin", "skill",
        "approval", "write", "network", "surface", "helper", "profile", "grant-digest",
        "valid-write-profile", "ineligible-alias"])
def test_unreviewed_native_combinations_are_refused(tmp_path, monkeypatch, mutate):
    with pytest.raises(ValueError):
        _host(tmp_path, monkeypatch, mutate=mutate)
    assert not (tmp_path / "runtime").exists()


def test_host_binding_detects_enabled_policy_drift(tmp_path, monkeypatch):
    service, path = _host(tmp_path, monkeypatch)
    raw = json.loads(path.read_text())
    raw["profiles"][NATIVE_PROFILE]["enabled"] = False
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="disabled"):
        service._require_current_coo_binding()
    assert service.runtime is None


def test_host_binding_detects_valid_policy_rotation(tmp_path, monkeypatch):
    service, path = _host(tmp_path, monkeypatch)
    raw = json.loads(path.read_text())
    raw["policy_version"] = "fixture.next-reviewed-policy"
    path.write_text(json.dumps(raw))
    with pytest.raises(ServiceError, match="drifted"):
        service._require_current_coo_binding()


@pytest.mark.parametrize("field", ["coo_operator_model_alias", "execution_profile_id", "provider", "account", "host"])
def test_public_summon_cannot_select_native_identity(field):
    packet = {"operation_key": "native-selection-fixture", "objective": "Inspect source only.",
              "department": "executive-infrastructure", "priority": 0,
              "execution_profile": "research_only", "workstream": "WS:Fixture",
              field: NATIVE_ALIAS}
    with pytest.raises(BridgeError):
        validate_tool_arguments("session_summon", packet)
