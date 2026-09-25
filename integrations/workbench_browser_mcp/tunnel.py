"""Fixed-channel stdio Browser composition over the existing Workbench runtime.

This module is a model-facing transport adapter only. The existing Workbench
channel runtime owns admission, selected project/root, lease, action key,
artifact/effect evidence, bounded executor, host/boot identity and durable
channel audit. Browser resource/action semantics come from the same ports used
by the Web Workbench Browser sibling.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import inspect
import json
from pathlib import Path
from collections.abc import Mapping
from typing import Any

import mcp.types as mcp_types
from jsonschema import ValidationError
from mcp.server.lowlevel import Server
from mcp.types import CallToolResult, ServerResult, TextContent

from common.bounded_sync_executor import SyncExecutionTimeout
from control_plane.browser_resource_contract import READ_ONLY_BROWSER_TOOLS
from integrations.business_mcp_auth.audit import AuditSinkPoisoned
from integrations.business_mcp_auth.contracts import CHANNEL_AUDIT_SCHEMA, ChannelAuditEvent
from integrations.workbench_action_mcp.runtime import (
    CHANNEL_AUTHORITY_KIND,
    ChannelRuntimeServices,
    WorkbenchActionRuntime,
)
from integrations.workbench_action_mcp.service import (
    BrowserServiceConfig,
    ServiceConfigurationError,
    parse_browser_service_config,
    shutdown_exit_code,
    ShutdownOutcome,
)
from integrations.workbench_action_mcp.tunnel import (
    TunnelConfig,
    TunnelConfigurationError,
    create_runtime_channel,
    load_private_json,
    load_tunnel_config,
    run_server_stdio,
)
from integrations.workbench_read_mcp.runtime import (
    RuntimeCloseIncomplete,
    RuntimeCloseUncertain,
    RuntimeClosed,
)

from .app import (
    PREPARE_RESOURCE_TOOL,
    RECONCILE_ACTION_TOOL,
    RECONCILE_RESOURCE_TOOL,
    RUN_ACTION_TOOL,
    START_RESOURCE_TOOL,
    _json_result,
    _native_result,
    _snapshot,
    build_browser_tool_surface,
)
from .browser_port import BrowserPortRefused
from .contracts import BrowserContractError
from .deployment import BrowserPorts, create_browser_ports
from .resource_port import (
    BrowserHostConfig,
    BrowserResourceRefused,
)


BROWSER_TUNNEL_SCHEMA = "mastermind.workbench_browser_tunnel.v1"
BROWSER_TUNNEL_RECEIPT_SCHEMA = "mastermind.workbench_browser_tunnel_receipt.v1"
SERVER_NAME = "Mastermind Workbench Browser Tunnel"
SERVER_VERSION = "0.1.0"
MAX_CONFIG_BYTES = 64 * 1024
MAX_BROWSER_CATALOG_BYTES = 2 * 1024 * 1024
MAX_ARGUMENT_BYTES = 128 * 1024


class BrowserTunnelConfigurationError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class BrowserTunnelConfig:
    schema: str
    action_config_path: str
    action: TunnelConfig
    browser: BrowserServiceConfig


def _refuse() -> None:
    raise BrowserTunnelConfigurationError("BROWSER_TUNNEL_CONFIGURATION_REFUSED")


def _absolute_path(value: object) -> str:
    if type(value) is not str or not value.startswith("/") or "\x00" in value:
        _refuse()
    path = Path(value)
    if ".." in path.parts:
        _refuse()
    return value


def load_browser_tunnel_config(path: str) -> BrowserTunnelConfig:
    try:
        value = load_private_json(path, maximum=MAX_CONFIG_BYTES)
        if set(value) != {"schema", "action_tunnel_config", "browser"}:
            _refuse()
        if value.get("schema") != BROWSER_TUNNEL_SCHEMA:
            _refuse()
        action_path = _absolute_path(value.get("action_tunnel_config"))
        browser = parse_browser_service_config(value.get("browser"))
        action = load_tunnel_config(action_path)
        return BrowserTunnelConfig(
            schema=BROWSER_TUNNEL_SCHEMA,
            action_config_path=action_path,
            action=action,
            browser=browser,
        )
    except BrowserTunnelConfigurationError:
        raise
    except (TunnelConfigurationError, ServiceConfigurationError, TypeError, ValueError) as error:
        raise BrowserTunnelConfigurationError(
            "BROWSER_TUNNEL_CONFIGURATION_REFUSED"
        ) from error


def _host_config(value: BrowserServiceConfig) -> BrowserHostConfig:
    return BrowserHostConfig(
        source_root=Path(value.source_root),
        python_executable=value.python_executable,
        node_executable=value.node_executable,
        mcp_cli_path=value.mcp_cli_path,
        chrome_executable=value.chrome_executable,
        relay_root=Path(value.relay_root),
        output_root=Path(value.output_root),
        home_dir=value.home_dir,
        tmp_dir=value.tmp_dir,
        startup_timeout_seconds=value.startup_timeout_seconds,
    )


class _ClosedBrowserTunnelServer(Server):
    def __init__(self, name: str, *, version: str, allowed_tools: frozenset[str]):
        super().__init__(name, version=version)
        self._browser_allowed_tools = allowed_tools

    async def _get_cached_tool_definition(self, tool_name: str):
        if (
            type(tool_name) is not str
            or tool_name not in self._browser_allowed_tools
        ):
            return None
        return await super()._get_cached_tool_definition(tool_name)

    def call_tool(self, *, validate_input: bool = True):
        register = super().call_tool(validate_input=validate_input)

        def decorator(func):
            registered = register(func)
            sdk_handler = self.request_handlers[mcp_types.CallToolRequest]

            async def closed_call_tool(req: mcp_types.CallToolRequest) -> ServerResult:
                params = getattr(req, "params", None)
                name = getattr(params, "name", None)
                if (
                    type(name) is not str
                    or name not in self._browser_allowed_tools
                ):
                    return ServerResult(_error("TOOL_NOT_AVAILABLE"))
                return await sdk_handler(req)

            self.request_handlers[mcp_types.CallToolRequest] = closed_call_tool
            return registered

        return decorator


def _error(code: str) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps({"code": code}, separators=(",", ":")),
            )
        ],
        isError=True,
    )


def _ref_digest(value: object) -> str | None:
    if type(value) is not str:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _run_existing(runtime: WorkbenchActionRuntime, operation):
    pending = runtime.run_io(operation)
    if not inspect.isawaitable(pending):
        raise RuntimeError("existing Workbench run_io did not return an awaitable")
    return await pending


def create_browser_tunnel_server(
    runtime: WorkbenchActionRuntime,
    browser_config: BrowserServiceConfig,
) -> Server:
    if not isinstance(runtime, WorkbenchActionRuntime):
        raise ValueError("WORKBENCH_ACTION_RUNTIME_REQUIRED")
    services = getattr(runtime, "channel_services", None)
    if type(services) is not ChannelRuntimeServices:
        raise ValueError("FIXED_CHANNEL_SERVICES_REQUIRED")
    if not isinstance(browser_config, BrowserServiceConfig):
        raise ValueError("BROWSER_HOST_CONFIG_REQUIRED")

    catalog = load_private_json(
        browser_config.tool_catalog_file,
        maximum=MAX_BROWSER_CATALOG_BYTES,
    )
    surface = build_browser_tool_surface(catalog)
    allowed_names = frozenset(surface.validators)
    caller = services.caller
    project_ref = services.project_ref
    ports: BrowserPorts = create_browser_ports(
        resolve_binding=runtime.resolve_binding,
        clock_ms=services.clock_ms,
        action_token_key=services.action_token_key,
        artifact_store=services.artifact_store,
        host_binding=services.host_binding,
        action_ttl_ms=services.action_ttl_ms,
        host_config=_host_config(browser_config),
        # Persistent authenticated browser identities remain separately owned
        # and are not admitted by the first worker stdio projection.
        profile_resolver=lambda _profile_ref: None,
    )
    resource_port = ports.resource_port
    action_port = ports.action_port

    def action_digest(name: str, request: Mapping[str, Any]) -> str | None:
        if name in {START_RESOURCE_TOOL, RECONCILE_RESOURCE_TOOL}:
            return _ref_digest(request.get("start_ref"))
        if name in {RUN_ACTION_TOOL, RECONCILE_ACTION_TOOL}:
            return _ref_digest(request.get("action_ref"))
        return None

    async def emit_channel_audit(
        *,
        code: str,
        accepted: bool,
        tool: str,
        digest: str | None,
    ) -> None:
        event = ChannelAuditEvent(
            schema=CHANNEL_AUDIT_SCHEMA,
            policy_id=services.audit_policy_id,
            code=code,
            accepted=accepted,
            channel_ref=services.channel_ref,
            tool=tool,
            action_digest=digest,
        )
        await runtime.emit_channel_audit(event)

    server: Server = _ClosedBrowserTunnelServer(
        SERVER_NAME,
        version=SERVER_VERSION,
        allowed_tools=allowed_names,
    )

    @server.list_tools()
    async def list_tools():
        return list(surface.tools)

    @server.call_tool(validate_input=False)
    async def call_tool(
        name: str, arguments: dict[str, object] | None
    ) -> CallToolResult:
        if name not in allowed_names:
            return _error("TOOL_NOT_AVAILABLE")
        try:
            request = _snapshot(arguments, MAX_ARGUMENT_BYTES)
            surface.validators[name].validate(request)
            digest = action_digest(name, request)
        except (ValidationError, TypeError, ValueError, BrowserContractError):
            try:
                await emit_channel_audit(
                    code="request_refused",
                    accepted=False,
                    tool=name,
                    digest=None,
                )
            except (AuditSinkPoisoned, RuntimeClosed, SyncExecutionTimeout):
                return _error("CHANNEL_AUDIT_UNAVAILABLE")
            return _error("INVALID_REQUEST")

        if runtime.resolve_binding(caller, project_ref) is None:
            try:
                await emit_channel_audit(
                    code="channel_refused",
                    accepted=False,
                    tool=name,
                    digest=digest,
                )
            except (AuditSinkPoisoned, RuntimeClosed, SyncExecutionTimeout):
                return _error("CHANNEL_AUDIT_UNAVAILABLE")
            return _error("CHANNEL_ADMISSION_REFUSED")
        try:
            await emit_channel_audit(
                code="accepted",
                accepted=True,
                tool=name,
                digest=digest,
            )
        except (AuditSinkPoisoned, RuntimeClosed, SyncExecutionTimeout):
            return _error("CHANNEL_AUDIT_UNAVAILABLE")

        effectful = name in {START_RESOURCE_TOOL, RUN_ACTION_TOOL}
        direct_native: Mapping[str, Any] | None = None
        try:
            if name == PREPARE_RESOURCE_TOOL:
                start_ref = await _run_existing(
                    runtime,
                    lambda: resource_port.prepare_resource(
                        caller,
                        project_ref=request["project_ref"],
                        mode=request["mode"],
                        profile_ref=request.get("profile_ref"),
                    ),
                )
                observed: Mapping[str, Any] = {
                    "status": "PREPARED",
                    "start_ref": start_ref,
                }
            elif name == START_RESOURCE_TOOL:
                observed = await _run_existing(
                    runtime,
                    lambda: resource_port.start_resource(
                        caller, request["start_ref"]
                    ),
                )
            elif name == RECONCILE_RESOURCE_TOOL:
                observed = await _run_existing(
                    runtime,
                    lambda: resource_port.reconcile_resource(
                        caller, request["start_ref"]
                    ),
                )
            elif name in READ_ONLY_BROWSER_TOOLS:
                native_args = dict(request)
                browser_ref = native_args.pop("browser_ref")
                direct_native = await _run_existing(
                    runtime,
                    lambda: action_port.call_read_tool(
                        caller, browser_ref, name, native_args
                    ),
                )
                observed = {}
            elif name in surface.prepare_tool_to_native:
                native_args = dict(request)
                browser_ref = native_args.pop("browser_ref")
                action_ref = await _run_existing(
                    runtime,
                    lambda: action_port.prepare_action(
                        caller,
                        browser_ref,
                        surface.prepare_tool_to_native[name],
                        native_args,
                    ),
                )
                observed = {"status": "PREPARED", "action_ref": action_ref}
            elif name == RUN_ACTION_TOOL:
                observed = await _run_existing(
                    runtime,
                    lambda: action_port.run_action(
                        caller,
                        request["browser_ref"],
                        request["action_ref"],
                    ),
                )
            else:
                observed = await _run_existing(
                    runtime,
                    lambda: action_port.reconcile_action(
                        caller,
                        request["browser_ref"],
                        request["action_ref"],
                    ),
                )
        except (BrowserResourceRefused, BrowserPortRefused) as error:
            return _error(error.code)
        except (RuntimeClosed, SyncExecutionTimeout):
            return _error(
                "BROWSER_EFFECT_UNKNOWN"
                if effectful
                else "CHANNEL_ADMISSION_CHANGED"
            )
        except BrowserContractError:
            return _error("INVALID_REQUEST")
        except Exception:
            return _error(
                "BROWSER_EFFECT_UNKNOWN"
                if effectful
                else "BROWSER_UNAVAILABLE"
            )

        if runtime.resolve_binding(caller, project_ref) is None:
            return _error(
                "BROWSER_EFFECT_UNKNOWN"
                if effectful
                else "CHANNEL_ADMISSION_CHANGED"
            )
        try:
            if direct_native is not None:
                return _native_result(direct_native)
            data = _snapshot(dict(observed), 256 * 1024)
            if name == RUN_ACTION_TOOL and isinstance(data.get("result"), dict):
                native = data.pop("result")
                result = _native_result(native, structured=data)
                if data.get("effect_state") == "EFFECT_UNKNOWN":
                    result.isError = True
                return result
            return _json_result(data)
        except Exception:
            return _error(
                "BROWSER_EFFECT_UNKNOWN"
                if effectful
                else "BROWSER_RESULT_UNVERIFIED"
            )

    return server


async def _serve(config: BrowserTunnelConfig) -> int:
    runtime = await create_runtime_channel(config.action)
    try:
        await run_server_stdio(
            runtime,
            server_factory=lambda selected: create_browser_tunnel_server(
                selected, config.browser
            ),
            close_timeout_seconds=config.action.close_timeout_seconds,
        )
    except RuntimeCloseIncomplete:
        return shutdown_exit_code(ShutdownOutcome.RUNTIME_CLOSE_INCOMPLETE)
    except RuntimeCloseUncertain:
        return shutdown_exit_code(ShutdownOutcome.RUNTIME_CLOSE_UNCERTAIN)
    except BaseException:
        return shutdown_exit_code(ShutdownOutcome.SERVER_FAILED)
    return shutdown_exit_code(ShutdownOutcome.CLEAN)


def run_configured_browser_stdio(path: str) -> int:
    try:
        config = load_browser_tunnel_config(path)
        return asyncio.run(_serve(config))
    except BrowserTunnelConfigurationError:
        return 2
    except BaseException:
        return 5


__all__ = [
    "BROWSER_TUNNEL_RECEIPT_SCHEMA",
    "BROWSER_TUNNEL_SCHEMA",
    "BrowserTunnelConfig",
    "BrowserTunnelConfigurationError",
    "create_browser_tunnel_server",
    "load_browser_tunnel_config",
    "run_configured_browser_stdio",
]
