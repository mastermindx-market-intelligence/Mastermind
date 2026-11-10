from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.claims import validate_verified_claims
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
from integrations.business_mcp_auth.jwks import BoundedJwksCache
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.business_mcp_auth.metadata import protected_resource_metadata


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


def _tainted_policy() -> ResourcePolicy:
    return dataclasses.replace(
        _policy(),
        required_scopes=("mastermind.steward.read", "offline_access"),
    )


def _claims(policy: ResourcePolicy, *, scope: str) -> dict[str, object]:
    return {
        "iss": policy.issuer,
        "sub": SUBJECT,
        "aud": policy.resource,
        "iat": 1_788_000_000,
        "nbf": 1_788_000_000,
        "exp": 1_788_000_600,
        "scope": scope,
        "client_id": "chatgpt-business-client",
    }


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


class _NeverKeySource:
    async def key_for(self, kid: str) -> dict[str, object]:
        raise AssertionError(f"JWKS access must not occur for malformed policy: {kid}")


class _ProjectionAuthenticator(JwtAuthenticator):
    def __init__(self, *, policy: ResourcePolicy, result: VerifiedPrincipal) -> None:
        self._policy = policy
        self.result = result
        self.calls: list[tuple[object, int]] = []

    async def verify_token(self, token: object, *, now: int) -> VerifiedPrincipal:
        self.calls.append((token, now))
        return self.result


class _Sink:
    def __init__(self) -> None:
        self.events: list[AuthAuditEvent] = []

    def emit(self, event: AuthAuditEvent) -> None:
        self.events.append(event)


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


def test_valid_wire_offline_access_remains_non_authorizing() -> None:
    policy = _policy()

    principal = validate_verified_claims(
        _claims(
            policy,
            scope="mastermind.steward.read offline_access",
        ),
        policy,
        now=NOW,
    )

    assert principal.scopes == ("mastermind.steward.read",)
    assert protected_resource_metadata(policy)["scopes_supported"] == [
        "mastermind.steward.read"
    ]


def test_replaced_policy_cannot_enter_claims_projection() -> None:
    policy = _tainted_policy()

    with pytest.raises(AuthError) as caught:
        validate_verified_claims(
            _claims(
                policy,
                scope="mastermind.steward.read offline_access",
            ),
            policy,
            now=NOW,
        )

    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_replaced_policy_cannot_enter_resource_metadata() -> None:
    policy = _tainted_policy()

    with pytest.raises(AuthError) as caught:
        protected_resource_metadata(policy)

    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_replaced_policy_cannot_bind_jwt_authenticator() -> None:
    policy = _tainted_policy()

    with pytest.raises(AuthError) as caught:
        JwtAuthenticator(policy=policy, jwks_cache=_NeverKeySource())

    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_replaced_policy_cannot_construct_mcp_verifier() -> None:
    policy = _tainted_policy()
    principal = VerifiedPrincipal(
        policy_id=policy.policy_id,
        issuer=policy.issuer,
        issuer_digest=hashlib.sha256(policy.issuer.encode("utf-8")).hexdigest(),
        resource=policy.resource,
        subject_digest=policy.allowed_subject_digests[0],
        client_ref="2" * 64,
        scopes=policy.required_scopes,
        issued_at=1_788_000_000,
        expires_at=1_788_000_600,
        jti_digest=None,
    )
    authenticator = _ProjectionAuthenticator(policy=policy, result=principal)

    with pytest.raises(AuthError) as caught:
        MastermindTokenVerifier(
            authenticator=authenticator,
            policy=policy,
            now=lambda: NOW,
            audit_sink=_Sink(),
        )

    assert caught.value.code is AuthErrorCode.INVALID_POLICY


def test_runtime_policy_drift_cannot_project_offline_access_as_mcp_authority() -> None:
    valid_policy = _policy()
    tainted_policy = _tainted_policy()
    principal = VerifiedPrincipal(
        policy_id=tainted_policy.policy_id,
        issuer=tainted_policy.issuer,
        issuer_digest=hashlib.sha256(
            tainted_policy.issuer.encode("utf-8")
        ).hexdigest(),
        resource=tainted_policy.resource,
        subject_digest=tainted_policy.allowed_subject_digests[0],
        client_ref="2" * 64,
        scopes=tainted_policy.required_scopes,
        issued_at=1_788_000_000,
        expires_at=1_788_000_600,
        jti_digest=None,
    )
    authenticator = _ProjectionAuthenticator(
        policy=valid_policy,
        result=principal,
    )
    sink = _Sink()
    clock_calls: list[bool] = []

    def _clock() -> int:
        clock_calls.append(True)
        return NOW

    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=valid_policy,
        now=_clock,
        audit_sink=sink,
    )
    verifier._policy = tainted_policy
    authenticator._policy = tainted_policy

    assert _run(verifier.verify_token("opaque-token")) is None
    assert clock_calls == []
    assert authenticator.calls == []
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=valid_policy.policy_id,
            code=AuthErrorCode.INTERNAL_ERROR.value,
            accepted=False,
        )
    ]
