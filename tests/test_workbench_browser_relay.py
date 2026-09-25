from __future__ import annotations

import json
import os
import socket
import sys
import threading
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from integrations.workbench_browser_mcp.relay import (
    BrowserRelayError,
    BrowserRelayServer,
    McpSessionReceipt,
    McpStdioSession,
    relay_request,
)


FAKE_TOOLS = [
    {
        "name": "browser_snapshot",
        "description": "snapshot",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "browser_click",
        "description": "click",
        "inputSchema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False},
    },
]


def _digest():
    return observed_mcp_tool_schema_digest(
        {"tools": {row["name"]: row for row in FAKE_TOOLS}}
    )


def _fake_child(tmp_path: Path, *, schema_drift: bool = False) -> list[str]:
    tools = json.loads(json.dumps(FAKE_TOOLS))
    if schema_drift:
        tools[0]["inputSchema"]["properties"]["changed"] = {"type": "string"}
    program = tmp_path / ("fake-mcp-drift.py" if schema_drift else "fake-mcp.py")
    program.write_text(
        """import json,sys
TOOLS = %s
for line in sys.stdin:
    req=json.loads(line)
    if req.get("method") == "initialize":
        out={"jsonrpc":"2.0","id":req["id"],"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"fake","version":"1"}}}
        print(json.dumps(out,separators=(",",":")),flush=True)
    elif req.get("method") == "notifications/initialized":
        continue
    elif req.get("method") == "tools/list":
        print(json.dumps({"jsonrpc":"2.0","id":req["id"],"result":{"tools":TOOLS}},separators=(",",":")),flush=True)
    elif req.get("method") == "tools/call":
        params=req.get("params",{})
        result={"content":[{"type":"text","text":json.dumps({"tool":params.get("name"),"arguments":params.get("arguments")},sort_keys=True)}],"isError":False}
        print(json.dumps({"jsonrpc":"2.0","id":req["id"],"result":result},separators=(",",":")),flush=True)
""" % repr(tools),
        encoding="utf-8",
    )
    return [sys.executable, "-I", "-S", str(program)]


def test_stdio_session_initializes_verifies_schema_and_calls_tool(tmp_path):
    session = McpStdioSession(
        argv=_fake_child(tmp_path),
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        allowed_tools=frozenset({"browser_snapshot", "browser_click"}),
        expected_tool_schema_digest=_digest(),
    )
    try:
        receipt = session.start()
        assert receipt.tool_schema_digest == _digest()
        assert receipt.allowed_tools == ("browser_click", "browser_snapshot")
        result = session.call("browser_click", {"target": "button"})
        text = result["content"][0]["text"]
        assert json.loads(text) == {"arguments": {"target": "button"}, "tool": "browser_click"}
    finally:
        session.close()


def test_stdio_session_refuses_catalog_schema_drift(tmp_path):
    session = McpStdioSession(
        argv=_fake_child(tmp_path, schema_drift=True),
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        allowed_tools=frozenset({"browser_snapshot", "browser_click"}),
        expected_tool_schema_digest=_digest(),
    )
    with pytest.raises(BrowserRelayError, match="schema"):
        session.start()
    session.close()


def test_stdio_session_refuses_ungranted_tool(tmp_path):
    session = McpStdioSession(
        argv=_fake_child(tmp_path),
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        allowed_tools=frozenset({"browser_snapshot", "browser_click"}),
        expected_tool_schema_digest=_digest(),
    )
    try:
        session.start()
        with pytest.raises(BrowserRelayError, match="not granted"):
            session.call("browser_evaluate", {})
    finally:
        session.close()


class _PostDispatchFailureSession(McpStdioSession):
    def __init__(self):
        super().__init__(
            argv=("/usr/bin/true",),
            env={},
            allowed_tools=frozenset({"browser_click"}),
            expected_tool_schema_digest="d" * 64,
        )
        self.dispatched = False

    def start(self):
        self._receipt = McpSessionReceipt(
            child_pid=1,
            tool_schema_digest="d" * 64,
            allowed_tools=("browser_click",),
        )
        return self._receipt

    def call(self, tool, arguments):
        assert tool == "browser_click"
        assert arguments == {"target": "button"}
        self.dispatched = True
        raise BrowserRelayError("synthetic response lost after dispatch")

    def close(self):
        self._receipt = None


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix sockets required")
def test_relay_marks_post_dispatch_child_failure_effect_unknown(tmp_path):
    socket_path = tmp_path / "relay-effect.sock"
    session = _PostDispatchFailureSession()
    relay = BrowserRelayServer(
        resource_id="a" * 32,
        socket_path=socket_path,
        session=session,
    )
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    relay.wait_ready(timeout=3)
    result = relay_request(
        socket_path,
        {
            "schema": "mastermind.workbench_browser_relay_request.v1",
            "kind": "tool",
            "request_id": "b" * 32,
            "resource_id": "a" * 32,
            "tool": "browser_click",
            "arguments": {"target": "button"},
        },
        timeout=2,
    )
    relay.stop()
    thread.join(timeout=3)
    assert session.dispatched is True
    assert result["ok"] is False
    assert result["error"] == "EFFECT_UNKNOWN"


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix sockets required")
def test_relay_routes_by_resource_identity_without_session_registry(tmp_path):
    socket_path = tmp_path / "relay.sock"
    session = McpStdioSession(
        argv=_fake_child(tmp_path),
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        allowed_tools=frozenset({"browser_snapshot", "browser_click"}),
        expected_tool_schema_digest=_digest(),
    )
    relay = BrowserRelayServer(
        resource_id="a" * 32,
        socket_path=socket_path,
        session=session,
    )
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    relay.wait_ready(timeout=3)

    status = relay_request(
        socket_path,
        {
            "schema": "mastermind.workbench_browser_relay_request.v1",
            "kind": "status",
            "request_id": "b" * 32,
            "resource_id": "a" * 32,
        },
        timeout=2,
    )
    assert status["ok"] is True
    assert status["resource_id"] == "a" * 32
    assert status["tool_schema_digest"] == _digest()

    result = relay_request(
        socket_path,
        {
            "schema": "mastermind.workbench_browser_relay_request.v1",
            "kind": "tool",
            "request_id": "c" * 32,
            "resource_id": "a" * 32,
            "tool": "browser_snapshot",
            "arguments": {},
        },
        timeout=2,
    )
    assert result["ok"] is True
    assert result["request_id"] == "c" * 32
    assert result["result"]["isError"] is False

    wrong = relay_request(
        socket_path,
        {
            "schema": "mastermind.workbench_browser_relay_request.v1",
            "kind": "status",
            "request_id": "d" * 32,
            "resource_id": "e" * 32,
        },
        timeout=2,
    )
    assert wrong["ok"] is False
    assert wrong["error"] == "RESOURCE_MISMATCH"

    relay.stop()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert not socket_path.exists()


def test_relay_refuses_preexisting_socket_path(tmp_path):
    socket_path = tmp_path / "relay.sock"
    socket_path.write_text("do-not-delete", encoding="utf-8")
    session = McpStdioSession(
        argv=_fake_child(tmp_path),
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        allowed_tools=frozenset({"browser_snapshot", "browser_click"}),
        expected_tool_schema_digest=_digest(),
    )
    relay = BrowserRelayServer(
        resource_id="a" * 32,
        socket_path=socket_path,
        session=session,
    )
    with pytest.raises(BrowserRelayError, match="exists"):
        relay.serve_forever()
    assert socket_path.read_text(encoding="utf-8") == "do-not-delete"


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix sockets required")
def test_relay_self_retires_at_authoritative_lease_expiry(tmp_path):
    socket_path = tmp_path / "relay-expiry.sock"
    now = {"value": 1000}
    session = McpStdioSession(
        argv=_fake_child(tmp_path),
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        allowed_tools=frozenset({"browser_snapshot", "browser_click"}),
        expected_tool_schema_digest=_digest(),
    )
    relay = BrowserRelayServer(
        resource_id="a" * 32,
        socket_path=socket_path,
        session=session,
        expires_at_ms=2000,
        clock_ms=lambda: now["value"],
    )
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    relay.wait_ready(timeout=3)
    assert socket_path.exists()
    now["value"] = 2000
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert not socket_path.exists()


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix sockets required")
def test_relay_self_retires_when_workbench_parent_disappears(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    import integrations.workbench_browser_mcp.relay as relay_module

    socket_path = tmp_path / "relay-parent.sock"
    observed_parent = {"pid": 4242}
    monkeypatch.setattr(relay_module.os, "getppid", lambda: observed_parent["pid"])
    session = McpStdioSession(
        argv=_fake_child(tmp_path),
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        allowed_tools=frozenset({"browser_snapshot", "browser_click"}),
        expected_tool_schema_digest=_digest(),
    )
    relay = BrowserRelayServer(
        resource_id="a" * 32,
        socket_path=socket_path,
        session=session,
        parent_pid=4242,
    )
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    relay.wait_ready(timeout=3)
    assert socket_path.exists()
    observed_parent["pid"] = 1
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert not socket_path.exists()
