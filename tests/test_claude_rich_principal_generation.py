from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    EXECUTIVE_COO_MCP_CAPABILITY_ID,
    EXECUTIVE_COO_MCP_CONFIG_NAME,
    PRINCIPAL_COMPANY_MCP_CAPABILITY_ID,
    PRINCIPAL_COMPANY_MCP_CONFIG_NAME,
    RICH_CLAUDE_PRINCIPAL_PROFILE_ID,
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
    observed_mcp_tool_schema_digest,
)
from integrations.executive_mcp.coo import (
    COO_SERVER_NAME,
    COO_SERVER_VERSION,
    COO_TOOL_NAMES,
    COO_TOOL_SCHEMA_DIGEST,
    COO_TOOL_SPECS,
    coo_tool_schema_digest,
)
from integrations.mastermind_company_mcp.principal_schemas import (
    PRINCIPAL_SERVER_IDENTITY,
    PRINCIPAL_SERVER_VERSION,
    PRINCIPAL_TOOL_SCHEMA_DIGEST,
    PRINCIPAL_TOOL_SPECS,
    principal_tool_schema_digest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "docs"
    / "claude_capability_hardening_20261004"
    / "RICH_PRINCIPAL_CAPABILITY_GENERATIONS.json"
)


def _catalog_digest(specs) -> str | None:
    tools = {
        spec.name: {
            "name": spec.name,
            "inputSchema": spec.input_schema,
            "annotations": spec.annotations,
        }
        for spec in specs
    }
    return observed_mcp_tool_schema_digest({"tools": tools})


def test_executive_coo_tool_generation_is_frozen_and_registry_compatible() -> None:
    assert COO_TOOL_SCHEMA_DIGEST == coo_tool_schema_digest()
    assert COO_TOOL_SCHEMA_DIGEST == _catalog_digest(COO_TOOL_SPECS)
    assert tuple(sorted(COO_TOOL_NAMES)) == tuple(
        sorted(spec.name for spec in COO_TOOL_SPECS)
    )


def test_principal_dialogue_tool_generation_is_frozen_and_registry_compatible() -> None:
    assert PRINCIPAL_TOOL_SCHEMA_DIGEST == principal_tool_schema_digest()
    assert PRINCIPAL_TOOL_SCHEMA_DIGEST == _catalog_digest(PRINCIPAL_TOOL_SPECS)


def test_candidate_manifest_matches_current_registry_and_source_generations() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest) == {
        "schema",
        "production_armed",
        "policy_version",
        "policy_digest",
        "profile_id",
        "profile_digest",
        "profile_state",
        "execution_surface",
        "capabilities",
        "unresolved",
    }
    assert manifest["schema"] == (
        "mastermind.claude_rich_principal_capability_generations.v2"
    )
    assert manifest["production_armed"] is False
    assert manifest["profile_id"] == RICH_CLAUDE_PRINCIPAL_PROFILE_ID
    assert manifest["profile_state"] == "DISABLED_REGISTRY_CANDIDATE"
    assert manifest["execution_surface"] == "claude-agent-sdk"

    registry = ExecutionCapabilityRegistry.load()
    profile = registry.profiles[RICH_CLAUDE_PRINCIPAL_PROFILE_ID]
    assert profile.enabled is False
    assert manifest["policy_version"] == registry.policy_version
    assert manifest["policy_digest"] == registry.policy_digest
    assert manifest["profile_digest"] == profile.profile_digest

    rows = {row["name"]: row for row in manifest["capabilities"]}
    assert set(rows) == {"executive_coo", "principal_company_dialogue"}

    executive = rows["executive_coo"]
    executive_grant = registry.mcp_servers[EXECUTIVE_COO_MCP_CAPABILITY_ID]
    assert executive["grant_capability_id"] == EXECUTIVE_COO_MCP_CAPABILITY_ID
    assert executive["grant_digest"] == executive_grant.grant_digest
    assert executive["config_name"] == EXECUTIVE_COO_MCP_CONFIG_NAME
    assert executive["transport"] == "streamable-http"
    assert executive["auth_status"] == "oAuth"
    assert executive["server_identity"] == COO_SERVER_NAME
    assert executive["server_version"] == COO_SERVER_VERSION
    assert executive["enabled_tools"] == sorted(COO_TOOL_NAMES)
    assert executive["tool_schema_digest"] == COO_TOOL_SCHEMA_DIGEST
    assert executive["transport_owner"] == "Mastermind#955"
    assert executive["transport_state"] == "SOURCE_MERGED_NATIVE_AUTH_PROOF_OPEN"

    dialogue = rows["principal_company_dialogue"]
    dialogue_grant = registry.mcp_servers[PRINCIPAL_COMPANY_MCP_CAPABILITY_ID]
    assert dialogue["grant_capability_id"] == PRINCIPAL_COMPANY_MCP_CAPABILITY_ID
    assert dialogue["grant_digest"] == dialogue_grant.grant_digest
    assert dialogue["config_name"] == PRINCIPAL_COMPANY_MCP_CONFIG_NAME
    assert dialogue["transport"] == "stdio"
    assert dialogue["auth_status"] == "unsupported"
    assert dialogue["server_identity"] == PRINCIPAL_SERVER_IDENTITY
    assert dialogue["server_version"] == PRINCIPAL_SERVER_VERSION
    assert dialogue["enabled_tools"] == sorted(
        spec.name for spec in PRINCIPAL_TOOL_SPECS
    )
    assert dialogue["tool_schema_digest"] == PRINCIPAL_TOOL_SCHEMA_DIGEST
    assert dialogue["transport_owner"] == (
        "ExecutiveControlService + "
        "ops/executive_os/company_dialogue_principal_edge.py"
    )
    assert dialogue["transport_state"] == (
        "EDGE_AND_LISTENER_SOURCE_BUILT_INSTALL_CONFIG_OPEN"
    )

    assert len(manifest["unresolved"]) == 5
    assert any("sandbox qualification" in item for item in manifest["unresolved"])
    assert any("supervisor and adapter admission" in item for item in manifest["unresolved"])
    assert any("production enablement" in item for item in manifest["unresolved"])


def test_candidate_manifest_cannot_be_loaded_as_capability_policy() -> None:
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(MANIFEST, source_root=ROOT)


def test_candidate_records_grants_without_embedding_launch_endpoints_or_secrets() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["production_armed"] is False
    rows = {row["name"]: row for row in manifest["capabilities"]}
    assert rows["executive_coo"]["grant_capability_id"] == EXECUTIVE_COO_MCP_CAPABILITY_ID
    assert rows["principal_company_dialogue"]["grant_capability_id"] == (
        PRINCIPAL_COMPANY_MCP_CAPABILITY_ID
    )
    for row in rows.values():
        assert len(row["grant_digest"]) == 64
        assert row["config_name"]
        assert row["transport"] in {"stdio", "streamable-http"}
        assert "url" not in row
        assert "command" not in row
        assert "args" not in row
        assert "token" not in json.dumps(row).lower()
        assert "secret" not in json.dumps(row).lower()


def test_candidate_generation_test_is_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_claude_rich_principal_generation.py" in gate["included"]
