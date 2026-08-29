"""Stable, SDK-free contracts for the Mastermind company-dialogue MCP facade."""

from integrations.mastermind_company_mcp.adapter import (
    CompanyDialogueGateway,
    DialogueBinding,
    DialogueBindingResolver,
)
from integrations.mastermind_company_mcp.schemas import (
    RESULT_SCHEMA,
    SCHEMA_SNAPSHOT_SHA256,
    SERVER_IDENTITY,
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_SCHEMA_DIGEST,
    TOOL_SPECS,
    GatewayError,
    ToolSpec,
    error_envelope,
    result_envelope,
    schema_snapshot_sha256,
    tool_schema_digest,
    tool_schema_snapshot,
    validate_tool_arguments,
)

__all__ = [
    "CompanyDialogueGateway",
    "DialogueBinding",
    "DialogueBindingResolver",
    "GatewayError",
    "RESULT_SCHEMA",
    "SCHEMA_SNAPSHOT_SHA256",
    "SERVER_IDENTITY",
    "SERVER_NAME",
    "SERVER_VERSION",
    "TOOL_SCHEMA_DIGEST",
    "TOOL_SPECS",
    "ToolSpec",
    "error_envelope",
    "result_envelope",
    "schema_snapshot_sha256",
    "tool_schema_digest",
    "tool_schema_snapshot",
    "validate_tool_arguments",
]
