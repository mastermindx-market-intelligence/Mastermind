from __future__ import annotations

from dataclasses import replace
from typing import Any

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    load_resource_policy,
    subject_digest,
)
from integrations.mastermind_executive_app import gateway
from integrations.mastermind_executive_app.gateway import AppPolicies, READ_SCOPE, SUBMIT_SCOPE

ISSUER = "https://issuer.mastermind.example.test/"
RESOURCE = "https://executive.mastermind.example.test/mcp"
METADATA_URL = "https://executive.mastermind.example.test/.well-known/oauth-protected-resource"
JWKS_URI = "https://issuer.mastermind.example.test/.well-known/jwks.json"


def _policy(*, policy_id: str, scopes: list[str]):
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": policy_id,
            "resource": RESOURCE,
            "resource_metadata_url": METADATA_URL,
            "issuer": ISSUER,
            "authorization_servers": [ISSUER],
            "jwks_uri": JWKS_URI,
            "required_scopes": scopes,
            "allowed_subject_digests": [
                subject_digest(issuer=ISSUER, subject="chairman-a")
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 3600,
            "jwks_cache_ttl_seconds": 600,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 30,
        }
    )


def _policies() -> AppPolicies:
    return AppPolicies(
        read=_policy(policy_id="executive-read", scopes=[READ_SCOPE]),
        submit=_policy(
            policy_id="executive-submit",
            scopes=sorted([READ_SCOPE, SUBMIT_SCOPE]),
        ),
    )


class _Cache:
    async def key_for(self, _kid: str) -> dict[str, Any]:
        raise AssertionError("key lookup is not needed for this construction test")


def test_default_authenticators_share_one_jwks_cache_for_same_authority(
    monkeypatch,
) -> None:
    created: list[object] = []

    def fake_default(_policy):
        cache = _Cache()
        created.append(cache)
        return cache

    monkeypatch.setattr(gateway, "_default_jwks_cache", fake_default)

    read_authenticator, submit_authenticator = gateway.make_jwt_authenticators(
        _policies()
    )

    assert len(created) == 1
    assert read_authenticator._jwks_cache is created[0]
    assert submit_authenticator._jwks_cache is created[0]


def test_default_authenticators_keep_caches_separate_when_cache_contract_differs(
    monkeypatch,
) -> None:
    policies = _policies()
    policies = AppPolicies(
        read=policies.read,
        submit=replace(
            policies.submit,
            fetch_failure_backoff_seconds=(
                policies.submit.fetch_failure_backoff_seconds + 1
            ),
        ),
    )
    created: list[object] = []

    def fake_default(_policy):
        cache = _Cache()
        created.append(cache)
        return cache

    monkeypatch.setattr(gateway, "_default_jwks_cache", fake_default)

    read_authenticator, submit_authenticator = gateway.make_jwt_authenticators(
        policies
    )

    assert len(created) == 2
    assert read_authenticator._jwks_cache is created[0]
    assert submit_authenticator._jwks_cache is created[1]


def test_submit_token_reuses_verified_jwks_generation_across_policy_fallback(
    monkeypatch,
) -> None:
    import asyncio
    import base64
    import json

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from integrations.business_mcp_auth.jwks import BoundedJwksCache
    from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()

    def b64uint(value: int) -> str:
        width = max(1, (value.bit_length() + 7) // 8)
        return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode()

    jwks = json.dumps(
        {
            "keys": [
                {
                    "kid": "shared-kid",
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "n": b64uint(numbers.n),
                    "e": b64uint(numbers.e),
                }
            ]
        }
    ).encode()

    class Fetcher:
        def __init__(self) -> None:
            self.calls = 0

        async def fetch(self, **_kwargs) -> bytes:
            self.calls += 1
            return jwks

    class Sink:
        def __init__(self) -> None:
            self.events = []

        def emit(self, event) -> None:
            self.events.append(event)

    fetcher = Fetcher()

    def fake_default(policy):
        return BoundedJwksCache(
            policy=policy,
            fetcher=fetcher,
            monotonic=lambda: 100.0,
        )

    monkeypatch.setattr(gateway, "_default_jwks_cache", fake_default)
    policies = _policies()
    read_authenticator, submit_authenticator = gateway.make_jwt_authenticators(
        policies
    )
    read_sink = Sink()
    submit_sink = Sink()
    read_verifier = MastermindTokenVerifier(
        authenticator=read_authenticator,
        policy=policies.read,
        now=lambda: 1_800_000_000,
        audit_sink=read_sink,
    )
    submit_verifier = MastermindTokenVerifier(
        authenticator=submit_authenticator,
        policy=policies.submit,
        now=lambda: 1_800_000_000,
        audit_sink=submit_sink,
    )
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": "chairman-a",
            "aud": RESOURCE,
            "iat": 1_800_000_000,
            "exp": 1_800_000_600,
            "scope": f"{SUBMIT_SCOPE} {READ_SCOPE}",
            "client_id": "chatgpt-business-client",
        },
        key,
        algorithm="RS256",
        headers={"kid": "shared-kid", "typ": "JWT"},
    )

    async def exercise():
        read_access = await read_verifier.verify_token(token)
        submit_access = await submit_verifier.verify_token(token)
        return read_access, submit_access

    read_access, submit_access = asyncio.run(exercise())

    assert read_access is None
    assert submit_access is not None
    assert submit_access.scopes == list(policies.submit.required_scopes)
    assert fetcher.calls == 1
    assert [event.code for event in read_sink.events] == ["scope_refused"]
    assert [event.code for event in submit_sink.events] == ["accepted"]
