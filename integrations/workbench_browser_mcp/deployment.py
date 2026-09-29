"""Inert Workbench Browser composition over existing Workbench runtime owners.

This module borrows the authenticated Workbench policy, selected-project binding,
bounded executor, action key, artifact store, host/boot identity and transport
policy. It creates no lease, queue, lifecycle, permission or retry owner.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from control_plane.codex_worker import ProcessInspector
from integrations.business_mcp_auth.contracts import validate_resource_policy
from integrations.workbench_action_mcp.deployment import RuntimeServices

from .app import create_authenticated_browser_server
from .browser_port import BrowserActionPort
from .contracts import BrowserRefCodec
from .resource_port import (
    BrowserHostConfig,
    BrowserResourcePort,
    ProfileResolver,
    RelayCommandBuilder,
    RelayRequester,
    default_relay_command,
    validate_host_config,
)
from .relay import relay_request


@dataclass(frozen=True)
class BrowserPorts:
    """Resource/effect ports detached from any model-facing transport."""

    resource_port: BrowserResourcePort
    action_port: BrowserActionPort


@dataclass(frozen=True)
class BrowserDeployment:
    """Borrowed browser facade over one existing Workbench runtime generation."""

    services: RuntimeServices
    server: object
    resource_port: BrowserResourcePort
    action_port: BrowserActionPort
    prepare_resource: Callable[..., Any]
    start_resource: Callable[..., Any]
    reconcile_resource: Callable[..., Any]
    read_tool: Callable[..., Any]
    prepare_action: Callable[..., Any]
    run_action: Callable[..., Any]
    reconcile_action: Callable[..., Any]
    cleanup_resource: Callable[..., Any]


async def _run_existing(services: RuntimeServices, operation: Callable[[], object]) -> object:
    pending = services.run_io(operation)
    if not inspect.isawaitable(pending):
        raise RuntimeError("existing Workbench run_io did not return an awaitable")
    return await pending


def create_browser_ports(
    *,
    resolve_binding: Callable[..., Any],
    clock_ms: Callable[[], int],
    action_token_key: bytes,
    artifact_store: object,
    host_binding: object,
    action_ttl_ms: int,
    host_config: BrowserHostConfig,
    profile_resolver: ProfileResolver,
    inspector: ProcessInspector | None = None,
    relay_requester: RelayRequester = relay_request,
    relay_command_builder: RelayCommandBuilder = default_relay_command,
) -> BrowserPorts:
    """Create the shared browser ports without selecting a client transport."""

    if (
        not callable(resolve_binding)
        or not callable(clock_ms)
        or not isinstance(action_token_key, bytes)
        or len(action_token_key) < 32
        or not callable(profile_resolver)
        or not callable(relay_requester)
        or not callable(relay_command_builder)
        or type(action_ttl_ms) is not int
        or action_ttl_ms <= 0
    ):
        raise ValueError("BROWSER_PORT_OWNERS_INVALID")
    selected_host = validate_host_config(host_config)
    selected_inspector = inspector or ProcessInspector()
    codec = BrowserRefCodec(action_token_key)

    resource_port = BrowserResourcePort(
        resolve_binding=resolve_binding,
        clock_ms=clock_ms,
        codec=codec,
        artifact_store=artifact_store,
        host_binding=host_binding,
        host_config=selected_host,
        profile_resolver=profile_resolver,
        inspector=selected_inspector,
        relay_requester=relay_requester,
        relay_command_builder=relay_command_builder,
    )
    action_port = BrowserActionPort(
        resolve_binding=resolve_binding,
        clock_ms=clock_ms,
        codec=codec,
        artifact_store=artifact_store,
        host_binding=host_binding,
        inspector=selected_inspector,
        relay_root=selected_host.relay_root,
        relay_requester=relay_requester,
        action_ttl_ms=action_ttl_ms,
    )
    return BrowserPorts(resource_port=resource_port, action_port=action_port)


def create_browser_deployment(
    *,
    services: RuntimeServices,
    host_config: BrowserHostConfig,
    tool_catalog: Mapping[str, Any],
    profile_resolver: ProfileResolver,
    inspector: ProcessInspector | None = None,
    relay_requester: RelayRequester = relay_request,
    relay_command_builder: RelayCommandBuilder = default_relay_command,
) -> BrowserDeployment:
    if not isinstance(services, RuntimeServices):
        raise ValueError("RUNTIME_SERVICES_REQUIRED")
    policy = validate_resource_policy(services.policy)
    if policy != validate_resource_policy(services.authenticator.policy):
        raise ValueError("AUTH_POLICY_BINDING_MISMATCH")
    # Browser is an additional Workbench capability surface under the existing
    # attended owner grant. Do not mint a second browser permission/lease plane.
    if policy.required_scopes != ("workbench.action",):
        raise ValueError("ACTION_SCOPE_REQUIRED")
    if not callable(services.run_io):
        raise ValueError("RUNTIME_SERVICES_INVALID")
    ports = create_browser_ports(
        resolve_binding=services.resolve_binding,
        clock_ms=services.clock_ms,
        action_token_key=services.action_token_key,
        artifact_store=services.artifact_store,
        host_binding=services.host_binding,
        action_ttl_ms=services.action_ttl_ms,
        host_config=host_config,
        profile_resolver=profile_resolver,
        inspector=inspector,
        relay_requester=relay_requester,
        relay_command_builder=relay_command_builder,
    )
    resource_port = ports.resource_port
    action_port = ports.action_port
    selected_host = validate_host_config(host_config)

    async def prepare_resource(caller, project_ref, mode, profile_ref):
        return await _run_existing(
            services,
            lambda: resource_port.prepare_resource(
                caller,
                project_ref=project_ref,
                mode=mode,
                profile_ref=profile_ref,
            ),
        )

    async def start_resource(caller, start_ref):
        return await _run_existing(
            services, lambda: resource_port.start_resource(caller, start_ref)
        )

    async def reconcile_resource(caller, start_ref):
        return await _run_existing(
            services, lambda: resource_port.reconcile_resource(caller, start_ref)
        )

    async def read_tool(caller, browser_ref, tool, arguments):
        return await _run_existing(
            services,
            lambda: action_port.call_read_tool(
                caller, browser_ref, tool, arguments
            ),
        )

    async def prepare_action(caller, browser_ref, tool, arguments):
        return await _run_existing(
            services,
            lambda: action_port.prepare_action(
                caller, browser_ref, tool, arguments
            ),
        )

    async def run_action(caller, browser_ref, action_ref):
        return await _run_existing(
            services,
            lambda: action_port.run_action(
                caller, browser_ref, action_ref
            ),
        )

    async def reconcile_action(caller, browser_ref, action_ref):
        return await _run_existing(
            services,
            lambda: action_port.reconcile_action(
                caller, browser_ref, action_ref
            ),
        )

    async def cleanup_resource(
        browser_ref,
        *,
        owner_state: str,
        effect_state: str,
        tool_call_inflight: bool = False,
    ):
        # Host/lease-owner method only; deliberately not exported as an MCP tool.
        return await _run_existing(
            services,
            lambda: resource_port.cleanup_resource(
                browser_ref,
                owner_state=owner_state,
                effect_state=effect_state,
                tool_call_inflight=tool_call_inflight,
            ),
        )

    server = create_authenticated_browser_server(
        authenticator=services.authenticator,
        policy=policy,
        now=services.now,
        audit_sink=services.audit_sink,
        tool_catalog=tool_catalog,
        prepare_resource=prepare_resource,
        start_resource=start_resource,
        reconcile_resource=reconcile_resource,
        read_tool=read_tool,
        prepare_action=prepare_action,
        run_action=run_action,
        reconcile_action=reconcile_action,
        allowed_hosts=services.allowed_hosts,
        call_receipt_sink=services.call_receipt_sink,
        allowed_origins=services.allowed_origins,
        expected_tool_schema_digest=selected_host.expected_tool_schema_digest,
    )

    return BrowserDeployment(
        services=services,
        server=server,
        resource_port=resource_port,
        action_port=action_port,
        prepare_resource=prepare_resource,
        start_resource=start_resource,
        reconcile_resource=reconcile_resource,
        read_tool=read_tool,
        prepare_action=prepare_action,
        run_action=run_action,
        reconcile_action=reconcile_action,
        cleanup_resource=cleanup_resource,
    )


__all__ = ["BrowserDeployment", "BrowserPorts", "create_browser_deployment", "create_browser_ports"]
