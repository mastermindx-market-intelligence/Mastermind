"""Pure post-signature JWT header and claims validation for Business MCP.

The caller must supply a signature-verified claims mapping.  This module owns
only deterministic policy enforcement and pseudonymous projection; it parses no
compact token, fetches no key, performs no I/O, and grants no organizational
role or Mastermind runtime authority.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping
from typing import Any

from integrations.business_mcp_auth.contracts import (
    AuthError,
    AuthErrorCode,
    NON_AUTHORIZING_OAUTH_SCOPES,
    ResourcePolicy,
    VerifiedPrincipal,
    _CONTROL_RE,
    _SCOPE_RE,
    _exact_subject,
    subject_digest,
    validate_resource_policy,
)


_KID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FORBIDDEN_HEADER_KEYS = frozenset({"jku", "x5u", "x5c", "jwk"})
_REQUIRED_CLAIMS = frozenset({"iss", "sub", "aud", "iat", "exp", "scope"})
_MAX_SCOPE_CHARS = 4096
_MAX_SCOPE_ITEMS = 32


def _refuse(code: AuthErrorCode) -> None:
    raise AuthError(code)


def _opaque_claim(value: Any, *, maximum: int = 1024) -> str:
    try:
        return _exact_subject(value, maximum=maximum)
    except AuthError:
        _refuse(AuthErrorCode.TOKEN_CLAIMS_REFUSED)


def _integer_claim(value: Any) -> int:
    if type(value) is not int:
        _refuse(AuthErrorCode.TOKEN_CLAIMS_REFUSED)
    return value


def _scope_claim(value: Any, policy: ResourcePolicy) -> tuple[str, ...]:
    if not isinstance(value, str):
        _refuse(AuthErrorCode.SCOPE_REFUSED)
    if (
        not value
        or len(value) > _MAX_SCOPE_CHARS
        or value != value.strip()
        or _CONTROL_RE.search(value)
        or "  " in value
    ):
        _refuse(AuthErrorCode.SCOPE_REFUSED)
    tokens = value.split(" ")
    if not tokens or len(tokens) > _MAX_SCOPE_ITEMS:
        _refuse(AuthErrorCode.SCOPE_REFUSED)
    if any(_SCOPE_RE.fullmatch(token) is None for token in tokens):
        _refuse(AuthErrorCode.SCOPE_REFUSED)
    if len(tokens) != len(set(tokens)):
        _refuse(AuthErrorCode.SCOPE_REFUSED)

    granted = frozenset(tokens)
    required = frozenset(policy.required_scopes)
    if not required.issubset(granted):
        _refuse(AuthErrorCode.SCOPE_REFUSED)
    if granted - required - NON_AUTHORIZING_OAUTH_SCOPES:
        _refuse(AuthErrorCode.SCOPE_REFUSED)

    # The verified principal carries resource authorization only.  The one
    # accepted OAuth session capability is deliberately consumed at this
    # boundary and never projected into MCP tool authority.
    return policy.required_scopes


def _optional_digest_claim(claims: Mapping[str, Any], name: str) -> str | None:
    if name not in claims:
        return None
    value = _opaque_claim(claims.get(name))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _client_ref(claims: Mapping[str, Any], issuer: str) -> str:
    missing = object()
    client_id = claims.get("client_id", missing)
    authorized_party = claims.get("azp", missing)
    if client_id is missing and authorized_party is missing:
        return "oauth-client-unavailable"

    client_value: str | None = None
    if client_id is not missing:
        client_value = _opaque_claim(client_id)
    if authorized_party is not missing:
        azp_value = _opaque_claim(authorized_party)
        if client_value is not None and client_value != azp_value:
            _refuse(AuthErrorCode.TOKEN_CLAIMS_REFUSED)
        client_value = azp_value
    if client_value is None:  # pragma: no cover - guarded by the branches above
        _refuse(AuthErrorCode.TOKEN_CLAIMS_REFUSED)
    return hashlib.sha256(
        (issuer + "\nclient\n" + client_value).encode("utf-8")
    ).hexdigest()


def validate_jwt_header(header: Mapping[str, object], policy: ResourcePolicy) -> str:
    """Validate the untrusted JWT header and return only the exact key id."""

    if not isinstance(policy, ResourcePolicy):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    policy = validate_resource_policy(policy)
    if not isinstance(header, Mapping):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    if header.get("alg") != "RS256" or "RS256" not in policy.allowed_algorithms:
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    if _FORBIDDEN_HEADER_KEYS & set(header):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    critical = header.get("crit")
    if critical not in (None, [], ()):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    token_type = header.get("typ")
    if token_type not in (None, "JWT", "at+jwt"):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)

    kid = header.get("kid")
    if (
        not isinstance(kid, str)
        or len(kid) > 128
        or kid != kid.strip()
        or _CONTROL_RE.search(kid)
        or _KID_RE.fullmatch(kid) is None
    ):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    return kid


def validate_verified_claims(
    claims: Mapping[str, object],
    policy: ResourcePolicy,
    *,
    now: int,
) -> VerifiedPrincipal:
    """Enforce exact resource policy over a signature-verified claims mapping."""

    if not isinstance(policy, ResourcePolicy):
        _refuse(AuthErrorCode.TOKEN_CLAIMS_REFUSED)
    policy = validate_resource_policy(policy)
    if not isinstance(claims, Mapping):
        _refuse(AuthErrorCode.TOKEN_CLAIMS_REFUSED)
    if type(now) is not int:
        _refuse(AuthErrorCode.TOKEN_CLAIMS_REFUSED)
    if not _REQUIRED_CLAIMS.issubset(claims):
        _refuse(AuthErrorCode.TOKEN_CLAIMS_REFUSED)

    issuer = claims.get("iss")
    if not isinstance(issuer, str) or issuer != policy.issuer:
        _refuse(AuthErrorCode.ISSUER_REFUSED)

    audience = claims.get("aud")
    if not isinstance(audience, str) or audience != policy.resource:
        _refuse(AuthErrorCode.RESOURCE_REFUSED)

    issued_at = _integer_claim(claims.get("iat"))
    expires_at = _integer_claim(claims.get("exp"))
    not_before: int | None = None
    if "nbf" in claims:
        not_before = _integer_claim(claims.get("nbf"))

    lifetime = expires_at - issued_at
    if lifetime <= 0 or lifetime > policy.max_token_lifetime_seconds:
        _refuse(AuthErrorCode.TOKEN_LIFETIME_REFUSED)

    skew = policy.clock_skew_seconds
    if now > expires_at + skew:
        _refuse(AuthErrorCode.TOKEN_EXPIRED)
    if now + skew < issued_at:
        _refuse(AuthErrorCode.TOKEN_NOT_YET_VALID)
    if not_before is not None and now + skew < not_before:
        _refuse(AuthErrorCode.TOKEN_NOT_YET_VALID)

    scopes = _scope_claim(claims.get("scope"), policy)

    subject = claims.get("sub")
    try:
        subject_ref = subject_digest(issuer=policy.issuer, subject=subject)  # type: ignore[arg-type]
    except AuthError:
        _refuse(AuthErrorCode.TOKEN_CLAIMS_REFUSED)
    subject_allowed = False
    for allowed in policy.allowed_subject_digests:
        # Evaluate every configured digest even after a match. Bitwise boolean
        # accumulation avoids the early-exit semantics of ``any`` and ``or``.
        subject_allowed |= hmac.compare_digest(subject_ref, allowed)
    if not subject_allowed:
        _refuse(AuthErrorCode.SUBJECT_REFUSED)

    jti_digest = _optional_digest_claim(claims, "jti")
    client_ref = _client_ref(claims, policy.issuer)
    issuer_digest = hashlib.sha256(policy.issuer.encode("utf-8")).hexdigest()

    return VerifiedPrincipal(
        policy_id=policy.policy_id,
        issuer=policy.issuer,
        issuer_digest=issuer_digest,
        resource=policy.resource,
        subject_digest=subject_ref,
        client_ref=client_ref,
        scopes=scopes,
        issued_at=issued_at,
        expires_at=expires_at,
        jti_digest=jti_digest,
    )


__all__ = ["validate_jwt_header", "validate_verified_claims"]
