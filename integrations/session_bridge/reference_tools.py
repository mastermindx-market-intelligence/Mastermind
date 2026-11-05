"""Optional READ-only original-reference discovery on the existing Executive host.

References are original-request provenance, not native COMMIT or parent ACK.
No new socket, database, queue, cursor registry, or SEND authority is added.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.executive_mcp.schemas import GatewayError, ToolSpec
from .installed import InstalledSessionBridgeClient

TOOL_NAME = "session_reply_references"
RESULT_SCHEMA = "mastermind.session_reply_references_result.v1"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_CURSOR = re.compile(r"^[A-Za-z0-9_=-]{1,2048}$")
_MAX_OUTPUT_BYTES = 64 * 1024
_ERRORS = {
    "invalid_input": "invalid original-reference selector",
    "not_found": "unknown original-reference tool",
    "reply_unavailable": "authorized canonical reply references unavailable",
    "output_too_large": "reply references exceed transport budget",
}


class NativeReplyReferencesTool:
    def __init__(self, client: InstalledSessionBridgeClient):
        if type(client) is not InstalledSessionBridgeClient:
            raise TypeError("exact installed Session Bridge client is required")
        self._client = client

    @staticmethod
    def tool_spec() -> ToolSpec:
        return ToolSpec(
            name=TOOL_NAME,
            description="List bounded immutable original-operation references for one "
                        "authorized workstream; REFERENCE_ONLY, not native reply or parent ACK. "
                        "Never sends, retries, consumes, or changes the active command.",
            input_schema={
                "type": "object",
                "properties": {
                    "work_ref": {"type": "string", "minLength": 1, "maxLength": 256},
                    "root_job_id": {"type": "string", "minLength": 1, "maxLength": 256},
                    "cursor": {"type": "string", "minLength": 1, "maxLength": 2048},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 32},
                },
                "required": ["work_ref"],
                "additionalProperties": False,
            },
            output_description=RESULT_SCHEMA, read_only=True,
        )

    @staticmethod
    def validate(name: str, arguments: Any) -> dict:
        if name != TOOL_NAME:
            raise GatewayError("not_found", _ERRORS["not_found"])
        if not isinstance(arguments, Mapping) or not {
                "work_ref"} <= set(arguments) or not set(arguments) <= {
                "work_ref", "root_job_id", "cursor", "page_size"}:
            raise GatewayError("invalid_input", _ERRORS["invalid_input"])
        result = dict(arguments)
        for key in ("work_ref", "root_job_id"):
            if key in result and (
                    type(result[key]) is not str
                    or _TOKEN.fullmatch(result[key]) is None):
                raise GatewayError("invalid_input", _ERRORS["invalid_input"])
        if "cursor" in result and (
                type(result["cursor"]) is not str
                or _CURSOR.fullmatch(result["cursor"]) is None):
            raise GatewayError("invalid_input", _ERRORS["invalid_input"])
        if "page_size" in result and (
                type(result["page_size"]) is not int
                or not 1 <= result["page_size"] <= 32):
            raise GatewayError("invalid_input", _ERRORS["invalid_input"])
        return result

    @staticmethod
    def error(name: str, code: Any, _message: Any = None) -> dict:
        safe = code if isinstance(code, str) and code in _ERRORS else "reply_unavailable"
        return {"schema": RESULT_SCHEMA, "tool": TOOL_NAME, "ok": False,
                "data": None, "error": {"code": safe, "message": _ERRORS[safe]}}

    async def handle(self, principal: Any, name: str, arguments: Any) -> dict:
        try:
            validated = self.validate(name, arguments)
        except GatewayError as exc:
            return self.error(name, exc.code)
        try:
            principal_projection(principal)
            data = await self._client.reply_references(principal, validated)
            if (type(data) is not dict
                    or set(data) != {"schema", "status", "references", "next_cursor", "high_water"}
                    or data["schema"] != "mastermind.session_reply_references.v1"
                    or data["status"] not in ("COMPLETE", "PARTIAL")
                    or type(data["references"]) is not list
                    or len(data["references"]) > validated.get("page_size", 16)
                    or type(data["high_water"]) is not int
                    or data["high_water"] < 0
                    or (data["status"] == "PARTIAL") != (data["next_cursor"] is not None)
                    or (data["next_cursor"] is not None and (
                        type(data["next_cursor"]) is not str
                        or _CURSOR.fullmatch(data["next_cursor"]) is None))):
                raise ValueError("invalid original-reference response")
            expected_keys = {"read_ref", "operation_key", "request_ref",
                             "request_event_id", "request_revision", "requested_at",
                             "work_ref", "root_job_id", "target_ref", "reference_only"}
            for row in data["references"]:
                if (type(row) is not dict or set(row) != expected_keys
                        or row["reference_only"] is not True
                        or row["work_ref"] != validated["work_ref"]
                        or ("root_job_id" in validated
                            and row["root_job_id"] != validated["root_job_id"])
                        or type(row["request_event_id"]) is not int
                        or not 1 <= row["request_event_id"] <= data["high_water"]
                        or any(type(row[key]) is not str or not row[key]
                               for key in expected_keys - {"reference_only", "request_event_id"})):
                    raise ValueError("invalid reference row")
            result = {"schema": RESULT_SCHEMA, "tool": TOOL_NAME,
                      "ok": True, "data": data, "error": None}
            if len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode("ascii")) > _MAX_OUTPUT_BYTES:
                return self.error(name, "output_too_large")
            return result
        except Exception:
            return self.error(name, "reply_unavailable")

    def extend_host_configuration(self, configuration: Mapping[str, Any]) -> dict:
        import mcp.types as mt

        tools = configuration.get("profile_tools")
        validate = configuration.get("profile_validator")
        names = configuration.get("direct_tool_names")
        submit = configuration.get("direct_submit_names")
        handler = configuration.get("direct_handler")
        error = configuration.get("direct_error_factory")
        release = configuration.get("release_tool_names", ())
        if (type(tools) is not tuple or type(names) is not tuple or type(submit) is not tuple
                or not callable(validate) or not callable(handler) or not callable(error)
                or type(release) is not tuple
                or TOOL_NAME in names + submit + release
                or any(t.name == TOOL_NAME for t in tools)
                or len({t.name for t in tools}) != len(tools)
                or not set(submit) <= set(names)
                or not set(names) <= {t.name for t in tools}):
            raise ValueError("reference extension cannot inherit SEND or release authority")
        spec = self.tool_spec()
        tool = mt.Tool(name=spec.name, description=spec.description,
            inputSchema=spec.input_schema, annotations=mt.ToolAnnotations(**spec.annotations))

        def extended_validator(name, arguments):
            return self.validate(name, arguments) if name == TOOL_NAME else validate(name, arguments)

        async def extended_handler(principal, name, arguments):
            if name == TOOL_NAME:
                return await self.handle(principal, name, arguments)
            if name not in names:
                raise GatewayError("not_found", "unknown direct tool")
            return await handler(principal, name, arguments)

        def extended_error(name, code, message):
            if name == TOOL_NAME:
                return self.error(name, code, message)
            if name not in names:
                raise GatewayError("not_found", "unknown direct tool")
            return error(name, code, message)

        return dict(configuration, profile_tools=tools + (tool,),
            profile_validator=extended_validator,
            direct_tool_names=names + (TOOL_NAME,),
            direct_submit_names=submit,
            direct_handler=extended_handler,
            direct_error_factory=extended_error)


__all__ = ["TOOL_NAME", "RESULT_SCHEMA", "NativeReplyReferencesTool"]
