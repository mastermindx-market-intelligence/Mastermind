from __future__ import annotations

import asyncio
import base64
import json

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator


NOW = 1_788_000_100
SUBJECT = "chairman-a"
KID = "kid-a"


def _run(coroutine):
    return asyncio.run(coroutine)


def _base64url_uint(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode()


def _policy() -> ResourcePolicy:
    issuer = "https://identity.example.test/"
    return load_resource_policy(
        {
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
                subject_digest(issuer=issuer, subject=SUBJECT)
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _rsa_jwk(private_key: rsa.RSAPrivateKey) -> dict[str, object]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kid": KID,
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": _base64url_uint(numbers.n),
        "e": _base64url_uint(numbers.e),
    }


def _jwks(private_key: rsa.RSAPrivateKey) -> bytes:
    return json.dumps(
        {"keys": [_rsa_jwk(private_key)]},
        separators=(",", ":"),
    ).encode()


def _token(private_key: rsa.RSAPrivateKey, policy: ResourcePolicy) -> str:
    return jwt.encode(
        {
            "iss": policy.issuer,
            "sub": SUBJECT,
            "aud": policy.resource,
            "iat": 1_788_000_000,
            "nbf": 1_788_000_000,
            "exp": 1_788_000_600,
            "scope": " ".join(policy.required_scopes),
            "client_id": "chatgpt-business-client",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": KID, "typ": "at+jwt"},
    )


class _Fetcher:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls = 0

    async def fetch(self, *, url: str, timeout_seconds: float, max_bytes: int) -> bytes:
        del url, timeout_seconds, max_bytes
        self.calls += 1
        return self.payload


def _authenticator(
    private_key: rsa.RSAPrivateKey,
) -> tuple[JwtAuthenticator, ResourcePolicy, _Fetcher]:
    policy = _policy()
    fetcher = _Fetcher(_jwks(private_key))
    cache = BoundedJwksCache(
        policy=policy,
        fetcher=fetcher,
        monotonic=lambda: 100.0,
    )
    return JwtAuthenticator(policy=policy, jwks_cache=cache), policy, fetcher


def test_correctly_signed_1024_bit_rs256_token_is_refused() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    authenticator, policy, fetcher = _authenticator(private_key)

    with pytest.raises(AuthError) as caught:
        _run(
            authenticator.verify_token(
                _token(private_key, policy),
                now=NOW,
            )
        )

    assert caught.value.code is AuthErrorCode.TOKEN_SIGNATURE_REFUSED
    assert fetcher.calls == 1


def test_correctly_signed_2048_bit_rs256_token_remains_accepted() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    authenticator, policy, fetcher = _authenticator(private_key)

    principal = _run(
        authenticator.verify_token(
            _token(private_key, policy),
            now=NOW,
        )
    )

    assert principal.policy_id == policy.policy_id
    assert principal.resource == policy.resource
    assert principal.scopes == policy.required_scopes
    assert fetcher.calls == 1
