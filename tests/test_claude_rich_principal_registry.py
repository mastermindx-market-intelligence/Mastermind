from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    CLAUDE_OPERATOR_EXECUTION_SURFACE,
    EXECUTIVE_COO_MCP_CAPABILITY_ID,
    EXECUTIVE_COO_MCP_CONFIG_NAME,
    EXECUTIVE_COO_MCP_ENABLED_TOOLS,
    EXECUTIVE_COO_MCP_SERVER_IDENTITY,
    EXECUTIVE_COO_MCP_SERVER_VERSION,
    EXECUTIVE_COO_MCP_TOOL_SCHEMA_DIGEST,
    EXECUTIVE_COO_MCP_URL,
    PRINCIPAL_COMPANY_MCP_ARGS,
    PRINCIPAL_COMPANY_MCP_CAPABILITY_ID,
    PRINCIPAL_COMPANY_MCP_COMMAND,
    PRINCIPAL_COMPANY_MCP_CONFIG_NAME,
    PRINCIPAL_COMPANY_MCP_ENABLED_TOOLS,
    PRINCIPAL_COMPANY_MCP_SERVER_IDENTITY,
    PRINCIPAL_COMPANY_MCP_SERVER_VERSION,
    PRINCIPAL_COMPANY_MCP_TOOL_SCHEMA_DIGEST,
    RICH_CLAUDE_PRINCIPAL_MCP_IDS,
    RICH_CLAUDE_PRINCIPAL_PROFILE_ID,
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from integrations.executive_mcp.coo import (
    COO_SERVER_NAME,
    COO_SERVER_VERSION,
    COO_TOOL_NAMES,
    COO_TOOL_SCHEMA_DIGEST,
)
from integrations.mastermind_company_mcp.principal_schemas import (
    PRINCIPAL_SERVER_IDENTITY,
    PRINCIPAL_SERVER_VERSION,
    PRINCIPAL_TOOL_SCHEMA_DIGEST,
    PRINCIPAL_TOOL_SPECS,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "executive_agent_capabilities.json"
POLICY_VERSION = "2026-10-06.claude-rich-principal-rg1"


def raw_policy() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def write_policy(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_rich_principal_grants_match_current_source_generations() -> None:
    assert EXECUTIVE_COO_MCP_SERVER_IDENTITY == COO_SERVER_NAME
    assert EXECUTIVE_COO_MCP_SERVER_VERSION == COO_SERVER_VERSION
    assert EXECUTIVE_COO_MCP_TOOL_SCHEMA_DIGEST == COO_TOOL_SCHEMA_DIGEST
    assert EXECUTIVE_COO_MCP_ENABLED_TOOLS == tuple(sorted(COO_TOOL_NAMES))

    assert PRINCIPAL_COMPANY_MCP_SERVER_IDENTITY == PRINCIPAL_SERVER_IDENTITY
    assert PRINCIPAL_COMPANY_MCP_SERVER_VERSION == PRINCIPAL_SERVER_VERSION
    assert PRINCIPAL_COMPANY_MCP_TOOL_SCHEMA_DIGEST == PRINCIPAL_TOOL_SCHEMA_DIGEST
    assert PRINCIPAL_COMPANY_MCP_ENABLED_TOOLS == tuple(
        sorted(spec.name for spec in PRINCIPAL_TOOL_SPECS)
    )


def test_default_policy_contains_only_disabled_inert_rich_candidate() -> None:
    registry = ExecutionCapabilityRegistry.load(POLICY, source_root=ROOT)
    assert registry.policy_version == POLICY_VERSION
    profile = registry.profiles[RICH_CLAUDE_PRINCIPAL_PROFILE_ID]

    assert profile.enabled is False
    assert profile.execution_surface == CLAUDE_OPERATOR_EXECUTION_SURFACE
    assert profile.write_capable is False
    assert profile.network_policy == "disabled"
    assert profile.mcp_servers == RICH_CLAUDE_PRINCIPAL_MCP_IDS
    assert profile.skills == ()
    assert profile.skill_grants == ()
    assert profile.resource_grants == ()
    assert profile.plugins == ()
    assert len(profile.profile_digest) == 64

    executive = registry.mcp_servers[EXECUTIVE_COO_MCP_CAPABILITY_ID]
    dialogue = registry.mcp_servers[PRINCIPAL_COMPANY_MCP_CAPABILITY_ID]

    assert executive.config_name == EXECUTIVE_COO_MCP_CONFIG_NAME
    assert executive.transport == "streamable-http"
    assert executive.url == EXECUTIVE_COO_MCP_URL
    assert executive.command is None and executive.args == ()
    assert executive.auth_status == "oAuth"
    assert executive.enabled_tools == EXECUTIVE_COO_MCP_ENABLED_TOOLS

    assert dialogue.config_name == PRINCIPAL_COMPANY_MCP_CONFIG_NAME
    assert dialogue.transport == "stdio"
    assert dialogue.command == PRINCIPAL_COMPANY_MCP_COMMAND
    assert dialogue.args == PRINCIPAL_COMPANY_MCP_ARGS
    assert dialogue.url is None
    assert dialogue.auth_status == "unsupported"
    assert dialogue.enabled_tools == PRINCIPAL_COMPANY_MCP_ENABLED_TOOLS


def test_rich_candidate_projection_is_exact_but_still_transport_inert() -> None:
    registry = ExecutionCapabilityRegistry.load(POLICY, source_root=ROOT)
    profile = registry.profiles[RICH_CLAUDE_PRINCIPAL_PROFILE_ID]
    projected = profile.claude_sdk_config_projection()

    assert projected["tools"] == ["Read", "Glob", "Grep"]
    assert projected["permission_mode"] == "dontAsk"
    assert projected["setting_sources"] == []
    assert projected["strict_mcp_config"] is True
    assert projected["skills"] == []
    assert set(projected["mcp_servers"]) == {
        EXECUTIVE_COO_MCP_CONFIG_NAME,
        PRINCIPAL_COMPANY_MCP_CONFIG_NAME,
    }
    assert projected["mcp_servers"][EXECUTIVE_COO_MCP_CONFIG_NAME] == {
        "type": "http",
        "url": EXECUTIVE_COO_MCP_URL,
    }
    assert projected["mcp_servers"][PRINCIPAL_COMPANY_MCP_CONFIG_NAME] == {
        "type": "stdio",
        "command": PRINCIPAL_COMPANY_MCP_COMMAND,
        "args": list(PRINCIPAL_COMPANY_MCP_ARGS),
    }

    expected_tools = {
        *(
            f"mcp__{EXECUTIVE_COO_MCP_CONFIG_NAME}__{tool}"
            for tool in EXECUTIVE_COO_MCP_ENABLED_TOOLS
        ),
        *(
            f"mcp__{PRINCIPAL_COMPANY_MCP_CONFIG_NAME}__{tool}"
            for tool in PRINCIPAL_COMPANY_MCP_ENABLED_TOOLS
        ),
    }
    assert set(projected["allowed_tools"]) == expected_tools
    network = projected["sandbox"]["network"]
    assert network == {
        "allowedDomains": [],
        "deniedDomains": ["*"],
        "allowAllUnixSockets": False,
        "allowLocalBinding": False,
    }
    assert len(profile.expected_config_digest) == 64


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8444/mcp",
        "http://127.0.0.1:8443/mcp",
        "http://127.0.0.1:8444/mcp?x=1",
        "https://127.0.0.1:8444/mcp",
        "http://127.0.0.1:8444/other",
    ],
)
def test_executive_coo_grant_refuses_any_loopback_drift(tmp_path: Path, url: str) -> None:
    raw = raw_policy()
    raw["mcp_servers"][EXECUTIVE_COO_MCP_CAPABILITY_ID]["url"] = url
    with pytest.raises(CapabilityPolicyError, match="exact reviewed loopback"):
        ExecutionCapabilityRegistry.load(write_policy(tmp_path, raw), source_root=ROOT)


def test_generic_http_grants_remain_https_only(tmp_path: Path) -> None:
    raw = raw_policy()
    raw["mcp_servers"]["openai-developer-docs-v1"]["url"] = (
        "http://127.0.0.1:8444/mcp"
    )
    with pytest.raises(CapabilityPolicyError, match="HTTPS"):
        ExecutionCapabilityRegistry.load(write_policy(tmp_path, raw), source_root=ROOT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("command", "/tmp/python"),
        ("args", ["-I", "-S", "-B", "-c", "pass"]),
        ("config_name", "borrowedPrincipal"),
        ("server_identity", "different-principal"),
        ("server_version", "9.9.9"),
        ("enabled_tools", ["read_thread"]),
        ("tool_schema_digest", "0" * 64),
        ("auth_status", "oAuth"),
    ],
)
def test_principal_company_grant_refuses_binding_drift(
    tmp_path: Path, field: str, value
) -> None:
    raw = raw_policy()
    raw["mcp_servers"][PRINCIPAL_COMPANY_MCP_CAPABILITY_ID][field] = value
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(write_policy(tmp_path, raw), source_root=ROOT)


def test_rich_grants_cannot_be_borrowed_by_another_profile(tmp_path: Path) -> None:
    for capability_id in RICH_CLAUDE_PRINCIPAL_MCP_IDS:
        raw = raw_policy()
        raw["profiles"]["operator.appserver.readonly.v1"]["mcp_servers"] = [
            capability_id
        ]
        with pytest.raises(CapabilityPolicyError, match="cannot borrow"):
            ExecutionCapabilityRegistry.load(write_policy(tmp_path, raw), source_root=ROOT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("enabled", True),
        ("execution_surface", "codex-app-server"),
        ("network_policy", "loopback-browser-only"),
        ("write_capable", True),
        ("native_helper_policy", "parent_read_only_ceiling"),
        ("resources", ["worker-browser-b1-local"]),
        ("plugins", ["ambient"]),
        ("forbidden", ["mastermindExecutiveCoo"]),
        ("mcp_servers", [EXECUTIVE_COO_MCP_CAPABILITY_ID]),
    ],
)
def test_rich_profile_refuses_authority_widening(
    tmp_path: Path, field: str, value
) -> None:
    raw = raw_policy()
    raw["profiles"][RICH_CLAUDE_PRINCIPAL_PROFILE_ID][field] = value
    if field == "native_helper_policy":
        raw["profiles"][RICH_CLAUDE_PRINCIPAL_PROFILE_ID]["native_helper"] = {
            "mechanism": "codex-multi-agent-v2-inherit-parent",
            "default_model": "gpt-5.6-sol",
            "default_reasoning_effort": "xhigh",
            "inherit_parent_capabilities": True,
            "hide_spawn_agent_metadata": True,
            "max_concurrent_helpers": 1,
            "max_depth": 1,
            "max_runtime_seconds": 60,
        }
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(write_policy(tmp_path, raw), source_root=ROOT)


def test_candidate_profile_cannot_use_codex_projection_or_be_treated_as_sealed_worker() -> None:
    registry = ExecutionCapabilityRegistry.load(POLICY, source_root=ROOT)
    profile = registry.profiles[RICH_CLAUDE_PRINCIPAL_PROFILE_ID]
    with pytest.raises(CapabilityPolicyError, match="cannot use a Codex"):
        profile.app_server_config_projection()
    assert profile.execution_surface != "claude-code"


def test_rg1_test_is_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_claude_rich_principal_registry.py" in gate["included"]
