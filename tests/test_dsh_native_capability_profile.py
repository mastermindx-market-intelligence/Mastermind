"""Exact native requirements compile without enabling any installed owner."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError, ExecutionCapabilityRegistry,
    DSH_OPERATOR_EXECUTION_SURFACE, DSH_NATIVE_CONVERSATION_PROFILE_ID,
    adapter_supports_execution_surface, is_sealed_worker_execution_surface,
)
from control_plane.native_conversation_result import DSH_NATIVE_RESULT_CONTRACT

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT/"config/executive_dsh_native_conversation_capabilities.json"
DEFAULT = ROOT/"config/executive_agent_capabilities.json"


def raw():
    return json.loads(CANDIDATE.read_bytes())


def load_mutation(tmp_path, mutate):
    value = raw()
    mutate(value)
    path = tmp_path/"candidate.json"
    path.write_text(json.dumps(value))
    return ExecutionCapabilityRegistry.load(path)


def test_explicit_candidate_is_disabled_and_declares_original_plugin_only():
    before = hashlib.sha256(DEFAULT.read_bytes()).hexdigest()
    incumbent = ExecutionCapabilityRegistry.load()
    registry = ExecutionCapabilityRegistry.load(CANDIDATE)
    profile = registry.profiles[DSH_NATIVE_CONVERSATION_PROFILE_ID]
    assert profile.enabled is False
    assert incumbent.resolve(DSH_NATIVE_CONVERSATION_PROFILE_ID).enabled is True
    with pytest.raises(CapabilityPolicyError):
        registry.resolve(DSH_NATIVE_CONVERSATION_PROFILE_ID)
    projection = profile.dsh_native_config_projection()
    assert projection["result_contract"] == DSH_NATIVE_RESULT_CONTRACT
    assert projection["plugins"] == ["mastermind-company"]
    assert not any(key in projection for key in ("attestation", "account", "authority", "enabled"))
    manifest = profile.capability_manifest(harness_binary_digest="a"*64)
    assert [(item.kind, item.name, item.harness_binary_digest) for item in manifest.required] == [
        ("tool", "read", "a"*64), ("tool", "glob", "a"*64),
        ("tool", "grep", "a"*64), ("plugin", "mastermind-company", "a"*64)]
    assert manifest.allowed_ambient == ()
    assert len(profile.expected_config_digest) == 64
    assert not adapter_supports_execution_surface("acp", DSH_OPERATOR_EXECUTION_SURFACE)
    assert adapter_supports_execution_surface("dsh-native-acp", DSH_OPERATOR_EXECUTION_SURFACE)
    assert not adapter_supports_execution_surface("dsh-native-acp", "acp-agent")
    assert not is_sealed_worker_execution_surface(DSH_OPERATOR_EXECUTION_SURFACE)
    assert hashlib.sha256(DEFAULT.read_bytes()).hexdigest() == before
    assert ExecutionCapabilityRegistry.load().policy_digest == incumbent.policy_digest


@pytest.mark.parametrize("field,value", [
    ("enabled", "true"), ("execution_surface", "acp-agent"),
    ("auth_realm", "dedicated-worker-no-auth"), ("sandbox_policy", "workspace-write"),
    ("network_policy", "loopback-browser-only"), ("approval_policy", "always"),
    ("write_capable", True), ("native_helper_policy", "PARENT_READ_ONLY_CEILING"),
    ("skills", ["foreign-skill"]), ("mcp_servers", ["native-return-mcp-v1"]),
    ("resources", ["foreign-resource"]), ("plugins", []),
    ("plugins", ["mastermind-company", "other-plugin"]),
    ("plugins", ["other-plugin"]), ("forbidden", ["other-plugin"]),
])
@pytest.mark.parametrize("enabled", [False, True])
def test_candidate_flag_cannot_broaden_installed_authority(tmp_path, field, value, enabled):
    def mutate(document):
        document["profiles"][DSH_NATIVE_CONVERSATION_PROFILE_ID]["enabled"] = enabled
        document["profiles"][DSH_NATIVE_CONVERSATION_PROFILE_ID][field] = value
    with pytest.raises(CapabilityPolicyError):
        load_mutation(tmp_path, mutate)


def test_native_surface_cannot_be_used_by_an_alias_profile(tmp_path):
    def mutate(document):
        document["profiles"]["other-native-profile"] = document["profiles"].pop(DSH_NATIVE_CONVERSATION_PROFILE_ID)
    with pytest.raises(CapabilityPolicyError):
        load_mutation(tmp_path, mutate)


def test_candidate_does_not_create_a_plugin_registry(tmp_path):
    def mutate(document):
        document["plugins"] = {"mastermind-company": {"enabled": True}}
    with pytest.raises(CapabilityPolicyError):
        load_mutation(tmp_path, mutate)


@pytest.mark.parametrize("method", ("app_server_config_projection", "app_server_config_overrides",
                                    "acp_config_projection", "claude_sdk_config_projection"))
def test_native_candidate_cannot_borrow_another_harness_projection(method):
    candidate = ExecutionCapabilityRegistry.load(CANDIDATE).profiles[DSH_NATIVE_CONVERSATION_PROFILE_ID]
    with pytest.raises(CapabilityPolicyError):
        getattr(candidate, method)()


@pytest.mark.parametrize("change", (
    {"enabled": 1}, {"plugins": ()}, {"execution_surface": "codex-app-server"},
    {"profile_id": "other-native-profile"}, {"write_capable": True},
))
def test_replaced_dataclass_cannot_broaden_candidate_projection(change):
    candidate = ExecutionCapabilityRegistry.load(CANDIDATE).profiles[DSH_NATIVE_CONVERSATION_PROFILE_ID]
    changed = replace(candidate, **change)
    with pytest.raises(CapabilityPolicyError):
        changed.dsh_native_config_projection()
    with pytest.raises(CapabilityPolicyError):
        changed.capability_manifest(harness_binary_digest="a"*64)
    with pytest.raises(CapabilityPolicyError):
        _ = changed.expected_config_digest


def test_enabled_exact_tuple_compiles_through_original_registry_without_installation(tmp_path):
    before = DEFAULT.read_bytes(), CANDIDATE.read_bytes()
    disabled = ExecutionCapabilityRegistry.load(CANDIDATE)
    def enable(document):
        document["profiles"][DSH_NATIVE_CONVERSATION_PROFILE_ID]["enabled"] = True
    registry = load_mutation(tmp_path, enable)
    profile = registry.resolve(DSH_NATIVE_CONVERSATION_PROFILE_ID)
    assert profile.enabled is True
    original = disabled.profiles[DSH_NATIVE_CONVERSATION_PROFILE_ID]
    assert profile.profile_digest != original.profile_digest
    assert registry.policy_digest != disabled.policy_digest
    assert profile.expected_config_digest == original.expected_config_digest
    assert profile.capability_manifest(harness_binary_digest="a"*64) == original.capability_manifest(harness_binary_digest="a"*64)
    assert profile.dsh_native_config_projection()["plugins"] == ["mastermind-company"]
    assert not is_sealed_worker_execution_surface(DSH_OPERATOR_EXECUTION_SURFACE)
    assert (DEFAULT.read_bytes(), CANDIDATE.read_bytes()) == before
    assert ExecutionCapabilityRegistry.load().resolve(DSH_NATIVE_CONVERSATION_PROFILE_ID) == profile


def test_default_native_route_resolves_exact_profile_without_changing_task_routes():
    from control_plane.model_router import ModelRouter
    registry = ExecutionCapabilityRegistry.load()
    router = ModelRouter.load()
    profile = registry.resolve(DSH_NATIVE_CONVERSATION_PROFILE_ID)
    disabled = ExecutionCapabilityRegistry.load(CANDIDATE).profiles[DSH_NATIVE_CONVERSATION_PROFILE_ID]
    assert profile.enabled and profile.profile_digest != disabled.profile_digest
    assert profile.dsh_native_config_projection() == disabled.dsh_native_config_projection()
    assert profile.capability_manifest(harness_binary_digest="a"*64) == disabled.capability_manifest(harness_binary_digest="a"*64)
    alias = router.model_aliases["dsh.native.conversation"]
    assert alias.worker_eligible and alias.adapter_id == "dsh-native-acp"
    assert (alias.provider_alias, alias.model, alias.effort, alias.cost_class) == (
        "acp", "deepseek-chat", "default", "small")
    assert alias.execution_profile_id == profile.profile_id
    assert alias.execution_profile_digest == profile.profile_digest
    assert alias.capability_policy_digest == registry.policy_digest
    assert router.capability_registry.policy_digest == registry.policy_digest
    capabilities = json.loads(DEFAULT.read_bytes())
    routes = json.loads((ROOT/"config/executive_worker_routes.json").read_bytes())
    assert capabilities["production_armed"] is routes["production_armed"] is False
    assert "dsh.native.conversation" not in json.dumps(routes["routes"])
    assert routes["providers"]["acp"] == dict(
        adapter_id="dsh-native-acp", enabled=True, autonomous_allowed=True)
