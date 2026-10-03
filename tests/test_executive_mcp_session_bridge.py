"""Static Session Bridge helper coverage after authenticated-host reconciliation."""
from __future__ import annotations

import asyncio

import pytest

from integrations.session_bridge.gateway import SessionBridgeGateway
from integrations.session_bridge.server import build_handlers, build_mcp_server, build_tools


class Calls:
    def __init__(self):
        self.values = []

    def read(self, kind):
        self.values.append(("read", kind))
        return [{"target_ref": "codex:binding-1"}]

    def send(self, *args):
        self.values.append(("send", args))
        return {"reply_committed": True, "action": "POSTED"}

    def summon(self, args):
        self.values.append(("summon", dict(args)))
        return {"accepted": True, "dispatched": False}


def gateway(calls: Calls) -> SessionBridgeGateway:
    return SessionBridgeGateway(
        target_reader=calls.read,
        reply_sender=calls.send,
        summoner=calls.summon,
    )


def test_static_bridge_helpers_preserve_closed_tool_surface():
    tools = build_tools()
    assert [tool.name for tool in tools] == [
        "session_targets",
        "session_send",
        "session_summon",
    ]
    by_name = {tool.name: tool for tool in tools}
    assert by_name["session_targets"].annotations.readOnlyHint is True
    assert by_name["session_send"].annotations.readOnlyHint is False
    assert by_name["session_summon"].annotations.readOnlyHint is False
    assert all(tool.inputSchema.get("additionalProperties") is False for tool in tools)


def test_handlers_delegate_only_to_existing_gateway():
    calls = Calls()
    handlers = build_handlers(gateway(calls))
    assert set(handlers) == {"session_targets", "session_send", "session_summon"}

    async def exercise():
        targets = await handlers["session_targets"]({"kind": "codex"})
        sent = await handlers["session_send"]({
            "target_ref": "codex:binding-1",
            "instruction": "Continue one bounded task.",
            "stop_condition": "Stop after one result.",
            "operation_key": "session-helper-send-001",
        })
        summoned = await handlers["session_summon"]({
            "objective": "Inspect one bounded issue.",
            "execution_profile": "research_only",
            "operation_key": "session-helper-summon-001",
        })
        return targets, sent, summoned

    targets, sent, summoned = asyncio.run(exercise())
    assert targets["ok"] is True
    assert sent["ok"] is True
    assert summoned["ok"] is True
    assert [item[0] for item in calls.values] == ["read", "send", "summon"]


def test_build_handlers_requires_real_gateway():
    with pytest.raises(TypeError, match="SessionBridgeGateway required"):
        build_handlers(object())


def test_standalone_session_bridge_network_edge_is_refused():
    with pytest.raises(RuntimeError, match="authenticated Executive MCP host"):
        build_mcp_server(gateway(Calls()))
