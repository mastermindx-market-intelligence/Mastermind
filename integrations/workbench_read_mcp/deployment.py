"""Inert Workbench composition over borrowed, existing-owner services.

No root, grant, executor, listener, credential or lifecycle is created here.
RuntimeServices describes injected capabilities; construction is not attestation
that a host or an account has been admitted to use them.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from integrations.business_mcp_auth.contracts import (
    AuthAuditSink, ResourcePolicy, validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from .app import create_authenticated_read_server
from .observer import MAX_FILE_BYTES, MAX_TEXT_BYTES
from .read_port import BindingResolver, ReadExecutor, create_descriptor_read_port


@dataclass(frozen=True)
class RuntimeServices:
    """Borrowed owner projections; no factories, persistence or cleanup rights."""

    authenticator: JwtAuthenticator
    policy: ResourcePolicy
    now: Callable[[], int]
    clock_ms: Callable[[], int]
    audit_sink: AuthAuditSink
    resolve_binding: BindingResolver
    run_io: ReadExecutor
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...] = ()


def observation_schema() -> dict[str, Any]:
    """Fresh schema for the existing descriptor result, plus port project_ref.

    Byte/range/hash relationships remain checked by the protected observer/port;
    this closes the advertised shape without claiming a new observation epoch.
    """
    digest = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    integer = {'type': 'integer', 'minimum': 0, 'maximum': MAX_FILE_BYTES}
    reference = {'type': 'string', 'minLength': 1, 'maxLength': 256,
                 'pattern': '^[^\x00-\x1f\x7f]+$'}
    properties = {
        'status': {'const': 'OK'},
        'relative_path': {'type': 'string', 'minLength': 1, 'maxLength': 1024},
        'project_ref': {'type': 'string', 'minLength': 1, 'maxLength': 128,
                        'pattern': '^[A-Za-z0-9][A-Za-z0-9._:-]*$'},
        'context_ref': dict(reference), 'owner_ref': dict(reference),
        'generation': dict(reference), 'view_kind': {'const': 'WORKING_TREE'},
        'committed_head': {'anyOf': [{'type': 'null'},
                                    {'type': 'string', 'pattern': '^[0-9a-f]{40}$'}]},
        'file_sha256': dict(digest), 'file_identity_digest': dict(digest),
        'observation_digest': dict(digest),
        'file_bytes': dict(integer), 'total_lines': dict(integer),
        'line_start': dict(integer), 'line_end': dict(integer),
        'content': {'type': 'string', 'maxLength': MAX_TEXT_BYTES},
        'content_bytes': {'type': 'integer', 'minimum': 0, 'maximum': MAX_TEXT_BYTES},
        'truncated': {'type': 'boolean'},
        'next_line': {'anyOf': [{'type': 'null'}, dict(integer)]},
        'observed_at_ms': {'type': 'integer', 'minimum': 0, 'maximum': 2**63 - 1},
        'index_status': {'const': 'NOT_OBSERVED'},
        'atomic_workspace_snapshot': {'const': False},
    }
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def create_deployment(services: RuntimeServices):
    """Construct the real server; the existing host owns all acquired services.

    The host must authorize bindings and enforce bounded admission/deadlines in
    run_io. A callable cannot prove those contracts. Qualification and explicit
    runtime admission are separate from this constructor's structural checks.
    """
    if not isinstance(services, RuntimeServices):
        raise ValueError('RUNTIME_SERVICES_REQUIRED')
    if (not isinstance(services.authenticator, JwtAuthenticator)
            or not callable(getattr(services.audit_sink, 'emit', None))
            or not all(callable(value) for value in
                       (services.now, services.clock_ms, services.resolve_binding, services.run_io))):
        raise ValueError('RUNTIME_SERVICES_INVALID')
    if validate_resource_policy(services.policy) != validate_resource_policy(services.authenticator.policy):
        raise ValueError('AUTH_POLICY_BINDING_MISMATCH')
    for addresses, required in ((services.allowed_hosts, True), (services.allowed_origins, False)):
        if (type(addresses) is not tuple or (required and not addresses)
                or any(type(item) is not str or not item or '*' in item
                       or any(ord(c) <= 32 or ord(c) == 127 for c in item) for item in addresses)):
            raise ValueError('TRANSPORT_POLICY_INVALID')
    port = create_descriptor_read_port(resolve_binding=services.resolve_binding,
                                      clock_ms=services.clock_ms, run_io=services.run_io)
    return create_authenticated_read_server(
        authenticator=services.authenticator, policy=services.policy, now=services.now,
        audit_sink=services.audit_sink, read_port=port, output_schema=observation_schema(),
        allowed_hosts=services.allowed_hosts, allowed_origins=services.allowed_origins,
    )
