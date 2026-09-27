#!/usr/bin/env python3
"""One-process-generation Claude Agent SDK JSON-lines helper.

Run only by the Executive adapter.  It imports the SDK lazily after initialize,
never queries the model during initialize, and exports only closed sanitized
observations.  No env hook, no exec override, no child-process ownership hacks.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import json
import sys
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from control_plane.claude_operator_helper_protocol import (  # noqa: E402
    INTERFACE_VERSION,
    MAX_EVENTS,
    MAX_TEXT_CHARS,
    MAX_WIRE_BYTES,
    HelperProtocolError,
    bounded_text,
    decode_json_line,
    encode_json_line,
    parse_request,
)
from scripts.ohf.redaction import redact_evidence_text  # noqa: E402


# Allowed config keys; env / extra_args are deliberately rejected.
_CONFIG_KEYS = frozenset(
    {
        "cli_path",
        "cwd",
        "model",
        "session_id",
        "tools",
        "mcp_servers",
        "permission_mode",
        "max_turns",
        "resume",
        "setting_sources",
        "strict_mcp_config",
        "skills",
        "allowed_tools",
        "disallowed_tools",
        "sandbox",
        "settings",
    }
)

# Safe API key source tags reported by the SDK init SystemMessage.
_SAFE_API_KEY_SOURCES = frozenset({"none"})

# SDK factory: returns the real claude_agent_sdk module in production.
_SDK_FACTORY: Callable[[], Any] = lambda: importlib.import_module("claude_agent_sdk")


def _set_sdk_factory(factory: Callable[[], Any]) -> None:
    """Test hook only: replace the SDK module factory."""
    global _SDK_FACTORY
    _SDK_FACTORY = factory


def _bump_event(events: list, entry: dict) -> None:
    events.append(entry)
    if len(events) > MAX_EVENTS:
        del events[:-MAX_EVENTS]


def _bounded_list(value: Any, *, limit: int = 200) -> list:
    if (not isinstance(value, list) or len(value) > MAX_EVENTS or
            any(not isinstance(x, str) or not 1 <= len(x) <= limit for x in value)):
        raise HelperProtocolError("native capability inventory is malformed or unsupported")
    return list(value)


class HelperRuntime:
    """One-generation transient wrapper around ClaudeSDKClient."""

    def __init__(self, generation_id: str, config: Mapping[str, Any]) -> None:
        unknown = set(config) - _CONFIG_KEYS
        if unknown:
            raise HelperProtocolError("SDK config option is not allowlisted")
        self.generation_id = generation_id
        self.config = dict(config)
        self.client: Any = None
        self.session_id: Optional[str] = None
        self.active_turn_id: Optional[str] = None
        self.active_turn_payload: Optional[str] = None
        self.terminal = False
        self.acknowledged = False
        self.summary: Optional[str] = None
        self.events: list[dict[str, Any]] = []
        self._drain_task: Optional[asyncio.Task] = None
        self._stop_drain = asyncio.Event()
        self._init_data: dict[str, Any] = {}
        self._registration_kept: Optional[dict[str, Any]] = None
        self._sdk_version: Optional[str] = None
        self._cli_version: Optional[str] = None
        self._model_was_queried = False
        self._seen_turns: set[str] = set()
        self._failure: str | None = None
        self._success = False
        self._collected = False
        self._effective_policy: dict[str, Any] = {}
        self._event_sequence = 0
        self._native_result_id: str | None = None
        self._applied_launch_provenance: dict[str, Any] = {}
        self._drain_closed = True

    def _record_event(self, entry: dict[str, Any]) -> None:
        self._event_sequence += 1
        _bump_event(self.events, {**entry, "sequence": self._event_sequence,
                                  "turn_id": self.active_turn_id})

    async def initialize(self) -> Mapping[str, Any]:
        if self.client is not None:
            raise HelperProtocolError("generation is already initialized")
        sdk = _SDK_FACTORY()
        Client = getattr(sdk, "ClaudeSDKClient", None)
        Options = getattr(sdk, "ClaudeAgentOptions", None)
        SystemMessage = getattr(sdk, "SystemMessage", None)
        ResultMessage = getattr(sdk, "ResultMessage", None)
        if not all([Client, Options, SystemMessage, ResultMessage]):
            raise HelperProtocolError("SDK does not provide required exports")

        cli_path = self.config.get("cli_path")
        cwd = self.config.get("cwd")
        model = self.config.get("model")
        session_id = self.config.get("session_id")
        for name, value in (
            ("cli_path", cli_path),
            ("cwd", cwd),
            ("model", model),
            ("session_id", session_id),
        ):
            if not isinstance(value, str) or not value:
                raise HelperProtocolError(f"{name} is missing")
        try:
            uuid.UUID(session_id)
        except (TypeError, ValueError) as exc:
            raise HelperProtocolError("session_id is not a UUID") from exc
        if not Path(cli_path).is_absolute() or not Path(cwd).is_absolute():
            raise HelperProtocolError("native paths must be absolute")
        if self.config.get("setting_sources", []) != [] or self.config.get("strict_mcp_config", True) is not True:
            raise HelperProtocolError("ambient configuration discovery is refused")
        if self.config.get("resume") is not None:
            raise HelperProtocolError("resume requires a separate Executive recovery binding")

        options_kwargs: dict[str, Any] = dict(
            cli_path=cli_path,
            cwd=cwd,
            model=model,
            session_id=session_id,
            setting_sources=self.config.get("setting_sources", []),
            strict_mcp_config=self.config.get("strict_mcp_config", True),
            mcp_servers=self.config.get("mcp_servers", {}) or {},
            tools=self.config.get("tools"),
            permission_mode=self.config.get("permission_mode", "dontAsk"),
            max_turns=self.config.get("max_turns", 1),
            stderr=lambda _line: None,
            system_prompt={"type": "preset", "preset": "claude_code"},
        )
        if "skills" in self.config:
            options_kwargs["skills"] = self.config.get("skills")
            if self.config["skills"] == []:
                # SDK0.2.160 documents [] as empty but does not emit a CLI
                # switch for it. Use the documented native switch and verify
                # the actual init inventory; never assume [] took effect.
                options_kwargs["extra_args"] = {"disable-slash-commands": None}
        if "resume" in self.config:
            options_kwargs["resume"] = self.config.get("resume")
        if "allowed_tools" in self.config:
            options_kwargs["allowed_tools"] = self.config.get("allowed_tools")
        if "disallowed_tools" in self.config:
            options_kwargs["disallowed_tools"] = self.config.get("disallowed_tools")
        if "sandbox" in self.config:
            options_kwargs["sandbox"] = self.config.get("sandbox")
        if "settings" in self.config:
            options_kwargs["settings"] = json.dumps(self.config["settings"], allow_nan=False)

        try:
            self._applied_launch_provenance = {
                name: options_kwargs.get(name) for name in ("setting_sources", "strict_mcp_config", "skills")
            }
            self.client = Client(Options(**options_kwargs))
            await self.client.connect(prompt=None)
        except HelperProtocolError:
            raise
        except Exception as exc:
            await self._safe_disconnect()
            raise HelperProtocolError("native initialization failed") from exc

        try:
            server = await self.client.get_server_info()
            context = await self.client.get_context_usage()
            mcp = await self.client.get_mcp_status()
        except Exception as exc:
            await self._safe_disconnect()
            raise HelperProtocolError("native metadata fetch failed") from exc

        # The model menu contains aliases, not the exact serving IDs. Compare
        # native context and init observations instead of treating it as a catalog.
        if not isinstance(server, Mapping):
            await self._safe_disconnect()
            raise HelperProtocolError("server info is malformed")
        if not isinstance(context, Mapping) or context.get("model") != model:
            await self._safe_disconnect()
            raise HelperProtocolError("native context model does not match exact requested model")
        account = server.get("account")
        if not isinstance(account, Mapping) or account.get("apiProvider") != "firstParty":
            await self._safe_disconnect()
            raise HelperProtocolError("native subscription provider was not observed")

        # Send the non-model registration before any work query.
        async def registration() -> AsyncIterator[dict]:
            yield {
                "type": "user",
                "session_id": session_id,
                "parent_tool_use_id": None,
                "message": {
                    "role": "user",
                    "content": "Executive session registration; no model work.",
                },
                "shouldQuery": False,
            }

        try:
            await self.client.query(registration(), session_id=session_id)
        except Exception as exc:
            await self._safe_disconnect()
            raise HelperProtocolError("registration query failed") from exc

        reg_result: Optional[dict[str, Any]] = None
        try:
            async for msg in self.client.receive_response():
                if isinstance(msg, SystemMessage):
                    if msg.subtype == "init" and isinstance(msg.data, Mapping):
                        if self._init_data:
                            raise HelperProtocolError("duplicate native initialization")
                        if msg.data.get("session_id") != session_id:
                            await self._safe_disconnect()
                            raise HelperProtocolError("init session_id mismatch")
                        self._capture_init(msg.data, session_id)
                elif isinstance(msg, ResultMessage):
                    if msg.session_id != session_id:
                        await self._safe_disconnect()
                        raise HelperProtocolError("registration session_id mismatch")
                    if msg.subtype != "success" or msg.is_error:
                        await self._safe_disconnect()
                        raise HelperProtocolError("registration result is not success")
                    if type(msg.num_turns) is not int or msg.num_turns != 0:
                        await self._safe_disconnect()
                        raise HelperProtocolError("registration is not zero-turn")
                    usage = msg.usage if isinstance(msg.usage, Mapping) else {}
                    for key in (
                        "input_tokens",
                        "cache_creation_input_tokens",
                        "cache_read_input_tokens",
                        "output_tokens",
                    ):
                        if type(usage.get(key)) is not int or usage[key] != 0:
                            await self._safe_disconnect()
                            raise HelperProtocolError("registration has non-zero usage")
                    if type(msg.total_cost_usd) not in (int, float) or msg.total_cost_usd != 0:
                        await self._safe_disconnect()
                        raise HelperProtocolError("registration has non-zero cost")
                    reg_result = {
                        "subtype": msg.subtype,
                        "is_error": bool(msg.is_error),
                        "num_turns": int(msg.num_turns),
                    }
                else:
                    raise HelperProtocolError("unexpected model event during registration")
        except HelperProtocolError:
            await self._safe_disconnect()
            raise
        except Exception as exc:
            await self._safe_disconnect()
            raise HelperProtocolError("registration drain failed") from exc

        if reg_result is None:
            await self._safe_disconnect()
            raise HelperProtocolError("registration result was not observed")
        if not self._init_data:
            await self._safe_disconnect()
            raise HelperProtocolError("init SystemMessage was not observed")

        self._registration_kept = reg_result
        self.session_id = session_id
        try:
            self._sdk_version = importlib.metadata.version("claude-agent-sdk")
        except Exception:
            self._sdk_version = None
        try:
            self._effective_policy = await self._observe_policy()
        except Exception:
            await self._safe_disconnect()
            raise
        return self._build_handshake(server, context, mcp)

    async def _observe_policy(self) -> dict[str, Any]:
        # Native get_settings is a published control subtype. Python has no
        # public convenience wrapper yet; this bridge is qualified only against
        # these exact versions. Do not infer effective settings from argv.
        if self._sdk_version != "0.2.160" or self._cli_version != "2.1.275":
            raise HelperProtocolError("native settings bridge version is unqualified")
        try:
            response = await self.client._query._send_control_request(
                {"subtype": "get_settings"}, timeout=10.0
            )
            if (not isinstance(response, Mapping) or set(response) != {"applied", "effective", "sources"}
                    or not isinstance(response["effective"], Mapping)
                    or set(response["effective"]) - {"sandbox", "permissions"}):
                raise HelperProtocolError("unqualified effective settings or native readback shape")
            from control_plane.claude_operator_helper_protocol import security_settings
            return security_settings(response.get("effective"))
        except Exception as exc:
            raise HelperProtocolError("effective native policy is unavailable") from exc

    def _capture_init(self, data: Mapping[str, Any], session_id: str) -> None:
        api_key_source = bounded_text(data.get("apiKeySource"), limit=100)
        if api_key_source not in _SAFE_API_KEY_SOURCES:
            raise HelperProtocolError("apiKeySource is not a safe tag")
        self._init_data = {
            "model": bounded_text(data.get("model"), limit=200),
            "tools": _bounded_list(data.get("tools")),
            "skills": _bounded_list(data.get("skills")),
            "mcp_servers": _bounded_list(data.get("mcp_servers")),
            "plugins": _bounded_list(data.get("plugins")),
            "cwd": bounded_text(data.get("cwd"), limit=4096),
            "permissionMode": bounded_text(data.get("permissionMode"), limit=100),
            "claude_code_version": bounded_text(data.get("claude_code_version"), limit=100),
            "apiKeySource": api_key_source,
            "session_id": session_id,
        }
        self._cli_version = self._init_data["claude_code_version"]
        # Require strict resolved exact model match parent config model.
        resolved_model = self._init_data["model"]
        if resolved_model != self.config.get("model"):
            raise HelperProtocolError("resolved model does not match parent config")
        if self._init_data["cwd"] != self.config["cwd"]:
            raise HelperProtocolError("native workspace mismatch")
        if self._init_data["permissionMode"] != self.config.get("permission_mode", "dontAsk"):
            raise HelperProtocolError("native permission mode mismatch")

    def _build_handshake(
        self,
        server: Any,
        context: Any,
        mcp: Any,
    ) -> Mapping[str, Any]:
        account_raw = server.get("account") if isinstance(server, Mapping) else None
        account = None
        if isinstance(account_raw, Mapping):
            account = {
                "apiProvider": bounded_text(account_raw.get("apiProvider"), limit=100),
                "subscriptionType": bounded_text(account_raw.get("subscriptionType"), limit=100),
            }
        server_info: dict[str, Any] = {}
        if isinstance(server, Mapping):
            server_info = {
                "current_permission_mode": bounded_text(
                    server.get("current_permission_mode"), limit=100
                ),
                "session_state": bounded_text(server.get("session_state"), limit=100),
                "account": account,
            }
        context_usage: dict[str, Any] = {}
        if isinstance(context, Mapping):
            context_usage = {"model": bounded_text(context.get("model"), limit=200)}
        # SDK uses key "mcpServers"; helper emits "servers" with names + status only.
        servers_out: list[dict[str, Any]] = []
        if isinstance(mcp, Mapping):
            raw_servers = mcp.get("mcpServers") or mcp.get("servers") or []
            if isinstance(raw_servers, list):
                for entry in raw_servers:
                    if isinstance(entry, Mapping):
                        servers_out.append(
                            {
                                "name": bounded_text(entry.get("name"), limit=200),
                                "status": bounded_text(entry.get("status"), limit=100),
                            }
                        )
                    elif isinstance(entry, str):
                        servers_out.append({"name": bounded_text(entry, limit=200), "status": None})
        return {
            "session_id": self.session_id,
            "server_info": server_info,
            "context_usage": context_usage,
            "mcp_status": {"servers": servers_out},
            "sdk_version": self._sdk_version,
            "cli_version": self._cli_version,
            "initialization": dict(self._init_data),
            "registration_zero_turn": True,
            "effective_policy": self._effective_policy,
            "native_subscription_verified": True,
            "applied_launch_provenance": self._applied_launch_provenance,
            "settings_readback_provenance": "native-get_settings/0.2.160/2.1.275",
        }

    async def begin_turn(self, turn_id: str, payload: str) -> Mapping[str, Any]:
        await self._require_client()
        if await self._observe_policy() != self._effective_policy:
            self._failure = "native_policy_drift"
            raise HelperProtocolError("effective native policy drifted before work")
        if not isinstance(turn_id, str) or not turn_id or len(turn_id) > 128:
            raise HelperProtocolError("turn_id is malformed")
        if self._failure is not None:
            raise HelperProtocolError("generation requires Executive reconciliation")
        if turn_id in self._seen_turns:
            raise HelperProtocolError("turn_id is duplicate")
        if self.active_turn_id is not None and not self._collected:
            raise HelperProtocolError("turn is already active")
        if self._drain_task is not None and not self._drain_task.done():
            raise HelperProtocolError("previous native response drain is not closed")
        if not isinstance(payload, str):
            raise HelperProtocolError("payload must be a string")
        if len(payload.encode("utf-8")) > MAX_TEXT_CHARS:
            raise HelperProtocolError("payload exceeds bound")

        # Reset per-turn state (terminal/ack/etc.) BEFORE recording new turn id.
        self.active_turn_id = turn_id
        self._seen_turns.add(turn_id)
        self._collected = False
        self._success = False
        self._native_result_id = None
        self.active_turn_payload = payload
        self.terminal = False
        self.acknowledged = False
        self.summary = None
        self._stop_drain = asyncio.Event()  # noqa: F841

        session_id = self.session_id

        async def turn_payload() -> AsyncIterator[dict]:
            yield {
                "type": "user",
                "session_id": session_id,
                "parent_tool_use_id": None,
                "message": {"role": "user", "content": payload},
            }

        try:
            await self.client.query(turn_payload(), session_id=session_id)
        except HelperProtocolError:
            self._failure = "query_effect_unknown"
            raise
        except Exception as exc:
            self._failure = "query_effect_unknown"
            raise HelperProtocolError("native query effect requires reconciliation") from exc

        self._model_was_queried = True
        self._drain_closed = False
        self._drain_task = asyncio.create_task(self._drain_response())
        # ACK is only marked true when an actual provider response event is observed.
        return {"provider_turn_id": turn_id, "acknowledged": self.acknowledged}

    async def _drain_response(self) -> None:
        draining_turn_id = self.active_turn_id
        sdk = _SDK_FACTORY()
        AssistantMessage = getattr(sdk, "AssistantMessage", None)
        SystemMessage = getattr(sdk, "SystemMessage", None)
        ResultMessage = getattr(sdk, "ResultMessage", None)
        try:
            async for msg in self.client.receive_response():
                if self.active_turn_id != draining_turn_id:
                    self._failure = "late_response_turn_mismatch"
                    return
                if self._stop_drain.is_set():
                    break
                if SystemMessage is not None and isinstance(msg, SystemMessage):
                    self._record_event(
                        {
                            "kind": "system",
                            "subtype": bounded_text(msg.subtype, limit=100),
                        },
                    )
                    self.acknowledged = True
                elif AssistantMessage is not None and isinstance(msg, AssistantMessage):
                    if getattr(msg, "session_id", None) not in (None, self.session_id):
                        self._failure = "assistant_session_mismatch"
                        return
                    text = self._extract_assistant_text(msg)
                    self._record_event(
                        {"kind": "message", "text": redact_evidence_text(text[:MAX_TEXT_CHARS])},
                    )
                    self.acknowledged = True
                elif ResultMessage is not None and isinstance(msg, ResultMessage):
                    if msg.session_id != self.session_id:
                        self._failure = "terminal_session_mismatch"
                        return
                    self.summary = bounded_text(getattr(msg, "result", None), limit=MAX_TEXT_CHARS)
                    self.terminal = True
                    self._success = msg.subtype == "success" and msg.is_error is False
                    if getattr(msg, "terminal_reason", None) in {"aborted_streaming", "aborted_tools", "max_turns"}:
                        self._success = False
                    origin = getattr(msg, "origin", None)
                    if origin is not None and (not isinstance(origin, Mapping) or origin.get("kind") != "human"):
                        self._failure = "unexpected_terminal_origin"
                        self._success = False
                    self._native_result_id = bounded_text(getattr(msg, "uuid", None), limit=128)
                    if not self._success:
                        status = getattr(msg, "api_error_status", None)
                        self._failure = self._failure or ("authentication_required" if status in (401, 403) else (
                            "quota_or_rate_limit" if status == 429 else "provider_turn_failed")
                        )
                    self.acknowledged = True
                    self._record_event(
                        {
                            "kind": "result",
                            "subtype": bounded_text(msg.subtype, limit=100),
                            "is_error": bool(getattr(msg, "is_error", False)),
                            "session_id": bounded_text(getattr(msg, "session_id", None), limit=64),
                            "num_turns": int(getattr(msg, "num_turns", 0) or 0),
                        },
                    )
            if not self.terminal and self._failure is None:
                self._failure = "terminal_result_missing"
        except asyncio.CancelledError:
            self._failure = "response_effect_unknown"
            raise
        except Exception:
            self._failure = "response_effect_unknown"
        finally:
            self._drain_closed = True

    @staticmethod
    def _extract_assistant_text(msg: Any) -> str:
        chunks: list[str] = []
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                if isinstance(block, Mapping):
                    if block.get("type") == "text":
                        text = bounded_text(block.get("text"), limit=MAX_TEXT_CHARS)
                        if text:
                            chunks.append(text)
                    elif "text" in block and isinstance(block.get("text"), str):
                        text = bounded_text(block.get("text"), limit=MAX_TEXT_CHARS)
                        if text:
                            chunks.append(text)
                elif isinstance(block, str):
                    chunks.append(block)
                elif isinstance(getattr(block, "text", None), str):
                    chunks.append(block.text[:MAX_TEXT_CHARS])
        elif isinstance(content, str):
            chunks.append(content)
        return "".join(chunks)[:MAX_TEXT_CHARS]

    async def read_events(self, max_events: int, after_sequence: int = 0) -> Mapping[str, Any]:
        await self._require_client()
        if type(max_events) is not int or not 1 <= max_events <= MAX_EVENTS:
            raise HelperProtocolError("max_events is out of range")
        if type(after_sequence) is not int or not 0 <= after_sequence <= self._event_sequence:
            raise HelperProtocolError("event cursor is invalid")
        if self.events and after_sequence < self.events[0]["sequence"] - 1:
            raise HelperProtocolError("event cursor fell outside retained window")
        pending = [x for x in self.events if x["sequence"] > after_sequence]
        drained, wire_size = [], 0
        for event in pending[:max_events]:
            size = len(encode_json_line(event))
            if wire_size + size > MAX_WIRE_BYTES // 2:
                break
            drained.append(event)
            wire_size += size
        return {"events": drained, "has_more": len(drained) < len(pending)}

    async def interrupt(self) -> None:
        await self._require_client()
        try:
            await self.client.interrupt()
        except Exception as exc:
            self._failure = "interrupt_effect_unknown"
            raise HelperProtocolError("interrupt requires reconciliation") from exc

    async def collect(self) -> Mapping[str, Any]:
        await self._require_client()
        if self.active_turn_id is None:
            raise HelperProtocolError("turn is not active")
        if not self.terminal or not self._drain_closed:
            return {"terminal": False, "success": False, "failure": self._failure,
                    "summary": None, "acknowledged": self.acknowledged,
                    "drain_closed": self._drain_closed, "event_sequence": self._event_sequence}
        # Fully drain terminal turn: keep candidate bounded, preserve session match.
        if len(self.events) > MAX_EVENTS:
            self.events = self.events[-MAX_EVENTS:]
        # Only a completely observed successful turn permits subsequent work.
        finished_turn_id = self.active_turn_id
        successful = self._success and self._failure is None
        self._collected = successful
        return {
            "terminal": True,
            "success": successful,
            "failure": self._failure,
            "summary": self.summary if successful else None,
            "acknowledged": self.acknowledged,
            "drain_closed": True,
            "event_sequence": self._event_sequence,
            "session_id": self.session_id,
            "turn_id": finished_turn_id,
            "native_result_id": self._native_result_id,
        }

    async def reconcile(self) -> Mapping[str, Any]:
        if self.client is None:
            return {"session_reachable": False}
        try:
            server = await self.client.get_server_info()
            context = await self.client.get_context_usage()
        except Exception:
            return {"session_reachable": None}
        state = server.get("session_state") if isinstance(server, Mapping) else None
        model = context.get("model") if isinstance(context, Mapping) else None
        return {
            "session_reachable": True,
            "session_state": bounded_text(state, limit=100),
            "model": bounded_text(model, limit=200),
            "session_id": self.session_id,
            "active_turn_id": self.active_turn_id,
            "terminal": self.terminal,
            "failure": self._failure,
        }

    async def disconnect(self) -> None:
        self._stop_drain.set()
        if self._drain_task is not None and not self._drain_task.done():
            self._drain_task.cancel()
            try:
                await self._drain_task
            except (asyncio.CancelledError, Exception):
                pass
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None

    async def _safe_disconnect(self) -> None:
        try:
            await self.disconnect()
        except Exception:
            pass

    async def _require_client(self) -> None:
        if self.client is None:
            raise HelperProtocolError("native client is not initialized")


async def _dispatch(line: bytes, runtime: Optional[HelperRuntime], seen: set) -> tuple:
    """Returns (response_dict, new_runtime_or_None)."""
    request_id = "unknown"
    try:
        message = decode_json_line(line)
        request = parse_request(message, seen_request_ids=seen)
        request_id = request.request_id
        fields = request.fields
        operation = request.operation

        if operation == "initialize":
            if runtime is not None:
                raise HelperProtocolError("generation is already initialized")
            runtime = HelperRuntime(fields["generation_id"], fields["config"])
            try:
                value = await runtime.initialize()
            except Exception:
                await runtime._safe_disconnect()
                runtime = None
                raise
            return ({"ok": True, "request_id": request_id, "value": value}, runtime)

        if runtime is None or fields["generation_id"] != runtime.generation_id:
            raise HelperProtocolError("generation is not initialized")

        if operation == "begin_turn":
            if "turn_id" not in fields or "payload" not in fields:
                raise HelperProtocolError("turn_id and payload are required")
            if runtime.active_turn_id == fields["turn_id"]:
                raise HelperProtocolError("turn_id is duplicate")
            value = await runtime.begin_turn(fields["turn_id"], fields["payload"])
        elif operation == "read_events":
            value = await runtime.read_events(fields["max_events"], fields["after_sequence"])
        elif operation == "interrupt":
            if "turn_id" in fields and fields["turn_id"] != runtime.active_turn_id:
                raise HelperProtocolError("turn_id does not match active turn")
            await runtime.interrupt()
            value = {"acknowledged": True}
        elif operation == "collect":
            if "turn_id" in fields and fields["turn_id"] != runtime.active_turn_id:
                raise HelperProtocolError("turn_id does not match active turn")
            value = await runtime.collect()
        elif operation == "reconcile":
            value = await runtime.reconcile()
        elif operation == "disconnect":
            await runtime.disconnect()
            value = {"acknowledged": True}
        else:
            raise HelperProtocolError("operation is refused")

        return ({"ok": True, "request_id": request_id, "value": value}, runtime)

    except HelperProtocolError as exc:
        return (
            {"ok": False, "request_id": request_id, "value": str(exc)[:500]},
            runtime,
        )
    except Exception as exc:
        return (
            {
                "ok": False,
                "request_id": request_id,
                "value": "helper refused malformed request",
            },
            runtime,
        )


async def _async_main() -> int:
    seen: set = set()
    runtime: Optional[HelperRuntime] = None
    loop = asyncio.get_running_loop()

    def _read_line() -> bytes:
        return sys.stdin.buffer.readline(MAX_WIRE_BYTES + 1)

    try:
        while True:
            line = await loop.run_in_executor(None, _read_line)
            if not line:
                break
            if len(line) > MAX_WIRE_BYTES or not line.endswith(b"\n"):
                break
            response, runtime = await _dispatch_rpc(line, runtime, seen)
            try:
                sys.stdout.buffer.write(encode_json_line(response))
                sys.stdout.buffer.flush()
            except BrokenPipeError:
                break
    finally:
        if runtime is not None:
            try:
                await runtime.disconnect()
            except Exception:
                pass
    return 0


async def _dispatch_rpc(line: bytes, runtime: Optional[HelperRuntime], seen: set) -> tuple:
    """Use Executive's existing JSON-RPC transport and owned-process lifecycle."""
    rpc_id = None
    try:
        wire = decode_json_line(line)
        if set(wire) != {"id", "method", "params"}:
            raise HelperProtocolError("RPC envelope is malformed")
        rpc_id = wire["id"]
        if type(rpc_id) is not int or not 1 <= rpc_id <= 1_000_000:
            raise HelperProtocolError("RPC id is malformed")
        if wire["method"] == "thread/turns/list":
            # Reuse Executive's existing private raw-result transport. This
            # compatibility operation only reads the exact active terminal turn;
            # it cannot launch, change a session, page another session or retry.
            fields = wire["params"]
            if (runtime is None or not isinstance(fields, dict)
                    or set(fields) != {"threadId", "turnId", "itemsView", "limit", "sortDirection"}
                    or fields["threadId"] != runtime.session_id or fields["turnId"] != runtime.active_turn_id
                    or fields["itemsView"] != "full" or type(fields["limit"]) is not int
                    or fields["limit"] != 1 or fields["sortDirection"] != "desc"):
                raise HelperProtocolError("private result identity is invalid")
            request_id = f"req-{rpc_id}"
            if request_id in seen or len(seen) >= 4096:
                raise HelperProtocolError("private result request is duplicate or exhausted")
            seen.add(request_id)
            return {"id": rpc_id, "result": await runtime.collect()}, runtime
        response, runtime = await _dispatch(encode_json_line({
            "request_id": f"req-{rpc_id}", "operation": wire["method"],
            "fields": wire["params"],
        }), runtime, seen)
        if response["ok"]:
            return {"id": rpc_id, "result": response["value"]}, runtime
        return {"id": rpc_id, "error": {"code": -32000, "message": response["value"]}}, runtime
    except Exception:
        return {"id": rpc_id, "error": {"code": -32600, "message": "malformed native helper RPC"}}, runtime


def main() -> int:
    try:
        return asyncio.run(_async_main())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
