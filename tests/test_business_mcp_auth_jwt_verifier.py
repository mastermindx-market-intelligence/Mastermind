from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache
from integrations.business_mcp_auth.jwt_verifier import (
    MAX_TOKEN_BYTES,
    JwtAuthenticator,
)


NOW = 1_788_000_100
SUBJECT = "chairman-opaque"
KID = "kid-a"


def _run(coroutine):
    return asyncio.run(coroutine)


def _base64url_uint(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode()


def _base64url_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _rsa_jwk(
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str = KID,
) -> dict[str, object]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kid": kid,
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": _base64url_uint(numbers.n),
        "e": _base64url_uint(numbers.e),
    }


def _jwks(*keys: Mapping[str, object]) -> bytes:
    return json.dumps({"keys": list(keys)}, separators=(",", ":")).encode()


def _policy() -> ResourcePolicy:
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
                subject_digest(issuer=issuer, subject=SUBJECT)
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _claims(policy: ResourcePolicy, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "iss": policy.issuer,
        "sub": SUBJECT,
        "aud": policy.resource,
        "iat": 1_788_000_000,
        "nbf": 1_788_000_000,
        "exp": 1_788_000_600,
        "scope": (
            "mastermind.executive.read "
            "mastermind.executive.intent.submit"
        ),
        "jti": "opaque-token-id",
        "client_id": "chatgpt-business-client",
    }
    value.update(overrides)
    return value


def _token(
    private_key: object,
    policy: ResourcePolicy,
    *,
    algorithm: str = "RS256",
    headers: Mapping[str, object] | None = None,
    **claim_overrides: object,
) -> str:
    complete_headers: dict[str, object] = {"kid": KID, "typ": "at+jwt"}
    if headers:
        complete_headers.update(headers)
    return jwt.encode(
        _claims(policy, **claim_overrides),
        private_key,
        algorithm=algorithm,
        headers=complete_headers,
    )


class _Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def monotonic(self) -> float:
        return self.value


class _Fetcher:
    def __init__(self, *responses: bytes | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    async def fetch(self, *, url: str, timeout_seconds: float, max_bytes: int) -> bytes:
        del timeout_seconds, max_bytes
        self.calls.append(url)
        await asyncio.sleep(0)
        if not self.responses:
            raise RuntimeError("unexpected fetch")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _authenticator(
    policy: ResourcePolicy,
    *jwks_payloads: bytes,
) -> tuple[JwtAuthenticator, _Fetcher, BoundedJwksCache]:
    fetcher = _Fetcher(*jwks_payloads)
    cache = BoundedJwksCache(
        policy=policy,
        fetcher=fetcher,
        monotonic=_Clock().monotonic,
    )
    return (
        JwtAuthenticator(policy=policy, jwks_cache=cache),
        fetcher,
        cache,
    )


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def other_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_valid_rs256_token_returns_exact_redacted_principal(rsa_key) -> None:
    policy = _policy()
    authenticator, fetcher, _cache = _authenticator(
        policy,
        _jwks(_rsa_jwk(rsa_key)),
    )

    principal = _run(authenticator.verify_token(_token(rsa_key, policy), now=NOW))

    assert principal.policy_id == policy.policy_id
    assert principal.resource == policy.resource
    assert principal.subject_digest == subject_digest(
        issuer=policy.issuer, subject=SUBJECT
    )
    assert principal.scopes == (
        "mastermind.executive.intent.submit",
        "mastermind.executive.read",
    )
    rendered = repr(principal)
    assert SUBJECT not in rendered
    assert "chatgpt-business-client" not in rendered
    assert fetcher.calls == [policy.jwks_uri]


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER", "bEaReR"])
def test_bearer_scheme_is_case_insensitive_with_one_ascii_space(
    rsa_key,
    scheme: str,
) -> None:
    policy = _policy()
    authenticator, _fetcher, _cache = _authenticator(
        policy,
        _jwks(_rsa_jwk(rsa_key)),
    )
    token = _token(rsa_key, policy)

    result = _run(
        authenticator.verify_authorization_header(
            f"{scheme} {token}",
            now=NOW,
        )
    )

    assert result.policy_id == policy.policy_id


def test_missing_authorization_header_is_typed() -> None:
    policy = _policy()
    authenticator, fetcher, _cache = _authenticator(policy, b"unused")

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_authorization_header(None, now=NOW))

    assert caught.value.code is AuthErrorCode.AUTHORIZATION_MISSING
    assert fetcher.calls == []


@pytest.mark.parametrize(
    "render",
    [
        lambda token: f"Basic {token}",
        lambda token: f"Bearer  {token}",
        lambda token: f"Bearer\t{token}",
        lambda token: "Bearer",
        lambda token: "Bearer ",
        lambda token: f" Bearer {token}",
        lambda token: f"Bearer {token} ",
        lambda token: f"Bearer {token},other",
        lambda token: f"Bearer {token}\r\nInjected: yes",
        lambda token: 42,
    ],
)
def test_malformed_authorization_header_is_refused_before_key_access(
    rsa_key,
    render,
) -> None:
    policy = _policy()
    authenticator, fetcher, _cache = _authenticator(policy, b"unused")
    header = render(_token(rsa_key, policy))

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_authorization_header(header, now=NOW))

    assert caught.value.code is AuthErrorCode.AUTHORIZATION_MALFORMED
    assert fetcher.calls == []


def test_oversized_token_is_refused_before_pyjwt_or_jwks(monkeypatch) -> None:
    from integrations.business_mcp_auth import jwt_verifier as module

    class _NeverCache:
        async def key_for(self, kid: str):
            raise AssertionError(f"cache reached for {kid}")

    def _unexpected_header(_token: str):
        raise AssertionError("PyJWT reached")

    monkeypatch.setattr(module.jwt, "get_unverified_header", _unexpected_header)
    authenticator = JwtAuthenticator(policy=_policy(), jwks_cache=_NeverCache())
    oversized = "a." + ("b" * MAX_TOKEN_BYTES) + ".c"

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(oversized, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_TOO_LARGE


def test_wrong_rsa_key_with_same_kid_is_refused(rsa_key, other_rsa_key) -> None:
    policy = _policy()
    authenticator, _fetcher, _cache = _authenticator(
        policy,
        _jwks(_rsa_jwk(rsa_key)),
    )

    with pytest.raises(AuthError) as caught:
        _run(
            authenticator.verify_token(
                _token(other_rsa_key, policy),
                now=NOW,
            )
        )

    assert caught.value.code is AuthErrorCode.TOKEN_SIGNATURE_REFUSED


def test_tampered_payload_is_refused(rsa_key) -> None:
    policy = _policy()
    authenticator, _fetcher, _cache = _authenticator(
        policy,
        _jwks(_rsa_jwk(rsa_key)),
    )
    parts = _token(rsa_key, policy).split(".")
    replacement = "A" if parts[1][-1] != "A" else "B"
    parts[1] = parts[1][:-1] + replacement
    tampered = ".".join(parts)

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(tampered, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_SIGNATURE_REFUSED


def test_none_algorithm_is_refused_by_header_policy() -> None:
    policy = _policy()
    authenticator, fetcher, _cache = _authenticator(policy, b"unused")
    token = jwt.encode(
        _claims(policy),
        key="",
        algorithm="none",
        headers={"kid": KID, "typ": "at+jwt"},
    )

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert fetcher.calls == []


def test_hs256_public_key_confusion_is_refused_before_jwks(rsa_key) -> None:
    policy = _policy()
    authenticator, fetcher, _cache = _authenticator(policy, b"unused")
    public_der = rsa_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    token = _token(public_der, policy, algorithm="HS256")

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert fetcher.calls == []


def test_es256_token_is_refused_before_jwks() -> None:
    policy = _policy()
    authenticator, fetcher, _cache = _authenticator(policy, b"unused")
    private_key = ec.generate_private_key(ec.SECP256R1())
    token = _token(private_key, policy, algorithm="ES256")

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert fetcher.calls == []


def test_unknown_kid_uses_one_bounded_refresh_then_preserves_key_error(rsa_key) -> None:
    policy = _policy()
    payload = _jwks(_rsa_jwk(rsa_key))
    authenticator, fetcher, cache = _authenticator(policy, payload, payload)
    _run(cache.key_for(KID))
    token = _token(rsa_key, policy, headers={"kid": "unknown-kid"})

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.KEY_NOT_FOUND
    assert fetcher.calls == [policy.jwks_uri, policy.jwks_uri]


@pytest.mark.parametrize("token", ["", "not-a-token", "a.b", "a.b.c.d", ".."])
def test_malformed_compact_shape_is_a_header_refusal(token: str) -> None:
    authenticator, fetcher, _cache = _authenticator(_policy(), b"unused")

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert fetcher.calls == []


def test_non_json_header_is_refused_before_jwks() -> None:
    token = ".".join(
        (
            _base64url_bytes(b"not-json"),
            _base64url_bytes(b"{}"),
            _base64url_bytes(b"signature"),
        )
    )
    authenticator, fetcher, _cache = _authenticator(_policy(), b"unused")

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert fetcher.calls == []


def test_non_json_payload_is_a_signature_decode_refusal(rsa_key) -> None:
    policy = _policy()
    header = _base64url_bytes(
        json.dumps({"alg": "RS256", "kid": KID, "typ": "at+jwt"}).encode()
    )
    token = ".".join(
        (
            header,
            _base64url_bytes(b"not-json"),
            _base64url_bytes(b"signature"),
        )
    )
    authenticator, _fetcher, _cache = _authenticator(
        policy,
        _jwks(_rsa_jwk(rsa_key)),
    )

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_SIGNATURE_REFUSED


@pytest.mark.parametrize(
    "headers",
    [
        {"crit": ["custom"]},
        {"jku": "https://attacker.test/jwks"},
        {"x5u": "https://attacker.test/cert"},
        {"jwk": {"kty": "RSA"}},
    ],
)
def test_remote_or_critical_header_fields_are_refused_before_jwks(
    rsa_key,
    headers: Mapping[str, object],
) -> None:
    policy = _policy()
    authenticator, fetcher, _cache = _authenticator(policy, b"unused")
    token = _token(rsa_key, policy, headers=headers)

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert fetcher.calls == []
    assert "attacker.test" not in str(caught.value)


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"iss": "https://attacker.example.test/"}, AuthErrorCode.ISSUER_REFUSED),
        (
            {"aud": "https://mcp.example.test/mcp/steward/v1"},
            AuthErrorCode.RESOURCE_REFUSED,
        ),
        ({"scope": "mastermind.executive.read"}, AuthErrorCode.SCOPE_REFUSED),
        ({"sub": "other-user"}, AuthErrorCode.SUBJECT_REFUSED),
        (
            {"iat": NOW - 100, "nbf": NOW - 100, "exp": NOW - 31},
            AuthErrorCode.TOKEN_EXPIRED,
        ),
        (
            {"iat": NOW, "nbf": NOW + 31, "exp": NOW + 600},
            AuthErrorCode.TOKEN_NOT_YET_VALID,
        ),
    ],
)
def test_signature_success_still_enforces_exact_claim_policy(
    rsa_key,
    overrides: Mapping[str, object],
    expected_code: AuthErrorCode,
) -> None:
    policy = _policy()
    authenticator, _fetcher, _cache = _authenticator(
        policy,
        _jwks(_rsa_jwk(rsa_key)),
    )
    token = _token(rsa_key, policy, **dict(overrides))

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(token, now=NOW))

    assert caught.value.code is expected_code
    assert token not in str(caught.value)
    assert SUBJECT not in str(caught.value)


def test_unexpected_cache_defect_maps_to_fixed_internal_error(rsa_key) -> None:
    class _BrokenCache:
        async def key_for(self, kid: str):
            raise RuntimeError(f"secret cache detail for {kid}")

    policy = _policy()
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=_BrokenCache())
    token = _token(rsa_key, policy)

    with pytest.raises(AuthError) as caught:
        _run(authenticator.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.INTERNAL_ERROR
    assert "secret cache detail" not in str(caught.value)
    assert token not in str(caught.value)
