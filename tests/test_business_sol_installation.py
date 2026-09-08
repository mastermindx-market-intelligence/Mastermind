from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from integrations.business_sol_installation import (
    FILE_MODE,
    InstallationContractError,
    compile_installation_bindings,
    preflight_installation,
    rollback_staged_compilation,
    stage_compilation,
    verify_staged_compilation,
)

SOURCE_COMMIT = "a" * 40
PACKAGE_DIGEST = "b" * 64
WORKSPACE_DIGEST = "c" * 64
RESOURCE_DIGEST = "d" * 64
OAUTH_DIGEST = "e" * 64
PLUGIN_ID = "Plugin_" + "1" * 32
STEWARD_ID = "asdk_app_" + "2" * 32
EXECUTIVE_ID = "asdk_app_" + "3" * 32


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def template() -> dict[str, object]:
    return {
        "schema": "mastermind.plugin_app_bindings_template.v1",
        "plugin": "mastermind-sol",
        "plugin_version": "0.1.0",
        "generated_file": ".app.json",
        "generated_by_wave": "BSC-U1",
        "bindings": [
            {
                "logical_name": "mastermind-steward",
                "required": True,
                "contract_owner": "integrations/mastermind_secretary_mcp/schemas.py",
                "app_id": None,
            },
            {
                "logical_name": "mastermind-executive",
                "required": True,
                "contract_owner": "integrations/executive_mcp/schemas.py",
                "app_id": None,
            },
        ],
    }


def app(logical_name: str) -> dict[str, object]:
    if logical_name == "mastermind-steward":
        app_id = STEWARD_ID
        display_name = "Mastermind Steward"
        server_name = "mastermind-steward"
        server_version = "2.0.0"
        tool_names = [
            "list_responsibilities",
            "get_responsibility",
            "get_attention",
            "get_current_runtime",
            "explain_blocker",
            "resolve_surface",
        ]
        tool_digest = "cde13b7d678427a230cfe40159be1d7aa0807df00324995a40d89b2b79c12047"
    else:
        app_id = EXECUTIVE_ID
        display_name = "Mastermind Executive"
        server_name = "mastermind-executive"
        server_version = "1.0.0"
        tool_names = [
            "executive_state",
            "executive_inbox",
            "executive_job",
            "ceo_intent_status",
            "submit_ceo_intent",
        ]
        tool_digest = "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
    return {
        "logical_name": logical_name,
        "app_id": app_id,
        "approved_app_id_digest": digest_text(app_id),
        "display_name": display_name,
        "workspace_digest": WORKSPACE_DIGEST,
        "scope": "WORKSPACE",
        "publication_state": "PUBLISHED",
        "app_generation": logical_name + "-g1",
        "approved_app_generation": logical_name + "-g1",
        "server_name": server_name,
        "server_version": server_version,
        "resource_digest": RESOURCE_DIGEST,
        "approved_resource_digest": RESOURCE_DIGEST,
        "oauth_policy_digest": OAUTH_DIGEST,
        "approved_oauth_policy_digest": OAUTH_DIGEST,
        "tool_names": tool_names,
        "tool_contract_digest": tool_digest,
        "status": "ENABLED",
        "availability": "AVAILABLE",
        "installed": False,
        "connected": False,
    }


def request() -> dict[str, object]:
    return {
        "schema": "mastermind.business_sol_installation_request.v1",
        "generation": 1,
        "source_commit": SOURCE_COMMIT,
        "observed_source_commit": SOURCE_COMMIT,
        "plugin_package_digest": PACKAGE_DIGEST,
        "observed_plugin_package_digest": PACKAGE_DIGEST,
        "workspace_digest": WORKSPACE_DIGEST,
        "workspace_role": "OWNER",
        "plugin": {
            "name": "mastermind-sol",
            "version": "0.1.0",
            "registry_id": PLUGIN_ID,
            "approved_registry_id_digest": digest_text(PLUGIN_ID),
            "display_name": "Mastermind Sol",
            "scope": "WORKSPACE",
            "status": "ENABLED",
            "installation_policy": "INSTALLED_BY_DEFAULT",
            "scanned_generation": "mastermind-sol-g1",
            "approved_scanned_generation": "mastermind-sol-g1",
            "installed": False,
        },
        "apps": [app("mastermind-steward"), app("mastermind-executive")],
    }


def test_complete_preflight_and_compile_are_deterministic() -> None:
    first_request = request()
    second_request = request()
    second_request["apps"] = list(reversed(second_request["apps"]))

    preflight = preflight_installation(template(), first_request)
    assert preflight["status"] == "READY_TO_COMPILE"
    assert preflight["issues"] == []
    assert preflight["binding_document_digest"] is None
    assert preflight["production_acceptance_granted"] is False

    first = compile_installation_bindings(template(), first_request)
    second = compile_installation_bindings(template(), second_request)
    assert first.content == second.content
    assert first.binding_digest == second.binding_digest
    assert first.public_receipt == second.public_receipt
    assert first.public_receipt["logical_bindings"] == [
        "mastermind-steward",
        "mastermind-executive",
    ]
    assert first.public_receipt["workspace_effect_applied"] is False
    assert first.public_receipt["oauth_effect_applied"] is False
    assert first.public_receipt["production_acceptance_granted"] is False

    rendered = json.loads(first.content)
    assert rendered == {"apps": {
        "mastermind-steward": {"id": STEWARD_ID, "required": True},
        "mastermind-executive": {"id": EXECUTIVE_ID, "required": True},
    }}
    assert PLUGIN_ID not in first.content.decode()
    assert len(first.public_receipt["installation_plan_digest"]) == 64
    public = json.dumps(first.public_receipt, sort_keys=True)
    assert PLUGIN_ID not in public
    assert STEWARD_ID not in public
    assert EXECUTIVE_ID not in public


def test_missing_steward_is_truthful_preflight_hold() -> None:
    value = request()
    value["apps"] = [app("mastermind-executive")]
    result = preflight_installation(template(), value)
    assert result["status"] == "PREFLIGHT_HELD"
    assert result["issues"] == [
        {"code": "REQUIRED_BINDING_MISSING", "logical_name": "mastermind-steward"}
    ]
    assert result["binding_document_digest"] is None
    with pytest.raises(InstallationContractError, match="PREFLIGHT_HELD"):
        compile_installation_bindings(template(), value)


def test_stage_verify_and_rollback_absent_preimage(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    output_root = tmp_path / "staging"
    source_root.mkdir()
    compilation = compile_installation_bindings(template(), request())

    stage = stage_compilation(
        compilation,
        output_root=output_root,
        source_root=source_root,
        expected_preimage_digest="ABSENT",
    )
    target = output_root / ".app.json"
    assert target.read_bytes() == compilation.content
    assert target.stat().st_mode & 0o777 == FILE_MODE
    assert stage.stage_receipt["status"] == "STAGED_VERIFIED"
    assert stage.rollback_manifest["prior_state"] == "ABSENT"
    assert str(target) not in json.dumps(stage.stage_receipt)

    readback = verify_staged_compilation(
        compilation,
        output_root=output_root,
        source_root=source_root,
    )
    assert readback["status"] == "READBACK_VERIFIED"

    rollback = rollback_staged_compilation(stage)
    assert rollback["status"] == "ROLLBACK_VERIFIED"
    assert rollback["restored_state"] == "ABSENT"
    assert not target.exists()


def test_stage_verify_and_rollback_present_preimage(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    output_root = tmp_path / "staging"
    source_root.mkdir()
    output_root.mkdir()
    target = output_root / ".app.json"
    prior = b'{"prior":true}\n'
    target.write_bytes(prior)
    target.chmod(0o640)
    compilation = compile_installation_bindings(template(), request())

    stage = stage_compilation(
        compilation,
        output_root=output_root,
        source_root=source_root,
        expected_preimage_digest=hashlib.sha256(prior).hexdigest(),
    )
    rollback_staged_compilation(stage)
    assert target.read_bytes() == prior
    assert target.stat().st_mode & 0o777 == 0o640


def test_changed_postimage_blocks_rollback(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    output_root = tmp_path / "staging"
    source_root.mkdir()
    compilation = compile_installation_bindings(template(), request())
    stage = stage_compilation(
        compilation,
        output_root=output_root,
        source_root=source_root,
        expected_preimage_digest="ABSENT",
    )
    stage.target_path.write_text("foreign\n", encoding="utf-8")
    with pytest.raises(InstallationContractError, match="PREIMAGE_CONFLICT"):
        rollback_staged_compilation(stage)

# Source-backed boundary witness: the S1 app (not its inner contract server)
# constructs MCP Server(SERVER_NAME, version=SERVER_VERSION) with these values.
# Mastermind PR #463 @ 7ffc3821004ab4bf4a63d56f88d18cb5165424d6
# integrations/mastermind_steward_app/server.py
# Git blob: a18ed8991ad19a1cdc55767d60d824fb2ca6d3e9
# Other workspace/app facts below are synthetic controls, not live observations.
def test_steward_app_advertisement_is_accepted_by_u1_preflight() -> None:
    value = request()
    value["apps"][0]["server_name"] = "mastermind-steward"
    value["apps"][0]["server_version"] = "2.0.0"
    result = preflight_installation(template(), value)
    assert result["status"] == "READY_TO_COMPILE"
    assert result["issues"] == []
    assert result["workspace_effect_applied"] is False
    assert result["oauth_effect_applied"] is False
    assert result["production_acceptance_granted"] is False


def test_steward_app_advertisement_is_preserved_in_compiled_binding() -> None:
    value = request()
    value["apps"][0]["server_name"] = "mastermind-steward"
    value["apps"][0]["server_version"] = "2.0.0"
    first = compile_installation_bindings(template(), value)
    second = compile_installation_bindings(template(), value)
    assert first.content == second.content
    document = json.loads(first.content)
    assert document["apps"]["mastermind-steward"] == {
        "id": STEWARD_ID, "required": True,
    }
    # Preflight above still verifies exact server name, version and tools;
    # the native file contains no server metadata. Bind it in receipt evidence.
    assert len(first.public_receipt["installation_plan_digest"]) == 64
    assert first.public_receipt["workspace_effect_applied"] is False
    assert first.public_receipt["oauth_effect_applied"] is False
    assert first.public_receipt["production_acceptance_granted"] is False


@pytest.mark.parametrize("bad_name", [
    "mastermind-secretary-grounding",  # The inner contract is not the app identity.
    "mastermind-executive",           # No cross-app substitution.
    "mastermind-steward-unknown",      # No permissive prefix/alias matching.
])
def test_steward_app_binding_refuses_inner_or_foreign_server_name(bad_name: str) -> None:
    value = request()
    value["apps"][0]["server_name"] = bad_name
    with pytest.raises(InstallationContractError, match="APP_CONTRACT_MISMATCH"):
        preflight_installation(template(), value)
    with pytest.raises(InstallationContractError, match="APP_CONTRACT_MISMATCH"):
        compile_installation_bindings(template(), value)


@pytest.mark.parametrize("changed_field,bad_value", [
    ("server_version", "1.0.0"),
    ("tool_contract_digest", "0" * 64),
    ("tool_names", ["list_responsibilities"]),
])
def test_steward_app_name_does_not_relax_generation_or_tool_contract(
    changed_field: str, bad_value: object,
) -> None:
    value = request()
    value["apps"][0]["server_name"] = "mastermind-steward"
    value["apps"][0][changed_field] = bad_value
    with pytest.raises(InstallationContractError, match="APP_CONTRACT_MISMATCH"):
        compile_installation_bindings(template(), value)


# Current first-party format witness, inspected 2026-09-05:
# https://learn.chatgpt.com/docs/enterprise/plugin-management
# "Reference an existing app with .app.json". These tests use synthetic
# identities and our deliberately strict projection of that documented shape;
# they are not an execution of OpenAI's private importer.
def native_request() -> dict[str, object]:
    value = request()
    for row in value["apps"]:
        raw = row["app_id"]
        if raw.startswith("plugin_asdk_app_"):
            raw = raw[len("plugin_"):]
        row["app_id"] = raw
        row["approved_app_id_digest"] = digest_text(raw)
    return value


def test_native_document_is_the_documented_apps_reference_shape() -> None:
    compilation = compile_installation_bindings(template(), native_request())
    expected = {"apps": {
        "mastermind-steward": {"id": "asdk_app_" + "2" * 32, "required": True},
        "mastermind-executive": {"id": "asdk_app_" + "3" * 32, "required": True},
    }}
    assert json.loads(compilation.content) == expected
    assert compilation.document == expected
    assert compilation.binding_digest == hashlib.sha256(compilation.content).hexdigest()


def test_native_output_does_not_mix_private_plan_into_app_reference() -> None:
    compilation = compile_installation_bindings(template(), native_request())
    native = json.loads(compilation.content)
    assert set(native) == {"apps"}
    assert PLUGIN_ID not in compilation.content.decode()
    assert "workspace_digest" not in native
    assert "bindings" not in native
    assert compilation.public_receipt["schema"] == "mastermind.business_sol_installation_receipt.v2"
    assert len(compilation.public_receipt["installation_plan_digest"]) == 64
    assert compilation.public_receipt["binding_document_digest"] == compilation.binding_digest


@pytest.mark.parametrize("bad_id", [
    "plugin_asdk_app_" + "2" * 32,
    "Plugin_" + "2" * 32,
    "plugin_connector_" + "2" * 32,
])
def test_native_compilation_refuses_plugin_identifiers_even_with_matching_digest(bad_id) -> None:
    value = native_request()
    value["apps"][0]["app_id"] = bad_id
    value["apps"][0]["approved_app_id_digest"] = digest_text(bad_id)
    with pytest.raises(InstallationContractError, match="APP_IDENTITY_MISMATCH"):
        compile_installation_bindings(template(), value)


def test_native_bytes_are_stable_but_evidence_binds_approved_generation() -> None:
    first = native_request()
    second = native_request()
    second["apps"][0]["app_generation"] = "mastermind-steward-g2"
    second["apps"][0]["approved_app_generation"] = "mastermind-steward-g2"
    a = compile_installation_bindings(template(), first)
    b = compile_installation_bindings(template(), second)
    assert a.content == b.content
    assert a.public_receipt["installation_plan_digest"] != b.public_receipt["installation_plan_digest"]
    assert a.public_receipt["binding_document_digest"] == b.public_receipt["binding_document_digest"]


def test_native_stage_readback_and_rollback_keep_zero_workspace_effects(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    compilation = compile_installation_bindings(template(), native_request())
    result = stage_compilation(compilation, source_root=source,
        output_root=tmp_path / "staged", expected_preimage_digest="ABSENT")
    assert set(json.loads(result.target_path.read_bytes())) == {"apps"}
    assert verify_staged_compilation(compilation, source_root=source,
        output_root=tmp_path / "staged")["status"] == "READBACK_VERIFIED"
    for receipt in (compilation.public_receipt, result.stage_receipt):
        assert receipt["workspace_effect_applied"] is False
        assert receipt["oauth_effect_applied"] is False
        assert receipt["production_acceptance_granted"] is False
    assert rollback_staged_compilation(result)["status"] == "ROLLBACK_VERIFIED"
    assert not result.target_path.exists()


def test_native_conversion_preserves_missing_required_app_refusal() -> None:
    value = native_request()
    value["apps"] = [value["apps"][1]]
    assert preflight_installation(template(), value)["status"] == "PREFLIGHT_HELD"
    with pytest.raises(InstallationContractError, match="PREFLIGHT_HELD"):
        compile_installation_bindings(template(), value)
