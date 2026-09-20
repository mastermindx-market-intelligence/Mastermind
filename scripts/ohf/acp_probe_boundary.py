"""Provider-free ACP qualification boundary; NOT an Executive worker adapter.

The optional SDK driver owns JSON-RPC and its streams. This module supplies a
bounded borrowed reader and a deny-only client for deterministic protocol peers.
It never launches a provider, registers an adapter, chooses an account, creates a
Job/Attempt, persists a session, resumes, retries, or declares production proof.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import math
import re
from typing import Any, Protocol


class BoundaryViolation(ValueError):
    """Fixed, secret-free reason; never copy a peer's exception or payload here."""


@dataclasses.dataclass(frozen=True)
class ProbeLimits:
    frame_bytes: int = 64 * 1024
    frames: int = 256
    text_bytes: int = 32 * 1024
    updates: int = 128
    permission_requests: int = 32

    def __post_init__(self) -> None:
        for name, lower, upper in (
            ("frame_bytes", 64, 1024 * 1024), ("frames", 1, 4096),
            ("text_bytes", 1, 1024 * 1024),
            ("updates", 1, 4096), ("permission_requests", 1, 256)):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError("INVALID_PROBE_LIMIT")


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    # ACP's Pydantic models are normalized at the SDK seam, not copied/redefined.
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        result = model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(result, dict):
            return result
    raise BoundaryViolation("INVALID_TYPED_VALUE")


def _update_text(update: Any) -> bytes:
    data = _as_dict(update)
    if set(data) != {"sessionUpdate", "content"} or data["sessionUpdate"] != "agent_message_chunk":
        raise BoundaryViolation("UPDATE_NOT_ADMITTED")
    content = data["content"]
    if not isinstance(content, dict) or set(content) != {"type", "text"} or content["type"] != "text":
        raise BoundaryViolation("UPDATE_NOT_ADMITTED")
    text = content["text"]
    if not isinstance(text, str):
        raise BoundaryViolation("UPDATE_NOT_ADMITTED")
    return text.encode("utf-8", errors="strict")


class ProbeClient:
    """One ephemeral fixture observation, with no durable lifecycle authority."""

    def __init__(self, limits: ProbeLimits | None = None):
        self.limits = limits or ProbeLimits()
        self.session_id: str | None = None
        self.violation: str | None = None
        self._issued = self._active = False
        self._updates = self._text_bytes = self._denials = 0
        self._digest = hashlib.sha256()

    def poison(self, reason: str) -> None:
        if self.violation is None:
            self.violation = reason

    def admit_update(self, update: Any) -> int:
        """Apply this client's semantic update policy and return its text size."""
        text = _update_text(update)
        self._digest.update(text)
        return len(text)

    def bind_session(self, session_id: str) -> None:
        if self.session_id is not None:
            self.poison("SESSION_REBIND")
            raise BoundaryViolation("SESSION_REBIND")
        if not isinstance(session_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id) is None:
            self.poison("INVALID_SESSION_ID")
            raise BoundaryViolation("INVALID_SESSION_ID")
        self.session_id = session_id

    def begin_prompt(self) -> None:
        if self._issued:
            raise BoundaryViolation("PROMPT_ALREADY_ISSUED")
        if self.session_id is None or self.violation is not None:
            raise BoundaryViolation("PROBE_NOT_READY")
        self._issued = self._active = True

    def seal(self) -> None:
        self._active = False

    def _callback_allowed(self, session_id: str) -> bool:
        if self.violation is not None:
            return False
        if not self._active:
            self.poison("CALLBACK_OUTSIDE_PROMPT")
        elif session_id != self.session_id:
            self.poison("SESSION_MISMATCH")
        return self.violation is None

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        if not self._callback_allowed(session_id):
            return
        if self._updates >= self.limits.updates:
            self.poison("UPDATE_BUDGET_EXCEEDED")
            return
        try:
            size = self.admit_update(update)
        except (ValueError, TypeError, UnicodeError):
            self.poison("UPDATE_NOT_ADMITTED")
            return
        if self._text_bytes + size > self.limits.text_bytes:
            self.poison("TEXT_BUDGET_EXCEEDED")
            return
        self._updates += 1
        self._text_bytes += size

    async def request_permission(self, session_id: str, tool_call: Any, options: Any, **kwargs: Any) -> dict:
        if self._callback_allowed(session_id):
            if self._denials >= self.limits.permission_requests:
                self.poison("PERMISSION_BUDGET_EXCEEDED")
            else:
                self._denials += 1
        # Never choose allow_once/allow_always based on provider-supplied options.
        return {"outcome": {"outcome": "cancelled"}}

    async def _deny_tool(self, *args: Any, **kwargs: Any) -> None:
        self.poison("TOOL_NOT_GRANTED")
        raise BoundaryViolation("TOOL_NOT_GRANTED")

    read_text_file = write_text_file = create_terminal = _deny_tool
    terminal_output = release_terminal = wait_for_terminal_exit = kill_terminal = _deny_tool
    ext_method = ext_notification = create_elicitation = complete_elicitation = _deny_tool

    def on_connect(self, conn: Any) -> None:
        # Connection availability grants no capability and dispatches no work.
        pass

    def snapshot(self) -> dict[str, Any]:
        return {
            "proof_scope": "PROVIDER_FREE_PROTOCOL_ONLY",
            "production_proven": False,
            "worker_adapter_implemented": False,
            "updates": self._updates,
            "text_bytes": self._text_bytes,
            "text_sha256": self._digest.hexdigest(),
            "permission_denials": self._denials,
            "boundary_violation": self.violation,
        }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BoundaryViolation("INVALID_FRAME")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise BoundaryViolation("INVALID_FRAME")


def _validate_json_structure(value: Any) -> None:
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 32 or nodes > 8192:
            raise BoundaryViolation("INVALID_FRAME")
        if isinstance(item, float) and not math.isfinite(item):
            raise BoundaryViolation("INVALID_FRAME")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _validate_rpc_frame(message: Any) -> None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise BoundaryViolation("INVALID_FRAME")
    if set(message) - {"jsonrpc", "id", "method", "params", "result", "error"}:
        raise BoundaryViolation("INVALID_FRAME")
    if "id" in message:
        request_id = message["id"]
        if not ((type(request_id) is int and 0 <= request_id <= 2**53 - 1)
                or (isinstance(request_id, str) and 1 <= len(request_id) <= 128)):
            raise BoundaryViolation("INVALID_FRAME")
    if "method" in message:
        if (not isinstance(message["method"], str) or not 1 <= len(message["method"]) <= 128
                or "result" in message or "error" in message
                or not isinstance(message.get("params", {}), dict)):
            raise BoundaryViolation("INVALID_FRAME")
    elif ("id" not in message or ("result" in message) == ("error" in message)
          or "params" in message):
        raise BoundaryViolation("INVALID_FRAME")
    result = message.get("result")
    if isinstance(result, dict):
        # Preserve wire types before the SDK's model construction can coerce them.
        if "protocolVersion" in result and type(result["protocolVersion"]) is not int:
            raise BoundaryViolation("INVALID_FRAME")
        for field in ("sessionId", "stopReason"):
            if field in result and not isinstance(result[field], str):
                raise BoundaryViolation("INVALID_FRAME")
    _validate_json_structure(message)


class StrictFrameReader:
    """Borrowed byte reader guarding SDK NDJSON parsing, not a JSON-RPC stack.

    Use a StreamReader configured with limit <= frame_bytes. An overrun becomes
    a different exception so SDK 0.12.1 cannot repeatedly drain readexactly() and
    accumulate an unbounded frame. No transport/process close or signal is owned
    here. Malformed bytes are never forwarded to the SDK's skip-and-continue path.
    """

    def __init__(self, reader: asyncio.StreamReader, client: ProbeClient):
        self.reader, self.client = reader, client
        self._frames = 0
        # asyncio exposes no public getter for its configured frame limit. This
        # probe binds that implementation seam explicitly, not by optimistic default.
        if type(getattr(reader, "_limit", None)) is not int or not 0 < reader._limit <= client.limits.frame_bytes:
            raise BoundaryViolation("READER_LIMIT_UNQUALIFIED")

    async def readuntil(self, separator: bytes = b"\n") -> bytes:
        if separator != b"\n":
            raise BoundaryViolation("DELIMITER_NOT_ADMITTED")
        if self.client.violation:
            raise BoundaryViolation(self.client.violation)
        try:
            line = await self.reader.readuntil(separator)
        except asyncio.LimitOverrunError:
            self.client.poison("FRAME_TOO_LARGE")
            raise BoundaryViolation("FRAME_TOO_LARGE") from None
        except asyncio.IncompleteReadError as exc:
            if not exc.partial:
                raise
            self.client.poison("PARTIAL_FRAME")
            raise BoundaryViolation("PARTIAL_FRAME") from None
        if self._frames >= self.client.limits.frames:
            self.client.poison("FRAME_BUDGET_EXCEEDED")
            raise BoundaryViolation("FRAME_BUDGET_EXCEEDED")
        if len(line) > self.client.limits.frame_bytes:
            self.client.poison("FRAME_TOO_LARGE")
            raise BoundaryViolation("FRAME_TOO_LARGE")
        try:
            obj = json.loads(line.decode("utf-8", errors="strict"),
                             object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            _validate_rpc_frame(obj)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self.client.poison("INVALID_FRAME")
            raise BoundaryViolation("INVALID_FRAME") from None
        self._frames += 1
        params = obj.get("params", {})
        method = obj.get("method")
        if method is not None:
            if method not in {"session/update", "session/request_permission"}:
                self.client.poison("TOOL_NOT_GRANTED")
                raise BoundaryViolation("TOOL_NOT_GRANTED")
            if not self.client._callback_allowed(params.get("sessionId")):
                raise BoundaryViolation(self.client.violation)
            try:
                if method == "session/update":
                    if set(params) != {"sessionId", "update"}:
                        raise BoundaryViolation("UPDATE_NOT_ADMITTED")
                    self.client.admit_update(params["update"])
                else:
                    if (set(params) != {"sessionId", "toolCall", "options"}
                            or not isinstance(params["toolCall"], dict)
                            or not isinstance(params["toolCall"].get("toolCallId"), str)
                            or not isinstance(params["options"], list)
                            or not 1 <= len(params["options"]) <= 16):
                        raise BoundaryViolation("PERMISSION_FRAME_NOT_ADMITTED")
                    for option in params["options"]:
                        if (not isinstance(option, dict)
                                or set(option) != {"optionId", "kind", "name"}
                                or any(not isinstance(value, str) or not 1 <= len(value) <= 128
                                       for value in option.values())
                                or option["kind"] not in {"allow_once", "allow_always", "reject_once", "reject_always"}):
                            raise BoundaryViolation("PERMISSION_FRAME_NOT_ADMITTED")
            except (KeyError, ValueError, TypeError, UnicodeError):
                code = "UPDATE_NOT_ADMITTED" if method == "session/update" else "PERMISSION_FRAME_NOT_ADMITTED"
                self.client.poison(code)
                raise BoundaryViolation(code) from None
        return line


class PromptPort(Protocol):
    async def prompt(self, *, session_id: str, prompt: list[dict]) -> Any: ...
    async def cancel(self, *, session_id: str) -> Any: ...


def _seconds(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 30:
        raise ValueError("INVALID_PROBE_TIMEOUT")
    return float(value)


async def observe_prompt(
    peer: PromptPort, client: ProbeClient, text: str, *,
    timeout: float = 2.0, cancel_timeout: float = 0.25,
    cancel_event: asyncio.Event | None = None,
) -> dict[str, Any]:
    """Observe one fixture turn; a cancel notification is never terminal proof.

    Local cancellation of an awaiting task is bookkeeping only. Neither it nor
    this receipt proves provider cancellation, process cleanup, or released quota.
    The fixture driver separately owns closure of its deterministic peers.
    """
    timeout, cancel_timeout = _seconds(timeout), _seconds(cancel_timeout)
    if not isinstance(text, str) or not 0 < len(text.encode("utf-8")) <= 4096:
        raise ValueError("INVALID_PROBE_PROMPT")
    if cancel_event is not None and cancel_event.is_set():
        return {**client.snapshot(), "disposition": "NOT_DISPATCHED", "reason": "PRE_CANCELLED",
                "prompt_calls": 0, "cancel_calls": 0, "local_tasks_pending": 0}
    client.begin_prompt()
    prompt = asyncio.create_task(peer.prompt(session_id=client.session_id, prompt=[{"type": "text", "text": text}]))
    wake = asyncio.create_task(cancel_event.wait()) if cancel_event else None
    owned: set[asyncio.Task] = {prompt}
    if wake:
        owned.add(wake)
    cancel_calls = 0
    reason = "PROMPT_TRANSPORT_UNCERTAIN"
    disposition = "INCONCLUSIVE"
    outer_cancelled = False
    try:
        semantic_deadline = asyncio.get_running_loop().time() + timeout
        done, _ = await asyncio.wait(owned, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        terminal_observed = prompt in done and asyncio.get_running_loop().time() <= semantic_deadline
        if not terminal_observed:
            cancel_calls = 1
            cancel = asyncio.create_task(peer.cancel(session_id=client.session_id))
            owned.add(cancel)
            # One absolute budget covers cancel delivery AND original prompt terminal.
            deadline = asyncio.get_running_loop().time() + cancel_timeout
            cancelled, _ = await asyncio.wait({cancel}, timeout=cancel_timeout)
            if (not cancelled or cancel.cancelled() or cancel.exception() is not None
                    or asyncio.get_running_loop().time() > deadline):
                reason = "CANCEL_DELIVERY_UNCERTAIN"
            else:
                finished, _ = await asyncio.wait({prompt}, timeout=max(0, deadline - asyncio.get_running_loop().time()))
                terminal_observed = prompt in finished and asyncio.get_running_loop().time() <= deadline
                if not terminal_observed:
                    reason = "CANCEL_TERMINAL_UNOBSERVED"
                else:
                    reason = "CANCEL_TERMINAL_MISMATCH"
        if terminal_observed and prompt.done() and not prompt.cancelled():
            if prompt.exception() is not None:
                reason = "PROMPT_TRANSPORT_UNCERTAIN"
            else:
                response = _as_dict(prompt.result())
                stop_reason = response.get("stopReason")
                if set(response) != {"stopReason"}:
                    reason = "TERMINAL_NOT_ADMITTED"
                elif cancel_calls and stop_reason == "cancelled":
                    disposition, reason = "OBSERVED_CANCELLED", "ORIGINAL_PROMPT_CANCELLED"
                elif not cancel_calls and stop_reason == "end_turn":
                    disposition, reason = "OBSERVED_END_TURN", "ORIGINAL_PROMPT_END_TURN"
                else:
                    reason = "CANCEL_TERMINAL_MISMATCH" if cancel_calls else "TERMINAL_NOT_ADMITTED"
    except asyncio.CancelledError:
        outer_cancelled = True
        reason = "CALLER_CANCELLED"
    except (ValueError, TypeError):
        reason = "TERMINAL_NOT_ADMITTED"
    finally:
        client.seal()
        for task in owned:
            if not task.done():
                task.cancel()
        _, pending = await asyncio.wait(owned, timeout=0.1)
        # Retrieve only settled exceptions; never wait indefinitely on a bad peer.
        for task in owned - pending:
            if not task.cancelled():
                task.exception()
    if outer_cancelled:
        raise asyncio.CancelledError
    if client.violation:
        disposition, reason = "INCONCLUSIVE", client.violation
    if pending:
        disposition, reason = "INCONCLUSIVE", "LOCAL_TASK_SETTLEMENT_UNPROVEN"
    return {**client.snapshot(), "disposition": disposition, "reason": reason,
            "prompt_calls": 1, "cancel_calls": cancel_calls, "local_tasks_pending": len(pending)}
