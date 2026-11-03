import asyncio
from dataclasses import replace

import pytest

from integrations.mastermind_browser_link.tool_contract import LINK_TOOL_SCHEMA_DIGEST, OWNER_INVENTORY_SCHEMA, OWNER_CONNECTION_SCHEMA, ACTION_TOOL
from integrations.mastermind_browser_plugin.facade import OwnerRefused
from integrations.mastermind_browser_plugin.link_inventory import LINK_ACTIONS
from integrations.mastermind_browser_plugin.workbench_composition import compose_browser_owner_from_workbench
from integrations.workbench_browser_mcp.deployment import ActiveBrowserProjection
from tests.test_mastermind_browser_workbench_composition import (
    FakeDeployment, workbench_resource, broker_caller, OuterCaller, outer_binding, KEY, NOW,
)


class LinkDeployment(FakeDeployment):
    def __init__(self):
        super().__init__(replace(workbench_resource(mode="extension"), tool_schema_digest=LINK_TOOL_SCHEMA_DIGEST))
        self.clock = [NOW]
        self.generation = "native-generation"
        self.rows = [{"tab_id": tab, "origin": "https://example.test", "consent_id": f"consent-{tab}",
                      "document_revision": 0, "state": "shared", "allow_create": False} for tab in (7, 8)]
        self.status_calls = []
        self.tab_calls = []
        self.other = False

    async def observe_active_resources(self, caller):
        result = list(await super().observe_active_resources(caller))
        if self.other:
            result.append(ActiveBrowserProjection(browser_ref="other-" + "c" * 64,
                resource=replace(self.resource, start_action_id="d" * 32, profile_ref="other-profile")))
        return tuple(result)

    async def observe_connection(self, caller, browser_ref):
        self.status_calls.append(browser_ref)
        return {"schema": OWNER_CONNECTION_SCHEMA, "instance_id": "b" * 64,
                "connected": True, "connection_generation": self.generation}

    async def observe_tab_group(self, caller, browser_ref):
        self.tab_calls.append(browser_ref)
        assert browser_ref == self.raw_ref, "unrelated native profile was queried"
        self.clock[0] += 20  # real I/O advances time; pre-read timestamps cannot qualify it
        return {"isError": False, "structuredContent": {
            "schema": OWNER_INVENTORY_SCHEMA, "instance_id": "b" * 64,
            "connection_generation": self.generation, "shared_tabs": self.rows,
        }}


def setup():
    deployment = LinkDeployment()
    composition = compose_browser_owner_from_workbench(
        deployment=deployment, signing_key=KEY, clock_ms=lambda: deployment.clock[0],
        caller_binding=outer_binding, broker_caller=broker_caller(),
        expected_backend_schema_digest=LINK_TOOL_SCHEMA_DIGEST,
    )
    caller = OuterCaller("e" * 64, "outer")
    return deployment, composition, caller


async def tabs_for(composition, caller):
    fleet = await composition.owner.browser_fleet(caller, {"limit": 10})
    session = fleet["browsers"][0]["browser_ref"]
    tabs = await composition.owner.browser_tabs(caller, {"browser_ref": session})
    return session, tabs["tabs"]


def decoded(composition, caller, reference, now):
    tab = composition.codec.decode(reference, now_ms=now)
    assert (tab.subject_digest, tab.client_ref, tab.resource) == (caller.subject_digest, caller.client_ref, caller.resource)
    return tab


def test_two_tabs_preserve_real_consent_and_only_selected_profile_is_observed():
    deployment, composition, caller = setup()
    deployment.other = True
    async def exercise():
        fleet = await composition.owner.browser_fleet(caller, {"limit": 10})
        assert len(fleet["browsers"]) == 2
        assert deployment.tab_calls == []  # connection discovery never queries page state
        chosen = next(row for row in fleet["browsers"] if row["profile_ref"] == "profile-a")
        tabs = (await composition.owner.browser_tabs(caller, {"browser_ref": chosen["browser_ref"]}))["tabs"]
        assert len(tabs) == 2
        first, second = [decoded(composition, caller, tab["tab_ref"], deployment.clock[0]) for tab in tabs]
        assert (first.tab_locator, first.consent_ref) == (7, "consent-7")
        assert (second.tab_locator, second.consent_ref) == (8, "consent-8")
        assert first.expires_at_ms - first.issued_at_ms == 30_000
        deployment.status_calls.clear()
        assert await composition.inventory.revalidate_tab(caller, second)
        assert deployment.status_calls == [deployment.raw_ref]
        deployment.rows[0]["consent_id"] = "replacement-consent"
        assert not await composition.inventory.revalidate_tab(caller, first)
        assert await composition.inventory.revalidate_tab(caller, second)
    asyncio.run(exercise())


def test_reconnect_changes_all_old_refs_without_falling_back_to_other_tab():
    deployment, composition, caller = setup()
    async def exercise():
        session, tabs = await tabs_for(composition, caller)
        tab = decoded(composition, caller, tabs[0]["tab_ref"], deployment.clock[0])
        deployment.generation = "new-native-generation"
        assert not await composition.inventory.revalidate_tab(caller, tab)
        with pytest.raises(OwnerRefused, match="BROWSER_BINDING_CHANGED"):
            await composition.owner.browser_tabs(caller, {"browser_ref": session})
    asyncio.run(exercise())


def test_busy_and_navigating_tabs_are_omitted_and_unknown_effect_is_read_only():
    deployment, composition, caller = setup()
    deployment.rows[0]["state"] = "navigating"
    deployment.rows[1]["state"] = "effect_unresolved"
    async def exercise():
        _session, tabs = await tabs_for(composition, caller)
        assert len(tabs) == 1
        tab = decoded(composition, caller, tabs[0]["tab_ref"], deployment.clock[0])
        assert tab.tab_locator == 8
        assert tab.allowed_actions == ("screenshot", "snapshot")
        deployment.rows[1]["state"] = "busy"
        _session, empty = await tabs_for(composition, caller)
        assert empty == []
    asyncio.run(exercise())


@pytest.mark.parametrize("mutate", [
    lambda rows: rows.append(dict(rows[0])),
    lambda rows: rows[0].update(tab_id=2**53),
    lambda rows: rows[0].update(document_revision=True),
    lambda rows: rows[0].update(consent_id=""),
    lambda rows: rows[0].update(unexpected=True),
])
def test_malformed_link_tab_facts_are_refused(mutate):
    deployment, composition, caller = setup()
    mutate(deployment.rows)
    with pytest.raises(OwnerRefused):
        asyncio.run(tabs_for(composition, caller))


def test_exact_action_projection_has_no_caller_writer_or_target_override():
    deployment, composition, caller = setup()
    async def exercise():
        _session, tabs = await tabs_for(composition, caller)
        await composition.owner.prepare_browser_action(caller, {
            "tab_ref": tabs[1]["tab_ref"], "action": "scroll",
            "args": {"delta_x": 0, "delta_y": 200},
        })
        call = [row for row in deployment.calls if row[0] == "prepare"][-1]
        assert call[3] == ACTION_TOOL
        assert call[4]["target"] == {"tab_id": 8, "consent_id": "consent-8",
            "connection_generation": "native-generation", "document_revision": 0}
        assert set(call[4]) == {"target", "command", "args", "expires_at_ms"}
        with pytest.raises(OwnerRefused):
            await composition.owner.prepare_browser_action(caller, {
                "tab_ref": tabs[1]["tab_ref"], "action": "scroll",
                "args": {"delta_x": 0, "delta_y": 200, "tab_id": 7},
            })
    asyncio.run(exercise())


def test_creation_actions_follow_exact_local_consent_and_never_another_tab():
    deployment, composition, caller = setup()
    deployment.rows[0]["allow_create"] = True
    async def exercise():
        _session, tabs = await tabs_for(composition, caller)
        permitted, ordinary = [decoded(composition, caller, row["tab_ref"], deployment.clock[0]) for row in tabs]
        assert {"create_tab", "create_window"} <= set(permitted.allowed_actions)
        assert {"create_tab", "create_window"}.isdisjoint(ordinary.allowed_actions)
        await composition.owner.prepare_browser_action(caller, {
            "tab_ref": tabs[0]["tab_ref"], "action": "create_window", "args": {"url": "https://child.test/"}})
        projected = [row for row in deployment.calls if row[0] == "prepare"][-1][4]
        assert projected["command"] == "create_window"
        assert projected["target"]["tab_id"] == 7
        with pytest.raises(OwnerRefused):
            await composition.owner.prepare_browser_action(caller, {
                "tab_ref": tabs[1]["tab_ref"], "action": "create_tab", "args": {"url": "https://child.test/"}})
        deployment.rows[0]["allow_create"] = False
        assert not await composition.inventory.revalidate_tab(caller, permitted)
    asyncio.run(exercise())


@pytest.mark.parametrize("flag", [None, 0, 1, "", [], {}])
def test_creation_permission_must_be_a_present_boolean(flag):
    deployment, composition, caller = setup()
    deployment.rows[0]["allow_create"] = flag
    with pytest.raises(OwnerRefused):
        asyncio.run(tabs_for(composition, caller))
