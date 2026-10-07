from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from control_plane.browser_resource_contract import BrowserMode
from integrations.mastermind_browser_plugin.catalog import SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.workbench_service import (
    WorkbenchBrowserFabricComposition,
    browser_broker_caller_from_lease,
    browser_caller_binding_from_action_caller,
    compose_workbench_browser_fabric,
    create_workbench_browser_fabric_http_app,
    derive_browser_signing_key,
)
from integrations.workbench_action_mcp.contracts import ActionCaller
from integrations.workbench_browser_mcp.contracts import BrowserResourceRef
from integrations.workbench_browser_mcp.deployment import ActiveBrowserProjection

NOW = 1_800_000_000_000
ACTION_KEY = b"a" * 32
BACKEND_DIGEST = "d" * 64


@dataclass(frozen=True)
class LeaseFixture:
    expected_subject_digest: str = "b" * 64
    expected_client_ref: str = "broker-client"
    resource: str = "https://workbench.example/browser"
    required_scopes: tuple[str, ...] = ("workbench.action",)
    project_ref: str = "project:browser"
    context_ref: str = "context:browser"
    responsibility_ref: str = "responsibility:browser"
    operation_ref: str = "operation:browser"
    owner_ref: str = "owner:browser"
    generation: str = "generation:browser"
    allowed_paths: tuple[str, ...] = ("browser/**",)
    committed_head: str | None = None
    lease_expires_at_ms: int = NOW + 60_000


def lease():
    return LeaseFixture()


def broker():
    return browser_broker_caller_from_lease(lease())


@dataclass(frozen=True)
class Outer:
    subject_digest: str = "e" * 64
    client_ref: str = "outer-client"
    resource: str = "browser-resource"
    scopes: tuple[str, ...] = ("browser.control",)
    expires_at: int = 2_000_000_000


def resource_ref(mode=BrowserMode.PERSISTENT.value, *, profile_ref="profile-a"):
    return BrowserResourceRef(
        schema="mastermind.workbench_browser_ref.v1",
        start_action_id="c" * 32,
        subject_digest=broker().subject_digest,
        client_ref=broker().client_ref,
        resource=broker().resource,
        project_ref=lease().project_ref,
        context_ref=lease().context_ref,
        responsibility_ref=lease().responsibility_ref,
        operation_ref=lease().operation_ref,
        owner_ref=lease().owner_ref,
        generation=lease().generation,
        host_id="f" * 64,
        boot_session_id="boot:browser",
        relay_pid=4321,
        relay_start_identity="1700000000.000001",
        relay_pgid=4321,
        relay_session_id=4321,
        mode=mode,
        profile_ref=profile_ref,
        tool_schema_digest=BACKEND_DIGEST,
        issued_at_ms=NOW - 1000,
        expires_at_ms=NOW + 60_000,
    )


class FakeDeployment:
    def __init__(self):
        self.inner_callers = []
        self.actions = []
        self.browser_ref = "wbr-" + "f" * 64

    async def observe_active_resources(self, caller):
        self.inner_callers.append(("fleet", caller))
        return (ActiveBrowserProjection(browser_ref=self.browser_ref, resource=resource_ref()),)

    async def observe_tab_group(self, caller, browser_ref):
        self.inner_callers.append(("tabs", caller, browser_ref))
        return {
            "content": [{
                "type": "text",
                "text": "### Result\n- 0: (current) [Example](https://example.test/path?secret=x#frag)",
            }],
            "isError": False,
        }

    async def read_tool(self, caller, browser_ref, tool, arguments):
        self.inner_callers.append(("read", caller, browser_ref, tool, dict(arguments)))
        return {
            "content": [{"type": "text", "text": "synthetic"}],
            "structuredContent": {"kind": "snapshot"},
            "isError": False,
        }

    async def prepare_action(self, caller, browser_ref, tool, arguments):
        self.inner_callers.append(("prepare", caller, browser_ref, tool, dict(arguments)))
        self.actions.append(("prepare", tool))
        return "owner-action-ref"

    async def run_action(self, caller, browser_ref, action_ref):
        self.inner_callers.append(("run", caller, browser_ref, action_ref))
        self.actions.append(("run", action_ref))
        return {
            "status": "OK",
            "effect_state": "APPLIED",
            "observed_sha256": "1" * 64,
            "reconciled": False,
        }

    async def reconcile_action(self, caller, browser_ref, action_ref):
        self.inner_callers.append(("reconcile", caller, browser_ref, action_ref))
        return {
            "status": "OK",
            "effect_state": "EFFECT_UNKNOWN",
            "observed_sha256": None,
            "reconciled": True,
        }


def test_browser_signing_key_is_domain_separated_and_deterministic():
    first = derive_browser_signing_key(ACTION_KEY)
    second = derive_browser_signing_key(ACTION_KEY)
    assert first == second
    assert first != ACTION_KEY
    assert isinstance(first, bytes)
    assert len(first) == 32
    with pytest.raises(TypeError):
        derive_browser_signing_key(b"short")


def test_broker_caller_is_exact_projection_of_existing_stable_lease():
    selected = broker()
    assert selected == ActionCaller(
        subject_digest=lease().expected_subject_digest,
        client_ref=lease().expected_client_ref,
        resource=lease().resource,
        scopes=lease().required_scopes,
        expires_at=lease().lease_expires_at_ms // 1000,
    )


def test_outer_caller_binding_is_not_the_workbench_broker_identity():
    outer = ActionCaller(
        subject_digest=Outer().subject_digest,
        client_ref=Outer().client_ref,
        resource=Outer().resource,
        scopes=Outer().scopes,
        expires_at=Outer().expires_at,
    )
    binding = browser_caller_binding_from_action_caller(outer)
    assert binding == BrowserCallerBinding(
        subject_digest=Outer().subject_digest,
        client_ref=Outer().client_ref,
        resource=Outer().resource,
    )
    assert binding.client_ref != broker().client_ref


def test_composition_routes_live_inventory_and_effects_through_one_fixed_broker():
    deployment = FakeDeployment()
    fabric = compose_workbench_browser_fabric(
        deployment=deployment,
        action_token_key=ACTION_KEY,
        clock_ms=lambda: NOW,
        caller_binding=browser_caller_binding_from_action_caller,
        broker_caller=broker(),
        expected_catalog_schema_digest=SCHEMA_DIGEST,
        expected_backend_schema_digest=BACKEND_DIGEST,
    )
    assert isinstance(fabric, WorkbenchBrowserFabricComposition)
    outer = ActionCaller(
        subject_digest=Outer().subject_digest,
        client_ref=Outer().client_ref,
        resource=Outer().resource,
        scopes=Outer().scopes,
        expires_at=Outer().expires_at,
    )
    fleet = asyncio.run(fabric.owner.browser_fleet(outer, {"limit": 10}))
    assert len(fleet["browsers"]) == 1
    assert deployment.browser_ref not in repr(fleet)
    session = fleet["browsers"][0]["browser_ref"]

    tabs = asyncio.run(fabric.owner.browser_tabs(outer, {"browser_ref": session}))
    assert len(tabs["tabs"]) == 1
    assert tabs["tabs"][0]["url"] == "https://example.test/path"
    assert "secret" not in repr(tabs)
    tab_ref = tabs["tabs"][0]["tab_ref"]

    snapshot = asyncio.run(fabric.owner.browser_snapshot(outer, {"tab_ref": tab_ref}))
    assert snapshot["structuredContent"]["kind"] == "snapshot"

    prepared = asyncio.run(
        fabric.owner.prepare_browser_action(
            outer,
            {
                "tab_ref": tab_ref,
                "action": "click",
                "args": {"element_ref": "element-a"},
            },
        )
    )
    assert prepared["action_ref"] != "owner-action-ref"
    run = asyncio.run(
        fabric.owner.run_browser_action(
            outer,
            {"tab_ref": tab_ref, "action_ref": prepared["action_ref"]},
        )
    )
    assert run["effect"] == "APPLIED"

    assert deployment.actions == [
        ("prepare", "browser_click"),
        ("run", "owner-action-ref"),
    ]
    inner = [row[1] for row in deployment.inner_callers]
    assert inner
    assert all(value == broker() for value in inner)
    assert all(value != outer for value in inner)


def test_composition_creates_no_listener_registry_or_tunnel():
    fabric = compose_workbench_browser_fabric(
        deployment=FakeDeployment(),
        action_token_key=ACTION_KEY,
        clock_ms=lambda: NOW,
        caller_binding=browser_caller_binding_from_action_caller,
        broker_caller=broker(),
        expected_catalog_schema_digest=SCHEMA_DIGEST,
        expected_backend_schema_digest=BACKEND_DIGEST,
    )
    names = set(fabric.__dataclass_fields__)
    for forbidden in {
        "server",
        "listener",
        "tunnel",
        "registry",
        "scheduler",
        "lease_store",
        "retry_queue",
    }:
        assert forbidden not in names


def test_http_fabric_uses_exact_route_and_isolates_outer_callers():
    httpx = pytest.importorskip("httpx")

    deployment = FakeDeployment()
    alice = ActionCaller(
        subject_digest="e" * 64,
        client_ref="alice-client",
        resource="browser-resource",
        scopes=("browser.control",),
        expires_at=2_000_000_000,
    )
    bob = ActionCaller(
        subject_digest="f" * 64,
        client_ref="bob-client",
        resource="browser-resource",
        scopes=("browser.control",),
        expires_at=2_000_000_000,
    )

    async def authenticate(request):
        return {"alice": alice, "bob": bob}.get(
            request.headers.get("x-fixture-caller")
        )

    fabric = create_workbench_browser_fabric_http_app(
        deployment=deployment,
        action_token_key=ACTION_KEY,
        clock_ms=lambda: NOW,
        caller_binding=browser_caller_binding_from_action_caller,
        broker_caller=broker(),
        authenticate=authenticate,
        auth_challenge=(
            'Bearer resource_metadata='
            '"https://browser.test/.well-known/oauth-protected-resource"'
        ),
        allowed_hosts=["browser.test"],
        expected_catalog_schema_digest=SCHEMA_DIGEST,
        expected_backend_schema_digest=BACKEND_DIGEST,
    )
    app = fabric.app
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "browser-fabric-test", "version": "1"},
        },
    }

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://browser.test",
            ) as client:
                base = {
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                }
                assert (
                    await client.post("/browser-fabric", json=init, headers=base)
                ).status_code == 401
                initialized = await client.post(
                    "/browser-fabric",
                    json=init,
                    headers={**base, "x-fixture-caller": "alice"},
                )
                assert initialized.status_code == 200
                assert (
                    initialized.json()["result"]["serverInfo"]["name"]
                    == "mastermind-browser"
                )
                tools = await client.post(
                    "/browser-fabric",
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    headers={**base, "x-fixture-caller": "alice"},
                )
                assert len(tools.json()["result"]["tools"]) == 7

                async def call(who, name, arguments, call_id):
                    response = await client.post(
                        "/browser-fabric",
                        headers={**base, "x-fixture-caller": who},
                        json={
                            "jsonrpc": "2.0",
                            "id": call_id,
                            "method": "tools/call",
                            "params": {"name": name, "arguments": arguments},
                        },
                    )
                    assert response.status_code == 200, response.text
                    return response.json()["result"]

                fleet_a = await call(
                    "alice", "browser_fleet", {"limit": 10}, 3
                )
                fleet_b = await call(
                    "bob", "browser_fleet", {"limit": 10}, 4
                )
                session_a = fleet_a["structuredContent"]["data"]["browsers"][0][
                    "browser_ref"
                ]
                session_b = fleet_b["structuredContent"]["data"]["browsers"][0][
                    "browser_ref"
                ]
                assert session_a != session_b
                assert deployment.browser_ref not in session_a
                assert deployment.browser_ref not in session_b

                tabs_a = await call(
                    "alice",
                    "browser_tabs",
                    {"browser_ref": session_a},
                    5,
                )
                tab_ref = tabs_a["structuredContent"]["data"]["tabs"][0][
                    "tab_ref"
                ]
                wrong = await call(
                    "bob",
                    "browser_tabs",
                    {"browser_ref": session_a},
                    6,
                )
                assert wrong["isError"] is True
                assert (
                    wrong["structuredContent"]["code"]
                    == "CALLER_BINDING_CHANGED"
                )

                snapshot = await call(
                    "alice",
                    "browser_snapshot",
                    {"tab_ref": tab_ref},
                    7,
                )
                assert snapshot["isError"] is False
                assert (
                    snapshot["structuredContent"]["data"]["structuredContent"][
                        "kind"
                    ]
                    == "snapshot"
                )

                wrong_host = await client.post(
                    "/browser-fabric",
                    json=init,
                    headers={
                        **base,
                        "x-fixture-caller": "alice",
                        "host": "attacker.test",
                    },
                )
                assert wrong_host.status_code == 421
                assert (
                    await client.post(
                        "/mcp",
                        json=init,
                        headers={**base, "x-fixture-caller": "alice"},
                    )
                ).status_code == 404

    asyncio.run(exercise())
