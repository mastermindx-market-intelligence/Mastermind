"""Frozen GS-1A Secretary grounding MCP contract tests."""

import copy
import json

import pytest

from integrations.mastermind_secretary_mcp.schemas import (
    MAX_REQUEST_BYTES,
    SCHEMA_SNAPSHOT_SHA256,
    TOOL_SCHEMA_DIGEST,
    TOOL_SPECS,
    GatewayError,
    canonical_json,
    schema_snapshot,
    schema_snapshot_sha256,
    tool_schema_digest,
    validate_tool_arguments,
)
from integrations.mastermind_secretary_mcp.server import build_tools


EXPECTED_TOOLS = (
    "list_responsibilities",
    "get_responsibility",
    "get_attention",
    "get_current_runtime",
    "explain_blocker",
    "resolve_surface",
)


def test_exact_six_tool_census_is_read_only():
    assert tuple(spec.name for spec in TOOL_SPECS) == EXPECTED_TOOLS
    assert all(spec.read_only for spec in TOOL_SPECS)
    assert all(spec.annotations["readOnlyHint"] is True for spec in TOOL_SPECS)


def test_model_visible_inputs_are_closed_and_action_identity_free():
    expected_properties = {
        "list_responsibilities": set(),
        "get_responsibility": {"responsibility_ref"},
        "get_attention": set(),
        "get_current_runtime": {"responsibility_ref"},
        "explain_blocker": {"responsibility_ref"},
        "resolve_surface": {"responsibility_ref"},
    }
    forbidden = {
        "provider",
        "account",
        "host",
        "native_session",
        "session",
        "browser_profile",
        "profile",
        "channel",
        "thread",
        "url",
        "coordinate",
        "coordinates",
        "target",
        "action",
        "purpose",
        "surface_ref",
    }

    for spec in TOOL_SPECS:
        schema = spec.input_schema
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["properties"]) == expected_properties[spec.name]
        assert not (set(schema["properties"]) & forbidden)
        expected_required = ["responsibility_ref"] if expected_properties[spec.name] else []
        assert schema.get("required", []) == expected_required


@pytest.mark.parametrize("tool_name", EXPECTED_TOOLS)
@pytest.mark.parametrize(
    "smuggled_field",
    [
        "provider",
        "account",
        "host",
        "native_session",
        "browser_profile",
        "channel",
        "thread",
        "url",
        "coordinates",
        "target",
        "action",
        "purpose",
        "surface_ref",
    ],
)
def test_identity_and_action_smuggling_fail_closed(tool_name, smuggled_field):
    arguments = {smuggled_field: "attacker-selected"}
    if tool_name not in {"list_responsibilities", "get_attention"}:
        arguments["responsibility_ref"] = "responsibility:alpha"
    with pytest.raises(GatewayError, match="INVALID_REQUEST"):
        validate_tool_arguments(tool_name, arguments)


def test_request_size_and_responsibility_ref_are_bounded():
    assert MAX_REQUEST_BYTES <= 8 * 1024
    with pytest.raises(GatewayError, match="INVALID_REQUEST"):
        validate_tool_arguments(
            "get_responsibility",
            {"responsibility_ref": "r" * (MAX_REQUEST_BYTES + 1)},
        )
    with pytest.raises(GatewayError, match="INVALID_REQUEST"):
        validate_tool_arguments("get_responsibility", {"responsibility_ref": "latest window"})


@pytest.mark.parametrize(
    "smuggled_ref",
    [
        "https://attacker.example/path",
        "provider:codex",
        "account:chairman",
        "host:Mac-Studio.local",
        "native_session:session-123",
        "browser_profile:Chairman",
        "channel:C123/thread:1700000000.000000",
        "coordinates:120-300",
        "action:send/target:production",
    ],
)
def test_selector_value_smuggling_is_not_a_responsibility_reference(smuggled_ref):
    with pytest.raises(GatewayError, match="INVALID_REQUEST"):
        validate_tool_arguments(
            "get_responsibility", {"responsibility_ref": smuggled_ref}
        )


@pytest.mark.parametrize("suffix_length", [32, 40, 64, 145])
def test_canonical_opaque_responsibility_refs_accept_full_declared_range(suffix_length):
    responsibility_ref = "responsibility:" + "a" * suffix_length
    assert validate_tool_arguments(
        "get_responsibility", {"responsibility_ref": responsibility_ref}
    ) == {"responsibility_ref": responsibility_ref}


def test_fact_value_schema_has_no_overlapping_one_of_numeric_branches():
    fact_schema = TOOL_SPECS[0].output_schema["properties"]["data"]["oneOf"][1][
        "properties"
    ]["facts"]["items"]
    predicate_schemas = {
        branch["properties"]["predicate"]["const"]: branch["properties"]["value"]
        for branch in fact_schema["allOf"][0]["oneOf"]
    }

    assert predicate_schemas["responsibility.priority"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
    }
    assert "oneOf" not in predicate_schemas["responsibility.priority"]


def test_live_schema_views_cannot_widen_the_canonical_contract():
    before_digest = tool_schema_digest()
    exposed = TOOL_SPECS[1].input_schema
    original = copy.deepcopy(exposed)
    try:
        exposed["properties"]["provider"] = {"type": "string"}
        exposed["required"].append("provider")

        assert "provider" not in TOOL_SPECS[1].input_schema["properties"]
        assert "provider" not in build_tools()[1]["inputSchema"]["properties"]
        assert tool_schema_digest() == before_digest == TOOL_SCHEMA_DIGEST
        with pytest.raises(GatewayError, match="INVALID_REQUEST"):
            validate_tool_arguments(
                "get_responsibility",
                {"responsibility_ref": "responsibility:alpha", "provider": "codex"},
            )
    finally:
        exposed.clear()
        exposed.update(original)


def test_static_schema_snapshot_and_digests_are_literal_and_drift_sensitive():
    assert schema_snapshot_sha256() == SCHEMA_SNAPSHOT_SHA256
    assert tool_schema_digest() == TOOL_SCHEMA_DIGEST
    assert len(SCHEMA_SNAPSHOT_SHA256) == 64
    assert len(TOOL_SCHEMA_DIGEST) == 64

    snapshot = schema_snapshot()
    assert [tool["name"] for tool in snapshot["tools"]] == list(EXPECTED_TOOLS)
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in snapshot["tools"])

    widened = copy.deepcopy(snapshot)
    widened["tools"][0]["input_schema"]["properties"]["provider"] = {
        "type": "string"
    }
    assert canonical_json(widened) != canonical_json(snapshot)
    assert json.loads(canonical_json(snapshot))["tools"][0]["name"] == EXPECTED_TOOLS[0]
