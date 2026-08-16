"""In-process Codex App Server double for OHF-P0 laboratory tests.

Speaks the documented JSON-RPC stdio dialect closely enough that the same
commission code path can measure lifecycle, fork, skills, MCP, and recovery
without a live Codex binary or provider account.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import uuid
from pathlib import Path
from typing import Any

from scripts.ohf.fixtures import (
    OHF_PROBE_MCP_SERVER,
    OHF_PROBE_MCP_TOOL,
    OHF_PROBE_SKILL_ACK,
    OHF_PROBE_SKILL_NAME,
    OHF_PROBE_TURN_ACK,
)
from scripts.ohf.redaction import redact_text

SECRET_FIXTURE = "sk-ohf-probe-fixture-" + ("A" * 24)


class FakeAppServer:
    def __init__(self) -> None:
        self.state_path = Path(os.environ.get("OHF_FAKE_STATE") or "ohf_fake_state.json")
        self.workspace = Path(os.environ.get("OHF_FAKE_WORKSPACE") or ".")
        self.skill_root = Path(os.environ.get("OHF_FAKE_SKILL_ROOT") or self.workspace)
        self.model = os.environ.get("OHF_FAKE_MODEL") or "gpt-5.6-sol"
        self.include_mcp = os.environ.get("OHF_FAKE_MCP_GONE") != "1"
        self.leak = os.environ.get("OHF_FAKE_LEAK") == "1"
        self.die_after = int(os.environ.get("OHF_FAKE_DIE_AFTER") or "0")
        self.requests_seen = 0
        self.initialized = False
        self.threads: dict[str, dict[str, Any]] = {}
        self.mcp_status = "ready" if self.include_mcp else "missing"
        self._load()
        signal.signal(signal.SIGTERM, self._on_term)

    def _on_term(self, *_args: object) -> None:
        self._save()
        raise SystemExit(0)

    def _load(self) -> None:
        if self.state_path.is_file():
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.threads = payload.get("threads") or {}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"threads": self.threads}, indent=2),
            encoding="utf-8",
        )

    def _write(self, payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"method": method, "params": params})

    def _error(self, request_id: Any, message: str, code: int = -32000) -> None:
        if self.leak:
            message = f"{message} token={SECRET_FIXTURE}"
        self._write({"id": request_id, "error": {"code": code, "message": redact_text(message) if not self.leak else message}})

    def _ok(self, request_id: Any, result: dict[str, Any]) -> None:
        self._write({"id": request_id, "result": result})

    def _thread_view(self, thread: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": thread["id"],
            "sessionId": thread.get("session_id") or thread["id"],
            "forkedFromId": thread.get("forked_from"),
            "status": "ready",
            "model": thread.get("model") or self.model,
            "turns": list(thread.get("turns") or []),
        }

    def _require_thread(self, thread_id: str) -> dict[str, Any] | None:
        return self.threads.get(thread_id)

    def handle(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}
        if request_id is not None:
            self.requests_seen += 1
            if self.die_after and self.requests_seen >= self.die_after:
                self._save()
                raise SystemExit(9)
        if method == "initialize":
            self.initialized = True
            if self.leak:
                sys.stderr.write(f"auth fixture {SECRET_FIXTURE}\n")
                sys.stderr.flush()
            self._ok(
                request_id,
                {
                    "userAgent": "ohf-fake-app-server/p0",
                    "codexHome": str(self.state_path.parent),
                    "platformFamily": "unix",
                    "platformOs": sys.platform,
                },
            )
            return
        if method == "initialized":
            return
        if not self.initialized:
            self._error(request_id, "Not initialized")
            return
        if method == "thread/start":
            thread_id = f"thr_{uuid.uuid4().hex[:10]}"
            thread = {
                "id": thread_id,
                "session_id": thread_id,
                "model": params.get("model") or self.model,
                "cwd": params.get("cwd") or str(self.workspace),
                "turns": [],
            }
            self.threads[thread_id] = thread
            self._save()
            view = self._thread_view(thread)
            self._ok(request_id, {"thread": view, "instructionSources": []})
            self._notify("thread/started", {"thread": view})
            return
        if method == "thread/resume":
            thread_id = str(params.get("threadId") or "")
            thread = self._require_thread(thread_id)
            if thread is None:
                self._error(request_id, f"native session reference missing: {thread_id}", code=-32004)
                return
            if not Path(thread.get("cwd") or self.workspace).exists():
                self._error(request_id, "workspace missing", code=-32005)
                return
            view = self._thread_view(thread)
            self._ok(request_id, {"thread": view, "instructionSources": []})
            self._notify("thread/started", {"thread": view})
            return
        if method == "thread/fork":
            parent_id = str(params.get("threadId") or "")
            parent = self._require_thread(parent_id)
            if parent is None:
                self._error(request_id, f"native session reference missing: {parent_id}", code=-32004)
                return
            child_id = f"thr_{uuid.uuid4().hex[:10]}"
            child = {
                "id": child_id,
                "session_id": child_id,
                "forked_from": parent_id,
                "model": parent.get("model") or self.model,
                "cwd": parent.get("cwd"),
                "turns": list(parent.get("turns") or []),
            }
            self.threads[child_id] = child
            self._save()
            view = self._thread_view(child)
            self._ok(request_id, {"thread": view, "instructionSources": []})
            self._notify("thread/started", {"thread": view})
            return
        if method == "thread/read":
            thread = self._require_thread(str(params.get("threadId") or ""))
            if thread is None:
                self._error(request_id, "native session reference missing", code=-32004)
                return
            self._ok(request_id, {"thread": self._thread_view(thread)})
            return
        if method == "turn/start":
            thread_id = str(params.get("threadId") or "")
            thread = self._require_thread(thread_id)
            if thread is None:
                self._error(request_id, "native session reference missing", code=-32004)
                return
            if not Path(thread.get("cwd") or self.workspace).exists():
                self._error(request_id, "workspace missing", code=-32005)
                return
            turn_id = f"turn_{uuid.uuid4().hex[:8]}"
            text_in = ""
            for item in params.get("input") or []:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_in += str(item.get("text") or "")
            if OHF_PROBE_SKILL_NAME in text_in or "$ohf-probe" in text_in:
                reply = OHF_PROBE_SKILL_ACK
                item_type = "skill"
            else:
                reply = OHF_PROBE_TURN_ACK
                item_type = "agent_message"
            thread.setdefault("turns", []).append({"id": turn_id, "text": reply})
            self._save()
            turn = {"id": turn_id, "status": "completed", "threadId": thread_id}
            self._ok(request_id, {"turn": turn})
            self._notify("turn/started", {"turn": {"id": turn_id}})
            self._notify(
                "item/completed",
                {
                    "item": {
                        "type": item_type,
                        "text": reply,
                        "id": f"item_{turn_id}",
                    }
                },
            )
            self._notify(
                "turn/completed",
                {
                    "turn": {
                        **turn,
                        "usage": {"input_tokens": 4, "output_tokens": 2},
                    }
                },
            )
            self._notify(
                "thread/tokenUsage/updated",
                {"threadId": thread_id, "input_tokens": 4, "output_tokens": 2},
            )
            return
        if method == "skills/list":
            names = []
            if self.skill_root.exists():
                for skill_md in self.skill_root.glob("*/SKILL.md"):
                    names.append(skill_md.parent.name)
            extra = params.get("perCwdExtraUserRoots") or {}
            for roots in extra.values() if isinstance(extra, dict) else []:
                for root in roots:
                    for skill_md in Path(root).glob("*/SKILL.md"):
                        names.append(skill_md.parent.name)
            self._ok(
                request_id,
                {
                    "data": [
                        {"name": name, "path": str(self.skill_root / name)}
                        for name in sorted(set(names))
                    ]
                },
            )
            return
        if method == "skills/extraRoots/set":
            self._ok(request_id, {})
            return
        if method == "config/read":
            mcp = [OHF_PROBE_MCP_SERVER] if self.include_mcp else []
            self._ok(
                request_id,
                {
                    "config": {
                        "model": self.model,
                        "mcp_servers": {name: {"command": "python3"} for name in mcp},
                        "plugins": {},
                    }
                },
            )
            return
        if method == "mcpServerStatus/list":
            if not self.include_mcp:
                self._ok(request_id, {"data": []})
                return
            self._ok(
                request_id,
                {
                    "data": [
                        {
                            "name": OHF_PROBE_MCP_SERVER,
                            "status": self.mcp_status,
                            "tools": [{"name": OHF_PROBE_MCP_TOOL}],
                            "authStatus": "none",
                        }
                    ]
                },
            )
            return
        if method == "mcpServer/tool/call":
            if not self.include_mcp:
                self._error(request_id, "mcp server missing", code=-32006)
                return
            arguments = params.get("arguments") or {}
            text = str(arguments.get("text") or "")
            self._ok(
                request_id,
                {"content": [{"type": "text", "text": f"echo:{text}"}], "isError": False},
            )
            self._notify(
                "item/completed",
                {
                    "item": {
                        "type": "mcp_tool_call",
                        "tool": OHF_PROBE_MCP_TOOL,
                        "server": OHF_PROBE_MCP_SERVER,
                    }
                },
            )
            return
        if method == "config/mcpServer/reload":
            config_path = Path(os.environ.get("CODEX_HOME", "")) / "config.toml"
            if config_path.is_file():
                self.include_mcp = "[mcp_servers.ohf_probe]" in config_path.read_text(
                    encoding="utf-8"
                )
            elif os.environ.get("OHF_FAKE_MCP_GONE") == "1":
                self.include_mcp = False
            self._ok(request_id, {})
            return
        if method == "account/read":
            self._ok(request_id, {"authMode": "chatgpt", "planType": "plus"})
            return
        if method == "account/rateLimits/read":
            self._ok(
                request_id,
                {
                    "rateLimits": {
                        "limitId": "codex",
                        "primary": {
                            "usedPercent": 11,
                            "windowDurationMins": 15,
                            "resetsAt": 1730947200,
                        },
                    }
                },
            )
            return
        if method == "account/usage/read":
            self._ok(
                request_id,
                {"input_tokens": 4, "output_tokens": 2, "classification": "provider_reported"},
            )
            return
        if method == "model/list":
            self._ok(request_id, {"data": [{"id": self.model}]})
            return
        if method == "plugin/list":
            self._ok(request_id, {"data": []})
            return
        if request_id is not None:
            self._error(request_id, f"method not found: {method}", code=-32601)

    def serve(self) -> int:
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                if self.leak:
                    sys.stderr.write(f"parse error {SECRET_FIXTURE}\n")
                    sys.stderr.flush()
                continue
            if isinstance(message, dict):
                self.handle(message)
        self._save()
        return 0


def main() -> int:
    return FakeAppServer().serve()


if __name__ == "__main__":
    raise SystemExit(main())
