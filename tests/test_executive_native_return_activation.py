"""Paired catalogue eligibility remains separate from live Operator admission."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.executive_service import ExecutiveControlService, ServiceConfig
from control_plane.model_router import ModelRouter, RoutingPolicyError, WorkRequest
from control_plane.operator_harness_contract import NativeHelperPolicy
from integrations.session_bridge.schemas import BridgeError, validate_tool_arguments

NATIVE_ALIAS = "coo.operator.native-return"
NATIVE_PROFILE = "operator.appserver.interactive.native-return.v1"
DOCS_PROFILE = "operator.appserver.readonly.docs-mcp.native-helper.v1"
POLICY_VERSION = "2026-10-14.attended-qualification"


def _config(tmp_path, **overrides):
    return ServiceConfig(runtime_root=tmp_path / "runtime", socket_path=tmp_path / "control.sock",
        proof_source_repository=tmp_path / "source", proof_workspace_root=tmp_path / "workspaces",
        proof_base_sha="a" * 40, **overrides)


def _policies():
    return (json.loads(Path("config/executive_worker_routes.json").read_text()),
            json.loads(Path("config/executive_agent_capabilities.json").read_text()))


def _load_pair(tmp_path, routes, capabilities):
    route_path, cap_path = tmp_path / "routes.json", tmp_path / "capabilities.json"
    route_path.write_text(json.dumps(routes)); cap_path.write_text(json.dumps(capabilities))
    return ModelRouter.load(route_path, capability_policy_path=cap_path)


def test_paired_catalogues_load_exact_closed_alias_without_production_arm():
    routes, caps = _policies()
    assert routes["production_armed"] is False
    assert caps["production_armed"] is False
    router = ModelRouter.load()
    alias = router.resolve_model_alias(NATIVE_ALIAS)
    profile = router.capability_registry.resolve(alias.execution_profile_id)
    assert alias.execution_profile_id == NATIVE_PROFILE
    assert alias.provider_alias == "codex" and alias.adapter_id == "codex-cli"
    assert (alias.model, alias.effort, alias.cost_class) == ("gpt-5.6-sol", "xhigh", "small")
    assert alias.capabilities == ("planning", "judgment", "escalation")
    assert profile.mcp_servers == ("native-return-mcp-v1",)
    assert profile.native_helper_policy is NativeHelperPolicy.DISABLED
    assert profile.native_helper is None
    assert profile.skills == profile.skill_grants == profile.resource_grants == profile.plugins == ()
    assert profile.auth_realm == "dedicated-worker-account"
    assert profile.sandbox_policy == "read-only" and not profile.write_capable
    assert profile.network_policy == "disabled" and profile.approval_policy == "never"
    assert router.policy_version == router.capability_registry.policy_version == POLICY_VERSION
    assert alias.capability_policy_digest == router.capability_registry.policy_digest
    assert alias.execution_profile_digest == profile.profile_digest


def test_host_must_explicitly_select_native_alias_and_remains_unarmed(tmp_path):
    default = ExecutiveControlService(_config(tmp_path / "default"))
    assert default.config.coo_operator_model_alias == "coo.operator.readonly"
    assert default._require_current_coo_binding()["operator_execution_profile_id"] == DOCS_PROFILE
    native = ExecutiveControlService(_config(tmp_path / "native", coo_operator_model_alias=NATIVE_ALIAS))
    binding = native._require_current_coo_binding()
    assert binding["operator_execution_profile_id"] == NATIVE_PROFILE
    assert binding["operator_harness_armed"] is False
    assert native.config.coo_autonomy_armed is False
    assert native.config.ceo_submit_armed is False
    assert native.runtime is default.runtime is None
    assert not native.config.runtime_root.exists()
    assert not default.config.runtime_root.exists()


@pytest.mark.parametrize("task,aliases", [
    ("implementation", ("fast.engineering", "standard.engineering")),
    ("mechanical", ("fast.engineering", "standard.engineering")),
    ("tests", ("fast.engineering", "standard.engineering")),
    ("research", ("fast.research", "standard.research")),
    ("review", ("standard.review",)),
])
def test_native_alias_is_absent_from_all_default_suitability_tiers(task, aliases):
    router = ModelRouter.load()
    assert router.route(WorkRequest(task)).preferred_model_aliases == aliases
    for risk in ("routine", "elevated"):
        decision = router.route(WorkRequest(task, risk=risk))
        assert all(NATIVE_ALIAS not in tier.model_aliases for tier in decision.suitability_tiers)
    assert router.route(WorkRequest("planning")).preferred_model_aliases == ("frontier.orchestrator",)


def test_native_alias_with_disabled_profile_refuses_real_router_load(tmp_path):
    routes, caps = _policies()
    caps["profiles"][NATIVE_PROFILE]["enabled"] = False
    with pytest.raises(RoutingPolicyError, match="disabled"):
        _load_pair(tmp_path, routes, caps)


def test_enabled_profile_without_alias_does_not_create_a_selection(tmp_path, monkeypatch):
    routes, caps = _policies()
    assert caps["profiles"][NATIVE_PROFILE]["enabled"] is True
    routes["model_aliases"].pop(NATIVE_ALIAS)
    router = _load_pair(tmp_path, routes, caps)
    monkeypatch.setattr(ModelRouter, "load", classmethod(lambda cls: router))
    with pytest.raises(ValueError, match="configured COO execution alias is invalid"):
        ExecutiveControlService(_config(tmp_path, coo_operator_model_alias=NATIVE_ALIAS))
    assert not (tmp_path / "runtime").exists()


def test_paired_activation_rotates_digests_without_broadening_docs_grant(tmp_path):
    routes, caps = _policies()
    active = _load_pair(tmp_path, routes, caps)
    active_alias = active.resolve_model_alias(NATIVE_ALIAS)
    routes["model_aliases"].pop(NATIVE_ALIAS)
    caps["profiles"][NATIVE_PROFILE]["enabled"] = False
    prior = _load_pair(tmp_path, routes, caps)
    assert active.capability_registry.policy_digest != prior.capability_registry.policy_digest
    assert active_alias.execution_profile_digest != prior.capability_registry.profiles[NATIVE_PROFILE].profile_digest
    old_docs = prior.resolve_model_alias("coo.operator.readonly")
    new_docs = active.resolve_model_alias("coo.operator.readonly")
    assert new_docs.execution_profile_id == DOCS_PROFILE
    assert new_docs.execution_profile_digest == old_docs.execution_profile_digest
    assert new_docs.capability_policy_digest != old_docs.capability_policy_digest
    assert active.capability_registry.resolve(DOCS_PROFILE).mcp_servers == ("openai-developer-docs-v1",)


@pytest.mark.parametrize("field", ["coo_operator_model_alias", "model_alias", "execution_profile_id", "account", "host", "provider"])
def test_public_summon_cannot_activate_or_choose_native_alias(field):
    packet = {"operation_key":"native-activation-fixture", "objective":"Inspect source.",
        "department":"executive-infrastructure", "priority":0,
        "execution_profile":"research_only", "workstream":"WS:Fixture", field:NATIVE_ALIAS}
    with pytest.raises(BridgeError):
        validate_tool_arguments("session_summon", packet)
