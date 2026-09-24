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
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


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


def _payload_text() -> str:
    policy = _policy()
    return json.dumps(
        {
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
        },
        separators=(",", ":"),
    )


def _raw_token(private_key, *, header_text: str, payload_text: str) -> str:
    header_segment = _b64u(header_text.encode("utf-8"))
    payload_segment = _b64u(payload_text.encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header_segment}.{payload_segment}.{_b64u(signature)}"


def _alternate_same_bytes(segment: str) -> str:
    remainder = len(segment) % 4
    if remainder not in (2, 3):
        raise AssertionError("segment must contain base64url pad bits")
    index = _ALPHABET.index(segment[-1])
    if remainder == 2:
        prefix = index & 0b110000
        candidate = prefix | ((index + 1) & 0b001111)
        if candidate == index:
            candidate = prefix | ((index + 2) & 0b001111)
    else:
        prefix = index & 0b111100
        candidate = prefix | ((index + 1) & 0b000011)
        if candidate == index:
            candidate = prefix | ((index + 2) & 0b000011)
    alternate = segment[:-1] + _ALPHABET[candidate]
    assert alternate != segment
    original = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    decoded = base64.urlsafe_b64decode(alternate + "=" * (-len(alternate) % 4))
    assert decoded == original
    return alternate


def _text_with_pad_bits(value: str) -> str:
    candidate = value
    for _ in range(4):
        if len(_b64u(candidate.encode("utf-8"))) % 4 in (2, 3):
            return candidate
        candidate += " "
    raise AssertionError("could not create a segment with pad bits")


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


def _verifier(private_key):
    cache = _Cache(_public_jwk(private_key))
    return JwtAuthenticator(policy=_policy(), jwks_cache=cache), cache


def test_duplicate_header_member_is_refused_before_jwks() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier, cache = _verifier(private_key)
    token = _raw_token(
        private_key,
        header_text=(
            '{"alg":"RS256","kid":"kid-a","kid":"kid-a",'
            '"typ":"at+jwt"}'
        ),
        payload_text=_payload_text(),
    )

    with pytest.raises(AuthError) as caught:
        _run(verifier.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert cache.calls == []


def test_duplicate_payload_member_is_refused_before_jwks() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier, cache = _verifier(private_key)
    policy = _policy()
    scope = "mastermind.executive.read mastermind.executive.intent.submit"
    payload = (
        '{'
        f'"iss":{json.dumps(policy.issuer)},'
        '"sub":"chairman-opaque",'
        f'"aud":{json.dumps(policy.resource)},'
        '"iat":1788000000,"nbf":1788000000,"exp":1788000600,'
        f'"scope":{json.dumps(scope)},"scope":{json.dumps(scope)},'
        '"jti":"token-id-opaque","client_id":"chatgpt-business-client"'
        '}'
    )
    token = _raw_token(
        private_key,
        header_text='{"alg":"RS256","kid":"kid-a","typ":"at+jwt"}',
        payload_text=payload,
    )

    with pytest.raises(AuthError) as caught:
        _run(verifier.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert cache.calls == []


def test_noncanonical_header_base64url_is_refused_before_jwks() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier, cache = _verifier(private_key)
    header_text = _text_with_pad_bits(
        '{"alg":"RS256","kid":"kid-a","typ":"at+jwt"}'
    )
    token = _raw_token(
        private_key,
        header_text=header_text,
        payload_text=_payload_text(),
    )
    header, payload, _signature = token.split(".")
    noncanonical_header = _alternate_same_bytes(header)
    signing_input = f"{noncanonical_header}.{payload}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    token = f"{noncanonical_header}.{payload}.{_b64u(signature)}"

    with pytest.raises(AuthError) as caught:
        _run(verifier.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert cache.calls == []


def test_noncanonical_payload_base64url_is_refused_before_jwks() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier, cache = _verifier(private_key)
    payload_text = _text_with_pad_bits(_payload_text())
    token = _raw_token(
        private_key,
        header_text='{"alg":"RS256","kid":"kid-a","typ":"at+jwt"}',
        payload_text=payload_text,
    )
    header, payload, _signature = token.split(".")
    noncanonical_payload = _alternate_same_bytes(payload)
    signing_input = f"{header}.{noncanonical_payload}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    token = f"{header}.{noncanonical_payload}.{_b64u(signature)}"

    with pytest.raises(AuthError) as caught:
        _run(verifier.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert cache.calls == []


def test_noncanonical_signature_base64url_is_refused_before_jwks() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier, cache = _verifier(private_key)
    token = _raw_token(
        private_key,
        header_text='{"alg":"RS256","kid":"kid-a","typ":"at+jwt"}',
        payload_text=_payload_text(),
    )
    header, payload, signature = token.split(".")
    noncanonical_signature = _alternate_same_bytes(signature)
    token = f"{header}.{payload}.{noncanonical_signature}"

    with pytest.raises(AuthError) as caught:
        _run(verifier.verify_token(token, now=NOW))

    assert caught.value.code is AuthErrorCode.TOKEN_HEADER_REFUSED
    assert cache.calls == []
