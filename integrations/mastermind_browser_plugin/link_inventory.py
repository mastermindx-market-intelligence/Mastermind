"""Live Link inventory projected through the existing Workbench deployment."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import re

from control_plane.browser_resource_contract import BrowserMode
from integrations.mastermind_browser_link.native_channel import (
    INVENTORY_SCHEMA, record, reference, validate_inventory,
)
from integrations.mastermind_browser_link.tool_contract import (
    LINK_TOOL_SCHEMA_DIGEST, OWNER_INVENTORY_SCHEMA, OWNER_CONNECTION_SCHEMA,
)
from integrations.workbench_browser_mcp.deployment import ActiveBrowserProjection
from integrations.workbench_browser_mcp.contracts import BrowserResourceRef

from .catalog import SCHEMA_DIGEST
from .inventory_owner import ActiveBrowserResource, BrowserTabObservation
from .tab_ref import TabBackend
from .workbench_inventory import (
    WorkbenchDeploymentInventoryProjection, WorkbenchInventoryProjectionError,
    _maybe, _clock, _opaque,
)

LINK_ACTIONS = ("click", "create_tab", "create_window", "navigate", "screenshot", "scroll", "snapshot", "type")
LINK_TAB_ACTIONS = tuple(action for action in LINK_ACTIONS if action not in {"create_tab", "create_window"})
LINK_READS = ("screenshot", "snapshot")
_LINK_OBSERVATION_TTL_MS = 30_000


def native_inventory(value):
    if not isinstance(value, Mapping) or value.get("isError") is not False:
        raise WorkbenchInventoryProjectionError("Link inventory unavailable")
    data = value.get("structuredContent")
    try:
        record(data, {"schema", "instance_id", "connection_generation", "shared_tabs"})
        if data["schema"] != OWNER_INVENTORY_SCHEMA or type(data["instance_id"]) is not str or re.fullmatch(r"[0-9a-f]{64}", data["instance_id"]) is None:
            raise ValueError("invalid Link owner inventory")
        reference(data["connection_generation"])
        validated = validate_inventory({
            "schema": INVENTORY_SCHEMA, "connection_generation": data["connection_generation"],
            "shared_tabs": data["shared_tabs"],
        }, data["connection_generation"])
    except (ValueError, TypeError) as exc:
        raise WorkbenchInventoryProjectionError("Link inventory invalid") from exc
    return {**data, "shared_tabs": validated["shared_tabs"]}


def parse_link_tab_group(value, *, resource, now_ms):
    data = native_inventory(value)
    now = _clock(now_ms)
    if (type(resource) is not ActiveBrowserResource
            or resource.backend_schema_digest != LINK_TOOL_SCHEMA_DIGEST
            or resource.backend != TabBackend.SHARED_HUMAN.value
            or data["instance_id"] != resource.browser_instance_ref
            or data["connection_generation"] != resource.connection_generation
            or resource.expires_at_ms <= now):
        raise WorkbenchInventoryProjectionError("Link generation changed")
    expires = min(resource.expires_at_ms, now + _LINK_OBSERVATION_TTL_MS)
    rows = []
    for item in data["shared_tabs"]:
        if item["state"] in {"busy", "navigating"}:
            continue
        capability = (LINK_READS if item["state"] == "effect_unresolved" else
                      LINK_ACTIONS if item["allow_create"] else LINK_TAB_ACTIONS)
        actions = tuple(sorted(set(capability) & set(resource.allowed_actions)))
        if not actions:
            continue
        rows.append(BrowserTabObservation(
            browser_ref=resource.browser_ref, tab_locator=item["tab_id"],
            document_revision=item["document_revision"], title=f"Shared tab {item['tab_id']}",
            url=item["origin"], observed_at_ms=now, expires_at_ms=expires,
            connection_generation=data["connection_generation"],
            consent_ref=item["consent_id"], allowed_actions=actions,
        ))
    return tuple(rows)


class LinkWorkbenchInventoryProjection(WorkbenchDeploymentInventoryProjection):
    """Select only currently connected, owner-admitted Link profiles."""

    async def _active(self):
        raw = await _maybe(self._deployment.observe_active_resources(self._broker_caller))
        if isinstance(raw, (str, bytes, bytearray)) or not isinstance(raw, Sequence) or len(raw) > 64:
            raise WorkbenchInventoryProjectionError("resource projection is invalid")
        return raw

    async def _project(self, item):
        if type(item) is not ActiveBrowserProjection:
            raise WorkbenchInventoryProjectionError("resource projection is invalid")
        resource = item.resource
        if type(resource) is not BrowserResourceRef:
            raise WorkbenchInventoryProjectionError("resource projection is invalid")
        if resource.tool_schema_digest != LINK_TOOL_SCHEMA_DIGEST or resource.mode != BrowserMode.EXTENSION.value:
            raise WorkbenchInventoryProjectionError("Link backend changed")
        if resource.expires_at_ms <= self._now():
            return None
        data = await _maybe(self._deployment.observe_connection(self._broker_caller, item.browser_ref))
        try:
            record(data, {"schema", "instance_id", "connected"}, {"connection_generation"})
            if (data["schema"] != OWNER_CONNECTION_SCHEMA or type(data["connected"]) is not bool
                    or type(data["instance_id"]) is not str or re.fullmatch(r"[0-9a-f]{64}", data["instance_id"]) is None):
                raise ValueError("invalid Link connection")
            if not data["connected"]:
                if "connection_generation" in data:
                    raise ValueError("disconnected generation")
                return None
            reference(data.get("connection_generation"))
        except (ValueError, TypeError) as exc:
            raise WorkbenchInventoryProjectionError("Link connection invalid") from exc
        if resource.expires_at_ms <= self._now():
            return None
        # This status advertises a qualified connected channel, not page facts.
        # A selected profile must answer a fresh native inventory before tabs
        # or actions can be authorized.
        return ActiveBrowserResource(
            backend=TabBackend.SHARED_HUMAN.value, browser_ref=item.browser_ref,
            host_ref=resource.host_id, boot_ref=resource.boot_session_id,
            profile_ref=resource.profile_ref, browser_instance_ref=data["instance_id"],
            connection_generation=data["connection_generation"],
            consent_ref=_opaque("profile-", resource.profile_ref),
            allowed_actions=LINK_ACTIONS, catalog_schema_digest=SCHEMA_DIGEST,
            backend_schema_digest=LINK_TOOL_SCHEMA_DIGEST, expires_at_ms=resource.expires_at_ms,
        )

    async def resource_reader(self, _outer_caller, limit, *, after=None):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise WorkbenchInventoryProjectionError("limit is invalid")
        from integrations.workbench_browser_mcp.resource_observation import bounded_resource_projection, ResourceObservation
        from .inventory_owner import BrowserResourcePage, BrowserHostObservation
        observe = getattr(self._deployment, "observe_resources", None)
        if callable(observe):
            request = {"limit": limit}
            if after is not None:
                request["after"] = {name: getattr(after, name) for name in
                                    ("profile_ref", "browser_instance_ref", "browser_ref")}
            result = ResourceObservation.from_document(await _maybe(observe(self._broker_caller, request)))
            return BrowserResourcePage(
                result.resources, (BrowserHostObservation(
                    result.host_ref, "partial" if result.observation_status == "partial" else "available",
                    result.boot_ref, result.observed_at_ms),), result.truncated)
        projected, _partial = await bounded_resource_projection(await self._active(), self._project)
        projected.sort(key=lambda row: (row.host_ref, row.profile_ref, row.browser_instance_ref, row.browser_ref))
        if after is not None:
            projected = [row for row in projected if (row.host_ref, row.profile_ref, row.browser_instance_ref, row.browser_ref)
                         > (after.host_ref, after.profile_ref, after.browser_instance_ref, after.browser_ref)]
        # Compatibility projections retain the legacy tuple when complete.
        if len(projected) > limit:
            hosts = {(row.host_ref, row.boot_ref) for row in projected}
            return BrowserResourcePage(tuple(projected[:limit]), tuple(BrowserHostObservation(
                host, "partial" if _partial else "available", boot, self._now()) for host, boot in sorted(hosts)), True)
        return tuple(projected[:limit])

    async def resource_lookup(self, _outer_caller, selected):
        browser_ref = selected if type(selected) is str else selected.browser_ref
        lookup = getattr(self._deployment, "observe_active_resource", None)
        if callable(lookup):
            item = await _maybe(lookup(self._broker_caller, browser_ref))
            return None if item is None else await self._project(item)
        # Compatibility for inert test/legacy projections without the new seam.
        matches = [item for item in await self._active() if item.browser_ref == browser_ref]
        return None if len(matches) != 1 else await self._project(matches[0])

    async def tab_reader(self, _outer_caller, resource):
        if type(resource) is not ActiveBrowserResource:
            raise WorkbenchInventoryProjectionError("browser resource is invalid")
        raw = await _maybe(self._deployment.observe_tab_group(self._broker_caller, resource.browser_ref))
        return parse_link_tab_group(raw, resource=resource, now_ms=self._now())
