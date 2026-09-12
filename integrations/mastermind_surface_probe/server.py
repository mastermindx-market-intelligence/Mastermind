"""Low-level MCP and loopback HTTP edge for the read-only HC0 probe.

This is the only surface-probe module that imports the MCP/ASGI SDKs.  It
adapts the accepted pure ``inspect_surface_context`` function without adding
resources, prompts, sampling, tasks, authentication, persistence, binding, or
Mastermind runtime authority.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from integrations.mastermind_surface_probe.probe import (
    HostContextProbeConfig,
    HostContextProbeError,
    inspect_surface_context,
)
from integrations.mastermind_surface_probe.schemas import (
    CONTRACT_DIGEST,
    INPUT_SCHEMA,
    OUTPUT_SCHEMA,
    SERVER_IDENTITY,
    SERVER_VERSION,
    TOOL_ANNOTATIONS,
    TOOL_DESCRIPTION,
    TOOL_NAME,
    TOOL_TITLE,
    canonical_json,
    contract_snapshot,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8011
MCP_PATH = "/mastermind-surface-probe/mcp"
RUNTIME_SCHEMA = "mastermind.host_context_probe_runtime.v1"

_ENV_APP_REALM = "MASTERMIND_SURFACE_PROBE_APP_REALM"
_ENV_APP_GENERATION = "MASTERMIND_SURFACE_PROBE_APP_GENERATION"
_ENV_TRANSPORT_PROFILE = "MASTERMIND_SURFACE_PROBE_TRANSPORT_PROFILE"
_ENV_KEY_ID = "MASTERMIND_SURFACE_PROBE_HMAC_KEY_ID"
_ENV_KEY_VERSION = "MASTERMIND_SURFACE_PROBE_HMAC_KEY_VERSION"
_ENV_SCOPE = "MASTERMIND_SURFACE_PROBE_FINGERPRINT_SCOPE"
_ENV_KEY = "MASTERMIND_SURFACE_PROBE_HMAC_KEY"
_ENV_HOST = "MASTERMIND_SURFACE_PROBE_HOST"
_ENV_PORT = "MASTERMIND_SURFACE_PROBE_PORT"
_ENV_PATH = "MASTERMIND_SURFACE_PROBE_MCP_PATH"


@dataclass(frozen=True)
class SurfaceProbeRuntime:
    """Secret-safe immutable loopback launch configuration."""

    probe_config: HostContextProbeConfig
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    mcp_path: str = MCP_PATH


def _runtime_refusal() -> None:
    raise ValueError("INVALID_RUNTIME_CONFIGURATION")


def _required_environment(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if not isinstance(value, str) or not value or value != value.strip():
        _runtime_refusal()
    return value


def _decode_secret(value: str) -> bytes:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        _runtime_refusal()
    if not 32 <= len(decoded) <= 256:
        _runtime_refusal()
    return decoded


def load_runtime_configuration(
    environ: Mapping[str, str] | None = None,
) -> SurfaceProbeRuntime:
    """Load one exact, loopback-only runtime from a caller-owned environment."""

    source = os.environ if environ is None else environ
    if not isinstance(source, Mapping):
        _runtime_refusal()

    host = source.get(_ENV_HOST, DEFAULT_HOST)
    if host != DEFAULT_HOST:
        _runtime_refusal()

    raw_port = source.get(_ENV_PORT)
    if raw_port is None:
        port = DEFAULT_PORT
    else:
        if not isinstance(raw_port, str) or not raw_port.isascii() or not raw_port.isdigit():
            _runtime_refusal()
        port = int(raw_port)
    if not 1024 <= port <= 65535:
        _runtime_refusal()

    mcp_path = source.get(_ENV_PATH, MCP_PATH)
    if mcp_path != MCP_PATH:
        _runtime_refusal()

    try:
        config = HostContextProbeConfig(
            app_realm=_required_environment(source, _ENV_APP_REALM),
            app_generation=_required_environment(source, _ENV_APP_GENERATION),
            transport_profile=_required_environment(source, _ENV_TRANSPORT_PROFILE),
            fingerprint_key_id=_required_environment(source, _ENV_KEY_ID),
            fingerprint_key_version=_required_environment(source, _ENV_KEY_VERSION),
            fingerprint_scope=_required_environment(source, _ENV_SCOPE),
            fingerprint_secret=_decode_secret(
                _required_environment(source, _ENV_KEY)
            ),
        )
    except HostContextProbeError:
        _runtime_refusal()

    return SurfaceProbeRuntime(
        probe_config=config,
        host=host,
        port=port,
        mcp_path=mcp_path,
    )


def describe_runtime(runtime: SurfaceProbeRuntime) -> dict[str, object]:
    """Return a secret-free readiness receipt; this is not host/live proof."""

    if not isinstance(runtime, SurfaceProbeRuntime):
        _runtime_refusal()
    return {
        "schema": RUNTIME_SCHEMA,
        "status": "READY_TO_SERVE",
        "server_identity": SERVER_IDENTITY,
        "server_version": SERVER_VERSION,
        "contract_digest": CONTRACT_DIGEST,
        "app_realm": runtime.probe_config.app_realm,
        "app_generation": runtime.probe_config.app_generation,
        "host": runtime.host,
        "port": runtime.port,
        "mcp_path": runtime.mcp_path,
        "stateless": True,
        "json_response": True,
        "oauth_configured": False,
        "production_armed": False,
    }


def build_tools() -> list[mcp_types.Tool]:
    """Build the exact immutable one-tool advertisement."""

    annotations = mcp_types.ToolAnnotations(
        title=TOOL_TITLE,
        **TOOL_ANNOTATIONS,
    )
    return [
        mcp_types.Tool(
            name=TOOL_NAME,
            title=TOOL_TITLE,
            description=TOOL_DESCRIPTION,
            inputSchema=INPUT_SCHEMA,
            outputSchema=OUTPUT_SCHEMA,
            annotations=annotations,
        )
    ]


def request_meta_mapping(meta: object) -> dict[str, Any]:
    """Project only host-provided ``openai/*`` request metadata.

    MCP progress/task mechanics and all non-OpenAI extension fields are removed.
    Unknown ``openai/*`` values are retained only long enough for the pure core
    to emit one opaque degradation; no name or value is returned.
    """

    if meta is None:
        return {}
    if isinstance(meta, Mapping):
        try:
            raw = dict(meta)
        except Exception:
            raise HostContextProbeError("INVALID_HOST_METADATA") from None
    else:
        model_dump = getattr(meta, "model_dump", None)
        if not callable(model_dump):
            raise HostContextProbeError("INVALID_HOST_METADATA")
        try:
            raw = dict(model_dump(by_alias=True, exclude_none=True))
        except Exception:
            raise HostContextProbeError("INVALID_HOST_METADATA") from None
    return {
        key: value
        for key, value in raw.items()
        if isinstance(key, str) and key.startswith("openai/")
    }


def _error_result(code: str) -> mcp_types.CallToolResult:
    safe_code = (
        code
        if code
        in {
            "INVALID_REQUEST",
            "INVALID_HOST_METADATA",
            "INVALID_OBSERVATION_TIME",
            "INVALID_CONFIGURATION",
            "INTERNAL_RESPONSE_TOO_LARGE",
            "INTERNAL_ERROR",
        }
        else "INTERNAL_ERROR"
    )
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=safe_code)],
        structuredContent=None,
        isError=True,
    )


def _success_result(envelope: dict[str, Any]) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        content=[
            mcp_types.TextContent(
                type="text",
                text=canonical_json(envelope).decode("utf-8"),
            )
        ],
        structuredContent=envelope,
        isError=False,
    )


def build_mcp_server(
    config: HostContextProbeConfig,
    *,
    utc_now: Callable[[], datetime] | None = None,
) -> Server:
    """Register only ping, list-tools and call-tool over the accepted core."""

    if not isinstance(config, HostContextProbeConfig):
        raise TypeError("config must be HostContextProbeConfig")
    clock = utc_now or (lambda: datetime.now(UTC))
    server: Server = Server(SERVER_IDENTITY, version=SERVER_VERSION)
    tools = build_tools()

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    @server.call_tool(validate_input=False)
    async def call_tool(
        name: str,
        arguments: dict[str, Any] | None,
    ) -> mcp_types.CallToolResult:
        if name != TOOL_NAME or arguments not in (None, {}):
            return _error_result("INVALID_REQUEST")
        try:
            metadata = request_meta_mapping(server.request_context.meta)
            envelope = inspect_surface_context(
                metadata,
                config=config,
                observed_at=clock(),
            )
        except HostContextProbeError as exc:
            return _error_result(exc.code)
        except Exception:
            return _error_result("INTERNAL_ERROR")
        return _success_result(envelope)

    return server


def initialization_options(server: Server) -> InitializationOptions:
    """Advertise exactly the handlers registered on the low-level server."""

    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


class _StreamableHTTPApp:
    def __init__(self, manager: StreamableHTTPSessionManager) -> None:
        self._manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._manager.handle_request(scope, receive, send)


def build_streamable_http_app(
    config: HostContextProbeConfig,
    *,
    utc_now: Callable[[], datetime] | None = None,
    host: str = DEFAULT_HOST,
    path: str = MCP_PATH,
) -> Starlette:
    """Build the exact stateless JSON loopback ASGI application."""

    if host != DEFAULT_HOST or path != MCP_PATH:
        _runtime_refusal()
    server = build_mcp_server(config, utc_now=utc_now)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*"],
        allowed_origins=["http://127.0.0.1:*"],
    )
    manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        retry_interval=None,
        json_response=True,
        stateless=True,
        security_settings=security,
    )
    endpoint = _StreamableHTTPApp(manager)

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with manager.run():
            yield

    app = Starlette(
        routes=[Route(MCP_PATH, endpoint=endpoint)],
        lifespan=lifespan,
    )
    app.state.mastermind_stateless = True
    app.state.mastermind_json_response = True
    app.state.mastermind_mcp_path = MCP_PATH
    return app


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the loopback-only, stateless, read-only Mastermind HC0 MCP "
            "surface. Private HTTPS transport is configured outside this process."
        )
    )
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--check-config", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    runtime = load_runtime_configuration()
    if args.describe:
        print(
            json.dumps(
                {
                    "runtime": describe_runtime(runtime),
                    "contract": contract_snapshot(),
                },
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.check_config:
        print(json.dumps(describe_runtime(runtime), sort_keys=True))
        return 0

    app = build_streamable_http_app(runtime.probe_config)
    import uvicorn

    uvicorn.run(
        app,
        host=runtime.host,
        port=runtime.port,
        log_level="warning",
        access_log=False,
    )
    return 0


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "MCP_PATH",
    "RUNTIME_SCHEMA",
    "SurfaceProbeRuntime",
    "build_mcp_server",
    "build_streamable_http_app",
    "build_tools",
    "describe_runtime",
    "initialization_options",
    "load_runtime_configuration",
    "main",
    "request_meta_mapping",
]
