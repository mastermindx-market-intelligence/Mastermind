"""Fixed private Session Bridge boundary shared by host and integration owners.

This contract does not discover targets, admit Jobs, validate business scopes,
or own a transport. The installed integration supplies its closed validator and
handler; the control service checks this nominal owner before entering it.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

PRIVATE_SCHEMA = "mastermind.executive_ceo_ingress_session_bridge.v1"
PRIVATE_RESULT_SCHEMA = "mastermind.executive_ceo_ingress_session_bridge_result.v1"
SESSION_TOOLS = ("session_targets", "session_send", "session_summon", "session_reply_read")
MODIFYING_TOOLS = ("session_send", "session_summon")


class BridgeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def private_result(tool: str, *, data: Any = None, code: str | None = None,
                   message: str | None = None) -> dict[str, Any]:
    return {
        "schema": PRIVATE_RESULT_SCHEMA,
        "tool": tool,
        "ok": code is None,
        "data": data if code is None else None,
        "error": None if code is None else {
            "code": code,
            "message": message or "installed Session Bridge operation was refused",
        },
    }


@dataclass(frozen=True)
class SessionBridgeIngressOwner:
    validator: Callable[[Any], str]
    handler: Callable[[Any], Awaitable[Mapping[str, Any]]]

    def __post_init__(self) -> None:
        if not callable(self.validator) or not callable(self.handler):
            raise TypeError("Session Bridge requires its fixed validator and handler")

    def validate_frame(self, frame: Any) -> str:
        tool = self.validator(frame)
        if type(tool) is not str or tool not in SESSION_TOOLS:
            raise BridgeError("invalid_input", "installed Session Bridge tool is invalid")
        return tool

    async def handle_frame(self, frame: Any) -> Mapping[str, Any]:
        result = await self.handler(frame)
        if not isinstance(result, Mapping):
            raise ValueError("installed Session Bridge result is invalid")
        return result
