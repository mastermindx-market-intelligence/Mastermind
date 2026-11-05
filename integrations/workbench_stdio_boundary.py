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
from mcp.shared.message import SessionMessage

MAX_WIRE_BYTES = 262144
MODERN_PROTOCOL_VERSION = "2026-07-28"
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
            # All SDK messages pass the typed writer below first. Never emit
            # an uncorrelated error for an unexpected oversized raw write.
            raise RuntimeError("WORKBENCH_MCP_OUTPUT_LIMIT")
        async with self._lock:
            await self._output.write(text)
            await self._output.flush()

    async def flush(self):
        # write already flushes under the same lock.
        return None


class _BoundedSessionWriter:
    """Bound the SDK message while its typed response ID is still available."""

    def __init__(self, stream):
        self._stream = stream

    async def send(self, message: SessionMessage) -> None:
        raw = message.message.model_dump_json(by_alias=True, exclude_none=True)
        if len(raw.encode("utf-8")) + 1 > MAX_WIRE_BYTES:
            logging.getLogger(__name__).warning("WORKBENCH_MCP_OUTPUT_LIMIT")
            root = message.message.root
            request_id = getattr(root, "id", None)
            if (
                not isinstance(root, (mcp_types.JSONRPCResponse, mcp_types.JSONRPCError))
                or type(request_id) not in {int, str}
                or (type(request_id) is str and len(request_id.encode("utf-8")) > 1024)
                or (type(request_id) is int and not -(2**63) <= request_id < 2**63)
            ):
                raise RuntimeError("WORKBENCH_MCP_OUTPUT_LIMIT")
            # A closed fixed error completes the ORIGINAL SDK request. The
            # oversized body and arbitrary/huge IDs are never reflected.
            message = SessionMessage(mcp_types.JSONRPCMessage(mcp_types.JSONRPCError(
                jsonrpc="2.0", id=request_id,
                error=mcp_types.ErrorData(code=-32603, message="WORKBENCH_MCP_OUTPUT_LIMIT"),
            )))
        await self._stream.send(message)

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def __aenter__(self):
        await self._stream.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self._stream.__aexit__(*args)

    def clone(self):
        return _BoundedSessionWriter(self._stream.clone())


def _validated_protocol_line(line: str) -> str:
    if len(line.encode("utf-8")) > MAX_WIRE_BYTES:
        raise ValueError("PROTOCOL_LIMIT")
    raw = json.loads(line, object_pairs_hook=_closed_object, parse_constant=_reject_constant)
    if type(raw) is not dict or raw.get("jsonrpc") != "2.0":
        raise ValueError("PROTOCOL_ENVELOPE")
    if "id" in raw:
        request_id = raw["id"]
        if (
            type(request_id) not in {str, int}
            or (type(request_id) is str and len(request_id) > 256)
            or (type(request_id) is int and not -(2**63) <= request_id < 2**63)
        ):
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
    def __init__(self, source, output: _ProtocolOutput, *, initial_line: str | None = None):
        self._source = source
        self._output = output
        self._initial_line = initial_line

    def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            if self._initial_line is not None:
                line = self._initial_line
                self._initial_line = None
            else:
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
async def private_stdio_server(*, initial_line: str | None = None):
    # Use the SDK's supported stream adapters and existing task group. These
    # wrappers borrow process stdio; they do not own another runtime lifecycle.
    source_wrapper = TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    output_wrapper = TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    output = _ProtocolOutput(anyio.wrap_file(output_wrapper))
    source = _ProtocolInput(source_wrapper, output, initial_line=initial_line)
    try:
        with _protocol_diagnostics():
            async with stdio_server(stdin=source, stdout=output) as (read, write):
                yield read, _BoundedSessionWriter(write)
    finally:
        # Do not let temporary wrappers close the process's borrowed handles.
        source_wrapper.detach()
        output_wrapper.detach()


async def read_bounded_stdio_line() -> str | None:
    """Read one bounded physical stdio frame without claiming protocol ownership."""
    raw = await anyio.to_thread.run_sync(sys.stdin.buffer.readline, MAX_WIRE_BYTES + 1)
    if not raw:
        return None
    if len(raw) > MAX_WIRE_BYTES and not raw.endswith(b"\n"):
        while True:
            tail = await anyio.to_thread.run_sync(sys.stdin.buffer.readline, MAX_WIRE_BYTES + 1)
            if not tail or tail.endswith(b"\n"):
                break
    return raw.decode("utf-8", errors="replace")


def _bounded_jsonrpc_object(line: str) -> dict[str, object]:
    if len(line.encode("utf-8")) > MAX_WIRE_BYTES:
        raise ValueError("PROTOCOL_LIMIT")
    raw = json.loads(line, object_pairs_hook=_closed_object, parse_constant=_reject_constant)
    if type(raw) is not dict or raw.get("jsonrpc") != "2.0":
        raise ValueError("PROTOCOL_ENVELOPE")
    if not set(raw) <= {"jsonrpc", "id", "method", "params"}:
        raise ValueError("PROTOCOL_ENVELOPE")
    request_id = raw.get("id")
    if "id" in raw and (
        type(request_id) not in {str, int}
        or (type(request_id) is str and len(request_id.encode("utf-8")) > 1024)
        or (type(request_id) is int and not -(2**63) <= request_id < 2**63)
    ):
        raise ValueError("PROTOCOL_ID")
    if type(raw.get("method")) is not str:
        raise ValueError("PROTOCOL_METHOD")
    if "params" in raw and type(raw["params"]) is not dict:
        raise ValueError("PROTOCOL_PARAMS")
    return raw


def is_modern_protocol_request(line: str) -> bool:
    """Classify only the 2026 stateless envelope; malformed data stays legacy-closed."""
    try:
        raw = _bounded_jsonrpc_object(line)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        return False
    if raw["method"] == "server/discover":
        return True
    params = raw.get("params") or {}
    meta = params.get("_meta") if type(params) is dict else None
    return (
        type(meta) is dict
        and meta.get("io.modelcontextprotocol/protocolVersion") == MODERN_PROTOCOL_VERSION
    )


def parse_modern_protocol_request(line: str) -> dict[str, object]:
    """Validate the closed JSON-RPC envelope used by the Workbench modern seam."""
    raw = _bounded_jsonrpc_object(line)
    params = raw.get("params") or {}
    meta = params.get("_meta") if type(params) is dict else None
    if meta is not None:
        if type(meta) is not dict:
            raise ValueError("PROTOCOL_META")
        version = meta.get("io.modelcontextprotocol/protocolVersion")
        if version is not None and version != MODERN_PROTOCOL_VERSION:
            raise ValueError("PROTOCOL_VERSION")
    return raw


async def write_bounded_stdio_json(payload: dict[str, object]) -> None:
    """Emit one compact response frame; never write an oversized or non-JSON result."""
    text = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ) + "\n"
    data = text.encode("utf-8")
    if len(data) > MAX_WIRE_BYTES:
        raise RuntimeError("WORKBENCH_MCP_OUTPUT_LIMIT")

    def _write() -> None:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    await anyio.to_thread.run_sync(_write)


__all__ = [
    "MAX_WIRE_BYTES",
    "MODERN_PROTOCOL_VERSION",
    "is_modern_protocol_request",
    "parse_modern_protocol_request",
    "private_stdio_server",
    "read_bounded_stdio_line",
    "write_bounded_stdio_json",
]
