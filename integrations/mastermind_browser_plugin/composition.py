"""Pure composition for the single Mastermind Browser owner surface.

The composition joins existing owner callbacks and effect ports. It creates no
browser, process, lease, registry, scheduler, listener, tunnel, auth grant,
retry loop, or persisted state. Transport composition remains separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .inventory_owner import BrowserInventoryOwner
from .owner_adapter import (
    ExistingBrowserEffectPort,
    ManagedBrowserOwnerAdapter,
    SharedHumanBrowserOwnerAdapter,
    WorkbenchManagedProjector,
)
from .owner_router import BrowserOwnerRouter
from .tab_ref import BrowserTabRefCodec


@dataclass(frozen=True, slots=True)
class BrowserOwnerComposition:
    """One transport-independent Browser owner projection."""

    codec: BrowserTabRefCodec
    inventory: BrowserInventoryOwner
    managed_owner: ManagedBrowserOwnerAdapter
    shared_owner: SharedHumanBrowserOwnerAdapter
    router: BrowserOwnerRouter

    @property
    def owner(self) -> BrowserOwnerRouter:
        return self.router


def compose_browser_owner(
    *,
    signing_key: bytes,
    clock_ms: Callable[[], int],
    caller_binding: Callable[[Any], Any],
    resource_reader: Callable[..., Any],
    tab_reader: Callable[..., Any],
    managed_effect_port: ExistingBrowserEffectPort,
    shared_effect_port: ExistingBrowserEffectPort,
    shared_broker_caller: Any,
    expected_catalog_schema_digest: str,
    managed_backend_schema_digest: str,
    shared_backend_schema_digest: str,
) -> BrowserOwnerComposition:
    """Join already-owned Browser seams without adding another control plane."""

    if type(signing_key) is not bytes or len(signing_key) < 32:
        raise TypeError("Browser signing key is invalid")
    if shared_broker_caller is None:
        raise TypeError("shared Browser broker caller is required")

    codec = BrowserTabRefCodec(signing_key)
    inventory = BrowserInventoryOwner(
        codec=codec,
        clock_ms=clock_ms,
        caller_binding=caller_binding,
        resource_reader=resource_reader,
        tab_reader=tab_reader,
        expected_catalog_schema_digest=expected_catalog_schema_digest,
    )
    projector = WorkbenchManagedProjector()
    managed = ManagedBrowserOwnerAdapter(
        codec=codec,
        clock_ms=clock_ms,
        caller_binding=caller_binding,
        revalidate_tab=inventory.revalidate_tab,
        effect_port=managed_effect_port,
        projector=projector,
        fleet_reader=inventory.browser_fleet,
        tabs_reader=inventory.browser_tabs,
        expected_catalog_schema_digest=expected_catalog_schema_digest,
        expected_backend_schema_digest=managed_backend_schema_digest,
    )
    shared = SharedHumanBrowserOwnerAdapter(
        broker_caller=shared_broker_caller,
        codec=codec,
        clock_ms=clock_ms,
        caller_binding=caller_binding,
        revalidate_tab=inventory.revalidate_tab,
        effect_port=shared_effect_port,
        projector=projector,
        fleet_reader=inventory.browser_fleet,
        tabs_reader=inventory.browser_tabs,
        expected_catalog_schema_digest=expected_catalog_schema_digest,
        expected_backend_schema_digest=shared_backend_schema_digest,
    )
    router = BrowserOwnerRouter(
        codec=codec,
        clock_ms=clock_ms,
        caller_binding=caller_binding,
        inventory_owner=inventory,
        managed_owner=managed,
        shared_owner=shared,
    )
    return BrowserOwnerComposition(
        codec=codec,
        inventory=inventory,
        managed_owner=managed,
        shared_owner=shared,
        router=router,
    )


__all__ = [
    "BrowserOwnerComposition",
    "compose_browser_owner",
]
