from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from integrations.mastermind_browser_plugin.catalog import SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.facade import OwnerRefused
from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.owner_router import HostRoutedBrowserOwnerRouter
from integrations.mastermind_browser_plugin.tab_ref import (
    BrowserTabRef,
    BrowserTabRefCodec,
    TAB_REF_SCHEMA,
    TabBackend,
)

NOW = 1_800_000_000_000
KEY = b"h" * 32
BACKEND_DIGEST = "e" * 64


@dataclass(frozen=True)
class Caller:
    subject_digest: str = "b" * 64
    client_ref: str = "client-a"
    resource: str = "browser-resource"


def caller_binding(caller):
    return BrowserCallerBinding(
        subject_digest=caller.subject_digest,
        client_ref=caller.client_ref,
        resource=caller.resource,
    )


def token(host, instance, generation, backend=TabBackend.MANAGED):
    value = BrowserTabRef(
        schema=TAB_REF_SCHEMA,
        backend=backend.value,
        browser_ref="browser-resource-" + host[-1] * 64,
        subject_digest="b" * 64,
        client_ref="client-a",
        resource="browser-resource",
        host_ref=host,
        boot_ref="boot-" + host[-1],
        profile_ref="profile-" + host[-1],
        browser_instance_ref=instance,
        connection_generation=generation,
        tab_locator=1,
        document_revision=1,
        consent_ref="consent-a" if backend is TabBackend.SHARED_HUMAN else None,
        allowed_actions=("click", "snapshot"),
        catalog_schema_digest=SCHEMA_DIGEST,
        backend_schema_digest=BACKEND_DIGEST,
        issued_at_ms=NOW,
        expires_at_ms=NOW + 60_000,
    )
    return BrowserTabRefCodec(KEY).encode(value)


class Backend:
    def __init__(self, label):
        self.label = label
        self.calls = []

    async def browser_snapshot(self, caller, args):
        self.calls.append(("snapshot", caller, dict(args)))
        return {"backend": self.label}

    async def browser_screenshot(self, caller, args):
        return {"backend": self.label}

    async def prepare_browser_action(self, caller, args):
        return {"action_ref": self.label + ":prepared"}

    async def run_browser_action(self, caller, args):
        return {"effect": "APPLIED", "backend": self.label}

    async def reconcile_browser_action(self, caller, args):
        return {"effect": "EFFECT_UNKNOWN", "backend": self.label}


class Inventory:
    async def browser_fleet(self, _caller, _args):
        return {"browsers": []}

    async def browser_tabs(self, _caller, _args):
        return {"tabs": []}


def make_router(*, now=NOW):
    a, b = Backend("m2"), Backend("mini1")
    calls = []

    def resolve(caller, tab):
        calls.append(
            (
                caller,
                tab.backend,
                tab.host_ref,
                tab.browser_instance_ref,
                tab.connection_generation,
            )
        )
        if tab.host_ref == "host-a":
            return a
        if tab.host_ref == "host-b":
            return b
        raise OwnerRefused("BACKEND_ROUTE_UNAVAILABLE")

    router = HostRoutedBrowserOwnerRouter(
        codec=BrowserTabRefCodec(KEY),
        clock_ms=lambda: now,
        caller_binding=caller_binding,
        inventory_owner=Inventory(),
        owner_resolver=resolve,
    )
    return router, a, b, calls


def test_two_managed_hosts_route_to_two_existing_owners_without_local_map():
    router, a, b, calls = make_router()
    result_a = asyncio.run(
        router.browser_snapshot(
            Caller(), {"tab_ref": token("host-a", "browser-a", "generation-a")}
        )
    )
    result_b = asyncio.run(
        router.browser_snapshot(
            Caller(), {"tab_ref": token("host-b", "browser-b", "generation-b")}
        )
    )
    assert result_a["backend"] == "m2"
    assert result_b["backend"] == "mini1"
    assert len(a.calls) == len(b.calls) == 1
    assert [row[2] for row in calls] == ["host-a", "host-b"]
    assert "_routes" not in vars(router)
    assert "_hosts" not in vars(router)


def test_route_resolver_receives_bound_tab_only_after_caller_validation():
    router, a, b, calls = make_router()
    with pytest.raises(OwnerRefused, match="CALLER_BINDING_CHANGED"):
        asyncio.run(
            router.browser_snapshot(
                Caller(client_ref="client-b"),
                {"tab_ref": token("host-a", "browser-a", "generation-a")},
            )
        )
    assert calls == []
    assert a.calls == b.calls == []


def test_resolver_refusal_does_not_fall_back_to_another_host():
    router, a, b, calls = make_router()
    with pytest.raises(OwnerRefused, match="BACKEND_ROUTE_UNAVAILABLE"):
        asyncio.run(
            router.browser_snapshot(
                Caller(),
                {"tab_ref": token("host-c", "browser-c", "generation-c")},
            )
        )
    assert len(calls) == 1
    assert a.calls == b.calls == []


def test_reconciliation_can_route_expired_tab_to_original_host():
    router, _, b, calls = make_router(now=NOW + 60_000)
    ref = token("host-b", "browser-b", "generation-b")
    with pytest.raises(OwnerRefused, match="TAB_REF_EXPIRED"):
        asyncio.run(
            router.run_browser_action(
                Caller(), {"tab_ref": ref, "action_ref": "outer"}
            )
        )
    result = asyncio.run(
        router.reconcile_browser_action(
            Caller(), {"tab_ref": ref, "action_ref": "outer"}
        )
    )
    assert result["effect"] == "EFFECT_UNKNOWN"
    assert result["backend"] == "mini1"
    assert calls[-1][2:] == (
        "host-b",
        "browser-b",
        "generation-b",
    )
    assert b.calls == []  # reconcile fixture method does not record


def test_backend_kind_remains_part_of_route_identity():
    router, _, _, calls = make_router()
    ref = token(
        "host-a",
        "browser-a",
        "generation-a",
        backend=TabBackend.SHARED_HUMAN,
    )
    asyncio.run(router.browser_snapshot(Caller(), {"tab_ref": ref}))
    assert calls[0][1] == "shared_human"


def test_constructor_requires_exact_resolver_and_inventory_port():
    with pytest.raises(TypeError):
        HostRoutedBrowserOwnerRouter(
            codec=BrowserTabRefCodec(KEY),
            clock_ms=lambda: NOW,
            caller_binding=caller_binding,
            inventory_owner=Inventory(),
            owner_resolver=None,
        )
