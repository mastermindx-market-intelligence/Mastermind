from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib

import pytest

from control_plane.browser_resource_contract import BrowserMode
from integrations.mastermind_browser_plugin.catalog import SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.inventory_owner import (
    ActiveBrowserResource,
    BrowserInventoryOwner,
    BrowserTabObservation,
)
from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.tab_ref import (
    BrowserTabRefCodec,
    TabBackend,
)
from integrations.mastermind_browser_plugin.workbench_inventory import (
    WorkbenchDeploymentInventoryProjection,
    parse_playwright_tab_group,
    project_active_resource,
)
from integrations.workbench_action_mcp.contracts import ActionCaller
from integrations.workbench_browser_mcp.contracts import BrowserResourceRef
from integrations.workbench_browser_mcp.deployment import ActiveBrowserProjection

NOW = 1_800_000_000_000
KEY = b"k" * 32


def resource(**changes):
    values = dict(
        schema="mastermind.workbench_browser_ref.v1",
        start_action_id="c" * 32,
        subject_digest="a" * 64,
        client_ref="broker-client",
        resource="https://workbench.example/browser",
        project_ref="project:browser",
        context_ref="context:browser",
        responsibility_ref="responsibility:browser",
        operation_ref="operation:browser",
        owner_ref="owner:browser",
        generation="generation:browser",
        host_id="b" * 64,
        boot_session_id="boot:browser",
        relay_pid=4321,
        relay_start_identity="1700000000.000001",
        relay_pgid=4321,
        relay_session_id=4321,
        mode=BrowserMode.PERSISTENT.value,
        profile_ref="profile-a",
        tool_schema_digest="d" * 64,
        issued_at_ms=NOW - 1000,
        expires_at_ms=NOW + 60_000,
    )
    values.update(changes)
    return BrowserResourceRef(**values)


def active(**changes):
    row = resource(**changes)
    return ActiveBrowserProjection(browser_ref="wbr-" + "f" * 64, resource=row)


def native_tabs(*lines):
    return {
        "content": [
            {
                "type": "text",
                "text": "### Result\n" + "\n".join(lines),
            }
        ],
        "isError": False,
    }


def test_persistent_resource_projects_to_managed_fleet_fact():
    observed = project_active_resource(active(), now_ms=NOW)
    assert isinstance(observed, ActiveBrowserResource)
    assert observed.backend == TabBackend.MANAGED.value
    assert observed.browser_ref == active().browser_ref
    assert observed.host_ref == "b" * 64
    assert observed.profile_ref == "profile-a"
    assert observed.consent_ref is None
    assert observed.catalog_schema_digest == SCHEMA_DIGEST
    assert observed.backend_schema_digest == "d" * 64
    assert observed.allowed_actions == (
        "click",
        "navigate",
        "screenshot",
        "snapshot",
        "type",
    )
    assert observed.connection_generation.startswith("conn-")
    assert observed.browser_instance_ref.startswith("browser-")


def test_extension_resource_projects_to_shared_human_broker_generation():
    observed = project_active_resource(
        active(mode=BrowserMode.EXTENSION.value, profile_ref="Profile-1"),
        now_ms=NOW,
    )
    assert observed.backend == TabBackend.SHARED_HUMAN.value
    assert observed.consent_ref is not None
    assert observed.consent_ref.startswith("consent-")
    assert observed.profile_ref == "Profile-1"


def test_isolated_or_expired_resources_are_not_shareable_fleet_resources():
    assert project_active_resource(
        active(mode=BrowserMode.ISOLATED.value, profile_ref=None),
        now_ms=NOW,
    ) is None
    assert project_active_resource(
        active(expires_at_ms=NOW),
        now_ms=NOW,
    ) is None


def test_resource_generation_rotates_with_exact_relay_process_identity():
    first = project_active_resource(active(), now_ms=NOW)
    second = project_active_resource(
        active(relay_start_identity="1700000000.000002"),
        now_ms=NOW,
    )
    assert first is not None and second is not None
    assert first.browser_instance_ref != second.browser_instance_ref
    assert first.consent_ref == second.consent_ref  # managed resources carry none


def test_one_current_tab_parses_to_bounded_observation():
    rows = parse_playwright_tab_group(
        native_tabs(
            "- 0: (current) [Example tab](https://example.test/path?secret=hidden#frag)"
        ),
        browser_ref=active().browser_ref,
        now_ms=NOW,
        resource_expires_at_ms=NOW + 60_000,
    )
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, BrowserTabObservation)
    assert row.tab_locator == 0
    assert row.title == "Example tab"
    assert row.url == "https://example.test/path?secret=hidden#frag"
    assert row.observed_at_ms == NOW
    assert NOW < row.expires_at_ms <= NOW + 5000
    assert row.document_revision > 0


def test_multiple_tabs_remain_multiple_so_inventory_owner_can_fail_closed():
    rows = parse_playwright_tab_group(
        native_tabs(
            "- 0: (current) [One](https://one.example/)",
            "- 1: [Two](https://two.example/)",
        ),
        browser_ref=active().browser_ref,
        now_ms=NOW,
        resource_expires_at_ms=NOW + 60_000,
    )
    assert [row.tab_locator for row in rows] == [0, 1]


@pytest.mark.parametrize(
    "payload",
    [
        {"content": [], "isError": False},
        {"content": [{"type": "text", "text": "### Result\n"}], "isError": False},
        native_tabs("- 0: (current) [Crashed](https://example.test/) [crashed]"),
        native_tabs("- 0: (current) [File](file:///etc/passwd)"),
        native_tabs("- 0: [Not selected](https://example.test/)"),
    ],
)
def test_tab_parser_refuses_malformed_crashed_or_noncurrent_single_group(payload):
    with pytest.raises(ValueError):
        parse_playwright_tab_group(
            payload,
            browser_ref=active().browser_ref,
            now_ms=NOW,
            resource_expires_at_ms=NOW + 60_000,
        )


class FakeDeployment:
    def __init__(self, projections, tab_result):
        self.projections = tuple(projections)
        self.tab_result = tab_result
        self.resource_calls = []
        self.tab_calls = []

    async def observe_active_resources(self, caller):
        self.resource_calls.append(caller)
        return self.projections

    async def observe_tab_group(self, caller, browser_ref):
        self.tab_calls.append((caller, browser_ref))
        return self.tab_result


def broker_caller():
    return ActionCaller(
        subject_digest="a" * 64,
        client_ref="broker-client",
        resource="https://workbench.example/browser",
        scopes=("workbench.action",),
        expires_at=2_000_000_000,
    )


def outer_binding(_caller):
    return BrowserCallerBinding(
        subject_digest="e" * 64,
        client_ref="outer-client",
        resource="browser-resource",
    )


def test_projection_feeds_stateless_inventory_owner_without_raw_ref_disclosure():
    deployment = FakeDeployment(
        [active()],
        native_tabs("- 0: (current) [Example](https://example.test/path?secret=x)"),
    )
    projection = WorkbenchDeploymentInventoryProjection(
        deployment=deployment,
        broker_caller=broker_caller(),
        clock_ms=lambda: NOW,
    )
    inventory = BrowserInventoryOwner(
        codec=BrowserTabRefCodec(KEY),
        clock_ms=lambda: NOW,
        caller_binding=outer_binding,
        resource_reader=projection.resource_reader,
        tab_reader=projection.tab_reader,
    )
    caller = object()
    fleet = asyncio.run(inventory.browser_fleet(caller, {"limit": 10}))
    assert len(fleet["browsers"]) == 1
    assert active().browser_ref not in repr(fleet)
    tabs = asyncio.run(
        inventory.browser_tabs(
            caller,
            {"browser_ref": fleet["browsers"][0]["browser_ref"]},
        )
    )
    assert len(tabs["tabs"]) == 1
    assert tabs["tabs"][0]["url"] == "https://example.test/path"
    assert "secret" not in repr(tabs)
    assert deployment.resource_calls
    assert deployment.tab_calls


def test_projection_does_not_rank_or_allocate_and_limit_is_only_output_bound():
    rows = [
        active(),
        ActiveBrowserProjection(
            browser_ref="wbr-" + "e" * 64,
            resource=replace(
                resource(),
                start_action_id="e" * 32,
                profile_ref="profile-b",
                relay_start_identity="1700000000.000002",
            ),
        ),
    ]
    deployment = FakeDeployment(rows, native_tabs("- 0: (current) [X](https://x.example/)"))
    projection = WorkbenchDeploymentInventoryProjection(
        deployment=deployment,
        broker_caller=broker_caller(),
        clock_ms=lambda: NOW,
    )
    result = asyncio.run(projection.resource_reader(object(), 1))
    assert len(result) == 1
    assert not any(
        name in vars(projection)
        for name in ("_scheduler", "_ranker", "_allocator", "_lease_store", "_retry_queue")
    )
