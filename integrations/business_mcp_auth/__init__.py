"""Pure Business MCP OAuth resource-server contract package.

Edge modules are intentionally not imported here so this package remains usable
without MCP, PyJWT, HTTPX, network, filesystem, or control-plane dependencies.
"""
from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AUTH_POLICY_SCHEMA,
    POLICY_KEYS,
    AuthAuditEvent,
    AuthAuditSink,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    VerifiedPrincipal,
    load_resource_policy,
    subject_digest,
)

__all__ = [
    "AUTH_AUDIT_SCHEMA",
    "AUTH_POLICY_SCHEMA",
    "POLICY_KEYS",
    "AuthAuditEvent",
    "AuthAuditSink",
    "AuthError",
    "AuthErrorCode",
    "ResourcePolicy",
    "VerifiedPrincipal",
    "load_resource_policy",
    "subject_digest",
]
