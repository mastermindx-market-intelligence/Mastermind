"""Pure, closed OAuth resource-server contracts for Business MCP apps.

This module deliberately contains no MCP SDK, JWT, HTTP client, filesystem,
network, persistence, Executive OS, or other control-plane dependency.  It
validates immutable policy data and projects only pseudonymous principal/audit
contracts.  Edge modules are responsible for signature verification and I/O.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import re
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import SplitResult, urlsplit


AUTH_POLICY_SCHEMA = "mastermind.business_mcp_auth_policy.v1"
AUTH_AUDIT_SCHEMA = "mastermind.business_mcp_auth_audit.v1"

POLICY_KEYS = frozenset(
    {
        "schema",
        "policy_id",
        "resource",
        "resource_metadata_url",
        "issuer",
        "authorization_servers",
        "jwks_uri",
        "required_scopes",
        "allowed_subject_digests",
        "allowed_algorithms",
        "clock_skew_seconds",
        "max_token_lifetime_seconds",
        "jwks_cache_ttl_seconds",
        "unknown_kid_refresh_cooldown_seconds",
        "fetch_failure_backoff_seconds",
    }
)

_POLICY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")
_SCOPE_RE = re.compile(r"^[a-z][a-z0-9._:-]{2,95}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_PERCENT_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_PATH_ATOM_RE = re.compile(r"[A-Za-z0-9._~!$&'()*+,;=:@/-]")
_URI_DANGEROUS = frozenset('"<> {}\\^|`')
_NON_AUTHORIZING_OAUTH_SCOPES = frozenset({"offline_access"})


class AuthErrorCode(str, enum.Enum):
    INVALID_POLICY = "invalid_policy"
    AUTHORIZATION_MISSING = "authorization_missing"
    AUTHORIZATION_MALFORMED = "authorization_malformed"
    TOKEN_TOO_LARGE = "token_too_large"
    TOKEN_HEADER_REFUSED = "token_header_refused"
    TOKEN_SIGNATURE_REFUSED = "token_signature_refused"
    TOKEN_CLAIMS_REFUSED = "token_claims_refused"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_NOT_YET_VALID = "token_not_yet_valid"
    TOKEN_LIFETIME_REFUSED = "token_lifetime_refused"
    ISSUER_REFUSED = "issuer_refused"
    RESOURCE_REFUSED = "resource_refused"
    SCOPE_REFUSED = "scope_refused"
    SUBJECT_REFUSED = "subject_refused"
    JWKS_UNAVAILABLE = "jwks_unavailable"
    JWKS_REFUSED = "jwks_refused"
    KEY_NOT_FOUND = "key_not_found"
    INTERNAL_ERROR = "internal_error"


_PUBLIC_MESSAGES: Mapping[AuthErrorCode, str] = {
    AuthErrorCode.INVALID_POLICY: "authentication policy refused",
    AuthErrorCode.AUTHORIZATION_MISSING: "authentication required",
    AuthErrorCode.AUTHORIZATION_MALFORMED: "authentication required",
    AuthErrorCode.JWKS_UNAVAILABLE: "authentication temporarily unavailable",
}


class AuthError(RuntimeError):
    """One typed refusal whose public text never contains dependency detail."""

    def __init__(self, code: AuthErrorCode) -> None:
        if not isinstance(code, AuthErrorCode):
            raise TypeError("AuthError requires an AuthErrorCode")
        public_message = _PUBLIC_MESSAGES.get(code, "authentication refused")
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


@dataclasses.dataclass(frozen=True)
class ResourcePolicy:
    schema: str
    policy_id: str
    resource: str
    resource_metadata_url: str
    issuer: str
    authorization_servers: tuple[str, ...]
    jwks_uri: str
    required_scopes: tuple[str, ...]
    allowed_subject_digests: tuple[str, ...]
    allowed_algorithms: tuple[str, ...]
    clock_skew_seconds: int
    max_token_lifetime_seconds: int
    jwks_cache_ttl_seconds: int
    unknown_kid_refresh_cooldown_seconds: int
    fetch_failure_backoff_seconds: int


@dataclasses.dataclass(frozen=True)
class VerifiedPrincipal:
    """Signature-verified, policy-authorized, pseudonymous caller projection."""

    policy_id: str
    issuer: str
    issuer_digest: str
    resource: str
    subject_digest: str
    client_ref: str
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int
    jti_digest: str | None


@dataclasses.dataclass(frozen=True)
class AuthAuditEvent:
    """Bounded audit fact; no token, raw subject, or provider payload."""

    schema: str
    policy_id: str
    code: str
    accepted: bool


class AuthAuditSink(Protocol):
    def emit(self, event: AuthAuditEvent) -> None: ...


def _refuse() -> None:
    raise AuthError(AuthErrorCode.INVALID_POLICY)


def _exact_text(value: Any, *, maximum: int = 1024) -> str:
    if not isinstance(value, str):
        _refuse()
    if not value or len(value) > maximum or value != value.strip():
        _refuse()
    if _CONTROL_RE.search(value):
        _refuse()
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        _refuse()
    return value


def _exact_subject(value: Any, *, maximum: int = 1024) -> str:
    """Validate one opaque JWT subject without normalizing exact UTF-8 bytes."""

    if not isinstance(value, str):
        _refuse()
    if not value or len(value) > maximum or value != value.strip():
        _refuse()
    if _CONTROL_RE.search(value):
        _refuse()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _refuse()
    return value


def _policy_id(value: Any) -> str:
    token = _exact_text(value, maximum=96)
    if _POLICY_ID_RE.fullmatch(token) is None:
        _refuse()
    return token


def _validate_exact_path(path: str) -> None:
    """Validate one exact RFC 3986 path without decoding or normalizing it."""

    index = 0
    while index < len(path):
        character = path[index]
        if character == "%":
            if _PERCENT_RE.fullmatch(path[index : index + 3]) is None:
                _refuse()
            index += 3
            continue
        if _PATH_ATOM_RE.fullmatch(character) is None:
            _refuse()
        index += 1


def _split_https_url(value: Any) -> tuple[str, SplitResult]:
    """Validate and preserve one exact, non-ambiguous HTTPS URI spelling."""

    token = _exact_text(value, maximum=2048)
    if any(character.isspace() for character in token):
        _refuse()
    if any(character in token for character in _URI_DANGEROUS):
        _refuse()
    if "?" in token or "#" in token:
        _refuse()
    try:
        parsed = urlsplit(token)
        port = parsed.port
    except (TypeError, ValueError):
        _refuse()
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or (parsed.path and not parsed.path.startswith("/"))
    ):
        _refuse()

    authority = token[len("https://") :].split("/", 1)[0]
    if not authority or "%" in authority:
        _refuse()
    _validate_exact_path(parsed.path)
    return token, parsed


def _sorted_unique_strings(
    value: Any,
    *,
    pattern: re.Pattern[str],
    maximum_items: int,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > maximum_items:
        _refuse()
    result: list[str] = []
    for item in value:
        token = _exact_text(item, maximum=128)
        if pattern.fullmatch(token) is None:
            _refuse()
        result.append(token)
    if result != sorted(result) or len(result) != len(set(result)):
        _refuse()
    return tuple(result)


def _bounded_integer(value: Any, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        _refuse()
    return value


def subject_digest(*, issuer: str, subject: str) -> str:
    """Digest exact canonical issuer and opaque subject UTF-8 bytes."""

    issuer_value, _issuer_parts = _split_https_url(issuer)
    subject_value = _exact_subject(subject, maximum=1024)
    return hashlib.sha256(
        f"{issuer_value}\n{subject_value}".encode("utf-8")
    ).hexdigest()


def load_resource_policy(value: object) -> ResourcePolicy:
    """Validate one exact closed policy wire and return an immutable contract."""

    if not isinstance(value, Mapping) or set(value) != POLICY_KEYS:
        _refuse()

    try:
        schema = value.get("schema")
        if schema != AUTH_POLICY_SCHEMA:
            _refuse()

        policy_id = _policy_id(value.get("policy_id"))
        resource, _resource_parts = _split_https_url(value.get("resource"))
        resource_metadata_url, _metadata_parts = _split_https_url(
            value.get("resource_metadata_url")
        )
        issuer, issuer_parts = _split_https_url(value.get("issuer"))

        authorization_servers_raw = value.get("authorization_servers")
        if authorization_servers_raw != [issuer]:
            _refuse()
        authorization_servers = (issuer,)

        jwks_uri, jwks_parts = _split_https_url(value.get("jwks_uri"))
        if (
            jwks_parts.scheme,
            jwks_parts.hostname,
            jwks_parts.port,
        ) != (
            issuer_parts.scheme,
            issuer_parts.hostname,
            issuer_parts.port,
        ):
            _refuse()

        required_scopes = _sorted_unique_strings(
            value.get("required_scopes"),
            pattern=_SCOPE_RE,
            maximum_items=32,
        )
        if set(required_scopes) & _NON_AUTHORIZING_OAUTH_SCOPES:
            _refuse()
        allowed_subject_digests = _sorted_unique_strings(
            value.get("allowed_subject_digests"),
            pattern=_DIGEST_RE,
            maximum_items=128,
        )

        algorithms = value.get("allowed_algorithms")
        if algorithms != ["RS256"]:
            _refuse()
        allowed_algorithms = ("RS256",)

        clock_skew_seconds = _bounded_integer(
            value.get("clock_skew_seconds"), minimum=0, maximum=120
        )
        max_token_lifetime_seconds = _bounded_integer(
            value.get("max_token_lifetime_seconds"), minimum=60, maximum=3600
        )
        jwks_cache_ttl_seconds = _bounded_integer(
            value.get("jwks_cache_ttl_seconds"), minimum=60, maximum=3600
        )
        unknown_kid_refresh_cooldown_seconds = _bounded_integer(
            value.get("unknown_kid_refresh_cooldown_seconds"),
            minimum=1,
            maximum=300,
        )
        fetch_failure_backoff_seconds = _bounded_integer(
            value.get("fetch_failure_backoff_seconds"),
            minimum=1,
            maximum=300,
        )
    except AuthError:
        raise
    except Exception:
        _refuse()

    return ResourcePolicy(
        schema=AUTH_POLICY_SCHEMA,
        policy_id=policy_id,
        resource=resource,
        resource_metadata_url=resource_metadata_url,
        issuer=issuer,
        authorization_servers=authorization_servers,
        jwks_uri=jwks_uri,
        required_scopes=required_scopes,
        allowed_subject_digests=allowed_subject_digests,
        allowed_algorithms=allowed_algorithms,
        clock_skew_seconds=clock_skew_seconds,
        max_token_lifetime_seconds=max_token_lifetime_seconds,
        jwks_cache_ttl_seconds=jwks_cache_ttl_seconds,
        unknown_kid_refresh_cooldown_seconds=(
            unknown_kid_refresh_cooldown_seconds
        ),
        fetch_failure_backoff_seconds=fetch_failure_backoff_seconds,
    )


def validate_resource_policy(value: object) -> ResourcePolicy:
    """Revalidate an existing policy through the sole closed wire parser.

    Frozen dataclasses can still be manually constructed, replaced, subclassed,
    or mutated through low-level object operations. Every authority-bearing edge
    therefore round-trips its policy through ``load_resource_policy`` instead of
    trusting construction history or duplicating policy rules.
    """

    if type(value) is not ResourcePolicy:
        _refuse()
    try:
        canonical = load_resource_policy(
            {
                "schema": value.schema,
                "policy_id": value.policy_id,
                "resource": value.resource,
                "resource_metadata_url": value.resource_metadata_url,
                "issuer": value.issuer,
                "authorization_servers": list(value.authorization_servers),
                "jwks_uri": value.jwks_uri,
                "required_scopes": list(value.required_scopes),
                "allowed_subject_digests": list(value.allowed_subject_digests),
                "allowed_algorithms": list(value.allowed_algorithms),
                "clock_skew_seconds": value.clock_skew_seconds,
                "max_token_lifetime_seconds": value.max_token_lifetime_seconds,
                "jwks_cache_ttl_seconds": value.jwks_cache_ttl_seconds,
                "unknown_kid_refresh_cooldown_seconds": (
                    value.unknown_kid_refresh_cooldown_seconds
                ),
                "fetch_failure_backoff_seconds": value.fetch_failure_backoff_seconds,
            }
        )
    except AuthError:
        raise
    except Exception:
        _refuse()
    if canonical != value:
        _refuse()
    return canonical


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
    "validate_resource_policy",
]