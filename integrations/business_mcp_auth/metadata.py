"""Pure OAuth metadata and challenge helpers for Business MCP apps.

This module performs deterministic validation and projection only.  It owns no
HTTP client, discovery cache, OAuth client registration, credential, MCP server,
Business workspace state, or backend authority.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Literal

from integrations.business_mcp_auth.contracts import (
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    _SCOPE_RE,
    _exact_text,
    _split_https_url,
    validate_resource_policy,
)


OAuthChallengeError = Literal["invalid_token", "insufficient_scope"]

OPENAI_SUPPORTED_TOKEN_ENDPOINT_AUTH_METHODS = frozenset(
    {
        "none",
        "private_key_jwt",
        "client_secret_post",
        "client_secret_basic",
    }
)

_MISSING_TOKEN_DESCRIPTION = (
    "Authentication required: no valid access token was provided."
)
_INVALID_TOKEN_DESCRIPTION = (
    "Authentication required: the access token is invalid or no longer usable."
)
_MISSING_SCOPE_DESCRIPTION = (
    "Authentication required: the access token does not include the required scope."
)

_ALLOWED_CHALLENGE_DESCRIPTIONS: Mapping[str, frozenset[str]] = {
    "invalid_token": frozenset(
        {_MISSING_TOKEN_DESCRIPTION, _INVALID_TOKEN_DESCRIPTION}
    ),
    "insufficient_scope": frozenset({_MISSING_SCOPE_DESCRIPTION}),
}


@dataclasses.dataclass(frozen=True)
class ValidatedAuthorizationServerMetadata:
    """Closed, reduced authorization-server capability projection."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    authorization_response_iss_parameter_supported: bool
    client_id_metadata_document_supported: bool
    registration_endpoint: str | None
    token_endpoint_auth_methods_supported: tuple[str, ...]
    code_challenge_methods_supported: tuple[str, ...]
    scopes_supported: tuple[str, ...]


def _refuse() -> None:
    raise AuthError(AuthErrorCode.INVALID_POLICY)


def _origin(parts: object) -> tuple[object, object, object]:
    return (parts.scheme, parts.hostname, parts.port)  # type: ignore[attr-defined]


def _same_origin_https(value: object, *, issuer_origin: tuple[object, ...]) -> str:
    token, parts = _split_https_url(value)
    if _origin(parts) != issuer_origin:
        _refuse()
    return token


def _unique_strings(
    value: object,
    *,
    maximum_items: int,
    maximum_length: int = 128,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > maximum_items:
        _refuse()
    result: list[str] = []
    for item in value:
        result.append(_exact_text(item, maximum=maximum_length))
    if len(result) != len(set(result)):
        _refuse()
    return tuple(result)


def _normalized_scopes(
    value: Sequence[object],
    *,
    require_mastermind_prefix: bool,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _refuse()
    if not value:
        if allow_empty:
            return ()
        _refuse()
    if len(value) > 32:
        _refuse()
    result: list[str] = []
    for item in value:
        token = _exact_text(item, maximum=96)
        if _SCOPE_RE.fullmatch(token) is None:
            _refuse()
        if require_mastermind_prefix and not token.startswith("mastermind."):
            _refuse()
        result.append(token)
    if len(result) != len(set(result)):
        _refuse()
    return tuple(sorted(result))


def protected_resource_metadata(policy: ResourcePolicy) -> dict[str, object]:
    """Return the exact public RFC 9728 resource projection."""

    policy = validate_resource_policy(policy)
    return {
        "resource": policy.resource,
        "authorization_servers": list(policy.authorization_servers),
        "scopes_supported": list(policy.required_scopes),
    }


def validate_authorization_server_metadata(
    value: Mapping[str, object],
    policy: ResourcePolicy,
) -> ValidatedAuthorizationServerMetadata:
    """Validate provider capabilities without selecting an enrollment strategy."""

    policy = validate_resource_policy(policy)
    if not isinstance(value, Mapping):
        _refuse()
    if value.get("issuer") != policy.issuer:
        _refuse()

    _issuer, issuer_parts = _split_https_url(policy.issuer)
    issuer_origin = _origin(issuer_parts)
    authorization_endpoint = _same_origin_https(
        value.get("authorization_endpoint"), issuer_origin=issuer_origin
    )
    token_endpoint = _same_origin_https(
        value.get("token_endpoint"), issuer_origin=issuer_origin
    )
    jwks_uri = _same_origin_https(value.get("jwks_uri"), issuer_origin=issuer_origin)
    if jwks_uri != policy.jwks_uri:
        _refuse()

    response_iss = value.get("authorization_response_iss_parameter_supported")
    if type(response_iss) is not bool:
        _refuse()

    client_metadata_supported = value.get(
        "client_id_metadata_document_supported", False
    )
    if type(client_metadata_supported) is not bool:
        _refuse()

    registration_endpoint: str | None = None
    if "registration_endpoint" in value and value.get("registration_endpoint") is not None:
        registration_endpoint = _same_origin_https(
            value.get("registration_endpoint"), issuer_origin=issuer_origin
        )

    advertised_auth_methods = _unique_strings(
        value.get("token_endpoint_auth_methods_supported"), maximum_items=16
    )
    supported_auth_methods = tuple(
        sorted(
            set(advertised_auth_methods)
            & OPENAI_SUPPORTED_TOKEN_ENDPOINT_AUTH_METHODS
        )
    )
    if not supported_auth_methods:
        _refuse()

    code_methods = _unique_strings(
        value.get("code_challenge_methods_supported"), maximum_items=8
    )
    if "S256" not in code_methods:
        _refuse()
    code_methods = tuple(sorted(code_methods))

    advertised_scopes = _normalized_scopes(
        value.get("scopes_supported"),  # type: ignore[arg-type]
        require_mastermind_prefix=False,
        allow_empty=False,
    )
    if not set(policy.required_scopes).issubset(advertised_scopes):
        _refuse()

    return ValidatedAuthorizationServerMetadata(
        issuer=policy.issuer,
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        jwks_uri=jwks_uri,
        authorization_response_iss_parameter_supported=response_iss,
        client_id_metadata_document_supported=client_metadata_supported,
        registration_endpoint=registration_endpoint,
        token_endpoint_auth_methods_supported=supported_auth_methods,
        code_challenge_methods_supported=code_methods,
        scopes_supported=advertised_scopes,
    )


def www_authenticate(
    policy: ResourcePolicy,
    required_scopes: tuple[str, ...] = (),
    *,
    error: OAuthChallengeError | None = None,
    error_description: str | None = None,
) -> str:
    """Build one canonical HTTP or tool-level OAuth challenge."""

    policy = validate_resource_policy(policy)
    # A frozen dataclass instance can be manually constructed or replaced after
    # policy loading. Revalidate the exact value at the final quoted boundary so
    # no raw quote or parser-ambiguous URI can create an extra challenge field.
    resource_metadata_url, _parts = _split_https_url(
        policy.resource_metadata_url
    )
    scopes = _normalized_scopes(
        required_scopes,
        require_mastermind_prefix=True,
        allow_empty=True,
    )
    if not set(scopes).issubset(policy.required_scopes):
        _refuse()

    if (error is None) != (error_description is None):
        _refuse()
    if error is not None:
        if error not in _ALLOWED_CHALLENGE_DESCRIPTIONS:
            _refuse()
        if error_description not in _ALLOWED_CHALLENGE_DESCRIPTIONS[error]:
            _refuse()

    parts = [f'Bearer resource_metadata="{resource_metadata_url}"']
    if scopes:
        parts.append(f'scope="{" ".join(scopes)}"')
    if error is not None and error_description is not None:
        parts.append(f'error="{error}"')
        parts.append(f'error_description="{error_description}"')
    return ", ".join(parts)


def oauth_security_schemes(scopes: Sequence[object]) -> list[dict[str, object]]:
    """Return one closed per-tool OAuth security scheme."""

    normalized = _normalized_scopes(
        scopes,
        require_mastermind_prefix=True,
        allow_empty=False,
    )
    return [{"type": "oauth2", "scopes": list(normalized)}]


def _challenge_for_error(error: AuthError) -> tuple[str, str]:
    if not isinstance(error, AuthError):
        _refuse()
    if error.code is AuthErrorCode.AUTHORIZATION_MISSING:
        return "invalid_token", _MISSING_TOKEN_DESCRIPTION
    if error.code is AuthErrorCode.SCOPE_REFUSED:
        return "insufficient_scope", _MISSING_SCOPE_DESCRIPTION
    return "invalid_token", _INVALID_TOKEN_DESCRIPTION


def mcp_auth_error_result(
    policy: ResourcePolicy,
    error: AuthError,
    *,
    required_scopes: tuple[str, ...] = (),
) -> dict[str, object]:
    """Return the fixed ChatGPT linking result for one typed auth refusal."""

    oauth_error, description = _challenge_for_error(error)
    return {
        "isError": True,
        "content": [{"type": "text", "text": "Authentication required."}],
        "_meta": {
            "mcp/www_authenticate": [
                www_authenticate(
                    policy,
                    required_scopes,
                    error=oauth_error,  # type: ignore[arg-type]
                    error_description=description,
                )
            ]
        },
    }


__all__ = [
    "OPENAI_SUPPORTED_TOKEN_ENDPOINT_AUTH_METHODS",
    "OAuthChallengeError",
    "ValidatedAuthorizationServerMetadata",
    "mcp_auth_error_result",
    "oauth_security_schemes",
    "protected_resource_metadata",
    "validate_authorization_server_metadata",
    "www_authenticate",
]