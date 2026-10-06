"""Closed capability policy for the attended Claude COO principal."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    CLAUDE_PRINCIPAL_AUTH_REALM,
    CLAUDE_PRINCIPAL_EXECUTION_SURFACE,
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
    adapter_supports_execution_surface,
    is_sealed_worker_execution_surface,
    observed_mcp_tool_schema_digest,
)
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
EXPECTED_POLICY_DIGEST = "9a244ed31570e1cf24a2c8746e3b97fd5ed2f87aec7f748c88a9bc28053523cf"
EXPECTED_PROFILE_DIGEST = "9bb045fa01053def3f152f4c17576b8de0e3b17b8c8b5315af444614cb733814"


def load(path=POLICY):
    return ExecutionCapabilityRegistry.load(path, source_root=ROOT)


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
