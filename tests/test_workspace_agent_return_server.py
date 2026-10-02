"""Static and SDK-facing fences for the Workspace return MCP surface."""
from __future__ import annotations

import ast
import asyncio
import copy
import json
from pathlib import Path

import pytest

from integrations.workspace_agent_return import (
    RETURN_RESULT_SCHEMA,
    TOOL_NAME,
    WorkspaceCandidateReturnGateway,
    tool_spec,
)


ROOT = Path(__file__).resolve().parent.parent


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_return_contract_is_sdk_free_and_server_is_only_mcp_importer():
    adapter_imports = _imports(ROOT / "integrations" / "workspace_agent_return.py")
    server_imports = _imports(ROOT / "integrations" / "workspace_agent_return_server.py")
    assert not any(name == "mcp" or name.startswith("mcp.") for name in adapter_imports)
    assert any(name == "mcp" or name.startswith("mcp.") for name in server_imports)
    forbidden = {
        "sqlite3",
        "subprocess",
        "keyring",
        "control_plane.executive_runtime",
        "control_plane.wake_ack_ingress",
    }
    assert not (adapter_imports & forbidden)


def test_one_tool_schema_has_no_lifecycle_or_target_selector_fields():
    spec = tool_spec()
    assert spec["name"] == "submit_candidate" == TOOL_NAME
    assert set(spec) == {"name", "description", "input_schema", "annotations"}
    schema = spec["input_schema"]
    assert schema["required"] == ["return_ref", "status", "result"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "return_ref",
        "status",
        "result",
        "evidence_refs",
    }
    rendered = json.dumps(spec, sort_keys=True)
    for forbidden in (
        '"job_id"',
        '"attempt_id"',
        '"worker_id"',
        '"runtime_binding"',
        '"wake_ack"',
        '"accepted": true',
        '"slack_token"',
    ):
        assert forbidden not in rendered
    assert spec["annotations"] == {
        "title": "submit_candidate",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


class _StubGateway(WorkspaceCandidateReturnGateway):
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, copy.deepcopy(arguments)))
        return {
            "schema": RETURN_RESULT_SCHEMA,
            "ok": False,
            "state": "INVALID_REQUEST",
        }


def test_mcp_server_advertises_only_one_tools_only_capability():
    pytest.importorskip("mcp")
    from mcp.server.lowlevel import NotificationOptions

    from integrations.workspace_agent_return_server import build_mcp_server, build_tools

    tools = build_tools()
    assert len(tools) == 1
    tool = tools[0]
    spec = tool_spec()
    assert tool.name == TOOL_NAME
    assert tool.description == spec["description"]
    assert tool.inputSchema == spec["input_schema"]
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.destructiveHint is False
    assert tool.annotations.idempotentHint is True
    assert tool.annotations.openWorldHint is False

    server = build_mcp_server(_StubGateway())
    capabilities = server.get_capabilities(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )
    assert capabilities.tools is not None
    assert capabilities.resources is None
    assert capabilities.prompts is None
    assert capabilities.completions is None
    assert {handler.__name__ for handler in server.request_handlers} == {
        "PingRequest",
        "ListToolsRequest",
        "CallToolRequest",
    }
    assert server.notification_handlers == {}


def test_mcp_call_invokes_gateway_once_and_returns_one_bounded_text_result():
    pytest.importorskip("mcp")
    from mcp import types as mcp_types

    from integrations.workspace_agent_return_server import build_mcp_server

    gateway = _StubGateway()
    server = build_mcp_server(gateway)
    handler = server.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(
            name=TOOL_NAME,
            arguments={
                "return_ref": "synthetic",
                "status": "PASS",
                "result": "candidate",
            },
        )
    )
    response = asyncio.run(handler(request))
    assert gateway.calls == [
        (
            TOOL_NAME,
            {
                "return_ref": "synthetic",
                "status": "PASS",
                "result": "candidate",
            },
        )
    ]
    document = response.model_dump(mode="json", by_alias=True)
    assert len(document["content"]) == 1
    assert document["content"][0]["type"] == "text"
    assert json.loads(document["content"][0]["text"]) == {
        "schema": RETURN_RESULT_SCHEMA,
        "ok": False,
        "state": "INVALID_REQUEST",
    }
