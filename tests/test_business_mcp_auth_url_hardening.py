from __future__ import annotations

import dataclasses

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.metadata import www_authenticate


def _wire() -> dict[str, object]:
    issuer = "https://identity.example.test/"
    return {
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": "mastermind-steward-v1",
        "resource": "https://mcp.example.test/mcp/steward/v1",
        "resource_metadata_url": (
            "https://mcp.example.test/.well-known/"
            "oauth-protected-resource/mcp/steward/v1"
        ),
        "issuer": issuer,
        "authorization_servers": [issuer],
        "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
        "required_scopes": ["mastermind.steward.read"],
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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("resource", 'https://mcp.example.test/mcp/steward/v1"'),
        (
            "resource_metadata_url",
            'https://mcp.example.test/meta",error="invalid_token',
        ),
        ("jwks_uri", "https://identity.example.test/.well-known/jwks`"),
        ("resource", "https://mcp.example.test/mcp/<steward>/v1"),
        ("resource", "https://mcp.example.test/mcp/{steward}/v1"),
        ("resource", "https://mcp.example.test/mcp/[steward]/v1"),
        ("resource", "https://mcp.example.test/mcp/steward/%ZZ"),
        ("resource", "https://mcp.example.test/mcp/steward/v1?"),
        ("resource", "https://mcp.example.test/mcp/steward/v1#"),
        ("resource", "https://%65xample.test/mcp/steward/v1"),
    ],
)
def test_policy_refuses_raw_illegal_or_ambiguous_uri_spelling(
    field: str,
    value: str,
) -> None:
    wire = _wire()
    wire[field] = value

    with pytest.raises(AuthError) as caught:
        load_resource_policy(wire)

    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert caught.value.public_message == "authentication policy refused"
    assert value not in str(caught.value)


def test_policy_refuses_quote_in_exact_issuer_spelling() -> None:
    issuer = 'https://identity.example.test/"'
    wire = _wire()
    wire["issuer"] = issuer
    wire["authorization_servers"] = [issuer]
    # The digest remains syntactically valid; issuer parsing must reject first.
    wire["allowed_subject_digests"] = ["0" * 64]

    with pytest.raises(AuthError) as caught:
        load_resource_policy(wire)

    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert issuer not in str(caught.value)


def test_www_authenticate_revalidates_resource_metadata_before_quoting() -> None:
    policy = load_resource_policy(_wire())
    bypassed = dataclasses.replace(
        policy,
        resource_metadata_url=(
            'https://mcp.example.test/meta", '
            'error="invalid_token", error_description="injected'
        ),
    )

    with pytest.raises(AuthError) as caught:
        www_authenticate(bypassed)

    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert "injected" not in str(caught.value)


@pytest.mark.parametrize(
    "url",
    [
        "https://mcp.example.test/path%0",
        "https://mcp.example.test/path%GG",
        "https://mcp.example.test/path%",
    ],
)
def test_policy_refuses_malformed_percent_encoding(url: str) -> None:
    wire = _wire()
    wire["resource"] = url

    with pytest.raises(AuthError) as caught:
        load_resource_policy(wire)

    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_legal_reserved_and_percent_encoded_path_spelling_remains_exact() -> None:
    wire = _wire()
    wire["resource"] = (
        "https://mcp.example.test/mcp/steward/"
        "v1;mode=read+safe@tenant%2Falpha"
    )

    policy = load_resource_policy(wire)

    assert policy.resource == wire["resource"]


def test_explicit_default_https_port_remains_legal_and_exact() -> None:
    wire = _wire()
    wire["resource"] = "https://mcp.example.test:443/mcp/steward/v1"

    policy = load_resource_policy(wire)

    assert policy.resource == wire["resource"]


def test_ipv6_authority_brackets_remain_legal_but_path_brackets_do_not() -> None:
    issuer = "https://[2001:db8::1]/"
    wire = _wire()
    wire["issuer"] = issuer
    wire["authorization_servers"] = [issuer]
    wire["jwks_uri"] = "https://[2001:db8::1]/.well-known/jwks.json"
    wire["allowed_subject_digests"] = [
        subject_digest(issuer=issuer, subject="chairman-opaque")
    ]

    policy = load_resource_policy(wire)

    assert policy.issuer == issuer
    assert policy.jwks_uri == wire["jwks_uri"]
