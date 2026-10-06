"""Managed-browser adapter from the seven-tool Browser service to an existing effect owner.

The adapter owns no browser registry, action store, retry loop, scheduler, lease,
process, or transport. It validates one signed Mastermind tab reference, asks an
injected owner to revalidate the live tab generation before live use, projects
high-level Browser actions into an injected backend tool call, and delegates
read/prepare/run/reconcile to the existing durable Browser effect owner.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import inspect
import json
import re
from typing import Any, Protocol

from .facade import OwnerRefused
from .tab_ref import (
    BrowserTabRef,
    BrowserTabRefCodec,
    BrowserTabRefError,
    HIGH_LEVEL_ACTIONS,
    TabBackend,
)

_EFFECTS = frozenset({"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_MAX_ARGUMENT_BYTES = 65_536


@dataclass(frozen=True, slots=True)
class BrowserCallerBinding:
    subject_digest: str
    client_ref: str
    resource: str

    def __post_init__(self) -> None:
        if type(self.subject_digest) is not str or _HEX64.fullmatch(self.subject_digest) is None:
            raise ValueError("caller subject is invalid")
        for value in (self.client_ref, self.resource):
            if type(value) is not str or _TOKEN.fullmatch(value) is None:
                raise ValueError("caller reference is invalid")


@dataclass(frozen=True, slots=True)
class OwnerToolCall:
    tool_name: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        if type(self.tool_name) is not str or _TOOL.fullmatch(self.tool_name) is None:
            raise ValueError("owner tool is invalid")
        if not isinstance(self.arguments, Mapping):
            raise ValueError("owner arguments are invalid")
        try:
            raw = json.dumps(
                dict(self.arguments),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise ValueError("owner arguments are invalid") from exc
        if len(raw) > _MAX_ARGUMENT_BYTES:
            raise ValueError("owner arguments are oversized")


class ExistingBrowserEffectPort(Protocol):
    def call_read_tool(
        self, caller: Any, browser_ref: str, tool: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def prepare_action(
        self, caller: Any, browser_ref: str, tool: str, arguments: Mapping[str, Any]
    ) -> str: ...

    def run_action(
        self, caller: Any, browser_ref: str, action_ref: str
    ) -> Mapping[str, Any]: ...

    def reconcile_action(
        self, caller: Any, browser_ref: str, action_ref: str
    ) -> Mapping[str, Any]: ...


class ManagedToolProjector(Protocol):
    def project_read(
        self, tab: BrowserTabRef, action: str, arguments: Mapping[str, Any]
    ) -> OwnerToolCall: ...

    def project_action(
        self, tab: BrowserTabRef, action: str, arguments: Mapping[str, Any]
    ) -> OwnerToolCall: ...


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class ManagedBrowserOwnerAdapter:
    """One stateless managed-browser owner projection.

    Production composition should inject the existing Workbench/Runtime browser
    effect port (or an equivalent accepted successor) plus its backend-specific
    tool projector. The projector is not an authority boundary: the effect port
    still enforces its own grant and action-reference contract.
    """

    def __init__(
        self,
        *,
        codec: BrowserTabRefCodec,
        clock_ms: Callable[[], int],
        caller_binding: Callable[[Any], BrowserCallerBinding],
        revalidate_tab: Callable[[Any, BrowserTabRef], bool],
        effect_port: ExistingBrowserEffectPort,
        projector: ManagedToolProjector,
        fleet_reader: Callable[[Any, Mapping[str, Any]], Mapping[str, Any]],
        tabs_reader: Callable[[Any, Mapping[str, Any]], Mapping[str, Any]],
        expected_catalog_schema_digest: str,
        expected_backend_schema_digest: str,
    ) -> None:
        if type(codec) is not BrowserTabRefCodec:
            raise TypeError("signed tab codec is required")
        if not all(
            callable(value)
            for value in (
                clock_ms,
                caller_binding,
                revalidate_tab,
                fleet_reader,
                tabs_reader,
            )
        ):
            raise TypeError("existing Browser owner callbacks are required")
        for method in ("call_read_tool", "prepare_action", "run_action", "reconcile_action"):
            if not callable(getattr(effect_port, method, None)):
                raise TypeError("existing Browser effect port is required")
        for method in ("project_read", "project_action"):
            if not callable(getattr(projector, method, None)):
                raise TypeError("managed Browser projector is required")
        for digest in (expected_catalog_schema_digest, expected_backend_schema_digest):
            if type(digest) is not str or _HEX64.fullmatch(digest) is None:
                raise TypeError("schema digest is invalid")

        self._codec = codec
        self._clock_ms = clock_ms
        self._caller_binding = caller_binding
        self._revalidate_tab = revalidate_tab
        self._effect_port = effect_port
        self._projector = projector
        self._fleet_reader = fleet_reader
        self._tabs_reader = tabs_reader
        self._catalog_digest = expected_catalog_schema_digest
        self._backend_digest = expected_backend_schema_digest

    def _now(self) -> int:
        value = self._clock_ms()
        if type(value) is not int or value < 0 or value >= 2**63:
            raise OwnerRefused("CLOCK_UNAVAILABLE")
        return value

    async def _caller(self, caller: Any) -> BrowserCallerBinding:
        try:
            binding = await _maybe(self._caller_binding(caller))
        except OwnerRefused:
            raise
        except Exception as exc:
            raise OwnerRefused("CALLER_BINDING_CHANGED") from exc
        if type(binding) is not BrowserCallerBinding:
            raise OwnerRefused("CALLER_BINDING_CHANGED")
        return binding

    async def _decode_tab(
        self,
        caller: Any,
        token: object,
        *,
        action: str | None = None,
        require_fresh: bool,
        require_current: bool,
    ) -> BrowserTabRef:
        binding = await self._caller(caller)
        try:
            tab = self._codec.decode(
                token,
                now_ms=self._now(),
                require_fresh=require_fresh,
            )
        except BrowserTabRefError as exc:
            raise OwnerRefused(str(exc)) from exc

        if (
            tab.subject_digest != binding.subject_digest
            or tab.client_ref != binding.client_ref
            or tab.resource != binding.resource
        ):
            raise OwnerRefused("CALLER_BINDING_CHANGED")
        if tab.backend != TabBackend.MANAGED.value:
            raise OwnerRefused("BACKEND_MISMATCH")
        if require_current:
            if tab.catalog_schema_digest != self._catalog_digest:
                raise OwnerRefused("CATALOG_SCHEMA_CHANGED")
            if tab.backend_schema_digest != self._backend_digest:
                raise OwnerRefused("BACKEND_SCHEMA_CHANGED")
        if action is not None:
            if action not in HIGH_LEVEL_ACTIONS or action not in tab.allowed_actions:
                raise OwnerRefused("ACTION_NOT_GRANTED")
        if require_current:
            try:
                current = await _maybe(self._revalidate_tab(caller, tab))
            except OwnerRefused:
                raise
            except Exception as exc:
                raise OwnerRefused("TAB_BINDING_CHANGED") from exc
            if current is not True:
                raise OwnerRefused("TAB_BINDING_CHANGED")
        return tab

    @staticmethod
    def _tool_call(value: Any) -> OwnerToolCall:
        if type(value) is not OwnerToolCall:
            raise OwnerRefused("BACKEND_PROJECTION_INVALID")
        try:
            value.__post_init__()
        except ValueError as exc:
            raise OwnerRefused("BACKEND_PROJECTION_INVALID") from exc
        return value

    @staticmethod
    def _receipt(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError("effect owner receipt is invalid")
        result = dict(value)
        if "effect" in result:
            raise ValueError("effect owner receipt uses the wrong effect field")
        effect = result.pop("effect_state", None)
        if effect not in _EFFECTS:
            raise ValueError("effect owner receipt lacks a valid effect state")
        result["effect"] = effect
        return result

    async def browser_fleet(self, caller: Any, args: dict) -> dict:
        await self._caller(caller)
        value = await _maybe(self._fleet_reader(caller, dict(args)))
        if not isinstance(value, Mapping):
            raise ValueError("fleet reader returned invalid data")
        return dict(value)

    async def browser_tabs(self, caller: Any, args: dict) -> dict:
        await self._caller(caller)
        value = await _maybe(self._tabs_reader(caller, dict(args)))
        if not isinstance(value, Mapping):
            raise ValueError("tabs reader returned invalid data")
        return dict(value)

    async def browser_snapshot(self, caller: Any, args: dict) -> dict:
        return await self._read(caller, args, "snapshot")

    async def browser_screenshot(self, caller: Any, args: dict) -> dict:
        return await self._read(caller, args, "screenshot")

    async def _read(self, caller: Any, args: dict, action: str) -> dict:
        tab = await self._decode_tab(
            caller,
            args["tab_ref"],
            action=action,
            require_fresh=True,
            require_current=True,
        )
        projected = self._tool_call(
            await _maybe(self._projector.project_read(tab, action, {}))
        )
        value = await _maybe(
            self._effect_port.call_read_tool(
                caller,
                tab.browser_ref,
                projected.tool_name,
                dict(projected.arguments),
            )
        )
        if not isinstance(value, Mapping):
            raise ValueError("effect owner read result is invalid")
        return dict(value)

    async def prepare_browser_action(self, caller: Any, args: dict) -> dict:
        action = args["action"]
        tab = await self._decode_tab(
            caller,
            args["tab_ref"],
            action=action,
            require_fresh=True,
            require_current=True,
        )
        projected = self._tool_call(
            await _maybe(
                self._projector.project_action(tab, action, dict(args["args"]))
            )
        )
        action_ref = await _maybe(
            self._effect_port.prepare_action(
                caller,
                tab.browser_ref,
                projected.tool_name,
                dict(projected.arguments),
            )
        )
        if type(action_ref) is not str or not action_ref:
            raise ValueError("effect owner action reference is invalid")
        return {"action_ref": action_ref}

    async def run_browser_action(self, caller: Any, args: dict) -> dict:
        tab = await self._decode_tab(
            caller,
            args["tab_ref"],
            require_fresh=True,
            require_current=True,
        )
        value = await _maybe(
            self._effect_port.run_action(
                caller,
                tab.browser_ref,
                args["action_ref"],
            )
        )
        return self._receipt(value)

    async def reconcile_browser_action(self, caller: Any, args: dict) -> dict:
        tab = await self._decode_tab(
            caller,
            args["tab_ref"],
            require_fresh=False,
            require_current=False,
        )
        value = await _maybe(
            self._effect_port.reconcile_action(
                caller,
                tab.browser_ref,
                args["action_ref"],
            )
        )
        return self._receipt(value)


__all__ = [
    "BrowserCallerBinding",
    "ExistingBrowserEffectPort",
    "ManagedBrowserOwnerAdapter",
    "ManagedToolProjector",
    "OwnerToolCall",
]
