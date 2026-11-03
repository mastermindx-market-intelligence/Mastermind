"""Bounded private resource observations from the existing Workbench owner.

This wire projection contains signed resource references and public identities,
never native paths, process identities, grants or credentials. It cannot start,
adopt, renew or move a browser.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, fields

from integrations.mastermind_browser_link.tool_contract import LINK_TOOL_SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.inventory_owner import ActiveBrowserResource, _integer, _token

OBSERVE_RESOURCES_TOOL = "observe_browser_resources"
RESOURCE_OBSERVATION_SCHEMA = "mastermind.workbench_browser_resources.v1"
OBSERVATION_TIMEOUT_SECONDS = 3.0
OBSERVATION_CONCURRENCY = 4

OBSERVE_RESOURCES_INPUT_SCHEMA = {
    "oneOf": [
        {"type": "object", "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            "after": {"type": "object", "properties": {
                "profile_ref": {"type": "string", "minLength": 1, "maxLength": 128},
                "browser_instance_ref": {"type": "string", "minLength": 1, "maxLength": 128},
                "browser_ref": {"type": "string", "minLength": 16, "maxLength": 16384}},
                "required": ["profile_ref", "browser_instance_ref", "browser_ref"], "additionalProperties": False}},
         "required": ["limit"], "additionalProperties": False},
        {"type": "object", "properties": {"browser_ref": {"type": "string", "minLength": 16, "maxLength": 16384}},
         "required": ["browser_ref"], "additionalProperties": False},
    ]
}


@dataclass(frozen=True)
class ResourceObservation:
    broker: BrowserCallerBinding
    host_ref: str
    boot_ref: str
    observed_at_ms: int
    resources: tuple[ActiveBrowserResource, ...]
    observation_status: str
    truncated: bool

    def __post_init__(self):
        if type(self.broker) is not BrowserCallerBinding:
            raise ValueError("resource observation broker invalid")
        self.broker.__post_init__()
        _token(self.host_ref, "host_ref")
        _token(self.boot_ref, "boot_ref")
        _integer(self.observed_at_ms, "observed_at_ms")
        if (type(self.resources) is not tuple or len(self.resources) > 50
                or any(type(row) is not ActiveBrowserResource for row in self.resources)
                or type(self.observation_status) is not str
                or self.observation_status not in {"complete", "partial"} or type(self.truncated) is not bool):
            raise ValueError("resource observation invalid")
        seen = set()
        for row in self.resources:
            row.__post_init__()
            if row.host_ref != self.host_ref or row.boot_ref != self.boot_ref or row.browser_ref in seen:
                raise ValueError("resource observation identity changed")
            seen.add(row.browser_ref)

    def document(self):
        return {"schema": RESOURCE_OBSERVATION_SCHEMA, "broker": asdict(self.broker), "host_ref": self.host_ref, "boot_ref": self.boot_ref,
                "observed_at_ms": self.observed_at_ms, "observation_status": self.observation_status,
                "truncated": self.truncated, "resources": [
                    {**asdict(row), "allowed_actions": list(row.allowed_actions)} for row in self.resources]}

    @classmethod
    def from_document(cls, value):
        keys = {"schema", "broker", "host_ref", "boot_ref", "observed_at_ms", "observation_status", "truncated", "resources"}
        if (type(value) is not dict or set(value) != keys or value["schema"] != RESOURCE_OBSERVATION_SCHEMA
                or type(value["resources"]) is not list or len(value["resources"]) > 50):
            raise ValueError("resource observation invalid")
        broker = value["broker"]
        if type(broker) is not dict or set(broker) != {"subject_digest", "client_ref", "resource"}:
            raise ValueError("resource observation broker invalid")
        broker = BrowserCallerBinding(**broker)
        rows = []
        resource_keys = {field.name for field in fields(ActiveBrowserResource)}
        for raw in value["resources"]:
            if type(raw) is not dict or set(raw) != resource_keys or type(raw["allowed_actions"]) is not list:
                raise ValueError("resource observation invalid")
            rows.append(ActiveBrowserResource(**{**raw, "allowed_actions": tuple(raw["allowed_actions"])}))
        return cls(broker=broker, host_ref=value["host_ref"], boot_ref=value["boot_ref"], observed_at_ms=value["observed_at_ms"],
                   resources=tuple(rows), observation_status=value["observation_status"], truncated=value["truncated"])


async def bounded_resource_projection(items, projector):
    gate = asyncio.Semaphore(OBSERVATION_CONCURRENCY)
    async def project(item):
        async with gate:
            return await projector(item)
    jobs = [asyncio.create_task(project(item)) for item in items]
    partial = False
    rows = []
    try:
        done, pending = await asyncio.wait(jobs, timeout=OBSERVATION_TIMEOUT_SECONDS) if jobs else (set(), set())
        partial = bool(pending)
        for task in done:
            try:
                row = task.result()
            except Exception:
                partial = True
                continue
            if row is not None:
                rows.append(row)
    finally:
        pending = [task for task in jobs if not task.done()]
        for task in pending:
            task.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
    return rows, partial


async def observe_resource_projection(*, deployment, caller, request, backend_digest, clock_ms, host_binding):
    from integrations.mastermind_browser_plugin.link_inventory import LinkWorkbenchInventoryProjection
    from integrations.mastermind_browser_plugin.workbench_inventory import project_active_resource
    if type(request) is not dict:
        raise ValueError("resource observation request invalid")
    source_partial = False
    after_key = None
    if "after" in request:
        after = request["after"]
        if type(after) is not dict or set(after) != {"profile_ref", "browser_instance_ref", "browser_ref"}:
            raise ValueError("resource cursor invalid")
        _token(after["profile_ref"], "profile_ref")
        _token(after["browser_instance_ref"], "browser_instance_ref")
        from integrations.mastermind_browser_plugin.inventory_owner import _browser_ref
        _browser_ref(after["browser_ref"])
        after_key = (after["profile_ref"], after["browser_instance_ref"], after["browser_ref"])
    if "limit" in request and not set(request) - {"limit", "after"}:
        limit = request["limit"]
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("resource observation request invalid")
        with_status = getattr(deployment, "observe_active_resources_with_status", None)
        if callable(with_status):
            active, source_partial = await with_status(caller)
        else:
            active = await deployment.observe_active_resources(caller)
    elif set(request) == {"browser_ref"}:
        limit = 1
        selected = await deployment.observe_active_resource(caller, request["browser_ref"])
        active = () if selected is None else (selected,)
    else:
        raise ValueError("resource observation request invalid")
    if type(active) is not tuple or len(active) > 64:
        raise ValueError("resource observation invalid")
    link = (LinkWorkbenchInventoryProjection(deployment=deployment, broker_caller=caller, clock_ms=clock_ms)
            if backend_digest == LINK_TOOL_SCHEMA_DIGEST else None)
    async def project(item):
        if link is not None:
            return await link._project(item)
        return project_active_resource(item, now_ms=clock_ms())
    # Profile identity is already known before native status I/O. Do not
    # repeatedly spend a later page's deadline on the completed prefix. Keep
    # equal-profile candidates because their full instance key is observed.
    from control_plane.browser_resource_contract import BrowserMode
    candidates = tuple(sorted((item for item in active
        if item.resource.mode != BrowserMode.ISOLATED.value
        and (after_key is None or item.resource.profile_ref >= after_key[0])),
        key=lambda item: (item.resource.profile_ref, item.browser_ref)))
    rows, partial = await bounded_resource_projection(candidates, project)
    rows = [row for row in rows if row.expires_at_ms > clock_ms()]
    rows.sort(key=lambda row: (row.profile_ref, row.browser_instance_ref, row.browser_ref))
    if after_key is not None:
        rows = [row for row in rows if (row.profile_ref, row.browser_instance_ref, row.browser_ref) > after_key]
    selected = list(rows[:limit])
    truncated = len(rows) > limit
    while True:
        document = ResourceObservation(
            broker=BrowserCallerBinding(caller.subject_digest, caller.client_ref, caller.resource),
            host_ref=host_binding.host_id, boot_ref=host_binding.boot_session_id, observed_at_ms=clock_ms(),
            resources=tuple(selected), observation_status="partial" if partial or source_partial else "complete",
            truncated=truncated).document()
        if len(json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 240 * 1024:
            return document
        if not selected:
            raise ValueError("resource observation oversized")
        selected.pop()
        truncated = True
