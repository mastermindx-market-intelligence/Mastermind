"""Static no-side-effect and no-widening fences for GS-1A."""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from integrations.mastermind_secretary_mcp.adapter import SecretaryGroundingGateway
from integrations.mastermind_secretary_mcp.schemas import (
    PUBLIC_FACT_CONTRACTS,
    TOOL_SCHEMA_DIGEST,
    TOOL_SPECS,
    GatewayError,
)
from integrations.mastermind_secretary_mcp.schemas import (
    error_envelope,
    result_envelope,
    validate_result_data,
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
        "value": "SOL_REQUIRED",
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


def test_advertised_schema_and_runtime_share_one_closed_public_fact_language():
    jsonschema = pytest.importorskip("jsonschema")
    output_schema = TOOL_SPECS[2].output_schema
    validator = jsonschema.Draft202012Validator(output_schema)
    fact_schema = output_schema["properties"]["data"]["oneOf"][1]["properties"][
        "facts"
    ]["items"]
    expected_predicates = set(PUBLIC_FACT_CONTRACTS)
    assert {
        branch["properties"]["predicate"]["const"]
        for branch in fact_schema["allOf"][0]["oneOf"]
    } == expected_predicates

    source = {"owner": "agent_os", "source_ref": "WS:SAFE", "observed_at": None}
    hostile_facts = (
        {
            "subject_ref": "responsibility:alpha",
            "predicate": "runtime.host",
            "value": "Mac Studio",
            "freshness": "FRESH",
            "sources": [source],
        },
        {
            "subject_ref": "responsibility:alpha",
            "predicate": "runtime.state",
            "value": "provider:codex",
            "freshness": "FRESH",
            "sources": [source],
        },
        {
            "subject_ref": "responsibility:alpha",
            "predicate": "surface.id",
            "value": 1_700_000_000_000_000,
            "freshness": "FRESH",
            "sources": [source],
        },
    )
    for fact in hostile_facts:
        data = {"state": "FACTS", "facts": [fact], "reason_codes": []}
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(
                {
                    "schema": "mastermind.secretary_grounding_mcp_result.v1",
                    "tool": "get_attention",
                    "ok": True,
                    "server_version": "1.0.0",
                    "data": data,
                    "error": None,
                }
            )
        with pytest.raises(GatewayError, match="RESPONSE_REFUSED"):
            validate_result_data(data)


@pytest.mark.parametrize("suffix_length", [32, 40, 64, 145])
def test_advertised_and_runtime_input_contract_accept_same_opaque_refs(suffix_length):
    jsonschema = pytest.importorskip("jsonschema")
    schema = TOOL_SPECS[1].input_schema
    responsibility_ref = "responsibility:" + "a" * suffix_length
    jsonschema.Draft202012Validator(schema).validate(
        {"responsibility_ref": responsibility_ref}
    )


@pytest.mark.parametrize(
    "wrapped_credential",
    [
        "safe-ghp_abcdefghijklmnopqrstuvwxyz123456",
        "safe-sb_secret_ZmQ4Yx2Kp1Rt",
        "safe-xoxb-abcdefghijklmnopqrstuvwxyz123456",
        "safe-sk-abcdefghijklmnopqrstuvwxyz123456",
    ],
)
def test_advertised_and_runtime_input_contract_reject_wrapped_credentials(
    wrapped_credential,
):
    jsonschema = pytest.importorskip("jsonschema")
    arguments = {"responsibility_ref": "responsibility:" + wrapped_credential}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(TOOL_SPECS[1].input_schema).validate(arguments)


@pytest.mark.parametrize(
    "source_ref",
    [
        "DEC:CHAIRMAN-CONTROL-ROOM-P0-ARCHITECTURE-ACCEPTED",
        "DSC:ASD-MODEL-VISIBLE-SETTINGS-CAN-EXPOSE-LIVE-CREDENTIALS",
        "WS:" + "A" * 64,
    ],
)
def test_advertised_and_runtime_output_contract_accept_same_canonical_sources(source_ref):
    jsonschema = pytest.importorskip("jsonschema")
    data = {
        "state": "FACTS",
        "facts": [
            {
                "subject_ref": "responsibility:alpha",
                "predicate": "attention.state",
                "value": "SOL_REQUIRED",
                "freshness": "FRESH",
                "sources": [
                    {"owner": "agent_os", "source_ref": source_ref, "observed_at": None}
                ],
            }
        ],
        "reason_codes": [],
    }
    normalized = validate_result_data(data)
    envelope = result_envelope("get_attention", data=normalized)
    jsonschema.Draft202012Validator(TOOL_SPECS[2].output_schema).validate(envelope)


@pytest.mark.parametrize(
    "wrapped_credential",
    [
        "SAFE-ghp_abcdefghijklmnopqrstuvwxyz123456",
        "SAFE-eyJabcdefghijklmnopqrstuvwxyz123456",
        "SAFE-sb_secret_ZmQ4Yx2Kp1Rt",
        "SAFE-xoxb-abcdefghijklmnopqrstuvwxyz123456",
        "SAFE-sk-abcdefghijklmnopqrstuvwxyz123456",
        "SAFE-AKIAIOSFODNN7EXAMPLE",
    ],
)
def test_advertised_output_contract_rejects_wrapped_source_credentials(
    wrapped_credential,
):
    jsonschema = pytest.importorskip("jsonschema")
    envelope = {
        "schema": "mastermind.secretary_grounding_mcp_result.v1",
        "tool": "get_attention",
        "ok": True,
        "server_version": "1.0.0",
        "data": {
            "state": "FACTS",
            "facts": [
                {
                    "subject_ref": "responsibility:alpha",
                    "predicate": "attention.state",
                    "value": "SOL_REQUIRED",
                    "freshness": "FRESH",
                    "sources": [
                        {
                            "owner": "agent_os",
                            "source_ref": "DEC:" + wrapped_credential,
                            "observed_at": None,
                        }
                    ],
                }
            ],
            "reason_codes": [],
        },
        "error": None,
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(TOOL_SPECS[2].output_schema).validate(envelope)


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
