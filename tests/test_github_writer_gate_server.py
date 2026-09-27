"""Real MCP protocol over in-memory transport; synthetic owner/HTTP only."""
import asyncio
from datetime import timedelta
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from integrations.mastermind_github_app.server import build_tools
from integrations.mastermind_github_app.writer_gate_server import build_read_only_mcp_server
from test_github_writer_gate_port import Owner, port


def test_mcp_advertises_only_read_tool_and_returns_canonical_receipt():
    owner = Owner()
    async def scenario():
        server = build_read_only_mcp_server(port(owner))
        async with create_connected_server_and_client_session(server, read_timeout_seconds=timedelta(seconds=5)) as client:
            tools = (await client.list_tools()).tools
            assert [tool.name for tool in tools] == ["source_continuity_writer_gate"]
            assert tools[0].annotations.readOnlyHint is True
            result = await client.call_tool(tools[0].name, {"operation_key": "operation:test"})
            assert result.isError is False
            receipt = json.loads(result.content[0].text)
            assert receipt["schema"] == "mastermind.source_continuity_writer_gate/v1"
            assert receipt["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
            assert receipt["merge_authorized"] is False
            assert "synthetic-service-value" not in result.model_dump_json()
    asyncio.run(scenario())
    assert len(owner.calls) == 8 and owner.token_calls == 1
    assert [tool.name for tool in build_tools()] == [
        "prepare_exact_branch_repair", "commit_exact_branch_repair", "reconcile_exact_branch_repair"]


@pytest.mark.parametrize("arguments", [None, {}, {"operation_key": "operation:test", "repository": "private-input-not-for-output"},
    {"operation_key": 42}])
def test_mcp_rejects_invalid_arguments_before_principal_or_http(arguments):
    owner = Owner()
    async def scenario():
        server = build_read_only_mcp_server(port(owner))
        async with create_connected_server_and_client_session(server, read_timeout_seconds=timedelta(seconds=5)) as client:
            result = await client.call_tool("source_continuity_writer_gate", arguments)
            assert result.isError is True
            assert json.loads(result.content[0].text)["code"] == "INPUT_REFUSED"
            assert "private-input-not-for-output" not in result.model_dump_json()
    asyncio.run(scenario())
    assert owner.token_calls == 0 and owner.calls == []


def test_disarmed_mcp_tool_cannot_read_installation_identity():
    owner = Owner()
    async def scenario():
        server = build_read_only_mcp_server(port(owner, enabled=False))
        async with create_connected_server_and_client_session(server, read_timeout_seconds=timedelta(seconds=5)) as client:
            result = await client.call_tool("source_continuity_writer_gate", {"operation_key": "operation:test"})
            assert result.isError is True
            assert json.loads(result.content[0].text)["code"] == "PRODUCTION_DISARMED"
    asyncio.run(scenario())
    assert owner.token_calls == 0 and owner.calls == []


def test_mcp_permission_denial_is_not_a_successful_unavailable_gate():
    owner = Owner()
    owner.status = 403
    async def scenario():
        server = build_read_only_mcp_server(port(owner))
        async with create_connected_server_and_client_session(server, read_timeout_seconds=timedelta(seconds=5)) as client:
            result = await client.call_tool("source_continuity_writer_gate", {"operation_key": "operation:test"})
            assert result.isError is True
            failure = json.loads(result.content[0].text)
            assert failure["code"] == "GITHUB_PERMISSION_DENIED" and failure["receipt"] is None
            assert "private-upstream-detail" not in result.model_dump_json()
    asyncio.run(scenario())
    assert len(owner.calls) == 1
