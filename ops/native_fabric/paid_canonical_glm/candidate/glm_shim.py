#!/usr/bin/env python3
"""Localhost OpenAI Responses API -> Z.ai chat-completions shim (stdlib only)."""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import re
import io
import json
import os
import secrets
import signal
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
_EXT_DIR = os.path.dirname(HERE)
if _EXT_DIR not in sys.path:  # glm_keys / quota_remote live one level up (ext/)
    sys.path.insert(0, _EXT_DIR)
DEFAULT_PORT = 4141
DEFAULT_OPENAI_BASE = "https://api.z.ai/api/coding/paas/v4"
DEFAULT_MODEL = "glm-5.3-flash"
TOKEN_PATH = os.path.join(HERE, ".token")
PID_PATH = os.path.join(HERE, "shim.pid")
LOCK_PATH = os.path.join(HERE, "shim.lock")
LOG_PATH = os.path.join(HERE, "shim.log")
USAGE_PATH = os.path.join(HERE, "usage.jsonl")
STDOUT_PATH = os.path.join(HERE, "shim.stdout")
DEFAULT_NAMED_CLIENT_UA_PATTERNS = "^codex(_[A-Za-z0-9]+)?/,^claude-cli/"
UNGUARDED_PATHS = ("/health", "/status")

_LOG_LOCK = threading.Lock()
_FILE_LOCK_FD = None


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return "%s_%s" % (prefix, secrets.token_hex(12))


def redact_secrets(text: str, secrets_list: Iterable[str]) -> str:
    if not text:
        return text or ""
    out = text
    for s in secrets_list:
        if s:
            out = out.replace(s, "[REDACTED]")
    return out


def check_auth(authorization: Optional[str], token: str) -> bool:
    if not token or not authorization:
        return False
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    got = parts[1].strip()
    if len(got) != len(token):
        return False
    return hmac.compare_digest(got, token)


def _named_client_patterns() -> List[re.Pattern[str]]:
    raw = os.environ.get(
        "GLM_NAMED_CLIENT_UA_PATTERNS",
        DEFAULT_NAMED_CLIENT_UA_PATTERNS,
    )
    return [
        re.compile(pattern, re.IGNORECASE)
        for pattern in raw.split(",")
        if pattern.strip()
    ]


def _client_user_agent_is_valid(value: Optional[str]) -> bool:
    if not value or not value.strip() or len(value) > 512:
        return False
    return all(0x20 <= ord(char) <= 0x7E for char in value)


def named_client_allowed(user_agent: Optional[str]) -> bool:
    if not _client_user_agent_is_valid(user_agent):
        return False
    return any(pattern.search(user_agent) for pattern in _named_client_patterns())


def named_client_enforced() -> bool:
    return os.environ.get("GLM_NAMED_CLIENT_ENFORCE", "1").strip() != "0"


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    cfg_path = path or os.environ.get("GLM_CONFIG") or os.path.expanduser("~/.glm/config.json")
    with open(cfg_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raw = {}
    api_key = raw.get("api_key") if isinstance(raw.get("api_key"), str) else ""
    base = raw.get("openai_base_url") if isinstance(raw.get("openai_base_url"), str) else ""
    model = raw.get("model") if isinstance(raw.get("model"), str) else ""
    port = raw.get("shim_port", DEFAULT_PORT)
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    return {
        "api_key": api_key,
        "openai_base_url": (base or DEFAULT_OPENAI_BASE).rstrip("/"),
        "model": model or DEFAULT_MODEL,
        "shim_port": port,
        "forward_reasoning": bool(raw.get("forward_reasoning")),
    }


def ensure_token(path: str = TOKEN_PATH) -> str:
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            tok = fh.read().strip()
        if tok:
            return tok
    tok = secrets.token_hex(16)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, tok.encode("utf-8"))
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    return tok


def usage_from_openai(usage: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    usage = usage or {}
    inp = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or (inp + out))
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    cached = int((details or {}).get("cached_tokens") or usage.get("cached_tokens") or 0)
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": total,
        "input_tokens_details": {"cached_tokens": cached},
        "output_tokens_details": {"reasoning_tokens": 0},
    }


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
                continue
            if not isinstance(p, dict):
                continue
            ptype = p.get("type") or ""
            if ptype in ("input_text", "output_text", "text"):
                parts.append(p.get("text") or "")
            elif ptype == "input_image":
                parts.append("[image]")
            elif "text" in p and isinstance(p.get("text"), str):
                parts.append(p["text"])
        return "".join(parts)
    return str(content)


_ROLE_MAP = {"developer": "system", "system": "system", "user": "user", "assistant": "assistant", "tool": "tool"}


def _flush_tool_buf(messages: List[Dict[str, Any]], buf: List[Dict[str, Any]]) -> None:
    if not buf:
        return
    messages.append({"role": "assistant", "content": "", "tool_calls": list(buf)})
    buf.clear()


def _map_role(role: str) -> str:
    return _ROLE_MAP.get((role or "user").lower(), "user")


def sanitize_chat_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only roles GLM chat-completions accepts; drop empty non-tool turns."""
    out: List[Dict[str, Any]] = []
    for msg in messages:
        role = _map_role(msg.get("role") or "user")
        content = msg.get("content")
        if content is None:
            content = ""
        tool_calls = msg.get("tool_calls")
        if role == "assistant" and tool_calls:
            out.append({"role": "assistant", "content": content if isinstance(content, str) else "", "tool_calls": tool_calls})
            continue
        if role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id") or "",
                    "content": content if isinstance(content, str) else _as_str_output(content),
                }
            )
            continue
        if isinstance(content, str) and content:
            out.append({"role": role, "content": content})
    return out


def _item_type(item: Dict[str, Any]) -> str:
    if item.get("type"):
        return str(item["type"])
    if "role" in item:
        return "message"
    return ""


def _as_str_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=True)
    except TypeError:
        return str(value)


def _custom_args(item: Dict[str, Any]) -> str:
    if "arguments" in item and item["arguments"] not in (None, ""):
        args = item["arguments"]
        return args if isinstance(args, str) else json.dumps(args)
    inp = item.get("input")
    if inp is None:
        inp = ""
    if not isinstance(inp, str):
        inp = json.dumps(inp)
    return json.dumps({"input": inp}, ensure_ascii=True)


def responses_request_to_chat(req: Dict[str, Any]) -> Tuple[Dict[str, Any], Set[str]]:
    """Translate a Responses request body to a chat-completions body.

    Returns (chat_request, custom_tool_names).
    """
    custom_names: Set[str] = set()
    messages: List[Dict[str, Any]] = []
    instructions = req.get("instructions")
    if isinstance(instructions, str) and instructions:
        messages.append({"role": "system", "content": instructions})

    raw_input = req.get("input")
    tool_buf: List[Dict[str, Any]] = []
    if isinstance(raw_input, str):
        messages.append({"role": "user", "content": raw_input})
    elif isinstance(raw_input, list):
        for item in raw_input:
            if not isinstance(item, dict):
                continue
            typ = _item_type(item)
            if typ in ("reasoning", "item_reference"):
                continue
            if typ == "message":
                _flush_tool_buf(messages, tool_buf)
                role = _map_role(item.get("role") or "user")
                messages.append({"role": role, "content": _content_to_text(item.get("content"))})
                continue
            if typ == "function_call":
                call_id = item.get("call_id") or item.get("id") or new_id("call")
                args = item.get("arguments")
                if args is None:
                    args = ""
                if not isinstance(args, str):
                    args = json.dumps(args)
                tool_buf.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": item.get("name") or "",
                            "arguments": args,
                        },
                    }
                )
                continue
            if typ == "custom_tool_call":
                call_id = item.get("call_id") or item.get("id") or new_id("call")
                tool_buf.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": item.get("name") or "",
                            "arguments": _custom_args(item),
                        },
                    }
                )
                continue
            if typ in ("function_call_output", "custom_tool_call_output"):
                _flush_tool_buf(messages, tool_buf)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item.get("call_id") or item.get("id") or "",
                        "content": _as_str_output(item.get("output")),
                    }
                )
                continue
            if typ == "local_shell_call":
                _flush_tool_buf(messages, tool_buf)
                continue
        _flush_tool_buf(messages, tool_buf)

    chat_tools: List[Dict[str, Any]] = []
    for tool in req.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        ttype = tool.get("type")
        if ttype == "function":
            fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
            chat_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": fn.get("name") or tool.get("name") or "",
                        "description": fn.get("description") or tool.get("description") or "",
                        "parameters": fn.get("parameters") or tool.get("parameters") or {"type": "object", "properties": {}},
                    },
                }
            )
        elif ttype == "custom":
            name = tool.get("name") or ""
            if name:
                custom_names.add(name)
            chat_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description") or "",
                        "parameters": {
                            "type": "object",
                            "properties": {"input": {"type": "string"}},
                            "required": ["input"],
                        },
                    },
                }
            )
        else:
            sys.stderr.write("drop tool type=%s\n" % (ttype or "?"))

    tool_choice = req.get("tool_choice")
    mapped_choice: Any = None
    if isinstance(tool_choice, str):
        mapped_choice = tool_choice
    elif isinstance(tool_choice, dict):
        if tool_choice.get("type") == "function":
            name = tool_choice.get("name")
            if not name and isinstance(tool_choice.get("function"), dict):
                name = tool_choice["function"].get("name")
            if name:
                mapped_choice = {"type": "function", "function": {"name": name}}
        elif "function" in tool_choice:
            mapped_choice = tool_choice

    chat: Dict[str, Any] = {
        "model": req.get("model") or DEFAULT_MODEL,
        "messages": messages,
    }
    if chat_tools:
        chat["tools"] = chat_tools
    if mapped_choice is not None:
        chat["tool_choice"] = mapped_choice
    if "parallel_tool_calls" in req:
        chat["parallel_tool_calls"] = req["parallel_tool_calls"]
    if req.get("max_output_tokens") is not None:
        chat["max_tokens"] = req["max_output_tokens"]
    if "temperature" in req:
        chat["temperature"] = req["temperature"]
    if "top_p" in req:
        chat["top_p"] = req["top_p"]
    effort = None
    reasoning = req.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
    if effort is not None and effort != "none":
        chat["thinking"] = {"type": "enabled"}
    if req.get("stream"):
        chat["stream"] = True
        chat["stream_options"] = {"include_usage": True}
    chat["messages"] = sanitize_chat_messages(messages)
    return chat, custom_names


def custom_input_from_arguments(arguments: str) -> str:
    if not arguments:
        return ""
    try:
        obj = json.loads(arguments)
    except (TypeError, ValueError):
        return arguments
    if isinstance(obj, dict) and "input" in obj:
        val = obj["input"]
        return val if isinstance(val, str) else json.dumps(val, ensure_ascii=True)
    return arguments


def _message_item(text: str, item_id: Optional[str] = None, status: str = "completed") -> Dict[str, Any]:
    return {
        "type": "message",
        "id": item_id or new_id("msg"),
        "role": "assistant",
        "status": status,
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _function_item(name: str, arguments: str, call_id: str, item_id: Optional[str] = None, status: str = "completed") -> Dict[str, Any]:
    return {
        "type": "function_call",
        "id": item_id or new_id("fc"),
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
        "status": status,
    }


def _custom_item(name: str, arguments: str, call_id: str, item_id: Optional[str] = None, status: str = "completed") -> Dict[str, Any]:
    return {
        "type": "custom_tool_call",
        "id": item_id or new_id("ctc"),
        "call_id": call_id,
        "name": name,
        "input": custom_input_from_arguments(arguments),
        "status": status,
    }


def chat_response_to_responses(
    chat: Dict[str, Any],
    custom_names: Optional[Set[str]] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    custom_names = custom_names or set()
    choice = {}
    choices = chat.get("choices") or []
    if choices and isinstance(choices[0], dict):
        choice = choices[0]
    msg = choice.get("message") or {}
    output: List[Dict[str, Any]] = []
    text = msg.get("content")
    if isinstance(text, str) and text:
        output.append(_message_item(text))
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        name = fn.get("name") or tc.get("name") or ""
        args = fn.get("arguments") or ""
        if not isinstance(args, str):
            args = json.dumps(args)
        call_id = tc.get("id") or new_id("call")
        if name in custom_names:
            output.append(_custom_item(name, args, call_id))
        else:
            output.append(_function_item(name, args, call_id))
    used_model = model or chat.get("model") or DEFAULT_MODEL
    return {
        "id": new_id("resp"),
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "error": None,
        "model": used_model,
        "output": output,
        "usage": usage_from_openai(chat.get("usage")),
    }


class StreamEmitter:
    def __init__(self, model: str, custom_names: Optional[Set[str]] = None, forward_reasoning: bool = False):
        self.model = model
        self.custom_names = custom_names or set()
        self.forward_reasoning = forward_reasoning
        self.seq = 0
        self.resp_id = new_id("resp")
        self.created_at = int(time.time())
        self.events: List[Tuple[str, Dict[str, Any]]] = []
        self.output: List[Dict[str, Any]] = []
        self.usage = usage_from_openai({})
        self._text: Optional[Dict[str, Any]] = None
        self._tools: Dict[int, Dict[str, Any]] = {}
        self._reason: Optional[Dict[str, Any]] = None

    def _emit(self, typ: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {"type": typ, "sequence_number": self.seq}
        if extra:
            data.update(extra)
        self.seq += 1
        self.events.append((typ, data))
        return data

    def _skeleton(self, status: str = "in_progress") -> Dict[str, Any]:
        return {
            "id": self.resp_id,
            "object": "response",
            "created_at": self.created_at,
            "status": status,
            "error": None,
            "model": self.model,
            "output": list(self.output),
        }

    def start(self) -> None:
        self._emit("response.created", {"response": self._skeleton("in_progress")})
        self._emit("response.in_progress", {"response": self._skeleton("in_progress")})

    def _ensure_text(self) -> Dict[str, Any]:
        if self._text is None:
            item = _message_item("", new_id("msg"), status="in_progress")
            item["content"][0]["text"] = ""
            self._text = {"item": item, "text": ""}
            self._emit(
                "response.output_item.added",
                {"output_index": len(self.output), "item": dict(item, content=[], status="in_progress")},
            )
            self._emit(
                "response.content_part.added",
                {
                    "item_id": item["id"],
                    "output_index": len(self.output),
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                },
            )
        return self._text

    def _finish_text(self) -> None:
        st = self._text
        if not st:
            return
        item = st["item"]
        text = st["text"]
        item["content"][0]["text"] = text
        item["status"] = "completed"
        idx = len(self.output)
        self._emit(
            "response.output_text.done",
            {"item_id": item["id"], "output_index": idx, "content_index": 0, "text": text},
        )
        self._emit(
            "response.content_part.done",
            {
                "item_id": item["id"],
                "output_index": idx,
                "content_index": 0,
                "part": {"type": "output_text", "text": text, "annotations": []},
            },
        )
        self._emit("response.output_item.done", {"output_index": idx, "item": item})
        self.output.append(item)
        self._text = None

    def _ensure_reason(self) -> Dict[str, Any]:
        if self._reason is None:
            item = {
                "type": "reasoning",
                "id": new_id("rs"),
                "status": "in_progress",
                "summary": [{"type": "summary_text", "text": ""}],
            }
            self._reason = {"item": item, "text": ""}
            self._emit("response.output_item.added", {"output_index": len(self.output), "item": item})
        return self._reason

    def _finish_reason(self) -> None:
        st = self._reason
        if not st:
            return
        item = st["item"]
        item["status"] = "completed"
        item["summary"] = [{"type": "summary_text", "text": st["text"]}]
        self._emit("response.output_item.done", {"output_index": len(self.output), "item": item})
        self.output.append(item)
        self._reason = None

    def _tool_index_base(self) -> int:
        n = len(self.output)
        if self._text:
            n += 1
        if self._reason:
            n += 1
        return n

    def _ensure_tool(self, idx: int, tc: Dict[str, Any]) -> Dict[str, Any]:
        if idx not in self._tools:
            self._finish_reason()
            self._finish_text()
            fn = tc.get("function") or {}
            name = fn.get("name") or tc.get("name") or ""
            call_id = tc.get("id") or new_id("call")
            is_custom = name in self.custom_names
            item_id = new_id("ctc" if is_custom else "fc")
            if is_custom:
                item = {
                    "type": "custom_tool_call",
                    "id": item_id,
                    "call_id": call_id,
                    "name": name,
                    "input": "",
                    "status": "in_progress",
                }
            else:
                item = {
                    "type": "function_call",
                    "id": item_id,
                    "call_id": call_id,
                    "name": name,
                    "arguments": "",
                    "status": "in_progress",
                }
            out_idx = self._tool_index_base() + len(self._tools)
            self._tools[idx] = {
                "item": item,
                "args": "",
                "is_custom": is_custom,
                "output_index": out_idx,
                "name": name,
            }
            self._emit("response.output_item.added", {"output_index": out_idx, "item": dict(item)})
        else:
            st = self._tools[idx]
            fn = tc.get("function") or {}
            if fn.get("name") and not st["item"].get("name"):
                st["item"]["name"] = fn["name"]
                st["name"] = fn["name"]
                if fn["name"] in self.custom_names:
                    st["is_custom"] = True
                    st["item"]["type"] = "custom_tool_call"
                    st["item"].setdefault("input", "")
            if tc.get("id") and not st["item"].get("call_id"):
                st["item"]["call_id"] = tc["id"]
        return self._tools[idx]

    def _finish_tool(self, idx: int) -> None:
        st = self._tools.pop(idx, None)
        if not st:
            return
        item = st["item"]
        args = st["args"]
        out_idx = st["output_index"]
        if st["is_custom"]:
            inp = custom_input_from_arguments(args)
            item["input"] = inp
            item["status"] = "completed"
            if args:
                self._emit(
                    "response.custom_tool_call_input.delta",
                    {"item_id": item["id"], "output_index": out_idx, "delta": inp},
                )
            self._emit(
                "response.custom_tool_call_input.done",
                {"item_id": item["id"], "output_index": out_idx, "input": inp},
            )
        else:
            item["arguments"] = args
            item["status"] = "completed"
            self._emit(
                "response.function_call_arguments.done",
                {
                    "item_id": item["id"],
                    "output_index": out_idx,
                    "name": item.get("name") or "",
                    "arguments": args,
                },
            )
        self._emit("response.output_item.done", {"output_index": out_idx, "item": item})
        self.output.append(item)

    def on_chunk(self, chunk: Dict[str, Any]) -> None:
        if chunk.get("usage"):
            self.usage = usage_from_openai(chunk["usage"])
        if chunk.get("model"):
            self.model = chunk["model"]
        choices = chunk.get("choices") or []
        if not choices:
            return
        choice = choices[0] if isinstance(choices[0], dict) else {}
        delta = choice.get("delta") or {}
        finish = choice.get("finish_reason")

        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        if reasoning and self.forward_reasoning:
            st = self._ensure_reason()
            st["text"] += reasoning
            self._emit(
                "response.reasoning_summary_text.delta",
                {
                    "item_id": st["item"]["id"],
                    "output_index": len(self.output),
                    "summary_index": 0,
                    "delta": reasoning,
                },
            )

        content = delta.get("content")
        if isinstance(content, str) and content:
            st = self._ensure_text()
            st["text"] += content
            self._emit(
                "response.output_text.delta",
                {
                    "item_id": st["item"]["id"],
                    "output_index": len(self.output),
                    "content_index": 0,
                    "delta": content,
                },
            )

        for tc in delta.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            idx = int(tc.get("index") or 0)
            st = self._ensure_tool(idx, tc)
            fn = tc.get("function") or {}
            arg_delta = fn.get("arguments")
            if isinstance(arg_delta, str) and arg_delta:
                st["args"] += arg_delta
                if not st["is_custom"]:
                    self._emit(
                        "response.function_call_arguments.delta",
                        {
                            "item_id": st["item"]["id"],
                            "output_index": st["output_index"],
                            "delta": arg_delta,
                        },
                    )

        if finish:
            self.finish_open()

    def finish_open(self) -> None:
        self._finish_reason()
        self._finish_text()
        for idx in list(sorted(self._tools)):
            self._finish_tool(idx)

    def completed(self) -> Dict[str, Any]:
        self.finish_open()
        resp = self._skeleton("completed")
        resp["usage"] = self.usage
        self._emit("response.completed", {"response": resp})
        return resp


def translate_stream(
    chunks: Iterable[Dict[str, Any]],
    custom_names: Optional[Set[str]] = None,
    model: str = DEFAULT_MODEL,
    forward_reasoning: bool = False,
) -> List[Tuple[str, Dict[str, Any]]]:
    em = StreamEmitter(model, custom_names, forward_reasoning)
    em.start()
    for chunk in chunks:
        if isinstance(chunk, dict):
            em.on_chunk(chunk)
    em.completed()
    return em.events


def parse_chat_sse(text: str) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            chunks.append(obj)
    return chunks


def iter_sse_chunks(fp) -> Iterator[Dict[str, Any]]:
    while True:
        line = fp.readline()
        if not line:
            break
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def format_sse(event_type: str, data: Dict[str, Any]) -> bytes:
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    return ("event: %s\ndata: %s\n\n" % (event_type, payload)).encode("utf-8")


def append_log(line: str, path: str = LOG_PATH) -> None:
    with _LOG_LOCK:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line.rstrip() + "\n")


def append_usage(row: Dict[str, Any], path: str = USAGE_PATH) -> None:
    with _LOG_LOCK:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")


def request_field_names(req: Dict[str, Any]) -> str:
    return ",".join(sorted(req.keys()))


# ── v2 canonical paid model-only request shape (closed) ───────────────────────

CANONICAL_RESPONSE_FIELDS = frozenset(("model", "input", "stream", "max_output_tokens"))
CANONICAL_INPUT_LIMIT = 1024 * 1024
CANONICAL_MAX_OUTPUT_TOKENS_LIMIT = 32768


def validate_canonical_model_request(req: Dict[str, Any], *, expected_model: str) -> None:
    """Validate the CLOSED canonical Responses shape or raise ValueError.

    Only {model, input, stream, max_output_tokens} is accepted: any extra key,
    nested input/items, tool/function/MCP/tool_choice/store/continuation
    surface, non-finite, malformed or oversize value is rejected before
    upstream.
    """
    if not isinstance(req, dict) or set(req) != CANONICAL_RESPONSE_FIELDS:
        raise ValueError("canonical request refused")
    if not isinstance(req["model"], str) or req["model"] != expected_model:
        raise ValueError("canonical request refused")
    value = req["input"]
    if not isinstance(value, str) or not value:
        raise ValueError("canonical request refused")
    try:
        encoded = value.encode("utf-8")
    except (UnicodeEncodeError, OverflowError):
        raise ValueError("canonical request refused") from None
    if not encoded or len(encoded) > CANONICAL_INPUT_LIMIT:
        raise ValueError("canonical request refused")
    if req["stream"] is not False or type(req["stream"]) is not bool:
        raise ValueError("canonical request refused")
    tokens = req["max_output_tokens"]
    if type(tokens) is not int or not 1 <= tokens <= CANONICAL_MAX_OUTPUT_TOKENS_LIMIT:
        raise ValueError("canonical request refused")


def require_canonical_chat_completion(value):
    # The generic translator historically labels responses completed. The paid
    # model-only surface must first observe the actual upstream finish reason.
    if (type(value) is not dict or value.get('error') is not None
            or type(value.get('choices')) is not list or len(value['choices']) != 1):
        raise ValueError('canonical completion refused')
    choice = value['choices'][0]
    if (type(choice) is not dict or choice.get('finish_reason') != 'stop'
            or type(choice.get('message')) is not dict):
        raise ValueError('canonical completion refused')
    message = choice['message']
    if (message.get('role') != 'assistant' or message.get('tool_calls')
            or message.get('function_call') or message.get('refusal')
            or type(message.get('content')) is not str or not message['content']):
        raise ValueError('canonical completion refused')


def canonical_request_to_chat(req: Dict[str, Any]) -> Dict[str, Any]:
    """Construct the CLOSED upstream chat body directly (no generic translator)."""
    return {
        "model": req["model"],
        "messages": [{"role": "user", "content": req["input"]}],
        "stream": False,
        "max_tokens": req["max_output_tokens"],
    }


class ShimContext:
    def __init__(
        self,
        api_key: str,
        openai_base_url: str,
        model: str,
        token: str,
        forward_reasoning: bool = False,
        log_path: str = LOG_PATH,
        usage_path: str = USAGE_PATH,
        upstream_post: Optional[Callable[..., Any]] = None,
        account_table: Optional[AccountTable] = None,
    ):
        self.api_key = api_key
        self.openai_base_url = openai_base_url.rstrip("/")
        self.model = model
        self.token = token
        self.forward_reasoning = forward_reasoning
        self.log_path = log_path
        self.usage_path = usage_path
        self.upstream_post = upstream_post
        self.account_table = account_table
        parsed = urlparse(self.openai_base_url)
        self.upstream_host = parsed.hostname or ""

    def secrets(self) -> List[str]:
        """All secret strings that must be redacted from log output.

        Includes every per-account key from ``account_table`` plus the
        legacy ``api_key`` and the bearer token used for shim auth.
        """
        keys: List[str] = []
        if self.account_table is not None:
            keys.extend(self.account_table.api_keys())
        if self.api_key:
            keys.append(self.api_key)
        if self.token:
            keys.append(self.token)
        return [s for s in keys if s]


def _count_tool_calls(output: List[Dict[str, Any]]) -> int:
    n = 0
    for item in output:
        if item.get("type") in ("function_call", "custom_tool_call"):
            n += 1
    return n


def post_upstream(
    ctx: ShimContext,
    chat: Dict[str, Any],
    timeout: int = 600,
    api_key: Optional[str] = None,
    client_user_agent: Optional[str] = None,
) -> Tuple[int, Dict[str, str], Any]:
    """POST chat completions. Returns (status, headers, body_or_fp).

    ``api_key`` overrides ``ctx.api_key`` for this single call (W4-G9
    multi-account: the failover helper picks a per-request key from the
    AccountTable). When ``ctx.upstream_post`` is set, the injectable
    callable is forwarded ``api_key`` as a kwarg so tests can observe
    the chosen account.
    """
    key = api_key if (api_key is not None and api_key) else ctx.api_key
    if ctx.upstream_post is not None:
        try:
            return ctx.upstream_post(chat, api_key=key, client_user_agent=client_user_agent)
        except TypeError:
            try:
                return ctx.upstream_post(chat, api_key=key)
            except TypeError:
                return ctx.upstream_post(chat)
    url = ctx.openai_base_url + "/chat/completions"
    data = json.dumps(chat, ensure_ascii=True).encode("utf-8")
    headers = {
        "Authorization": "Bearer %s" % key,
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if chat.get("stream") else "application/json",
    }
    if _client_user_agent_is_valid(client_user_agent):
        headers["User-Agent"] = client_user_agent
    req = Request(url, data=data, headers=headers, method="POST")
    resp = urlopen(req, timeout=timeout)
    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    return resp.status, hdrs, resp


# ── W4-G9 multi-account: AccountTable + selection + failover ───────────────────


_QUOTA_BODY_TOKENS = (
    "quota", "rate limit", "rate_limit", "ratelimit",
    "exhaust", "exceed", "insufficient", "credit",
)


def _is_quota_error_body(code: int, body_text: str) -> bool:
    """True if the upstream error indicates quota/limit exhaustion.

    HTTP 429 is always a quota signal; a 4xx with body text mentioning any
    of ``_QUOTA_BODY_TOKENS`` (case-insensitive) is treated the same way
    so the shim fails over to the next eligible account.
    """
    if code == 429:
        return True
    if not (400 <= code < 500) or not body_text:
        return False
    lower = body_text.lower()
    return any(token in lower for token in _QUOTA_BODY_TOKENS)


def _iso_to_epoch(value: Any) -> Optional[float]:
    """Parse an ISO-8601 timestamp or epoch into a UTC unix epoch.

    Mirrors ``quota_remote._iso`` semantics so the AccountTable can
    normalise ``nextResetTime`` strings returned by Z.ai.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(
            tzinfo=timezone.utc
        )
        return dt.astimezone(timezone.utc).timestamp()
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds <= 0:
            return None
        if seconds > 10_000_000_000:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).timestamp()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text or text.lower() in ("none", "null", "unknown"):
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


def _extract_next_reset(body_text: str) -> Optional[float]:
    """Best-effort extract of ``nextResetTime`` / ``reset_at`` from an
    upstream error body. Returns None when no parseable reset is found.
    """
    if not body_text:
        return None
    try:
        obj = json.loads(body_text)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    candidates: List[Any] = []
    data = obj.get("data") if isinstance(obj.get("data"), dict) else obj
    if isinstance(data, dict) and data.get("nextResetTime") is not None:
        candidates.append(data["nextResetTime"])
    err = obj.get("error")
    if isinstance(err, dict):
        for key in ("nextResetTime", "reset_at", "resetTime", "reset_time"):
            if err.get(key) is not None:
                candidates.append(err[key])
    for value in candidates:
        ts = _iso_to_epoch(value)
        if ts is not None and ts > 0:
            return ts
    return None


class AccountTable:
    """Per-account GLM state: live-quota reading + exhaustion tracking.

    Selection policy: choose the non-exhausted account with the LOWEST 5h
    percentage used (tie → lowest weekly percentage, then config order).

    Refresh policy: ``live_reader(name, key)`` is called at most once per
    ``REFRESH_INTERVAL_S`` per account. A failed read keeps the previous
    state and never marks an account exhausted. Refreshes happen inside
    the request path only when the existing reading is older than the
    interval — fresh readings short-circuit to selection.
    """

    REFRESH_INTERVAL_S = 300
    EXHAUST_FALLBACK_S = 300

    def __init__(
        self,
        accounts: Dict[str, Dict[str, str]],
        live_reader: Optional[Callable[[str, str], List[Any]]] = None,
        lock: Optional[threading.Lock] = None,
        now_fn: Optional[Callable[[], float]] = None,
    ):
        self._accounts: Dict[str, Dict[str, str]] = {
            name: dict(info) for name, info in (accounts or {}).items()
        }
        self._live_reader = live_reader or self._default_live_reader
        self._lock = lock or threading.Lock()
        self._now_fn = now_fn or time.time
        self._state: Dict[str, Dict[str, Any]] = {
            name: {
                "exhausted_until_ts": 0.0,
                "last_pct_5h": None,
                "last_pct_week": None,
                "observed_at": None,
                "next_reset_5h": None,
            }
            for name in self._accounts
        }
        self._last_refresh: Dict[str, float] = {
            name: 0.0 for name in self._accounts
        }

    @staticmethod
    def _default_live_reader(name: str, key: str) -> List[Any]:
        """Fallback live reader: defer to ``quota_remote._live_glm``."""
        try:
            import quota_remote  # noqa: WPS433 — late import on purpose
            return quota_remote._live_glm(name, key)
        except Exception:
            return []

    def names(self) -> List[str]:
        return list(self._accounts.keys())

    def get(self, name: str) -> Optional[Dict[str, str]]:
        info = self._accounts.get(name)
        return dict(info) if info is not None else None

    def api_keys(self) -> List[str]:
        return [
            info.get("api_key", "")
            for info in self._accounts.values()
            if isinstance(info, dict) and info.get("api_key")
        ]

    def state(self, name: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state.get(name, {}))

    def snapshot(self) -> List[Dict[str, Any]]:
        """Public ``/health`` view: names + numbers, never any secret."""
        out: List[Dict[str, Any]] = []
        with self._lock:
            for name in self._accounts:
                s = self._state[name]
                out.append({
                    "name": name,
                    "exhausted_until": s["exhausted_until_ts"],
                    "pct_5h": s["last_pct_5h"],
                    "pct_week": s["last_pct_week"],
                    "observed_at": s["observed_at"],
                })
        return out

    def refresh(self, name: str, now_ts: Optional[float] = None,
                force: bool = False) -> None:
        """Refresh one account's reading, throttled to 1/REFRESH_INTERVAL_S.

        On any exception, the previous state is preserved and the account
        is never marked exhausted (the shim treats stale +0pct as the
        best-effort fallback).
        """
        if name not in self._accounts:
            return
        now = float(now_ts) if now_ts is not None else float(self._now_fn())
        with self._lock:
            if (not force
                    and now - self._last_refresh.get(name, 0.0)
                    < self.REFRESH_INTERVAL_S):
                return
            self._last_refresh[name] = now
        try:
            api_key = self._accounts[name].get("api_key", "")
            states = self._live_reader(name, api_key) or []
        except Exception:
            return
        pct_5h: Optional[float] = None
        pct_week: Optional[float] = None
        reset_5h_epoch: Optional[float] = None
        observed_at: Any = None
        for st in states:
            window = getattr(st, "window", None)
            used = getattr(st, "used", None)
            if window == "5h":
                pct_5h = used
                reset_5h_epoch = _iso_to_epoch(getattr(st, "reset_at", None))
                if observed_at is None:
                    observed_at = getattr(st, "observed_at", None)
            elif window == "weekly":
                pct_week = used
                if observed_at is None:
                    observed_at = getattr(st, "observed_at", None)
        with self._lock:
            cur = self._state[name]
            if pct_5h is not None:
                cur["last_pct_5h"] = float(pct_5h)
            if pct_week is not None:
                cur["last_pct_week"] = float(pct_week)
            if observed_at is not None:
                cur["observed_at"] = observed_at
            if reset_5h_epoch is not None:
                cur["next_reset_5h"] = reset_5h_epoch

    def _observe_age(self, observed_at: Any, now: float) -> Optional[float]:
        if not observed_at:
            return None
        ts = _iso_to_epoch(observed_at)
        if ts is None:
            return None
        return max(0.0, now - ts)

    def select(self, now_ts: Optional[float] = None) -> Optional[str]:
        """Pick the non-exhausted account with the lowest 5h pct."""
        now = float(now_ts) if now_ts is not None else float(self._now_fn())
        # Refresh stale readings — never inside the request path when a
        # reading younger than REFRESH_INTERVAL_S exists.
        for name in self._accounts:
            with self._lock:
                obs_at = self._state[name].get("observed_at")
                last_ref = self._last_refresh.get(name, 0.0)
            age = self._observe_age(obs_at, now)
            if age is None or age >= self.REFRESH_INTERVAL_S:
                if now - last_ref >= self.REFRESH_INTERVAL_S:
                    self.refresh(name, now_ts=now)
        candidates: List[Tuple[float, float, int, str]] = []
        with self._lock:
            for idx, name in enumerate(self._accounts):
                s = self._state[name]
                if s["exhausted_until_ts"] > now:
                    continue
                pct_5h = s["last_pct_5h"]
                if pct_5h is None:
                    pct_5h = 0.0
                pct_week = s["last_pct_week"]
                if pct_week is None:
                    pct_week = 0.0
                candidates.append((float(pct_5h), float(pct_week), idx, name))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (x[0], x[1], x[2]))
        return candidates[0][3]

    def mark_exhausted(self, name: str, until_ts: float) -> None:
        """Mark ``name`` exhausted until ``until_ts`` (unix epoch seconds)."""
        if name not in self._accounts:
            return
        with self._lock:
            self._state[name]["exhausted_until_ts"] = float(until_ts)


def _execute_chat(
    ctx: ShimContext,
    chat: Dict[str, Any],
    account_table: Optional[AccountTable],
    client_user_agent: Optional[str] = None,
    bound_account: Optional[str] = None,
    retry_allowed: bool = True,
) -> Tuple[int, Dict[str, str], Any, Optional[str]]:
    """Execute ``chat`` with optional exact account binding.

    Controller traffic retains the existing one-retry multi-account behavior.
    Lease-capability workers pass ``bound_account`` and ``retry_allowed=False``:
    the request uses exactly the broker-assigned account and never spills into a
    second account behind the broker's back.
    """
    if account_table is None:
        if bound_account is not None:
            raise HTTPError(
                url=ctx.openai_base_url, code=503, msg="glm-shim-account-table-unavailable",
                hdrs=None, fp=io.BytesIO(b"bound account unavailable"),
            )
        status, hdrs, body = post_upstream(ctx, chat, client_user_agent=client_user_agent)
        return status, hdrs, body, None

    if bound_account is not None and account_table.get(bound_account) is None:
        raise HTTPError(
            url=ctx.openai_base_url, code=401, msg="glm-shim-bound-account-invalid",
            hdrs=None, fp=io.BytesIO(b"bound account invalid"),
        )

    tried: Set[str] = set()
    last_code: Optional[int] = None
    last_body_text: str = ""
    attempts = 1 if bound_account is not None or not retry_allowed else 2
    for _ in range(attempts):
        name = bound_account if bound_account is not None else account_table.select()
        if name is None or name in tried:
            break
        tried.add(name)
        info = account_table.get(name) or {}
        api_key = info.get("api_key", "")
        try:
            status, hdrs, body = post_upstream(
                ctx, chat, api_key=api_key, client_user_agent=client_user_agent
            )
            return status, hdrs, body, name
        except HTTPError as exc:
            code = int(exc.code or 0)
            body_text = ""
            try:
                body_text = exc.read().decode("utf-8", "replace")
            except Exception:
                try:
                    body_text = str(exc.reason or exc)
                except Exception:
                    body_text = ""
            if _is_quota_error_body(code, body_text):
                reset_ts = _extract_next_reset(body_text)
                if reset_ts is None or reset_ts <= time.time():
                    reset_ts = time.time() + account_table.EXHAUST_FALLBACK_S
                account_table.mark_exhausted(name, reset_ts)
                last_code = code
                last_body_text = body_text
                if bound_account is not None or not retry_allowed:
                    break
                continue
            raise
    if last_code is not None:
        raise HTTPError(
            url=ctx.openai_base_url,
            code=last_code,
            msg="glm-shim-bound-account" if bound_account is not None else "glm-shim-failover",
            hdrs=None,
            fp=io.BytesIO(last_body_text.encode("utf-8")),
        )
    raise HTTPError(
        url=ctx.openai_base_url, code=502, msg="glm-shim-no-account",
        hdrs=None,
        fp=io.BytesIO(b"no eligible glm account"),
    )


def make_handler(ctx: ShimContext, lease_gateway: Any = None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            try:
                sys.stderr.write("%s %s\n" % (self.command, fmt % args))
            except Exception:
                pass

        def _send_json(
            self,
            status: int,
            obj: Dict[str, Any],
            extra_headers: Optional[Dict[str, str]] = None,
        ) -> None:
            raw = json.dumps(obj, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(raw)

        def _one(self, name: str) -> str:
            values = self.headers.get_all(name) or []
            if len(values) != 1 or not isinstance(values[0], str) or not values[0]:
                raise ValueError("header refused")
            if len(values[0]) > 4096 or "\r" in values[0] or "\n" in values[0]:
                raise ValueError("header refused")
            return values[0]

        def _controller_authorized(self) -> bool:
            try:
                return check_auth(self._one("Authorization"), ctx.token)
            except ValueError:
                return False

        def _read_object(self, limit: int = 1024 * 1024) -> Tuple[bytes, Dict[str, Any]]:
            if self.headers.get_all("Transfer-Encoding"):
                raise ValueError("unsupported framing")
            try:
                length_raw = self._one("Content-Length")
            except ValueError:
                length_raw = "0"
            if not re.fullmatch(r"[0-9]{1,8}", length_raw):
                raise ValueError("invalid length")
            length = int(length_raw)
            if length < 0 or length > limit:
                raise ValueError("invalid length")
            raw = self.rfile.read(length) if length else b"{}"
            if len(raw) != length:
                raise ValueError("incomplete body")
            def pairs(items):
                result: Dict[str, Any] = {}
                for key, value in items:
                    if key in result:
                        raise ValueError("duplicate key")
                    result[key] = value
                return result
            def constant(_value):
                raise ValueError("nonfinite number")
            payload = json.loads(
                raw.decode("utf-8") or "{}",
                object_pairs_hook=pairs,
                parse_constant=constant,
            )
            if not isinstance(payload, dict):
                raise ValueError("object required")
            return raw, payload

        def _worker_claims(self, model: str) -> Optional[Dict[str, Any]]:
            try:
                if lease_gateway is None:
                    raise ValueError("worker capability unavailable")
                authorization = self._one("Authorization")
                header_model = self._one("X-MM-Worker-Model")
                if header_model != model:
                    raise ValueError("model mismatch")
                if authorization.startswith("Bearer v2."):
                    claims = lease_gateway.authorize_canonical(
                        authorization[7:],
                        model=model,
                        run_id=self._one("X-MM-Run-Id"),
                        host=self._one("X-MM-Host"),
                    )
                elif authorization.startswith("Bearer v1."):
                    claims = lease_gateway.authorize(
                        authorization[7:],
                        model=model,
                        run_id=self._one("X-MM-Run-Id"),
                        host=self._one("X-MM-Host"),
                    )
                else:
                    raise ValueError("worker capability required")
                if ctx.account_table is None or ctx.account_table.get(claims["account"]) is None:
                    raise ValueError("account unavailable")
                return claims
            except Exception:
                self._send_json(
                    401,
                    {"error": {"message": "worker capability refused", "type": "worker_capability_refused"}},
                )
                return None

        def _named_client_ok(self) -> bool:
            if not named_client_enforced():
                return True
            if named_client_allowed(self.headers.get("User-Agent")):
                return True
            append_log(
                redact_secrets(
                    "client_not_named user_agent=%s" % (self.headers.get("User-Agent") or "-"),
                    ctx.secrets(),
                ),
                ctx.log_path,
            )
            self._send_json(
                403,
                {"error": {"message": "client not named", "type": "client_not_named"}},
            )
            return False

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/health":
                payload: Dict[str, Any] = {
                    "ok": True,
                    "upstream": ctx.upstream_host,
                    "worker_capabilities": (
                        "lease-v1"
                        if lease_gateway is not None and lease_gateway.broker_ready()
                        else None
                    ),
                }
                if ctx.account_table is not None:
                    payload["accounts"] = ctx.account_table.snapshot()
                # Worker readiness is live state, not a cacheable startup claim.
                self._send_json(200, payload, {"Cache-Control": "no-store"})
                return
            if path == "/worker-health":
                try:
                    model = self._one("X-MM-Worker-Model")
                except ValueError:
                    self._send_json(
                        401,
                        {"error": {"message": "worker capability refused", "type": "worker_capability_refused"}},
                    )
                    return
                claims = self._worker_claims(model)
                if claims is not None:
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "worker_capabilities": "lease-v1",
                            "lease_id": claims["lease_id"],
                            "run_id": claims["run_id"],
                            "model": claims["model"],
                            "host": claims["host"],
                            "account": claims["account"],
                            "root": claims["root"],
                            "expires_at": claims["expires_at"],
                        },
                        {"Cache-Control": "no-store"},
                    )
                return
            self._send_json(404, {"error": {"message": "not found", "type": "not_found"}})

        def do_POST(self):
            path = self.path.split("?", 1)[0]

            if path == "/worker-capabilities":
                if not self._controller_authorized() or lease_gateway is None:
                    self._send_json(
                        401,
                        {"error": {"message": "unauthorized", "type": "auth_error"}},
                    )
                    return
                try:
                    _raw, payload = self._read_object(16384)
                    issued = lease_gateway.issue(payload)
                except Exception:
                    self._send_json(
                        400,
                        {"error": {"message": "capability request refused", "type": "invalid_control_request"}},
                    )
                    return
                self._send_json(200, issued, {"Cache-Control": "no-store"})
                return

            if path != "/v1/responses":
                self._send_json(404, {"error": {"message": "not found", "type": "not_found"}})
                return

            try:
                _raw, req = self._read_object()
            except Exception:
                self._send_json(400, {"error": {"message": "invalid json", "type": "invalid_request"}})
                return

            model = req.get("model") or ctx.model
            if not isinstance(model, str) or not model:
                self._send_json(400, {"error": {"message": "model required", "type": "invalid_request"}})
                return

            claims = None
            if self._controller_authorized():
                bound_account = None
                retry_allowed = True
                claims = None
            else:
                claims = self._worker_claims(model)
                if claims is None:
                    return
                bound_account = claims["account"]
                retry_allowed = False

            if claims is not None and claims.get('v') == 2:
                if self.headers.get('User-Agent') != 'mastermind-canonical-paid-model/1':
                    self._send_json(400, {'error': {'type': 'canonical_request_refused',
                                                 'message': 'canonical request refused'}})
                    return
            elif not self._named_client_ok():
                return
            self._handle_responses(
                req,
                raw_body=_raw,
                worker_claims=claims,
                bound_account=bound_account,
                retry_allowed=retry_allowed,
            )

        def _canonical_preflight(self, req, raw_body, claims) -> bool:
            """Verify exact raw canonical body digest + closed shape pre-upstream."""
            try:
                if not isinstance(raw_body, bytes) or not raw_body:
                    raise ValueError("canonical body required")
                digest = hashlib.sha256(raw_body).hexdigest()
                if not hmac.compare_digest(digest, claims["request_body_sha256"]):
                    raise ValueError("canonical body digest mismatch")
                validate_canonical_model_request(req, expected_model=claims["model"])
            except Exception:
                self._send_json(
                    400,
                    {"error": {"message": "canonical request refused", "type": "canonical_request_refused"}},
                )
                return False
            return True

        def _handle_responses(
            self,
            req: Dict[str, Any],
            *,
            raw_body: Optional[bytes] = None,
            worker_claims: Optional[Dict[str, Any]] = None,
            bound_account: Optional[str] = None,
            retry_allowed: bool = True,
        ) -> None:
            t0 = time.time()
            req_id = new_id("req")
            model = req.get("model") or ctx.model
            fields = request_field_names(req)
            if worker_claims is not None and worker_claims.get("v") == 2:
                # Closed canonical paid scope: exact raw body digest against the
                # signed capsule, closed shape validation, then the closed
                # upstream constructor — never the generic translator surface.
                if not self._canonical_preflight(req, raw_body, worker_claims):
                    return
                chat, custom_names = canonical_request_to_chat(req), set()
                try:
                    lease_gateway._consume_canonical_provider_intent(worker_claims)
                except Exception:
                    self._send_json(409, {'error': {'type': 'canonical_operation_unavailable',
                                                 'message': 'original operation unavailable'}})
                    return
            else:
                chat, custom_names = responses_request_to_chat(req)
                if not chat.get("model"):
                    chat["model"] = model
            stream = bool(req.get("stream") or chat.get("stream"))
            upstream_status = 0
            usage = usage_from_openai({})
            tool_calls = 0
            account_name: Optional[str] = None
            try:
                status, _hdrs, body, account_name = _execute_chat(
                    ctx,
                    chat,
                    ctx.account_table,
                    self.headers.get("User-Agent"),
                    bound_account=bound_account,
                    retry_allowed=retry_allowed,
                )
                upstream_status = int(status or 0)
                if stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    em = StreamEmitter(model, custom_names, ctx.forward_reasoning)
                    em.start()
                    for typ, data in em.events:
                        self.wfile.write(format_sse(typ, data))
                    em.events.clear()
                    for chunk in iter_sse_chunks(body):
                        em.on_chunk(chunk)
                        for typ, data in em.events:
                            self.wfile.write(format_sse(typ, data))
                        em.events.clear()
                    em.completed()
                    for typ, data in em.events:
                        self.wfile.write(format_sse(typ, data))
                    self.wfile.flush()
                    try:
                        body.close()
                    except Exception:
                        pass
                    usage = em.usage
                    tool_calls = _count_tool_calls(em.output)
                else:
                    raw_body = body.read() if hasattr(body, "read") else body
                    try:
                        body.close()
                    except Exception:
                        pass
                    if isinstance(raw_body, bytes):
                        decoded = raw_body.decode("utf-8", "replace")
                    else:
                        decoded = str(raw_body)
                    chat_obj = json.loads(decoded) if decoded else {}
                    if worker_claims is not None and worker_claims.get('v') == 2:
                        require_canonical_chat_completion(chat_obj)
                    resp_obj = chat_response_to_responses(chat_obj, custom_names, model)
                    usage = resp_obj["usage"]
                    tool_calls = _count_tool_calls(resp_obj.get("output") or [])
                    self._send_json(200, resp_obj)
            except HTTPError as exc:
                upstream_status = int(exc.code or 0)
                err_text = ""
                try:
                    err_text = exc.read().decode("utf-8", "replace")
                except Exception:
                    err_text = str(exc.reason or exc)
                err_text = redact_secrets(err_text, ctx.secrets())
                self._send_json(
                    upstream_status or 502,
                    {"error": {"message": err_text, "type": "upstream_error"}},
                )
            except (URLError, TimeoutError, ConnectionError, OSError) as exc:
                upstream_status = 502
                msg = redact_secrets(str(exc), ctx.secrets())
                self._send_json(502, {"error": {"message": msg, "type": "upstream_error"}})
            except Exception as exc:
                upstream_status = 500
                msg = redact_secrets("%s" % exc, ctx.secrets())
                self._send_json(500, {"error": {"message": msg, "type": "shim_error"}})
            latency_ms = int((time.time() - t0) * 1000)
            in_roles = []
            if isinstance(req.get("input"), list):
                for it in req["input"]:
                    if isinstance(it, dict):
                        in_roles.append("%s:%s" % (_item_type(it) or "?", it.get("role") or "-"))
            elif isinstance(req.get("input"), str):
                in_roles.append("string:user")
            out_roles = [m.get("role") or "-" for m in (chat.get("messages") or [])]
            append_log(
                "%s id=%s model=%s upstream=%s latency_ms=%s in=%s cached=%s out=%s tool_calls=%s fields=%s in_items=%s out_roles=%s account=%s"
                % (
                    utc_ts(),
                    req_id,
                    model,
                    upstream_status,
                    latency_ms,
                    usage.get("input_tokens", 0),
                    (usage.get("input_tokens_details") or {}).get("cached_tokens", 0),
                    usage.get("output_tokens", 0),
                    tool_calls,
                    fields,
                    ",".join(in_roles) or "-",
                    ",".join(out_roles) or "-",
                    account_name or "chairman-max",
                ),
                ctx.log_path,
            )
            append_usage(
                {
                    "ts": utc_ts(),
                    "model": model,
                    "input_tokens": usage.get("input_tokens", 0),
                    "cached_tokens": (usage.get("input_tokens_details") or {}).get("cached_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "account": account_name or "chairman-max",
                },
                ctx.usage_path,
            )

    return Handler


def acquire_singleton_lock(path: str = LOCK_PATH):
    global _FILE_LOCK_FD
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise SystemExit("glm_shim: already running")
    _FILE_LOCK_FD = fd
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode("utf-8"))
    return fd


def write_pid(path: str = PID_PATH) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, b"%d\n" % os.getpid())
    finally:
        os.close(fd)


def serve(
    ctx: ShimContext,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    lease_gateway: Any = None,
) -> ThreadingHTTPServer:
    handler = make_handler(ctx, lease_gateway=lease_gateway)
    canonical_owner = getattr(lease_gateway, '_canonical_owner', None)
    server_class = ThreadingHTTPServer
    if canonical_owner is not None:
        canonical_owner.require_gateway(lease_gateway)
        class CanonicalPaidHTTPServer(ThreadingHTTPServer):
            # Count real accepted request lifetimes, including manual legacy
            # traffic. The ordinary shim without this owner is unchanged.
            def process_request(self, request, client_address):
                if not canonical_owner.enter_http_request():
                    self.shutdown_request(request)
                    return
                try:super().process_request(request,client_address)
                except BaseException:
                    canonical_owner.leave_http_request()
                    raise
            def process_request_thread(self, request, client_address):
                try:super().process_request_thread(request,client_address)
                finally:canonical_owner.leave_http_request()
        server_class = CanonicalPaidHTTPServer
    httpd = server_class((host, port), handler)
    return httpd


_CANONICAL_INCUMBENT_LOADED = object()


class _CanonicalIncumbent:
    __slots__ = ('context','gateway','pid','lock_fd','lock_identity','_origin')
    def __init__(self,context,gateway,origin):
        self.context,self.gateway=context,gateway
        self.pid=os.getpid()
        self.lock_fd=_FILE_LOCK_FD
        self.lock_identity=os.fstat(_FILE_LOCK_FD)
        self._origin=origin


def require_canonical_incumbent(value):
    if (type(value) is not _CanonicalIncumbent
            or value._origin is not _CANONICAL_INCUMBENT_LOADED
            or value.pid!=os.getpid() or value.lock_fd!=_FILE_LOCK_FD
            or value.lock_identity!=os.fstat(value.lock_fd)):
        raise ValueError('canonical incumbent context unavailable')
    return value.context,value.gateway


def build_canonical_incumbent_context(owner_ext):
    """Private root-profile constructor on the SAME incumbent shim owner.

    Call only after root release/config and adopted Unix FD qualification.
    Existing state/credentials stay in their original namespace; no default
    path derived from this overlay file and no token/key creation fallback.
    """
    fixed = '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
    if owner_ext != fixed:
        raise ValueError('canonical incumbent owner unavailable')
    state = os.path.join(fixed, 'glm_shim')
    token_path = os.path.join(state, '.token')
    fd = os.open(token_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        import stat
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                or not 1 <= before.st_size <= 4096):
            raise ValueError('canonical incumbent owner unavailable')
        raw = os.read(fd, 4097)
        after = os.fstat(fd)
        visible = os.lstat(token_path)
        identity=lambda i:(i.st_dev,i.st_ino,i.st_uid,i.st_gid,i.st_mode,i.st_nlink,
            i.st_size,i.st_mtime_ns,i.st_ctime_ns)
        if (identity(before)!=identity(after) or identity(before)!=identity(visible)
                or len(raw)!=before.st_size):
            raise ValueError('canonical incumbent owner unavailable')
        token = raw.decode('ascii').strip()
        if not token:
            raise ValueError('canonical incumbent owner unavailable')
    finally:
        os.close(fd)
    # This is the SAME singleton lock and provisioned account table; no second
    # shim/controller, alternate credential store or public canonical issuer.
    acquire_singleton_lock(os.path.join(state,'shim.lock'))
    cfg = load_config()
    import glm_keys
    accounts = glm_keys.accounts()
    if not accounts:
        raise ValueError('canonical incumbent owner unavailable')
    table = AccountTable(accounts=accounts)
    ctx = ShimContext(api_key=cfg['api_key'],openai_base_url=cfg['openai_base_url'],
        model=cfg['model'],token=token,forward_reasoning=cfg['forward_reasoning'],
        account_table=table,log_path=os.path.join(state,'shim.log'),
        usage_path=os.path.join(state,'usage.jsonl'))
    from glm_lease_gateway import GlmLeaseGateway
    gateway = GlmLeaseGateway(os.path.join(fixed,'broker/leases.sqlite'),
        set(table.names()),{'glm-5.3','glm-5.3-flash'})
    return _CanonicalIncumbent(ctx,gateway,_CANONICAL_INCUMBENT_LOADED)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    acquire_singleton_lock()
    cfg = load_config()
    token = ensure_token()
    # W4-G9 / RV-G9 B1: build the multi-account table from ~/.glm/config.json
    # (account NAMES only are ever written to stderr; keys stay inside the table).
    try:
        import glm_keys  # noqa: WPS433 — ext/ was put on sys.path above
        _accounts = glm_keys.accounts()
    except Exception as exc:  # pragma: no cover — degrade to single-key mode
        sys.stderr.write("glm_shim accounts loader failed (%s); single-key mode\n" % type(exc).__name__)
        _accounts = {}
    table = AccountTable(accounts=_accounts) if _accounts else None
    sys.stderr.write("glm_shim accounts=%s\n" % (",".join(_accounts) if _accounts else "(legacy single key)"))
    ctx = ShimContext(
        api_key=cfg["api_key"],
        openai_base_url=cfg["openai_base_url"],
        model=cfg["model"],
        token=token,
        forward_reasoning=cfg["forward_reasoning"],
        account_table=table,
    )
    gateway = None
    if os.environ.get("GLM_WORKER_CAPABILITIES") == "1":
        try:
            if table is None:
                raise RuntimeError("glm accounts unavailable")
            import pick  # noqa: WPS433 — ext/ is canonical routing owner
            from glm_lease_gateway import GlmLeaseGateway
            spec = (pick.load_pools().get("pools") or {}).get("glm") or {}
            models = {
                str(value)
                for value in (spec.get("models") or {}).values()
                if isinstance(value, str) and value
            }
            if not models:
                raise RuntimeError("glm model registry unavailable")
            gateway = GlmLeaseGateway(
                os.path.join(_EXT_DIR, "broker", "leases.sqlite"),
                set(table.names()),
                models,
            )
        except Exception as exc:
            sys.stderr.write(
                "glm_shim worker capability startup refused (%s)\n"
                % type(exc).__name__
            )
            return 78

    port = int(os.environ.get("GLM_SHIM_PORT") or cfg["shim_port"] or DEFAULT_PORT)
    write_pid()
    httpd = serve(ctx, "127.0.0.1", port, lease_gateway=gateway)

    def _stop(signum, _frame):
        # The signal handler executes on the main thread, which also runs
        # serve_forever(). Calling httpd.shutdown() here deadlocks because
        # BaseServer.shutdown() waits for that same loop to exit.
        # Unwind instead; the finally block closes the socket and removes
        # our exact PID file after in-flight request threads finish.
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    sys.stderr.write("glm_shim listening 127.0.0.1:%s upstream=%s\n" % (port, ctx.upstream_host))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass
        try:
            if os.path.isfile(PID_PATH):
                with open(PID_PATH, encoding="utf-8") as fh:
                    if fh.read().strip() == str(os.getpid()):
                        os.remove(PID_PATH)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)
