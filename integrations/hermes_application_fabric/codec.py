"""Lossless supported chat semantics for the incumbent APPLICATION wire.

Unsupported semantics are explicit pre-effect errors. This module performs no
I/O, model selection, identity allocation, retry, accounting or tool execution.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

from .errors import CodecError

MAX_REQUEST_BYTES = 512 * 1024
MAX_RESULT_BYTES = 1024 * 1024
MAX_ARGUMENT_BYTES = 128 * 1024
ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_KEYS = frozenset({"model", "messages", "tools", "tool_choice", "max_tokens",
                   "max_completion_tokens", "temperature", "stop", "stream",
                   "stream_options", "extra_headers"})


def fail(code="hermes_fabric_request_invalid"):
    raise CodecError(code)


def _shape(value: Any, depth=0):
    if depth > 64:
        fail("hermes_fabric_nesting_bound")
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for v in value:
            _shape(v, depth + 1)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for v in value.values():
            _shape(v, depth + 1)
        return
    fail("hermes_fabric_json_invalid")


def json_bytes(value: Any, limit: int) -> bytes:
    try:
        _shape(value)
        data = json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError):
        fail("hermes_fabric_json_invalid")
    if len(data) > limit:
        fail("hermes_fabric_size_bound")
    return data


def _id(value):
    if type(value) is not str or ID.fullmatch(value) is None:
        fail("hermes_fabric_identity_invalid")
    return value


def _object_arguments(value):
    if type(value) is not str:
        fail("hermes_fabric_tool_arguments_invalid")
    try:
        if len(value.encode("utf-8")) > MAX_ARGUMENT_BYTES:
            fail("hermes_fabric_size_bound")

        def pairs(items):
            result = {}
            for key, item in items:
                if key in result:
                    fail("hermes_fabric_duplicate_json_key")
                result[key] = item
            return result

        def constant(_):
            fail("hermes_fabric_json_invalid")

        out = json.loads(value, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError, UnicodeError):
        fail("hermes_fabric_tool_arguments_invalid")
    if type(out) is not dict:
        fail("hermes_fabric_tool_arguments_invalid")
    json_bytes(out, MAX_ARGUMENT_BYTES)
    return out


def _text(value):
    if type(value) is str:
        return value
    if type(value) is not list:
        fail("hermes_fabric_content_unsupported")
    parts = []
    for block in value:
        if (type(block) is not dict or set(block) != {"type", "text"}
                or block["type"] != "text" or type(block["text"]) is not str):
            fail("hermes_fabric_content_unsupported")
        parts.append(block["text"])
    return "".join(parts)


def to_owner_request(kwargs: dict, selected_model: str) -> dict:
    if type(kwargs) is not dict or set(kwargs) - _KEYS:
        fail("hermes_fabric_parameter_unsupported")
    # Snapshot first: the caller cannot mutate a checked nested payload in flight.
    kw = json.loads(json_bytes(kwargs, MAX_REQUEST_BYTES))
    if kw.get("model") != _id(selected_model):
        fail("hermes_fabric_model_selection_mismatch")
    if "extra_headers" in kw:
        # Native Relay adds SDK-shaped traceparent AFTER llm_execution. The
        # native trace already records this call; APPLICATION correlation uses
        # its original request_id. Do not forward arbitrary HTTP/auth headers
        # through an owner API that does not accept header overrides.
        headers = kw["extra_headers"]
        if type(headers) is not dict or len(headers) > 1:
            fail("hermes_fabric_header_unsupported")
        for name, value in headers.items():
            if (name.lower() != "traceparent" or type(value) is not str
                    or re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", value) is None
                    or value[3:35] == "0" * 32 or value[36:52] == "0" * 16):
                fail("hermes_fabric_header_unsupported")
    if "stream" in kw and type(kw["stream"]) is not bool:
        fail()
    if "stream_options" in kw:
        options = kw["stream_options"]
        if (type(options) is not dict or set(options) - {"include_usage"}
                or any(type(v) is not bool for v in options.values())):
            fail()
    if kw.get("stream") is True:
        fail("hermes_fabric_native_stream_unqualified")
    if "max_tokens" in kw and "max_completion_tokens" in kw:
        fail("hermes_fabric_token_budget_invalid")
    maximum = kw.get("max_tokens", kw.get("max_completion_tokens", 4096))
    if type(maximum) is not int or not 1 <= maximum <= 32768:
        fail("hermes_fabric_token_budget_invalid")
    out = {"model": selected_model, "max_tokens": maximum}
    messages = kw.get("messages")
    if type(messages) is not list or not 1 <= len(messages) <= 512:
        fail("hermes_fabric_history_invalid")
    rows, pending, seen = [], set(), set()
    for position, message in enumerate(messages):
        if type(message) is not dict:
            fail("hermes_fabric_history_invalid")
        role = message.get("role")
        allowed = {"role", "content"}
        if role == "assistant":
            allowed.add("tool_calls")
        elif role == "tool":
            allowed.add("tool_call_id")
        if set(message) - allowed or not {"role", "content"} <= set(message):
            fail("hermes_fabric_history_unsupported")
        if role == "system" and position == 0:
            out["system"] = _text(message["content"])
            continue
        if role == "tool":
            ident = _id(message.get("tool_call_id"))
            if ident not in pending:
                fail("hermes_fabric_tool_history_invalid")
            rows.append({"role": "user", "content": [{"type": "tool_result",
                         "tool_use_id": ident, "content": _text(message["content"])}]})
            pending.remove(ident)
            continue
        if role not in {"user", "assistant"} or pending:
            fail("hermes_fabric_tool_history_invalid")
        calls = message.get("tool_calls", [])
        if type(calls) is not list or len(calls) > 64:
            fail("hermes_fabric_tools_invalid")
        content = message["content"]
        if content is None and role == "assistant" and calls:
            text = ""
        else:
            text = _text(content)
        if not calls:
            rows.append({"role": role, "content": text})
            continue
        blocks = [{"type": "text", "text": text}] if text else []
        for call in calls:
            if (type(call) is not dict or set(call) != {"id", "type", "function"}
                    or call["type"] != "function" or type(call["function"]) is not dict
                    or set(call["function"]) != {"name", "arguments"}):
                fail("hermes_fabric_tools_invalid")
            ident = _id(call["id"])
            if ident in seen:
                fail("hermes_fabric_tool_history_invalid")
            seen.add(ident)
            pending.add(ident)
            blocks.append({"type": "tool_use", "id": ident,
                           "name": _id(call["function"]["name"]),
                           "input": _object_arguments(call["function"]["arguments"])})
        rows.append({"role": "assistant", "content": blocks})
    if not rows or pending:
        fail("hermes_fabric_tool_history_invalid")
    out["messages"] = rows
    tools = kw.get("tools", [])
    if type(tools) is not list or len(tools) > 64:
        fail("hermes_fabric_tools_invalid")
    names, converted = set(), []
    for tool in tools:
        if (type(tool) is not dict or set(tool) != {"type", "function"}
                or tool["type"] != "function" or type(tool["function"]) is not dict):
            fail("hermes_fabric_tools_invalid")
        fn = tool["function"]
        if set(fn) - {"name", "description", "parameters"} or "parameters" not in fn:
            fail("hermes_fabric_tool_semantics_unsupported")
        name = _id(fn.get("name"))
        if name in names or type(fn["parameters"]) is not dict:
            fail("hermes_fabric_tools_invalid")
        names.add(name)
        item = {"name": name, "input_schema": fn["parameters"]}
        if "description" in fn:
            if type(fn["description"]) is not str:
                fail("hermes_fabric_tools_invalid")
            item["description"] = fn["description"]
        converted.append(item)
    if converted:
        out["tools"] = converted
    if "tool_choice" in kw:
        choice = kw["tool_choice"]
        if type(choice) is str and choice in {"auto", "none", "required"}:
            if choice == "required" and not names:
                fail("hermes_fabric_tools_invalid")
            out["tool_choice"] = {"type": {"required": "any"}.get(choice, choice)}
        elif (type(choice) is dict and set(choice) == {"type", "function"}
              and choice["type"] == "function" and type(choice["function"]) is dict
              and set(choice["function"]) == {"name"}
              and choice["function"]["name"] in names):
            out["tool_choice"] = {"type": "tool", "name": choice["function"]["name"]}
        else:
            fail("hermes_fabric_tools_invalid")
    if "temperature" in kw:
        value = kw["temperature"]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 2:
            fail()
        out["temperature"] = value
    if "stop" in kw:
        stops = [kw["stop"]] if type(kw["stop"]) is str else kw["stop"]
        if type(stops) is not list or len(stops) > 4 or any(type(x) is not str for x in stops):
            fail()
        out["stop_sequences"] = stops
    json_bytes(out, MAX_REQUEST_BYTES)
    return out


def to_hermes_response(response, *, request_id: str, selected_model: str) -> dict:
    _id(request_id)
    if getattr(response, "model", None) != selected_model:
        fail("hermes_fabric_served_model_mismatch")
    content, stop = getattr(response, "content", None), getattr(response, "stop_reason", None)
    if type(content) is not list or stop not in {"end_turn", "max_tokens", "tool_use"}:
        fail("hermes_fabric_response_invalid")
    text, calls, names = [], [], set()
    for block in content:
        kind = getattr(block, "type", None)
        if kind == "text" and type(getattr(block, "text", None)) is str:
            text.append(block.text)
        elif kind == "tool_use":
            ident, name = _id(getattr(block, "id", None)), _id(getattr(block, "name", None))
            value = getattr(block, "input", None)
            if ident in names or type(value) is not dict or len(calls) >= 64:
                fail("hermes_fabric_tool_response_invalid")
            names.add(ident)
            calls.append({"id": ident, "type": "function", "function": {
                "name": name, "arguments": json_bytes(value, MAX_ARGUMENT_BYTES).decode("utf-8")}})
        else:
            fail("hermes_fabric_response_unsupported")
    if bool(calls) != (stop == "tool_use") or not calls and not "".join(text).strip():
        fail("hermes_fabric_tool_response_invalid")
    usage = getattr(response, "usage", None)
    counts = [getattr(usage, k, None) for k in ("input_tokens", "output_tokens")]
    if any(type(v) is not int or not 0 <= v <= 10**12 for v in counts):
        fail("hermes_fabric_usage_unknown")
    message = {"role": "assistant", "content": "".join(text) or None}
    if calls:
        message["tool_calls"] = calls
    result = {"id": request_id, "object": "chat.completion", "created": 0,
              "model": response.model, "choices": [{"index": 0, "message": message,
              "finish_reason": {"end_turn": "stop", "max_tokens": "length", "tool_use": "tool_calls"}[stop]}],
              "usage": {"prompt_tokens": counts[0], "completion_tokens": counts[1],
                        "total_tokens": sum(counts)}}
    json_bytes(result, MAX_RESULT_BYTES)
    return result
