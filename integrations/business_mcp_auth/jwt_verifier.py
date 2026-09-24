"""Strict RS256 bearer verification for Business MCP resource servers.

This module is the package's only PyJWT edge.  It composes the accepted pure
header/claims policy with the exact-URL JWKS cache and creates no token/session
store, authorization server, retry loop, credential, MCP surface, or backend
authority.
"""
from __future__ import annotations

import base64
import binascii
import json
import math
import re
from collections.abc import Mapping
from typing import Protocol

import jwt

from integrations.business_mcp_auth.claims import (
    validate_jwt_header,
    validate_verified_claims,
)
from integrations.business_mcp_auth.contracts import (
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    VerifiedPrincipal,
    validate_resource_policy,
)


MAX_TOKEN_BYTES = 16 * 1024

_COMPACT_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_DECODE_OPTIONS = {
    "verify_signature": True,
    "enforce_minimum_key_length": True,
    "verify_exp": False,
    "verify_nbf": False,
    "verify_iat": False,
    "verify_aud": False,
    "verify_iss": False,
    "require": [],
}


class JwksKeySource(Protocol):
    async def key_for(self, kid: str) -> Mapping[str, object]: ...


class _DuplicateJsonMember(ValueError):
    """Raised only inside the strict compact-token representation preflight."""


class _NonFiniteJsonNumber(ValueError):
    """Raised when a JWT segment contains a JSON number outside RFC 8259."""


def _refuse(code: AuthErrorCode) -> None:
    raise AuthError(code)


def _canonical_segment_bytes(segment: str) -> bytes:
    """Decode one unpadded base64url segment and reject alternate spellings."""

    try:
        decoded = base64.b64decode(
            segment + "=" * (-len(segment) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if canonical != segment:
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    return decoded


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonMember
        result[key] = value
    return result


def _reject_nonfinite_json_constant(_value: str) -> object:
    raise _NonFiniteJsonNumber


def _refuse_nonfinite_json_values(value: object) -> None:
    """Reject exponent overflow without recursively walking attacker data."""

    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, float) and not math.isfinite(current):
            raise _NonFiniteJsonNumber
        if isinstance(current, dict):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)


def _strict_header_json(payload: bytes) -> dict[str, object]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonfinite_json_constant,
        )
        _refuse_nonfinite_json_values(value)
    except (RecursionError, ValueError):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    if not isinstance(value, dict):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    return value


def _preflight_payload_json(payload: bytes) -> None:
    """Reject ambiguous JSON while preserving malformed-payload error parity.

    Invalid UTF-8 or malformed JSON retains the established post-key
    signature-decode refusal. Duplicate members, non-finite numbers, parser
    depth faults, and integer conversion-limit faults are unambiguous bounded
    representation refusals and never reach JWKS access.
    """

    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonfinite_json_constant,
        )
        _refuse_nonfinite_json_values(value)
    except (_DuplicateJsonMember, _NonFiniteJsonNumber, RecursionError):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    except ValueError:
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)


def _compact_token(token: object) -> str:
    if not isinstance(token, str) or not token or token != token.strip():
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    try:
        token_bytes = token.encode("ascii")
    except UnicodeEncodeError:
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    if len(token_bytes) > MAX_TOKEN_BYTES:
        _refuse(AuthErrorCode.TOKEN_TOO_LARGE)
    if _CONTROL_RE.search(token):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
    segments = token.split(".")
    if len(segments) != 3 or any(
        not segment or _COMPACT_SEGMENT_RE.fullmatch(segment) is None
        for segment in segments
    ):
        _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)

    header_bytes, payload_bytes, _signature_bytes = (
        _canonical_segment_bytes(segment) for segment in segments
    )
    _strict_header_json(header_bytes)
    _preflight_payload_json(payload_bytes)
    return token


def _authorization_token(header: object) -> str:
    if header is None:
        _refuse(AuthErrorCode.AUTHORIZATION_MISSING)
    if not isinstance(header, str) or not header or header != header.strip():
        _refuse(AuthErrorCode.AUTHORIZATION_MALFORMED)
    try:
        header.encode("ascii")
    except UnicodeEncodeError:
        _refuse(AuthErrorCode.AUTHORIZATION_MALFORMED)
    if _CONTROL_RE.search(header) or header.count(" ") != 1:
        _refuse(AuthErrorCode.AUTHORIZATION_MALFORMED)
    scheme, token = header.split(" ", 1)
    if scheme.lower() != "bearer" or not token:
        _refuse(AuthErrorCode.AUTHORIZATION_MALFORMED)
    if token.count(".") != 2 or any(
        _COMPACT_SEGMENT_RE.fullmatch(segment) is None
        for segment in token.split(".")
    ):
        _refuse(AuthErrorCode.AUTHORIZATION_MALFORMED)
    return token


class JwtAuthenticator:
    """Verify one bearer token against one immutable resource policy."""

    def __init__(
        self,
        *,
        policy: ResourcePolicy,
        jwks_cache: JwksKeySource,
    ) -> None:
        if not isinstance(policy, ResourcePolicy):
            raise TypeError("policy must be ResourcePolicy")
        if not callable(getattr(jwks_cache, "key_for", None)):
            raise TypeError("jwks_cache must provide key_for")
        self._policy = validate_resource_policy(policy)
        self._jwks_cache = jwks_cache

    @property
    def policy(self) -> ResourcePolicy:
        """Return the exact immutable policy bound to this authenticator."""

        return self._policy

    async def verify_authorization_header(
        self,
        header: object,
        *,
        now: int,
    ) -> VerifiedPrincipal:
        token = _authorization_token(header)
        return await self.verify_token(token, now=now)

    async def verify_token(
        self,
        token: object,
        *,
        now: int,
    ) -> VerifiedPrincipal:
        # Revalidate before parsing attacker-controlled token bytes or touching
        # JWKS state. A frozen policy can still be replaced or low-level mutated.
        policy = validate_resource_policy(self._policy)
        compact = _compact_token(token)

        try:
            unverified_header = jwt.get_unverified_header(compact)
        except (jwt.PyJWTError, TypeError, ValueError):
            _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)
        except Exception:
            _refuse(AuthErrorCode.INTERNAL_ERROR)

        try:
            kid = validate_jwt_header(unverified_header, policy)
        except AuthError:
            raise
        except Exception:
            _refuse(AuthErrorCode.INTERNAL_ERROR)

        try:
            key_mapping = await self._jwks_cache.key_for(kid)
        except AuthError:
            raise
        except Exception:
            _refuse(AuthErrorCode.INTERNAL_ERROR)

        try:
            if not isinstance(key_mapping, Mapping):
                _refuse(AuthErrorCode.TOKEN_SIGNATURE_REFUSED)
            jwk = jwt.PyJWK.from_dict(dict(key_mapping), algorithm="RS256")
            if jwk.algorithm_name != "RS256":
                _refuse(AuthErrorCode.TOKEN_SIGNATURE_REFUSED)
            verified = jwt.decode_complete(
                compact,
                key=jwk.key,
                algorithms=["RS256"],
                options=dict(_DECODE_OPTIONS),
            )
        except AuthError:
            raise
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            _refuse(AuthErrorCode.TOKEN_SIGNATURE_REFUSED)
        except Exception:
            _refuse(AuthErrorCode.INTERNAL_ERROR)

        if not isinstance(verified, Mapping):
            _refuse(AuthErrorCode.TOKEN_SIGNATURE_REFUSED)
        verified_header = verified.get("header")
        payload = verified.get("payload")
        if not isinstance(verified_header, Mapping) or not isinstance(payload, Mapping):
            _refuse(AuthErrorCode.TOKEN_SIGNATURE_REFUSED)

        try:
            verified_kid = validate_jwt_header(verified_header, policy)
        except AuthError:
            raise
        except Exception:
            _refuse(AuthErrorCode.INTERNAL_ERROR)
        if verified_kid != kid:
            _refuse(AuthErrorCode.TOKEN_HEADER_REFUSED)

        try:
            return validate_verified_claims(payload, policy, now=now)
        except AuthError:
            raise
        except Exception:
            _refuse(AuthErrorCode.INTERNAL_ERROR)


__all__ = ["MAX_TOKEN_BYTES", "JwksKeySource", "JwtAuthenticator"]