"""Fixed-route, bounded MCP transport for existing remote Workbench owners.

Each call owns one SDK session through cleanup. There is no action replay,
connection failover, browser owner, lease renewal or credential refresh here.
The configured credential artifact belongs to the enrolled outgoing client.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from integrations.mastermind_browser_link.tool_contract import LINK_TOOL_SCHEMA_DIGEST, tool_catalog
from integrations.workbench_browser_mcp.app import build_browser_tool_surface, MAX_RESULT_BYTES
from .resource_identity import validate_browser_resource
from .owner_adapter import BrowserCallerBinding
from .workbench_client import WorkbenchBrowserClientError

ROUTES_SCHEMA = "mastermind.browser_fabric_routes.v1"
CREDENTIAL_SCHEMA = "mastermind.browser_workbench_credential.v1"
MAX_HOST_ROUTES = 16
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_BEARER = re.compile(r"[A-Za-z0-9._~+/=-]{1,32768}")


@dataclass(frozen=True)
class WorkbenchHostRoute:
    host_ref: str
    mcp_url: str
    resource: str
    broker_subject_digest: str
    broker_client_ref: str
    backend_schema_digest: str
    credential_file: Path
    timeout_seconds: float = 15.0
    max_concurrency: int = 4

    def __post_init__(self):
        if type(self.host_ref) is not str or not _TOKEN.fullmatch(self.host_ref):
            raise ValueError("browser host route invalid")
        validate_browser_resource(self.mcp_url)
        validate_browser_resource(self.resource)
        self.broker.__post_init__()
        if (urlsplit(self.mcp_url).scheme != "https" or not urlsplit(self.mcp_url).netloc
                or urlsplit(self.resource).scheme != "https"
                or urlsplit(self.mcp_url).netloc != urlsplit(self.resource).netloc
                or self.backend_schema_digest != LINK_TOOL_SCHEMA_DIGEST
                or not isinstance(self.credential_file, Path) or not self.credential_file.is_absolute()
                or ".." in self.credential_file.parts
                or any(c in str(self.credential_file) for c in ("\x00", "\r", "\n"))
                or type(self.timeout_seconds) not in (int, float) or not 1 <= self.timeout_seconds <= 60
                or type(self.max_concurrency) is not int or not 1 <= self.max_concurrency <= 8):
            raise ValueError("browser host route invalid")

    @property
    def broker(self):
        # Identity fact only: remote authentication and its owner lease remain
        # authoritative. This creates no bearer, expiry or grant.
        return BrowserCallerBinding(self.broker_subject_digest, self.broker_client_ref, self.resource)


def parse_host_routes(document):
    if (type(document) is not dict or set(document) != {"schema", "routes"}
            or document["schema"] != ROUTES_SCHEMA or type(document["routes"]) is not list
            or len(document["routes"]) > MAX_HOST_ROUTES):
        raise ValueError("browser host routes invalid")
    rows = []
    for raw in document["routes"]:
        if type(raw) is not dict or set(raw) != {
                "host_ref", "mcp_url", "resource", "broker_subject_digest", "broker_client_ref", "backend_schema_digest",
                "credential_file", "timeout_seconds", "max_concurrency"}:
            raise ValueError("browser host route invalid")
        if type(raw["credential_file"]) is not str:
            raise ValueError("browser host route invalid")
        path = Path(raw["credential_file"])
        if str(path) != raw["credential_file"]:
            raise ValueError("browser host route invalid")
        rows.append(WorkbenchHostRoute(**{**raw, "credential_file": path}))
    if len({row.host_ref for row in rows}) != len(rows) or len({row.mcp_url for row in rows}) != len(rows):
        raise ValueError("browser host route duplicated")
    return tuple(rows)


def _credential(route, now):
    # Reuse the existing service's bounded private regular-file reader.
    # A rotated credential can be observed on the next independent call; a
    # rejected or expired credential never causes a modifying POST to replay.
    from integrations.workbench_action_mcp.service import _secure_json
    document = _secure_json(str(route.credential_file), maximum=65536, owner_only=True)
    if (type(document) is not dict or set(document) != {"schema", "resource", "access_token", "expires_at"}
            or document["schema"] != CREDENTIAL_SCHEMA or document["resource"] != route.resource
            or type(document["access_token"]) is not str or not _BEARER.fullmatch(document["access_token"])
            or type(document["expires_at"]) is not int or not now < document["expires_at"] < 2**63):
        raise WorkbenchBrowserClientError("ROUTE_CREDENTIAL_UNAVAILABLE")
    return document["access_token"]


class _BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream, maximum):
        self._stream, self._maximum = stream, maximum

    async def __aiter__(self):
        total = 0
        async for chunk in self._stream:
            total += len(chunk)
            if total > self._maximum:
                raise WorkbenchBrowserClientError("REMOTE_RESPONSE_TOO_LARGE")
            yield chunk

    async def aclose(self):
        await self._stream.aclose()


class _BoundedTransport(httpx.AsyncBaseTransport):
    def __init__(self, transport):
        self._transport = transport

    async def handle_async_request(self, request):
        response = await self._transport.handle_async_request(request)
        try:
            # The reviewed owner serves stateless JSON. Refuse stateful/SSE
            # peers rather than enter SDK resumption or leak a remote session.
            if "mcp-session-id" in response.headers:
                raise WorkbenchBrowserClientError("REMOTE_SESSION_REFUSED")
            if (request.method == "POST" and 200 <= response.status_code < 300
                    and response.status_code not in {202, 204}
                    and response.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json"):
                raise WorkbenchBrowserClientError("REMOTE_FORMAT_REFUSED")
            # Explicit identity encoding also bounds decoded allocation.
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise WorkbenchBrowserClientError("REMOTE_ENCODING_REFUSED")
            size = response.headers.get("content-length")
            if size is not None and (not size.isdecimal() or int(size) > MAX_RESULT_BYTES):
                raise WorkbenchBrowserClientError("REMOTE_RESPONSE_TOO_LARGE")
            response.stream = _BoundedStream(response.stream, MAX_RESULT_BYTES)
            return response
        except BaseException:
            await response.aclose()
            raise

    async def aclose(self):
        await self._transport.aclose()


class WorkbenchHostTransport:
    """One reviewed endpoint; independent sessions preserve parallel tab use."""

    def __init__(self, *, route, now, http_transport_factory=None, credential_reader=_credential):
        if type(route) is not WorkbenchHostRoute or not callable(now) or not callable(credential_reader):
            raise TypeError("fixed browser transport configuration required")
        route.__post_init__()
        if http_transport_factory is not None and not callable(http_transport_factory):
            raise TypeError("HTTP transport factory invalid")
        self.route = route
        self._now = now
        self._credential_reader = credential_reader
        self._http_transport_factory = http_transport_factory or (
            lambda: httpx.AsyncHTTPTransport(retries=0, trust_env=False))
        self._surface = build_browser_tool_surface(
            tool_catalog(), expected_tool_schema_digest=route.backend_schema_digest,
            include_resource_observation=True)
        expected = {"tools": {row.name: row.model_dump(mode="json", by_alias=True, exclude_none=True)
                              for row in self._surface.tools}}
        self._expected_private_digest = observed_mcp_tool_schema_digest(expected)
        self._permits = asyncio.Semaphore(route.max_concurrency)
        self._opened = False
        self._active = set()

    @asynccontextmanager
    async def opened(self):
        if self._opened:
            raise WorkbenchBrowserClientError("ROUTE_ALREADY_OPEN")
        self._opened = True
        try:
            yield self
        finally:
            self._opened = False
            pending = tuple(self._active)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    async def call_tool(self, name, arguments):
        if not self._opened or name not in self._surface.validators:
            raise WorkbenchBrowserClientError("ROUTE_UNAVAILABLE")
        # Freeze and validate before the first await, and never derive routing
        # or authentication from a tool argument.
        try:
            raw = json.dumps(arguments, allow_nan=False, separators=(",", ":")).encode("utf-8")
            if len(raw) > 128 * 1024:
                raise ValueError("oversize")
            request = json.loads(raw)
            self._surface.validators[name].validate(request)
        except Exception as error:
            raise WorkbenchBrowserClientError("REMOTE_ARGUMENTS_INVALID") from error
        current = asyncio.current_task()
        self._active.add(current)
        try:
            async with asyncio.timeout(self.route.timeout_seconds):
                async with self._permits:
                    if not self._opened:
                        raise WorkbenchBrowserClientError("ROUTE_UNAVAILABLE")
                    token = self._credential_reader(self.route, self._now())
                    transport = _BoundedTransport(self._http_transport_factory())
                    async with httpx.AsyncClient(
                        transport=transport, follow_redirects=False, trust_env=False,
                        timeout=httpx.Timeout(self.route.timeout_seconds, connect=min(5.0, self.route.timeout_seconds)),
                        headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"},
                    ) as client:
                        async with streamable_http_client(
                                self.route.mcp_url, http_client=client, terminate_on_close=False) as streams:
                            async with ClientSession(
                                    streams[0], streams[1],
                                    read_timeout_seconds=timedelta(seconds=self.route.timeout_seconds)) as session:
                                initialized = await session.initialize()
                                if initialized.serverInfo.name != "Mastermind Workbench Browser":
                                    raise WorkbenchBrowserClientError("REMOTE_SERVER_CHANGED")
                                catalog = await session.list_tools()
                                actual = {"tools": {row.name: row.model_dump(mode="json", by_alias=True, exclude_none=True)
                                                     for row in catalog.tools}}
                                if catalog.nextCursor is not None or len(actual["tools"]) != len(catalog.tools):
                                    raise WorkbenchBrowserClientError("REMOTE_SCHEMA_CHANGED")
                                if name == "reconcile_browser_action":
                                    # Recovery uses the stable original-action seam.
                                    # Unrelated fresh-tool upgrades must not strand an
                                    # existing receipt. Its own contract remains pinned.
                                    expected_row = next(row for row in self._surface.tools if row.name == name)
                                    expected_recovery = {"tools": {name: expected_row.model_dump(
                                        mode="json", by_alias=True, exclude_none=True)}}
                                    actual_recovery = {"tools": {name: actual["tools"].get(name)}}
                                    qualified = (observed_mcp_tool_schema_digest(actual_recovery)
                                                 == observed_mcp_tool_schema_digest(expected_recovery))
                                else:
                                    qualified = (set(actual["tools"]) == set(self._surface.schemas)
                                                 and observed_mcp_tool_schema_digest(actual) == self._expected_private_digest)
                                if not qualified:
                                    raise WorkbenchBrowserClientError("REMOTE_SCHEMA_CHANGED")
                                # Catalog qualification fills the SDK output schema
                                # cache before effects. This is the only tool POST.
                                result = await session.call_tool(name, request)
                                return result.model_dump(mode="json", by_alias=True, exclude_none=True)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise WorkbenchBrowserClientError("REMOTE_CALL_UNAVAILABLE") from error
        finally:
            self._active.discard(current)
