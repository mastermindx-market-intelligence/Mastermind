from __future__ import annotations

import dataclasses
import hashlib

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AUTH_POLICY_SCHEMA,
    AuthAuditEvent,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    VerifiedPrincipal,
    load_resource_policy,
    subject_digest,
)


def _policy() -> dict[str, object]:
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


def test_subject_digest_is_exact_issuer_subject_sha256() -> None:
    issuer = "https://identity.example.test/"
    subject = "chairman-opaque"
    expected = hashlib.sha256(f"{issuer}\n{subject}".encode("utf-8")).hexdigest()
    assert subject_digest(issuer=issuer, subject=subject) == expected


@pytest.mark.parametrize(
    ("issuer", "subject"),
    [
        ("", "subject"),
        (" https://identity.example.test/", "subject"),
        ("https://identity.example.test/ ", "subject"),
        ("https://identity.example.test/", ""),
        ("https://identity.example.test/", " subject"),
        ("https://identity.example.test/", "subject "),
        ("https://identity.example.test/", "bad\nsubject"),
        ("https://identity.example.test/", "x" * 1025),
    ],
)
def test_subject_digest_refuses_ambiguous_or_unsafe_text(
    issuer: str, subject: str
) -> None:
    with pytest.raises(AuthError) as caught:
        subject_digest(issuer=issuer, subject=subject)
    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert caught.value.public_message == "authentication policy refused"
    if issuer:
        assert issuer not in str(caught.value)
    if subject:
        assert subject not in str(caught.value)


def test_exact_policy_wire_is_accepted_and_normalized() -> None:
    policy = load_resource_policy(_policy())
    assert policy.schema == AUTH_POLICY_SCHEMA
    assert policy.policy_id == "mastermind-steward-v1"
    assert policy.allowed_algorithms == ("RS256",)
    assert policy.required_scopes == ("mastermind.steward.read",)
    assert policy.authorization_servers == (policy.issuer,)
    assert policy.unknown_kid_refresh_cooldown_seconds == 30
    assert policy.fetch_failure_backoff_seconds == 5
    assert dataclasses.is_dataclass(policy)
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.policy_id = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.update(extra="x"),
        lambda value: value.update(schema="unsupported"),
        lambda value: value.update(policy_id="Mastermind Steward"),
        lambda value: value.update(
            resource="http://mcp.example.test/mcp/steward/v1"
        ),
        lambda value: value.update(
            resource="https://user@mcp.example.test/mcp/steward/v1"
        ),
        lambda value: value.update(
            resource="https://mcp.example.test:8443/mcp/steward/v1"
        ),
        lambda value: value.update(
            resource="https://mcp.example.test/mcp/steward/v1?tenant=x"
        ),
        lambda value: value.update(
            resource_metadata_url="https://mcp.example.test/meta#fragment"
        ),
        lambda value: value.update(
            authorization_servers=["https://other.example.test/"]
        ),
        lambda value: value.update(
            jwks_uri="https://keys.other.example.test/jwks.json"
        ),
        lambda value: value.update(allowed_algorithms=["HS256"]),
        lambda value: value.update(allowed_algorithms=["RS256", "HS256"]),
        lambda value: value.update(required_scopes=[]),
        lambda value: value.update(
            required_scopes=[
                "mastermind.steward.read",
                "mastermind.steward.read",
            ]
        ),
        lambda value: value.update(
            required_scopes=[
                "mastermind.steward.write",
                "mastermind.steward.read",
            ]
        ),
        lambda value: value.update(allowed_subject_digests=[]),
        lambda value: value.update(clock_skew_seconds=True),
        lambda value: value.update(clock_skew_seconds=121),
        lambda value: value.update(max_token_lifetime_seconds=59),
        lambda value: value.update(max_token_lifetime_seconds=3601),
        lambda value: value.update(jwks_cache_ttl_seconds=59),
        lambda value: value.update(jwks_cache_ttl_seconds=3601),
        lambda value: value.update(unknown_kid_refresh_cooldown_seconds=0),
        lambda value: value.update(unknown_kid_refresh_cooldown_seconds=301),
        lambda value: value.update(fetch_failure_backoff_seconds=0),
        lambda value: value.update(fetch_failure_backoff_seconds=301),
    ],
)
def test_policy_refuses_unknown_or_unsafe_values(mutator) -> None:
    value = _policy()
    mutator(value)
    with pytest.raises(AuthError) as caught:
        load_resource_policy(value)
    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert caught.value.public_message == "authentication policy refused"


def test_auth_error_vocabulary_is_closed_and_public_messages_are_opaque() -> None:
    assert {code.value for code in AuthErrorCode} == {
        "invalid_policy",
        "authorization_missing",
        "authorization_malformed",
        "token_too_large",
        "token_header_refused",
        "token_signature_refused",
        "token_claims_refused",
        "token_expired",
        "token_not_yet_valid",
        "token_lifetime_refused",
        "issuer_refused",
        "resource_refused",
        "scope_refused",
        "subject_refused",
        "jwks_unavailable",
        "jwks_refused",
        "key_not_found",
        "internal_error",
    }
    for code in AuthErrorCode:
        error = AuthError(code)
        assert error.code is code
        assert error.public_message in {
            "authentication policy refused",
            "authentication required",
            "authentication temporarily unavailable",
            "authentication refused",
        }
        assert code.value not in error.public_message


def test_public_contract_dataclasses_contain_only_pseudonymous_identity() -> None:
    principal = VerifiedPrincipal(
        policy_id="mastermind-steward-v1",
        issuer="https://identity.example.test/",
        issuer_digest="1" * 64,
        resource="https://mcp.example.test/mcp/steward/v1",
        subject_digest="2" * 64,
        client_ref="oauth-client-unavailable",
        scopes=("mastermind.steward.read",),
        issued_at=1_788_000_000,
        expires_at=1_788_000_600,
        jti_digest=None,
    )
    event = AuthAuditEvent(
        schema=AUTH_AUDIT_SCHEMA,
        policy_id="mastermind-steward-v1",
        code="accepted",
        accepted=True,
    )
    assert "subject" not in dataclasses.asdict(principal)
    assert "token" not in dataclasses.asdict(principal)
    assert "email" not in dataclasses.asdict(principal)
    assert event.schema == AUTH_AUDIT_SCHEMA


def test_load_resource_policy_does_not_mutate_input() -> None:
    value = _policy()
    before = repr(value)
    policy = load_resource_policy(value)
    assert repr(value) == before
    assert isinstance(policy, ResourcePolicy)


@pytest.mark.parametrize(
    "issuer",
    (
        "https://identity.example.test",
        "https://identity.example.test/",
    ),
)
def test_policy_accepts_exact_root_issuer_spelling(issuer: str) -> None:
    value = _policy()
    value["issuer"] = issuer
    value["authorization_servers"] = [issuer]
    value["allowed_subject_digests"] = [
        subject_digest(issuer=issuer, subject="chairman-opaque")
    ]

    policy = load_resource_policy(value)

    assert policy.issuer == issuer
    assert policy.authorization_servers == (issuer,)


def test_subject_digest_accepts_unicode_without_normalization() -> None:
    issuer = "https://identity.example.test/"
    composed = "主席-é-opaque"
    decomposed = "主席-e\u0301-opaque"

    expected_composed = hashlib.sha256(
        f"{issuer}\n{composed}".encode("utf-8")
    ).hexdigest()
    expected_decomposed = hashlib.sha256(
        f"{issuer}\n{decomposed}".encode("utf-8")
    ).hexdigest()

    assert subject_digest(issuer=issuer, subject=composed) == expected_composed
    assert subject_digest(issuer=issuer, subject=decomposed) == expected_decomposed
    assert expected_composed != expected_decomposed


@pytest.mark.parametrize(
    "issuer",
    (
        "identity.example.test",
        "http://identity.example.test/",
        "https://identity.example.test/?tenant=x",
        "https://identity.example.test/#fragment",
    ),
)
def test_subject_digest_requires_canonical_https_issuer(issuer: str) -> None:
    with pytest.raises(AuthError) as caught:
        subject_digest(issuer=issuer, subject="chairman-opaque")
    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert caught.value.public_message == "authentication policy refused"
    assert issuer not in str(caught.value)


@pytest.mark.parametrize(
    "resource",
    (
        "https://mcp .example.test/mcp/steward/v1",
        "https://mcp.example.test/mcp\\steward/v1",
        "https://mcp.example.test/mcp/steward v1",
    ),
)
def test_policy_refuses_parser_differential_https_urls(resource: str) -> None:
    value = _policy()
    value["resource"] = resource

    with pytest.raises(AuthError) as caught:
        load_resource_policy(value)
    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert caught.value.public_message == "authentication policy refused"
    assert resource not in str(caught.value)


def test_subject_digest_refuses_non_utf8_surrogate_data() -> None:
    with pytest.raises(AuthError) as caught:
        subject_digest(
            issuer="https://identity.example.test/",
            subject="bad-\ud800-subject",
        )
    assert caught.value.code is AuthErrorCode.INVALID_POLICY
    assert caught.value.public_message == "authentication policy refused"
