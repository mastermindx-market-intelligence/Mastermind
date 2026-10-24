from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

import pytest

from control_plane.browser_resource_contract import (
    BrowserMode,
    WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
)
from integrations.mastermind_browser_plugin.catalog import SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.facade import BrowserFacade
from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.workbench_composition import (
    WorkbenchDeploymentEffectPort,
    compose_browser_owner_from_workbench,
)
from integrations.workbench_action_mcp.contracts import ActionCaller
from integrations.workbench_browser_mcp.contracts import BrowserResourceRef
from integrations.workbench_browser_mcp.deployment import ActiveBrowserProjection

NOW = 1_800_000_000_000
KEY = b"k" * 32


@dataclass(frozen=True)
class OuterCaller:
    subject_digest: str
    client_ref: str
    resource: str = "browser-resource"


def outer_binding(caller):
    return BrowserCallerBinding(
        subject_digest=caller.subject_digest,
        client_ref=caller.client_ref,
        resource=caller.resource,
    )


def broker_caller():
    return ActionCaller(
        subject_digest="a" * 64,
        client_ref="browser-broker",
        resource="https://workbench.example/browser",
        scopes=("workbench.action",),
        expires_at=2_000_000_000,
    )


def workbench_resource(*, mode=BrowserMode.PERSISTENT.value, profile_ref="profile-a"):
    return BrowserResourceRef(
        schema="mastermind.workbench_browser_ref.v1",
        start_action_id="c" * 32,
        subject_digest="a" * 64,
        client_ref="browser-broker",
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
        mode=mode,
        profile_ref=profile_ref,
        tool_schema_digest=WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
        issued_at_ms=NOW - 1000,
        expires_at_ms=NOW + 60_000,
    )


def tab_result():
    return {
        "content": [
            {
                "type": "text",
                "text": "### Result\n- 0: (current) [Shared tab](https://example.test/app)",
            }
        ],
        "isError": False,
    }


class FakeDeployment:
    def __init__(self, resource=None):
        resource = resource or workbench_resource()
        self.raw_ref = "wbr-" + "f" * 64
        self.resource = resource
        self.calls = []
        self.owner_action_ref = "owner-action-ref"

    async def observe_active_resources(self, caller):
        self.calls.append(("observe_resources", caller))
        return (
            ActiveBrowserProjection(
                browser_ref=self.raw_ref,
                resource=self.resource,
            ),
        )

    async def observe_tab_group(self, caller, browser_ref):
        self.calls.append(("observe_tabs", caller, browser_ref))
        return tab_result()

    async def read_tool(self, caller, browser_ref, tool, arguments):
        self.calls.append(("read", caller, browser_ref, tool, dict(arguments)))
        return {
            "content": [{"type": "text", "text": "synthetic observation"}],
            "isError": False,
        }

    async def prepare_action(self, caller, browser_ref, tool, arguments):
        self.calls.append(("prepare", caller, browser_ref, tool, dict(arguments)))
        return self.owner_action_ref

    async def run_action(self, caller, browser_ref, action_ref):
        self.calls.append(("run", caller, browser_ref, action_ref))
        return {
            "status": "OK",
            "effect_state": "APPLIED",
            "observed_sha256": "d" * 64,
            "reconciled": False,
        }

    async def reconcile_action(self, caller, browser_ref, action_ref):
        self.calls.append(("reconcile", caller, browser_ref, action_ref))
        return {
            "status": "OK",
            "effect_state": "EFFECT_UNKNOWN",
            "observed_sha256": None,
            "reconciled": True,
        }


def composition(deployment):
    return compose_browser_owner_from_workbench(
        deployment=deployment,
        signing_key=KEY,
        clock_ms=lambda: NOW,
        caller_binding=outer_binding,
        broker_caller=broker_caller(),
        expected_catalog_schema_digest=SCHEMA_DIGEST,
        expected_backend_schema_digest=WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
    )


def session_and_tab(owner, caller):
    fleet = asyncio.run(owner.browser_fleet(caller, {"limit": 10}))
    session_ref = fleet["browsers"][0]["browser_ref"]
    tabs = asyncio.run(owner.browser_tabs(caller, {"browser_ref": session_ref}))
    return session_ref, tabs["tabs"][0]["tab_ref"]


def test_effect_port_always_uses_fixed_workbench_broker_caller():
    deployment = FakeDeployment()
    effect = WorkbenchDeploymentEffectPort(
        deployment=deployment,
        broker_caller=broker_caller(),
    )
    outer = OuterCaller("e" * 64, "outer-a")
    result = asyncio.run(
        effect.call_read_tool(
            outer,
            deployment.raw_ref,
            "browser_snapshot",
            {},
        )
    )
    assert result["isError"] is False
    call = deployment.calls[-1]
    assert call[0] == "read"
    assert call[1] == broker_caller()
    assert call[1] != outer


def test_two_outer_callers_share_one_underlying_tab_but_get_distinct_refs():
    deployment = FakeDeployment()
    owner = composition(deployment).owner
    a = OuterCaller("e" * 64, "outer-a")
    b = OuterCaller("f" * 64, "outer-b")

    session_a, tab_a = session_and_tab(owner, a)
    session_b, tab_b = session_and_tab(owner, b)
    assert session_a != session_b
    assert tab_a != tab_b

    first = asyncio.run(owner.browser_snapshot(a, {"tab_ref": tab_a}))
    second = asyncio.run(owner.browser_snapshot(b, {"tab_ref": tab_b}))
    assert first["isError"] is False
    assert second["isError"] is False
    reads = [row for row in deployment.calls if row[0] == "read"]
    assert len(reads) == 2
    assert {row[2] for row in reads} == {deployment.raw_ref}
    assert all(row[1] == broker_caller() for row in reads)


def test_managed_prepare_and_run_use_original_workbench_effect_owner_once():
    deployment = FakeDeployment()
    owner = composition(deployment).owner
    caller = OuterCaller("e" * 64, "outer-a")
    _session, tab_ref = session_and_tab(owner, caller)

    prepared = asyncio.run(
        owner.prepare_browser_action(
            caller,
            {
                "tab_ref": tab_ref,
                "action": "click",
                "args": {"element_ref": "button-a"},
            },
        )
    )
    assert prepared["action_ref"] != deployment.owner_action_ref
    foreign = OuterCaller("f" * 64, "outer-b")
    _foreign_session, foreign_tab = session_and_tab(owner, foreign)
    with pytest.raises(Exception):
        asyncio.run(
            owner.run_browser_action(
                foreign,
                {
                    "tab_ref": foreign_tab,
                    "action_ref": prepared["action_ref"],
                },
            )
        )
    assert [row[0] for row in deployment.calls].count("run") == 0

    result = asyncio.run(
        owner.run_browser_action(
            caller,
            {
                "tab_ref": tab_ref,
                "action_ref": prepared["action_ref"],
            },
        )
    )
    assert result["effect"] == "APPLIED"
    assert [row[0] for row in deployment.calls].count("prepare") == 1
    assert [row[0] for row in deployment.calls].count("run") == 1


def test_shared_human_action_ref_is_outer_caller_bound_over_same_broker():
    deployment = FakeDeployment(
        workbench_resource(
            mode=BrowserMode.EXTENSION.value,
            profile_ref="profile-human",
        )
    )
    owner = composition(deployment).owner
    a = OuterCaller("e" * 64, "outer-a")
    b = OuterCaller("f" * 64, "outer-b")
    _session_a, tab_a = session_and_tab(owner, a)
    _session_b, tab_b = session_and_tab(owner, b)

    prepared = asyncio.run(
        owner.prepare_browser_action(
            a,
            {
                "tab_ref": tab_a,
                "action": "type",
                "args": {"element_ref": "field-a", "text": "synthetic"},
            },
        )
    )
    assert prepared["action_ref"] != deployment.owner_action_ref
    with pytest.raises(Exception):
        asyncio.run(
            owner.run_browser_action(
                b,
                {
                    "tab_ref": tab_b,
                    "action_ref": prepared["action_ref"],
                },
            )
        )
    assert [row[0] for row in deployment.calls].count("run") == 0

    result = asyncio.run(
        owner.run_browser_action(
            a,
            {
                "tab_ref": tab_a,
                "action_ref": prepared["action_ref"],
            },
        )
    )
    assert result["effect"] == "APPLIED"
    assert [row[0] for row in deployment.calls].count("run") == 1


def test_browser_facade_over_workbench_composition_keeps_closed_seven_tool_catalog():
    deployment = FakeDeployment()
    comp = composition(deployment)
    caller = OuterCaller("e" * 64, "outer-a")
    facade = BrowserFacade(owner=comp.owner, caller_resolver=lambda: caller)
    assert len(facade.catalog()) == 7
    result = asyncio.run(facade.call("browser_fleet", {"limit": 10}))
    assert result["is_error"] is False
    assert len(result["data"]["browsers"]) == 1


def test_workbench_composition_adds_no_scheduler_or_retry_plane():
    deployment = FakeDeployment()
    comp = composition(deployment)
    names = set(comp.__dataclass_fields__)
    for forbidden in {
        "_scheduler",
        "_allocator",
        "_lease_store",
        "_retry_queue",
        "_browser_registry",
    }:
        assert forbidden not in names
