"""Bounded private stdio boundary for Workbench servers using MCP SDK 1.28.1.

Reuses the documented SDK stdin/stdout adapters and task group. No application
runtime, authorization, effect, store, process or lifecycle ownership lives here.
"""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from io import TextIOWrapper
import json
import logging
import sys

import anyio
import mcp.types as mcp_types
from mcp.server.stdio import stdio_server

MAX_WIRE_BYTES = 262144
_PROTOCOL_SCOPE = ContextVar("workbench_stdio_diagnostics", default=False)


def _closed_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("PROTOCOL_DUPLICATE_FIELD")
        value[key] = item
    return value


def _reject_constant(_value):
    raise ValueError("PROTOCOL_NONFINITE")


class _ProtocolDiagnosticFilter(logging.Filter):
    """Sanitize only this server's pinned SDK records, including exception text."""

    def filter(self, record: logging.LogRecord) -> bool:
        if _PROTOCOL_SCOPE.get() and (
            record.name == "mcp.server.lowlevel.server"
            or (record.name == "root" and record.pathname.endswith("/mcp/shared/session.py"))
        ):
            record.msg = "WORKBENCH_MCP_SDK_DIAGNOSTIC"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


@contextmanager
def _protocol_diagnostics():
    # Logger filters apply before handlers. Scope follows this async task and
    # its SDK descendants; unrelated sessions keep their original diagnostics.
    selected = (logging.getLogger(), logging.getLogger("mcp.server.lowlevel.server"))
    sanitizer = _ProtocolDiagnosticFilter()
    token = _PROTOCOL_SCOPE.set(True)
    for logger in selected:
        logger.addFilter(sanitizer)
    try:
        yield
    finally:
        for logger in selected:
            logger.removeFilter(sanitizer)
        _PROTOCOL_SCOPE.reset(token)


class _ProtocolOutput:
    def __init__(self, output):
        self._output = output
        self._lock = anyio.Lock()

    async def write(self, text: str):
        # SDK output and fixed protocol refusals share this single line writer.
        if len(text.encode("utf-8")) > MAX_WIRE_BYTES:
            logging.getLogger(__name__).warning("WORKBENCH_MCP_OUTPUT_LIMIT")
            text = ('{"jsonrpc":"2.0","id":null,"error":{"code":-32603,'
                    '"message":"WORKBENCH_MCP_OUTPUT_LIMIT"}}\n')
        async with self._lock:
            await self._output.write(text)
            await self._output.flush()

    async def flush(self):
        # write already flushes under the same lock.
        return None


def _validated_protocol_line(line: str) -> str:
    if len(line.encode("utf-8")) > MAX_WIRE_BYTES:
        raise ValueError("PROTOCOL_LIMIT")
    raw = json.loads(line, object_pairs_hook=_closed_object, parse_constant=_reject_constant)
    if type(raw) is not dict or raw.get("jsonrpc") != "2.0":
        raise ValueError("PROTOCOL_ENVELOPE")
    if "id" in raw:
        request_id = raw["id"]
        if type(request_id) not in {str, int} or (type(request_id) is str and len(request_id) > 256):
            raise ValueError("PROTOCOL_ID")
    if "method" not in raw:
        # Responses must reach the SDK's existing response waiters (send_ping,
        # etc.). A closed response shape is not a client request/notification.
        if set(raw) == {"jsonrpc", "id", "result"}:
            mcp_types.JSONRPCResponse.model_validate(raw, strict=True)
        elif set(raw) == {"jsonrpc", "id", "error"}:
            error = raw["error"]
            if type(error) is not dict or not set(error) <= {"code", "message", "data"}:
                raise ValueError("PROTOCOL_ERROR")
            mcp_types.JSONRPCError.model_validate(raw, strict=True)
        else:
            raise ValueError("PROTOCOL_ENVELOPE")
    else:
        if not set(raw) <= {"jsonrpc", "id", "method", "params"}:
            raise ValueError("PROTOCOL_ENVELOPE")
        if type(raw["method"]) is not str:
            raise ValueError("PROTOCOL_METHOD")
        if "params" in raw and type(raw["params"]) is not dict:
            raise ValueError("PROTOCOL_PARAMS")
        if "id" in raw:
            parsed = mcp_types.ClientRequest.model_validate(raw, strict=True)
            if isinstance(parsed.root, mcp_types.CallToolRequest):
                if not set(raw.get("params", {})) <= {"name", "arguments", "_meta", "task"}:
                    raise ValueError("PROTOCOL_PARAMS")
        else:
            mcp_types.ClientNotification.model_validate(raw, strict=True)
    # Validate both layers before the SDK can construct value-bearing errors.
    mcp_types.JSONRPCMessage.model_validate(raw, strict=True)
    return json.dumps(raw, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"


class _ProtocolInput:
    def __init__(self, source, output: _ProtocolOutput):
        self._source = source
        self._output = output

    def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            line = await anyio.to_thread.run_sync(self._source.readline, MAX_WIRE_BYTES + 1)
            if not line:
                raise StopAsyncIteration
            too_long = len(line) > MAX_WIRE_BYTES
            if too_long and not line.endswith("\n"):
                # Drain this one rejected frame in bounded chunks, then recover.
                while True:
                    tail = await anyio.to_thread.run_sync(self._source.readline, MAX_WIRE_BYTES + 1)
                    if not tail or tail.endswith("\n"):
                        break
            try:
                if too_long:
                    raise ValueError("PROTOCOL_LIMIT")
                return _validated_protocol_line(line)
            except (ValueError, TypeError, RecursionError, UnicodeError):
                logging.getLogger(__name__).warning("WORKBENCH_MCP_INVALID_REQUEST")
                # Rejected IDs can themselves contain secrets; never reflect them.
                await self._output.write(
                    '{"jsonrpc":"2.0","id":null,"error":{"code":-32600,'
                    '"message":"WORKBENCH_MCP_INVALID_REQUEST"}}\n'
                )


@asynccontextmanager
async def private_stdio_server():
    # Use the SDK's supported stream adapters and existing task group. These
    # wrappers borrow process stdio; they do not own another runtime lifecycle.
    source_wrapper = TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    output_wrapper = TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    output = _ProtocolOutput(anyio.wrap_file(output_wrapper))
    source = _ProtocolInput(source_wrapper, output)
    try:
        with _protocol_diagnostics():
            async with stdio_server(stdin=source, stdout=output) as streams:
                yield streams
    finally:
        # Do not let temporary wrappers close the process's borrowed handles.
        source_wrapper.detach()
        output_wrapper.detach()


__all__ = ["private_stdio_server"]
