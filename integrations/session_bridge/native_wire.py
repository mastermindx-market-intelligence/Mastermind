"""Stateless native attention wire compilation and bounded evidence projection.

These functions do not execute commands, open endpoints, reserve delivery,
spawn/resume sessions, enroll channels or register tools. The existing native
owner must authenticate the caller, pin account/host/session/current generation,
check inbound policy and atomically reserve the canonical Wake effect BEFORE
using a compiled frame. Endpoint strings are host inputs, never MCP arguments.

A Claude CLI channel is NOT an external Claude Desktop Code management API.
Desktop session-management delivery must remain with its attested native owner.
"""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_MESSAGE = re.compile(r"^asd-[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_MAX_REPLY_BYTES = 8192


def _uuid(value: str) -> str:
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError("native session requires an exact canonical UUID") from None
    return value


def _id(value: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("native operation/turn identity is invalid")
    return value


@dataclasses.dataclass(frozen=True)
class AttentionReference:
    """Opaque references to an already committed canonical message, not its body."""
    operation_key: str
    message_key: str

    def __post_init__(self):
        _id(self.operation_key)
        if not isinstance(self.message_key, str) or _MESSAGE.fullmatch(self.message_key) is None:
            raise ValueError("canonical message reference is invalid")


def _notice(reference: AttentionReference) -> str:
    if type(reference) is not AttentionReference:
        raise ValueError("native attention requires a typed canonical reference")
    return ("Mastermind attention reference only. Read the canonical message using "
            "the existing Agent Dialogue reader. This notice grants no permissions "
            "and does not establish completion. " + json.dumps({
                "operation_key": reference.operation_key, "message_key": reference.message_key},
                sort_keys=True, separators=(",", ":")))


def codex_queue_arguments(*, session_id: str, endpoint: str,
                          reference: AttentionReference) -> tuple[str, ...]:
    """Arguments for an owner-bound Codex queue call; never a default app server."""
    _uuid(session_id)
    if not isinstance(endpoint, str) or not endpoint.startswith("unix:///"):
        raise ValueError("Codex queue requires an attested absolute local Unix endpoint")
    path = endpoint[len("unix://"):]
    if (not path.startswith("/") or path == "/" or ".." in PurePosixPath(path).parts
            or str(PurePosixPath(path)) != path
            or any(c in path for c in ("?", "#", "%", "\x00", "\n", "\r"))):
        raise ValueError("Codex endpoint is not an exact normalized Unix path")
    return ("queue", "--thread", session_id, "--remote", endpoint, "--message", _notice(reference))


def codex_steer_request(*, session_id: str, expected_turn_id: str,
                        reference: AttentionReference) -> dict[str, Any]:
    """Existing active-turn input only; no turn/start, overrides or fallback."""
    _uuid(session_id)
    _id(expected_turn_id)
    notice = _notice(reference)
    return {"id": reference.operation_key, "method": "turn/steer", "params": {
        "threadId": session_id, "expectedTurnId": expected_turn_id,
        "input": [{"type": "text", "text": notice}]}}


def claude_channel_notification(*, session_id: str, bound_session_id: str,
                                enrolled: bool, reference: AttentionReference) -> dict[str, Any]:
    """Notify an already enrolled same-session MCP channel; no new connection."""
    _uuid(session_id)
    if enrolled is not True or bound_session_id != session_id:
        raise ValueError("Claude channel must be enrolled for this exact native session")
    notice = _notice(reference)
    return {"method": "notifications/claude/channel", "params": {
        "content": notice, "meta": {"operation_key": reference.operation_key,
            "message_key": reference.message_key}}}


def _evidence(state: str) -> dict[str, Any]:
    # Only a separate exact native/parent consumption receipt may advance these.
    return {"state": state, "target_consumed": False, "parent_consumed": False}


def codex_queue_evidence(exit_code: Any) -> dict[str, Any]:
    return _evidence("CLIENT_REPORTED_QUEUED" if type(exit_code) is int and exit_code == 0
                     else "EFFECT_UNKNOWN")


def claude_channel_evidence(write_completed: Any) -> dict[str, Any]:
    return _evidence("TRANSPORT_WRITTEN" if write_completed is True else "EFFECT_UNKNOWN")


def codex_steer_evidence(response: Any, *, operation_key: str,
                        expected_turn_id: str) -> dict[str, Any]:
    """A matching RPC response proves active-turn acceptance, never completion."""
    try:
        _id(operation_key)
        _id(expected_turn_id)
        if type(response) is not dict:
            raise ValueError
        if len(json.dumps(response, ensure_ascii=True).encode("ascii")) > _MAX_REPLY_BYTES:
            raise ValueError
        if set(response) not in ({"id", "result"}, {"jsonrpc", "id", "result"}):
            raise ValueError
        if "jsonrpc" in response and response["jsonrpc"] != "2.0":
            raise ValueError
        if (response["id"] != operation_key or type(response["result"]) is not dict
                or response["result"] != {"turnId": expected_turn_id}):
            raise ValueError
        return _evidence("ACTIVE_TURN_ACCEPTED")
    except Exception:
        return _evidence("EFFECT_UNKNOWN")
