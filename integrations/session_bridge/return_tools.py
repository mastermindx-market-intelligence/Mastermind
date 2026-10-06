"""Read-only native reply tool for the incumbent authenticated Executive host.

This module supplies one tool and a compile-time composition extension. It starts
no server, registers no default route, changes no OAuth policy and creates no
subscription, identity, retry, acknowledgement or message store. The installed
host must select this extension and provide the existing authorized reply reader.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.executive_mcp.schemas import GatewayError, ToolSpec
from .native_read import NativeReplyReader

TOOL_NAME = "session_reply_read"
RESULT_SCHEMA = "mastermind.session_reply_read_result.v1"
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_MAX_OUTPUT_BYTES = 24 * 1024
_REPLY_KEYS = frozenset({"schema", "read_ref", "request_ref", "in_reply_to", "message_key",
    "fingerprint", "text", "next_step", "primary_ts", "reply_committed", "parent_consumed"})
_ERRORS = {
    "invalid_input": "reply read requires one valid read_ref or original operation_key",
    "not_found": "unknown reply read tool",
    "reply_unavailable": "authorized canonical reply is unavailable",
    "output_too_large": "reply read exceeds the transport budget",
}


class NativeReplyReadTool:
    def __init__(self, reader: NativeReplyReader) -> None:
        from .installed import InstalledSessionBridgeClient
        if type(reader) is NativeReplyReader:
            self._reader = reader
        elif type(reader) is InstalledSessionBridgeClient:
            self._reader = reader.reply_read
        else:
            raise TypeError("the existing canonical reader or installed private client is required")

    @staticmethod
    def tool_spec() -> ToolSpec:
        return ToolSpec(name=TOOL_NAME,
            description="Read the exact canonical native-session reply referenced by an authorized "
                        "original-request notification, or recover it using the original operation_key. "
                        "Read-only; this does not acknowledge consumption, "
                        "send instructions, choose a recipient, or advance a Job.",
            input_schema={"type": "object", "properties": {
                "read_ref": {"type": "string", "minLength": 1, "maxLength": 256},
                "operation_key": {"type": "string", "minLength": 1, "maxLength": 256}},
                "oneOf": [{"required": ["read_ref"]}, {"required": ["operation_key"]}],
                "additionalProperties": False},
            output_description=RESULT_SCHEMA, read_only=True)

    @staticmethod
    def validate(name: str, arguments: Any) -> dict[str, str]:
        if name != TOOL_NAME:
            raise GatewayError("not_found", _ERRORS["not_found"])
        if not isinstance(arguments, Mapping) or set(arguments) not in (
                {"read_ref"}, {"operation_key"}):
            raise GatewayError("invalid_input", _ERRORS["invalid_input"])
        field = next(iter(arguments))
        if not isinstance(arguments[field], str) or _REF.fullmatch(arguments[field]) is None:
            raise GatewayError("invalid_input", _ERRORS["invalid_input"])
        return {field: arguments[field]}

    @staticmethod
    def error(name: str, code: Any, _message: Any = None) -> dict[str, Any]:
        safe_code = code if isinstance(code, str) and code in _ERRORS else "reply_unavailable"
        return {"schema": RESULT_SCHEMA, "tool": TOOL_NAME, "ok": False, "data": None,
                "error": {"code": safe_code, "message": _ERRORS[safe_code]}}

    async def handle(self, principal: Any, name: str, arguments: Any) -> dict[str, Any]:
        try:
            validated = self.validate(name, arguments)
        except GatewayError as exc:
            return self.error(name, exc.code)
        try:
            # Authentication remains with the existing host. Require its exact
            # verified type; a caller-supplied dict is never authentication.
            principal_projection(principal)
            data = await self._reader(principal, validated)
            expected_keys = _REPLY_KEYS | ({"operation_key"} if "operation_key" in validated else set())
            if (type(data) is not dict or set(data) != expected_keys
                    or data["schema"] != "mastermind.native_reply_read.v1"
                    or not isinstance(data["read_ref"], str) or _REF.fullmatch(data["read_ref"]) is None
                    or ("read_ref" in validated and data["read_ref"] != validated["read_ref"])
                    or ("operation_key" in validated and data["operation_key"] != validated["operation_key"])
                    or data["reply_committed"] is not True
                    or data["parent_consumed"] is not False):
                raise ValueError
            result = {"schema": RESULT_SCHEMA, "tool": TOOL_NAME, "ok": True,
                      "data": data, "error": None}
            encoded = json.dumps(result, ensure_ascii=True, allow_nan=False).encode("ascii")
            if len(encoded) > _MAX_OUTPUT_BYTES:
                return self.error(name, "output_too_large")
            return result
        except Exception:
            # Never expose existence of another caller's reply or backend text.
            # Cancellation remains cancellation and this path never writes.
            return self.error(name, "reply_unavailable")

    def extend_host_configuration(self, configuration: Mapping[str, Any]) -> dict[str, Any]:
        """Extend one existing _build_profile_mcp_app configuration in memory.

        Existing tools, dispatch, scopes, settings and app mounts are retained.
        Nothing is installed or exposed until the existing host chooses this
        configuration. No shared server.py edit or secondary listener is needed
        to test the composition; production selection is a separate release gate.
        """
        import mcp.types as mt

        if not isinstance(configuration, Mapping):
            raise ValueError("existing host configuration is required")
        tools = configuration.get("profile_tools")
        validate = configuration.get("profile_validator")
        names = configuration.get("direct_tool_names", ())
        submit = configuration.get("direct_submit_names", ())
        handler = configuration.get("direct_handler")
        error = configuration.get("direct_error_factory")
        release_names = configuration.get("release_tool_names", ())
        if (configuration.get("release_profile", False) is not False
                or type(release_names) is not tuple or TOOL_NAME in release_names):
            raise ValueError("reply read cannot inherit a release/submit policy")
        if (type(tools) is not tuple or not callable(validate)
                or type(names) is not tuple or type(submit) is not tuple
                or any(type(n) is not str for n in names + submit)
                or any(not isinstance(t, mt.Tool) for t in tools)
                or len({t.name for t in tools}) != len(tools)
                or len(names) != len(set(names)) or len(submit) != len(set(submit))
                or not set(submit) <= set(names)
                or not set(names) <= {t.name for t in tools}
                or (names and (not callable(handler) or not callable(error)))
                or TOOL_NAME in names + submit or any(t.name == TOOL_NAME for t in tools)):
            raise ValueError("existing host composition is invalid or already contains reply read")
        spec = self.tool_spec()
        native_tool = mt.Tool(name=spec.name, description=spec.description,
            inputSchema=spec.input_schema, annotations=mt.ToolAnnotations(**spec.annotations))

        def extended_validator(name, arguments):
            return self.validate(name, arguments) if name == TOOL_NAME else validate(name, arguments)

        async def extended_handler(principal, name, arguments):
            if name == TOOL_NAME:
                return await self.handle(principal, name, arguments)
            if name not in names or handler is None:
                raise GatewayError("not_found", "unknown direct tool")
            return await handler(principal, name, arguments)

        def extended_error(name, code, message):
            if name == TOOL_NAME:
                return self.error(name, code, message)
            if name not in names or error is None:
                raise GatewayError("not_found", "unknown direct tool")
            return error(name, code, message)

        return dict(configuration, profile_tools=tools + (native_tool,),
            profile_validator=extended_validator, direct_tool_names=names + (TOOL_NAME,),
            direct_submit_names=submit, direct_handler=extended_handler,
            direct_error_factory=extended_error)


__all__ = ["TOOL_NAME", "RESULT_SCHEMA", "NativeReplyReadTool"]
