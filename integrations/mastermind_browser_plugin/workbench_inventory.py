"""Project one live Workbench Browser deployment into Browser fleet facts.

This is a read projection only. Workbench Browser remains the resource/effect
owner; BrowserInventoryOwner remains the caller-bound ref projector. No browser
is started, selected, ranked, leased, retried, or persisted here.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import inspect
import re
from typing import Any

from control_plane.browser_resource_contract import BrowserMode
from integrations.workbench_action_mcp.contracts import ActionCaller
from integrations.workbench_browser_mcp.contracts import BrowserResourceRef
from integrations.workbench_browser_mcp.deployment import ActiveBrowserProjection

from .catalog import SCHEMA_DIGEST
from .inventory_owner import ActiveBrowserResource, BrowserTabObservation
from .tab_ref import TabBackend

_SHAREABLE_ACTIONS = (
    "click",
    "navigate",
    "screenshot",
    "snapshot",
    "type",
)
_TAB_LINE = re.compile(
    r"^- (?P<index>[0-9]+):(?P<current> \(current\))? "
    r"\[(?P<title>.*)\]\((?P<url>https?://.*)\)$"
)
_TAB_OBSERVATION_TTL_MS = 5_000


class WorkbenchInventoryProjectionError(ValueError):
    """A live Workbench projection could not be represented safely."""


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _clock(value: object) -> int:
    if type(value) is not int or not 0 <= value < 2**63:
        raise WorkbenchInventoryProjectionError("clock is invalid")
    return value


def _opaque(prefix: str, *parts: object) -> str:
    raw = "\x00".join(str(part) for part in parts).encode("utf-8")
    return prefix + hashlib.sha256(raw).hexdigest()


def project_active_resource(
    value: ActiveBrowserProjection,
    *,
    now_ms: int,
) -> ActiveBrowserResource | None:
    """Project one already-started persistent/extension resource.

    Isolated worker resources intentionally stay outside the shared fleet.
    """
    now = _clock(now_ms)
    if type(value) is not ActiveBrowserProjection:
        raise WorkbenchInventoryProjectionError("active projection is invalid")
    resource = value.resource
    if type(resource) is not BrowserResourceRef:
        raise WorkbenchInventoryProjectionError("browser resource is invalid")
    if resource.expires_at_ms <= now:
        return None
    if resource.mode == BrowserMode.ISOLATED.value:
        return None
    if (
        resource.mode not in {
            BrowserMode.PERSISTENT.value,
            BrowserMode.EXTENSION.value,
        }
        or type(resource.profile_ref) is not str
        or not resource.profile_ref
    ):
        raise WorkbenchInventoryProjectionError("shareable browser profile is invalid")

    instance_ref = _opaque(
        "browser-",
        resource.host_id,
        resource.boot_session_id,
        resource.start_action_id,
        resource.relay_pid,
        resource.relay_start_identity,
    )
    connection_generation = "conn-" + resource.start_action_id
    if resource.mode == BrowserMode.EXTENSION.value:
        backend = TabBackend.SHARED_HUMAN.value
        consent_ref = _opaque(
            "consent-",
            instance_ref,
            resource.profile_ref,
            connection_generation,
        )
    else:
        backend = TabBackend.MANAGED.value
        consent_ref = None

    return ActiveBrowserResource(
        backend=backend,
        browser_ref=value.browser_ref,
        host_ref=resource.host_id,
        boot_ref=resource.boot_session_id,
        profile_ref=resource.profile_ref,
        browser_instance_ref=instance_ref,
        connection_generation=connection_generation,
        consent_ref=consent_ref,
        allowed_actions=_SHAREABLE_ACTIONS,
        catalog_schema_digest=SCHEMA_DIGEST,
        backend_schema_digest=resource.tool_schema_digest,
        expires_at_ms=resource.expires_at_ms,
    )


def _result_lines(value: object) -> tuple[str, ...]:
    if not isinstance(value, Mapping) or value.get("isError") is True:
        raise WorkbenchInventoryProjectionError("tab result is invalid")
    content = value.get("content")
    if (
        type(content) is not list
        or len(content) != 1
        or type(content[0]) is not dict
        or content[0].get("type") != "text"
        or type(content[0].get("text")) is not str
    ):
        raise WorkbenchInventoryProjectionError("tab result is invalid")
    text = content[0]["text"]
    marker = "### Result\n"
    if marker not in text:
        raise WorkbenchInventoryProjectionError("tab result is invalid")
    section = text.split(marker, 1)[1]
    if "\n### " in section:
        section = section.split("\n### ", 1)[0]
    lines = tuple(line for line in section.strip().splitlines() if line)
    if not lines or len(lines) > 64:
        raise WorkbenchInventoryProjectionError("tab group is invalid")
    return lines


def parse_playwright_tab_group(
    value: object,
    *,
    browser_ref: str,
    now_ms: int,
    resource_expires_at_ms: int,
) -> tuple[BrowserTabObservation, ...]:
    """Parse the pinned Playwright 0.0.79 browser_tabs/list result.

    The upstream tool mixes list/select/create/close. The Workbench owner calls
    only the fixed list operation before this parser sees the result.
    """
    now = _clock(now_ms)
    expires = _clock(resource_expires_at_ms)
    if expires <= now:
        raise WorkbenchInventoryProjectionError("browser resource expired")

    rows: list[tuple[int, bool, str, str]] = []
    for line in _result_lines(value):
        if line.endswith(" [crashed]"):
            raise WorkbenchInventoryProjectionError("tab crashed")
        match = _TAB_LINE.fullmatch(line)
        if match is None:
            raise WorkbenchInventoryProjectionError("tab result is invalid")
        index = int(match.group("index"))
        current = match.group("current") is not None
        rows.append((index, current, match.group("title"), match.group("url")))

    if [row[0] for row in rows] != list(range(len(rows))):
        raise WorkbenchInventoryProjectionError("tab indexes are invalid")
    if sum(1 for row in rows if row[1]) != 1:
        raise WorkbenchInventoryProjectionError("tab current selection is invalid")

    observed_expires = min(expires, now + _TAB_OBSERVATION_TTL_MS)
    result: list[BrowserTabObservation] = []
    for index, _current, title, url in rows:
        digest = hashlib.sha256(
            f"{index}\x00{title}\x00{url}".encode("utf-8")
        ).digest()
        revision = int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
        if revision == 0:
            revision = 1
        result.append(
            BrowserTabObservation(
                browser_ref=browser_ref,
                tab_locator=index,
                document_revision=revision,
                title=title,
                url=url,
                observed_at_ms=now,
                expires_at_ms=observed_expires,
            )
        )
    return tuple(result)


class WorkbenchDeploymentInventoryProjection:
    """Read already-active resources from one canonical Workbench deployment."""

    def __init__(
        self,
        *,
        deployment: Any,
        broker_caller: ActionCaller,
        clock_ms: Any,
    ) -> None:
        if not callable(getattr(deployment, "observe_active_resources", None)):
            raise TypeError("Workbench active-resource projection is required")
        if not callable(getattr(deployment, "observe_tab_group", None)):
            raise TypeError("Workbench tab observation is required")
        if type(broker_caller) is not ActionCaller:
            raise TypeError("exact Workbench broker caller is required")
        if not callable(clock_ms):
            raise TypeError("runtime clock is required")
        self._deployment = deployment
        self._broker_caller = broker_caller
        self._clock_ms = clock_ms

    def _now(self) -> int:
        return _clock(self._clock_ms())

    async def resource_reader(
        self, _outer_caller: Any, limit: int
    ) -> tuple[ActiveBrowserResource, ...]:
        if type(limit) is not int or isinstance(limit, bool) or not 1 <= limit <= 50:
            raise WorkbenchInventoryProjectionError("limit is invalid")
        raw = await _maybe(
            self._deployment.observe_active_resources(self._broker_caller)
        )
        if isinstance(raw, (str, bytes, bytearray)) or not isinstance(raw, Sequence):
            raise WorkbenchInventoryProjectionError("resource projection is invalid")
        now = self._now()
        projected: list[ActiveBrowserResource] = []
        for item in raw:
            row = project_active_resource(item, now_ms=now)
            if row is not None:
                projected.append(row)
        # Deterministic presentation only; Capacity remains the ranking owner.
        projected.sort(
            key=lambda row: (
                row.host_ref,
                row.profile_ref,
                row.browser_instance_ref,
            )
        )
        return tuple(projected[:limit])

    async def tab_reader(
        self, _outer_caller: Any, resource: ActiveBrowserResource
    ) -> tuple[BrowserTabObservation, ...]:
        if type(resource) is not ActiveBrowserResource:
            raise WorkbenchInventoryProjectionError("browser resource is invalid")
        raw = await _maybe(
            self._deployment.observe_tab_group(
                self._broker_caller,
                resource.browser_ref,
            )
        )
        return parse_playwright_tab_group(
            raw,
            browser_ref=resource.browser_ref,
            now_ms=self._now(),
            resource_expires_at_ms=resource.expires_at_ms,
        )


__all__ = [
    "WorkbenchDeploymentInventoryProjection",
    "WorkbenchInventoryProjectionError",
    "parse_playwright_tab_group",
    "project_active_resource",
]
