"""Compose the seven-tool Browser owner over one existing Workbench deployment.

The Workbench deployment remains the browser resource/effect owner. This module
adds no browser lifecycle, registry, scheduler, retry loop, transport, or auth
plane. One internal Workbench caller owns pooled resources while outer Browser
callers are isolated by signed session/tab/action references.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable, Mapping

from control_plane.browser_resource_contract import (
    WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
)
from integrations.workbench_action_mcp.contracts import ActionCaller

from .catalog import SCHEMA_DIGEST
from .composition import BrowserOwnerComposition, compose_browser_owner
from .workbench_inventory import WorkbenchDeploymentInventoryProjection


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class WorkbenchDeploymentEffectPort:
    """Thin effect adapter that always uses the fixed internal broker caller."""

    def __init__(self, *, deployment: Any, broker_caller: ActionCaller) -> None:
        for name in ("read_tool", "prepare_action", "run_action", "reconcile_action"):
            if not callable(getattr(deployment, name, None)):
                raise TypeError("complete Workbench Browser deployment is required")
        if type(broker_caller) is not ActionCaller:
            raise TypeError("exact Workbench broker caller is required")
        self._deployment = deployment
        self._broker_caller = broker_caller

    async def call_read_tool(
        self,
        _outer_caller: Any,
        browser_ref: str,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        value = await _maybe(
            self._deployment.read_tool(
                self._broker_caller,
                browser_ref,
                tool,
                dict(arguments),
            )
        )
        if not isinstance(value, Mapping):
            raise ValueError("Workbench browser read result is invalid")
        return dict(value)

    async def prepare_action(
        self,
        _outer_caller: Any,
        browser_ref: str,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> str:
        value = await _maybe(
            self._deployment.prepare_action(
                self._broker_caller,
                browser_ref,
                tool,
                dict(arguments),
            )
        )
        if type(value) is not str or not value:
            raise ValueError("Workbench action reference is invalid")
        return value

    async def run_action(
        self,
        _outer_caller: Any,
        browser_ref: str,
        action_ref: str,
    ) -> Mapping[str, Any]:
        value = await _maybe(
            self._deployment.run_action(
                self._broker_caller,
                browser_ref,
                action_ref,
            )
        )
        if not isinstance(value, Mapping):
            raise ValueError("Workbench action receipt is invalid")
        return dict(value)

    async def reconcile_action(
        self,
        _outer_caller: Any,
        browser_ref: str,
        action_ref: str,
    ) -> Mapping[str, Any]:
        value = await _maybe(
            self._deployment.reconcile_action(
                self._broker_caller,
                browser_ref,
                action_ref,
            )
        )
        if not isinstance(value, Mapping):
            raise ValueError("Workbench reconciliation receipt is invalid")
        return dict(value)


def compose_browser_owner_from_workbench(
    *,
    deployment: Any,
    signing_key: bytes,
    clock_ms: Callable[[], int],
    caller_binding: Callable[[Any], Any],
    broker_caller: ActionCaller,
    expected_catalog_schema_digest: str = SCHEMA_DIGEST,
    expected_backend_schema_digest: str = WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
) -> BrowserOwnerComposition:
    """Join one Workbench deployment to the external Browser owner surface."""

    projection = WorkbenchDeploymentInventoryProjection(
        deployment=deployment,
        broker_caller=broker_caller,
        clock_ms=clock_ms,
    )
    effect_port = WorkbenchDeploymentEffectPort(
        deployment=deployment,
        broker_caller=broker_caller,
    )
    return compose_browser_owner(
        signing_key=signing_key,
        clock_ms=clock_ms,
        caller_binding=caller_binding,
        resource_reader=projection.resource_reader,
        tab_reader=projection.tab_reader,
        managed_effect_port=effect_port,
        shared_effect_port=effect_port,
        shared_broker_caller=broker_caller,
        managed_broker_caller=broker_caller,
        expected_catalog_schema_digest=expected_catalog_schema_digest,
        managed_backend_schema_digest=expected_backend_schema_digest,
        shared_backend_schema_digest=expected_backend_schema_digest,
    )


__all__ = [
    "WorkbenchDeploymentEffectPort",
    "compose_browser_owner_from_workbench",
]
