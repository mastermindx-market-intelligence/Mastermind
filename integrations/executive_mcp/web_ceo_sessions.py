"""Authenticated Web-CEO profile adding exact Session Bridge tools."""
from __future__ import annotations

from typing import Any
from integrations.executive_mcp import schemas as legacy
from integrations.executive_mcp import web_ceo as v2
from integrations.session_bridge import schemas as bridge

WEB_CEO_SESSIONS_PROFILE = "web_ceo_sessions_v1"
WEB_CEO_SESSIONS_SERVER_NAME = legacy.SERVER_NAME
WEB_CEO_SESSIONS_SERVER_VERSION = "1.4.0"
SESSION_TOOL_NAMES = ("session_targets", "session_send", "session_summon")
SESSION_SUBMIT_TOOL_NAMES = ("session_send", "session_summon")

def _spec(name: str, description: str, schema: dict[str, Any], *, read_only: bool) -> legacy.ToolSpec:
    return legacy.ToolSpec(name=name, description=description, input_schema=schema,
        output_description="mastermind.session_bridge_result.v1 authenticated Session Bridge result",
        read_only=read_only)

SESSION_TARGETS_SPEC = _spec("session_targets",
    "List exact addressable session targets from the authenticated caller's trusted current projection. Read-only; no target registry is created.",
    {"type":"object","properties":{"kind":{"type":"string","enum":list(bridge.TARGET_KINDS)}},"additionalProperties":False},
    read_only=True)
SESSION_SEND_SPEC = _spec("session_send",
    "Send one governed Agent Dialogue continuation only to an exact target in the authenticated caller projection; native attention remains a separate existing owner.",
    {"type":"object","properties":{
        "target_ref":{"type":"string","minLength":1,"maxLength":256},
        "instruction":{"type":"string","minLength":1,"maxLength":bridge.MAX_INSTRUCTION_CHARS},
        "stop_condition":{"type":"string","minLength":1,"maxLength":bridge.MAX_STOP_CONDITION_CHARS},
        "operation_key":{"type":"string","minLength":1,"maxLength":bridge.MAX_OPERATION_KEY_CHARS}},
     "required":["target_ref","instruction","stop_condition","operation_key"],"additionalProperties":False},
    read_only=False)
SESSION_SUMMON_SPEC = _spec("session_summon",
    "Request existing Executive admission and Capacity placement. Provider, account and host selection are never accepted from the caller.",
    {"type":"object","properties":{
        "objective":{"type":"string","minLength":1,"maxLength":4000},
        "execution_profile":{"type":"string","enum":["bounded_code_change","research_only"]},
        "operation_key":{"type":"string","minLength":1,"maxLength":bridge.MAX_OPERATION_KEY_CHARS}},
     "required":["objective","execution_profile","operation_key"],"additionalProperties":False},
    read_only=False)

if v2.WEB_CEO_V2_TOOL_SPECS[-1].name != legacy.MODIFYING_TOOL:
    raise RuntimeError("Web CEO v2 modifying-tool position changed")
WEB_CEO_SESSIONS_TOOL_SPECS = (v2.WEB_CEO_V2_TOOL_SPECS[:-1] +
    (SESSION_TARGETS_SPEC, SESSION_SEND_SPEC, SESSION_SUMMON_SPEC) +
    v2.WEB_CEO_V2_TOOL_SPECS[-1:])
_BY_NAME = {spec.name: spec for spec in WEB_CEO_SESSIONS_TOOL_SPECS}

def web_ceo_sessions_tool_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in WEB_CEO_SESSIONS_TOOL_SPECS)

def validate_web_ceo_sessions_tool_arguments(tool_name: str, arguments: Any) -> dict[str, Any]:
    if tool_name not in SESSION_TOOL_NAMES:
        return v2.validate_web_ceo_v2_tool_arguments(tool_name, arguments)
    try:
        return bridge.validate_tool_arguments(tool_name, arguments)
    except bridge.BridgeError as exc:
        raise legacy.GatewayError(exc.code, exc.message) from exc
