"""Bounded structured JSON over the owner's existing forced-tool protocol.

This is adapter-enforced JSON validation, not a claim of provider-native strict
schema support. The reserved result tool is consumed here, never by Hermes.
There is one owner call and no repair, retry, or fallback on an invalid result.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from .codec import ID, json_bytes, MAX_RESULT_BYTES
from .errors import HermesFabricError

RESULT_TOOL = "mmx_hermes_structured_result"
MAX_SCHEMA_BYTES = 16 * 1024
_KEYWORDS = frozenset({"type", "properties", "required", "additionalProperties",
    "items", "enum", "const", "anyOf", "oneOf", "allOf", "minItems", "maxItems",
    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "title", "description"})


def _reject(code="hermes_fabric_structured_format_unsupported"):
    raise HermesFabricError(code)


def _bounded_schema(schema, depth=0):
    # No references, remote retrieval, recursive schemas, regexes, format checks,
    # or vocabulary extensions. Unknown keywords must not be silently ignored.
    if type(schema) is not dict or depth > 16 or set(schema) - _KEYWORDS:
        _reject()
    properties = schema.get("properties", {})
    if type(properties) is not dict or len(properties) > 128:
        _reject()
    for name, child in properties.items():
        if type(name) is not str or len(name) > 128:
            _reject()
        _bounded_schema(child, depth + 1)
    if "additionalProperties" in schema and type(schema["additionalProperties"]) is not bool:
        _reject()
    if "items" in schema:
        _bounded_schema(schema["items"], depth + 1)
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            children = schema[key]
            if type(children) is not list or not 1 <= len(children) <= 16:
                _reject()
            for child in children:
                _bounded_schema(child, depth + 1)


@dataclass(frozen=True)
class StructuredResult:
    validator: object

    def consume(self, payload: dict) -> dict:
        choice = payload["choices"][0]
        message = choice["message"]
        calls = message.get("tool_calls", [])
        if (choice["finish_reason"] != "tool_calls" or len(calls) != 1
                or calls[0]["function"]["name"] != RESULT_TOOL
                or message.get("content") not in (None, "")):
            _reject("hermes_fabric_structured_result_invalid")
        value = json.loads(calls[0]["function"]["arguments"])
        if type(value) is not dict:
            _reject("hermes_fabric_structured_result_invalid")
        error = None
        try:
            if not self.validator.is_valid(value):
                error = HermesFabricError("hermes_fabric_structured_result_invalid")
        except Exception:
            error = HermesFabricError("hermes_fabric_structured_result_invalid")
        if error is not None:
            raise error
        choice["message"] = {"role": "assistant", "content": json_bytes(value, MAX_RESULT_BYTES).decode("utf-8")}
        choice["finish_reason"] = "stop"
        # All original usage and served-model fields survive unchanged.
        json_bytes(payload, MAX_RESULT_BYTES)
        return payload


def prepare_structured_request(request: dict) -> tuple[dict, StructuredResult | None]:
    if "response_format" not in request:
        return request, None
    if request.get("tools") or "tool_choice" in request or "parallel_tool_calls" in request:
        _reject()
    fmt = request["response_format"]
    if type(fmt) is not dict:
        _reject()
    if fmt == {"type": "json_object"}:
        schema = {"type": "object"}
    elif set(fmt) == {"type", "json_schema"} and fmt["type"] == "json_schema":
        spec = fmt["json_schema"]
        if (type(spec) is not dict or set(spec) - {"name", "schema", "strict", "description"}
                or not {"name", "schema"} <= set(spec)
                or type(spec["name"]) is not str or ID.fullmatch(spec["name"]) is None
                or "strict" in spec and type(spec["strict"]) is not bool
                or "description" in spec and type(spec["description"]) is not str):
            _reject()
        schema = spec["schema"]
    else:
        _reject()
    schema = json.loads(json_bytes(schema, MAX_SCHEMA_BYTES))
    if type(schema) is not dict or schema.get("type") != "object":
        _reject()
    _bounded_schema(schema)
    error = None
    validator = None
    try:
        # Required from the host's qualified dependency closure; the upstream
        # Hermes lock does not guarantee it. No auto-install, network schema
        # resolver, hand-written validator, or permissive fallback.
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except ImportError:
        error = HermesFabricError("hermes_fabric_schema_validator_required")
    except Exception:
        error = HermesFabricError("hermes_fabric_structured_schema_invalid")
    if error is not None:
        raise error
    adapted = {k: v for k, v in request.items() if k not in {"response_format", "tools"}}
    adapted["tools"] = [{"type": "function", "function": {"name": RESULT_TOOL,
        "description": "Return the final structured JSON result; this function is not executed.",
        "parameters": schema}}]
    adapted["tool_choice"] = {"type": "function", "function": {"name": RESULT_TOOL}}
    return adapted, StructuredResult(validator)
