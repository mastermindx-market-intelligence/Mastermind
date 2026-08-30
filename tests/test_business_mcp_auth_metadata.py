from __future__ import annotations

import dataclasses
import json

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.metadata import (
    OPENAI_SUPPORTED_TOKEN_ENDPOINT_AUTH_METHODS,
    ValidatedAuthorizationServerMetadata,
    mcp_auth_error_result,
    oauth_security_schemes,
    protected_resource_metadata,
    validate_authorization_server_metadata,
    www_authenticate,
)


def _policy():
    issuer = "https://identity.example.test/"
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-executive-v1",
            "resource": "https://mcp.example.test/mcp/executive/v1",
            "resource_metadata_url": (
                "https://mcp.example.test/.well-known/"
                "oauth-protected-resource/mcp/executive/v1"
            ),
            "issuer": issuer,
            "authorization_servers": [issuer],
            "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
            "required_scopes": [
                "mastermind.executive.intent.submit",
                "mastermind.executive.read",
            ],
            "allowed_subject_digests": [
                subject_digest(issuer=issuer, subject="chairman-opaque")
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _metadata() -> dict[str, object]:
    policy = _policy()
    return {
        "issuer": policy.issuer,
        "authorization_endpoint": "https://identity.example.test/authorize",
        "token_endpoint": "https://identity.example.test/oauth/token",
        "jwks_uri": policy.jwks_uri,
        "authorization_response_iss_parameter_supported": True,
        "client_id_metadata_document_supported": True,
        "registration_endpoint": "https://identity.example.test/register",
        "token_endpoint_auth_methods_supported": ["private_key_jwt", "none"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": [
            "mastermind.executive.read",
            "mastermind.executive.intent.submit",
            "offline_access",
        ],
        "provider_extension": "ignored",
    }


def test_protected_resource_metadata_is_exact_and_deterministic() -> None:
    policy = _policy()
    expected = {
        "resource": policy.resource,
        "authorization_servers": [policy.issuer],
        "scopes_supported": list(policy.required_scopes),
    }
    assert protected_resource_metadata(policy) == expected
    assert json.dumps(expected, sort_keys=True) == json.dumps(
        protected_resource_metadata(policy), sort_keys=True
    )


def test_authorization_server_metadata_is_reduced_without_strategy_selection() -> None:
    policy = _policy()
    result = validate_authorization_server_metadata(_metadata(), policy)
    assert result == ValidatedAuthorizationServerMetadata(
        issuer=policy.issuer,
        authorization_endpoint="https://identity.example.test/authorize",
        token_endpoint="https://identity.example.test/oauth/token",
        jwks_uri=policy.jwks_uri,
        authorization_response_iss_parameter_supported=True,
        client_id_metadata_document_supported=True,
        registration_endpoint="https://identity.example.test/register",
        token_endpoint_auth_methods_supported=("none", "private_key_jwt"),
        code_challenge_methods_supported=("S256",),
        scopes_supported=(
            "mastermind.executive.intent.submit",
            "mastermind.executive.read",
            "offline_access",
        ),
    )
    assert "provider_extension" not in dataclasses.asdict(result)


@pytest.mark.parametrize(
    ("cimd", "registration", "methods", "expected_registration", "expected_methods"),
    [
        (
            False,
            "https://identity.example.test/register",
            ["client_secret_basic"],
            "https://identity.example.test/register",
            ("client_secret_basic",),
        ),
        (False, None, ["client_secret_post"], None, ("client_secret_post",)),
    ],
)
def test_metadata_accepts_dcr_or_predefined_client_capabilities(
    cimd, registration, methods, expected_registration, expected_methods
) -> None:
    value = _metadata()
    value["client_id_metadata_document_supported"] = cimd
    if registration is None:
        value.pop("registration_endpoint")
    else:
        value["registration_endpoint"] = registration
    value["token_endpoint_auth_methods_supported"] = methods
    result = validate_authorization_server_metadata(value, _policy())
    assert result.registration_endpoint == expected_registration
    assert result.token_endpoint_auth_methods_supported == expected_methods


def test_supported_token_endpoint_methods_are_closed() -> None:
    assert OPENAI_SUPPORTED_TOKEN_ENDPOINT_AUTH_METHODS == frozenset(
        {"none", "private_key_jwt", "client_secret_post", "client_secret_basic"}
    )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.update(issuer="https://other.example.test/"),
        lambda value: value.update(
            authorization_endpoint="https://other.example.test/authorize"
        ),
        lambda value: value.update(
            token_endpoint="https://identity.example.test/token?tenant=x"
        ),
        lambda value: value.update(jwks_uri="https://other.example.test/jwks"),
        lambda value: value.update(
            authorization_response_iss_parameter_supported="true"
        ),
        lambda value: value.update(client_id_metadata_document_supported="true"),
        lambda value: value.update(code_challenge_methods_supported=["plain"]),
        lambda value: value.update(
            token_endpoint_auth_methods_supported=["tls_client_auth"]
        ),
        lambda value: value.update(scopes_supported=["mastermind.executive.read"]),
        lambda value: value.update(
            registration_endpoint="https://other.example.test/register"
        ),
        lambda value: value.update(
            token_endpoint_auth_methods_supported=["none", "none"]
        ),
        lambda value: value.update(code_challenge_methods_supported=["S256", "S256"]),
    ],
)
def test_metadata_refuses_unsafe_or_ambiguous_values(mutator) -> None:
    value = _metadata()
    mutator(value)
    with pytest.raises(AuthError) as caught:
        validate_authorization_server_metadata(value, _policy())
    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert caught.value.public_message == "authentication policy refused"


def test_http_and_scoped_challenges_are_canonical() -> None:
    policy = _policy()
    assert www_authenticate(policy) == (
        'Bearer resource_metadata="https://mcp.example.test/.well-known/'
        'oauth-protected-resource/mcp/executive/v1"'
    )
    assert www_authenticate(
        policy,
        ("mastermind.executive.read", "mastermind.executive.intent.submit"),
    ).endswith(
        'scope="mastermind.executive.intent.submit mastermind.executive.read"'
    )


@pytest.mark.parametrize(
    ("code", "error", "description"),
    [
        (
            AuthErrorCode.AUTHORIZATION_MISSING,
            "invalid_token",
            "Authentication required: no valid access token was provided.",
        ),
        (
            AuthErrorCode.TOKEN_SIGNATURE_REFUSED,
            "invalid_token",
            "Authentication required: the access token is invalid or no longer usable.",
        ),
        (
            AuthErrorCode.SCOPE_REFUSED,
            "insufficient_scope",
            "Authentication required: the access token does not include the required scope.",
        ),
    ],
)
def test_tool_linking_challenge_uses_fixed_oauth_fields(code, error, description) -> None:
    policy = _policy()
    result = mcp_auth_error_result(
        policy,
        AuthError(code),
        required_scopes=("mastermind.executive.intent.submit",)
        if code is AuthErrorCode.SCOPE_REFUSED
        else (),
    )
    challenge = result["_meta"]["mcp/www_authenticate"][0]
    rendered = json.dumps(result, sort_keys=True)
    assert result["content"] == [
        {"type": "text", "text": "Authentication required."}
    ]
    assert result["isError"] is True
    assert f'error="{error}"' in challenge
    assert f'error_description="{description}"' in challenge
    assert "chairman-opaque" not in rendered
    assert "token_signature_refused" not in rendered


@pytest.mark.parametrize(
    "kwargs",
    [
        {"error": "invalid_token"},
        {"error_description": "Authentication required."},
        {
            "error": "invalid_token",
            "error_description": "untrusted description",
        },
        {
            "error": "unsupported",
            "error_description": "Authentication required.",
        },
    ],
)
def test_challenge_refuses_unpaired_or_untrusted_error_fields(kwargs) -> None:
    with pytest.raises(AuthError) as caught:
        www_authenticate(_policy(), **kwargs)
    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_challenge_refuses_scope_outside_resource_policy() -> None:
    with pytest.raises(AuthError) as caught:
        www_authenticate(_policy(), ("mastermind.dialogue.write",))
    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_per_tool_security_scheme_is_closed_and_deterministic() -> None:
    assert oauth_security_schemes(
        ["mastermind.executive.read", "mastermind.executive.intent.submit"]
    ) == [
        {
            "type": "oauth2",
            "scopes": [
                "mastermind.executive.intent.submit",
                "mastermind.executive.read",
            ],
        }
    ]


@pytest.mark.parametrize(
    "scopes",
    [
        [],
        ["read"],
        ["mastermind.executive.read", "mastermind.executive.read"],
        ["mastermind.executive.read\nwrite"],
        [42],
    ],
)
def test_per_tool_security_scheme_refuses_invalid_scopes(scopes) -> None:
    with pytest.raises(AuthError) as caught:
        oauth_security_schemes(scopes)
    assert caught.value.code is AuthErrorCode.INVALID_POLICY
