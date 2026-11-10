"""Anthropic Messages <-> OpenAI chat-completions translation (pure functions).

The unified router speaks the Anthropic wire to T3 and may forward to pools
that only speak the OpenAI wire. Translation is total and closed: unknown
block types raise ``WireTranslationError`` instead of being dropped silently,
and a translated stream never invents content the upstream did not send.
"""
from __future__ import annotations

import json
from typing import Any


class WireTranslationError(ValueError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise WireTranslationError(reason)


def _inline_context_text(content: Any) -> str:
    """Preserve T3 inline context; unsupported context must never disappear."""
    if isinstance(content, str):
        return content
    _require(isinstance(content, list), "FABRIC_TRANSLATE_CONTENT")
    parts = []
    for block in content:
        _require(isinstance(block, dict) and block.get("type") == "text",
                 "FABRIC_TRANSLATE_BLOCK")
        text = block.get("text", "")
        _require(isinstance(text, str), "FABRIC_TRANSLATE_CONTENT")
        if text:
            parts.append(text)
    return "\n".join(parts)


def anthropic_to_openai(body: dict) -> dict:
    """Anthropic Messages request -> OpenAI chat/completions request."""
    _require(isinstance(body, dict), "FABRIC_TRANSLATE_BODY")
    messages: list[dict] = []
    system = body.get("system")
    if isinstance(system, str) and system:
        messages.append({"role": "system", "content": system})
    elif isinstance(system, list):
        text = "\n".join(block.get("text", "") for block in system
                         if isinstance(block, dict) and block.get("type") == "text")
        if text:
            messages.append({"role": "system", "content": text})
    for message in body.get("messages", []):
        _require(isinstance(message, dict), "FABRIC_TRANSLATE_MESSAGE")
        role = message.get("role")
        content = message.get("content")
        blocks = content if isinstance(content, list) else (
            [{"type": "text", "text": content}] if isinstance(content, str) else [])
        if role == "user":
            parts, tool_results = [], []
            for block in blocks:
                kind = block.get("type")
                if kind == "text":
                    text = block.get("text", "")
                    _require(isinstance(text, str), "FABRIC_TRANSLATE_CONTENT")
                    if text:
                        parts.append({"type": "text", "text": text})
                elif kind == "tool_result":
                    tool_results.append(block)
                elif kind == "image":
                    source = block.get("source") or {}
                    if source.get("type") == "base64":
                        parts.append({"type": "image_url", "image_url": {
                            "url": f"data:{source.get('media_type','image/png')};base64,"
                                   f"{source.get('data','')}"}});
                else:
                    raise WireTranslationError("FABRIC_TRANSLATE_BLOCK")
            if parts:
                messages.append({"role": "user", "content": parts})
            for block in tool_results:
                inner = block.get("content")
                if isinstance(inner, list):
                    text = "\n".join(p.get("text", "") for p in inner
                                     if isinstance(p, dict) and p.get("type") == "text")
                else:
                    text = inner if isinstance(inner, str) else json.dumps(inner)
                messages.append({"role": "tool", "tool_call_id": block.get("tool_use_id", ""),
                                 "content": text})
        elif role == "assistant":
            text_parts, tool_calls = [], []
            for block in blocks:
                kind = block.get("type")
                if kind == "text":
                    text_parts.append(block.get("text", ""))
                elif kind == "tool_use":
                    tool_calls.append({"id": block.get("id", ""), "type": "function",
                                       "function": {"name": block.get("name", ""),
                                                    "arguments": json.dumps(
                                                        block.get("input") or {})}})
                elif kind == "thinking":
                    continue
                else:
                    raise WireTranslationError("FABRIC_TRANSLATE_BLOCK")
            entry: dict[str, Any] = {"role": "assistant",
                                     "content": "\n".join(text_parts) or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            messages.append(entry)
        elif role in ("system", "developer"):
            text = _inline_context_text(content)
            if text:
                messages.append({"role": "system", "content": text})
        else:
            raise WireTranslationError("FABRIC_TRANSLATE_ROLE")
    request: dict = {"model": body.get("model"), "messages": messages,
                     "max_tokens": body.get("max_tokens")}
    if body.get("stream") is True:
        request["stream"] = True
        request["stream_options"] = {"include_usage": True}
    for source, target in (("temperature", "temperature"), ("top_p", "top_p")):
        if isinstance(body.get(source), (int, float)):
            request[target] = body[source]
    if body.get("stop_sequences"):
        request["stop"] = body["stop_sequences"]
    tools = body.get("tools")
    if isinstance(tools, list) and tools:
        request["tools"] = [{"type": "function", "function": {
            "name": tool.get("name", ""),
            "description": tool.get("description", "") or None,
            "parameters": tool.get("input_schema") or {"type": "object"}}}
            for tool in tools if isinstance(tool, dict)]
        choice = body.get("tool_choice")
        if isinstance(choice, dict):
            if choice.get("type") == "any":
                request["tool_choice"] = "required"
            elif choice.get("type") == "tool":
                request["tool_choice"] = {"type": "function",
                                          "function": {"name": choice.get("name", "")}}
            else:
                request["tool_choice"] = "auto"
    return request


def openai_to_anthropic(payload: dict, *, model: str) -> dict:
    """OpenAI chat/completions response -> Anthropic Messages response."""
    _require(isinstance(payload, dict) and isinstance(payload.get("choices"), list)
             and payload["choices"], "FABRIC_TRANSLATE_RESPONSE")
    message = payload["choices"][0].get("message") or {}
    content: list[dict] = []
    text = message.get("content")
    if isinstance(text, str) and text:
        content.append({"type": "text", "text": text})
    tool_calls = message.get("tool_calls") or []
    for call in tool_calls:
        _require(isinstance(call, dict), "FABRIC_TRANSLATE_TOOL_CALL")
        function = call.get("function") or {}
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except ValueError:
            raise WireTranslationError("FABRIC_TRANSLATE_TOOL_ARGUMENTS") from None
        content.append({"type": "tool_use", "id": call.get("id", ""),
                        "name": function.get("name", ""), "input": arguments})
    if not content:
        content.append({"type": "text", "text": ""})
    finish = payload["choices"][0].get("finish_reason")
    stop_reason = {"tool_calls": "tool_use", "function_call": "tool_use",
                   "length": "max_tokens"}.get(finish, "end_turn")
    usage = payload.get("usage") or {}
    return {"id": payload.get("id") or "msg_fabric", "type": "message",
            "role": "assistant", "model": model, "content": content,
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": usage.get("prompt_tokens", 0),
                      "output_tokens": usage.get("completion_tokens", 0)}}


class OpenAIStreamTranslator:
    """Incremental OpenAI chat chunks -> Anthropic Messages SSE events."""

    def __init__(self, *, model: str):
        self.model = model
        self._text_open = False
        self._tools: dict[int, dict] = {}
        self._finish: str | None = None
        self._usage: dict = {}

    def _events(self, event: str, data: dict) -> tuple[str, str]:
        return event, json.dumps(data, separators=(",", ":"))

    def message_start(self) -> tuple[str, str]:
        return self._events("message_start", {"type": "message_start", "message": {
            "id": "msg_fabric", "type": "message", "role": "assistant",
            "model": self.model, "content": [], "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0}}})

    def feed(self, chunk: dict) -> list[tuple[str, str]]:
        _require(isinstance(chunk, dict), "FABRIC_TRANSLATE_CHUNK")
        out: list[tuple[str, str]] = []
        usage = chunk.get("usage")
        if isinstance(usage, dict):
            self._usage = usage
        for choice in chunk.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta") or {}
            piece = delta.get("content")
            if isinstance(piece, str) and piece:
                if not self._text_open:
                    out.append(self._events("content_block_start", {
                        "type": "content_block_start", "index": 0,
                        "content_block": {"type": "text", "text": ""}}))
                    self._text_open = True
                out.append(self._events("content_block_delta", {
                    "type": "content_block_delta", "index": 0,
                    "delta": {"type": "text_delta", "text": piece}}))
            for call in delta.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                index = call.get("index", 0)
                tool = self._tools.get(index)
                function = call.get("function") or {}
                if tool is None:
                    tool = self._tools[index] = {
                        "id": call.get("id", f"toolu_{index}"),
                        "name": function.get("name", ""),
                        "arguments": "", "emitted": False}
                if call.get("id"):
                    tool["id"] = call["id"]
                if function.get("name"):
                    tool["name"] = function["name"]
                if function.get("arguments"):
                    tool["arguments"] += function["arguments"]
            if choice.get("finish_reason"):
                self._finish = choice["finish_reason"]
        return out

    def finish(self) -> list[tuple[str, str]]:
        _require(self._finish is not None, "FABRIC_STREAM_INCOMPLETE")
        out: list[tuple[str, str]] = []
        block_index = 1 if self._text_open else 0
        if self._text_open:
            out.append(self._events("content_block_stop", {
                "type": "content_block_stop", "index": 0}))
            self._text_open = False
        for index in sorted(self._tools):
            tool = self._tools[index]
            try:
                arguments = json.loads(tool["arguments"] or "{}")
            except ValueError:
                raise WireTranslationError("FABRIC_TRANSLATE_TOOL_ARGUMENTS") from None
            out.append(self._events("content_block_start", {
                "type": "content_block_start", "index": block_index,
                "content_block": {"type": "tool_use", "id": tool["id"],
                                  "name": tool["name"], "input": {}}}))
            out.append(self._events("content_block_delta", {
                "type": "content_block_delta", "index": block_index,
                "delta": {"type": "input_json_delta",
                          "partial_json": json.dumps(arguments,
                                                      separators=(",", ":"))}}))
            out.append(self._events("content_block_stop", {
                "type": "content_block_stop", "index": block_index}))
            block_index += 1
        stop_reason = {"tool_calls": "tool_use", "function_call": "tool_use",
                       "length": "max_tokens"}.get(self._finish or "", "end_turn")
        out.append(self._events("message_delta", {
            "type": "message_delta", "delta": {"stop_reason": stop_reason,
                                               "stop_sequence": None},
            "usage": {"output_tokens": self._usage.get("completion_tokens", 0)}}))
        out.append(self._events("message_stop", {"type": "message_stop"}))
        return out


# ── OpenAI Responses wire (ChatGPT codex backend) ─────────────────────────────

def anthropic_to_responses(body: dict) -> dict:
    """Anthropic Messages request -> OpenAI Responses request (closed)."""
    _require(isinstance(body, dict), "FABRIC_TRANSLATE_BODY")
    input_items: list[dict] = []
    system = body.get("system")
    instructions: str | None = None
    if isinstance(system, str) and system:
        instructions = system
    elif isinstance(system, list):
        text = "\n".join(block.get("text", "") for block in system
                         if isinstance(block, dict) and block.get("type") == "text")
        if text:
            instructions = text
    for message in body.get("messages", []):
        _require(isinstance(message, dict), "FABRIC_TRANSLATE_MESSAGE")
        role = message.get("role")
        content = message.get("content")
        blocks = content if isinstance(content, list) else (
            [{"type": "text", "text": content}] if isinstance(content, str) else [])
        if role == "user":
            parts: list[dict] = []
            for block in blocks:
                kind = block.get("type")
                if kind == "text":
                    text = block.get("text", "")
                    _require(isinstance(text, str), "FABRIC_TRANSLATE_CONTENT")
                    if text:
                        parts.append({"type": "input_text", "text": text})
                elif kind == "image":
                    source = block.get("source") or {}
                    if source.get("type") == "base64":
                        parts.append({"type": "input_image",
                                      "image_url":
                                          f"data:{source.get('media_type','image/png')}"
                                          f";base64,{source.get('data','')}"})
                elif kind == "tool_result":
                    inner = block.get("content")
                    if isinstance(inner, list):
                        text = "\n".join(p.get("text", "") for p in inner
                                         if isinstance(p, dict)
                                         and p.get("type") == "text")
                    else:
                        text = inner if isinstance(inner, str) else json.dumps(inner)
                    input_items.append({"type": "function_call_output",
                                        "call_id": block.get("tool_use_id", ""),
                                        "output": text})
                else:
                    raise WireTranslationError("FABRIC_TRANSLATE_BLOCK")
            if parts:
                input_items.append({"role": "user", "content": parts})
        elif role == "assistant":
            parts = []
            calls = []
            for block in blocks:
                kind = block.get("type")
                if kind == "text":
                    parts.append({"type": "output_text",
                                  "text": block.get("text", "")})
                elif kind == "tool_use":
                    calls.append({"type": "function_call",
                                  "call_id": block.get("id", ""),
                                  "name": block.get("name", ""),
                                  "arguments": json.dumps(
                                      block.get("input") or {},
                                      separators=(",", ":"))})
                elif kind == "thinking":
                    continue
                else:
                    raise WireTranslationError("FABRIC_TRANSLATE_BLOCK")
            if parts:
                input_items.append({"role": "assistant", "content": parts})
            input_items.extend(calls)
        elif role in ("system", "developer"):
            text = _inline_context_text(content)
            if text:
                input_items.append({"role": "developer", "content": [
                    {"type": "input_text", "text": text}]})
        else:
            raise WireTranslationError("FABRIC_TRANSLATE_ROLE")
    request: dict = {"model": body.get("model"), "input": input_items,
                     "max_output_tokens": body.get("max_tokens"),
                     "store": False}
    if instructions is not None:
        request["instructions"] = instructions
    if body.get("stream") is True:
        request["stream"] = True
    for source, target in (("temperature", "temperature"), ("top_p", "top_p")):
        if isinstance(body.get(source), (int, float)):
            request[target] = body[source]
    tools = body.get("tools")
    if isinstance(tools, list) and tools:
        request["tools"] = [{"type": "function", "name": tool.get("name", ""),
                             "description": tool.get("description", "") or None,
                             "parameters": tool.get("input_schema")
                             or {"type": "object"}}
                            for tool in tools if isinstance(tool, dict)]
        choice = body.get("tool_choice")
        if isinstance(choice, dict):
            if choice.get("type") == "any":
                request["tool_choice"] = "required"
            elif choice.get("type") == "tool":
                request["tool_choice"] = {"type": "function",
                                          "name": choice.get("name", "")}
            else:
                request["tool_choice"] = "auto"
    return request


def responses_to_anthropic(payload: dict, *, model: str) -> dict:
    """OpenAI Responses response -> Anthropic Messages response (closed)."""
    _require(isinstance(payload, dict) and isinstance(payload.get("output"), list),
             "FABRIC_TRANSLATE_RESPONSE")
    content: list[dict] = []
    finish = "end_turn"
    for item in payload["output"]:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "message":
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        content.append({"type": "text", "text": text})
        elif kind == "function_call":
            try:
                arguments = json.loads(item.get("arguments") or "{}")
            except ValueError:
                raise WireTranslationError(
                    "FABRIC_TRANSLATE_TOOL_ARGUMENTS") from None
            content.append({"type": "tool_use", "id": item.get("call_id", ""),
                            "name": item.get("name", ""), "input": arguments})
            finish = "tool_use"
        elif kind == "reasoning":
            continue
        else:
            continue
    if not content:
        content.append({"type": "text", "text": ""})
    status = payload.get("status")
    if status == "incomplete" and finish != "tool_use":
        finish = "max_tokens"
    usage = payload.get("usage") or {}
    return {"id": payload.get("id") or "msg_fabric", "type": "message",
            "role": "assistant", "model": model, "content": content,
            "stop_reason": finish, "stop_sequence": None,
            "usage": {"input_tokens": usage.get("input_tokens", 0),
                      "output_tokens": usage.get("output_tokens", 0)}}


class ResponsesStreamTranslator:
    """Incremental Responses events -> Anthropic Messages SSE events."""

    def __init__(self, *, model: str, retain_text: bool = True):
        self.model = model
        self._text_open = False
        self._calls: dict[str, dict] = {}
        self._order: list[str] = []
        self._finish: str | None = None
        self._usage: dict = {}
        self._block_index = 0
        self._text_parts: list[str] = []
        self._retain_text = retain_text
        self.completed = False
        self._item_to_call: dict[str, str] = {}

    def to_message(self) -> dict:
        """Assemble the accumulated stream into one Messages response."""
        _require(self.completed, "FABRIC_STREAM_INCOMPLETE")
        content: list[dict] = []
        text = "".join(self._text_parts)
        if text:
            content.append({"type": "text", "text": text})
        for call_id in self._order:
            tool = self._calls[call_id]
            try:
                arguments = json.loads(tool["arguments"] or "{}")
            except ValueError:
                raise WireTranslationError(
                    "FABRIC_TRANSLATE_TOOL_ARGUMENTS") from None
            content.append({"type": "tool_use", "id": tool["id"],
                            "name": tool["name"], "input": arguments})
        if not content:
            content.append({"type": "text", "text": ""})
        return {"id": "msg_fabric", "type": "message", "role": "assistant",
                "model": self.model, "content": content,
                "stop_reason": self._finish or (
                    "tool_use" if self._order else "end_turn"),
                "stop_sequence": None,
                "usage": {"input_tokens": self._usage.get("input_tokens", 0),
                          "output_tokens": self._usage.get("output_tokens", 0)}}

    def _events(self, event: str, data: dict) -> tuple[str, str]:
        return event, json.dumps(data, separators=(",", ":"))

    def message_start(self) -> tuple[str, str]:
        return self._events("message_start", {"type": "message_start", "message": {
            "id": "msg_fabric", "type": "message", "role": "assistant",
            "model": self.model, "content": [], "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0}}})

    def feed(self, event: dict) -> list[tuple[str, str]]:
        _require(isinstance(event, dict), "FABRIC_TRANSLATE_CHUNK")
        out: list[tuple[str, str]] = []
        kind = event.get("type")
        if kind in {"error", "response.failed"}:
            raise WireTranslationError("FABRIC_UPSTREAM_STREAM_ERROR")
        if kind == "response.output_text.delta":
            piece = event.get("delta")
            if isinstance(piece, str) and piece:
                if self._retain_text:
                    self._text_parts.append(piece)
                if not self._text_open:
                    out.append(self._events("content_block_start", {
                        "type": "content_block_start", "index": self._block_index,
                        "content_block": {"type": "text", "text": ""}}))
                    self._text_open = True
                out.append(self._events("content_block_delta", {
                    "type": "content_block_delta", "index": self._block_index,
                    "delta": {"type": "text_delta", "text": piece}}))
        elif kind == "response.output_item.added":
            item = event.get("item") or {}
            if item.get("type") == "function_call":
                call_id = str(item.get("call_id") or item.get("id")
                              or f"toolu_{len(self._calls)}")
                self._calls[call_id] = {"id": call_id, "name": item.get("name", ""),
                                        "arguments": item.get("arguments") or ""}
                self._order.append(call_id)
                if item.get("id"):
                    self._item_to_call[str(item["id"])] = call_id
        elif kind == "response.function_call_arguments.delta":
            call_id = str(event.get("call_id") or self._item_to_call.get(
                str(event.get("item_id") or ""), ""))
            tool = self._calls.get(call_id)
            _require(tool is not None, "FABRIC_TRANSLATE_TOOL_IDENTITY")
            if tool is not None and isinstance(event.get("delta"), str):
                tool["arguments"] += event["delta"]
        usage = event.get("usage")
        if isinstance(usage, dict):
            self._usage = usage
        if kind in {"response.completed", "response.incomplete"}:
            response = event.get("response") or {}
            _require(isinstance(response, dict), "FABRIC_TRANSLATE_RESPONSE")
            _require(response.get("status") in {"completed", "incomplete"},
                     "FABRIC_TRANSLATE_RESPONSE")
            if response.get("status") == "incomplete" or kind == "response.incomplete":
                details = response.get("incomplete_details") or {}
                _require(isinstance(details, dict) and details.get("reason") == "max_output_tokens",
                         "FABRIC_UPSTREAM_INCOMPLETE")
                self._finish = "max_tokens"
            elif self._calls:
                self._finish = "tool_use"
            else:
                self._finish = "end_turn"
            self.completed = True
            self._usage = response.get("usage") or self._usage
        return out

    def finish(self) -> list[tuple[str, str]]:
        _require(self.completed, "FABRIC_STREAM_INCOMPLETE")
        out: list[tuple[str, str]] = []
        if self._text_open:
            out.append(self._events("content_block_stop", {
                "type": "content_block_stop", "index": self._block_index}))
            self._text_open = False
            self._block_index += 1
        for call_id in self._order:
            tool = self._calls[call_id]
            try:
                arguments = json.loads(tool["arguments"] or "{}")
            except ValueError:
                raise WireTranslationError(
                    "FABRIC_TRANSLATE_TOOL_ARGUMENTS") from None
            out.append(self._events("content_block_start", {
                "type": "content_block_start", "index": self._block_index,
                "content_block": {"type": "tool_use", "id": tool["id"],
                                  "name": tool["name"], "input": {}}}))
            out.append(self._events("content_block_delta", {
                "type": "content_block_delta", "index": self._block_index,
                "delta": {"type": "input_json_delta",
                          "partial_json": json.dumps(arguments,
                                                      separators=(",", ":"))}}))
            out.append(self._events("content_block_stop", {
                "type": "content_block_stop", "index": self._block_index}))
            self._block_index += 1
        stop_reason = self._finish or ("tool_use" if self._order else "end_turn")
        out.append(self._events("message_delta", {
            "type": "message_delta", "delta": {"stop_reason": stop_reason,
                                               "stop_sequence": None},
            "usage": {"output_tokens": self._usage.get("output_tokens", 0)}}))
        out.append(self._events("message_stop", {"type": "message_stop"}))
        return out
