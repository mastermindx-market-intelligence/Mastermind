from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator


NOW = 1_788_000_100


def _b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64u_uint(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return _b64u(value.to_bytes(width, "big"))


def _public_jwk(private_key, *, kid: str = "kid-a") -> dict[str, object]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kid": kid,
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": _b64u_uint(numbers.n),
        "e": _b64u_uint(numbers.e),
    }


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


def _payload_text(*, extension: str = "0") -> str:
    policy = _policy()
    scope = "mastermind.executive.read mastermind.executive.intent.submit"
    return (
        "{"
        f'"iss":{json.dumps(policy.issuer)},'
        '"sub":"chairman-opaque",'
        f'"aud":{json.dumps(policy.resource)},'
        '"iat":1788000000,"nbf":1788000000,"exp":1788000600,'
        f'"scope":{json.dumps(scope)},'
        '"jti":"token-id-opaque",'
        '"client_id":"chatgpt-business-client",'
        f'"extension":{extension}'
        "}"
    )


def _raw_token(private_key, *, header_text: str, payload_text: str) -> str:
    header_segment = _b64u(header_text.encode("utf-8"))
    payload_segment = _b64u(payload_text.encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header_segment}.{payload_segment}.{_b64u(signature)}"


class _Cache:
    def __init__(self, key: Mapping[str, object]) -> None:
        self.key = dict(key)
        self.calls: list[str] = []

    async def key_for(self, kid: str) -> dict[str, object]:
        self.calls.append(kid)
        await asyncio.sleep(0)
        return dict(self.key)


def _run(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _verifier(private_key):
    cache = _Cache(_public_jwk(private_key))
    return JwtAuthenticator(policy=_policy(), jwks_cache=cache), cache


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_header_number_is_refused_before_jwks(
    private_key,
    constant: str,
) -> None:
    verifier, cache = _verifier(private_key)
    token = _raw_token(
        private_key,
        header_text=(
            '{"alg":"RS256","kid":"kid-a","typ":"at+jwt",'
            f'"extension":{constant}'
            "}"
        ),
        payload_text=_payload_text(),
    )

    with pytest.raises(AuthError) as caught:
        _run(verifier.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert cache.calls == []


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_payload_number_is_refused_before_jwks(
    private_key,
    constant: str,
) -> None:
    verifier, cache = _verifier(private_key)
    token = _raw_token(
        private_key,
        header_text='{"alg":"RS256","kid":"kid-a","typ":"at+jwt"}',
        payload_text=_payload_text(extension=constant),
    )

    with pytest.raises(AuthError) as caught:
        _run(verifier.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert cache.calls == []


def test_oversized_header_integer_maps_to_typed_refusal_before_jwks(
    private_key,
) -> None:
    verifier, cache = _verifier(private_key)
    huge_integer = "9" * 5_000
    token = _raw_token(
        private_key,
        header_text=(
            '{"alg":"RS256","kid":"kid-a","typ":"at+jwt",'
            f'"extension":{huge_integer}'
            "}"
        ),
        payload_text=_payload_text(),
    )

    with pytest.raises(AuthError) as caught:
        _run(verifier.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert cache.calls == []


def test_oversized_payload_integer_maps_to_typed_refusal_before_jwks(
    private_key,
) -> None:
    verifier, cache = _verifier(private_key)
    token = _raw_token(
        private_key,
        header_text='{"alg":"RS256","kid":"kid-a","typ":"at+jwt"}',
        payload_text=_payload_text(extension="9" * 5_000),
    )

    with pytest.raises(AuthError) as caught:
        _run(verifier.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert cache.calls == []
