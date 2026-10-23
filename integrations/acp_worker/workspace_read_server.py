"""Official MCP SDK edge for the governed ACP workspace read/search tools."""
from __future__ import annotations

import json
import math
from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from common.bounded_sync_executor import BoundedSyncExecutor
from integrations.workbench_stdio_boundary import private_stdio_server
from .workspace_read_mcp import (
    MAX_RESULT_BYTES,
    SERVER_NAME,
    SERVER_VERSION,
    WorkspaceReadGateway,
    tool_catalog,
)

MAX_ARGUMENT_BYTES = 16 * 1024


def build_tools() -> list[mcp_types.Tool]:
    result: list[mcp_types.Tool] = []
    for row in tool_catalog():
        result.append(
            mcp_types.Tool(
                name=row["name"],
                description=(
                    "Read bounded data from the exact Executive workspace. "
                    "The workspace root is host-owned and cannot be selected by the caller."
                    if row["name"] == "read_file"
                    else "Search one bounded page of one exact Executive workspace file. "
                    "This never crawls or writes the workspace."
                ),
                inputSchema=row["inputSchema"],
                annotations=mcp_types.ToolAnnotations(**row["annotations"]),
            )
        )
    return result


def _snapshot(arguments: object) -> dict[str, Any]:
    try:
        raw = json.dumps(
            arguments,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(raw) > MAX_ARGUMENT_BYTES:
            raise ValueError
        value = json.loads(raw.decode("utf-8"))
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        raise ValueError("INVALID_REQUEST") from None
    if type(value) is not dict:
        raise ValueError("INVALID_REQUEST")
    return value


def _result(payload: dict[str, Any]) -> mcp_types.CallToolResult:
    try:
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(raw) > MAX_RESULT_BYTES:
            raise ValueError
        text = raw.decode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        text = '{"error":{"code":"INTERNAL_ERROR"},"ok":false,"tool":"unknown"}'
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=text)],
            isError=True,
        )
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)],
        isError=payload.get("ok") is not True,
    )


def build_server(
    gateway: WorkspaceReadGateway,
    executor: BoundedSyncExecutor | None = None,
    *,
    call_timeout_seconds: float = 5.0,
) -> Server:
    if not isinstance(gateway, WorkspaceReadGateway):
        raise TypeError("gateway must be WorkspaceReadGateway")
    if executor is not None and not isinstance(executor, BoundedSyncExecutor):
        raise TypeError("executor must be BoundedSyncExecutor")
    selected = executor or BoundedSyncExecutor(max_concurrency=2)
    if selected.max_concurrency > 2:
        raise ValueError("executor capacity must not exceed two calls")
    if (
        isinstance(call_timeout_seconds, bool)
        or not isinstance(call_timeout_seconds, (int, float))
        or not math.isfinite(call_timeout_seconds)
        or not 0 < call_timeout_seconds <= 30
    ):
        raise ValueError("call timeout must be a positive bounded number")

    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)
    tools = build_tools()
    names = frozenset(tool.name for tool in tools)
    server._acp_workspace_executor = selected  # type: ignore[attr-defined]

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    @server.call_tool(validate_input=False)
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> mcp_types.CallToolResult:
        if type(name) is not str or name not in names:
            return _result(gateway.call("unknown", {}))
        try:
            request = _snapshot(arguments or {})
        except ValueError:
            return _result(gateway.call(name, {"__invalid__": True}))
        try:
            payload = await selected.run(
                lambda: gateway.call(name, request),
                timeout=float(call_timeout_seconds),
            )
        except Exception:
            payload = gateway.call("unknown", {})
            payload["error"] = {"code": "INTERNAL_ERROR"}
        return _result(payload)

    # Refuse unknown tool names before the SDK's default cache/logging path can
    # interpolate caller-controlled names into diagnostics.
    sdk_handler = server.request_handlers[mcp_types.CallToolRequest]

    async def sanitized(
        request: mcp_types.CallToolRequest,
    ) -> mcp_types.ServerResult:
        if type(request.params.name) is not str or request.params.name not in names:
            return mcp_types.ServerResult(_result(gateway.call("unknown", {})))
        return await sdk_handler(request)

    server.request_handlers[mcp_types.CallToolRequest] = sanitized
    return server


def initialization_options(server: Server) -> InitializationOptions:
    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


async def run_stdio(gateway: WorkspaceReadGateway) -> None:
    executor: BoundedSyncExecutor | None = None
    try:
        server = build_server(gateway)
        selected = getattr(server, "_acp_workspace_executor", None)
        if not isinstance(selected, BoundedSyncExecutor):
            raise RuntimeError("ACP workspace executor ownership missing")
        executor = selected
        async with private_stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                initialization_options(server),
            )
    finally:
        if executor is not None:
            await executor.aclose(timeout=10.0)
        gateway.close()


__all__ = [
    "MAX_ARGUMENT_BYTES",
    "build_server",
    "build_tools",
    "initialization_options",
    "run_stdio",
]
