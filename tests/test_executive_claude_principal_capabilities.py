"""Closed capability policy for explicit Executive COO principals."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from control_plane import executive_agent_capabilities as capability_registry
from control_plane.executive_agent_capabilities import (
    CAPABILITY_POLICY_SCHEMA_V5,
    CLAUDE_PRINCIPAL_AUTH_REALM,
    CLAUDE_PRINCIPAL_EXECUTION_SURFACE,
    HERMES_NATIVE_PRINCIPAL_EXECUTION_SURFACE,
    HERMES_NATIVE_PRINCIPAL_PROFILE_ID,
    OAUTH_PRINCIPAL_AUTH_REALM,
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
    adapter_supports_execution_surface,
    is_sealed_worker_execution_surface,
    observed_mcp_tool_schema_digest,
    supports_supervisor_validation_resources,
)
from control_plane.operator_harness_contract import NativeHelperPolicy
from integrations.executive_mcp.coo import (
    COO_SERVER_NAME,
    COO_SERVER_VERSION,
    COO_TOOL_SPECS,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/executive_claude_principal_capabilities.json"
DEFAULT_POLICY = ROOT / "config/executive_agent_capabilities.json"
PROFILE_ID = "principal.claude-code.executive-coo.v1"
GRANT_ID = "mastermind-executive-coo-v1"
# Adding disabled context, discovery and project knowledge alternatives changes only the aggregate
# policy identity. Existing profile/grant/config identities below stay fixed.
EXPECTED_POLICY_DIGEST = "7d75e40a79866b0ec0f8409c379ee4ed9b21725038df9beb0cd95ef7a5f8ff3f"
EXPECTED_PROFILE_DIGEST = "5d4a2b7e89c5fee0e34be6a623a4a19e5d91b5d743c7365826ef3384af8bf217"
# The incumbent Claude config projection for the current COO tool catalog.
# Adding Hermes preserves the existing Claude surface and grant projection;
# the catalog itself includes C29's selected-child tool.
EXPECTED_CLAUDE_CONFIG_DIGEST = (
    "fd45f3293d1017491335075b3faf329404eccac6851f9419aa494dde79878631"
)
# Independently fixed public configuration identity for the Hermes surface.
EXPECTED_HERMES_CONFIG_DIGEST = (
    "db0769ca59b37eda6d5424cc2e11a8da52258af5711a8e9a08ad5e0a6550b97e"
)
# The incumbent principal policy's Executive COO OAuth grant identity and
# transport contract, fixed by the sole policy file.
PRINCIPAL_COO_URL = "https://mcp.mastermind-x.com/mcp/coo"
PRINCIPAL_COO_CONFIG_NAME = "mastermindExecutiveCoo"
# The accepted V4 fixture is the source of the one capability package the
# opt-in V5 supervisor-validation plane requires.
V4_FIXTURE = ROOT / "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json"
V5_RESOURCE_ID = "codespace-devbox-sandbox-v1"
V5_IMAGE_DIGEST = "519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7"


def load(path=POLICY):
    return ExecutionCapabilityRegistry.load(path, source_root=ROOT)


def write_policy(tmp_path, raw, name="policy.json"):
    path = tmp_path / name
    path.write_text(json.dumps(raw))
    return path


def coo_catalog():
    """Return the current COO tool catalog from the accepted owner.

    The catalog is derived from the owning module rather than an obsolete
    hardcoded tool list, so an evolving COO schema moves this fixture with
    it instead of freezing a stale catalog into the policy.
    """
    specs = {
        item.name: {
            "name": item.name,
            "inputSchema": item.input_schema,
            "annotations": item.annotations,
        }
        for item in COO_TOOL_SPECS
    }
    return sorted(specs), observed_mcp_tool_schema_digest({"tools": specs})


def hermes_profile():
    """The opt-in Hermes native principal profile declaration."""
    return {
        "enabled": True,
        "execution_surface": HERMES_NATIVE_PRINCIPAL_EXECUTION_SURFACE,
        "auth_realm": OAUTH_PRINCIPAL_AUTH_REALM,
        "sandbox_policy": "read-only",
        "approval_policy": "never",
        "network_policy": "disabled",
        "write_capable": False,
        "native_helper_policy": "disabled",
        "native_helper": None,
        "skills": [],
        "mcp_servers": [GRANT_ID],
        "resources": [],
        "plugins": [],
        "forbidden": ["browser-control", "filesystem-write", "worker-launch"],
    }


def hermes_policy_document():
    """Use the actual shipped profile for bounded mutation tests."""
    raw = json.loads(POLICY.read_text())
    assert raw["profiles"][HERMES_NATIVE_PRINCIPAL_PROFILE_ID] == hermes_profile()
    return raw


def v5_validation_resource():
    return {
        "kind": "codespace-devbox-sandbox-v1",
        "recipes": ["compileall"],
        "image_digest": V5_IMAGE_DIGEST,
        "network": "none",
        "cpu_millis": 1000,
        "memory_bytes": 512 * 1024 * 1024,
        "pids_limit": 64,
        "workspace_tmpfs_bytes": 256 * 1024 * 1024,
        "tmp_tmpfs_bytes": 64 * 1024 * 1024,
        "timeout_seconds": 120,
        "max_stdout_bytes": 4 * 1024 * 1024,
        "max_stderr_bytes": 1024 * 1024,
        "max_snapshot_files": 4096,
        "max_snapshot_bytes": 64 * 1024 * 1024,
    }


def v5_hermes_policy_document():
    """The principal policy carried in the opt-in V5 generation."""
    raw = json.loads(POLICY.read_text())
    v4 = json.loads(V4_FIXTURE.read_text())
    raw["schema_version"] = CAPABILITY_POLICY_SCHEMA_V5
    raw["capability_packages"] = v4["capability_packages"]
    raw["validation_resources"] = {V5_RESOURCE_ID: v5_validation_resource()}
    for profile in raw["profiles"].values():
        profile["skill_capabilities"] = []
        profile["validation_resource_grants"] = []
    hermes = hermes_profile()
    hermes["skill_capabilities"] = []
    hermes["validation_resource_grants"] = []
    raw["profiles"][HERMES_NATIVE_PRINCIPAL_PROFILE_ID] = hermes
    return raw


def test_principal_policy_is_distinct_from_default_worker_registry():
    default = ExecutionCapabilityRegistry.load(DEFAULT_POLICY, source_root=ROOT)
    assert PROFILE_ID not in default.profiles
    assert GRANT_ID not in default.mcp_servers

    registry = load()
    profile = registry.resolve(PROFILE_ID)
    assert registry.policy_digest == EXPECTED_POLICY_DIGEST
    assert profile.profile_digest == EXPECTED_PROFILE_DIGEST
    assert profile.execution_surface == CLAUDE_PRINCIPAL_EXECUTION_SURFACE
    assert profile.auth_realm == CLAUDE_PRINCIPAL_AUTH_REALM
    assert profile.write_capable is False
    assert profile.skills == ()
    assert profile.resource_grants == ()
    assert profile.plugins == ()
    assert len(profile.mcp_server_grants) == 1
    assert adapter_supports_execution_surface("claude-code", profile.execution_surface) is False
    assert is_sealed_worker_execution_surface(profile.execution_surface) is False


def test_principal_policy_pins_exact_role_correct_coo_catalog():
    registry = load()
    grant = registry.resolve(PROFILE_ID).mcp_server_grants[0]
    specs = {
        item.name: {
            "name": item.name,
            "inputSchema": item.input_schema,
            "annotations": item.annotations,
        }
        for item in COO_TOOL_SPECS
    }
    assert grant.capability_id == GRANT_ID
    assert grant.server_identity == COO_SERVER_NAME
    assert grant.server_version == COO_SERVER_VERSION
    assert grant.auth_status == "oAuth"
    assert grant.url == "https://mcp.mastermind-x.com/mcp/coo"
    assert set(grant.enabled_tools) == set(specs)
    assert grant.tool_schema_digest == observed_mcp_tool_schema_digest({"tools": specs})


@pytest.mark.parametrize(
    "mutation",
    [
        "worker_surface",
        "worker_realm",
        "oauth_realm_on_worker_surface",
        "write",
        "no_mcp",
        "non_oauth",
        "resource",
        "plugin",
        "helper",
    ],
)
def test_principal_policy_cannot_widen_into_worker_or_ambient_authority(tmp_path, mutation):
    raw = json.loads(POLICY.read_text())
    profile = raw["profiles"][PROFILE_ID]
    if mutation == "worker_surface":
        profile["execution_surface"] = "claude-code"
    elif mutation == "oauth_realm_on_worker_surface":
        # The OAuth principal realm stays, but the profile takes a surface
        # that is neither a principal surface nor a sealed worker surface.
        profile["execution_surface"] = "codex-app-server"
    elif mutation == "worker_realm":
        profile["auth_realm"] = "dedicated-worker-account"
    elif mutation == "write":
        profile["write_capable"] = True
        profile["sandbox_policy"] = "workspace-write"
    elif mutation == "no_mcp":
        profile["mcp_servers"] = []
    elif mutation == "non_oauth":
        raw["mcp_servers"][GRANT_ID]["auth_status"] = "unsupported"
    elif mutation == "resource":
        profile["resources"] = ["invented-resource"]
    elif mutation == "plugin":
        profile["plugins"] = ["invented-plugin"]
    else:
        profile["native_helper_policy"] = "parent_read_only_ceiling"
        profile["native_helper"] = {
            "mechanism": "codex-multi-agent-v2-inherit-parent",
            "default_model": "gpt-5.6-sol",
            "default_reasoning_effort": "xhigh",
            "inherit_parent_capabilities": True,
            "hide_spawn_agent_metadata": True,
            "max_concurrent_helpers": 1,
            "max_depth": 1,
            "max_runtime_seconds": 60,
        }
    path = tmp_path / "principal.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(path, source_root=ROOT)


def test_hermes_native_principal_profile_parses_with_its_own_surface_and_digest():
    registry = load()
    hermes = registry.resolve(HERMES_NATIVE_PRINCIPAL_PROFILE_ID)
    claude = registry.resolve(PROFILE_ID)

    assert hermes.execution_surface == HERMES_NATIVE_PRINCIPAL_EXECUTION_SURFACE
    assert hermes.auth_realm == OAUTH_PRINCIPAL_AUTH_REALM
    assert OAUTH_PRINCIPAL_AUTH_REALM == CLAUDE_PRINCIPAL_AUTH_REALM
    assert hermes.sandbox_policy == "read-only"
    assert hermes.approval_policy == "never"
    assert hermes.network_policy == "disabled"
    assert hermes.write_capable is False
    assert hermes.native_helper_policy is NativeHelperPolicy.DISABLED
    assert hermes.native_helper is None
    assert hermes.skills == ()
    assert hermes.skill_grants == ()
    assert hermes.resource_grants == ()
    assert hermes.validation_resource_grants == ()
    assert hermes.plugins == ()

    # Exactly the incumbent Executive COO OAuth grant, with its existing
    # capability identity and transport contract.
    assert len(hermes.mcp_server_grants) == 1
    grant = hermes.mcp_server_grants[0]
    assert grant.capability_id == GRANT_ID
    assert grant.config_name == PRINCIPAL_COO_CONFIG_NAME
    assert grant.transport == "streamable-http"
    assert grant.url == PRINCIPAL_COO_URL
    assert grant.auth_status == "oAuth"
    assert grant.server_identity == COO_SERVER_NAME
    assert grant.server_version == COO_SERVER_VERSION
    assert grant.grant_digest == claude.mcp_server_grants[0].grant_digest

    # The catalog comes from the accepted owner, never a frozen tool list.
    names, digest = coo_catalog()
    assert list(grant.enabled_tools) == names
    assert grant.tool_schema_digest == digest

    # Each principal surface keeps its own expected config digest, and the
    # existing Claude surface keeps its exact pre-existing bytes.
    assert hermes.expected_config_digest == EXPECTED_HERMES_CONFIG_DIGEST
    assert claude.expected_config_digest == EXPECTED_CLAUDE_CONFIG_DIGEST
    assert hermes.expected_config_digest != claude.expected_config_digest
    assert hermes.profile_digest != claude.profile_digest


@pytest.mark.parametrize(
    "mutation",
    [
        "profile_id",
        "surface",
        "realm",
        "mcp_capability",
        "mcp_identity",
        "mcp_version",
        "mcp_config_name",
        "mcp_url",
        "mcp_transport",
        "extra_mcp",
        "write",
        "helper",
        "skill",
        "plugin",
        "resource",
    ],
)
def test_hermes_native_principal_ceiling_refuses_widening(tmp_path, mutation):
    raw = hermes_policy_document()
    hermes = raw["profiles"][HERMES_NATIVE_PRINCIPAL_PROFILE_ID]
    if mutation == "profile_id":
        raw["profiles"]["principal.hermes-native.executive-coo.v2"] = raw["profiles"].pop(
            HERMES_NATIVE_PRINCIPAL_PROFILE_ID
        )
    elif mutation == "surface":
        hermes["execution_surface"] = CLAUDE_PRINCIPAL_EXECUTION_SURFACE
    elif mutation == "realm":
        hermes["auth_realm"] = "dedicated-worker-account"
    elif mutation == "mcp_capability":
        raw["mcp_servers"]["invented-http-v1"] = {
            "config_name": "inventedHttp",
            "transport": "streamable-http",
            "url": "https://invented.example.com/mcp",
            "required": True,
            "auth_status": "bearerToken",
            "server_identity": "invented-http",
            "server_version": "1.0.0",
            "enabled_tools": ["invented_tool"],
            "default_tools_approval_mode": "approve",
            "tool_schema_digest": "9" * 64,
        }
        hermes["mcp_servers"] = ["invented-http-v1"]
    elif mutation == "mcp_identity":
        raw["mcp_servers"][GRANT_ID]["server_identity"] = "invented-identity"
    elif mutation == "mcp_version":
        raw["mcp_servers"][GRANT_ID]["server_version"] = "9.9.9"
    elif mutation == "mcp_config_name":
        raw["mcp_servers"][GRANT_ID]["config_name"] = "inventedCoo"
    elif mutation == "mcp_url":
        raw["mcp_servers"][GRANT_ID]["url"] = "https://invented.example.com/mcp"
    elif mutation == "mcp_transport":
        raw["mcp_servers"][GRANT_ID].pop("url")
        raw["mcp_servers"][GRANT_ID]["transport"] = "stdio"
        raw["mcp_servers"][GRANT_ID]["command"] = "/usr/bin/python3"
        raw["mcp_servers"][GRANT_ID]["args"] = []
    elif mutation == "extra_mcp":
        raw["mcp_servers"]["invented-http-v1"] = {
            "config_name": "inventedHttp",
            "transport": "streamable-http",
            "url": "https://invented.example.com/mcp",
            "required": True,
            "auth_status": "bearerToken",
            "server_identity": "invented-http",
            "server_version": "1.0.0",
            "enabled_tools": ["invented_tool"],
            "default_tools_approval_mode": "approve",
            "tool_schema_digest": "9" * 64,
        }
        hermes["mcp_servers"] = [GRANT_ID, "invented-http-v1"]
    elif mutation == "write":
        hermes["write_capable"] = True
        hermes["sandbox_policy"] = "workspace-write"
    elif mutation == "helper":
        hermes["native_helper_policy"] = "parent_read_only_ceiling"
        hermes["native_helper"] = {
            "mechanism": "codex-multi-agent-v2-inherit-parent",
            "default_model": "gpt-5.6-sol",
            "default_reasoning_effort": "xhigh",
            "inherit_parent_capabilities": True,
            "hide_spawn_agent_metadata": True,
            "max_concurrent_helpers": 1,
            "max_depth": 1,
            "max_runtime_seconds": 60,
        }
    elif mutation == "skill":
        hermes["skills"] = ["invented-skill"]
    elif mutation == "plugin":
        hermes["plugins"] = ["invented-plugin"]
    else:
        hermes["resources"] = ["invented-resource"]
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(
            write_policy(tmp_path, raw), source_root=ROOT
        )


def test_hermes_native_principal_has_no_worker_or_launch_eligibility(tmp_path):
    registry = ExecutionCapabilityRegistry.load(
        write_policy(tmp_path, hermes_policy_document()), source_root=ROOT
    )
    hermes = registry.resolve(HERMES_NATIVE_PRINCIPAL_PROFILE_ID)
    surface = hermes.execution_surface

    # No adapter owns the surface, so no worker placement can select it.
    for adapter in ("codex-cli", "claude-code", "attended-fabric", "acp", "canonical-paid-fabric"):
        assert adapter_supports_execution_surface(adapter, surface) is False
    # The public helper needs an adapter id it does not enumerate, so the
    # "joins no adapter mapping" claim is asserted against the mapping itself.
    assert all(
        HERMES_NATIVE_PRINCIPAL_EXECUTION_SURFACE not in surfaces
        for surfaces in capability_registry._ADAPTER_EXECUTION_SURFACES.values()
    )
    assert is_sealed_worker_execution_surface(surface) is False
    assert supports_supervisor_validation_resources(surface) is False

    # Neither the Codex nor the Claude launch projection is usable here.
    with pytest.raises(CapabilityPolicyError):
        hermes.app_server_config_projection()
    with pytest.raises(CapabilityPolicyError):
        hermes.claude_sdk_config_projection()
    with pytest.raises(CapabilityPolicyError):
        hermes.app_server_config_overrides()


def test_hermes_native_principal_is_explicitly_shipped_outside_worker_policy():
    default = ExecutionCapabilityRegistry.load(DEFAULT_POLICY, source_root=ROOT)
    assert HERMES_NATIVE_PRINCIPAL_PROFILE_ID not in default.profiles
    assert HERMES_NATIVE_PRINCIPAL_EXECUTION_SURFACE not in {
        profile.execution_surface for profile in default.profiles.values()
    }

    registry = load()
    assert HERMES_NATIVE_PRINCIPAL_PROFILE_ID in registry.profiles
    assert registry.production_armed is False
    assert registry.policy_digest == EXPECTED_POLICY_DIGEST
    assert registry.resolve(PROFILE_ID).profile_digest == EXPECTED_PROFILE_DIGEST


def test_hermes_native_principal_refuses_supervisor_validation_resources(tmp_path):
    raw = v5_hermes_policy_document()
    registry = ExecutionCapabilityRegistry.load(
        write_policy(tmp_path, raw), source_root=ROOT
    )
    hermes = registry.profiles[HERMES_NATIVE_PRINCIPAL_PROFILE_ID]
    assert hermes.validation_resource_grants == ()

    raw["profiles"][HERMES_NATIVE_PRINCIPAL_PROFILE_ID][
        "validation_resource_grants"
    ] = [V5_RESOURCE_ID]
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(
            write_policy(tmp_path, raw, "granted.json"), source_root=ROOT
        )
