"""Static no-side-effect and no-widening fences for GS-1A."""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from integrations.mastermind_secretary_mcp.adapter import SecretaryGroundingGateway
from integrations.mastermind_secretary_mcp.schemas import TOOL_SCHEMA_DIGEST, TOOL_SPECS
from integrations.mastermind_secretary_mcp.schemas import (
    error_envelope,
    result_envelope,
)
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


def test_advertised_output_schema_matches_runtime_state_and_error_law():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(TOOL_SPECS[2].output_schema)
    source = {"owner": "agent_os", "source_ref": "WS:SAFE", "observed_at": None}
    fresh_fact = {
        "subject_ref": "responsibility:alpha",
        "predicate": "attention.state",
        "value": 1,
        "freshness": "FRESH",
        "sources": [source],
    }
    stale_fact = {**fresh_fact, "freshness": "STALE"}
    valid_data = (
        {"state": "FACTS", "facts": [fresh_fact], "reason_codes": []},
        {"state": "UNKNOWN", "facts": [], "reason_codes": ["NO_SOURCE"]},
        {
            "state": "DEGRADED",
            "facts": [stale_fact],
            "reason_codes": ["STALE_SOURCE"],
        },
        {"state": "REFUSED", "facts": [], "reason_codes": ["POLICY_REFUSAL"]},
    )
    for data in valid_data:
        validator.validate(result_envelope("get_attention", data=data))
    validator.validate(error_envelope("get_attention", "INVALID_REQUEST"))

    contradictory = error_envelope("get_attention", "INVALID_REQUEST")
    contradictory["ok"] = True
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(contradictory)

    mismatched_error = error_envelope("get_attention", "INVALID_REQUEST")
    mismatched_error["error"]["message"] = "INTERNAL_ERROR"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(mismatched_error)

    successful_error = result_envelope("get_attention", data=valid_data[0])
    successful_error["ok"] = False
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(successful_error)

    malformed_state = copy.deepcopy(successful_error)
    malformed_state["ok"] = True
    malformed_state["data"] = {
        "state": "REFUSED",
        "facts": [fresh_fact],
        "reason_codes": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(malformed_state)

    stale_facts_state = result_envelope("get_attention", data=valid_data[0])
    stale_facts_state["data"]["facts"][0]["freshness"] = "STALE"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(stale_facts_state)


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
