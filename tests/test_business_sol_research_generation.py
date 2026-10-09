from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from integrations.business_sol_installation.bindings import stage_compilation
from integrations.business_sol_installation.research_generation import (
    CANDIDATE_PLUGIN_VERSION,
    REQUIRED_STEWARD_TOOLS,
    ResearchGenerationError,
    compile_research_binding,
    compile_research_manifest,
    preflight_research_generation,
)

SOURCE_COMMIT = "a" * 40
PACKAGE_DIGEST = "b" * 64
WORKSPACE_DIGEST = "c" * 64
RESOURCE_DIGEST = "d" * 64
OAUTH_DIGEST = "e" * 64
TOOL_DIGEST = "8eec65289bf72818fe8362cb02587b6cc78c6eb526a1f602edbd22ffff030918"
SNAPSHOT_DIGEST = "1" * 64
PLUGIN_ID = "Plugin_" + "2" * 32
STEWARD_ID = "asdk_app_" + "3" * 32


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def request() -> dict[str, object]:
    return {
        "schema": "mastermind.business_sol_research_generation_request.v1",
        "generation": 2,
        "source_commit": SOURCE_COMMIT,
        "observed_source_commit": SOURCE_COMMIT,
        "plugin_package_digest": PACKAGE_DIGEST,
        "observed_plugin_package_digest": PACKAGE_DIGEST,
        "workspace_digest": WORKSPACE_DIGEST,
        "workspace_role": "OWNER",
        "plugin": {
            "name": "mastermind-sol",
            "version": CANDIDATE_PLUGIN_VERSION,
            "registry_id": PLUGIN_ID,
            "approved_registry_id_digest": digest_text(PLUGIN_ID),
            "display_name": "Mastermind CEO",
            "installation_policy": "INSTALLED_BY_DEFAULT",
            "installed_version": CANDIDATE_PLUGIN_VERSION,
            "installed_scanned_generation": "mastermind-sol-research-g2",
            "approved_scanned_generation": "mastermind-sol-research-g2",
            "installed": True,
            "enabled": True,
            "research_skill_loaded": True,
            "research_skill_blob_sha": "006c10283d200b47e4cb816906be5f5db3ce7a0f",
        },
        "steward": {
            "app_id": STEWARD_ID,
            "approved_app_id_digest": digest_text(STEWARD_ID),
            "display_name": "Mastermind Steward",
            "workspace_digest": WORKSPACE_DIGEST,
            "publication_state": "PUBLISHED",
            "app_generation": "mastermind-steward-research-g2",
            "approved_app_generation": "mastermind-steward-research-g2",
            "server_name": "mastermind-steward",
            "server_version": "3.0.0",
            "approved_server_version": "3.0.0",
            "resource_digest": RESOURCE_DIGEST,
            "approved_resource_digest": RESOURCE_DIGEST,
            "oauth_policy_digest": OAUTH_DIGEST,
            "approved_oauth_policy_digest": OAUTH_DIGEST,
            "tool_names": list(REQUIRED_STEWARD_TOOLS),
            "tool_contract_digest": TOOL_DIGEST,
            "approved_tool_contract_digest": TOOL_DIGEST,
            "frozen_snapshot_digest": SNAPSHOT_DIGEST,
            "approved_frozen_snapshot_digest": SNAPSHOT_DIGEST,
            "enabled": True,
            "available": True,
            "installed": True,
            "connected": True,
            "authenticated": True,
            "deep_research_eligible": True,
            "company_knowledge_eligible": True,
            "citation_surface_ready": True,
        },
        "github": {
            "connected": True,
            "repository": "mastermindx-market-intelligence/Mastermind",
            "repository_authorized": True,
        },
    }


def test_canonical_app_id_compiles_private_native_reference() -> None:
    value = request()
    result = preflight_research_generation(value)
    assert result["assembly_status"] == "READY_TO_COMPILE"
    assert result["canary_status"] == "READY_FOR_CANARY"
    compiled = compile_research_binding(value)
    assert json.loads(compiled.content) == {
        "apps": {"mastermind-steward": {"id": STEWARD_ID, "required": True}}
    }
    public = json.dumps(compiled.public_receipt, sort_keys=True)
    assert STEWARD_ID not in public
    assert PLUGIN_ID not in public
    assert compiled.public_receipt["generation"] == 2
    assert compiled.public_receipt["workspace_effect_applied"] is False
    assert compiled.public_receipt["oauth_effect_applied"] is False
    assert compiled.public_receipt["production_acceptance_granted"] is False


def test_directory_plugin_identity_is_not_accepted_as_native_app_id() -> None:
    value = request()
    plugin_identity = "plugin_asdk_app_" + "3" * 32
    value["steward"]["app_id"] = plugin_identity
    value["steward"]["approved_app_id_digest"] = digest_text(plugin_identity)
    with pytest.raises(ResearchGenerationError, match="APP_IDENTITY_MISMATCH"):
        preflight_research_generation(value)


def test_missing_search_fetch_holds_assembly_before_native_binding() -> None:
    value = request()
    value["steward"]["tool_names"] = list(REQUIRED_STEWARD_TOOLS[:-2])
    result = preflight_research_generation(value)
    assert result["assembly_status"] == "PREFLIGHT_HELD"
    assert {"code": "RESEARCH_TOOLS_MISSING", "logical_name": "mastermind-steward"} in result["assembly_issues"]
    with pytest.raises(ResearchGenerationError, match="PREFLIGHT_HELD"):
        compile_research_binding(value)

def test_app_publication_is_assembly_gate_but_auth_is_canary_gate() -> None:
    value = request()
    value["steward"]["publication_state"] = "DRAFT"
    result = preflight_research_generation(value)
    assert result["assembly_status"] == "PREFLIGHT_HELD"
    assert {"code": "APP_NOT_PUBLISHED", "logical_name": "mastermind-steward"} in result["assembly_issues"]

    value = request()
    value["steward"]["authenticated"] = False
    value["github"]["repository_authorized"] = False
    value["plugin"]["research_skill_loaded"] = False
    result = preflight_research_generation(value)
    assert result["assembly_status"] == "READY_TO_COMPILE"
    assert result["canary_status"] == "CANARY_HELD"
    assert {row["code"] for row in result["canary_issues"]} == {
        "GITHUB_REPO_UNAUTHORIZED",
        "RESEARCH_SKILL_NOT_LOADED",
        "STEWARD_AUTH_MISSING",
    }


def test_source_or_snapshot_drift_refuses_instead_of_compiling() -> None:
    value = request()
    value["observed_source_commit"] = "9" * 40
    with pytest.raises(ResearchGenerationError, match="PLUGIN_SOURCE_MISMATCH"):
        preflight_research_generation(value)

    value = request()
    value["steward"]["frozen_snapshot_digest"] = "9" * 64
    with pytest.raises(ResearchGenerationError, match="APP_CONTRACT_MISMATCH"):
        preflight_research_generation(value)

def test_private_binding_can_reuse_incumbent_safe_stager(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    compiled = compile_research_binding(request())
    staged = stage_compilation(
        compiled,
        source_root=source_root,
        output_root=tmp_path / "staged",
        expected_preimage_digest="ABSENT",
    )
    assert staged.target_path.name == ".app.json"
    assert staged.target_path.read_bytes() == compiled.content
    assert staged.stage_receipt["workspace_effect_applied"] is False
    assert staged.stage_receipt["oauth_effect_applied"] is False
    assert staged.stage_receipt["production_acceptance_granted"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("display_name", "https://private.example.test"),
        ("server_name", "/Users/private/server"),
    ],
)
def test_secret_or_private_locator_shaped_app_metadata_is_refused(field: str, value: str) -> None:
    payload = request()
    payload["steward"][field] = value
    with pytest.raises(ResearchGenerationError, match="SECRET_SHAPED_INPUT"):
        preflight_research_generation(payload)


def candidate_manifest() -> dict[str, object]:
    return {
        "name": "mastermind-sol",
        "version": CANDIDATE_PLUGIN_VERSION,
        "description": "Governed Mastermind CEO workflows.",
        "author": {"name": "Mastermind-X"},
        "skills": "./skills/",
        "interface": {
            "displayName": "Mastermind CEO",
            "shortDescription": "Governed Mastermind CEO workflows",
            "longDescription": "Governed Mastermind CEO workflows for current company work.",
            "developerName": "Mastermind-X",
            "category": "Productivity",
            "capabilities": ["Read"],
        },
    }


def test_research_manifest_projection_adds_only_existing_app_reference() -> None:
    source = candidate_manifest()
    rendered = compile_research_manifest(source)
    value = json.loads(rendered)
    assert value == {**source, "apps": "./.app.json"}
    assert "mcpServers" not in value
    assert "mcp" not in value


def test_research_manifest_projection_refuses_wrong_release_or_existing_binding() -> None:
    source = candidate_manifest()
    source["version"] = "0.2.0"
    with pytest.raises(ResearchGenerationError, match="PLUGIN_IDENTITY_MISMATCH"):
        compile_research_manifest(source)

    source = candidate_manifest()
    source["apps"] = "./foreign.app.json"
    with pytest.raises(ResearchGenerationError, match="PLUGIN_IDENTITY_MISMATCH"):
        compile_research_manifest(source)


def test_missing_user_openable_citation_surface_holds_canary() -> None:
    value = request()
    value["steward"]["citation_surface_ready"] = False
    result = preflight_research_generation(value)
    assert result["assembly_status"] == "READY_TO_COMPILE"
    assert result["canary_status"] == "CANARY_HELD"
    assert {
        "code": "STEWARD_CITATION_SURFACE_MISSING",
        "logical_name": "mastermind-steward",
    } in result["canary_issues"]


@pytest.mark.parametrize("mutation", ("server_version", "tool_contract_digest"))
def test_matching_but_unaccepted_steward_contract_is_refused(mutation: str) -> None:
    value = request()
    if mutation == "server_version":
        value["steward"]["server_version"] = "9.9.9"
        value["steward"]["approved_server_version"] = "9.9.9"
    else:
        wrong = "9" * 64
        value["steward"]["tool_contract_digest"] = wrong
        value["steward"]["approved_tool_contract_digest"] = wrong
    with pytest.raises(ResearchGenerationError, match="APP_CONTRACT_MISMATCH"):
        preflight_research_generation(value)


def test_wrong_loaded_research_skill_blob_is_refused() -> None:
    value = request()
    value["plugin"]["research_skill_blob_sha"] = "9" * 40
    with pytest.raises(ResearchGenerationError, match="PLUGIN_IDENTITY_MISMATCH"):
        preflight_research_generation(value)


def test_missing_steward_app_identity_is_typed_assembly_hold() -> None:
    value = request()
    value["steward"]["app_id"] = None
    value["steward"]["approved_app_id_digest"] = None
    result = preflight_research_generation(value)
    assert result["assembly_status"] == "PREFLIGHT_HELD"
    assert {
        "code": "APP_ID_MISSING",
        "logical_name": "mastermind-steward",
    } in result["assembly_issues"]
    assert result["steward_app_id_digest"] is None
    with pytest.raises(ResearchGenerationError, match="PREFLIGHT_HELD"):
        compile_research_binding(value)
