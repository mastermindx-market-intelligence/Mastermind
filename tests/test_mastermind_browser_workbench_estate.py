import asyncio
from contextlib import AsyncExitStack
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from integrations.mastermind_browser_plugin.facade import BrowserFacade
from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.workbench_estate import compose_browser_estate_from_workbench
from integrations.workbench_action_mcp.contracts import ActionCaller
from integrations.workbench_browser_mcp.resource_observation import ResourceObservation
from tests.test_mastermind_browser_workbench_transport import Host
from tests.test_mastermind_browser_workbench_composition import OuterCaller, outer_binding, KEY


def local_deployment(host):
    return SimpleNamespace(
        read_tool=host.read, prepare_action=host.prepare, run_action=host.run,
        reconcile_action=host.reconcile, observe_resources=host.observe)


def caller(host):
    return ActionCaller(host.broker.subject_digest, host.broker.client_ref, host.resource,
                        ("workbench.action",), host.now + 600)


def compose(local, remotes, *, clock=None, faults=None, routes=None):
    by_host = {host.name: host for host in remotes}
    faults = faults or {}
    def transport_factory(*, route, now):
        host = by_host[route.host_ref]
        transport = host.transport(faults.get(route.host_ref))
        # The real transport receives the configured route, including its broker.
        transport.route = route
        return transport
    return compose_browser_estate_from_workbench(
        deployment=local_deployment(local), local_host_ref=local.name, broker_caller=caller(local),
        routes=tuple(host.route for host in remotes) if routes is None else routes,
        signing_key=KEY, clock_ms=clock or (lambda: local.now * 1000),
        caller_binding=outer_binding, transport_factory=transport_factory)


def test_real_remote_fleet_degrades_offline_host_but_exact_selection_never_scans_others():
    async def exercise():
        local, remote, offline = Host("local"), Host("remote"), Host("offline")
        outer = OuterCaller("e" * 64, "outer", "https://central.test/mcp")
        estate = compose(local, [remote, offline], faults={"offline": "offline"})
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(remote.app.router.lifespan_context(remote.app))
            await stack.enter_async_context(estate.opened())
            fleet = await estate.owner.browser_fleet(outer, {"limit": 10})
            assert [row["host_ref"] for row in fleet["browsers"]] == ["local", "remote"]
            assert fleet["observation_status"] == "partial"
            assert {row["host_ref"]: row["status"] for row in fleet["hosts"]} == {
                "local": "available", "remote": "available", "offline": "unavailable"}
            selected = next(row["browser_ref"] for row in fleet["browsers"] if row["host_ref"] == "remote")
            local.calls.clear(); offline.http_calls.clear(); remote.calls.clear()
            tabs = await estate.owner.browser_tabs(outer, {"browser_ref": selected})
            assert len(tabs["tabs"]) == 1
            assert not local.calls and not offline.http_calls
            assert remote.calls[0] == ("observe", {"browser_ref": remote.row.browser_ref})
            tab = estate.codec.decode(tabs["tabs"][0]["tab_ref"], now_ms=local.now * 1000)
            assert (tab.host_ref, tab.profile_ref, tab.tab_locator) == ("remote", "profile-remote", 7)
            assert tab.subject_digest == outer.subject_digest
            assert tab.client_ref != remote.broker.client_ref
    asyncio.run(exercise())


def test_route_broker_mismatch_is_unavailable_without_rebinding_outer_identity():
    async def exercise():
        local, remote = Host("local"), Host("remote")
        outer = OuterCaller("e" * 64, "outer")
        estate = compose(local, [remote], routes=(replace(remote.route, broker_subject_digest="d" * 64),))
        async with remote.app.router.lifespan_context(remote.app):
            async with estate.opened():
                fleet = await estate.owner.browser_fleet(outer, {"limit": 10})
                assert [row["host_ref"] for row in fleet["browsers"]] == ["local"]
                assert next(row for row in fleet["hosts"] if row["host_ref"] == "remote")["status"] == "unavailable"
                assert all(row[0] == "observe" for row in remote.calls)
    asyncio.run(exercise())


def test_original_host_reconciliation_survives_expired_refs_and_current_inventory_change():
    async def exercise():
        local, remote = Host("local"), Host("remote")
        clock = [local.now * 1000]
        outer = OuterCaller("e" * 64, "outer")
        estate = compose(local, [remote], clock=lambda: clock[0])
        async with remote.app.router.lifespan_context(remote.app):
            async with estate.opened():
                fleet = await estate.owner.browser_fleet(outer, {"limit": 10})
                session = next(row["browser_ref"] for row in fleet["browsers"] if row["host_ref"] == "remote")
                tab = (await estate.owner.browser_tabs(outer, {"browser_ref": session}))["tabs"][0]["tab_ref"]
                prepared = await estate.owner.prepare_browser_action(outer, {
                    "tab_ref": tab, "action": "create_tab", "args": {"url": "https://child.test"}})
                original = {"tab_ref": tab, "action_ref": prepared["action_ref"]}
                assert (await estate.owner.run_browser_action(outer, original))["effect"] == "APPLIED"
                remote.calls.clear()
                clock[0] += 61_000
                remote.row = replace(remote.row, boot_ref="replacement-boot", connection_generation="replacement")
                result = await estate.owner.reconcile_browser_action(outer, original)
                assert result["effect"] == "APPLIED"
                assert [row[0] for row in remote.calls] == ["reconcile"]
                removed = compose(local, [], clock=lambda: clock[0])
                facade = BrowserFacade(owner=removed.owner, caller_resolver=lambda: outer)
                unavailable = await facade.call("reconcile_browser_action", original)
                assert unavailable["effect"] == "EFFECT_UNKNOWN"
                assert unavailable["retry_allowed"] is False
    asyncio.run(exercise())


def test_fleet_status_is_per_call_and_partial_local_projection_is_preserved():
    async def exercise():
        local = Host("local")
        outer = OuterCaller("e" * 64, "outer")
        count = 0
        async def observations(caller, request):
            nonlocal count
            count += 1
            partial = count == 1
            if partial:
                await asyncio.sleep(0.02)
            return ResourceObservation(local.broker, local.name, local.row.boot_ref, local.now * 1000,
                (local.row,), "partial" if partial else "complete", partial).document()
        local.observe = observations
        estate = compose(local, [])
        results = await asyncio.gather(
            estate.owner.browser_fleet(outer, {"limit": 10}), estate.owner.browser_fleet(outer, {"limit": 10}))
        assert results[0]["observation_status"] == "partial" and results[0]["truncated"] is True
        assert results[1]["observation_status"] == "complete" and results[1]["truncated"] is False
    asyncio.run(exercise())


def test_tab_pages_obey_envelope_budget_and_reach_every_shared_tab():
    from tests.test_mastermind_browser_link_inventory import setup
    async def exercise():
        deployment, composition, outer = setup()
        deployment.raw_ref = "inner-" + "b" * 6000
        deployment.rows = [{"tab_id": i, "origin": "https://example.test", "consent_id": f"consent-{i}",
            "document_revision": 0, "state": "shared", "allow_create": False} for i in range(1, 65)]
        facade = BrowserFacade(owner=composition.owner, caller_resolver=lambda: outer)
        fleet = await facade.call("browser_fleet", {"limit": 10})
        session = fleet["data"]["browsers"][0]["browser_ref"]
        args = {"browser_ref": session}
        all_ids, pages = [], 0
        while True:
            result = await facade.call("browser_tabs", args)
            assert result["is_error"] is False
            assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= 65536
            data = result["data"]
            all_ids.extend(composition.codec.decode(row["tab_ref"], now_ms=deployment.clock[0]).tab_locator
                           for row in data["tabs"])
            pages += 1
            if not data.get("truncated"):
                break
            args["after_tab_id"] = data["next_after_tab_id"]
            assert pages <= 64
        assert pages > 1 and all_ids == list(range(1, 65))
    asyncio.run(exercise())


def test_observation_wire_rejects_foreign_host_and_extra_broker_fields():
    host = Host("host-one")
    observation = ResourceObservation(host.broker, host.name, host.row.boot_ref, host.now * 1000,
                                      (host.row,), "complete", False).document()
    bad = {**observation, "host_ref": "another"}
    with pytest.raises(ValueError):
        ResourceObservation.from_document(bad)
    bad = {**observation, "broker": {**observation["broker"], "expires_at": 1}}
    with pytest.raises(ValueError):
        ResourceObservation.from_document(bad)


def test_returned_large_session_tab_and_action_refs_round_trip_public_facade():
    from tests.test_mastermind_browser_link_inventory import setup
    async def exercise():
        deployment, composition, outer = setup()
        deployment.raw_ref = "inner-" + "b" * 10_900
        deployment.owner_action_ref = "a" * 14_000
        outer = replace(outer, resource="https://central.test/" + "x" * 1900)
        facade = BrowserFacade(owner=composition.owner, caller_resolver=lambda: outer)
        fleet = await facade.call("browser_fleet", {"limit": 10})
        assert not fleet["is_error"]
        session = fleet["data"]["browsers"][0]["browser_ref"]
        assert len(session) > 16_384
        tabs = await facade.call("browser_tabs", {"browser_ref": session})
        assert not tabs["is_error"]
        tab = tabs["data"]["tabs"][0]["tab_ref"]
        assert len(tab) > 16_384
        prepared = await facade.call("prepare_browser_action", {
            "tab_ref": tab, "action": "click", "args": {"element_ref": "element-1"}})
        assert not prepared["is_error"]
        action = prepared["data"]["action_ref"]
        assert len(action) > 16_384
        args = {"tab_ref": tab, "action_ref": action}
        result = await facade.call("run_browser_action", args)
        assert not result["is_error"] and result["effect"] == "APPLIED"
        reconciled = await facade.call("reconcile_browser_action", args)
        assert not reconciled["is_error"] and reconciled["effect"] == "EFFECT_UNKNOWN"
    asyncio.run(exercise())


def test_fleet_pages_reach_all_profiles_on_both_hosts_without_duplicate_selection():
    async def exercise():
        local, remote = Host("local"), Host("remote")
        for host in (local, remote):
            rows = tuple(replace(host.row, profile_ref=f"profile-{i:03d}",
                                browser_ref=host.row.browser_ref + f"-{i:03d}") for i in range(60))
            host.row, host.extra_rows = rows[0], rows[1:]
        outer = OuterCaller("e" * 64, "outer")
        estate = compose(local, [remote])
        facade = BrowserFacade(owner=estate.owner, caller_resolver=lambda: outer)
        async with remote.app.router.lifespan_context(remote.app):
            async with estate.opened():
                args, observed, pages = {"limit": 7}, [], 0
                while True:
                    result = await facade.call("browser_fleet", args)
                    assert not result["is_error"]
                    assert len(json.dumps(result, separators=(",", ":")).encode()) <= 65536
                    data = result["data"]
                    assert data["observation_status"] == "complete"
                    observed.extend((row["host_ref"], row["profile_ref"]) for row in data["browsers"])
                    pages += 1
                    if not data["truncated"]:
                        break
                    args["after_browser_ref"] = data["next_after_browser_ref"]
                    assert pages < 25
                assert observed == [(host, f"profile-{i:03d}") for host in ("local", "remote") for i in range(60)]
    asyncio.run(exercise())


def test_private_owner_pages_connection_projection_beyond_fifty_resources():
    from tests.test_mastermind_browser_link_inventory import LinkDeployment
    from integrations.workbench_browser_mcp.resource_observation import observe_resource_projection
    from integrations.workbench_browser_mcp.deployment import ActiveBrowserProjection
    from integrations.mastermind_browser_link.tool_contract import LINK_TOOL_SCHEMA_DIGEST
    from tests.test_mastermind_browser_workbench_composition import broker_caller
    async def exercise():
        deployment = LinkDeployment()
        active = tuple(ActiveBrowserProjection(
            browser_ref=deployment.raw_ref + f"-{i:03d}",
            resource=replace(deployment.resource, profile_ref=f"profile-{i:03d}")) for i in range(64))
        async def observe(_caller):
            return active
        deployment.observe_active_resources = observe
        def request(args):
            return observe_resource_projection(
                deployment=deployment, caller=broker_caller(), request=args,
                backend_digest=LINK_TOOL_SCHEMA_DIGEST, clock_ms=lambda: deployment.clock[0],
                host_binding=SimpleNamespace(host_id=deployment.resource.host_id,
                                             boot_session_id=deployment.resource.boot_session_id))
        first = await request({"limit": 50})
        assert len(first["resources"]) == 50 and first["truncated"]
        last = first["resources"][-1]
        second = await request({"limit": 50, "after": {key: last[key] for key in
                                ("profile_ref", "browser_instance_ref", "browser_ref")}})
        assert len(second["resources"]) == 14 and not second["truncated"]
        assert [row["profile_ref"] for row in first["resources"] + second["resources"]] == [
            f"profile-{i:03d}" for i in range(64)]
    asyncio.run(exercise())


def test_partial_discovery_requires_restart_even_if_later_page_is_complete():
    async def exercise():
        earlier, later = Host("a-earlier"), Host("b-later")
        later.extra_rows = (replace(later.row, profile_ref="z-later", browser_ref=later.row.browser_ref + "-next"),)
        ready = False
        original = earlier.observe
        async def observe(caller, request):
            if not ready:
                raise RuntimeError("host unavailable")
            return await original(caller, request)
        earlier.observe = observe
        estate = compose(earlier, [later])
        outer = OuterCaller("e" * 64, "outer")
        async with later.app.router.lifespan_context(later.app):
            async with estate.opened():
                first = await estate.owner.browser_fleet(outer, {"limit": 1})
                assert first["restart_required"] and first["observation_status"] == "partial"
                assert first["browsers"][0]["host_ref"] == later.name
                ready = True
                second = await estate.owner.browser_fleet(outer, {
                    "limit": 1, "after_browser_ref": first["next_after_browser_ref"]})
                assert second["observation_status"] == "complete" and not second["restart_required"]
                # Per-call recovery cannot repair a walk that missed an earlier
                # host. Clients retain the first flag and restart discovery.
                assert all(row["host_ref"] == later.name for row in second["browsers"])
                restarted = await estate.owner.browser_fleet(outer, {"limit": 1})
                assert not restarted["restart_required"]
                assert restarted["browsers"][0]["host_ref"] == earlier.name
    asyncio.run(exercise())


def test_late_healthy_host_gets_discovery_attempt_after_slow_prefix(monkeypatch):
    from integrations.mastermind_browser_plugin import workbench_estate as module
    async def exercise():
        monkeypatch.setattr(module, "FLEET_HOST_TIMEOUT_SECONDS", 0.02)
        monkeypatch.setattr(module, "FLEET_TIMEOUT_SECONDS", 0.5)
        queried = []
        healthy = Host("host-16")
        async def observe(request):
            queried.append(healthy.name)
            return await healthy.observe(caller(healthy), request)
        async def stalled(request):
            queried.append("stalled")
            await asyncio.Event().wait()
        endpoints = [module._Endpoint(
            f"host-{i:02d}", healthy.broker, None, stalled, 15) for i in range(16)]
        endpoints.append(module._Endpoint(healthy.name, healthy.broker, None, observe, 15))
        projection = module.WorkbenchEstateProjection(
            endpoints=endpoints, clock_ms=lambda: healthy.now * 1000)
        page = await projection.resource_reader(None, 10)
        assert queried.count("stalled") == 16 and healthy.name in queried
        assert [row.host_ref for row in page] == [healthy.name]
        assert len(page.hosts) == 17
    asyncio.run(exercise())


def test_private_cursor_excludes_completed_profile_prefix_before_status_io(monkeypatch):
    from tests.test_mastermind_browser_link_inventory import LinkDeployment
    from tests.test_mastermind_browser_workbench_composition import broker_caller
    from integrations.workbench_browser_mcp import resource_observation as module
    from integrations.workbench_browser_mcp.deployment import ActiveBrowserProjection
    from integrations.mastermind_browser_link.tool_contract import LINK_TOOL_SCHEMA_DIGEST
    async def exercise():
        deployment = LinkDeployment()
        active = tuple(ActiveBrowserProjection(
            browser_ref=deployment.raw_ref + f"-{i:03d}",
            resource=replace(deployment.resource, profile_ref=f"profile-{i:03d}")) for i in range(64))
        async def observe(_caller):
            return active
        deployment.observe_active_resources = observe
        queried = []
        original = deployment.observe_connection
        async def connection(caller, ref):
            queried.append(ref)
            if int(ref[-3:]) < 50:
                await asyncio.Event().wait()
            return await original(caller, ref)
        deployment.observe_connection = connection
        monkeypatch.setattr(module, "OBSERVATION_TIMEOUT_SECONDS", 0.05)
        result = await module.observe_resource_projection(
            deployment=deployment, caller=broker_caller(),
            request={"limit": 50, "after": {"profile_ref": "profile-049",
                "browser_instance_ref": "f" * 64, "browser_ref": active[49].browser_ref}},
            backend_digest=LINK_TOOL_SCHEMA_DIGEST, clock_ms=lambda: deployment.clock[0],
            host_binding=SimpleNamespace(host_id=deployment.resource.host_id,
                                         boot_session_id=deployment.resource.boot_session_id))
        assert [row["profile_ref"] for row in result["resources"]] == [
            f"profile-{i:03d}" for i in range(50, 64)]
        assert all(int(ref[-3:]) >= 49 for ref in queried)
        assert result["observation_status"] == "partial"
    asyncio.run(exercise())


@pytest.mark.parametrize("with_cursor", [False, True])
def test_private_observation_excludes_valid_isolated_resources_before_profile_sort(with_cursor):
    from control_plane.browser_resource_contract import BrowserMode
    from tests.test_mastermind_browser_workbench_inventory import active, NOW
    from integrations.mastermind_browser_plugin.workbench_inventory import project_active_resource
    from integrations.workbench_browser_mcp.resource_observation import observe_resource_projection
    async def exercise():
        first = active(profile_ref="profile-a")
        second = replace(active(profile_ref="profile-b"), browser_ref=first.browser_ref + "-next")
        isolated = active(mode=BrowserMode.ISOLATED.value, profile_ref=None)
        async def observe(_caller):
            return (first, isolated, second)
        deployment = SimpleNamespace(observe_active_resources=observe)
        projected = project_active_resource(first, now_ms=NOW)
        request = {"limit": 50}
        if with_cursor:
            request["after"] = {key: getattr(projected, key) for key in
                                ("profile_ref", "browser_instance_ref", "browser_ref")}
        result = await observe_resource_projection(
            deployment=deployment, caller=SimpleNamespace(
                subject_digest="a" * 64, client_ref="broker-client", resource="https://workbench.example/browser"),
            request=request, backend_digest="d" * 64, clock_ms=lambda: NOW,
            host_binding=SimpleNamespace(host_id=first.resource.host_id,
                                         boot_session_id=first.resource.boot_session_id))
        assert result["observation_status"] == "complete"
        assert [row["profile_ref"] for row in result["resources"]] == (
            ["profile-b"] if with_cursor else ["profile-a", "profile-b"])
    asyncio.run(exercise())
