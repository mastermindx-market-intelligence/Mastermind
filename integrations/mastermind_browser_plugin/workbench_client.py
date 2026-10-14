"""Thin adapter from Browser-owner calls to the merged Workbench Browser MCP.

Transport, authentication, endpoint resolution, connection pooling and retries
belong to the injected caller/route owner. This adapter never serializes the
outer Browser caller identity into the low-level MCP request and never retries a
lost response.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
import inspect
from typing import Any

_READ_TOOLS = frozenset({"browser_snapshot", "browser_take_screenshot"})
_ACTION_TOOLS = frozenset({"browser_click", "browser_type", "browser_navigate"})
_EFFECTS = frozenset({"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"})
_MAX_REF_BYTES = 16 * 1024
_MAX_ARGUMENT_BYTES = 65_536


class WorkbenchBrowserClientError(RuntimeError):
    """Bounded internal Browser-client refusal with no remote payload echo."""


def _ref(value: object, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > _MAX_REF_BYTES
        or any(ord(ch) < 32 for ch in value)
    ):
        raise WorkbenchBrowserClientError(f"{field.upper()}_INVALID")
    return value


def _arguments(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise WorkbenchBrowserClientError("ARGUMENTS_INVALID")
    import json

    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise WorkbenchBrowserClientError("ARGUMENTS_INVALID") from exc
    if len(raw) > _MAX_ARGUMENT_BYTES:
        raise WorkbenchBrowserClientError("ARGUMENTS_INVALID")
    return dict(value)


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class WorkbenchBrowserMcpEffectPort:
    """Use one already-authenticated Workbench Browser MCP connection."""

    def __init__(
        self,
        *,
        call_tool: Callable[[str, dict[str, Any]], Awaitable[Any] | Any],
    ) -> None:
        if not callable(call_tool):
            raise TypeError("existing Workbench Browser MCP caller is required")
        self._call_tool = call_tool

    async def _call(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        effectful: bool,
    ) -> dict[str, Any]:
        try:
            value = await _maybe(self._call_tool(name, arguments))
        except Exception as exc:
            raise WorkbenchBrowserClientError(
                "TRANSPORT_UNCERTAIN" if effectful else "TRANSPORT_UNAVAILABLE"
            ) from exc
        if not isinstance(value, Mapping):
            raise WorkbenchBrowserClientError("REMOTE_RESULT_INVALID")
        result = dict(value)
        if type(result.get("isError")) is not bool:
            raise WorkbenchBrowserClientError("REMOTE_RESULT_INVALID")
        content = result.get("content")
        structured = result.get("structuredContent")
        if not isinstance(content, list) or not isinstance(structured, Mapping):
            raise WorkbenchBrowserClientError("REMOTE_RESULT_INVALID")
        if result["isError"]:
            raise WorkbenchBrowserClientError(
                "REMOTE_EFFECT_UNCERTAIN" if effectful else "REMOTE_REFUSED"
            )
        result["structuredContent"] = dict(structured)
        return result

    async def call_read_tool(
        self,
        caller: Any,
        browser_ref: str,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        # caller is deliberately not serialized; authentication is already
        # bound to the injected MCP connection by its route owner.
        del caller
        if type(tool) is not str or tool not in _READ_TOOLS:
            raise WorkbenchBrowserClientError("TOOL_NOT_ALLOWED")
        selected = _arguments(dict(arguments) if isinstance(arguments, Mapping) else arguments)
        if "browser_ref" in selected:
            raise WorkbenchBrowserClientError("ARGUMENTS_INVALID")
        return await self._call(
            tool,
            {"browser_ref": _ref(browser_ref, "browser_ref"), **selected},
            effectful=False,
        )

    async def prepare_action(
        self,
        caller: Any,
        browser_ref: str,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> str:
        del caller
        if type(tool) is not str or tool not in _ACTION_TOOLS:
            raise WorkbenchBrowserClientError("TOOL_NOT_ALLOWED")
        selected = _arguments(dict(arguments) if isinstance(arguments, Mapping) else arguments)
        if "browser_ref" in selected:
            raise WorkbenchBrowserClientError("ARGUMENTS_INVALID")
        result = await self._call(
            "prepare_" + tool,
            {"browser_ref": _ref(browser_ref, "browser_ref"), **selected},
            effectful=False,
        )
        structured = result["structuredContent"]
        action_ref = structured.get("action_ref")
        if type(action_ref) is not str or not action_ref:
            raise WorkbenchBrowserClientError("REMOTE_RESULT_INVALID")
        return _ref(action_ref, "action_ref")

    async def run_action(
        self,
        caller: Any,
        browser_ref: str,
        action_ref: str,
    ) -> Mapping[str, Any]:
        del caller
        result = await self._call(
            "run_browser_action",
            {
                "browser_ref": _ref(browser_ref, "browser_ref"),
                "action_ref": _ref(action_ref, "action_ref"),
            },
            effectful=True,
        )
        receipt = dict(result["structuredContent"])
        if receipt.get("effect_state") not in _EFFECTS:
            raise WorkbenchBrowserClientError("REMOTE_RESULT_INVALID")
        return receipt

    async def reconcile_action(
        self,
        caller: Any,
        browser_ref: str,
        action_ref: str,
    ) -> Mapping[str, Any]:
        del caller
        result = await self._call(
            "reconcile_browser_action",
            {
                "browser_ref": _ref(browser_ref, "browser_ref"),
                "action_ref": _ref(action_ref, "action_ref"),
            },
            effectful=False,
        )
        receipt = dict(result["structuredContent"])
        if receipt.get("effect_state") not in _EFFECTS:
            raise WorkbenchBrowserClientError("REMOTE_RESULT_INVALID")
        return receipt


__all__ = [
    "WorkbenchBrowserClientError",
    "WorkbenchBrowserMcpEffectPort",
]
