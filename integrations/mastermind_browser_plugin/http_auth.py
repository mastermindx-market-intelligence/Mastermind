"""Strict Browser HTTP bearer projection over the existing Business auth owner.

The Browser plugin owns no OAuth provider, credential, token/session store,
discovery cache, JWKS fetcher, user directory, or authorization policy. An
already-configured Business MCP JwtAuthenticator/ResourcePolicy composition
remains the cryptographic authority. This module only:

1. rejects ambiguous HTTP Authorization representation;
2. delegates compact-token verification/audit to MastermindTokenVerifier; and
3. projects the verified pseudonymous caller into ActionCaller for Browser refs.

Auth0 tenant/client/resource values are configuration and remain deliberately
outside this source module.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Callable
from typing import Any, Protocol

from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AuthAuditEvent,
    AuthAuditSink,
    AuthErrorCode,
    ResourcePolicy,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.workbench_action_mcp.contracts import ActionCaller

BROWSER_CONTROL_SCOPE = "browser.control"
_MAX_AUTHORIZATION_BYTES = 20 * 1024
_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_UNAVAILABLE_CLIENT_REF = "oauth-client-unavailable"


class BrowserHttpAuthError(TypeError):
    """Trusted composition is invalid before request authentication begins."""


class TokenVerifierPort(Protocol):
    async def verify_token(self, token: str) -> Any: ...


def _valid_client_ref(value: object) -> bool:
    return (
        type(value) is str
        and (
            _HEX64.fullmatch(value) is not None
            or value == _UNAVAILABLE_CLIENT_REF
        )
    )


@dataclass(frozen=True, slots=True)
class BrowserHttpAuth:
    """One immutable Browser resource-auth edge.

    token_verifier is normally the existing MastermindTokenVerifier. The
    protocol shape is intentionally small so tests can prove HTTP behavior
    without constructing or contacting an identity provider.
    """

    policy: ResourcePolicy
    token_verifier: TokenVerifierPort
    audit_sink: AuthAuditSink

    def __post_init__(self) -> None:
        try:
            selected = validate_resource_policy(self.policy)
        except Exception as exc:
            raise BrowserHttpAuthError("Browser auth policy is invalid") from exc
        if selected.required_scopes != (BROWSER_CONTROL_SCOPE,):
            raise BrowserHttpAuthError("Browser control scope is required")
        if not callable(getattr(self.token_verifier, "verify_token", None)):
            raise BrowserHttpAuthError("Browser token verifier is required")
        if not callable(getattr(self.audit_sink, "emit", None)):
            raise BrowserHttpAuthError("Browser auth audit sink is required")

    @property
    def auth_challenge(self) -> str:
        policy = validate_resource_policy(self.policy)
        return (
            'Bearer resource_metadata="'
            + policy.resource_metadata_url
            + '"'
        )

    def _emit_preverification_refusal(self, code: AuthErrorCode) -> bool:
        try:
            self.audit_sink.emit(
                AuthAuditEvent(
                    schema=AUTH_AUDIT_SCHEMA,
                    policy_id=self.policy.policy_id,
                    code=code.value,
                    accepted=False,
                )
            )
        except Exception:
            return False
        return True

    def _token_from_request(self, request: Any) -> tuple[str | None, AuthErrorCode | None]:
        scope = getattr(request, "scope", None)
        if not isinstance(scope, dict):
            return None, AuthErrorCode.AUTHORIZATION_MALFORMED
        raw_headers = scope.get("headers", ())
        if not isinstance(raw_headers, (list, tuple)):
            return None, AuthErrorCode.AUTHORIZATION_MALFORMED

        values: list[bytes] = []
        for row in raw_headers:
            if (
                not isinstance(row, (list, tuple))
                or len(row) != 2
                or not isinstance(row[0], bytes)
                or not isinstance(row[1], bytes)
            ):
                return None, AuthErrorCode.AUTHORIZATION_MALFORMED
            if row[0].lower() == b"authorization":
                values.append(row[1])

        if not values:
            return None, AuthErrorCode.AUTHORIZATION_MISSING
        if len(values) != 1:
            return None, AuthErrorCode.AUTHORIZATION_MALFORMED

        raw = values[0]
        if (
            not raw
            or len(raw) > _MAX_AUTHORIZATION_BYTES
            or any(byte < 32 or byte == 127 for byte in raw)
        ):
            return None, AuthErrorCode.AUTHORIZATION_MALFORMED
        try:
            header = raw.decode("ascii", errors="strict")
        except UnicodeDecodeError:
            return None, AuthErrorCode.AUTHORIZATION_MALFORMED

        if header != header.strip() or header.count(" ") != 1:
            return None, AuthErrorCode.AUTHORIZATION_MALFORMED
        scheme, token = header.split(" ", 1)
        if scheme.lower() != "bearer" or not token:
            return None, AuthErrorCode.AUTHORIZATION_MALFORMED
        if (
            len(token.encode("ascii")) > 16 * 1024
            or token.count(".") != 2
            or any(_SEGMENT.fullmatch(segment) is None for segment in token.split("."))
        ):
            return None, AuthErrorCode.AUTHORIZATION_MALFORMED
        return token, None

    async def authenticate(self, request: Any) -> ActionCaller | None:
        token, refusal = self._token_from_request(request)
        if refusal is not None:
            self._emit_preverification_refusal(refusal)
            return None
        assert token is not None

        try:
            access = await self.token_verifier.verify_token(token)
        except Exception:
            self._emit_preverification_refusal(AuthErrorCode.INTERNAL_ERROR)
            return None
        if access is None:
            return None

        policy = validate_resource_policy(self.policy)
        try:
            subject = access.subject
            client_ref = access.client_id
            resource = str(access.resource)
            scopes = tuple(access.scopes)
            expires_at = access.expires_at
        except Exception:
            self._emit_preverification_refusal(AuthErrorCode.INTERNAL_ERROR)
            return None

        if (
            type(subject) is not str
            or _HEX64.fullmatch(subject) is None
            or subject not in policy.allowed_subject_digests
            or not _valid_client_ref(client_ref)
            or resource != policy.resource
            or scopes != policy.required_scopes
            or type(expires_at) is not int
            or isinstance(expires_at, bool)
            or expires_at <= 0
        ):
            self._emit_preverification_refusal(AuthErrorCode.INTERNAL_ERROR)
            return None

        return ActionCaller(
            subject_digest=subject,
            client_ref=client_ref,
            resource=resource,
            scopes=scopes,
            expires_at=expires_at,
        )


def build_browser_http_auth(
    *,
    authenticator: JwtAuthenticator,
    policy: ResourcePolicy,
    now: Callable[[], int],
    audit_sink: AuthAuditSink,
) -> BrowserHttpAuth:
    """Bind Browser HTTP to the accepted Business OAuth verifier contracts."""
    if type(authenticator) is not JwtAuthenticator:
        raise BrowserHttpAuthError("Browser JwtAuthenticator is required")
    try:
        selected = validate_resource_policy(policy)
        bound = validate_resource_policy(authenticator.policy)
    except Exception as exc:
        raise BrowserHttpAuthError("Browser auth policy is invalid") from exc
    if selected != bound:
        raise BrowserHttpAuthError("Browser authenticator policy mismatch")
    if selected.required_scopes != (BROWSER_CONTROL_SCOPE,):
        raise BrowserHttpAuthError("Browser control scope is required")
    if not callable(now):
        raise BrowserHttpAuthError("Browser auth clock is required")
    if not callable(getattr(audit_sink, "emit", None)):
        raise BrowserHttpAuthError("Browser auth audit sink is required")

    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=selected,
        now=now,
        audit_sink=audit_sink,
    )
    return BrowserHttpAuth(
        policy=selected,
        token_verifier=verifier,
        audit_sink=audit_sink,
    )


__all__ = [
    "BROWSER_CONTROL_SCOPE",
    "BrowserHttpAuth",
    "BrowserHttpAuthError",
    "TokenVerifierPort",
    "build_browser_http_auth",
]
