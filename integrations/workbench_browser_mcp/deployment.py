"""Inert Workbench Browser composition over existing Workbench runtime owners.

This module borrows the authenticated Workbench policy, selected-project binding,
bounded executor, action key, artifact store, host/boot identity and transport
policy. It creates no lease, queue, lifecycle, permission or retry owner.
"""
from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from control_plane.codex_worker import ProcessInspector
from integrations.business_mcp_auth.contracts import validate_resource_policy
from integrations.workbench_action_mcp.contracts import ActionCaller
from integrations.workbench_action_mcp.deployment import RuntimeServices

from .app import create_authenticated_browser_server
from .browser_port import BrowserActionPort, BrowserPortRefused
from .contracts import BrowserRefCodec, BrowserResourceRef
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
class ActiveBrowserProjection:
    """Ephemeral read projection of one exact resource this deployment started."""

    browser_ref: str
    resource: BrowserResourceRef


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
    observe_active_resources: Callable[..., Any]
    observe_tab_group: Callable[..., Any]


async def _run_existing(services: RuntimeServices, operation: Callable[[], object]) -> object:
    pending = services.run_io(operation)
    if not inspect.isawaitable(pending):
        raise RuntimeError("existing Workbench run_io did not return an awaitable")
    return await pending


async def _run_recovery(
    services: RuntimeServices, tool: str, operation: Callable[[], object]
) -> object:
    if services.run_recovery_io is None:
        raise RuntimeError("browser recovery executor is unavailable")
    pending = services.run_recovery_io(tool, operation)
    if not inspect.isawaitable(pending):
        raise RuntimeError("browser recovery executor did not return an awaitable")
    return await pending


def create_browser_ports(
    *,
    resolve_binding: Callable[..., Any],
    resolve_recovery_binding: Callable[..., Any] | None = None,
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
    if resolve_recovery_binding is not None and not callable(resolve_recovery_binding):
        raise ValueError("BROWSER_RECOVERY_BINDING_INVALID")
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
        resolve_recovery_binding=resolve_recovery_binding,
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
    if not callable(services.resolve_recovery_binding) or not callable(services.run_recovery_io):
        raise ValueError("BROWSER_RECOVERY_OWNERS_REQUIRED")
    ports = create_browser_ports(
        resolve_binding=services.resolve_binding,
        resolve_recovery_binding=services.resolve_recovery_binding,
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

    # Runtime-scoped projection only. The signed browser_ref and Workbench owner
    # remain authoritative; this set is neither durable nor independently
    # recoverable and disappears with the deployment process.
    projection_gate = threading.RLock()
    active_projection: dict[
        str, tuple[tuple[str, str, str], BrowserResourceRef]
    ] = {}

    def caller_key(caller: ActionCaller) -> tuple[str, str, str]:
        if type(caller) is not ActionCaller:
            raise TypeError("browser projection caller must be ActionCaller")
        return (caller.subject_digest, caller.client_ref, caller.resource)

    def remember(
        caller: ActionCaller, browser_ref: str, resource: BrowserResourceRef
    ) -> None:
        key = caller_key(caller)
        with projection_gate:
            active_projection[browser_ref] = (key, resource)

    def forget(browser_ref: object) -> None:
        if type(browser_ref) is not str:
            return
        with projection_gate:
            active_projection.pop(browser_ref, None)

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
        receipt = await _run_existing(
            services, lambda: resource_port.start_resource(caller, start_ref)
        )
        if (
            isinstance(receipt, Mapping)
            and receipt.get("effect_state") == "APPLIED"
            and type(receipt.get("browser_ref")) is str
        ):
            browser_ref = receipt["browser_ref"]
            try:
                observed = await _run_existing(
                    services,
                    lambda: action_port.observe_resource(caller, browser_ref),
                )
            except BrowserPortRefused:
                # The start receipt remains authoritative. A transient inability
                # to observe it must not be rewritten as NOT_APPLIED.
                pass
            else:
                if type(observed) is BrowserResourceRef:
                    remember(caller, browser_ref, observed)
        return receipt

    async def reconcile_resource(caller, start_ref):
        return await _run_existing(
            services, lambda: resource_port.reconcile_resource(caller, start_ref)
        )

    async def observe_active_resources(
        caller: ActionCaller,
    ) -> tuple[ActiveBrowserProjection, ...]:
        key = caller_key(caller)

        def project() -> tuple[ActiveBrowserProjection, ...]:
            with projection_gate:
                snapshot = tuple(active_projection.items())
            result: list[ActiveBrowserProjection] = []
            stale: list[str] = []
            for browser_ref, (owner_key, _cached) in snapshot:
                if owner_key != key:
                    continue
                try:
                    live = action_port.observe_resource(caller, browser_ref)
                except BrowserPortRefused:
                    stale.append(browser_ref)
                    continue
                result.append(
                    ActiveBrowserProjection(browser_ref=browser_ref, resource=live)
                )
            if stale:
                with projection_gate:
                    for browser_ref in stale:
                        current = active_projection.get(browser_ref)
                        if current is not None and current[0] == key:
                            active_projection.pop(browser_ref, None)
            return tuple(result)

        return await _run_existing(services, project)

    async def observe_tab_group(caller: ActionCaller, browser_ref: str):
        return await _run_existing(
            services,
            lambda: action_port.observe_tab_group(caller, browser_ref),
        )

    async def read_tool(caller, browser_ref, tool, arguments):
        return await _run_recovery(
            services,
            tool,
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
        receipt = await _run_existing(
            services,
            lambda: resource_port.cleanup_resource(
                browser_ref,
                owner_state=owner_state,
                effect_state=effect_state,
                tool_call_inflight=tool_call_inflight,
            ),
        )
        if isinstance(receipt, Mapping) and receipt.get("released") is True:
            forget(browser_ref)
        return receipt

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
        observe_active_resources=observe_active_resources,
        observe_tab_group=observe_tab_group,
    )


__all__ = [
    "ActiveBrowserProjection",
    "BrowserDeployment",
    "BrowserPorts",
    "create_browser_deployment",
    "create_browser_ports",
]
