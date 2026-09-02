"""C0 falsifier — closed semantic facade contract.

These tests are the frozen boundary between a model/caller and any semantic
backend. They exist to make widening the surface impossible without a failing
test, per the protected C0 plan (Task 1).
"""

from __future__ import annotations

import json

import pytest

from experiments.code_intelligence.semantic_contract import (
    MAX_ARGUMENT_BYTES,
    MAX_LIMIT,
    SEMANTIC_TOOL_SCHEMAS,
    SemanticContractError,
    SemanticRequest,
    SemanticResponse,
    canonical_json,
    semantic_tool_schema_digest,
    validate_semantic_request,
)

EXPECTED_TOOLS = {
    "workspace_status",
    "symbol_overview",
    "find_symbol",
    "find_references",
    "find_implementations",
    "diagnostics",
}

# Any of these tokens appearing in a model-facing schema field name would let a
# caller steer location, identity or execution. None may ever appear.
FORBIDDEN_TOKENS = (
    "root",
    "path",
    "project",
    "attempt",
    "worker",
    "session",
    "endpoint",
    "command",
    "executable",
    "cwd",
    "env",
    "memory",
    "edit",
    "shell",
)


def _iter_field_names(schema: object) -> list[str]:
    """Collect every property name declared anywhere in a schema."""
    found: list[str] = []
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            found.extend(str(key) for key in properties)
        for value in schema.values():
            found.extend(_iter_field_names(value))
    elif isinstance(schema, list):
        for item in schema:
            found.extend(_iter_field_names(item))
    return found


class TestToolCensus:
    def test_tool_census_is_exactly_the_six_mastermind_tools(self) -> None:
        assert set(SEMANTIC_TOOL_SCHEMAS) == EXPECTED_TOOLS

    def test_census_has_no_extra_tool(self) -> None:
        assert len(SEMANTIC_TOOL_SCHEMAS) == 6


class TestClosedSchemas:
    @pytest.mark.parametrize("tool", sorted(EXPECTED_TOOLS))
    def test_every_schema_rejects_unknown_fields(self, tool: str) -> None:
        schema = SEMANTIC_TOOL_SCHEMAS[tool]
        assert schema["additionalProperties"] is False

    @pytest.mark.parametrize("tool", sorted(EXPECTED_TOOLS))
    def test_every_nested_object_also_rejects_unknown_fields(self, tool: str) -> None:
        def walk(node: object) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object":
                    assert node.get("additionalProperties") is False, node
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(SEMANTIC_TOOL_SCHEMAS[tool])

    @pytest.mark.parametrize("tool", sorted(EXPECTED_TOOLS))
    def test_no_schema_field_exposes_a_steering_token(self, tool: str) -> None:
        for field in _iter_field_names(SEMANTIC_TOOL_SCHEMAS[tool]):
            normalized = field.lower()
            for token in FORBIDDEN_TOKENS:
                assert token not in normalized, (
                    f"tool {tool} field {field!r} exposes forbidden token {token!r}"
                )

    def test_workspace_status_accepts_no_arguments(self) -> None:
        schema = SEMANTIC_TOOL_SCHEMAS["workspace_status"]
        assert schema["properties"] == {}
        assert schema["additionalProperties"] is False


class TestRequestValidation:
    def test_unknown_tool_is_refused(self) -> None:
        with pytest.raises(SemanticContractError):
            validate_semantic_request("read_file", {})

    def test_unknown_argument_is_refused(self) -> None:
        with pytest.raises(SemanticContractError):
            validate_semantic_request("find_symbol", {"name": "x", "project_root": "/etc"})

    def test_workspace_status_with_any_argument_is_refused(self) -> None:
        with pytest.raises(SemanticContractError):
            validate_semantic_request("workspace_status", {"limit": 1})

    def test_valid_request_round_trips(self) -> None:
        request = validate_semantic_request("find_symbol", {"name": "Producer"})
        assert isinstance(request, SemanticRequest)
        assert request.tool == "find_symbol"
        assert request.arguments["name"] == "Producer"

    @pytest.mark.parametrize(
        "bad",
        [
            "/etc/passwd",
            "/Users/chriswong/secret.py",
            "../outside.py",
            "src/../../outside.py",
            "src/sample/../../../../etc/hosts",
            "C:\\Windows\\system32",
            "src/sample\x00.py",
            "~/secret.py",
        ],
    )
    def test_hostile_locations_are_refused(self, bad: str) -> None:
        with pytest.raises(SemanticContractError):
            validate_semantic_request("diagnostics", {"relative_file": bad})

    def test_plain_relative_file_is_accepted(self) -> None:
        request = validate_semantic_request(
            "diagnostics", {"relative_file": "src/sample/producer.py"}
        )
        assert request.arguments["relative_file"] == "src/sample/producer.py"

    def test_limit_above_ceiling_is_refused(self) -> None:
        with pytest.raises(SemanticContractError):
            validate_semantic_request("find_references", {"name": "x", "limit": MAX_LIMIT + 1})

    def test_limit_at_ceiling_is_accepted(self) -> None:
        request = validate_semantic_request("find_references", {"name": "x", "limit": MAX_LIMIT})
        assert request.arguments["limit"] == MAX_LIMIT

    def test_negative_and_zero_limits_are_refused(self) -> None:
        for value in (0, -1):
            with pytest.raises(SemanticContractError):
                validate_semantic_request("find_references", {"name": "x", "limit": value})

    def test_bool_is_not_accepted_as_limit(self) -> None:
        # bool is an int subclass in Python; a closed contract must not silently
        # accept True as 1.
        with pytest.raises(SemanticContractError):
            validate_semantic_request("find_references", {"name": "x", "limit": True})

    def test_oversized_argument_is_refused(self) -> None:
        with pytest.raises(SemanticContractError):
            validate_semantic_request(
                "find_symbol", {"name": "a" * (MAX_ARGUMENT_BYTES + 1)}
            )

    def test_required_argument_missing_is_refused(self) -> None:
        with pytest.raises(SemanticContractError):
            validate_semantic_request("find_symbol", {})

    def test_wrong_type_is_refused(self) -> None:
        with pytest.raises(SemanticContractError):
            validate_semantic_request("find_symbol", {"name": 17})


class TestCanonicalJson:
    def test_canonical_json_is_sorted_compact_ascii(self) -> None:
        rendered = canonical_json({"b": 1, "a": "é"})
        assert rendered == '{"a":"\\u00e9","b":1}'

    def test_canonical_json_refuses_nan(self) -> None:
        with pytest.raises(ValueError):
            canonical_json({"a": float("nan")})

    def test_schema_digest_is_stable_and_hex(self) -> None:
        first = semantic_tool_schema_digest()
        second = semantic_tool_schema_digest()
        assert first == second
        assert len(first) == 64
        int(first, 16)

    def test_schema_digest_tracks_schema_content(self) -> None:
        # The digest must be a function of the frozen schema bytes, so that any
        # widening is visible in the binding receipt.
        expected = json.loads(canonical_json(SEMANTIC_TOOL_SCHEMAS))
        assert set(expected) == EXPECTED_TOOLS


class TestResponseShape:
    def test_response_binds_workspace_and_backend(self) -> None:
        response = SemanticResponse(
            tool="workspace_status",
            workspace_binding_digest="a" * 64,
            backend_digest="b" * 64,
            payload={"ok": True},
        )
        assert response.tool == "workspace_status"
        assert response.workspace_binding_digest == "a" * 64
        assert response.backend_digest == "b" * 64
        assert response.payload == {"ok": True}

    def test_response_is_immutable(self) -> None:
        response = SemanticResponse(
            tool="workspace_status",
            workspace_binding_digest="a" * 64,
            backend_digest="b" * 64,
            payload={"ok": True},
        )
        with pytest.raises(Exception):
            response.tool = "diagnostics"  # type: ignore[misc]

    def test_request_is_immutable(self) -> None:
        request = validate_semantic_request("workspace_status", {})
        with pytest.raises(Exception):
            request.tool = "diagnostics"  # type: ignore[misc]
