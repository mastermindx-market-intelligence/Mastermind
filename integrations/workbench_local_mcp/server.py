"""MCP SDK edge for the local Workbench tunnel profile.

The official Secure MCP Tunnel launches this server over stdio. This module is
the only package module that imports the MCP SDK; authority and project access
remain in the adapter and existing Workbench observer.
"""
from __future__ import annotations

import json
import math
from typing import Any

import jsonschema
import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from common.bounded_sync_executor import BoundedSyncExecutor
from integrations.workbench_stdio_boundary import private_stdio_server
from .adapter import LocalWorkbenchGateway
from .schemas import (
    MAX_ARGUMENT_BYTES,
    MAX_RESULT_BYTES,
    PROFILE_PRO_READ_PREPARE,
    RESULT_SCHEMA,
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_SPECS,
    canonical_json,
)

_UNKNOWN_TOOL_RESULT_NAME = "unknown"
_TOOL_VALIDATORS = {
    spec.name: jsonschema.Draft202012Validator(spec.input_schema) for spec in TOOL_SPECS
}
_FIXED_INTERNAL_ERROR = canonical_json(
    {
        "schema": RESULT_SCHEMA,
        "tool": _UNKNOWN_TOOL_RESULT_NAME,
        "ok": False,
        "server_version": SERVER_VERSION,
        "profile": PROFILE_PRO_READ_PREPARE,
        "mutation_allowed": False,
        "project_ref": "unknown",
        "data": None,
        "error": {"code": "INTERNAL_ERROR"},
    }
).decode("utf-8")


def build_tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
            annotations=mcp_types.ToolAnnotations(**spec.annotations),
        )
        for spec in TOOL_SPECS
    ]


def _validated_arguments(name: str, arguments: object) -> dict[str, Any]:
    """Return a plain bounded JSON object or a fixed invalid-request marker."""

    try:
        raw = canonical_json(arguments)
        if len(raw) > MAX_ARGUMENT_BYTES:
            raise ValueError
        selected = json.loads(raw)
        if type(selected) is not dict:
            raise ValueError
        _TOOL_VALIDATORS[name].validate(selected)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, jsonschema.ValidationError):
        raise ValueError("invalid tool arguments") from None
    return selected


def _result(payload: dict[str, Any]) -> mcp_types.CallToolResult:
    """Serialize only the closed adapter envelope and preserve MCP error truth."""

    try:
        serialized = canonical_json(payload)
        if len(serialized) > MAX_RESULT_BYTES:
            raise ValueError
        text = serialized.decode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError):
        # Every adapter envelope is already bounded. This branch is a final
        # fixed failure boundary if a future change violates that contract.
        text = _FIXED_INTERNAL_ERROR
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=text)],
            isError=True,
        )
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)],
        isError=not payload.get("ok", False),
    )


def build_server(
    gateway: LocalWorkbenchGateway,
    executor: BoundedSyncExecutor | None = None,
    *,
    call_timeout_seconds: float = 5.0,
) -> Server:
    if not isinstance(gateway, LocalWorkbenchGateway):
        raise TypeError("gateway must be LocalWorkbenchGateway")
    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)
    tools = build_tools()
    if executor is not None and not isinstance(executor, BoundedSyncExecutor):
        raise TypeError("executor must be BoundedSyncExecutor")
    _executor = executor or BoundedSyncExecutor(max_concurrency=2)
    if _executor.max_concurrency > 2:
        raise ValueError("executor capacity must not exceed two calls")
    if (
        isinstance(call_timeout_seconds, bool)
        or not isinstance(call_timeout_seconds, (int, float))
        or not math.isfinite(call_timeout_seconds)
        or call_timeout_seconds <= 0
    ):
        raise ValueError("call_timeout_seconds must be a positive finite number")
    tool_names = frozenset(_TOOL_VALIDATORS)
    server._workbench_executor = _executor  # type: ignore[attr-defined]

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> mcp_types.CallToolResult:
        def _run() -> dict[str, Any]:
            try:
                selected = _validated_arguments(name, arguments or {})
            except ValueError:
                return gateway._error(name, "INVALID_REQUEST")
            return gateway.call(name, selected)

        try:
            payload = await _executor.run(_run, timeout=float(call_timeout_seconds))
        except Exception:
            payload = gateway._error(name, "INTERNAL_ERROR")
        return _result(payload)

    sdk_call_handler = server.request_handlers[mcp_types.CallToolRequest]

    async def sanitized_call_handler(req: mcp_types.CallToolRequest) -> mcp_types.ServerResult:
        """Refuse unknown names before the SDK cache logs caller-controlled text."""

        if type(req.params.name) is not str or req.params.name not in tool_names:
            payload = gateway._error(_UNKNOWN_TOOL_RESULT_NAME, "TOOL_NOT_AVAILABLE")
            return mcp_types.ServerResult(_result(payload))
        return await sdk_call_handler(req)

    server.request_handlers[mcp_types.CallToolRequest] = sanitized_call_handler

    return server


def initialization_options(server: Server) -> InitializationOptions:
    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


async def _drain_and_close(
    gateway: LocalWorkbenchGateway,
    executor: BoundedSyncExecutor,
    *,
    drain_timeout_seconds: float = 10.0,
) -> None:
    await executor.aclose(timeout=drain_timeout_seconds)
    gateway.close()


async def run_stdio(gateway: LocalWorkbenchGateway) -> None:
    executor: BoundedSyncExecutor | None = None
    try:
        server = build_server(gateway)
        selected_executor = getattr(server, "_workbench_executor", None)
        if not isinstance(selected_executor, BoundedSyncExecutor):
            raise RuntimeError("Workbench executor ownership missing")
        executor = selected_executor
        options = initialization_options(server)
        async with private_stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, options)
    finally:
        if executor is None:
            gateway.close()
        else:
            await _drain_and_close(gateway, executor)
