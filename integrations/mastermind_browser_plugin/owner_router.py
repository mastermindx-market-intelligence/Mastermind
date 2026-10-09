"""Stateless backend router for the single Mastermind Browser service.

The router owns no browser inventory, grant, action reference, effect receipt,
process, retry, placement, or lifecycle. It validates the caller-bound signed
TabRef only far enough to select its already-owned backend, then delegates the
whole operation to that backend. Inventory remains with an injected existing
owner. Expired tab refs are accepted only to route reconciliation.
"""
from __future__ import annotations

import inspect
from typing import Any, Protocol

from .facade import OwnerRefused
from .owner_adapter import BrowserCallerBinding
from .tab_ref import (
    BrowserTabRefCodec,
    BrowserTabRefError,
    TabBackend,
)


class BrowserInventoryPort(Protocol):
    async def browser_fleet(self, caller: Any, args: dict) -> dict: ...
    async def browser_tabs(self, caller: Any, args: dict) -> dict: ...


class BrowserTabBackendPort(Protocol):
    async def browser_snapshot(self, caller: Any, args: dict) -> dict: ...
    async def browser_screenshot(self, caller: Any, args: dict) -> dict: ...
    async def prepare_browser_action(self, caller: Any, args: dict) -> dict: ...
    async def run_browser_action(self, caller: Any, args: dict) -> dict: ...
    async def reconcile_browser_action(self, caller: Any, args: dict) -> dict: ...


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class BrowserOwnerRouter:
    """Route one signed tab to its managed or shared-human owner."""

    def __init__(
        self,
        *,
        codec: BrowserTabRefCodec,
        clock_ms,
        caller_binding,
        inventory_owner: BrowserInventoryPort,
        managed_owner: BrowserTabBackendPort,
        shared_owner: BrowserTabBackendPort,
    ) -> None:
        if type(codec) is not BrowserTabRefCodec:
            raise TypeError("signed tab codec is required")
        if not callable(clock_ms) or not callable(caller_binding):
            raise TypeError("router callbacks are required")
        for owner, methods in (
            (inventory_owner, ("browser_fleet", "browser_tabs")),
            (
                managed_owner,
                (
                    "browser_snapshot",
                    "browser_screenshot",
                    "prepare_browser_action",
                    "run_browser_action",
                    "reconcile_browser_action",
                ),
            ),
            (
                shared_owner,
                (
                    "browser_snapshot",
                    "browser_screenshot",
                    "prepare_browser_action",
                    "run_browser_action",
                    "reconcile_browser_action",
                ),
            ),
        ):
            if any(not callable(getattr(owner, method, None)) for method in methods):
                raise TypeError("existing Browser owner port is required")
        self._codec = codec
        self._clock_ms = clock_ms
        self._caller_binding = caller_binding
        self._inventory = inventory_owner
        self._managed = managed_owner
        self._shared = shared_owner

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

    async def _tab_owner(
        self,
        caller: Any,
        tab_ref: object,
        *,
        require_fresh: bool,
    ) -> BrowserTabBackendPort:
        binding = await self._caller(caller)
        try:
            tab = self._codec.decode(
                tab_ref,
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
        if tab.backend == TabBackend.MANAGED.value:
            return self._managed
        if tab.backend == TabBackend.SHARED_HUMAN.value:
            return self._shared
        raise OwnerRefused("BACKEND_MISMATCH")

    @staticmethod
    def _args(value: object) -> dict:
        if type(value) is not dict:
            raise OwnerRefused("INVALID_ARGUMENTS")
        return value

    async def browser_fleet(self, caller: Any, args: dict) -> dict:
        await self._caller(caller)
        selected = self._args(args)
        return await _maybe(self._inventory.browser_fleet(caller, selected))

    async def browser_tabs(self, caller: Any, args: dict) -> dict:
        await self._caller(caller)
        selected = self._args(args)
        return await _maybe(self._inventory.browser_tabs(caller, selected))

    async def _route(
        self,
        method: str,
        caller: Any,
        args: dict,
        *,
        require_fresh: bool,
    ) -> dict:
        selected = self._args(args)
        owner = await self._tab_owner(
            caller,
            selected.get("tab_ref"),
            require_fresh=require_fresh,
        )
        return await _maybe(getattr(owner, method)(caller, selected))

    async def browser_snapshot(self, caller: Any, args: dict) -> dict:
        return await self._route(
            "browser_snapshot", caller, args, require_fresh=True
        )

    async def browser_screenshot(self, caller: Any, args: dict) -> dict:
        return await self._route(
            "browser_screenshot", caller, args, require_fresh=True
        )

    async def prepare_browser_action(self, caller: Any, args: dict) -> dict:
        return await self._route(
            "prepare_browser_action", caller, args, require_fresh=True
        )

    async def run_browser_action(self, caller: Any, args: dict) -> dict:
        return await self._route(
            "run_browser_action", caller, args, require_fresh=True
        )

    async def reconcile_browser_action(self, caller: Any, args: dict) -> dict:
        return await self._route(
            "reconcile_browser_action", caller, args, require_fresh=False
        )


class HostRoutedBrowserOwnerRouter(BrowserOwnerRouter):
    """Resolve the already-owned backend from each caller-bound signed tab.

    The resolver is an injected owner seam. This class stores no host table,
    endpoint map, placement preference, lease, browser registry, or retry state.
    """

    def __init__(
        self,
        *,
        codec: BrowserTabRefCodec,
        clock_ms,
        caller_binding,
        inventory_owner: BrowserInventoryPort,
        owner_resolver,
    ) -> None:
        if type(codec) is not BrowserTabRefCodec:
            raise TypeError("signed tab codec is required")
        if (
            not callable(clock_ms)
            or not callable(caller_binding)
            or not callable(owner_resolver)
        ):
            raise TypeError("router callbacks are required")
        if any(
            not callable(getattr(inventory_owner, method, None))
            for method in ("browser_fleet", "browser_tabs")
        ):
            raise TypeError("existing Browser inventory port is required")
        self._codec = codec
        self._clock_ms = clock_ms
        self._caller_binding = caller_binding
        self._inventory = inventory_owner
        self._owner_resolver = owner_resolver

    @staticmethod
    def _validate_backend_owner(owner: Any) -> BrowserTabBackendPort:
        methods = (
            "browser_snapshot",
            "browser_screenshot",
            "prepare_browser_action",
            "run_browser_action",
            "reconcile_browser_action",
        )
        if any(not callable(getattr(owner, method, None)) for method in methods):
            raise OwnerRefused("BACKEND_ROUTE_UNAVAILABLE")
        return owner

    async def _tab_owner(
        self,
        caller: Any,
        tab_ref: object,
        *,
        require_fresh: bool,
    ) -> BrowserTabBackendPort:
        binding = await self._caller(caller)
        try:
            tab = self._codec.decode(
                tab_ref,
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
        try:
            owner = self._owner_resolver(caller, tab)
            owner = await _maybe(owner)
        except OwnerRefused:
            raise
        except Exception as exc:
            raise OwnerRefused("BACKEND_ROUTE_UNAVAILABLE") from exc
        return self._validate_backend_owner(owner)


__all__ = [
    "BrowserInventoryPort",
    "BrowserOwnerRouter",
    "BrowserTabBackendPort",
    "HostRoutedBrowserOwnerRouter",
]
