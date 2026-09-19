from __future__ import annotations

import contextlib
import importlib.metadata
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time

import pytest

REPO = Path(__file__).resolve().parents[1]
SENTINEL = "WORKBENCH_REJECTED_SECRET_7b927c"
# Cold interpreter/import startup is separate from an already-live MCP call.
STARTUP_TIMEOUT_SECONDS = 20
RESPONSE_TIMEOUT_SECONDS = 5


class NativeChild:
    """Test observer retains the exact Popen and records every cleanup fallback."""

    def __init__(self, args, *, pass_fds=()):
        self.stderr_file = tempfile.TemporaryFile()
        self.process = subprocess.Popen(
            args, cwd="/", stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.stderr_file, pass_fds=pass_fds,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO),
                 "PYTHONUNBUFFERED": "1"},
        )
        self.fallback_used = False
        self.buffer = b""
        self.wire = b""

    def send(self, payload):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode() + b"\n"
        self.process.stdin.write(raw)
        self.process.stdin.flush()

    def receive(self, timeout=RESPONSE_TIMEOUT_SECONDS):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "native child response timed out"
            ready, _, _ = select.select([self.process.stdout], [], [], remaining)
            assert ready, "native child response timed out"
            chunk = os.read(self.process.stdout.fileno(), 65536)
            assert chunk, "native child ended before protocol response"
            self.wire += chunk
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def eof(self):
        if not self.process.stdin.closed:
            self.process.stdin.close()

    def assert_exit(self, expected=0):
        self.eof()
        code = self.process.wait(timeout=10)
        self.wire += self.process.stdout.read()
        assert code == expected, f"native child exit {code}; expected {expected}"
        assert not self.fallback_used

    def stderr(self):
        self.stderr_file.seek(0)
        return self.stderr_file.read()

    def cleanup(self):
        self.eof()
        if self.process.poll() is None:
            self.fallback_used = True
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process.stdout.close()
        self.stderr_file.close()


@contextlib.contextmanager
def child(args, *, pass_fds=()):
    selected = NativeChild(args, pass_fds=pass_fds)
    try:
        yield selected
    finally:
        selected.cleanup()


def initialize(process):
    process.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-11-25", "capabilities": {},
        "clientInfo": {"name": "native-test", "version": "1"},
    }})
    assert "result" in process.receive(timeout=STARTUP_TIMEOUT_SECONDS)
    process.send({"jsonrpc": "2.0", "method": "notifications/initialized"})


# This exercises the transport independently, with the real pinned SDK; it does
# not substitute a runtime. Production launcher/runtime cases follow separately.
PROTOCOL_CHILD = '''
import asyncio, logging
from mcp.server.lowlevel import Server
from integrations.workbench_stdio_boundary import private_stdio_server
logging.basicConfig(level=logging.DEBUG)
async def main():
    server = Server("protocol-boundary-test")
    async with private_stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
asyncio.run(main())
'''


def malformed_frames():
    return [
        ("json", b'{"' + SENTINEL.encode() + b'":\n'),
        ("envelope", [SENTINEL]),
        ("method", {"jsonrpc": "2.0", "id": 2, "method": {"secret": SENTINEL}}),
        ("unknown_method", {"jsonrpc": "2.0", "id": 2, "method": SENTINEL}),
        ("id", {"jsonrpc": "2.0", "id": [SENTINEL], "method": "ping"}),
        ("params", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": [SENTINEL]}),
        ("name", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": [SENTINEL]}}),
        ("arguments", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "prepare_text_patch", "arguments": SENTINEL}}),
        ("extra", {"jsonrpc": "2.0", "id": 2, "method": "ping", "secret": SENTINEL}),
        ("params_extra", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "prepare_text_patch", "secret": SENTINEL}}),
        ("duplicate", ('{"jsonrpc":"2.0","id":2,"method":"' + SENTINEL + '","method":"ping"}\n').encode()),
        ("nonfinite", ('{"jsonrpc":"2.0","id":2,"method":"ping","params":{"' + SENTINEL + '":NaN}}\n').encode()),
    ]


@pytest.mark.parametrize("label,payload", malformed_frames(), ids=lambda value: value if isinstance(value, str) else None)
def test_native_protocol_rejection_is_private_and_recovers(label, payload):
    assert importlib.metadata.version("mcp") == "1.28.1"
    with child([sys.executable, "-c", PROTOCOL_CHILD]) as process:
        initialize(process)
        process.send(payload)
        rejected = process.receive()
        assert rejected == {"jsonrpc": "2.0", "id": None, "error": {
            "code": -32600, "message": "WORKBENCH_MCP_INVALID_REQUEST",
        }}
        process.send({"jsonrpc": "2.0", "id": 3, "method": "ping"})
        assert process.receive() == {"jsonrpc": "2.0", "id": 3, "result": {}}
        process.assert_exit()
        assert SENTINEL.encode() not in process.wire + process.stderr()
        assert b"WORKBENCH_MCP_INVALID_REQUEST" in process.stderr()
        assert not process.fallback_used


def test_native_protocol_oversize_frame_is_bounded_and_drained():
    from integrations.workbench_stdio_boundary import MAX_WIRE_BYTES

    with child([sys.executable, "-c", PROTOCOL_CHILD]) as process:
        initialize(process)
        process.send(b'{"secret":"' + SENTINEL.encode() + b'x' * MAX_WIRE_BYTES + b'"}\n')
        assert process.receive()["error"]["code"] == -32600
        process.send({"jsonrpc": "2.0", "id": 3, "method": "ping"})
        assert process.receive()["result"] == {}
        process.assert_exit()
        assert SENTINEL.encode() not in process.wire + process.stderr()


def test_scoped_sdk_filter_preserves_other_sessions_and_diagnostics(caplog):
    import logging
    from integrations.workbench_stdio_boundary import _protocol_diagnostics

    logger = logging.getLogger("mcp.server.lowlevel.server")
    caplog.set_level(logging.DEBUG)
    logger.warning("outside-before")
    with _protocol_diagnostics():
        try:
            raise ValueError(SENTINEL)
        except ValueError:
            logger.exception("sensitive %s", SENTINEL)
        logging.getLogger("unrelated.application").warning("useful-local-diagnostic")
    logger.warning("outside-after")
    assert SENTINEL not in caplog.text
    assert "WORKBENCH_MCP_SDK_DIAGNOSTIC" in caplog.text
    assert "useful-local-diagnostic" in caplog.text
    assert "outside-before" in caplog.text and "outside-after" in caplog.text


@pytest.mark.parametrize("response_kind", ["result", "error"])
def test_server_initiated_ping_receives_native_response(response_kind):
    code = '''
import asyncio, logging
import anyio
from mcp.server.lowlevel import Server
from mcp.types import Tool
from mcp.shared.exceptions import McpError
from integrations.workbench_stdio_boundary import private_stdio_server
logging.basicConfig(level=logging.DEBUG)
async def main():
    server = Server("server-ping-test")
    @server.list_tools()
    async def listed():
        with anyio.fail_after(2):
            try:
                await server.request_context.session.send_ping()
                name = "pong"
            except McpError:
                name = "refused"
        return [Tool(name=name, inputSchema={})]
    async with private_stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
asyncio.run(main())
'''
    with child([sys.executable, "-c", code]) as process:
        initialize(process)
        process.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        ping = process.receive()
        assert ping["method"] == "ping"
        reply = {"jsonrpc": "2.0", "id": ping["id"], response_kind: {}}
        if response_kind == "error":
            reply["error"] = {"code": -32000, "message": "test refusal"}
        process.send(reply)
        listed = process.receive()
        assert listed["id"] == 2
        assert listed["result"]["tools"][0]["name"] == ("pong" if response_kind == "result" else "refused")
        process.assert_exit(0)
        assert b"WORKBENCH_MCP_INVALID_REQUEST" not in process.stderr()


def test_oversized_native_output_is_refused_and_next_request_survives():
    from integrations.workbench_stdio_boundary import MAX_WIRE_BYTES

    code = '''
import asyncio, logging
from mcp.server.lowlevel import Server
from mcp.types import Tool
from integrations.workbench_stdio_boundary import private_stdio_server, MAX_WIRE_BYTES
logging.basicConfig(level=logging.DEBUG)
async def main():
    server = Server("output-limit-test")
    @server.list_tools()
    async def listed():
        return [Tool(name="oversized", description="WORKBENCH_REJECTED_SECRET_7b927c" + "界" * MAX_WIRE_BYTES, inputSchema={})]
    async with private_stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
asyncio.run(main())
'''
    with child([sys.executable, "-c", code]) as process:
        initialize(process)
        before = len(process.wire)
        process.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        reply = process.receive()
        assert reply == {"jsonrpc": "2.0", "id": 2, "error": {
            "code": -32603, "message": "WORKBENCH_MCP_OUTPUT_LIMIT",
        }}
        assert len(process.wire) - before < MAX_WIRE_BYTES
        process.send({"jsonrpc": "2.0", "id": 3, "method": "ping"})
        assert process.receive()["result"] == {}
        process.assert_exit(0)
        assert SENTINEL.encode() not in process.wire + process.stderr()
        assert b"WORKBENCH_MCP_OUTPUT_LIMIT" in process.stderr()


def test_official_client_original_oversized_request_completes_without_timeout(monkeypatch):
    """Observe the original SDK waiter and exact child, not a second raw ping."""
    import asyncio
    from datetime import timedelta
    import importlib
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.shared.exceptions import McpError

    stdio = importlib.import_module("mcp.client.stdio")
    handles, fallback = [], []
    real_create = stdio._create_platform_compatible_process
    real_terminate = stdio._terminate_process_tree

    async def create(**kwargs):
        process = await real_create(**kwargs)
        handles.append(process)
        return process

    async def terminate(process):
        fallback.append(process)
        await real_terminate(process)

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", create)
    monkeypatch.setattr(stdio, "_terminate_process_tree", terminate)
    code = '''
import asyncio
from mcp.server.lowlevel import Server
from mcp.types import Tool
from integrations.workbench_stdio_boundary import private_stdio_server, MAX_WIRE_BYTES
async def main():
    server = Server("original-response-test")
    @server.list_tools()
    async def listed():
        return [Tool(name="oversized", description="WORKBENCH_REJECTED_SECRET_7b927c" + "x" * MAX_WIRE_BYTES, inputSchema={})]
    async with private_stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
asyncio.run(main())
'''
    with tempfile.TemporaryFile(mode="w+") as errors:
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=["-c", code], cwd="/",
                                            env={"PYTHONPATH": str(REPO), "PYTHONUNBUFFERED": "1"})
            async with stdio.stdio_client(params, errlog=errors) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
                    with anyio.fail_after(STARTUP_TIMEOUT_SECONDS):
                        await session.initialize()
                    # The client's 30-second timeout cannot explain this result.
                    with anyio.fail_after(RESPONSE_TIMEOUT_SECONDS):
                        with pytest.raises(McpError) as caught:
                            await session.list_tools()
                    assert caught.value.error.code == -32603
                    assert caught.value.error.message == "WORKBENCH_MCP_OUTPUT_LIMIT"
        asyncio.run(exercise())
        assert len(handles) == 1
        assert handles[0].returncode == 0
        assert not fallback
        errors.seek(0)
        assert SENTINEL not in errors.read()


@pytest.mark.parametrize("request_id", [True, 2**64, SENTINEL + "x" * 1024])
def test_uncorrelatable_request_id_is_refused_before_sdk(request_id):
    from integrations.workbench_stdio_boundary import _validated_protocol_line

    with pytest.raises(ValueError, match="PROTOCOL_ID"):
        _validated_protocol_line(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": "ping"}))
