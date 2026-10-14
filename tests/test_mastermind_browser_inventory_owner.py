from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import json

import pytest

from integrations.mastermind_browser_plugin.catalog import SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.facade import OwnerRefused
from integrations.mastermind_browser_plugin.inventory_owner import (
    ActiveBrowserResource,
    BrowserInventoryOwner,
    BrowserTabObservation,
)
from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.tab_ref import (
    BrowserSessionRef,
    BrowserTabRefCodec,
    BrowserTabRefError,
    TabBackend,
)

NOW = 1_800_000_000_000
KEY = b"k" * 32
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


def active(**changes):
    values = dict(
        backend=TabBackend.MANAGED.value,
        browser_ref="browser-resource-" + "a" * 64,
        host_ref="host-" + "c" * 64,
        boot_ref="boot-a",
        profile_ref="profile-a",
        browser_instance_ref="browser-a",
        connection_generation="generation-a",
        consent_ref=None,
        allowed_actions=("click", "navigate", "screenshot", "snapshot", "type"),
        catalog_schema_digest=SCHEMA_DIGEST,
        backend_schema_digest=BACKEND_DIGEST,
        expires_at_ms=NOW + 60_000,
    )
    values.update(changes)
    return ActiveBrowserResource(**values)


def tab(resource=None, **changes):
    resource = resource or active()
    values = dict(
        browser_ref=resource.browser_ref,
        tab_locator=1,
        document_revision=7,
        title="Example tab",
        url="https://example.test/path?secret=not-returned#fragment",
        observed_at_ms=NOW - 100,
        expires_at_ms=NOW + 5_000,
    )
    values.update(changes)
    return BrowserTabObservation(**values)


def owner(*, resources=None, tabs=None, now=NOW):
    calls = {"resources": 0, "tabs": 0}

    async def resource_reader(caller, limit):
        calls["resources"] += 1
        rows = [active()] if resources is None else resources
        return rows[:limit]

    async def tab_reader(caller, resource):
        calls["tabs"] += 1
        return [tab(resource)] if tabs is None else tabs

    value = BrowserInventoryOwner(
        codec=BrowserTabRefCodec(KEY),
        clock_ms=lambda: now,
        caller_binding=caller_binding,
        resource_reader=resource_reader,
        tab_reader=tab_reader,
        expected_catalog_schema_digest=SCHEMA_DIGEST,
    )
    return value, calls


def fleet(value, caller=Caller(), limit=10):
    return asyncio.run(value.browser_fleet(caller, {"limit": limit}))


def tabs(value, browser_ref, caller=Caller()):
    return asyncio.run(value.browser_tabs(caller, {"browser_ref": browser_ref}))


def test_fleet_returns_caller_bound_signed_session_ref_not_raw_owner_capability():
    inventory, calls = owner()
    result = fleet(inventory)
    assert calls == {"resources": 1, "tabs": 0}
    assert len(result["browsers"]) == 1
    row = result["browsers"][0]
    assert set(row) == {
        "browser_ref",
        "backend",
        "host_ref",
        "profile_ref",
        "allowed_actions",
        "expires_at_ms",
    }
    assert row["backend"] == "managed"
    assert row["host_ref"] == active().host_ref
    assert active().browser_ref not in json.dumps(result)

    decoded = BrowserTabRefCodec(KEY).decode_session(
        row["browser_ref"],
        now_ms=NOW,
        subject_digest=Caller().subject_digest,
        client_ref=Caller().client_ref,
        resource=Caller().resource,
    )
    assert isinstance(decoded, BrowserSessionRef)
    assert decoded.browser_ref == active().browser_ref
    assert decoded.connection_generation == "generation-a"


def test_same_owner_resource_gets_distinct_outer_refs_for_distinct_callers():
    inventory, _ = owner()
    a = fleet(inventory, Caller(client_ref="client-a"))["browsers"][0]["browser_ref"]
    b = fleet(inventory, Caller(client_ref="client-b"))["browsers"][0]["browser_ref"]
    assert a != b
    with pytest.raises(BrowserTabRefError, match="CALLER_BINDING_CHANGED"):
        BrowserTabRefCodec(KEY).decode_session(
            a,
            now_ms=NOW,
            subject_digest="b" * 64,
            client_ref="client-b",
            resource="browser-resource",
        )


def test_fleet_is_a_fresh_projection_not_a_local_browser_registry():
    inventory, calls = owner()
    fleet(inventory)
    fleet(inventory)
    assert calls["resources"] == 2
    assert "registry" not in vars(inventory)


def test_expired_resource_is_not_advertised():
    inventory, _ = owner(resources=[active(expires_at_ms=NOW)])
    assert fleet(inventory) == {"browsers": []}


def test_catalog_schema_drift_is_not_advertised():
    inventory, _ = owner(resources=[active(catalog_schema_digest="f" * 64)])
    assert fleet(inventory) == {"browsers": []}


def test_duplicate_active_owner_capability_fails_closed():
    row = active()
    inventory, _ = owner(resources=[row, row])
    with pytest.raises(OwnerRefused, match="INVENTORY_DUPLICATE"):
        fleet(inventory)


def test_browser_tabs_requires_exact_current_resource_generation_and_caller():
    inventory, _ = owner()
    browser_ref = fleet(inventory)["browsers"][0]["browser_ref"]

    changed = replace(active(), connection_generation="generation-b")
    moved, _ = owner(resources=[changed])
    with pytest.raises(OwnerRefused, match="BROWSER_BINDING_CHANGED"):
        tabs(moved, browser_ref)

    with pytest.raises(OwnerRefused, match="CALLER_BINDING_CHANGED"):
        tabs(inventory, browser_ref, Caller(client_ref="client-b"))


def test_exactly_one_tab_per_resource_prevents_selected_page_races():
    inventory, _ = owner(tabs=[])
    browser_ref = fleet(inventory)["browsers"][0]["browser_ref"]
    with pytest.raises(OwnerRefused, match="TAB_UNAVAILABLE"):
        tabs(inventory, browser_ref)

    resource = active()
    inventory, _ = owner(tabs=[tab(resource), tab(resource, tab_locator=2)])
    browser_ref = fleet(inventory)["browsers"][0]["browser_ref"]
    with pytest.raises(OwnerRefused, match="TAB_GROUP_NOT_EXCLUSIVE"):
        tabs(inventory, browser_ref)


def test_tab_projection_sanitizes_url_and_signs_exact_document_generation():
    inventory, _ = owner()
    browser_ref = fleet(inventory)["browsers"][0]["browser_ref"]
    result = tabs(inventory, browser_ref)
    assert len(result["tabs"]) == 1
    row = result["tabs"][0]
    assert row["title"] == "Example tab"
    assert row["url"] == "https://example.test/path"
    assert "secret" not in json.dumps(row)
    decoded = BrowserTabRefCodec(KEY).decode(
        row["tab_ref"],
        now_ms=NOW,
    )
    assert decoded.tab_locator == 1
    assert decoded.document_revision == 7
    assert decoded.backend == TabBackend.MANAGED.value
    assert decoded.consent_ref is None
    assert decoded.catalog_schema_digest == SCHEMA_DIGEST
    assert decoded.backend_schema_digest == BACKEND_DIGEST


def test_shared_human_tab_carries_owner_consent_generation():
    resource = active(
        backend=TabBackend.SHARED_HUMAN.value,
        consent_ref="consent-a",
    )
    inventory, _ = owner(resources=[resource], tabs=[tab(resource)])
    browser_ref = fleet(inventory)["browsers"][0]["browser_ref"]
    result = tabs(inventory, browser_ref)
    decoded = BrowserTabRefCodec(KEY).decode(result["tabs"][0]["tab_ref"], now_ms=NOW)
    assert decoded.backend == TabBackend.SHARED_HUMAN.value
    assert decoded.consent_ref == "consent-a"


def test_tab_observation_must_be_current_and_match_underlying_resource():
    resource = active()
    for observed, code in [
        (tab(resource, browser_ref="browser-resource-" + "d" * 64), "TAB_BINDING_CHANGED"),
        (tab(resource, observed_at_ms=NOW + 1), "TAB_OBSERVATION_NOT_CURRENT"),
        (tab(resource, expires_at_ms=NOW), "TAB_OBSERVATION_NOT_CURRENT"),
    ]:
        inventory, _ = owner(resources=[resource], tabs=[observed])
        browser_ref = fleet(inventory)["browsers"][0]["browser_ref"]
        with pytest.raises(OwnerRefused, match=code):
            tabs(inventory, browser_ref)


def test_revalidate_tab_re_reads_owner_resource_and_document_every_time():
    resource = active()
    current = tab(resource)
    inventory, calls = owner(resources=[resource], tabs=[current])
    browser_ref = fleet(inventory)["browsers"][0]["browser_ref"]
    projected = tabs(inventory, browser_ref)["tabs"][0]["tab_ref"]
    signed = BrowserTabRefCodec(KEY).decode(projected, now_ms=NOW)

    assert asyncio.run(inventory.revalidate_tab(Caller(), signed)) is True
    assert calls["resources"] == 3
    assert calls["tabs"] == 2

    changed, _ = owner(
        resources=[resource],
        tabs=[replace(current, document_revision=8)],
    )
    assert asyncio.run(changed.revalidate_tab(Caller(), signed)) is False


def test_fleet_limit_is_closed_and_does_not_become_placement():
    inventory, _ = owner()
    assert len(fleet(inventory, limit=1)["browsers"]) == 1
    for value in [0, 51, True, 1.2, "1"]:
        with pytest.raises(OwnerRefused, match="INVALID_ARGUMENTS"):
            asyncio.run(inventory.browser_fleet(Caller(), {"limit": value}))
    with pytest.raises(OwnerRefused, match="INVALID_ARGUMENTS"):
        asyncio.run(inventory.browser_fleet(Caller(), {"limit": 1, "select_host": "m2"}))


def test_resource_and_tab_types_reject_secret_bearing_or_unbounded_fields():
    with pytest.raises(ValueError):
        active(profile_ref="/Users/private/Profile 2")
    with pytest.raises(ValueError):
        active(consent_ref="person@example.com", backend=TabBackend.SHARED_HUMAN.value)
    with pytest.raises(ValueError):
        tab(title="x\nsecret")
    with pytest.raises(ValueError):
        tab(url="file:///etc/passwd")
    with pytest.raises(ValueError):
        tab(url="https://user:pass@example.test/")


def test_inventory_never_starts_allocates_or_ranks_resources():
    inventory, _ = owner()
    names = set(vars(inventory))
    for forbidden in {
        "_start_resource",
        "_prepare_resource",
        "_select_host",
        "_rank",
        "_scheduler",
        "_lease_store",
        "_retry_queue",
    }:
        assert forbidden not in names
