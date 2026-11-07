#!/usr/bin/env python3
"""Local OpenCode Go multi-account router (stdlib only)."""
from __future__ import annotations

import fcntl
import hashlib
import http.client
import io
import json
import math
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
_EXT_DIR = os.path.dirname(HERE)
if os.path.isdir(os.path.join(_EXT_DIR, "glm_shim")):
    sys.path.insert(0, os.path.join(_EXT_DIR, "glm_shim"))
if _EXT_DIR not in sys.path:
    sys.path.insert(0, _EXT_DIR)

from glm_shim import (  # noqa: E402
    acquire_singleton_lock,
    check_auth,
    ensure_token,
    format_sse,
    iter_sse_chunks,
    redact_secrets,
    write_pid,
)

DEFAULTS = {
    "GO_ACCOUNTS_PATH": os.path.expanduser("~/.opencode-go/accounts.json"),
    "GO_UPSTREAM_BASE": "https://opencode.ai/zen/go/v1",
    "GO_SHIM_PORT": "4142",
    "GO_STATE_DIR": HERE,
    "GO_REFRESH_S": "120",
    "GO_PER_ACCOUNT_INFLIGHT": "4",
    "GO_STICKY_MAX_PCT": "85",
    "GO_ALLOW_UNPRICED": "0",
    "GO_ALLOW_TRAINING_MODELS": "0",
    "GO_PROMO_DEEPSEEK_V41_FLASH_ENDS": "2026-09-19T12:00Z",
    "GO_WIRE_COMPAT_PATH": os.path.join(_EXT_DIR, "state", "go_wire_compat.json"),
    "GO_RESPONSES_TO_CHAT": "1",
    "GO_WIRE_MATRIX_PATH": os.path.join(HERE, "wire_matrix.json"),
    "GO_MODEL_TIERS_PATH": os.path.join(HERE, "model_tiers.json"),
    "GO_FRONTIER_MAX_MONTHLY_PCT": "60",
    "GO_WEIGHTS_PATH": os.path.join(_EXT_DIR, "state", "go_weights.jsonl"),
}
WINDOWS = ("rolling", "weekly", "monthly")
WINDOW_SECONDS = {"rolling": 5 * 3600, "weekly": 7 * 86400, "monthly": 30 * 86400}
FRACTIONS = {"rolling": Decimal("0.2"), "weekly": Decimal("0.5"), "monthly": Decimal("1")}


def utc_iso(epoch: Optional[float] = None) -> str:
    moment = datetime.fromtimestamp(epoch if epoch is not None else time.time(), timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def upstream_url(base: str, path: str) -> str:
    normalized_base = base.rstrip("/")
    if normalized_base.endswith("/v1") and path in ("/v1", "/v1/",) or normalized_base.endswith("/v1") and path.startswith("/v1/"):
        path = path[3:]
    return normalized_base + path


AUTH_ERROR_MARKERS = ("auth", "permission", "forbidden", "credential", "api_key", "apikey")
WIRE_OF = {"/v1/chat/completions": "chat", "/v1/messages": "messages", "/v1/responses": "responses"}


def wire_of(endpoint: str) -> Optional[str]:
    return WIRE_OF.get(endpoint)


def responses_to_chat_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the supported Responses request subset to OpenAI Chat.

    codex sends role='developer' (per codex_responses_request_redacted.json); qwen3.7-plus
    rejects role 'developer' on the chat wire with HTTP 400
    ([invalid_parameter_error] developer is not one of ['system','assistant',...]). Map
    'developer' -> 'system' and any role outside {system,user,assistant,tool} -> 'user'
    so the chat wire only ever sees supported chat roles.

    Input items whose `type` is anything other than 'message', 'function_call', or
    'function_call_output' (and items with no `type` but a `role` are still treated
    as message-like) are dropped — they do not produce a chat message.
    """
    result: Dict[str, Any] = {"model": payload.get("model")}
    if payload.get("stream") is not None:
        result["stream"] = payload["stream"]
    for source, target in (("temperature", "temperature"), ("top_p", "top_p"), ("max_output_tokens", "max_tokens"), ("stop", "stop")):
        if source in payload:
            result[target] = payload[source]
    messages: List[Dict[str, Any]] = []
    if payload.get("instructions"):
        messages.append({"role": "system", "content": payload["instructions"]})
    incoming = payload.get("input", "")
    if isinstance(incoming, str):
        messages.append({"role": "user", "content": incoming})
    elif isinstance(incoming, list):
        for item in incoming:
            if not isinstance(item, dict):
                continue
            kind = item.get("type")
            if kind == "function_call_output":
                messages.append({"role": "tool", "tool_call_id": item.get("call_id") or item.get("id"), "content": item.get("output", "")})
                continue
            if kind == "function_call":
                messages.append({"role": "assistant", "tool_calls": [{"id": item.get("call_id") or item.get("id"), "type": "function", "function": {"name": item.get("name", ""), "arguments": item.get("arguments", "")}}]})
                continue
            if kind not in (None, "message"):
                # skip reasoning items and any other non-message non-tool types
                continue
            role = item.get("role", "user")
            content = item.get("content", "")
            if isinstance(content, list):
                content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict) and part.get("type") in {"input_text", "text"})
            chat_role = "system" if role == "developer" else role if role in {"system", "user", "assistant", "tool"} else "user"
            messages.append({"role": chat_role, "content": content})
    result["messages"] = messages
    if isinstance(payload.get("tools"), list):
        result["tools"] = [{"type": "function", "function": {key: tool.get(key) for key in ("name", "description", "parameters") if key in tool}}
                           for tool in payload["tools"] if isinstance(tool, dict) and tool.get("type") == "function"]
    if payload.get("tool_choice") is not None:
        choice = payload["tool_choice"]
        result["tool_choice"] = {"type": "function", "function": {"name": choice.get("name")}} if isinstance(choice, dict) and choice.get("type") == "function" else choice
    return result


_CHAT_ALLOWED_ROLES = {"system", "user", "assistant", "tool"}


def _normalize_chat_role(role: str) -> str:
    return role if role in _CHAT_ALLOWED_ROLES else "user"


def _stable_item_id(chat_id: Optional[str], suffix: str) -> str:
    base = chat_id or "rs"
    return f"{base}-{suffix}"


def _chat_response_id(chat_id: Optional[str]) -> str:
    return _stable_item_id(chat_id, "response")


_THINK_PREFIX = "<think>"
_THINK_END = "</think>"


def _extract_think_prefix_from_string(content: str) -> Tuple[Optional[str], str]:
    """Extract a leading <think>...</think> block from a non-streaming content string.

    Returns (reasoning_text_or_None, visible_content). When the content does not
    begin with the opening tag, or the closing tag is missing, the reasoning is
    None and the original content (possibly with leading whitespace) is returned.
    Whitespace immediately after </think> is stripped from the visible content.
    """
    if not isinstance(content, str) or not content:
        return None, content or ""
    if not content.startswith(_THINK_PREFIX):
        return None, content
    end = content.find(_THINK_END, len(_THINK_PREFIX))
    if end == -1:
        return None, content
    reasoning = content[len(_THINK_PREFIX):end]
    rest = content[end + len(_THINK_END):].lstrip()
    if not reasoning:
        return None, rest
    return reasoning, rest


def _make_think_extractor():
    """Build a streaming-safe extractor for a leading <think>...</think> block.

    Returns (state_dict, feed_fn). state_dict is mutated by feed_fn. Each call
    to feed_fn(text) returns a list of (kind, text) tuples where kind is
    'reasoning' or 'visible'. The state machine:
      * while the prefix has not been ruled out and </think> has not been seen,
        text is buffered;
      * if the buffer stops matching the <think> prefix, the whole buffer is
        flushed as visible content;
      * if </think> appears inside the buffer, the body is emitted as reasoning
        and the tail (after a whitespace strip) is emitted as visible content;
      * once anything has been emitted as visible, all further input is visible.
    """
    state = {"buffer": "", "in_visible": False}

    def feed(text: str):
        emissions: List[Tuple[str, str]] = []
        if not text:
            return emissions
        if state["in_visible"]:
            emissions.append(("visible", text))
            return emissions
        state["buffer"] += text
        if len(state["buffer"]) < len(_THINK_PREFIX):
            if state["buffer"] == _THINK_PREFIX[:len(state["buffer"])]:
                # still consistent with the opening tag prefix
                pass
            else:
                emissions.append(("visible", state["buffer"]))
                state["buffer"] = ""
                state["in_visible"] = True
        elif state["buffer"].startswith(_THINK_PREFIX):
            if _THINK_END in state["buffer"]:
                idx = state["buffer"].index(_THINK_END)
                body = state["buffer"][len(_THINK_PREFIX):idx]
                if body:
                    emissions.append(("reasoning", body))
                rest = state["buffer"][idx + len(_THINK_END):]
                rest_stripped = rest.lstrip()
                state["buffer"] = ""
                if rest_stripped:
                    emissions.append(("visible", rest_stripped))
                    state["in_visible"] = True
            else:
                # still waiting for </think>, keep buffering
                pass
        else:
            emissions.append(("visible", state["buffer"]))
            state["buffer"] = ""
            state["in_visible"] = True
        return emissions

    return state, feed


def _format_usage_row(usage_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build the F4 five-key Responses usage object from a chat usage payload.

    Always emits total_tokens (deriving as input + output when upstream omits it) and
    output_tokens_details (defaulting to {"reasoning_tokens":0}).
    """
    in_tokens = int(usage_payload.get("prompt_tokens") or 0)
    out_tokens = int(usage_payload.get("completion_tokens") or 0)
    explicit_total = usage_payload.get("total_tokens")
    if explicit_total is None:
        total_tokens = in_tokens + out_tokens
    else:
        total_tokens = int(explicit_total)
    details_in = usage_payload.get("prompt_tokens_details") or {}
    details_out = usage_payload.get("completion_tokens_details") or {}
    return {
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "total_tokens": total_tokens,
        "input_tokens_details": {"cached_tokens": int(details_in.get("cached_tokens") or 0)},
        "output_tokens_details": {"reasoning_tokens": int(details_out.get("reasoning_tokens") or 0)},
    }


def _parse_chat_sse(response: bytes) -> List[Dict[str, Any]]:
    """Parse an upstream chat SSE body into a list of chunk dicts.

    Tolerates the qwen `data: [DONE]` sentinel and the Go upstream's
    `data: {"choices":[],"cost":"0"}` trailer; both are dropped.
    """
    out: List[Dict[str, Any]] = []
    for line in response.decode("utf-8", "replace").splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].lstrip()
        if payload == "[DONE]":
            continue
        if "choices" in payload and "\"cost\"" in payload and "delta" not in payload:
            continue
        parsed = _try_json(payload)
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def chat_to_responses_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a non-streaming chat response into a Responses-shaped object.

    output message items carry id and status:"completed"; output_text parts carry
    annotations:[] and logprobs:[] (codex's parser requires those exact keys);
    function_call items carry both id and call_id; usage carries the F4 five-key
    block including total_tokens and output_tokens_details.

    When the message content begins with `<think>...</think>`, the body of the
    think block is extracted as a separate reasoning OUTPUT ITEM placed before
    the message item in the `output` array; only the post-</think> tail
    (whitespace-stripped) becomes the message's output_text.
    """
    choice = ((payload.get("choices") or [{}])[0] or {})
    message = choice.get("message") or {}
    chat_id = payload.get("id")
    response_id = _chat_response_id(chat_id if isinstance(chat_id, str) else None)
    output: List[Dict[str, Any]] = []

    raw_content = message.get("content")
    reasoning_text: Optional[str] = None
    visible_text = ""
    has_content_field = raw_content is not None
    if isinstance(raw_content, str):
        reasoning_text, visible_text = _extract_think_prefix_from_string(raw_content)
    elif raw_content is not None:
        visible_text = raw_content

    if reasoning_text:
        reasoning_item_id = _stable_item_id(response_id, "reasoning")
        output.append({
            "id": reasoning_item_id,
            "type": "reasoning",
            "status": "completed",
            "encrypted_content": response_id + "-0",
            "content": [{"type": "reasoning_text", "text": reasoning_text}],
            "summary": [],
        })

    if has_content_field and visible_text:
        text_id = _stable_item_id(response_id, "msg")
        output.append({
            "id": text_id,
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{
                "type": "output_text",
                "text": visible_text,
                "annotations": [],
                "logprobs": [],
            }],
        })
    for call in (message.get("tool_calls") or []):
        function = call.get("function") or {}
        call_id = call.get("id") or _stable_item_id(response_id, "call")
        output.append({
            "id": call_id,
            "type": "function_call",
            "call_id": call_id,
            "name": function.get("name", ""),
            "arguments": function.get("arguments", ""),
            "status": "completed",
        })
    result = {
        "id": response_id,
        "object": "response",
        "status": "completed",
        "model": payload.get("model"),
        "output": output,
    }
    if "usage" in payload:
        result["usage"] = _format_usage_row(payload["usage"] or {})
    return result


def chat_to_responses_stream(response: bytes) -> bytes:
    """Translate an upstream chat SSE body into the F1/F2/F3/F4 Responses stream.

    Emits a two-line `event: <type>` + `data: {json}\n` envelope per event with a
    contiguous `sequence_number` starting at 0; emits response.created /
    response.in_progress followed by either a reasoning item (at output_index 0
    when reasoning text is present — sourced from BOTH `delta.reasoning_content`
    and a streaming-safe extraction of a leading `<think>...</think>` block from
    `delta.content`), a text message item, or one function_call item per tool-call
    index (reasoning then text first, then tool calls at increasing output_index);
    emits exactly one response.completed carrying the F4 five-key usage; ignores
    [DONE] and the Go upstream cost trailer; and degrades gracefully to an empty
    created/in_progress/completed sequence when upstream returns no reasoning,
    no visible content, and no tool calls (so codex never sits on an un-acked
    stream).
    """
    chunks = _parse_chat_sse(response)
    response_id: Optional[str] = None
    model: Optional[str] = None
    chat_created_at: Optional[int] = None
    for chunk in chunks:
        if response_id is None and isinstance(chunk.get("id"), str):
            response_id = chunk["id"]
        if model is None and isinstance(chunk.get("model"), str):
            model = chunk["model"]
        if chat_created_at is None and isinstance(chunk.get("created"), (int, float)):
            chat_created_at = int(chunk["created"])
    if response_id is None:
        response_id = uuid.uuid4().hex
    prefix_id = response_id
    response_id = _chat_response_id(prefix_id if isinstance(prefix_id, str) else None)
    created_at = int(chat_created_at) if chat_created_at is not None else int(time.time())
    completed_at = created_at + 1

    reasoning_deltas: List[str] = []
    text_deltas: List[str] = []
    tool_state: Dict[int, Dict[str, Any]] = {}
    _extractor_state, extractor = _make_think_extractor()

    for chunk in chunks:
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        rc = delta.get("reasoning_content")
        if isinstance(rc, str) and rc:
            reasoning_deltas.append(rc)
        content = delta.get("content")
        if isinstance(content, str) and content:
            for kind, piece in extractor(content):
                if kind == "reasoning":
                    reasoning_deltas.append(piece)
                elif kind == "visible":
                    text_deltas.append(piece)
        for call in (delta.get("tool_calls") or []):
            if not isinstance(call, dict):
                continue
            index = call.get("index")
            if not isinstance(index, int):
                index = 0
            entry = tool_state.setdefault(index, {"id": None, "name": None, "arguments": ""})
            call_id = call.get("id")
            if isinstance(call_id, str) and call_id:
                entry["id"] = call_id
            function = call.get("function") or {}
            name = function.get("name")
            if isinstance(name, str) and name:
                entry["name"] = name
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                entry["arguments"] += arguments

    usage_payload: Optional[Dict[str, Any]] = None
    for chunk in chunks:
        usage = chunk.get("usage")
        if isinstance(usage, dict):
            usage_payload = usage
            break
    usage_obj = _format_usage_row(usage_payload or {})

    ordered_indexes = sorted(tool_state.keys())
    has_reasoning = bool("".join(reasoning_deltas))
    has_text = any(text_deltas)
    has_tools = bool(ordered_indexes)

    events_out: List[Dict[str, Any]] = []
    seq = 0

    def _push(event_type: str, data: Dict[str, Any]):
        nonlocal seq
        data = {"type": event_type, "sequence_number": seq, **data}
        seq += 1
        events_out.append((event_type, data))

    base_response = {
        "id": response_id,
        "object": "response",
        "created_at": created_at,
        "status": "in_progress",
        "model": model,
        "parallel_tool_calls": True,
        "tools": [],
        "tool_choice": "auto",
    }
    _push("response.created", {"response": {**base_response, "status": "in_progress"}})
    _push("response.in_progress", {"response": {**base_response, "status": "in_progress"}})

    if has_reasoning:
        reasoning_item_id = _stable_item_id(prefix_id, "reasoning")
        full_reasoning_text = "".join(reasoning_deltas)
        _push("response.output_item.added", {
            "output_index": 0,
            "item": {
                "id": reasoning_item_id,
                "type": "reasoning",
                "status": "in_progress",
                "encrypted_content": response_id + "-0",
                "content": [],
                "summary": [],
            },
        })
        _push("response.content_part.added", {
            "output_index": 0,
            "content_index": 0,
            "item_id": reasoning_item_id,
            "part": {"type": "reasoning_text", "text": ""},
        })
        for r_delta in reasoning_deltas:
            _push("response.reasoning_text.delta", {
                "output_index": 0,
                "content_index": 0,
                "item_id": reasoning_item_id,
                "delta": r_delta,
            })
        _push("response.reasoning_text.done", {
            "output_index": 0,
            "content_index": 0,
            "item_id": reasoning_item_id,
            "text": full_reasoning_text,
        })
        _push("response.content_part.done", {
            "output_index": 0,
            "content_index": 0,
            "item_id": reasoning_item_id,
            "part": {"type": "reasoning_text", "text": full_reasoning_text},
        })
        _push("response.output_item.done", {
            "output_index": 0,
            "item": {
                "id": reasoning_item_id,
                "type": "reasoning",
                "status": "completed",
                "encrypted_content": response_id + "-0",
                "content": [{"type": "reasoning_text", "text": full_reasoning_text}],
                "summary": [],
            },
        })

    final_text = "".join(text_deltas)
    text_out_idx = 1 if has_reasoning else 0

    if has_text:
        message_item_id = _stable_item_id(prefix_id, "msg")
        _push("response.output_item.added", {
            "output_index": text_out_idx,
            "item": {
                "id": message_item_id,
                "type": "message",
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            },
        })
        _push("response.content_part.added", {
            "output_index": text_out_idx,
            "content_index": 0,
            "item_id": message_item_id,
            "part": {"type": "output_text", "text": "", "annotations": [], "logprobs": []},
        })
        for delta_text in text_deltas:
            if not isinstance(delta_text, str):
                continue
            _push("response.output_text.delta", {
                "output_index": text_out_idx,
                "content_index": 0,
                "item_id": message_item_id,
                "delta": delta_text,
                "logprobs": [],
            })
        _push("response.output_text.done", {
            "output_index": text_out_idx,
            "content_index": 0,
            "item_id": message_item_id,
            "text": final_text,
            "logprobs": [],
        })
        _push("response.content_part.done", {
            "output_index": text_out_idx,
            "content_index": 0,
            "item_id": message_item_id,
            "part": {"type": "output_text", "text": final_text, "annotations": [], "logprobs": []},
        })
        _push("response.output_item.done", {
            "output_index": text_out_idx,
            "item": {
                "id": message_item_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": final_text, "annotations": [], "logprobs": []}],
            },
        })

    tool_start_index = text_out_idx + (1 if has_text else 0)
    for offset, tool_index in enumerate(ordered_indexes):
        entry = tool_state[tool_index]
        call_id = entry["id"] or _stable_item_id(prefix_id, f"call-{tool_index}")
        name = entry["name"] or ""
        arguments = entry["arguments"]
        out_idx = tool_start_index + offset
        item_id = call_id
        _push("response.output_item.added", {
            "output_index": out_idx,
            "item": {
                "id": item_id,
                "type": "function_call",
                "status": "in_progress",
                "name": name,
                "call_id": call_id,
                "arguments": "",
            },
        })
        try:
            chunked_args = json.dumps(_split_arguments_for_deltas(arguments)) if arguments else []
        except (TypeError, ValueError):
            chunked_args = []
        if arguments and not chunked_args:
            _push("response.function_call_arguments.delta", {
                "output_index": out_idx,
                "item_id": item_id,
                "delta": arguments,
            })
        else:
            for piece in chunked_args:
                _push("response.function_call_arguments.delta", {
                    "output_index": out_idx,
                    "item_id": item_id,
                    "delta": piece,
                })
        _push("response.function_call_arguments.done", {
            "output_index": out_idx,
            "item_id": item_id,
            "arguments": arguments,
        })
        _push("response.output_item.done", {
            "output_index": out_idx,
            "item": {
                "id": item_id,
                "type": "function_call",
                "status": "completed",
                "name": name,
                "call_id": call_id,
                "arguments": arguments,
            },
        })

    completed_response = {
        **base_response,
        "status": "completed",
        "completed_at": completed_at,
        "output": _build_completed_output(prefix_id, response_id, reasoning_deltas, final_text, has_reasoning, has_text, tool_state, ordered_indexes, tool_start_index),
        "usage": usage_obj,
    }
    _push("response.completed", {"response": completed_response})

    out_buf: List[bytes] = []
    for event_type, data in events_out:
        out_buf.append(("event: " + event_type + "\n").encode("utf-8"))
        out_buf.append(("data: " + json.dumps(data, separators=(",", ":")) + "\n\n").encode("utf-8"))
    return b"".join(out_buf)


def _split_arguments_for_deltas(arguments: str) -> List[str]:
    """Best-effort split for emitting function_call_arguments.delta pieces.

    Splits on top-level JSON boundaries when arguments parse cleanly; otherwise
    returns a single-element list so the caller emits one event with the raw
    string. Always returns at least one element when arguments is non-empty so
    codex sees at least one delta per call.
    """
    try:
        parsed = json.loads(arguments)
    except (TypeError, ValueError):
        return [arguments] if arguments else []
    if not isinstance(parsed, (dict, list)):
        return [arguments]
    tokens: List[str] = []
    if isinstance(parsed, dict):
        tokens = [json.dumps({key: value}, separators=(",", ":")) for key, value in parsed.items()]
    else:
        tokens = [json.dumps(item, separators=(",", ":")) for item in parsed]
    if not tokens:
        return [arguments]
    return tokens


def _build_completed_output(
    prefix_id: str,
    response_id: str,
    reasoning_deltas: List[str],
    final_text: str,
    has_reasoning: bool,
    has_text: bool,
    tool_state: Dict[int, Dict[str, Any]],
    ordered_indexes: List[int],
    tool_start_index: int,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if has_reasoning:
        full_reasoning = "".join(reasoning_deltas)
        reasoning_item_id = _stable_item_id(prefix_id, "reasoning")
        out.append({
            "id": reasoning_item_id,
            "type": "reasoning",
            "status": "completed",
            "encrypted_content": response_id + "-0",
            "content": [{"type": "reasoning_text", "text": full_reasoning}],
            "summary": [],
        })
    if has_text:
        message_item_id = _stable_item_id(prefix_id, "msg")
        out.append({
            "id": message_item_id,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": final_text, "annotations": [], "logprobs": []}],
        })
    for offset, tool_index in enumerate(ordered_indexes):
        entry = tool_state[tool_index]
        call_id = entry["id"] or _stable_item_id(prefix_id, f"call-{tool_index}")
        out.append({
            "id": call_id,
            "type": "function_call",
            "status": "completed",
            "name": entry["name"] or "",
            "call_id": call_id,
            "arguments": entry["arguments"],
        })
    return out


def classify_upstream_error(status: int, raw: bytes) -> Tuple[str, Optional[str], Optional[str], Dict[str, Any]]:
    decoded = raw.decode("utf-8", "replace")
    try:
        parsed = json.loads(decoded)
    except (TypeError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, dict):
        payload = parsed
    else:
        payload = {"error": {"type": "upstream_error", "message": decoded[:200]}}
    error = payload.get("error")
    error_type = error.get("type") if isinstance(error, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    error_type = error_type if isinstance(error_type, str) else None
    message = message if isinstance(message, str) else None
    kind = "auth" if not isinstance(parsed, dict) or error_type is None or any(marker in error_type.lower() for marker in AUTH_ERROR_MARKERS) else "model"
    return kind, error_type, message, payload


def load_wire_compat(path: str) -> Dict[str, List[str]]:
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, List[str]] = {}
    for model, wires in raw.items():
        if str(model).startswith("_") or not isinstance(wires, list):
            continue
        valid = [str(wire).lower() for wire in wires if isinstance(wire, str) and str(wire).lower() in WIRE_OF.values()]
        if valid:
            result.setdefault(str(model).lower(), []).extend(valid)
    return result


def synthesize_upstream_http_error(status: int, raw: bytes) -> Dict[str, Any]:
    decoded = raw.decode("utf-8", "replace")
    message = decoded[:200] if decoded.strip() else "empty upstream error body"
    return {"error": {"message": message, "type": "upstream_http_error", "code": status}}


def _redact_reason(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    redacted = re.sub(r"sk-[A-Za-z0-9_\-]{4,}", "sk-REDACTED", text)
    return " ".join(redacted.split())[:80]


def load_prices(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_model_tiers(path: str) -> Dict[str, Any]:
    fallback = {"_meta": {"default_weight": 4, "frontier_weight": 4}, "models": {}}
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return fallback
    if not isinstance(raw, dict):
        return fallback
    meta_raw = raw.get("_meta") if isinstance(raw.get("_meta"), dict) else {}
    models_raw = raw.get("models") if isinstance(raw.get("models"), dict) else {}
    meta = {
        "default_weight": int(meta_raw.get("default_weight", 4)) if isinstance(meta_raw.get("default_weight", 4), (int, float, str)) else 4,
        "frontier_weight": int(meta_raw.get("frontier_weight", 4)) if isinstance(meta_raw.get("frontier_weight", 4), (int, float, str)) else 4,
    }
    models: Dict[str, Any] = {}
    for key, value in models_raw.items():
        if isinstance(value, dict):
            models[str(key)] = value
    return {"_meta": meta, "models": models}


def deepseek_peak(now_utc: datetime) -> bool:
    return now_utc.weekday() < 5 and (1 <= now_utc.hour < 4 or 6 <= now_utc.hour < 10)


def select_price_row(prices: Dict[str, Any], model: str, input_tokens: int, now_utc: datetime) -> Optional[Dict[str, Any]]:
    entry = prices["models"].get(model)
    if not entry:
        return None
    rows = entry["rows"]
    peak = deepseek_peak(now_utc)
    for row in rows:
        band = row.get("band") or {}
        if band.get("kind") == "peak" and peak:
            return dict(row)
        if band.get("kind") == "peak" and not peak:
            continue
        if band.get("kind") == "peak":
            return dict(row)
    for row in rows:
        band = row.get("band") or {}
        threshold = band.get("threshold_tokens")
        if threshold is None or input_tokens <= int(threshold):
            return dict(row)
    return dict(rows[-1])


def effective_price_row(row: Dict[str, Any], now_epoch: float) -> Dict[str, Any]:
    result = dict(row)
    promo = result.get("promo")
    if promo and now_epoch >= parse_utc(promo["ends_utc"]):
        result["monthly_usd"] = promo["baseline_usd"]
        result["promo_active"] = False
    else:
        result["promo_active"] = bool(promo)
    return result


def estimate_cost(row: Dict[str, Any], usage: Dict[str, int]) -> Decimal:
    input_tokens = max(0, int(usage.get("input") or 0))
    cached_read = min(input_tokens, max(0, int(usage.get("cached_read") or 0)))
    cache_write = max(0, int(usage.get("cache_write") or 0))
    output = max(0, int(usage.get("output") or 0))
    uncached = Decimal(input_tokens - cached_read) / Decimal(1_000_000) * Decimal(row["in"])
    cached = Decimal(cached_read) / Decimal(1_000_000) * Decimal(row["cached_read"])
    write_price = row.get("cache_write")
    write_cost = Decimal(cache_write) / Decimal(1_000_000) * (Decimal(write_price) if write_price is not None else Decimal(row["in"]))
    output_cost = Decimal(output) / Decimal(1_000_000) * Decimal(row["out"])
    return uncached + cached + write_cost + output_cost


def _first(items: List[Any], key: str) -> Optional[str]:
    for item in items:
        if isinstance(item, dict) and isinstance(item.get(key), str):
            return item[key]
    return None


def session_key(model: str, body: Dict[str, Any], headers: Dict[str, str]) -> str:
    direct = headers.get("x-opencode-session") or headers.get("session_id")
    if direct:
        return direct
    chunks: List[str] = []
    instructions = body.get("instructions")
    if isinstance(instructions, str):
        chunks.append(instructions)
    system = body.get("system")
    if isinstance(system, str):
        chunks.append(system)
    elif isinstance(system, list):
        value = _first(system, "text")
        if value:
            chunks.append(value)
    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            content = first.get("content")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                value = _first(content, "text")
                if value:
                    chunks.append(value)
            elif isinstance(first.get("text"), str):
                chunks.append(first["text"])
    payload = (model + "\n" + "\n".join(chunks))[:4096]
    return hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()


def _sse_objects(text: str) -> List[Dict[str, Any]]:
    import io

    return [
        obj
        for line in text.splitlines()
        if line.startswith("data:")
        for obj in [_try_json(line[5:].strip())]
        if isinstance(obj, dict)
    ]


def _try_json(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def extract_usage(endpoint: str, stream: bool, response: bytes) -> Tuple[Optional[Dict[str, int]], Optional[str]]:
    try:
        payload = json.loads(response.decode("utf-8")) if not stream else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    chunks = _sse_objects(response.decode("utf-8", "replace")) if stream else []
    if endpoint.endswith("/chat/completions"):
        source = (payload or {}).get("usage") or {}
        if stream:
            for chunk in reversed(chunks):
                if isinstance(chunk.get("usage"), dict):
                    source = chunk["usage"]
                    break
        details = source.get("prompt_tokens_details") or {}
        if "prompt_tokens" in source:
            return {"input": int(source.get("prompt_tokens") or 0), "cached_read": int(details.get("cached_tokens") or 0), "cache_write": int(source.get("cache_write") or source.get("cache_write_tokens") or 0), "output": int(source.get("completion_tokens") or 0)}, None
    elif endpoint.endswith("/messages"):
        start = {}
        delta = {}
        if stream:
            for chunk in chunks:
                if chunk.get("type") == "message_start":
                    start = ((chunk.get("message") or {}).get("usage") or {})
                if chunk.get("type") == "message_delta":
                    delta = chunk.get("usage") or {}
        else:
            source = payload or {}
            start = source.get("usage") or {}
            delta = start
        if start:
            return {"input": int(start.get("input_tokens") or 0), "cached_read": int(start.get("cache_read_input_tokens") or 0), "cache_write": int(start.get("cache_creation_input_tokens") or 0), "output": int(delta.get("output_tokens") or 0)}, None
    elif endpoint.endswith("/responses"):
        source = (payload or {}).get("usage") or {}
        if stream:
            for chunk in reversed(chunks):
                if chunk.get("type") == "response.completed":
                    source = (((chunk.get("response") or {}).get("usage")) or {})
                    break
        if "input_tokens" in source:
            details = source.get("input_tokens_details") or {}
            return {"input": int(source.get("input_tokens") or 0), "cached_read": int(details.get("cached_tokens") or 0), "cache_write": int(source.get("cache_write") or source.get("cache_write_tokens") or 0), "output": int(source.get("output_tokens") or 0)}, None
    if stream:
        return None, "estimated_from_bytes"
    return None, "no_usage"


class Router:
    def __init__(
        self,
        accounts_path: str,
        upstream_base: str,
        state_dir: str,
        prices_path: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        clock: Optional[Any] = None,
    ):
        self.env = {**os.environ, **(env or {})}
        self.clock = clock or time.time
        self.accounts_path = os.path.abspath(accounts_path)
        self.upstream_base = upstream_base.rstrip("/")
        self.state_dir = os.path.abspath(state_dir)
        self.prices = load_prices(prices_path or os.path.join(HERE, "go_prices.json"))
        self.wire_compat_path = self.env.get("GO_WIRE_COMPAT_PATH") or DEFAULTS["GO_WIRE_COMPAT_PATH"]
        self._initialize_wire_compat()
        self.wire_matrix_path = self.env.get("GO_WIRE_MATRIX_PATH") or DEFAULTS["GO_WIRE_MATRIX_PATH"]
        self.wire_compat = load_wire_compat(self.wire_compat_path)
        self.refresh_s = int(self.env.get("GO_REFRESH_S") or DEFAULTS["GO_REFRESH_S"])
        self.max_inflight = int(self.env.get("GO_PER_ACCOUNT_INFLIGHT") or DEFAULTS["GO_PER_ACCOUNT_INFLIGHT"])
        self.sticky_max_pct = int(self.env.get("GO_STICKY_MAX_PCT") or DEFAULTS["GO_STICKY_MAX_PCT"])
        self.allow_unpriced = self.env.get("GO_ALLOW_UNPRICED", DEFAULTS["GO_ALLOW_UNPRICED"]) == "1"
        self.allow_training = self.env.get("GO_ALLOW_TRAINING_MODELS", DEFAULTS["GO_ALLOW_TRAINING_MODELS"]) == "1"
        self.promo_ends = self.env.get("GO_PROMO_DEEPSEEK_V41_FLASH_ENDS", DEFAULTS["GO_PROMO_DEEPSEEK_V41_FLASH_ENDS"])
        self.model_tiers_path = self.env.get("GO_MODEL_TIERS_PATH") or DEFAULTS["GO_MODEL_TIERS_PATH"]
        self.frontier_max_monthly_pct = float(self.env.get("GO_FRONTIER_MAX_MONTHLY_PCT") or DEFAULTS["GO_FRONTIER_MAX_MONTHLY_PCT"])
        self.weights_path = self.env.get("GO_WEIGHTS_PATH") or DEFAULTS["GO_WEIGHTS_PATH"]
        self.model_tiers = load_model_tiers(self.model_tiers_path)
        os.makedirs(self.state_dir, mode=0o700, exist_ok=True)
        os.chmod(self.state_dir, 0o700)
        self._validate_accounts_path()
        with open(self.accounts_path, encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError("accounts.json: top-level value must be an object")
        accounts = {}
        for name, value in raw.items():
            api_key = value.get("api_key") if isinstance(value, dict) else None
            if not isinstance(api_key, str) or not api_key:
                raise ValueError(f'accounts.json: entry "{name}" must be an object with a non-empty string "api_key"')
            accounts[name] = api_key
        self.accounts = accounts
        self.token_path = os.path.join(self.state_dir, ".token")
        self.pid_path = os.path.join(self.state_dir, "shim.pid")
        self.lock_path = os.path.join(self.state_dir, "shim.lock")
        self.log_path = os.path.join(self.state_dir, "shim.log")
        self.usage_path = os.path.join(self.state_dir, "usage.jsonl")
        self.state_path = os.path.join(self.state_dir, "state.json")
        self.token = ensure_token(self.token_path)
        self.lock: threading.RLock = threading.RLock()
        self.write_lock = threading.Lock()
        self.in_flight = {name: 0 for name in self.accounts}
        self.worker_in_flight = {name: {} for name in self.accounts}
        self.gateway_instance_id = uuid.uuid4().hex
        self.round_robin = 0
        self.sticky: Dict[str, Tuple[str, float]] = {}
        self.snapshots = {name: None for name in self.accounts}
        self.snapshot_at = {name: 0.0 for name in self.accounts}
        self.request_counts = {name: 0 for name in self.accounts}
        self.calibration_factors = {name: 1.0 for name in self.accounts}
        self.exhausted_until = {name: 0.0 for name in self.accounts}
        self.auth_failed = {name: False for name in self.accounts}
        self.auth_failed_at = {name: None for name in self.accounts}
        self.auth_failed_reason = {name: None for name in self.accounts}
        self.last_error = {name: None for name in self.accounts}
        self.usage_rows: List[Dict[str, Any]] = []
        self._load_state()

    def _initialize_wire_compat(self) -> None:
        live = os.path.abspath(self.wire_compat_path)
        if os.path.exists(live):
            return
        seed = os.path.join(HERE, "go_wire_compat.json")
        try:
            with open(seed, "rb") as source:
                data = source.read()
            os.makedirs(os.path.dirname(live), mode=0o700, exist_ok=True)
            temporary = live + ".tmp"
            with open(temporary, "wb") as target:
                target.write(data)
            os.replace(temporary, live)
        except OSError:
            pass

    def _validate_accounts_path(self) -> None:
        parent = os.path.dirname(self.accounts_path)
        if not os.path.isfile(self.accounts_path):
            raise PermissionError(f"accounts file missing: {self.accounts_path}")
        if stat_mode(parent) != 0o700 or stat_mode(self.accounts_path) != 0o600:
            raise PermissionError("accounts path must have parent mode 0700 and file mode 0600")

    def now(self) -> float:
        return float(self.clock())

    def _log(self, event: str, **fields: Any) -> None:
        row = {"ts": utc_iso(self.now()), "event": event, **fields}
        text = json.dumps(row, separators=(",", ":"), sort_keys=True)
        with self.write_lock:
            fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, redact_secrets(text + "\n", self.accounts.values()).encode("utf-8"))
            finally:
                os.close(fd)

    def _persist_state(self) -> None:
        state = {
            "accounts": {
                name: {
                    "exhausted_until": utc_iso(self.exhausted_until[name]) if self.exhausted_until[name] else None,
                    "auth_failed": self.auth_failed[name],
                    "auth_failed_at": utc_iso(self.auth_failed_at[name]) if self.auth_failed_at[name] else None,
                    "auth_failed_reason": self.auth_failed_reason[name],
                    "last_error_class": self.last_error[name],
                }
                for name in self.accounts
            },
            "usage_rows": self.usage_rows,
        }
        temporary = self.state_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(state, handle, separators=(",", ":"), sort_keys=True)
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.state_path)

    def _load_state(self) -> None:
        if not os.path.exists(self.state_path):
            return
        with open(self.state_path, encoding="utf-8") as handle:
            state = json.load(handle)
        for name, value in (state.get("accounts") or {}).items():
            if name in self.accounts:
                self.exhausted_until[name] = parse_utc(value["exhausted_until"]) if value.get("exhausted_until") else 0.0
                self.auth_failed[name] = bool(value.get("auth_failed"))
                self.auth_failed_at[name] = parse_utc(value["auth_failed_at"]) if value.get("auth_failed_at") else None
                self.auth_failed_reason[name] = value.get("auth_failed_reason")
                self.last_error[name] = value.get("last_error_class")
        self.usage_rows = [row for row in state.get("usage_rows", []) if row.get("account") in self.accounts]

    def _append_usage(self, row: Dict[str, Any]) -> None:
        row = dict(row)
        row["session_key_sha8"] = hashlib.sha256(row.pop("session_key", "").encode()).hexdigest()[:8]
        self.usage_rows.append(row)
        text = json.dumps(row, separators=(",", ":"), sort_keys=True)
        with self.write_lock:
            fd = os.open(self.usage_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, redact_secrets(text + "\n", self.accounts.values()).encode("utf-8"))
            finally:
                os.close(fd)
        self._persist_state()

    def _get_json(self, account: str, path: str, timeout: float = 4.0) -> Any:
        request = Request(upstream_url(self.upstream_base, path), headers={"Authorization": "Bearer " + self.accounts[account], "User-Agent": "mastermind-go-shim/1"})
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def refresh(self, account: str, force: bool = False) -> Optional[Dict[str, Any]]:
        now = self.now()
        if not force and self.snapshots[account] and now - self.snapshot_at[account] < self.refresh_s and self.request_counts[account] < 25:
            return self.snapshots[account]
        try:
            payload = self._get_json(account, "/usage")
            snapshot = payload.get("usage")
            if not isinstance(snapshot, dict) or any(not isinstance(snapshot.get(window), dict) for window in WINDOWS):
                raise ValueError("invalid /usage shape")
            self.snapshots[account] = snapshot
            self.snapshot_at[account] = now
            self.request_counts[account] = 0
            factor = 1.0
            local = self.local_aggregate_pct(account, "rolling")
            provider = float(snapshot["rolling"].get("percent") or 0)
            if local > 5 and provider > 5:
                factor = min(4.0, max(0.5, provider / local))
            self.calibration_factors[account] = factor
            return snapshot
        except Exception as error:
            self.last_error[account] = type(error).__name__
            self._log("usage_refresh_failed", account=account, error=type(error).__name__)
            return self.snapshots[account]

    def local_spend(self, account: str, model: str, window: str) -> Decimal:
        now = self.now()
        cutoff = now - WINDOW_SECONDS[window]
        return sum(
            (Decimal(str(row.get("est_usd") or 0)) for row in self.usage_rows if row.get("account") == account and row.get("model") == model and row.get("status") == "ok" and parse_utc(row["ts"]) >= cutoff),
            Decimal(0),
        )

    def local_pct(self, account: str, model: str, window: str) -> float:
        entry = self.prices["models"].get(model)
        if not entry:
            return 0.0
        row = entry["rows"][0]
        monthly = Decimal(row["monthly_usd"])
        if self.now() >= parse_utc(self.promo_ends) and row.get("promo"):
            monthly = Decimal(row["promo"]["baseline_usd"])
        cap = monthly * FRACTIONS[window]
        if not cap:
            return 0.0
        return float(self.local_spend(account, model, window) / cap * Decimal(100))

    def local_aggregate_pct(self, account: str, window: str) -> float:
        return sum(self.local_pct(account, model, window) for model in self.prices["models"])

    def eligible(self, account: str, model: str, lock_held: bool = False) -> bool:
        if self.auth_failed[account] or self.now() < self.exhausted_until[account] or self.in_flight[account] >= self.max_inflight:
            return False
        snapshot = self.refresh(account)
        if not snapshot or any((snapshot.get(window) or {}).get("status") != "ok" for window in WINDOWS):
            return False
        if not self.tier_allows(account, model):
            return False
        return all(self.local_pct(account, model, window) < 100 for window in WINDOWS)

    def tier_weight(self, model: str) -> int:
        entry = self.model_tiers.get("models", {}).get(model)
        meta = self.model_tiers.get("_meta", {}) or {}
        default_weight = int(meta.get("default_weight", 4))
        if not isinstance(entry, dict):
            return default_weight
        try:
            weight = int(entry.get("weight", default_weight))
        except (TypeError, ValueError):
            weight = default_weight
        promo_until = entry.get("promo_until")
        if promo_until:
            try:
                if self.now() >= parse_utc(str(promo_until)):
                    weight = int(entry.get("post_promo_weight", weight))
            except (TypeError, ValueError):
                pass
        return weight

    def is_frontier(self, model: str) -> bool:
        meta = self.model_tiers.get("_meta", {}) or {}
        frontier_weight = int(meta.get("frontier_weight", 4))
        return self.tier_weight(model) >= frontier_weight

    def provider_pct(self, account: str, window: str) -> float:
        snap = self.snapshots.get(account) or {}
        win = snap.get(window) or {}
        try:
            return float(win.get("percent") or 0)
        except (TypeError, ValueError):
            return 0.0

    def tier_allows(self, account: str, model: str) -> bool:
        if not self.is_frontier(model):
            return True
        return self.provider_pct(account, "monthly") < self.frontier_max_monthly_pct

    def tier_budget_gate(self, model: str) -> Dict[str, Any]:
        weight = self.tier_weight(model)
        frontier = self.is_frontier(model)
        threshold_pct = float(self.frontier_max_monthly_pct)
        considered = [name for name in self.accounts if not self.auth_failed.get(name) and self.now() >= self.exhausted_until.get(name, 0.0)]
        if not frontier:
            return {
                "weight": weight,
                "frontier": False,
                "allowed": True,
                "threshold_pct": threshold_pct,
                "accounts_checked": len(considered),
                "min_monthly_pct": None,
                "retry_after": 30,
            }
        for name in considered:
            try:
                self.refresh(name)
            except Exception:
                pass
        pcts: List[float] = []
        for name in considered:
            pcts.append(self.provider_pct(name, "monthly"))
        min_pct: Optional[float] = min(pcts) if pcts else None
        allowed = any(p < threshold_pct for p in pcts) if pcts else False
        retry_after = 30
        now = self.now()
        earliest: Optional[float] = None
        for name in considered:
            snap = self.snapshots[name] or {}
            reset = (snap.get("monthly") or {}).get("resetsAt")
            if reset:
                try:
                    t = parse_utc(str(reset))
                    if earliest is None or t < earliest:
                        earliest = t
                except (TypeError, ValueError):
                    pass
        if earliest is not None:
            retry_after = max(30, int(math.ceil(earliest - now)))
        return {
            "weight": weight,
            "frontier": True,
            "allowed": allowed,
            "threshold_pct": threshold_pct,
            "accounts_checked": len(considered),
            "min_monthly_pct": min_pct,
            "retry_after": retry_after,
        }

    def ledger_tier_refusal(self, model: str, endpoint: str, body: Dict[str, Any], headers: Dict[str, str], gate: Dict[str, Any]) -> None:
        self._append_usage({
            "ts": utc_iso(self.now()),
            "account": None,
            "model": model,
            "endpoint": endpoint,
            "stream": bool(body.get("stream")),
            "status": "refused_tier_budget",
            "latency_ms": 0,
            "est_usd": "0",
            "price_row": None,
            "session_key": session_key(model, body, headers),
            "attempt": 0,
            "replayed_from": None,
            "error_class": "go_tier_budget",
            "weight": int(gate["weight"]),
            "tag": "frontier",
            "threshold_pct": float(gate["threshold_pct"]),
            "min_monthly_pct": gate.get("min_monthly_pct"),
        })

    def _append_weight_row(self, account: str, model: str, counts: Optional[Dict[str, Any]], pct_before: Optional[float], snapshot_at_before: Optional[float]) -> None:
        if account not in self.accounts:
            return
        counts = counts or {}
        in_tok = counts.get("input_tokens")
        cached_tok = counts.get("cached_tokens")
        out_tok = counts.get("output_tokens")
        try:
            in_int = int(in_tok) if in_tok is not None else None
        except (TypeError, ValueError):
            in_int = None
        try:
            cached_int = int(cached_tok) if cached_tok is not None else None
        except (TypeError, ValueError):
            cached_int = None
        try:
            out_int = int(out_tok) if out_tok is not None else None
        except (TypeError, ValueError):
            out_int = None
        pct_after = self.provider_pct(account, "rolling")
        pct_after_refreshed = snapshot_at_before is not None and self.snapshot_at.get(account) != snapshot_at_before
        row = {
            "ts": utc_iso(self.now()),
            "account_fp": hashlib.sha256(account.encode()).hexdigest()[:12],
            "model": model,
            "weight": self.tier_weight(model),
            "input_tokens": in_int,
            "cached_tokens": cached_int,
            "output_tokens": out_int,
            "pct_before": pct_before,
            "pct_after": pct_after,
            "pct_window": "rolling",
            "pct_after_refreshed": bool(pct_after_refreshed),
        }
        parent = os.path.dirname(self.weights_path)
        if parent:
            os.makedirs(parent, mode=0o700, exist_ok=True)
        text = redact_secrets(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n", self.accounts.values())
        with self.write_lock:
            fd = os.open(self.weights_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, text.encode("utf-8"))
            finally:
                os.close(fd)

    def ranked(self, model: str, sticky: Optional[str] = None) -> List[str]:
        candidates: List[Tuple[Tuple[float, float, float, int, int], str]] = []
        for index, name in enumerate(self.accounts):
            if not self.eligible(name, model, lock_held=True):
                continue
            snapshot = self.snapshots[name] or {}
            provider_rolling = float((snapshot.get("rolling") or {}).get("percent") or 0)
            key = (max(provider_rolling, self.local_pct(name, model, "rolling")), float((snapshot.get("weekly") or {}).get("percent") or 0), float((snapshot.get("monthly") or {}).get("percent") or 0), self.round_robin, index)
            candidates.append((key, name))
        candidates.sort(key=lambda item: item[0])
        ordered = [name for _, name in candidates]
        if sticky in ordered:
            snapshot = self.snapshots[sticky] or {}
            if float((snapshot.get("rolling") or {}).get("percent") or 0) < self.sticky_max_pct:
                ordered.remove(sticky)
                ordered.insert(0, sticky)
        return ordered

    def choose(self, model: str, session_key: str, bound_account: Optional[str] = None) -> Optional[str]:
        with self.lock:
            now = self.now()
            sticky, expires = self.sticky.get(session_key, (None, 0.0))
            if now > expires:
                sticky = None
            ordered = ([bound_account] if bound_account in self.accounts and self.eligible(bound_account, model, lock_held=True) else []) if bound_account is not None else self.ranked(model, sticky)
            if not ordered:
                return None
            selected = ordered[0]
            self.sticky[session_key] = (selected, now + 2 * 3600)
            self.round_robin = (self.round_robin + 1) % max(1, len(self.accounts))
            self.request_counts[selected] += 1
            self.in_flight[selected] += 1
            return selected

    def release(self, account: str, worker_lease: Optional[str] = None) -> None:
        with self.lock:
            if worker_lease is not None:
                counts = self.worker_in_flight[account]
                count = counts.get(worker_lease, 0)
                if count < 1:
                    raise RuntimeError("worker_reservation_missing")
                if count == 1:
                    del counts[worker_lease]
                else:
                    counts[worker_lease] = count - 1
            self.in_flight[account] = max(0, self.in_flight[account] - 1)

    def mark_exhausted(self, account: str) -> None:
        snapshot = self.refresh(account, force=True) or {}
        resets = [window for window in WINDOWS if (snapshot.get(window) or {}).get("status") == "rate-limited"]
        if resets:
            until = max(parse_utc((snapshot[reset] or {}).get("resetsAt", "")) if (snapshot[reset] or {}).get("resetsAt") else self.now() + 900 for reset in resets)
        else:
            until = self.now() + 900
        self.exhausted_until[account] = until
        self.last_error[account] = "rate_limited"
        self._persist_state()

    def mark_auth_failed(self, account: str, error_class: str, reason: Optional[str] = None) -> None:
        self.auth_failed[account] = True
        self.auth_failed_at[account] = self.now()
        self.auth_failed_reason[account] = _redact_reason(reason)
        self.last_error[account] = error_class
        self._persist_state()

    def reenable(self, account: str) -> bool:
        if account not in self.accounts:
            return False
        self.auth_failed[account] = False
        self.auth_failed_at[account] = None
        self.auth_failed_reason[account] = None
        self.exhausted_until[account] = 0.0
        self.last_error[account] = None
        self._persist_state()
        return True

    def status(self) -> Dict[str, Any]:
        now = self.now()
        # One lock snapshot joins per-account and exact-lease reservations.
        with self.lock:
            inflight = dict(self.in_flight)
            worker_inflight = {name: dict(counts) for name, counts in self.worker_in_flight.items()}
        return {
            "ok": True,
            "accounts": {
                name: {
                    "provider_windows": self.snapshots[name],
                    "local_models": {
                        model: {window: {"spend_usd": str(self.local_spend(name, model, window)), "pct": round(self.local_pct(name, model, window), 6)} for window in WINDOWS}
                        for model in self.prices["models"] if any(row.get("account") == name and row.get("model") == model for row in self.usage_rows)
                    },
                    "in_flight": inflight[name],
                    "exhausted_until": utc_iso(self.exhausted_until[name]) if self.exhausted_until[name] > now else None,
                    "auth_failed": self.auth_failed[name],
                    "auth_failed_at": utc_iso(self.auth_failed_at[name]) if self.auth_failed_at[name] else None,
                    "auth_failed_reason": self.auth_failed_reason[name],
                    "last_error_class": self.last_error[name],
                    "calibration_factor": self.calibration_factors[name],
                }
                for name in self.accounts
            },
            "gateway_instance_id": self.gateway_instance_id,
            "worker_settlement": "lease-inflight-v1",
            "worker_in_flight": worker_inflight,
            "pool": {"accounts": len(self.accounts), "eligible": sum(1 for name in self.accounts if self.eligible(name, next(iter(self.prices["models"]))))},
        }

    def _pool_exhausted(self, handler: Any) -> None:
        now = self.now()
        candidates = [self.snapshots[name] for name in self.accounts if not self.auth_failed[name]]
        retry = 30
        for snapshot in candidates:
            reset = ((snapshot or {}).get("rolling") or {}).get("resetsAt")
            if reset:
                retry = max(30, int(math.ceil(parse_utc(reset) - now)))
                break
        handler._json(429, {"error": {"type": "go_pool_exhausted", "message": "no eligible account", "windows": {name: (self.snapshots[name] or {}) for name in self.accounts}}}, {"Retry-After": str(retry)})

    def wire_supported(self, model: str, endpoint: str) -> bool:
        wire = wire_of(endpoint)
        return model.lower() not in self.wire_compat or wire not in self.wire_compat[model.lower()]

    def translated_endpoint(self, model: str, endpoint: str) -> Optional[str]:
        if endpoint != "/v1/responses" or self.env.get("GO_RESPONSES_TO_CHAT", DEFAULTS["GO_RESPONSES_TO_CHAT"]) != "1":
            return None
        incompatible = self.wire_compat.get(model.lower(), [])
        if "responses" in incompatible and "chat" not in incompatible:
            return "/v1/chat/completions"
        return None

    def _usage_row(self, handler: Any, account: str, endpoint: str, body: Dict[str, Any], started: float, status: str, response: bytes, attempt: int, replayed_from: Optional[str], error_class: Optional[str] = None, *, pct_before: Optional[float] = None, snapshot_at_before: Optional[float] = None, translated_from: Optional[str] = None) -> None:
        stream = bool(body.get("stream"))
        usage, estimate_class = extract_usage(endpoint, stream, response)
        if usage is None and estimate_class == "estimated_from_bytes":
            usage = {"input": len(response) // 4, "cached_read": 0, "cache_write": 0, "output": 0}
        model = str(body.get("model"))
        if usage is None:
            row = None
        else:
            row = select_price_row(self.prices, model, usage["input"], datetime.fromtimestamp(self.now(), timezone.utc))
            row = effective_price_row(row, self.now())
            if model == "deepseek-v4.1-flash":
                row["promo"]["ends_utc"] = self.promo_ends
            row["monthly_usd"] = row["promo"]["baseline_usd"] if model == "deepseek-v4.1-flash" and self.now() >= parse_utc(self.promo_ends) else row["monthly_usd"]
        row_fields = None if row is None else {key: row.get(key) for key in ("qualifier", "in", "out", "cached_read", "cache_write", "monthly_usd")}
        estimated = Decimal(0) if usage is None else estimate_cost(row, usage)
        self._append_usage({
            "ts": utc_iso(self.now()), "account": account, "model": model, "endpoint": endpoint, "stream": stream,
            "status": status, "latency_ms": int((self.now() - started) * 1000),
            **({} if usage is None else usage), "est_usd": str(estimated), "price_row": row_fields,
            "session_key": session_key(model, body, {key.lower(): value for key, value in handler.headers.items()}),
            "attempt": attempt, "replayed_from": replayed_from, "error_class": error_class or estimate_class,
            "weight": self.tier_weight(model), "tag": "frontier" if self.is_frontier(model) else "bulk",
            **({} if not getattr(handler, "worker_claims", None) else {
                "worker_lease": {key: handler.worker_claims[key] for key in ("lease_id", "root", "model", "run_id", "host")},
                "serving_model": None,
            }),
            **({} if translated_from is None else {"translated_from": translated_from}),
        })
        if account in self.accounts:
            counts = {
                "input_tokens": None if usage is None else usage.get("input"),
                "cached_tokens": None if usage is None else usage.get("cached_read"),
                "output_tokens": None if usage is None else usage.get("output"),
            }
            self._append_weight_row(account, model, counts, pct_before, snapshot_at_before)

    def _upstream(self, handler: Any, endpoint: str, body: bytes, payload: Dict[str, Any], account: str) -> Tuple[Any, Optional[bytes], Optional[int]]:
        headers = {"User-Agent": "mastermind-go-shim/1", "Authorization": "Bearer " + self.accounts[account], "Content-Type": "application/json", "Accept": payload.get("stream") and "text/event-stream" or "application/json"}
        if endpoint == "/v1/messages":
            headers["x-api-key"] = self.accounts[account]
        session_id = handler.headers.get("x-opencode-session") or handler.headers.get("session_id")
        if not session_id:
            session_id = "go-" + session_key(str(payload.get("model") or ""), payload, {key.lower(): value for key, value in handler.headers.items()})[:32]
        if not session_id:
            session_id = "go-" + uuid.uuid4().hex
        headers["x-opencode-session"] = session_id
        for key in ("x-opencode-session", "session_id"):
            if handler.headers.get(key):
                headers[key] = handler.headers[key]
        request = Request(upstream_url(self.upstream_base, endpoint), data=body, headers=headers, method="POST")
        response = urlopen(request, timeout=300)
        if bool(payload.get("stream")):
            prefix = response.read1(13)
            if prefix:
                return response, prefix, None
            response.close()
            raise http.client.RemoteDisconnected("upstream closed before bytes")
        return response, None, None

    def _learn_wire_incompatibility(self, model: str, endpoint: str) -> bool:
        wire = wire_of(endpoint)
        try:
            with open(self.wire_matrix_path, encoding="utf-8") as handle:
                matrix = json.load(handle)
            cells = (matrix.get("models") or {}).get(model) or {}
            current_status = (cells.get(wire) or {}).get("http_status")
            has_other_ok = any(
                cell.get("http_status") == 200
                for other_wire, cell in cells.items()
                if other_wire != wire and isinstance(cell, dict)
            )
            if wire is None or current_status is None or int(current_status) < 500 or not has_other_ok:
                return False
            self.wire_compat.setdefault(model.lower(), [])
            if wire not in self.wire_compat[model.lower()]:
                self.wire_compat[model.lower()].append(wire)
            table = self.wire_compat.copy()
            table["_semantics"] = (
                "map model_id -> list of wires KNOWN INCOMPATIBLE for that model. "
                "Wire tokens: chat | messages | responses. A model absent from this table, "
                "or a wire absent from its list, is UNKNOWN and proceeds to upstream."
            )
            temporary = self.wire_compat_path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(table, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, self.wire_compat_path)
            return True
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return False

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def proxy(self, handler: Any, endpoint: str, body: bytes, model: str, payload: Dict[str, Any], *, upstream_endpoint: Optional[str] = None, translated_from: Optional[str] = None, bound_account: Optional[str] = None, retry_allowed: bool = True) -> None:
        worker_lease = (getattr(handler, "worker_claims", None) or {}).get("lease_id")
        upstream_endpoint = upstream_endpoint or endpoint
        started = self.now()
        key = session_key(model, payload, {key.lower(): value for key, value in handler.headers.items()})
        attempts: List[str] = []
        forwarded_bytes = 0
        total = 0
        same_account_retry: Optional[str] = None
        pct_before: Optional[float] = None
        snapshot_at_before: Optional[float] = None
        while total < (3 if retry_allowed else 1):
            retrying_same_account = same_account_retry is not None
            if same_account_retry is not None:
                with self.lock:
                    account = same_account_retry
                    retryable = not self.auth_failed[account] and self.now() >= self.exhausted_until[account] and self.in_flight[account] < self.max_inflight
                    if retryable:
                        self.in_flight[account] += 1
                        if worker_lease is not None:
                            counts = self.worker_in_flight[account]
                            counts[worker_lease] = counts.get(worker_lease, 0) + 1
                    else:
                        account = None
                same_account_retry = None
            else:
                account = router_choose_for_proxy(self, model, key, exclude=set(attempts), bound_account=bound_account, worker_lease=worker_lease)
            if account is None:
                break
            attempts.append(account)
            total += 1
            pct_before = self.provider_pct(account, "rolling")
            snapshot_at_before = self.snapshot_at.get(account)
            # Quota/wire checks can take time. Recheck a worker's live lease as
            # close to upstream submission as possible; already sent work is
            # not claimed atomically revocable.
            if getattr(handler, "worker_claims", None) and handler._worker_claims(model) is None:
                self.release(account, worker_lease)
                return
            try:
                response, prefix, _ = self._upstream(handler, upstream_endpoint, body, payload, account)
            except HTTPError as error:
                error_body = error.read()
                self.release(account, worker_lease)
                if error.code == 401 or error.code == 403:
                    kind, error_type, message, error_payload = classify_upstream_error(error.code, error_body)
                    if kind == "auth":
                        self.mark_auth_failed(account, f"upstream_{error.code}", f"{error_type or 'unknown'}: {message or ''}")
                        self._log("auth_failed", account=account, status=error.code)
                        self._usage_row(handler, account, upstream_endpoint, payload, started, "upstream_error", error_body, total, None, f"upstream_{error.code}", pct_before=pct_before, snapshot_at_before=snapshot_at_before, translated_from=translated_from)
                        handler._json(error.code, error_payload)
                        return
                    self._learn_wire_incompatibility(model, upstream_endpoint)
                    self._log("upstream_model_error", account=account, status=error.code, model=model, wire=wire_of(upstream_endpoint), error_type=error_type)
                    self._usage_row(handler, account, upstream_endpoint, payload, started, "upstream_error", error_body, total, None, "upstream_model_error", pct_before=pct_before, snapshot_at_before=snapshot_at_before, translated_from=translated_from)
                    handler._json(400, error_payload)
                    return
                text = error_body.decode("utf-8", "replace").lower()
                quota = error.code == 429 or error.code < 500 and re.search(r"quota|limit|rate", text)
                if quota:
                    if forwarded_bytes == 0:
                        self.mark_exhausted(account)
                        if not retry_allowed:
                            self._usage_row(handler, account, upstream_endpoint, payload, started, "upstream_error", error_body, total, None, "worker_upstream_quota", translated_from=translated_from)
                            handler._json(error.code, synthesize_upstream_http_error(error.code, error_body))
                            return
                        continue
                    self.last_error[account] = "rate_limited"
                    handler._json(error.code, json.loads(error_body.decode("utf-8", "replace")))
                    return
                if error.code >= 500 and forwarded_bytes == 0 and retry_allowed and total < 3 and not retrying_same_account:
                    self._learn_wire_incompatibility(model, upstream_endpoint)
                    same_account_retry = account
                    self._sleep(2)
                    continue
                error_payload = synthesize_upstream_http_error(error.code, error_body)
                self._usage_row(handler, account, upstream_endpoint, payload, started, "upstream_error", error_body, total, None, "upstream_http_error", pct_before=pct_before, snapshot_at_before=snapshot_at_before, translated_from=translated_from)
                handler._json(error.code, error_payload)
                return
            except (URLError, OSError, http.client.HTTPException) as error:
                self.release(account, worker_lease)
                self.last_error[account] = type(error).__name__
                if forwarded_bytes > 0:
                    self._usage_row(handler, account, upstream_endpoint, payload, started, "upstream_closed", b"", total, None, type(error).__name__, pct_before=pct_before, snapshot_at_before=snapshot_at_before, translated_from=translated_from)
                    return
                if retry_allowed and total < 3 and not retrying_same_account:
                    same_account_retry = account
                    self._sleep(2)
                elif not retry_allowed:
                    self._usage_row(handler, account, upstream_endpoint, payload, started, "upstream_closed", b"", total, None, type(error).__name__, translated_from=translated_from)
                    handler._json(502, {"error": {"type": "upstream_unavailable", "message": "worker request was not retried"}})
                    return
                continue
            try:
                stream = bool(payload.get("stream"))
                if stream:
                    raw_forwarded = prefix or b""
                    if translated_from:
                        while True:
                            chunk = response.read1(65536) if hasattr(response, "read1") else response.read(65536)
                            if not chunk:
                                break
                            raw_forwarded += chunk
                        forwarded = chat_to_responses_stream(raw_forwarded)
                        forwarded_bytes += len(forwarded)
                        handler.send_response(response.status)
                        handler.send_header("Content-Type", "text/event-stream")
                        handler.send_header("Transfer-Encoding", "chunked")
                        handler.end_headers()
                        handler.wfile.write(b"%x\r\n" % len(forwarded) + forwarded + b"\r\n0\r\n\r\n")
                        handler.wfile.flush()
                        self._usage_row(handler, account, upstream_endpoint, payload, started, "ok", raw_forwarded, total, attempts[-2] if total > 1 else None, pct_before=pct_before, snapshot_at_before=snapshot_at_before, translated_from=translated_from)
                        return
                    handler.send_response(response.status)
                    for name, value in response.headers.items():
                        if name.lower() not in {"connection", "transfer-encoding", "content-length", "server", "date"}:
                            handler.send_header(name, value)
                    handler.send_header("Transfer-Encoding", "chunked")
                    handler.end_headers()
                    forwarded = b""
                    if prefix:
                        forwarded += prefix
                        forwarded_bytes += len(prefix)
                    handler.wfile.write(b"%x\r\n" % len(prefix) + prefix + b"\r\n")
                    handler.wfile.flush()
                    while True:
                        chunk = response.read1(65536) if hasattr(response, "read1") else response.read(65536)
                        if not chunk:
                            break
                        forwarded += chunk
                        forwarded_bytes += len(chunk)
                        handler.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                        handler.wfile.flush()
                    self._usage_row(handler, account, upstream_endpoint, payload, started, "ok", forwarded, total, attempts[-2] if total > 1 else None, pct_before=pct_before, snapshot_at_before=snapshot_at_before, translated_from=translated_from)
                    handler.wfile.write(b"0\r\n\r\n")
                else:
                    response_body = response.read()
                    self._usage_row(handler, account, upstream_endpoint, payload, started, "ok", response_body, total, attempts[-2] if total > 1 else None, pct_before=pct_before, snapshot_at_before=snapshot_at_before, translated_from=translated_from)
                    returned = chat_to_responses_response(json.loads(response_body.decode("utf-8"))) if translated_from else json.loads(response_body.decode("utf-8"))
                    handler._json(response.status, returned, dict(response.headers.items()))
                return
            except HTTPError as error:
                error_body = error.read()
                if error.code == 429 or error.code < 500 and re.search(r"quota|limit|rate", error_body.decode("utf-8", "replace").lower()):
                    if forwarded_bytes == 0:
                        self.mark_exhausted(account)
                        continue
                    self.last_error[account] = "rate_limited"
                    self._usage_row(handler, account, upstream_endpoint, payload, started, "upstream_error", error_body, total, None, "upstream_429_post_effect", pct_before=pct_before, snapshot_at_before=snapshot_at_before, translated_from=translated_from)
                    return
                raise
            except (BrokenPipeError, ConnectionResetError):
                self._usage_row(handler, account, upstream_endpoint, payload, started, "client_closed", b"", total, None, "client_closed", pct_before=pct_before, snapshot_at_before=snapshot_at_before, translated_from=translated_from)
                return
            except (URLError, OSError, http.client.HTTPException) as error:
                self.last_error[account] = type(error).__name__
                self._usage_row(handler, account, upstream_endpoint, payload, started, "upstream_closed", b"", total, None, type(error).__name__, pct_before=pct_before, snapshot_at_before=snapshot_at_before, translated_from=translated_from)
                return
            finally:
                response.close()
                self.release(account, worker_lease)
        self._pool_exhausted(handler)


def router_choose_for_proxy(router: Router, model: str, key: str, exclude: set, bound_account: Optional[str] = None, worker_lease: Optional[str] = None) -> Optional[str]:
    with router.lock:
        now = router.now()
        sticky, expires = router.sticky.get(key, (None, 0.0))
        if now > expires:
            sticky = None
        ordered = ([bound_account] if bound_account in router.accounts and router.eligible(bound_account, model, lock_held=True) else []) if bound_account is not None else router.ranked(model, sticky)
        ordered = [name for name in ordered if name not in exclude]
        if not ordered:
            return None
        selected = ordered[0]
        router.sticky[key] = (selected, now + 2 * 3600)
        router.round_robin = (router.round_robin + 1) % max(1, len(router.accounts))
        router.request_counts[selected] += 1
        router.in_flight[selected] += 1
        if worker_lease is not None:
            counts = router.worker_in_flight[selected]
            counts[worker_lease] = counts.get(worker_lease, 0) + 1
        return selected


def stat_mode(path: str) -> int:
    return os.stat(path, follow_symlinks=False).st_mode & 0o777


# A worker's completed response must not outrun its account/lease settlement.
# Controller streams retain their existing behavior. No retry or request queue.
WORKER_REPLY_LIMIT = 16 * 1024 * 1024


class WorkerReplyBuffer(io.BytesIO):
    def write(self, data):
        if self.tell() + len(data) > WORKER_REPLY_LIMIT:
            raise ValueError("worker response exceeds bound")
        return super().write(data)


def make_server(router: Router, port: int = 0, lease_gateway: Any = None) -> ThreadingHTTPServer:
    # Capability validity is checked against live broker state per request.
    # This does not claim atomic cancellation of an already forwarded inference.
    worker_inflight = set()
    worker_inflight_lock = threading.Lock()
    source_sha256 = {}
    for name, path in (("go_shim.py", __file__),
                       ("go_lease_capability.py", os.path.join(_EXT_DIR, "go_lease_capability.py")),
                       ("go_lease_gateway.py", os.path.join(_EXT_DIR, "go_lease_gateway.py"))):
        if os.path.isfile(path):
            with open(path, "rb") as source:
                source_sha256[name] = hashlib.sha256(source.read()).hexdigest()
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _json(self, status: int, payload: Any, headers: Optional[Dict[str, str]] = None) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            values = self.headers.get_all("Authorization") or []
            return len(values) == 1 and check_auth(values[0], router.token)

        def _refuse(self, status: int, kind: str) -> None:
            self.close_connection = True
            self._json(status, {"error": {"type": kind, "message": "request refused"}})

        def _one(self, name: str) -> str:
            values = self.headers.get_all(name) or []
            if len(values) != 1 or not values[0]:
                raise ValueError("one header required")
            return values[0]

        def _read_object(self, limit: int = 8 * 1024 * 1024) -> Tuple[bytes, Dict[str, Any]]:
            if self.headers.get_all("Transfer-Encoding"):
                raise ValueError("unsupported framing")
            length = self._one("Content-Length")
            if not re.fullmatch(r"[0-9]{1,8}", length) or not 0 < int(length) <= limit:
                raise ValueError("invalid length")
            raw = self.rfile.read(int(length))
            if len(raw) != int(length):
                raise ValueError("incomplete body")
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result:
                        raise ValueError("duplicate key")
                    result[key] = value
                return result
            def constant(value):
                raise ValueError("nonfinite number")
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
            if not isinstance(payload, dict):
                raise ValueError("object required")
            return raw, payload

        def _worker_claims(self, model: str) -> Optional[Dict[str, Any]]:
            try:
                if lease_gateway is None or self.headers.get_all("X-MM-Leased") or self.headers.get_all("X-MM-Pool-Account"):
                    raise ValueError("worker capability unavailable")
                authorization = self._one("Authorization")
                if not authorization.startswith("Bearer v1."):
                    raise ValueError("worker bearer required")
                model_headers = self.headers.get_all("X-MM-Worker-Model") or []
                if model_headers and model_headers != [model]:
                    raise ValueError("conflicting model")
                claims = lease_gateway.authorize(authorization[7:], model=model,
                    run_id=self._one("X-MM-Run-Id"), host=self._one("X-MM-Host"))
                if claims["account"] not in router.accounts:
                    raise ValueError("unknown account")
                self.worker_claims = claims
                return claims
            except Exception:
                self._refuse(401, "worker_capability_refused")
                return None

        def _dispatch_proxy(self, path: str, body: bytes, model: str, payload: Dict[str, Any], *, controller: bool, bound_account: Optional[str], **kwargs: Any) -> None:
            lease_id = None if controller else self.worker_claims["lease_id"]
            if lease_id is not None:
                with worker_inflight_lock:
                    with router.lock:
                        unresolved = router.worker_in_flight[self.worker_claims["account"]].get(lease_id, 0) > 0
                    if lease_id in worker_inflight or unresolved:
                        self._refuse(429, "worker_lease_busy")
                        return
                    worker_inflight.add(lease_id)
            output = self.wfile
            buffered = WorkerReplyBuffer() if lease_id is not None else None
            failed = False
            if buffered is not None:
                self.wfile = buffered
            try:
                router.proxy(self, path, body, model, payload, bound_account=bound_account, retry_allowed=controller, **kwargs)
            except Exception:
                if buffered is None:
                    raise
                failed = True
            finally:
                self.wfile = output
                if lease_id is not None:
                    with worker_inflight_lock:
                        worker_inflight.discard(lease_id)
            if buffered is not None:
                try:
                    if failed:
                        # No partial successful response escaped. Do not replay upstream.
                        self._headers_buffer = []
                        self._refuse(502, "worker_response_incomplete")
                    else:
                        # proxy() has closed upstream and released account bookkeeping;
                        # the per-lease guard above is also clear before completion is visible.
                        output.write(buffered.getvalue())
                        output.flush()
                finally:
                    buffered.close()

        def _account_binding(self) -> Tuple[bool, Optional[str]]:
            leased = self.headers.get_all("X-MM-Leased") or []
            accounts = self.headers.get_all("X-MM-Pool-Account") or []
            if not leased and not accounts:
                return True, None  # Existing unleased clients retain legacy routing.
            if leased == ["1"] and len(accounts) == 1 and accounts[0] in router.accounts:
                return True, accounts[0]
            self._json(400, {"error": {"type": "invalid_account_binding", "message": "one valid leased account is required"}})
            return False, None

        def do_GET(self) -> None:
            path = self.path.partition("?")[0]
            if path == "/health":
                self._json(200, {"ok": True, "accounts": len(router.accounts), "eligible": None, "eligibility_source": "/status", "account_binding": "exact-v1",
                    "worker_capabilities": "lease-v1" if lease_gateway is not None else None, "source_sha256": source_sha256,
                    "gateway_instance_id": router.gateway_instance_id})
                return
            if path == "/worker-health":
                try:
                    model = self._one("X-MM-Worker-Model")
                except ValueError:
                    self._refuse(401, "worker_capability_refused")
                    return
                claims = self._worker_claims(model)
                if claims is not None:
                    self._json(200, {"ok": True, "worker_capabilities": "lease-v1", "source_sha256": source_sha256,
                        "lease_id": claims["lease_id"], "run_id": claims["run_id"], "model": claims["model"], "host": claims["host"], "account": claims["account"], "root": claims["root"], "expires_at": claims["expires_at"]})
                return
            if not self._authorized():
                self._refuse(401, "unauthorized")
                return
            if path == "/status":
                self._json(200, router.status())
                return
            if path == "/v1/models":
                valid, bound_account = self._account_binding()
                if not valid:
                    return
                account = None
                released = False
                try:
                    account = router.choose(next(iter(router.prices["models"])), "models", bound_account=bound_account)
                    if account is None:
                        raise RuntimeError("pool exhausted")
                    try:
                        payload = router._get_json(account, "/models")
                        released = True
                        router.release(account)
                        self._json(200, payload)
                    finally:
                        if not released:
                            router.release(account)
                except Exception:
                    if not self.wfile.closed:
                        self._json(429, {"error": {"type": "go_pool_exhausted", "message": "no eligible account"}})
                return
            self._json(404, {"error": {"type": "not_found", "message": self.path}})

        def do_POST(self) -> None:
            self.worker_claims = None
            path = self.path.partition("?")[0]
            controller = self._authorized()
            if path in {"/worker-capabilities", "/reenable"}:
                if not controller:
                    self._refuse(401, "unauthorized")
                    return
                try:
                    _, payload = self._read_object(16384)
                    if path == "/worker-capabilities":
                        if lease_gateway is None:
                            self._refuse(404, "worker_capabilities_disabled")
                            return
                        issued = lease_gateway.issue(payload)
                        self._json(200, issued, {"Cache-Control": "no-store"})
                        return
                    if router.reenable(str(payload.get("account") or "")):
                        self._json(200, {"ok": True})
                    else:
                        self._refuse(404, "unknown_account")
                except Exception:
                    self._refuse(400, "invalid_control_request")
                return
            if path not in {"/v1/chat/completions", "/v1/messages", "/v1/responses"}:
                self._refuse(404, "not_found")
                return
            if not controller:
                values = self.headers.get_all("Authorization") or []
                if lease_gateway is None or len(values) != 1 or not values[0].startswith("Bearer v1."):
                    self._refuse(401, "unauthorized")
                    return
            try:
                body, payload = self._read_object()
                model = payload.get("model")
                if not isinstance(model, str) or not model:
                    raise ValueError("model required")
            except Exception:
                self._refuse(400, "invalid_json")
                return
            if controller:
                valid, bound_account = self._account_binding()
                if not valid:
                    self.close_connection = True
                    return
            else:
                claims = self._worker_claims(model)
                if claims is None:
                    return
                bound_account = claims["account"]
            if model not in router.prices["models"] and model not in router.prices["unpriced"]:
                self._json(400, {"error": {"type": "unknown_model", "message": "unknown model", "known_ids": list(router.prices["models"]) + router.prices["unpriced"]}})
                return
            if model in router.prices["unpriced"] and not router.allow_unpriced:
                self._json(400, {"error": {"type": "unpriced_model", "message": f"{model} has no published price row"}})
                return
            if router.prices["models"].get(model, {}).get("training_consent") and not router.allow_training:
                self._json(400, {"error": {"type": "training_consent_required", "message": f"{model} requires training consent"}})
                return
            if not router.wire_supported(model, path):
                upstream_endpoint = router.translated_endpoint(model, path)
                if upstream_endpoint is None:
                    wire = wire_of(path)
                    self._json(400, {"error": {"type": "wire_unsupported", "message": f"{model} is not served on the {wire} wire", "model": model, "wire": wire}})
                    return
                upstream_payload = responses_to_chat_request(payload)
                upstream_body = json.dumps(upstream_payload, separators=(",", ":")).encode("utf-8")
                gate = router.tier_budget_gate(model)
                if not gate["allowed"]:
                    router.ledger_tier_refusal(model, path, payload, {key.lower(): value for key, value in self.headers.items()}, gate)
                    self._json(429, {"error": {"type": "go_tier_budget", "message": f"{model} is weight-{gate['weight']} (frontier); every account is at or above {gate['threshold_pct']}% of its monthly Go quota", "model": model, "weight": gate["weight"], "threshold_pct": gate["threshold_pct"], "min_monthly_pct": gate["min_monthly_pct"], "accounts_checked": gate["accounts_checked"]},}, {"Retry-After": str(gate["retry_after"])})
                    return
                self._dispatch_proxy(path, upstream_body, model, upstream_payload, upstream_endpoint=upstream_endpoint, translated_from="responses", bound_account=bound_account, controller=controller)
                return
            gate = router.tier_budget_gate(model)
            if not gate["allowed"]:
                router.ledger_tier_refusal(model, path, payload, {key.lower(): value for key, value in self.headers.items()}, gate)
                self._json(
                    429,
                    {
                        "error": {
                            "type": "go_tier_budget",
                            "message": f"{model} is weight-{gate['weight']} (frontier); every account is at or above {gate['threshold_pct']}% of its monthly Go quota",
                            "model": model,
                            "weight": gate["weight"],
                            "threshold_pct": gate["threshold_pct"],
                            "min_monthly_pct": gate["min_monthly_pct"],
                            "accounts_checked": gate["accounts_checked"],
                        }
                    },
                    {"Retry-After": str(gate["retry_after"])},
                )
                return
            self._dispatch_proxy(path, body, model, payload, bound_account=bound_account, controller=controller)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> int:
    if "--check" in sys.argv:
        state_dir = os.environ.get("GO_STATE_DIR", DEFAULTS["GO_STATE_DIR"])
        try:
            Router(os.environ.get("GO_ACCOUNTS_PATH", DEFAULTS["GO_ACCOUNTS_PATH"]), os.environ.get("GO_UPSTREAM_BASE", DEFAULTS["GO_UPSTREAM_BASE"]), state_dir)
        except Exception as error:
            print(f"go_shim: {error}", file=sys.stderr)
            return 1
        return 0
    state_dir = os.environ.get("GO_STATE_DIR", DEFAULTS["GO_STATE_DIR"])
    acquire_singleton_lock(os.path.join(state_dir, "shim.lock"))
    router = Router(os.environ.get("GO_ACCOUNTS_PATH", DEFAULTS["GO_ACCOUNTS_PATH"]), os.environ.get("GO_UPSTREAM_BASE", DEFAULTS["GO_UPSTREAM_BASE"]), state_dir)
    write_pid(router.pid_path)
    gateway = None
    if os.environ.get("GO_WORKER_CAPABILITIES") == "1":
        from go_lease_gateway import GoLeaseGateway
        gateway = GoLeaseGateway(os.path.join(_EXT_DIR, "broker", "leases.sqlite"),
            router.accounts, set(router.prices["models"]) | set(router.prices["unpriced"]))
    server = make_server(router, int(os.environ.get("GO_SHIM_PORT", DEFAULTS["GO_SHIM_PORT"])), lease_gateway=gateway)
    print(f"go_shim listening port={server.server_port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
