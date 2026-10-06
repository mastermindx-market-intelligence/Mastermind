from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
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


def test_candidate_manifest_matches_both_current_source_generations() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest) == {
        "schema",
        "production_armed",
        "profile_id",
        "profile_state",
        "execution_surface",
        "capabilities",
        "unresolved",
    }
    assert manifest["schema"] == (
        "mastermind.claude_rich_principal_capability_generations.v1"
    )
    assert manifest["production_armed"] is False
    assert manifest["profile_id"] == "principal.claude.coo.rich.v1"
    assert manifest["profile_state"] == "CANDIDATE_ONLY_TRANSPORT_GATED"
    assert manifest["execution_surface"] == "claude-agent-sdk"

    rows = {row["name"]: row for row in manifest["capabilities"]}
    assert set(rows) == {"executive_coo", "principal_company_dialogue"}

    executive = rows["executive_coo"]
    assert executive["server_identity"] == COO_SERVER_NAME
    assert executive["server_version"] == COO_SERVER_VERSION
    assert executive["enabled_tools"] == sorted(COO_TOOL_NAMES)
    assert executive["tool_schema_digest"] == COO_TOOL_SCHEMA_DIGEST
    assert executive["grant_capability_id"] is None
    assert executive["transport_owner"] == "Mastermind#955"
    assert executive["transport_state"] == (
        "SOURCE_REPAIRED_REVIEW_AND_NATIVE_PROOF_OPEN"
    )

    dialogue = rows["principal_company_dialogue"]
    assert dialogue["server_identity"] == PRINCIPAL_SERVER_IDENTITY
    assert dialogue["server_version"] == PRINCIPAL_SERVER_VERSION
    assert dialogue["enabled_tools"] == sorted(
        spec.name for spec in PRINCIPAL_TOOL_SPECS
    )
    assert dialogue["tool_schema_digest"] == PRINCIPAL_TOOL_SCHEMA_DIGEST
    assert dialogue["grant_capability_id"] is None
    assert dialogue["transport_owner"] == (
        "integrations/company_dialogue_principal_host_transport.py"
    )
    assert dialogue["transport_state"] == (
        "UNIX_EDGE_SOURCE_BUILT_SERVICE_BINDING_INSTALL_OPEN"
    )

    assert len(manifest["unresolved"]) == 5
    assert any("network policy" in item for item in manifest["unresolved"])
    assert any("profile_digest" in item for item in manifest["unresolved"])


def test_candidate_manifest_cannot_be_loaded_as_capability_policy() -> None:
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(MANIFEST, source_root=ROOT)


def test_candidate_intentionally_has_no_transport_or_grant_identity() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for row in manifest["capabilities"]:
        assert row["grant_capability_id"] is None
        assert "config_name" not in row
        assert "transport" not in row
        assert "url" not in row
        assert "command" not in row
        assert "args" not in row


def test_candidate_generation_test_is_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_claude_rich_principal_generation.py" in gate["included"]
