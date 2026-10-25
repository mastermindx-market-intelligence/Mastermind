"""Central routing over existing local and remote Workbench Browser owners.

Only fixed deployment configuration selects routes. The estate has one signed
inventory surface, while each Workbench retains its resources, actions and
reconciliation. Observations are per invocation; there is no last-known fleet
cache, implicit host fallback or action retry.
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from types import MappingProxyType

from integrations.mastermind_browser_link.tool_contract import INVENTORY_TOOL, LINK_TOOL_SCHEMA_DIGEST
from integrations.workbench_browser_mcp.resource_observation import ResourceObservation
from .catalog import SCHEMA_DIGEST
from .inventory_owner import BrowserHostObservation, BrowserInventoryOwner, BrowserResourcePage
from .link_inventory import parse_link_tab_group
from .owner_adapter import BrowserCallerBinding, BrowserLinkProjector, SharedHumanBrowserOwnerAdapter
from .owner_router import HostRoutedBrowserOwnerRouter
from .tab_ref import BrowserTabRefCodec, TabBackend
from .workbench_client import WorkbenchBrowserClientError, WorkbenchBrowserMcpEffectPort
from .workbench_composition import WorkbenchDeploymentEffectPort
from .workbench_transport import MAX_HOST_ROUTES, WorkbenchHostRoute, WorkbenchHostTransport

FLEET_TIMEOUT_SECONDS = 20.0
FLEET_CONCURRENCY = 4
# At most 17 hosts need five waves. Every host gets an attempt within the
# global budget even when the first four routes do not respond.
FLEET_HOST_TIMEOUT_SECONDS = 3.5
MAX_OBSERVATION_AGE_MS = 60_000
MAX_CLOCK_SKEW_MS = 5_000


@dataclass(frozen=True)
class _Endpoint:
    host_ref: str
    broker: BrowserCallerBinding
    effect_port: object
    observe_resources: object
    timeout_seconds: float

    async def observe(self, request, clock_ms):
        value = await self.observe_resources(request)
        result = value if type(value) is ResourceObservation else ResourceObservation.from_document(value)
        result.__post_init__()
        now = clock_ms()
        if (result.host_ref != self.host_ref or result.broker != self.broker
                or not now - MAX_OBSERVATION_AGE_MS <= result.observed_at_ms <= now + MAX_CLOCK_SKEW_MS
                or any(row.backend_schema_digest != LINK_TOOL_SCHEMA_DIGEST
                       or row.backend != TabBackend.SHARED_HUMAN.value
                       or row.catalog_schema_digest != SCHEMA_DIGEST for row in result.resources)):
            raise WorkbenchBrowserClientError("REMOTE_OBSERVATION_BINDING_CHANGED")
        return result


class WorkbenchEstateProjection:
    def __init__(self, *, endpoints, clock_ms):
        if not endpoints or len(endpoints) > MAX_HOST_ROUTES + 1 or not callable(clock_ms):
            raise TypeError("bounded fixed browser estate required")
        by_host = {item.host_ref: item for item in endpoints}
        if len(by_host) != len(endpoints):
            raise ValueError("browser estate host duplicated")
        self.endpoints = MappingProxyType(by_host)
        self._clock_ms = clock_ms

    async def resource_reader(self, _caller, limit, *, after=None):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("browser fleet limit invalid")
        gate = asyncio.Semaphore(FLEET_CONCURRENCY)
        async def observe(endpoint):
            async with gate:
                try:
                    async with asyncio.timeout(min(endpoint.timeout_seconds, FLEET_HOST_TIMEOUT_SECONDS)):
                        request = {"limit": limit}
                        if after is not None and endpoint.host_ref == after.host_ref:
                            request["after"] = {name: getattr(after, name) for name in
                                                ("profile_ref", "browser_instance_ref", "browser_ref")}
                        result = await endpoint.observe(request, self._clock_ms)
                    return result
                except Exception:
                    return None
        jobs = {asyncio.create_task(observe(item)): item for item in self.endpoints.values()}
        try:
            done, _pending = await asyncio.wait(jobs, timeout=FLEET_TIMEOUT_SECONDS)
            rows, hosts, truncated = [], [], False
            for task, endpoint in jobs.items():
                result = task.result() if task in done and not task.cancelled() else None
                if result is None:
                    hosts.append(BrowserHostObservation(endpoint.host_ref, "unavailable", None, None))
                else:
                    hosts.append(BrowserHostObservation(
                        endpoint.host_ref, "partial" if result.observation_status == "partial" else "available",
                        result.boot_ref, result.observed_at_ms))
                    rows.extend(row for row in result.resources if row.expires_at_ms > self._clock_ms()
                                and (after is None or (row.host_ref, row.profile_ref, row.browser_instance_ref, row.browser_ref)
                                     > (after.host_ref, after.profile_ref, after.browser_instance_ref, after.browser_ref)))
                    if after is None or endpoint.host_ref >= after.host_ref:
                        truncated = truncated or result.truncated
            rows.sort(key=lambda row: (row.host_ref, row.profile_ref, row.browser_instance_ref, row.browser_ref))
            hosts.sort(key=lambda row: row.host_ref)
            return BrowserResourcePage(tuple(rows[:limit]), tuple(hosts), truncated or len(rows) > limit)
        finally:
            for task in jobs:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)

    def endpoint(self, signed):
        # Callers supply an already verified signed session/tab or an internal
        # resource projection. No endpoint can come from tool arguments.
        endpoint = self.endpoints.get(signed.host_ref)
        if endpoint is None or signed.backend != TabBackend.SHARED_HUMAN.value:
            raise WorkbenchBrowserClientError("ORIGINAL_ROUTE_UNAVAILABLE")
        return endpoint

    async def resource_lookup(self, _caller, signed):
        endpoint = self.endpoint(signed)
        async with asyncio.timeout(endpoint.timeout_seconds):
            result = await endpoint.observe({"browser_ref": signed.browser_ref}, self._clock_ms)
        if (result.truncated or result.observation_status != "complete" or len(result.resources) > 1
                or any(row.browser_ref != signed.browser_ref for row in result.resources)):
            raise WorkbenchBrowserClientError("EXACT_OBSERVATION_UNAVAILABLE")
        return result.resources[0] if result.resources else None

    async def tab_reader(self, _caller, resource):
        endpoint = self.endpoint(resource)
        async with asyncio.timeout(endpoint.timeout_seconds):
            value = await endpoint.effect_port.call_read_tool(
                endpoint.broker, resource.browser_ref, INVENTORY_TOOL, {})
        return parse_link_tab_group(value, resource=resource, now_ms=self._clock_ms())


@dataclass(frozen=True)
class WorkbenchEstateComposition:
    codec: BrowserTabRefCodec
    inventory: BrowserInventoryOwner
    router: HostRoutedBrowserOwnerRouter
    projection: WorkbenchEstateProjection
    transports: tuple[WorkbenchHostTransport, ...]

    @property
    def owner(self):
        return self.router

    @asynccontextmanager
    async def opened(self):
        # Opening reserves transport lifecycle only; an offline host cannot
        # prevent other hosts or the central listener from starting.
        async with AsyncExitStack() as stack:
            for transport in self.transports:
                await stack.enter_async_context(transport.opened())
            yield self


def compose_browser_estate_from_workbench(
    *, deployment, local_host_ref, broker_caller, signing_key, clock_ms,
    caller_binding, routes, transport_factory=WorkbenchHostTransport,
):
    if type(routes) is not tuple or any(type(route) is not WorkbenchHostRoute for route in routes):
        raise TypeError("reviewed browser routes required")
    if len(routes) > MAX_HOST_ROUTES or not callable(transport_factory):
        raise TypeError("bounded browser routes required")
    local_identity = BrowserCallerBinding(
        broker_caller.subject_digest, broker_caller.client_ref, broker_caller.resource)
    local_port = WorkbenchDeploymentEffectPort(deployment=deployment, broker_caller=broker_caller)
    async def local_observation(request):
        return await deployment.observe_resources(broker_caller, request)
    endpoints = [_Endpoint(local_host_ref, local_identity, local_port, local_observation, 10.0)]
    transports = []
    for route in routes:
        route.__post_init__()
        transport = transport_factory(route=route, now=lambda: clock_ms() // 1000)
        port = WorkbenchBrowserMcpEffectPort(
            call_tool=transport.call_tool, expected_backend_schema_digest=route.backend_schema_digest)
        endpoints.append(_Endpoint(route.host_ref, route.broker, port, port.observe_resources, route.timeout_seconds))
        transports.append(transport)
    projection = WorkbenchEstateProjection(endpoints=endpoints, clock_ms=clock_ms)
    codec = BrowserTabRefCodec(signing_key)
    inventory = BrowserInventoryOwner(
        codec=codec, clock_ms=clock_ms, caller_binding=caller_binding,
        resource_reader=projection.resource_reader, resource_lookup=projection.resource_lookup,
        tab_reader=projection.tab_reader, expected_catalog_schema_digest=SCHEMA_DIGEST)
    owners = {}
    for endpoint in endpoints:
        owners[endpoint.host_ref] = SharedHumanBrowserOwnerAdapter(
            broker_caller=endpoint.broker, codec=codec, clock_ms=clock_ms, caller_binding=caller_binding,
            revalidate_tab=inventory.revalidate_tab, effect_port=endpoint.effect_port,
            projector=BrowserLinkProjector(), fleet_reader=inventory.browser_fleet,
            tabs_reader=inventory.browser_tabs, expected_catalog_schema_digest=SCHEMA_DIGEST,
            expected_backend_schema_digest=LINK_TOOL_SCHEMA_DIGEST)
    fixed_owners = MappingProxyType(owners)
    def resolve(_caller, tab):
        # Deliberately no freshness, boot, inventory or schema test here:
        # old action references must still reach their original durable owner.
        if tab.backend != TabBackend.SHARED_HUMAN.value or tab.host_ref not in fixed_owners:
            raise WorkbenchBrowserClientError("ORIGINAL_ROUTE_UNAVAILABLE")
        return fixed_owners[tab.host_ref]
    router = HostRoutedBrowserOwnerRouter(
        codec=codec, clock_ms=clock_ms, caller_binding=caller_binding,
        inventory_owner=inventory, owner_resolver=resolve)
    return WorkbenchEstateComposition(codec, inventory, router, projection, tuple(transports))
