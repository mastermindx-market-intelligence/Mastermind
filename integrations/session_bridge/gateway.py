"""Stateless router from Dot-facing tools to incumbent canonical owners."""
from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from .schemas import BridgeError, RESULT_SCHEMA, SERVER_VERSION, validate_tool_arguments


class SessionBridgeGateway:
    """Delegate exact-session operations without owning lifecycle or placement.

    Backends are injected incumbent-owner adapters:
    * target_reader: current RuntimeBinding / Agent dialogue projection reader
    * sender: exact-target carrier adapter; MUST refuse stale/ambiguous targets
    * summoner: existing Executive admission/placement path
    """

    def __init__(
        self,
        *,
        target_reader: Callable[[str | None], Any],
        sender: Callable[[str, str, str], Any],
        summoner: Callable[[Mapping[str, Any]], Any],
    ) -> None:
        for name, value in (
            ("target_reader", target_reader),
            ("sender", sender),
            ("summoner", summoner),
        ):
            if not callable(value):
                raise TypeError(f"{name} must be callable")
        self._target_reader = target_reader
        self._sender = sender
        self._summoner = summoner

    async def call(self, tool_name: str, arguments: Any) -> dict[str, Any]:
        try:
            args = validate_tool_arguments(tool_name, arguments)
            if tool_name == "session_targets":
                data = await _maybe_await(self._target_reader(args.get("kind")))
            elif tool_name == "session_send":
                data = await _maybe_await(
                    self._sender(args["target_ref"], args["message"], args["operation_key"])
                )
            elif tool_name == "session_summon":
                # This MUST be an existing Executive admission path. The bridge
                # never constructs a provider session directly.
                data = await _maybe_await(self._summoner(args))
            else:
                raise BridgeError("not_found", "unknown tool")
            return {
                "schema": RESULT_SCHEMA,
                "server_version": SERVER_VERSION,
                "tool": tool_name,
                "ok": True,
                "data": data,
                "error": None,
            }
        except BridgeError as exc:
            return {
                "schema": RESULT_SCHEMA,
                "server_version": SERVER_VERSION,
                "tool": tool_name,
                "ok": False,
                "data": None,
                "error": {"code": exc.code, "message": exc.message},
            }


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value
