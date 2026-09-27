"""Optional tools-only read companion inside the existing GitHub owner app.

This factory creates a protocol object only. It opens no listener, registers no
application, reads no credential, and leaves the three-tool patch server intact.
Deployment must separately bind the existing authentication and transport owners.
"""
from __future__ import annotations

from copy import deepcopy
import json

import mcp.types as mcp_types
from mcp.server.lowlevel import Server

from .writer_gate_port import (
    GithubWriterGatePort, WriterGateServiceRefused, WRITER_GATE_TOOL_SPEC,
)


def _result(payload: dict[str, object], *, failed: bool) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        isError=failed,
        content=[mcp_types.TextContent(type="text", text=json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False))],
    )


def build_read_only_mcp_server(port: GithubWriterGatePort) -> Server:
    if type(port) is not GithubWriterGatePort:
        raise TypeError("writer-gate port required")
    server = Server("mastermind-github-writer-gate", version="0.1.0")
    tool = mcp_types.Tool(
        name=WRITER_GATE_TOOL_SPEC["name"], description=WRITER_GATE_TOOL_SPEC["description"],
        inputSchema=deepcopy(WRITER_GATE_TOOL_SPEC["inputSchema"]),
        annotations=mcp_types.ToolAnnotations(**WRITER_GATE_TOOL_SPEC["annotations"]),
    )

    @server.list_tools()
    async def list_tools():
        return [tool.model_copy(deep=True)]

    # Validate here, not in a generic schema-error formatter that may echo the
    # rejected instance. Model input and upstream error bodies are never copied.
    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict | None):
        if (name != tool.name or type(arguments) is not dict
                or set(arguments) != {"operation_key"}
                or type(arguments["operation_key"]) is not str):
            return _result({"code": "INPUT_REFUSED", "receipt": None}, failed=True)
        try:
            receipt = await port.observe_writer_gate(arguments["operation_key"])
            return _result(receipt, failed=receipt.get("schema") != "mastermind.source_continuity_writer_gate/v1")
        except WriterGateServiceRefused as error:
            return _result({"code": error.code, "receipt": None}, failed=True)
        except Exception:
            return _result({"code": "SERVICE_UNAVAILABLE", "receipt": None}, failed=True)

    return server
