"""Static no-side-effect and no-widening fences for GS-1A."""

from __future__ import annotations

import ast
from pathlib import Path

from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from integrations.mastermind_secretary_mcp.adapter import SecretaryGroundingGateway
from integrations.mastermind_secretary_mcp.schemas import TOOL_SCHEMA_DIGEST, TOOL_SPECS
from integrations.mastermind_secretary_mcp.server import (
    STATIC_CAPABILITIES,
    SecretaryGroundingContractServer,
    build_tools,
)

PACKAGE = Path(__file__).parents[1] / "integrations" / "mastermind_secretary_mcp"
FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "control_plane",
    "github",
    "httpx",
    "integrations.slack_agent_dialogue",
    "linear",
    "mcp",
    "openclaw",
    "requests",
    "socket",
    "sqlite3",
    "subprocess",
    "urllib",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_sdk_free_static_tool_rows_are_exact_and_read_only():
    tools = build_tools()
    assert [row["name"] for row in tools] == [spec.name for spec in TOOL_SPECS]
    assert len(tools) == 6
    assert all(row["annotations"]["readOnlyHint"] is True for row in tools)
    assert all(row["annotations"]["destructiveHint"] is False for row in tools)
    assert all(row["inputSchema"]["additionalProperties"] is False for row in tools)
    assert all(row["outputSchema"]["additionalProperties"] is False for row in tools)
    assert STATIC_CAPABILITIES == {
        "tools": True,
        "resources": False,
        "prompts": False,
        "roots": False,
        "sampling": False,
        "elicitation": False,
        "dynamic_registration": False,
    }
    assert len(TOOL_SCHEMA_DIGEST) == 64
    observed = {"tools": {row["name"]: row for row in tools}}
    assert observed_mcp_tool_schema_digest(observed) == TOOL_SCHEMA_DIGEST


def test_static_contract_server_exposes_only_list_and_call():
    public = {
        name
        for name in dir(SecretaryGroundingContractServer)
        if not name.startswith("_")
    }
    assert public == {"call_tool", "list_tools"}
    assert SecretaryGroundingContractServer.__annotations__ == {}
    assert SecretaryGroundingContractServer.__doc__


def test_production_package_has_no_owner_transport_sdk_or_side_effect_imports():
    imports = set().union(*(_imports(path) for path in PACKAGE.glob("*.py")))
    for imported in imports:
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORT_ROOTS
        ), imported

    rendered = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(PACKAGE.glob("*.py"))
    )
    forbidden_fragments = (
        "FakeSteward",
        "open(",
        ".read_text(",
        ".write_text(",
        "list_resources(",
        "list_prompts(",
        "list_roots(",
        "create_job",
        "requeue_job",
        "send_message",
        "computer_control",
        "shell(command",
        "dynamic_tool",
    )
    for fragment in forbidden_fragments:
        assert fragment not in rendered


def test_test_fake_is_not_reachable_from_production_package():
    assert not any("fake" in path.name.lower() for path in PACKAGE.glob("*.py"))
    assert not any(
        imported == "tests" or imported.startswith("tests.")
        for path in PACKAGE.glob("*.py")
        for imported in _imports(path)
    )
    assert SecretaryGroundingGateway.__module__.startswith(
        "integrations.mastermind_secretary_mcp"
    )
