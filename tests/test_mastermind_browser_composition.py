from __future__ import annotations

import asyncio
from dataclasses import dataclass

from integrations.mastermind_browser_plugin.catalog import SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.composition import (
    BrowserOwnerComposition,
    compose_browser_owner,
)
from integrations.mastermind_browser_plugin.inventory_owner import (
    ActiveBrowserResource,
    BrowserTabObservation,
)
from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.playwright_extension import (
    EXPECTED_TOOL_SCHEMA_DIGEST,
)
from integrations.mastermind_browser_plugin.tab_ref import BrowserTabRefCodec, TabBackend

NOW = 1_800_000_000_000
KEY = b"k" * 32


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


def resource(backend, suffix, *, consent=None):
    return ActiveBrowserResource(
        backend=backend,
        browser_ref="browser-resource-" + suffix * 64,
        host_ref="host-" + suffix * 64,
        boot_ref=f"boot-{suffix}",
        profile_ref=f"profile-{suffix}",
        browser_instance_ref=f"browser-{suffix}",
        connection_generation=f"generation-{suffix}",
        consent_ref=consent,
        allowed_actions=("click", "navigate", "screenshot", "snapshot", "type"),
        catalog_schema_digest=SCHEMA_DIGEST,
        backend_schema_digest=EXPECTED_TOOL_SCHEMA_DIGEST,
        expires_at_ms=NOW + 60_000,
    )


MANAGED = resource(TabBackend.MANAGED.value, "a")
SHARED = resource(TabBackend.SHARED_HUMAN.value, "c", consent="consent-c")


def observation(row):
    return BrowserTabObservation(
        browser_ref=row.browser_ref,
        tab_locator=1,
        document_revision=7,
        title=f"{row.backend} tab",
        url="https://example.test/path?secret=hidden#fragment",
        observed_at_ms=NOW - 100,
        expires_at_ms=NOW + 5_000,
    )


class EffectPort:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def call_read_tool(self, caller, browser_ref, tool, arguments):
        self.calls.append(("read", caller, browser_ref, tool, dict(arguments)))
        return {"content": [], "structuredContent": {"owner": self.name}, "isError": False}

    def prepare_action(self, caller, browser_ref, tool, arguments):
        self.calls.append(("prepare", caller, browser_ref, tool, dict(arguments)))
        return f"{self.name}-action"

    def run_action(self, caller, browser_ref, action_ref):
        self.calls.append(("run", caller, browser_ref, action_ref))
        return {
            "status": "OK",
            "effect_state": "APPLIED",
            "observed_sha256": "d" * 64,
            "reconciled": False,
        }

    def reconcile_action(self, caller, browser_ref, action_ref):
        self.calls.append(("reconcile", caller, browser_ref, action_ref))
        return {
            "status": "OK",
            "effect_state": "EFFECT_UNKNOWN",
            "observed_sha256": None,
            "reconciled": True,
        }


def fixture():
    managed = EffectPort("managed")
    shared = EffectPort("shared")
    broker = Caller(
        subject_digest="e" * 64,
        client_ref="browser-broker",
        resource="browser-resource",
    )

    async def resources(_caller, limit):
        return [MANAGED, SHARED][:limit]

    async def tabs(_caller, row):
        return [observation(row)]

    composition = compose_browser_owner(
        signing_key=KEY,
        clock_ms=lambda: NOW,
        caller_binding=caller_binding,
        resource_reader=resources,
        tab_reader=tabs,
        managed_effect_port=managed,
        shared_effect_port=shared,
        shared_broker_caller=broker,
        expected_catalog_schema_digest=SCHEMA_DIGEST,
        managed_backend_schema_digest=EXPECTED_TOOL_SCHEMA_DIGEST,
        shared_backend_schema_digest=EXPECTED_TOOL_SCHEMA_DIGEST,
    )
    return composition, managed, shared, broker


def test_composition_builds_one_router_and_one_shared_inventory():
    composition, _, _, _ = fixture()
    assert isinstance(composition, BrowserOwnerComposition)
    assert composition.router is composition.owner
    result = asyncio.run(composition.owner.browser_fleet(Caller(), {"limit": 10}))
    assert [row["backend"] for row in result["browsers"]] == ["managed", "shared_human"]
    assert not hasattr(composition, "registry")
    assert not hasattr(composition, "scheduler")


def test_managed_and_shared_tabs_route_to_distinct_existing_effect_owners():
    composition, managed, shared, broker = fixture()
    fleet = asyncio.run(composition.owner.browser_fleet(Caller(), {"limit": 10}))
    by_backend = {row["backend"]: row["browser_ref"] for row in fleet["browsers"]}

    managed_tab = asyncio.run(
        composition.owner.browser_tabs(
            Caller(), {"browser_ref": by_backend["managed"]}
        )
    )["tabs"][0]["tab_ref"]
    shared_tab = asyncio.run(
        composition.owner.browser_tabs(
            Caller(), {"browser_ref": by_backend["shared_human"]}
        )
    )["tabs"][0]["tab_ref"]

    managed_result = asyncio.run(
        composition.owner.browser_snapshot(Caller(), {"tab_ref": managed_tab})
    )
    shared_result = asyncio.run(
        composition.owner.browser_snapshot(Caller(), {"tab_ref": shared_tab})
    )

    assert managed_result["structuredContent"]["owner"] == "managed"
    assert shared_result["structuredContent"]["owner"] == "shared"
    assert managed.calls[0][1] == Caller()
    assert shared.calls[0][1] == broker


def test_shared_action_uses_outer_caller_ref_but_inner_broker_effect_identity():
    composition, _, shared, broker = fixture()
    fleet = asyncio.run(composition.owner.browser_fleet(Caller(), {"limit": 10}))
    session = next(
        row["browser_ref"]
        for row in fleet["browsers"]
        if row["backend"] == "shared_human"
    )
    tab_ref = asyncio.run(
        composition.owner.browser_tabs(Caller(), {"browser_ref": session})
    )["tabs"][0]["tab_ref"]

    prepared = asyncio.run(
        composition.owner.prepare_browser_action(
            Caller(),
            {
                "tab_ref": tab_ref,
                "action": "click",
                "args": {"element_ref": "element-a"},
            },
        )
    )
    assert prepared["action_ref"] != "shared-action"
    result = asyncio.run(
        composition.owner.run_browser_action(
            Caller(),
            {"tab_ref": tab_ref, "action_ref": prepared["action_ref"]},
        )
    )
    assert result["effect"] == "APPLIED"
    assert [call[0] for call in shared.calls] == ["prepare", "run"]
    assert all(call[1] == broker for call in shared.calls)


def test_composition_requires_explicit_shared_broker_and_existing_ports():
    managed = EffectPort("managed")
    shared = EffectPort("shared")

    async def resources(_caller, _limit):
        return []

    async def tabs(_caller, _row):
        return []

    base = dict(
        signing_key=KEY,
        clock_ms=lambda: NOW,
        caller_binding=caller_binding,
        resource_reader=resources,
        tab_reader=tabs,
        managed_effect_port=managed,
        shared_effect_port=shared,
        shared_broker_caller=Caller(),
        expected_catalog_schema_digest=SCHEMA_DIGEST,
        managed_backend_schema_digest=EXPECTED_TOOL_SCHEMA_DIGEST,
        shared_backend_schema_digest=EXPECTED_TOOL_SCHEMA_DIGEST,
    )
    for field, value in (
        ("shared_broker_caller", None),
        ("managed_effect_port", object()),
        ("shared_effect_port", object()),
        ("signing_key", b"short"),
    ):
        args = dict(base)
        args[field] = value
        try:
            compose_browser_owner(**args)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(f"{field} must fail closed")


def test_composition_codec_decodes_its_own_outer_session_refs():
    composition, _, _, _ = fixture()
    row = asyncio.run(
        composition.owner.browser_fleet(Caller(), {"limit": 1})
    )["browsers"][0]
    observed = composition.codec.decode_session(
        row["browser_ref"],
        now_ms=NOW,
        subject_digest=Caller().subject_digest,
        client_ref=Caller().client_ref,
        resource=Caller().resource,
    )
    assert observed.browser_ref == MANAGED.browser_ref
    assert isinstance(composition.codec, BrowserTabRefCodec)
