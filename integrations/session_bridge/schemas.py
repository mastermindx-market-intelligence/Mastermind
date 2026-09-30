"""Strict public contract for the stateless Mastermind Session Bridge."""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from typing import Any

SERVER_NAME = "mastermind-session-bridge"
SERVER_VERSION = "0.1.0"
RESULT_SCHEMA = "mastermind.session_bridge_result.v1"

TARGET_KINDS = ("fabric_attempt", "codex", "claude")
MODIFYING_TOOLS = ("session_send", "session_summon")
MAX_MESSAGE_CHARS = 12000
MAX_OPERATION_KEY_CHARS = 96

_TARGET_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_OPERATION_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")


class BridgeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    name: str
    modifying: bool


TOOL_SPECS = (
    ToolSpec("session_targets", False),
    ToolSpec("session_send", True),
    ToolSpec("session_summon", True),
)


def tool_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in TOOL_SPECS)


def _object(value: Any, *, required: set[str], optional: set[str] | None = None) -> Mapping[str, Any]:
    optional = optional or set()
    if not isinstance(value, Mapping):
        raise BridgeError("invalid_input", "arguments must be an object")
    keys = set(value)
    missing = required - keys
    extra = keys - required - optional
    if missing:
        raise BridgeError("invalid_input", f"missing fields: {sorted(missing)}")
    if extra:
        raise BridgeError("invalid_input", f"unexpected fields: {sorted(extra)}")
    return value


def _text(value: Any, field: str, *, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BridgeError("invalid_input", f"{field} must be a non-empty string")
    if len(value) > max_chars:
        raise BridgeError("invalid_input", f"{field} exceeds {max_chars} characters")
    return value


def validate_tool_arguments(tool_name: str, arguments: Any) -> dict[str, Any]:
    if tool_name == "session_targets":
        obj = _object(arguments, required=set(), optional={"kind"})
        kind = obj.get("kind")
        if kind is not None and kind not in TARGET_KINDS:
            raise BridgeError("invalid_input", "kind is unsupported")
        return {} if kind is None else {"kind": kind}

    if tool_name == "session_send":
        obj = _object(arguments, required={"target_ref", "message", "operation_key"})
        target_ref = _text(obj["target_ref"], "target_ref", max_chars=256)
        if _TARGET_REF_RE.fullmatch(target_ref) is None:
            raise BridgeError("invalid_input", "target_ref has an unsupported form")
        message = _text(obj["message"], "message", max_chars=MAX_MESSAGE_CHARS)
        operation_key = _text(obj["operation_key"], "operation_key", max_chars=MAX_OPERATION_KEY_CHARS)
        if _OPERATION_KEY_RE.fullmatch(operation_key) is None:
            raise BridgeError("invalid_input", "operation_key has an unsupported form")
        return {"target_ref": target_ref, "message": message, "operation_key": operation_key}

    if tool_name == "session_summon":
        obj = _object(
            arguments,
            required={"objective", "execution_profile", "operation_key"},
            optional={"preferred_surface"},
        )
        objective = _text(obj["objective"], "objective", max_chars=4000)
        execution_profile = _text(obj["execution_profile"], "execution_profile", max_chars=64)
        operation_key = _text(obj["operation_key"], "operation_key", max_chars=MAX_OPERATION_KEY_CHARS)
        if _OPERATION_KEY_RE.fullmatch(operation_key) is None:
            raise BridgeError("invalid_input", "operation_key has an unsupported form")
        preferred_surface = obj.get("preferred_surface")
        if preferred_surface is not None and preferred_surface not in ("codex", "claude"):
            raise BridgeError("invalid_input", "preferred_surface is unsupported")
        out = {
            "objective": objective,
            "execution_profile": execution_profile,
            "operation_key": operation_key,
        }
        if preferred_surface is not None:
            out["preferred_surface"] = preferred_surface
        return out

    raise BridgeError("not_found", "unknown tool")
