from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from integrations.mastermind_browser_plugin.catalog import SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.facade import BrowserFacade, OwnerRefused
from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.owner_router import BrowserOwnerRouter
from integrations.mastermind_browser_plugin.tab_ref import (
    BrowserTabRef,
    BrowserTabRefCodec,
    TAB_REF_SCHEMA,
    TabBackend,
)

NOW = 1_800_000_000_000
KEY = b"r" * 32
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


def tab(backend: TabBackend, **changes):
    values = dict(
        schema=TAB_REF_SCHEMA,
        backend=backend.value,
        browser_ref="browser-resource-" + "a" * 64,
        subject_digest="b" * 64,
        client_ref="client-a",
        resource="browser-resource",
        host_ref="host-a",
        boot_ref="boot-a",
        profile_ref="profile-a",
        browser_instance_ref="browser-a",
        connection_generation="generation-a",
        tab_locator=7,
        document_revision=3,
        consent_ref="consent-a" if backend is TabBackend.SHARED_HUMAN else None,
        allowed_actions=("click", "navigate", "screenshot", "snapshot", "type"),
        catalog_schema_digest=SCHEMA_DIGEST,
        backend_schema_digest=BACKEND_DIGEST,
        issued_at_ms=NOW,
        expires_at_ms=NOW + 60_000,
    )
    values.update(changes)
    return BrowserTabRef(**values)


def token(backend: TabBackend, **changes):
    return BrowserTabRefCodec(KEY).encode(tab(backend, **changes))


class Backend:
    def __init__(self, label):
        self.label = label
        self.calls = []

    async def browser_snapshot(self, caller, args):
        self.calls.append(("snapshot", caller, dict(args)))
        return {"backend": self.label, "kind": "snapshot"}

    async def browser_screenshot(self, caller, args):
        self.calls.append(("screenshot", caller, dict(args)))
        return {"backend": self.label, "kind": "screenshot"}

    async def prepare_browser_action(self, caller, args):
        self.calls.append(("prepare", caller, dict(args)))
        return {"action_ref": self.label + ":prepared"}

    async def run_browser_action(self, caller, args):
        self.calls.append(("run", caller, dict(args)))
        return {"effect": "APPLIED", "backend": self.label}

    async def reconcile_browser_action(self, caller, args):
        self.calls.append(("reconcile", caller, dict(args)))
        return {"effect": "EFFECT_UNKNOWN", "backend": self.label}


class Inventory:
    def __init__(self):
        self.calls = []

    async def browser_fleet(self, caller, args):
        self.calls.append(("fleet", caller, dict(args)))
        return {"browsers": ["managed-a", "shared-a"]}

    async def browser_tabs(self, caller, args):
        self.calls.append(("tabs", caller, dict(args)))
        return {"tabs": ["tab-a"]}


def make_router(*, now=NOW):
    managed = Backend("managed")
    shared = Backend("shared")
    inventory = Inventory()
    router = BrowserOwnerRouter(
        codec=BrowserTabRefCodec(KEY),
        clock_ms=lambda: now,
        caller_binding=caller_binding,
        inventory_owner=inventory,
        managed_owner=managed,
        shared_owner=shared,
    )
    return router, managed, shared, inventory


@pytest.mark.parametrize(
    "backend,label",
    [(TabBackend.MANAGED, "managed"), (TabBackend.SHARED_HUMAN, "shared")],
)
def test_same_seven_tool_owner_routes_each_signed_tab_to_its_backend(backend, label):
    router, managed, shared, _ = make_router()
    ref = token(backend)
    snapshot = asyncio.run(router.browser_snapshot(Caller(), {"tab_ref": ref}))
    assert snapshot["backend"] == label
    prepared = asyncio.run(
        router.prepare_browser_action(
            Caller(),
            {
                "tab_ref": ref,
                "action": "click",
                "args": {"element_ref": "element-a"},
            },
        )
    )
    assert prepared["action_ref"] == label + ":prepared"
    called = managed if backend is TabBackend.MANAGED else shared
    idle = shared if backend is TabBackend.MANAGED else managed
    assert [row[0] for row in called.calls] == ["snapshot", "prepare"]
    assert idle.calls == []


def test_run_routes_by_exact_signed_tab_and_keeps_caller_binding():
    router, managed, shared, _ = make_router()
    ref = token(TabBackend.SHARED_HUMAN)
    result = asyncio.run(
        router.run_browser_action(
            Caller(),
            {"tab_ref": ref, "action_ref": "outer-action"},
        )
    )
    assert result == {"effect": "APPLIED", "backend": "shared"}
    assert shared.calls[0][1] == Caller()
    assert managed.calls == []


def test_foreign_caller_refuses_before_backend_selection():
    router, managed, shared, _ = make_router()
    with pytest.raises(OwnerRefused, match="CALLER_BINDING_CHANGED"):
        asyncio.run(
            router.browser_snapshot(
                Caller(client_ref="client-b"),
                {"tab_ref": token(TabBackend.SHARED_HUMAN)},
            )
        )
    assert managed.calls == []
    assert shared.calls == []


def test_invalid_signed_ref_refuses_before_any_backend():
    router, managed, shared, _ = make_router()
    ref = token(TabBackend.MANAGED)
    changed = ref[:-1] + ("A" if ref[-1] != "A" else "B")
    with pytest.raises(OwnerRefused):
        asyncio.run(router.browser_snapshot(Caller(), {"tab_ref": changed}))
    assert managed.calls == []
    assert shared.calls == []


def test_only_reconcile_may_route_an_expired_tab_ref():
    router, managed, shared, _ = make_router(now=NOW + 60_000)
    ref = token(TabBackend.SHARED_HUMAN)
    with pytest.raises(OwnerRefused, match="TAB_REF_EXPIRED"):
        asyncio.run(
            router.run_browser_action(
                Caller(),
                {"tab_ref": ref, "action_ref": "outer-action"},
            )
        )
    result = asyncio.run(
        router.reconcile_browser_action(
            Caller(),
            {"tab_ref": ref, "action_ref": "outer-action"},
        )
    )
    assert result["effect"] == "EFFECT_UNKNOWN"
    assert [row[0] for row in shared.calls] == ["reconcile"]
    assert managed.calls == []


def test_inventory_stays_with_injected_existing_owner():
    router, managed, shared, inventory = make_router()
    assert asyncio.run(router.browser_fleet(Caller(), {"limit": 2})) == {
        "browsers": ["managed-a", "shared-a"]
    }
    assert asyncio.run(router.browser_tabs(Caller(), {"browser_ref": "browser-a"})) == {
        "tabs": ["tab-a"]
    }
    assert [row[0] for row in inventory.calls] == ["fleet", "tabs"]
    assert managed.calls == []
    assert shared.calls == []


def test_facade_can_use_router_as_one_backend_agnostic_owner():
    router, managed, shared, _ = make_router()
    facade = BrowserFacade(owner=router, caller_resolver=lambda: Caller())
    result = asyncio.run(
        facade.call(
            "browser_snapshot",
            {"tab_ref": token(TabBackend.MANAGED)},
        )
    )
    assert result["is_error"] is False
    assert result["data"]["backend"] == "managed"
    assert len(managed.calls) == 1
    assert shared.calls == []
