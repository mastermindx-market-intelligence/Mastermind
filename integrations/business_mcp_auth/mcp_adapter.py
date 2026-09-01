"""Least-privilege MCP SDK adapter for verified Business principals.

This module is the package's only MCP SDK edge. It projects one already
verified pseudonymous principal into ``AccessToken`` form and emits one closed
audit fact. It creates no server, tool, route, backend call, credential,
session, persistence, retry, lifecycle, or organizational authority.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable

from mcp.server.auth.provider import AccessToken, TokenVerifier

from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AuthAuditEvent,
    AuthAuditSink,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    VerifiedPrincipal,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator


_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_UNAVAILABLE_CLIENT_REF = "oauth-client-unavailable"


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _HEX_DIGEST_RE.fullmatch(value) is not None


def _principal_matches_policy(
    principal: object,
    policy: ResourcePolicy,
) -> bool:
    try:
        policy = validate_resource_policy(policy)
    except AuthError:
        return False
    if not isinstance(principal, VerifiedPrincipal):
        return False
    if (
        principal.policy_id != policy.policy_id
        or principal.issuer != policy.issuer
        or principal.resource != policy.resource
        or principal.scopes != policy.required_scopes
    ):
        return False
    if type(principal.issued_at) is not int or type(principal.expires_at) is not int:
        return False
    if principal.expires_at <= principal.issued_at:
        return False

    expected_issuer_digest = hashlib.sha256(
        policy.issuer.encode("utf-8")
    ).hexdigest()
    if (
        not _is_digest(principal.issuer_digest)
        or not hmac.compare_digest(principal.issuer_digest, expected_issuer_digest)
    ):
        return False
    if not _is_digest(principal.subject_digest):
        return False
    subject_allowed = False
    for allowed in policy.allowed_subject_digests:
        # Evaluate every allowlist entry even after a match. Bitwise boolean
        # accumulation avoids the early exit semantics of ``any`` and ``or``.
        subject_allowed |= hmac.compare_digest(principal.subject_digest, allowed)
    if not subject_allowed:
        return False
    if not (
        _is_digest(principal.client_ref)
        or principal.client_ref == _UNAVAILABLE_CLIENT_REF
    ):
        return False
    if principal.jti_digest is not None and not _is_digest(principal.jti_digest):
        return False
    return True


class MastermindTokenVerifier(TokenVerifier):
    """Adapt one configured Business resource policy to MCP authentication."""

    def __init__(
        self,
        *,
        authenticator: JwtAuthenticator,
        policy: ResourcePolicy,
        now: Callable[[], int],
        audit_sink: AuthAuditSink,
    ) -> None:
        if not isinstance(authenticator, JwtAuthenticator):
            raise TypeError("authenticator must be JwtAuthenticator")
        if not isinstance(policy, ResourcePolicy):
            raise TypeError("policy must be ResourcePolicy")
        if not callable(now):
            raise TypeError("now must be callable")
        if not callable(getattr(audit_sink, "emit", None)):
            raise TypeError("audit_sink must provide emit")
        self._authenticator = authenticator
        self._policy = validate_resource_policy(policy)
        self._now = now
        self._audit_sink = audit_sink

    def _emit(self, *, code: str, accepted: bool) -> bool:
        event = AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=self._policy.policy_id,
            code=code,
            accepted=accepted,
        )
        try:
            self._audit_sink.emit(event)
        except Exception:
            return False
        return True

    def _refuse_internal(self) -> None:
        self._emit(
            code=AuthErrorCode.INTERNAL_ERROR.value,
            accepted=False,
        )

    def _authenticator_policy_matches(self) -> bool:
        """Revalidate the exact immutable verifier policy before token work."""

        try:
            expected_policy = validate_resource_policy(self._policy)
            bound_policy = validate_resource_policy(self._authenticator.policy)
        except Exception:
            return False
        return bound_policy == expected_policy

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return one closed MCP token projection or fail closed with ``None``."""

        # The JWT verifier and MCP adapter must be one exact policy composition.
        # Refuse before reading the clock or asking the authenticator to inspect
        # attacker-controlled token bytes when that trusted composition drifted.
        if not self._authenticator_policy_matches():
            self._refuse_internal()
            return None

        try:
            now = self._now()
        except Exception:
            self._refuse_internal()
            return None
        if type(now) is not int:
            self._refuse_internal()
            return None

        try:
            principal = await self._authenticator.verify_token(token, now=now)
        except AuthError as error:
            self._emit(code=error.code.value, accepted=False)
            return None
        except Exception:
            self._refuse_internal()
            return None

        try:
            if not _principal_matches_policy(principal, self._policy):
                self._refuse_internal()
                return None
            access = AccessToken(
                token=token,
                client_id=principal.client_ref,
                scopes=list(principal.scopes),
                expires_at=principal.expires_at,
                resource=principal.resource,
                subject=principal.subject_digest,
                claims={
                    "issuer_digest": principal.issuer_digest,
                    "client_ref": principal.client_ref,
                    "jti_digest": principal.jti_digest,
                },
            )
        except Exception:
            self._refuse_internal()
            return None

        if not self._emit(code="accepted", accepted=True):
            return None
        return access


__all__ = ["MastermindTokenVerifier"]