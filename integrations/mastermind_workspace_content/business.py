"""Compose the workspace content resource with the existing Business auth owner.

This module does not create an issuer, JWT key, token/session store, source grant,
content store, server process, or route enrollment.  The application owner must
supply one already accepted resource policy and the current source-access/read
callbacks.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AuthAuditEvent,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    VerifiedPrincipal,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_workspace_content.resource import WorkspaceContentResource

CONTENT_SCOPE = "mastermind.workspace.content.read"


class AuditSink(Protocol):
    def emit(self, event: AuthAuditEvent) -> None: ...


def _ticket(value: object) -> tuple[object, ...] | None:
    if type(value) is not tuple or not 1 <= len(value) <= 9:
        return None
    frozen: list[object] = []
    for item in value:
        if type(item) is int:
            frozen.append(item)
            continue
        if type(item) is str and 0 < len(item) <= 2048:
            frozen.append(item)
            continue
        return None
    return tuple(frozen)


def build_business_workspace_content_resource(
    *,
    authenticator: JwtAuthenticator,
    policy: ResourcePolicy,
    current_access: Callable[[VerifiedPrincipal, str], Awaitable[tuple[object, ...] | None]],
    read_source: Callable[[], Awaitable[bytes]],
    source_ref: str,
    now: Callable[[], int],
    allowed_origin: str,
    audit_sink: AuditSink,
) -> WorkspaceContentResource:
    """Return a fixed resource bound to existing auth and source owners."""

    if not isinstance(authenticator, JwtAuthenticator):
        raise TypeError("incumbent JwtAuthenticator is required")
    expected_policy = validate_resource_policy(policy)
    if expected_policy.required_scopes != (CONTENT_SCOPE,):
        raise ValueError("a separate accepted workspace content scope is required")
    if not callable(current_access) or not callable(read_source) or not callable(now):
        raise TypeError("current access, source read, and clock callbacks are required")
    if not callable(getattr(audit_sink, "emit", None)):
        raise TypeError("the incumbent closed audit sink is required")

    class BusinessContentOwner:
        async def authorize(
            self,
            authorization_header: str,
            resource: str,
            requested_source_ref: str,
        ) -> tuple[object, ...] | None:
            result: tuple[object, ...] | None = None
            code = AuthErrorCode.SCOPE_REFUSED.value
            try:
                result = await self._authorize(
                    authorization_header,
                    resource,
                    requested_source_ref,
                )
                if result is not None:
                    code = "accepted"
            except AuthError as error:
                code = error.code.value
            except Exception:
                code = AuthErrorCode.INTERNAL_ERROR.value
            try:
                audit_sink.emit(
                    AuthAuditEvent(
                        schema=AUTH_AUDIT_SCHEMA,
                        policy_id=expected_policy.policy_id,
                        code=code,
                        accepted=result is not None,
                    )
                )
            except Exception:
                return None
            return result

        async def _authorize(
            self,
            authorization_header: str,
            resource: str,
            requested_source_ref: str,
        ) -> tuple[object, ...] | None:
            if (
                resource != expected_policy.resource
                or requested_source_ref != source_ref
                or validate_resource_policy(authenticator.policy) != expected_policy
            ):
                return None
            instant = now()
            if type(instant) is not int:
                return None
            principal = await authenticator.verify_authorization_header(
                authorization_header,
                now=instant,
            )
            if (
                not isinstance(principal, VerifiedPrincipal)
                or validate_resource_policy(authenticator.policy) != expected_policy
                or principal.policy_id != expected_policy.policy_id
                or principal.resource != expected_policy.resource
                or principal.scopes != expected_policy.required_scopes
            ):
                return None
            access_evidence = _ticket(await current_access(principal, source_ref))
            if access_evidence is None:
                return None
            final_time = now()
            if (
                type(final_time) is not int
                or final_time < instant
                or final_time > principal.expires_at + expected_policy.clock_skew_seconds
                or validate_resource_policy(authenticator.policy) != expected_policy
            ):
                return None
            return (
                principal.policy_id,
                principal.issuer_digest,
                principal.subject_digest,
                principal.client_ref,
                principal.jti_digest or "no-jti",
                principal.issued_at,
                principal.expires_at,
                *access_evidence,
            )

        async def read(self, requested_source_ref: str) -> bytes:
            if requested_source_ref != source_ref:
                raise ValueError("source reference changed")
            return await read_source()

    return WorkspaceContentResource(
        owner=BusinessContentOwner(),
        resource=expected_policy.resource,
        source_ref=source_ref,
        allowed_origin=allowed_origin,
    )


__all__ = ["CONTENT_SCOPE", "build_business_workspace_content_resource"]
