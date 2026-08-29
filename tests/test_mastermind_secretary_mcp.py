"""Frozen GS-1A Secretary grounding MCP contract tests."""

from integrations.mastermind_secretary_mcp.schemas import TOOL_SPECS


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
