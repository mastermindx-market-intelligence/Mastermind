from __future__ import annotations

import dataclasses
import hashlib

import pytest

from integrations.business_mcp_auth.claims import (
    validate_jwt_header,
    validate_verified_claims,
)
from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    VerifiedPrincipal,
    load_resource_policy,
    subject_digest,
)


NOW = 1_788_000_100
GOOD_HEADER = {"alg": "RS256", "kid": "key-2026-01", "typ": "at+jwt"}


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


def _claims(**overrides):
    policy = _policy()
    value = {
        "iss": policy.issuer,
        "sub": "chairman-opaque",
        "aud": policy.resource,
        "iat": 1_788_000_000,
        "nbf": 1_788_000_000,
        "exp": 1_788_000_600,
        "scope": (
            "mastermind.executive.read "
            "mastermind.executive.intent.submit"
        ),
        "jti": "token-id-opaque",
        "client_id": "chatgpt-business-client",
        "email": "must-not-be-projected@example.test",
        "name": "Must Not Be Projected",
        "roles": ["admin"],
    }
    value.update(overrides)
    return value


def test_valid_header_returns_exact_kid() -> None:
    assert validate_jwt_header(GOOD_HEADER, _policy()) == "key-2026-01"


@pytest.mark.parametrize(
    "header",
    [
        {"alg": "none", "kid": "key-2026-01", "typ": "at+jwt"},
        {"alg": "HS256", "kid": "key-2026-01", "typ": "at+jwt"},
        {"alg": "RS256", "typ": "at+jwt"},
        {"alg": "RS256", "kid": "", "typ": "at+jwt"},
        {"alg": "RS256", "kid": " key-2026-01", "typ": "at+jwt"},
        {"alg": "RS256", "kid": "key/2026", "typ": "at+jwt"},
        {"alg": "RS256", "kid": "key-2026-01", "typ": "other"},
        {"alg": "RS256", "kid": "key-2026-01", "crit": ["custom"]},
        {
            "alg": "RS256",
            "kid": "key-2026-01",
            "jku": "https://attacker.test/jwks",
        },
        {
            "alg": "RS256",
            "kid": "key-2026-01",
            "x5u": "https://attacker.test/cert",
        },
        {"alg": "RS256", "kid": "key-2026-01", "x5c": ["cert"]},
        {"alg": "RS256", "kid": "key-2026-01", "jwk": {"kty": "RSA"}},
        "not-a-mapping",
        None,
    ],
)
def test_unsafe_or_ambiguous_header_is_refused(header) -> None:
    with pytest.raises(AuthError) as caught:
        validate_jwt_header(header, _policy())
    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert caught.value.public_message == "authentication refused"
    assert "attacker.test" not in str(caught.value)


@pytest.mark.parametrize("typ", [None, "JWT", "at+jwt"])
def test_header_accepts_only_frozen_typ_values(typ) -> None:
    header = dict(GOOD_HEADER)
    if typ is None:
        header.pop("typ")
    else:
        header["typ"] = typ
    assert validate_jwt_header(header, _policy()) == "key-2026-01"


def test_valid_claims_return_only_pseudonymous_principal() -> None:
    policy = _policy()
    result = validate_verified_claims(_claims(), policy, now=NOW)

    expected_subject = subject_digest(
        issuer=policy.issuer, subject="chairman-opaque"
    )
    expected_issuer = hashlib.sha256(policy.issuer.encode("utf-8")).hexdigest()
    expected_jti = hashlib.sha256(b"token-id-opaque").hexdigest()
    expected_client = hashlib.sha256(
        (
            policy.issuer
            + "\nclient\n"
            + "chatgpt-business-client"
        ).encode("utf-8")
    ).hexdigest()

    assert result == VerifiedPrincipal(
        policy_id=policy.policy_id,
        issuer=policy.issuer,
        issuer_digest=expected_issuer,
        resource=policy.resource,
        subject_digest=expected_subject,
        client_ref=expected_client,
        scopes=(
            "mastermind.executive.intent.submit",
            "mastermind.executive.read",
        ),
        issued_at=1_788_000_000,
        expires_at=1_788_000_600,
        jti_digest=expected_jti,
    )
    assert dataclasses.is_dataclass(result)
    projected = dataclasses.asdict(result)
    rendered = repr(projected)
    for forbidden in (
        "chairman-opaque",
        "chatgpt-business-client",
        "token-id-opaque",
        "must-not-be-projected@example.test",
        "Must Not Be Projected",
        "admin",
    ):
        assert forbidden not in rendered


def test_scope_order_is_normalized_not_rejected() -> None:
    result = validate_verified_claims(
        _claims(
            scope=(
                "mastermind.executive.read "
                "mastermind.executive.intent.submit"
            )
        ),
        _policy(),
        now=NOW,
    )
    assert result.scopes == (
        "mastermind.executive.intent.submit",
        "mastermind.executive.read",
    )


@pytest.mark.parametrize(
    "scope",
    [
        " mastermind.executive.read mastermind.executive.intent.submit",
        "mastermind.executive.read mastermind.executive.intent.submit ",
        "mastermind.executive.read  mastermind.executive.intent.submit",
        "mastermind.executive.read mastermind.executive.read",
        "mastermind.executive.read",
        ["mastermind.executive.read"],
        "mastermind.executive.read\nmastermind.executive.intent.submit",
        "x" * 4097,
    ],
)
def test_noncanonical_duplicate_or_insufficient_scope_is_refused(scope) -> None:
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(_claims(scope=scope), _policy(), now=NOW)
    assert caught.value.code is AuthErrorCode.SCOPE_REFUSED
    assert caught.value.public_message == "authentication refused"


@pytest.mark.parametrize("missing", ["iss", "sub", "aud", "iat", "exp", "scope"])
def test_required_claim_is_mandatory(missing: str) -> None:
    claims = _claims()
    claims.pop(missing)
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(claims, _policy(), now=NOW)
    assert caught.value.code is AuthErrorCode.TOKEN_CLAIMS_REFUSED


def test_wrong_issuer_is_refused_without_echo() -> None:
    wrong = "https://attacker.example.test/"
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(_claims(iss=wrong), _policy(), now=NOW)
    assert caught.value.code is AuthErrorCode.ISSUER_REFUSED
    assert wrong not in str(caught.value)


@pytest.mark.parametrize(
    "audience",
    [
        None,
        "https://mcp.example.test/mcp/other/v1",
        "*",
        ["https://mcp.example.test/mcp/executive/v1"],
        [
            "https://mcp.example.test/mcp/executive/v1",
            "https://mcp.example.test/mcp/other/v1",
        ],
    ],
)
def test_audience_must_be_one_exact_resource(audience) -> None:
    claims = _claims()
    if audience is None:
        claims.pop("aud")
    else:
        claims["aud"] = audience
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(claims, _policy(), now=NOW)
    expected = (
        AuthErrorCode.TOKEN_CLAIMS_REFUSED
        if audience is None
        else AuthErrorCode.RESOURCE_REFUSED
    )
    assert caught.value.code is expected


def test_expired_beyond_inclusive_skew_is_refused() -> None:
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(
            _claims(iat=NOW - 100, nbf=NOW - 100, exp=NOW - 31),
            _policy(),
            now=NOW,
        )
    assert caught.value.code is AuthErrorCode.TOKEN_EXPIRED


def test_expiry_at_skew_boundary_is_accepted() -> None:
    result = validate_verified_claims(
        _claims(iat=NOW - 100, nbf=NOW - 100, exp=NOW - 30),
        _policy(),
        now=NOW,
    )
    assert result.expires_at == NOW - 30


@pytest.mark.parametrize(
    "overrides",
    [
        {"iat": NOW + 31, "nbf": NOW},
        {"iat": NOW, "nbf": NOW + 31},
    ],
)
def test_future_iat_or_nbf_beyond_skew_is_refused(overrides) -> None:
    claims = _claims(exp=NOW + 600)
    claims.update(overrides)
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(claims, _policy(), now=NOW)
    assert caught.value.code is AuthErrorCode.TOKEN_NOT_YET_VALID


@pytest.mark.parametrize(
    "overrides",
    [
        {"iat": 1_788_000_600, "exp": 1_788_000_600},
        {"iat": 1_788_000_600, "exp": 1_788_000_599},
        {"iat": 1_788_000_000, "exp": 1_788_000_901},
    ],
)
def test_invalid_or_excessive_token_lifetime_is_refused(overrides) -> None:
    claims = _claims(nbf=1_788_000_000)
    claims.update(overrides)
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(claims, _policy(), now=NOW)
    assert caught.value.code is AuthErrorCode.TOKEN_LIFETIME_REFUSED


@pytest.mark.parametrize("field", ["iat", "nbf", "exp"])
def test_boolean_timestamp_is_refused(field: str) -> None:
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(_claims(**{field: True}), _policy(), now=NOW)
    assert caught.value.code is AuthErrorCode.TOKEN_CLAIMS_REFUSED


def test_boolean_now_is_refused() -> None:
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(_claims(), _policy(), now=True)
    assert caught.value.code is AuthErrorCode.TOKEN_CLAIMS_REFUSED


def test_unauthorized_subject_is_refused_without_echo() -> None:
    raw_subject = "other-user-opaque"
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(
            _claims(sub=raw_subject),
            _policy(),
            now=NOW,
        )
    assert caught.value.code is AuthErrorCode.SUBJECT_REFUSED
    assert raw_subject not in str(caught.value)


def test_unicode_subject_is_compared_by_exact_digest() -> None:
    issuer = "https://identity.example.test/"
    subject = "主席-é-opaque"
    value = {
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
            subject_digest(issuer=issuer, subject=subject)
        ],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 300,
        "unknown_kid_refresh_cooldown_seconds": 30,
        "fetch_failure_backoff_seconds": 5,
    }
    policy = load_resource_policy(value)
    claims = _claims(
        iss=issuer,
        sub=subject,
        aud=policy.resource,
        scope="mastermind.steward.read",
    )
    result = validate_verified_claims(claims, policy, now=NOW)
    assert result.subject_digest == subject_digest(issuer=issuer, subject=subject)


@pytest.mark.parametrize(
    "jti",
    ["", " token-id", "token-id ", "bad\nidentifier", 42, "x" * 1025],
)
def test_malformed_jti_is_refused(jti) -> None:
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(_claims(jti=jti), _policy(), now=NOW)
    assert caught.value.code is AuthErrorCode.TOKEN_CLAIMS_REFUSED


def test_absent_jti_is_explicit_null() -> None:
    claims = _claims()
    claims.pop("jti")
    result = validate_verified_claims(claims, _policy(), now=NOW)
    assert result.jti_digest is None


@pytest.mark.parametrize("claim_name", ["client_id", "azp"])
def test_single_client_claim_is_pseudonymized(claim_name: str) -> None:
    claims = _claims()
    claims.pop("client_id")
    claims[claim_name] = "chatgpt-client"
    result = validate_verified_claims(claims, _policy(), now=NOW)
    assert result.client_ref != "chatgpt-client"
    assert len(result.client_ref) == 64


def test_absent_client_claim_has_explicit_nonidentity_marker() -> None:
    claims = _claims()
    claims.pop("client_id")
    result = validate_verified_claims(claims, _policy(), now=NOW)
    assert result.client_ref == "oauth-client-unavailable"


def test_matching_client_id_and_azp_are_accepted_once() -> None:
    result = validate_verified_claims(
        _claims(
            client_id="chatgpt-client",
            azp="chatgpt-client",
        ),
        _policy(),
        now=NOW,
    )
    assert len(result.client_ref) == 64


def test_conflicting_client_id_and_azp_are_refused() -> None:
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(
            _claims(client_id="one", azp="two"),
            _policy(),
            now=NOW,
        )
    assert caught.value.code is AuthErrorCode.TOKEN_CLAIMS_REFUSED


@pytest.mark.parametrize(
    "value",
    ["", " client", "client ", "bad\nclient", 42, "x" * 1025],
)
def test_malformed_client_claim_is_refused(value) -> None:
    with pytest.raises(AuthError) as caught:
        validate_verified_claims(
            _claims(client_id=value),
            _policy(),
            now=NOW,
        )
    assert caught.value.code is AuthErrorCode.TOKEN_CLAIMS_REFUSED
