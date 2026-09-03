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
    SERVER_VERSION,
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
RESULT_SCHEMA_V2 = "mastermind.secretary_grounding_mcp_result.v2"


def _source(work_ref: str) -> GroundingSource:
    return GroundingSource(
        owner="agent_os",
        source_ref=work_ref,
        observed_at="2026-09-03T20:00:00Z",
    )


def _responsibility_facts(
    subject_ref: str,
    work_ref: str,
    title: str,
) -> tuple[GroundingFact, ...]:
    source = (_source(work_ref),)
    return (
        GroundingFact(
            subject_ref=subject_ref,
            predicate="responsibility.identity",
            value=work_ref,
            freshness="FRESH",
            sources=source,
        ),
        GroundingFact(
            subject_ref=subject_ref,
            predicate="responsibility.title",
            value=title,
            freshness="FRESH",
            sources=source,
        ),
        GroundingFact(
            subject_ref=subject_ref,
            predicate="responsibility.state",
            value="ACTIVE",
            freshness="FRESH",
            sources=source,
        ),
        GroundingFact(
            subject_ref=subject_ref,
            predicate="responsibility.next_action",
            value="Review the current exact gate.",
            freshness="FRESH",
            sources=source,
        ),
    )


class _Port:
    async def _unknown(self) -> StewardGrounding:
        return StewardGrounding(
            state="UNKNOWN",
            facts=(),
            reason_codes=("NO_SOURCE",),
        )

    async def list_responsibilities(self):
        # Intentionally reverse source order. The protected v2 contract owns
        # deterministic subject and predicate ordering.
        return StewardGrounding(
            state="FACTS",
            facts=(
                *_responsibility_facts(
                    "responsibility:beta",
                    "WS:BETA",
                    "Beta responsibility",
                ),
                *_responsibility_facts(
                    "responsibility:alpha",
                    "WS:ALPHA",
                    "Alpha responsibility",
                ),
            ),
            reason_codes=(),
        )

    async def get_responsibility(self, responsibility_ref: str):
        del responsibility_ref
        return await self._unknown()

    async def get_attention(self):
        return await self._unknown()

    async def get_current_runtime(self, responsibility_ref: str):
        del responsibility_ref
        return await self._unknown()

    async def explain_blocker(self, responsibility_ref: str):
        del responsibility_ref
        return await self._unknown()

    async def resolve_surface(self, responsibility_ref: str):
        del responsibility_ref
        return await self._unknown()


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
        output = tool.outputSchema
        assert output["properties"]["schema"] == {"const": RESULT_SCHEMA_V2}
        assert output["properties"]["server_version"] == {"const": "2.0.0"}
        data_schema = output["properties"]["data"]["oneOf"][1]
        assert "subjects" in data_schema["properties"]
        assert "facts" not in data_schema["properties"]
        subject_schema = data_schema["properties"]["subjects"]["items"]
        assert set(subject_schema["properties"]) == {"subject_ref", "facts"}
        nested_fact = subject_schema["properties"]["facts"]["items"]
        assert "subject_ref" not in nested_fact["properties"]

        rendered = tool.model_dump(by_alias=True, exclude_none=True)
        schemes = rendered["securitySchemes"]
        assert schemes == [{"type": "oauth2", "scopes": [REQUIRED_SCOPE]}]
        assert rendered["_meta"]["securitySchemes"] == schemes
        if tool.name == "list_responsibilities":
            assert rendered["_meta"]["ui"] == {"resourceUri": UI_RESOURCE_URI}
            assert rendered["_meta"]["openai/outputTemplate"] == UI_RESOURCE_URI
        else:
            assert "ui" not in rendered["_meta"]
            assert "openai/outputTemplate" not in rendered["_meta"]


def test_low_level_surface_is_six_tools_plus_one_ui_resource_only():
    server = build_mcp_server(build_contract_server(_Port()))
    assert set(server.request_handlers) == {
        mcp_types.ListToolsRequest,
        mcp_types.CallToolRequest,
        mcp_types.ListResourcesRequest,
        mcp_types.ReadResourceRequest,
        mcp_types.PingRequest,
    }


def test_contract_call_returns_grouped_v2_structured_secretary_envelope():
    contract = build_contract_server(_Port())
    result = asyncio.run(contract.call_tool("list_responsibilities", {}))

    assert result["schema"] == RESULT_SCHEMA_V2
    assert result["server_version"] == "2.0.0"
    assert result["tool"] == "list_responsibilities"
    assert result["ok"] is True
    assert set(result["data"]) == {"state", "subjects", "reason_codes"}
    assert "facts" not in result["data"]
    assert result["data"]["state"] == "FACTS"
    assert result["data"]["reason_codes"] == []

    subjects = result["data"]["subjects"]
    assert [row["subject_ref"] for row in subjects] == [
        "responsibility:alpha",
        "responsibility:beta",
    ]
    assert sum(len(row["facts"]) for row in subjects) == 8
    for subject in subjects:
        assert set(subject) == {"subject_ref", "facts"}
        assert [fact["predicate"] for fact in subject["facts"]] == [
            "responsibility.identity",
            "responsibility.title",
            "responsibility.next_action",
            "responsibility.state",
        ]
        for fact in subject["facts"]:
            assert set(fact) == {"predicate", "value", "freshness", "sources"}
            assert "subject_ref" not in fact


def test_describe_and_ui_resource_are_v2_static_self_contained_and_inert():
    payload = json.loads(describe())
    assert payload["server_name"] == SERVER_NAME
    assert payload["server_version"] == SERVER_VERSION == "2.0.0"
    assert payload["tools"] == EXPECTED_TOOLS
    assert payload["required_scope"] == REQUIRED_SCOPE
    assert payload["ui_resource"] == UI_RESOURCE_URI
    assert UI_RESOURCE_URI == "ui://mastermind/steward/control-room-v2.html"
    assert "control-room-v1.html" not in UI_RESOURCE_URI
    assert UI_MIME_TYPE == "text/html;profile=mcp-app"
    assert "<!doctype html>" in CONTROL_ROOM_HTML.lower()
    assert "http://" not in CONTROL_ROOM_HTML
    assert "https://" not in CONTROL_ROOM_HTML
    assert "ui/notifications/tool-result" in CONTROL_ROOM_HTML
    assert "event.source !== window.parent" in CONTROL_ROOM_HTML
    assert 'message.jsonrpc !== "2.0"' in CONTROL_ROOM_HTML
    assert "replaceChildren" in CONTROL_ROOM_HTML
    assert "@media (max-width:480px)" in CONTROL_ROOM_HTML
    assert "data && data.subjects" in CONTROL_ROOM_HTML
    assert "data && data.facts" not in CONTROL_ROOM_HTML
    assert "const MAX_FACTS = 64" in CONTROL_ROOM_HTML
    for state in ("FACTS", "UNKNOWN", "DEGRADED", "REFUSED"):
        assert state in CONTROL_ROOM_HTML
    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "new Function",
        "setTimeout(",
        "setInterval(",
    ):
        assert forbidden not in CONTROL_ROOM_HTML
