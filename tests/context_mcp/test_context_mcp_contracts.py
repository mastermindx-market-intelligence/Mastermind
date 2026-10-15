from __future__ import annotations

import ast
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from integrations.context_mcp.contracts import (
    INPUT_SCHEMAS,
    RESULT_SCHEMA,
    TOOL_DESCRIPTIONS,
    TOOL_NAMES,
)


def test_exact_tool_surface_is_closed():
    assert TOOL_NAMES == (
        "resolve_context",
        "expand_context",
        "diff_context",
        "atlas_search",
        "workspace_overlay",
    )
    assert set(INPUT_SCHEMAS) == set(TOOL_NAMES)
    assert set(TOOL_DESCRIPTIONS) == set(TOOL_NAMES)


def test_all_input_and_result_schemas_are_valid_json_schema():
    for schema in INPUT_SCHEMAS.values():
        Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(RESULT_SCHEMA)


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_all_tool_inputs_reject_unknown_keys(name):
    assert INPUT_SCHEMAS[name]["additionalProperties"] is False


def test_resolve_context_is_bounded_and_has_no_root_path_or_command_inputs():
    schema = INPUT_SCHEMAS["resolve_context"]
    properties = schema["properties"]
    assert properties["max_items"]["maximum"] == 64
    assert properties["task"]["maxLength"] == 8192
    assert properties["workstreams"]["maxItems"] == 16
    assert properties["repositories"]["maxItems"] == 16
    assert set(properties).isdisjoint(
        {
            "root",
            "path",
            "workspace_path",
            "source_repo",
            "command",
            "argv",
            "token",
            "credential",
            "url",
        }
    )


def test_workspace_overlay_cannot_select_lane_or_filesystem_path():
    properties = INPUT_SCHEMAS["workspace_overlay"]["properties"]
    assert set(properties) == {"project_ref", "operation_id"}


def test_atlas_search_cannot_supply_cache_or_repo_root():
    properties = INPUT_SCHEMAS["atlas_search"]["properties"]
    assert "repository" in properties
    assert "revision" in properties
    assert set(properties).isdisjoint({"cache_root", "repo_root", "path", "command"})


def test_app_source_reuses_business_auth_and_has_no_direct_io_runtime_imports():
    source = (
        Path(__file__).parents[2] / "integrations" / "context_mcp" / "app.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert any(
        module.startswith("integrations.business_mcp_auth")
        for module in imported_modules
    )
    forbidden = {
        "os",
        "pathlib",
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "time",
        "random",
    }
    assert not any(module.split(".", 1)[0] in forbidden for module in imported_modules)


def test_app_source_marks_every_tool_read_only():
    source = (
        Path(__file__).parents[2] / "integrations" / "context_mcp" / "app.py"
    ).read_text(encoding="utf-8")
    assert "readOnlyHint=True" in source
    assert "destructiveHint=False" in source
    assert "openWorldHint=False" in source
    assert "stateless_http=True" in source


def test_result_envelope_has_no_authority_or_execution_fields():
    properties = RESULT_SCHEMA["properties"]
    assert set(properties).isdisjoint(
        {
            "authorized",
            "permission",
            "lease",
            "runtime_binding",
            "execute",
            "write",
            "credential",
            "token",
        }
    )
