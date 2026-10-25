"""Offline compatibility guard for Hermes consuming the INCUMBENT six Steward reads.

This is not an MCP server, authentication layer, router, registry, admission
source or substitute for the existing Steward service. No network, model,
credentials, file-system writes or company Job/Attempt effects occur here.
Passing means only that one in-memory advertisement matches the current source
contract; runtime authorization must be enforced by the receiving Steward MCP.
"""

from __future__ import annotations

import json
from typing import Any

from integrations.mastermind_secretary_mcp.schemas import SERVER_GENERATION, SERVER_VERSION
from integrations.mastermind_secretary_mcp.server import STATIC_CAPABILITIES, build_tools

SCHEMA = "mastermind.hermes_steward_source_compatibility.v1"

# This six-name witness intentionally does not replace the owning build_tools().
# A new or renamed company tool is a new authority review, never auto-approved.
EXPECTED_NAMES = (
    "list_responsibilities",
    "get_responsibility",
    "get_attention",
    "get_current_runtime",
    "explain_blocker",
    "resolve_surface",
)
EXPECTED_CAPABILITIES = {
    "tools": True,
    "resources": False,
    "prompts": False,
    "roots": False,
    "sampling": False,
    "elicitation": False,
    "dynamic_registration": False,
}
MAX_ADVERTISEMENT_BYTES = 1024 * 1024  # Upper cap for actual owner-generated closed schema
MAX_ADVERTISEMENT_OVERAGE_BYTES = 4096  # Drift headroom, not an authority grant


def inspect_advertisement(advertised: object) -> dict[str, Any]:
    """Compare supplied JSON-compatible MCP Tool rows to the source owner.

    A malicious or changed advertisement is refused without reflecting its
    values, URLs, tokens, extra tool names or descriptions in the result.
    """
    errors: set[str] = set()
    expected: list[dict[str, object]] = []
    try:
        expected = build_tools()
    except Exception:
        errors.add("OWNER_CONTRACT_UNAVAILABLE")
    if SERVER_VERSION != "2.0.0" or SERVER_GENERATION != 2:
        errors.add("OWNER_GENERATION_UNQUALIFIED")
    if STATIC_CAPABILITIES != EXPECTED_CAPABILITIES:
        errors.add("OWNER_CAPABILITIES_CHANGED")
    if tuple(item.get("name") for item in expected) != EXPECTED_NAMES:
        errors.add("OWNER_TOOL_SET_CHANGED")

    for item in expected:
        annotations = item.get("annotations")
        inputs = item.get("inputSchema")
        if not isinstance(annotations, dict) or (
            annotations.get("readOnlyHint") is not True
            or annotations.get("destructiveHint") is not False
            or annotations.get("idempotentHint") is not True
            or annotations.get("openWorldHint") is not False
        ):
            errors.add("OWNER_READ_ONLY_FENCE_CHANGED")
        if not isinstance(inputs, dict) or inputs.get("additionalProperties") is not False:
            errors.add("OWNER_INPUT_BOUNDARY_CHANGED")

    if not isinstance(advertised, list) or len(advertised) != len(EXPECTED_NAMES):
        errors.add("ADVERTISED_TOOL_SET_INVALID")
    else:
        names = [row.get("name") if isinstance(row, dict) else None for row in advertised]
        if tuple(names) != EXPECTED_NAMES:
            errors.add("ADVERTISED_TOOL_SET_INVALID")
        try:
            encoded = json.dumps(advertised, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
            current = json.dumps(expected, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        except (TypeError, ValueError, OverflowError, RecursionError):
            errors.add("ADVERTISED_SHAPE_INVALID")
        else:
            # The reviewed six-tool owner expands to a substantial nested
            # JSON Schema. Base the advertisement allowance on *that exact
            # canonical source*, not an undersized arbitrary fixed threshold.
            # The independent hard ceiling still refuses unexpected growth.
            source_size = len(current.encode("utf-8"))
            candidate_size = len(encoded.encode("utf-8"))
            if source_size > MAX_ADVERTISEMENT_BYTES:
                errors.add("OWNER_ADVERTISEMENT_TOO_LARGE")
            permitted_size = min(MAX_ADVERTISEMENT_BYTES, source_size + MAX_ADVERTISEMENT_OVERAGE_BYTES)
            if candidate_size > permitted_size:
                errors.add("ADVERTISED_SIZE_EXCEEDED")
            if encoded != current:
                errors.add("ADVERTISED_SOURCE_DRIFT")

    return {
        "schema": SCHEMA,
        "status": "REFUSED" if errors else "PASS_SOURCE_CONTRACT_ONLY",
        "source_owner": "mastermind_secretary_mcp",
        "source_generation": SERVER_GENERATION,
        "tool_names": list(EXPECTED_NAMES),
        "issues": sorted(errors),
        "mcp_server_connected": False,
        "identity_or_authority_granted": False,
        "steward_live_data_read": False,
        "provider_or_model_called": False,
        "runtime_tools_admitted": False,
    }


__all__ = ["EXPECTED_NAMES", "inspect_advertisement"]
