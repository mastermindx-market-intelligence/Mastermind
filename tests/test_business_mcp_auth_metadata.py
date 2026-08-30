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


def _authorization_server_metadata() -> dict[str, object]:
    policy = _policy()
    return {
        "issuer": policy.issuer,
        "authorization_endpoint": "https://identity.example.test/authorize",
        "token_endpoint": "https://identity.example.test/oauth/token",
        "jwks_uri": policy.jwks_uri,
        "authorization_response_iss_parameter_supported": True,
        "client_id_metadata_document_supported": True,
        "registration_endpoint": "https://identity.example.test/register",
        "token_endpoint_auth_methods_supported": [
            "private_key_jwt",
            "none",
        ],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": [
            "mastermind.executive.read",
            "mastermind.executive.intent.submit",
            "offline_access",
        ],
        "unrelated_provider_field": "ignored",
    }


def test_protected_resource_metadata_is_exact_and_deterministic() -> None:
    policy = _policy()
    expected = {
        "resource": policy.resource,
        "authorization_servers": [policy.issuer],
        "scopes_supported": list(policy.required_scopes),
    }
    assert protected_resource_metadata(policy) == expected
    assert protected_resource_metadata(policy) == expected
    assert json.dumps(expected, sort_keys=True, separators=(",", ":")) == json.dumps(
        protected_resource_metadata(policy),
        sort_keys=True,
        separators=(",", ":"),
    )


def test_authorization_server_metadata_is_validated_and_reduced() -> None:
    policy = _policy()
    result = validate_authorization_server_metadata(
        _authorization_server_metadata(), policy
    )
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
    assert dataclasses.is_dataclass(result)
    assert "unrelated_provider_field" not in dataclasses.asdict(result)


def test_metadata_accepts_dcr_client_secret_basic_without_cimd() -> None:
    policy = _policy()
    value = _authorization_server_metadata()
    value["client_id_metadata_document_supported"] = False
    value["registration_endpoint"] = "https://identity.example.test/register"
    value["token_endpoint_auth_methods_supported"] = ["client_secret_basic"]

    result = validate_authorization_server_metadata(value, policy)

    assert result.client_id_metadata_document_supported is False
    assert result.registration_endpoint == "https://identity.example.test/register"
    assert result.token_endpoint_auth_methods_supported == ("client_secret_basic",)


def test_metadata_accepts_predefined_client_without_cimd_or_dcr() -> None:
    policy = _policy()
    value = _authorization_server_metadata()
    value.pop("registration_endpoint")
    value["client_id_metadata_document_supported"] = False
    value["token_endpoint_auth_methods_supported"] = ["client_secret_post"]

    result = validate_authorization_server_metadata(value, policy)

    assert result.registration_endpoint is None
    assert result.token_endpoint_auth_methods_supported == ("client_secret_post",)


def test_supported_token_endpoint_auth_methods_are_closed() -> None:
    assert OPENAI_SUPPORTED_TOKEN_ENDPOINT_AUTH_METHODS == frozenset(
        {
            "none",
            "private_key_jwt",
            "client_secret_post",
            "client_secret_basic",
        }
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
        lambda value: value.update(token_endpoint_auth_methods_supported=["tls_client_auth"]),
        lambda value: value.update(
            scopes_supported=["mastermind.executive.read"]
        ),
        lambda value: value.update(
            registration_endpoint="https://other.example.test/register"
        ),
        lambda value: value.update(
            token_endpoint_auth_methods_supported=[
                "none",
                "none",
            ]
        ),
        lambda value: value.update(
            code_challenge_methods_supported=["S256", "S256"]
        ),
    ],
)
def test_authorization_server_metadata_refuses_unsafe_or_ambiguous_values(
    mutator,
) -> None:
    policy = _policy()
    value = _authorization_server_metadata()
    mutator(value)

    with pytest.raises(AuthError) as caught:
        validate_authorization_server_metadata(value, policy)

    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert caught.value.public_message == "authentication policy refused"
    assert "identity.example.test" not in str(caught.value)


def test_http_www_authenticate_uses_exact_resource_metadata_only() -> None:
    policy = _policy()
    assert www_authenticate(policy) == (
        'Bearer resource_metadata="https://mcp.example.test/.well-known/'
        'oauth-protected-resource/mcp/executive/v1"'
    )


def test_www_authenticate_adds_only_validated_sorted_scope() -> None:
    policy = _policy()
    assert www_authenticate(
        policy,
        (
            "mastermind.executive.read",
            "mastermind.executive.intent.submit",
        ),
    ) == (
        'Bearer resource_metadata="https://mcp.example.test/.well-known/'
        'oauth-protected-resource/mcp/executive/v1", '
        'scope="mastermind.executive.intent.submit mastermind.executive.read"'
    )


def test_tool_level_challenge_contains_required_oauth_error_fields() -> None:
    policy = _policy()
    result = mcp_auth_error_result(
        policy,
        AuthError(AuthErrorCode.SCOPE_REFUSED),
        required_scopes=("mastermind.executive.intent.submit",),
    )
    challenge = result["_meta"]["mcp/www_authenticate"][0]
    assert result["isError"] is True
    assert result["content"] == [
        {"type": "text", "text": "Authentication required."}
    ]
    assert 'error="insufficient_scope"' in challenge
    assert (
        'error_description="Authentication required: the access token does not '
        'include the required scope."' in challenge
    )
    assert 'scope="mastermind.executive.intent.submit"' in challenge


def test_missing_token_challenge_uses_fixed_invalid_token_description() -> None:
    policy = _policy()
    result = mcp_auth_error_result(
        policy,
        AuthError(AuthErrorCode.AUTHORIZATION_MISSING),
    )
    challenge = result["_meta"]["mcp/www_authenticate"][0]
    assert 'error="invalid_token"' in challenge
    assert (
        'error_description="Authentication required: no valid access token was '
        'provided."' in challenge
    )


def test_invalid_token_challenge_never_echoes_dependency_or_identity_text() -> None:
    policy = _policy()
    result = mcp_auth_error_result(
        policy,
        AuthError(AuthErrorCode.TOKEN_SIGNATURE_REFUSED),
    )
    rendered = json.dumps(result, sort_keys=True)
    assert 'error="invalid_token"' in rendered
    assert "chairman-opaque" not in rendered
    assert "identity.example.test" not in rendered
    assert "token_signature_refused" not in rendered


@pytest.mark.parametrize(
    "kwargs",
    [
        {"error": "invalid_token"},
        {"error_description": "Authentication required."},
        {
            "error": "invalid_token",
            "error_description": 'bad"\r\nInjected: yes',
        },
        {
            "error": "other",
            "error_description": "Authentication required.",
        },
        {
            "error": "invalid_token",
            "error_description": "attacker-selected description",
        },
    ],
)
def test_challenge_refuses_unpaired_or_untrusted_error_description(kwargs) -> None:
    with pytest.raises(AuthError) as caught:
        www_authenticate(_policy(), **kwargs)
    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_challenge_refuses_scope_outside_exact_resource_policy() -> None:
    with pytest.raises(AuthError) as caught:
        www_authenticate(_policy(), ("mastermind.dialogue.write",))
    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_per_tool_security_scheme_is_closed_and_deterministic() -> None:
    assert oauth_security_schemes(
        [
            "mastermind.executive.read",
            "mastermind.executive.intent.submit",
        ]
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
