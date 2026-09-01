from __future__ import annotations

import asyncio
import json

import mcp.types as mcp_types

from integrations.mastermind_secretary_mcp.adapter import (
    GroundingFact,
    GroundingSource,
    StewardGrounding,
)
from integrations.mastermind_steward_app.server import (
    REQUIRED_SCOPE,
    SERVER_NAME,
    build_contract_server,
    build_mcp_server,
    build_tools,
    describe,
)
from integrations.mastermind_steward_app.ui import (
    CONTROL_ROOM_HTML,
    UI_MIME_TYPE,
    UI_RESOURCE_URI,
)


EXPECTED_TOOLS = [
    "list_responsibilities",
    "get_responsibility",
    "get_attention",
    "get_current_runtime",
    "explain_blocker",
    "resolve_surface",
]


class _Port:
    async def _return(self, predicate: str = "responsibility.state"):
        return StewardGrounding(
            state="FACTS",
            facts=(
                GroundingFact(
                    subject_ref="responsibility:" + "a" * 64,
                    predicate=predicate,
                    value="ACTIVE" if predicate == "responsibility.state" else "UNKNOWN",
                    freshness="FRESH",
                    sources=(
                        GroundingSource(
                            owner="agent_os",
                            source_ref="WS:ALPHA",
                            observed_at="2026-09-01T12:00:00Z",
                        ),
                    ),
                ),
            ),
            reason_codes=(),
        )

    async def list_responsibilities(self):
        return await self._return()

    async def get_responsibility(self, responsibility_ref: str):
        del responsibility_ref
        return await self._return()

    async def get_attention(self):
        return await self._return("attention.state")

    async def get_current_runtime(self, responsibility_ref: str):
        del responsibility_ref
        return await self._return("runtime.state")

    async def explain_blocker(self, responsibility_ref: str):
        del responsibility_ref
        return await self._return("blocker.kind")

    async def resolve_surface(self, responsibility_ref: str):
        del responsibility_ref
        return await self._return("surface.health")


def test_tool_census_schemas_annotations_and_oauth_metadata_are_exact():
    tools = build_tools()
    assert [tool.name for tool in tools] == EXPECTED_TOOLS
    for tool in tools:
        assert isinstance(tool, mcp_types.Tool)
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is False
        assert tool.outputSchema is not None
        rendered = tool.model_dump(by_alias=True, exclude_none=True)
        schemes = rendered["securitySchemes"]
        assert schemes == [{"type": "oauth2", "scopes": [REQUIRED_SCOPE]}]
        assert rendered["_meta"]["securitySchemes"] == schemes


def test_low_level_surface_is_six_tools_plus_one_ui_resource_only():
    server = build_mcp_server(build_contract_server(_Port()))
    assert set(server.request_handlers) == {
        mcp_types.ListToolsRequest,
        mcp_types.CallToolRequest,
        mcp_types.ListResourcesRequest,
        mcp_types.ReadResourceRequest,
        mcp_types.PingRequest,
    }


def test_contract_call_returns_structured_secretary_envelope():
    contract = build_contract_server(_Port())
    result = asyncio.run(contract.call_tool("list_responsibilities", {}))
    assert result["schema"] == "mastermind.secretary_grounding_mcp_result.v1"
    assert result["tool"] == "list_responsibilities"
    assert result["ok"] is True
    assert result["data"]["state"] == "FACTS"


def test_describe_and_ui_resource_are_static_and_self_contained():
    payload = json.loads(describe())
    assert payload["server_name"] == SERVER_NAME
    assert payload["tools"] == EXPECTED_TOOLS
    assert payload["required_scope"] == REQUIRED_SCOPE
    assert payload["ui_resource"] == UI_RESOURCE_URI
    assert UI_MIME_TYPE == "text/html+skybridge"
    assert "<!doctype html>" in CONTROL_ROOM_HTML.lower()
    assert "http://" not in CONTROL_ROOM_HTML
    assert "https://" not in CONTROL_ROOM_HTML
