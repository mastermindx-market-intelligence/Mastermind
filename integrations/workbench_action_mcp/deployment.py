"""Inert composition for Workbench Action F0.

The deployment borrows authentication, selected-project binding, bounded I/O,
audit, clock and token-key services from existing owners. It opens no project
root, listener, credential, executor, lifecycle, queue, or retry plane itself.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from dataclasses import dataclass

from integrations.business_mcp_auth.contracts import (
    AuthAuditSink,
    ResourcePolicy,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator

from .action_artifacts import (
    ActionArtifactStore,
    ActionHostBinding,
    validate_host_binding,
)
from .app import create_authenticated_action_server
from .contracts import ActionTokenCodec, MAX_ACTION_TTL_MS
from .patch_port import ActionBindingResolver, ActionExecutor, create_text_patch_port


@dataclass(frozen=True)
class RuntimeServices:
    authenticator: JwtAuthenticator
    policy: ResourcePolicy
    now: Callable[[], int]
    clock_ms: Callable[[], int]
    audit_sink: AuthAuditSink
    artifact_store: ActionArtifactStore
    host_binding: ActionHostBinding
    resolve_binding: ActionBindingResolver
    run_io: ActionExecutor
    action_token_key: bytes
    allowed_hosts: tuple[str, ...]
    call_receipt_sink: Callable[[Mapping[str, Any]], None] | None = None
    allowed_origins: tuple[str, ...] = ()
    action_ttl_ms: int = MAX_ACTION_TTL_MS


def create_deployment(services: RuntimeServices):
    if not isinstance(services, RuntimeServices):
        raise ValueError("RUNTIME_SERVICES_REQUIRED")
    if (
        not isinstance(services.authenticator, JwtAuthenticator)
        or not callable(getattr(services.audit_sink, "emit", None))
        or not all(
            callable(value)
            for value in (
                services.now,
                services.clock_ms,
                services.resolve_binding,
                services.run_io,
            )
        )
    ):
        raise ValueError("RUNTIME_SERVICES_INVALID")
    if type(services.artifact_store) is not ActionArtifactStore:
        raise ValueError("RUNTIME_SERVICES_INVALID")
    try:
        validate_host_binding(services.host_binding)
    except Exception as error:
        raise ValueError("RUNTIME_SERVICES_INVALID") from error
    policy = validate_resource_policy(services.policy)
    if policy != validate_resource_policy(services.authenticator.policy):
        raise ValueError("AUTH_POLICY_BINDING_MISMATCH")
    if policy.required_scopes != ("workbench.action",):
        raise ValueError("ACTION_SCOPE_REQUIRED")
    for addresses, required in (
        (services.allowed_hosts, True),
        (services.allowed_origins, False),
    ):
        if (
            type(addresses) is not tuple
            or (required and not addresses)
            or any(
                type(item) is not str
                or not item
                or "*" in item
                or any(ord(character) <= 32 or ord(character) == 127 for character in item)
                for item in addresses
            )
        ):
            raise ValueError("TRANSPORT_POLICY_INVALID")
    codec = ActionTokenCodec(services.action_token_key)
    prepare, commit, reconcile = create_text_patch_port(
        resolve_binding=services.resolve_binding,
        clock_ms=services.clock_ms,
        run_io=services.run_io,
        token_codec=codec,
        artifact_store=services.artifact_store,
        host=services.host_binding,
        action_ttl_ms=services.action_ttl_ms,
    )
    return create_authenticated_action_server(
        authenticator=services.authenticator,
        policy=policy,
        now=services.now,
        audit_sink=services.audit_sink,
        prepare_port=prepare,
        commit_port=commit,
        reconcile_port=reconcile,
        allowed_hosts=services.allowed_hosts,
        call_receipt_sink=services.call_receipt_sink,
        allowed_origins=services.allowed_origins,
    )


__all__ = ["RuntimeServices", "create_deployment"]
