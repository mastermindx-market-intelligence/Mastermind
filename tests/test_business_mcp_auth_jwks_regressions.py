from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache


def _policy():
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
                subject_digest(issuer=issuer, subject="chairman-opaque")
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _key(kid: str = "kid-a", **overrides) -> dict[str, object]:
    value: dict[str, object] = {
        "kid": kid,
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": "AQAB",
        "e": "AQAB",
    }
    value.update(overrides)
    return value


def _jwks(*keys: Mapping[str, object]) -> bytes:
    return json.dumps({"keys": list(keys)}, separators=(",", ":")).encode()


class _Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def monotonic(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _Fetcher:
    def __init__(self, *responses: bytes) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def fetch(self, *, url: str, timeout_seconds: float, max_bytes: int) -> bytes:
        del url, timeout_seconds, max_bytes
        self.calls += 1
        await asyncio.sleep(0)
        if not self.responses:
            raise RuntimeError("unexpected fetch")
        return self.responses.pop(0)


def _run(coroutine):
    return asyncio.run(coroutine)


def test_returned_nested_certificate_chain_cannot_corrupt_cache() -> None:
    key = _key(x5c=["certificate-a", "certificate-b"])
    fetcher = _Fetcher(_jwks(key))
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=fetcher, monotonic=_Clock().monotonic
    )

    first = _run(cache.key_for("kid-a"))
    assert isinstance(first["x5c"], list)
    first["x5c"].append("attacker-change")

    second = _run(cache.key_for("kid-a"))
    assert second["x5c"] == ["certificate-a", "certificate-b"]
    assert fetcher.calls == 1


def test_rejected_jwks_document_uses_cross_request_backoff() -> None:
    clock = _Clock()
    fetcher = _Fetcher(b"not-json", b"not-json", b"not-json")
    cache = BoundedJwksCache(
        policy=_policy(), fetcher=fetcher, monotonic=clock.monotonic
    )

    with pytest.raises(AuthError) as first:
        _run(cache.key_for("kid-a"))
    assert first.value.code is AuthErrorCode.JWKS_REFUSED

    with pytest.raises(AuthError) as during_backoff:
        _run(cache.key_for("kid-a"))
    assert during_backoff.value.code is AuthErrorCode.JWKS_UNAVAILABLE
    assert fetcher.calls == 1

    clock.advance(5)
    with pytest.raises(AuthError) as after_backoff:
        _run(cache.key_for("kid-a"))
    assert after_backoff.value.code is AuthErrorCode.JWKS_REFUSED
    assert fetcher.calls == 2
