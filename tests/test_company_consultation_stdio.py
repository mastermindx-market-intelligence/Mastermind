"""Real SDK stdio protocol over pipes; no provider or production host."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import uuid

import pytest

from integrations.mastermind_company_mcp.consultation import (
    COMPANY_CONSULTATION_SERVER_IDENTITY,
    COMPANY_CONSULTATION_SERVER_VERSION,
    COMPANY_CONSULTATION_TOOL_SPECS,
)


def test_real_company_stdio_advertises_exact_catalog_and_preserves_refusal(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root = Path(__file__).resolve().parents[1]
    # The host-owned nonexistent path deterministically refuses before send.
    # No caller identity, endpoint, or retry control exists in the tool schema.
    socket_path = "/private/tmp/mmx-company-unavailable-" + uuid.uuid4().hex
    launcher = tmp_path / "company_stdio_fixture.py"
    launcher.write_text(
        "import asyncio,sys\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        "from integrations.mastermind_company_mcp.server import run_company_consultation_stdio\n"
        f"asyncio.run(run_company_consultation_stdio(socket_path={socket_path!r}, "
        "server_uid=450, timeout_seconds=1.0))\n"
    )

    async def scenario():
        parameters = StdioServerParameters(
            command=sys.executable, args=["-I", "-B", str(launcher)],
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                initialized = await client.initialize()
                assert initialized.serverInfo.name == COMPANY_CONSULTATION_SERVER_IDENTITY
                assert initialized.serverInfo.version == COMPANY_CONSULTATION_SERVER_VERSION
                capabilities = initialized.capabilities.model_dump(exclude_none=True)
                assert set(capabilities) <= {"tools", "experimental"}
                tools = await client.list_tools()
                expected = {spec.name: spec for spec in COMPANY_CONSULTATION_TOOL_SPECS}
                assert len(tools.tools) == len(expected) == 4
                assert {tool.name for tool in tools.tools} == set(expected)
                for tool in tools.tools:
                    assert tool.inputSchema == expected[tool.name].input_schema
                response = await client.call_tool("company.peers", {})
                envelope = json.loads(response.content[0].text)
                assert envelope["tool"] == "company.peers"
                assert envelope["server_identity"] == COMPANY_CONSULTATION_SERVER_IDENTITY
                assert envelope["ok"] is False
                assert envelope["error"]["code"] == "UNAVAILABLE"
                # Caller identity cannot be injected through the semantic tool.
                refused = await client.call_tool("company.peers", {"attempt_id": "foreign"})
                assert refused.isError is True
                assert len((await client.list_tools()).tools) == 4

    asyncio.run(asyncio.wait_for(scenario(), timeout=20.0))


def test_stdio_rejects_invalid_host_binding_before_opening_stdio(monkeypatch):
    from integrations.mastermind_company_mcp import server

    def forbidden():
        raise AssertionError("invalid binding must not open the MCP stream")
    monkeypatch.setattr(server, "stdio_server", forbidden)
    with pytest.raises(ValueError, match="invalid Company host binding"):
        asyncio.run(server.run_company_consultation_stdio(
            socket_path="relative.sock", server_uid=450))
