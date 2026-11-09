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
                    parts.append({"type": "text", "text": block.get("text", "")})
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
        out: list[tuple[str, str]] = []
        if self._text_open:
            out.append(self._events("content_block_stop", {
                "type": "content_block_stop", "index": 0}))
            self._text_open = False
        block_index = 1
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
