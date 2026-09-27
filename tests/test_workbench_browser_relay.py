from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from contextlib import nullcontext
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from integrations.workbench_browser_mcp.relay import (
    RELAY_REQUEST_SCHEMA,
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
        owner_pid=os.getpid(),
        parent_pid=os.getppid(),
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


class _CountingSession(McpStdioSession):
    def __init__(self):
        super().__init__(
            argv=("/usr/bin/true",),
            env={},
            allowed_tools=frozenset({"browser_click"}),
            expected_tool_schema_digest="d" * 64,
        )
        self.calls = 0

    def start(self):
        self._receipt = McpSessionReceipt(
            child_pid=os.getpid(),
            tool_schema_digest="d" * 64,
            allowed_tools=("browser_click",),
        )
        return self._receipt

    def call(self, tool, arguments):
        assert tool == "browser_click"
        assert arguments == {"target": "button"}
        self.calls += 1
        return {
            "content": [{"type": "text", "text": "AUTHORIZED"}],
            "isError": False,
        }

    def close(self):
        self._receipt = None


@pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX")
    or (sys.platform != "darwin" and not sys.platform.startswith("linux")),
    reason="Unix peer-PID credentials required",
)
def test_relay_refuses_same_uid_sibling_before_browser_dispatch(tmp_path):
    socket_path = tmp_path / "relay-peer-pid.sock"
    session = _CountingSession()
    relay = BrowserRelayServer(
        resource_id="a" * 32,
        socket_path=socket_path,
        session=session,
        owner_pid=os.getpid(),
        parent_pid=os.getppid(),
    )
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    relay.wait_ready(timeout=3)

    bypass_request = {
        "schema": "mastermind.workbench_browser_relay_request.v1",
        "kind": "tool",
        "request_id": "b" * 32,
        "resource_id": "a" * 32,
        "tool": "browser_click",
        "arguments": {"target": "button"},
    }
    child_program = r"""
import json,socket,sys
path=sys.argv[1]
request=json.loads(sys.argv[2])
client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
client.settimeout(2)
client.connect(path)
client.sendall(json.dumps(request,separators=(",",":")).encode()+b"\n")
data=b""
while b"\n" not in data:
    part=client.recv(65536)
    if not part:
        break
    data += part
client.close()
print(data.split(b"\n",1)[0].decode())
"""
    completed = subprocess.run(
        [sys.executable, "-c", child_program, str(socket_path), json.dumps(bypass_request)],
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    )
    refused = json.loads(completed.stdout)
    assert refused["ok"] is False
    assert refused["error"] == "REQUEST_REFUSED"
    assert session.calls == 0

    authorized = relay_request(
        socket_path,
        {
            **bypass_request,
            "request_id": "c" * 32,
        },
        timeout=2,
    )
    assert authorized["ok"] is True
    assert authorized["result"]["isError"] is False
    assert session.calls == 1

    relay.stop()
    thread.join(timeout=3)
    assert not thread.is_alive()


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
        owner_pid=os.getpid(),
        parent_pid=os.getppid(),
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
        owner_pid=os.getpid(),
        parent_pid=os.getppid(),
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
        owner_pid=os.getpid(),
        parent_pid=os.getppid(),
        expires_at_ms=2000,
        clock_ms=lambda: now["value"],
    )
    relay._retirement_guard = lambda: nullcontext(True)  # synthetic terminal-owner proof
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
        owner_pid=os.getpid(),
        parent_pid=4242,
    )
    relay._retirement_guard = lambda: nullcontext(True)  # synthetic terminal-owner proof
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    relay.wait_ready(timeout=3)
    assert socket_path.exists()
    observed_parent["pid"] = 1
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert not socket_path.exists()


@pytest.mark.parametrize("trigger", ["expiry", "parent_loss"])
def test_automatic_retirement_retains_target_when_evidence_not_terminal(tmp_path, monkeypatch, trigger):
    from contextlib import contextmanager
    import integrations.workbench_browser_mcp.relay as module

    parent = [4242]
    now = [1000]
    monkeypatch.setattr(module.os, "getppid", lambda: parent[0])
    session = _CountingSession()
    relay = BrowserRelayServer(
        resource_id="a" * 32, socket_path=tmp_path / "retained.sock", session=session,
        owner_pid=os.getpid(), parent_pid=4242, expires_at_ms=2000,
        clock_ms=lambda: now[0],
    )
    checked = threading.Event()

    @contextmanager
    def guard():
        checked.set()
        yield False

    relay._retirement_guard = guard
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    relay.wait_ready(timeout=3)
    try:
        if trigger == "expiry":
            now[0] = 2000
        else:
            parent[0] = 1
        assert checked.wait(1), "automatic retirement must consult existing effect evidence"
        assert thread.is_alive(), "an uncertain target must survive automatic retirement"
        assert session.receipt.child_pid == os.getpid()
        status = relay_request(relay._socket_path, {
            "schema": RELAY_REQUEST_SCHEMA, "kind": "status",
            "request_id": "b" * 32, "resource_id": "a" * 32,
        }, timeout=2)
        assert status["ok"] is True and status["admission_closed"] is True
        refused = relay_request(relay._socket_path, {
            "schema": RELAY_REQUEST_SCHEMA, "kind": "tool",
            "request_id": "c" * 32, "resource_id": "a" * 32,
            "tool": "browser_click", "arguments": {"target": "button"},
        }, timeout=2)
        assert refused["ok"] is False and refused["error"] == "REQUEST_REFUSED"
        assert session.calls == 0
    finally:
        relay.stop()
        thread.join(timeout=3)
        assert not thread.is_alive()


def test_expiry_at_handle_time_refuses_and_cannot_reopen_on_clock_rollback(tmp_path):
    now = [2000]
    session = _CountingSession()
    session.start()
    relay = BrowserRelayServer(
        resource_id="a" * 32, socket_path=tmp_path / "late.sock", session=session,
        owner_pid=os.getpid(), parent_pid=os.getppid(), expires_at_ms=2000,
        clock_ms=lambda: now[0],
    )
    request = {"schema": RELAY_REQUEST_SCHEMA, "kind": "tool", "request_id": "b" * 32,
               "resource_id": "a" * 32, "tool": "browser_click", "arguments": {"target": "button"}}
    try:
        assert relay._handle(request)["ok"] is False
        now[0] = 1000
        assert relay._handle(request)["ok"] is False
        assert session.calls == 0
    finally:
        session.close()


def test_response_write_loss_does_not_destroy_browser_target(tmp_path, monkeypatch):
    session = _CountingSession()
    relay = BrowserRelayServer(
        resource_id="a" * 32, socket_path=tmp_path / "lost.sock", session=session,
        owner_pid=os.getpid(), parent_pid=os.getppid(),
    )
    original = relay._write_response
    lost = threading.Event()

    def lose_tool_response(connection, response):
        if "result" in response:
            lost.set()
            raise BrokenPipeError("synthetic caller disconnected after native action")
        return original(connection, response)

    monkeypatch.setattr(relay, "_write_response", lose_tool_response)
    failures = []

    def run():
        try:
            relay.serve_forever()
        except BaseException as error:
            failures.append(type(error).__name__)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    relay.wait_ready(timeout=3)
    try:
        with pytest.raises(BrowserRelayError):
            relay_request(relay._socket_path, {
                "schema": RELAY_REQUEST_SCHEMA, "kind": "tool", "request_id": "b" * 32,
                "resource_id": "a" * 32, "tool": "browser_click", "arguments": {"target": "button"},
            }, timeout=2)
        assert lost.wait(1)
        thread.join(timeout=0.1)
        assert not failures and thread.is_alive(), "connection loss cannot retire the effect target"
        assert session.calls == 1
        assert session.receipt.child_pid == os.getpid()
    finally:
        relay.stop()
        thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.mark.parametrize("trigger", ["already_expired", "already_orphaned"])
def test_relay_never_starts_native_child_under_retired_authority(tmp_path, trigger):
    session = _CountingSession()
    started = []
    original_start = session.start

    def start():
        started.append(True)
        return original_start()

    session.start = start
    relay = BrowserRelayServer(
        resource_id="a"*32, socket_path=tmp_path / "not-started.sock", session=session,
        owner_pid=os.getpid(), parent_pid=os.getppid() if trigger=="already_expired" else os.getppid()+100,
        expires_at_ms=2000, clock_ms=lambda: 2000 if trigger=="already_expired" else 1000,
        retirement_guard=lambda: nullcontext(True),
    )
    with pytest.raises(BrowserRelayError):
        relay.serve_forever()
    assert started == []
    assert not relay._socket_path.exists()


@pytest.mark.parametrize("guard", [None, lambda: True])
def test_absent_or_invalid_retirement_proof_cannot_close_target(tmp_path, guard):
    session = _CountingSession()
    session.start()
    relay = BrowserRelayServer(
        resource_id="a"*32, socket_path=tmp_path / "no-proof.sock", session=session,
        owner_pid=os.getpid(), parent_pid=os.getppid(), retirement_guard=guard,
    )
    try:
        assert relay._try_automatic_retirement() is False
        assert relay._admission_closed is True
        assert session.receipt.child_pid == os.getpid()
    finally:
        session.close()


def test_lost_status_reply_does_not_quarantine_an_unmodified_resource(tmp_path, monkeypatch):
    session = _CountingSession()
    relay = BrowserRelayServer(
        resource_id="a"*32, socket_path=tmp_path / "status-loss.sock", session=session,
        owner_pid=os.getpid(), parent_pid=os.getppid(),
    )
    original = relay._write_response
    first = [True]

    def lose_first_status(connection, response):
        if first[0] and "child_pid" in response:
            first[0] = False
            raise BrokenPipeError("synthetic lost read-only status reply")
        return original(connection, response)

    monkeypatch.setattr(relay, "_write_response", lose_first_status)
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    relay.wait_ready(timeout=3)
    request = {"schema":RELAY_REQUEST_SCHEMA,"kind":"status","request_id":"b"*32,"resource_id":"a"*32}
    try:
        with pytest.raises(BrowserRelayError):
            relay_request(relay._socket_path,request,timeout=2)
        status = relay_request(relay._socket_path,request,timeout=2)
        assert status["ok"] is True and status["admission_closed"] is False
        result = relay_request(relay._socket_path,{**request,"kind":"tool","tool":"browser_click",
                                                  "arguments":{"target":"button"}},timeout=2)
        assert result["ok"] is True and session.calls == 1
    finally:
        relay.stop()
        thread.join(timeout=3)
        assert not thread.is_alive()
