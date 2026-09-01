from __future__ import annotations

import asyncio
import dataclasses
import hashlib

import pytest

from integrations.business_mcp_auth import mcp_adapter
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


NOW = 1_788_000_100


def _policy(subject: str = "chairman-a") -> ResourcePolicy:
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
                subject_digest(issuer=issuer, subject=subject)
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


class _Fetcher:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls = 0

    async def fetch(self, *, url: str, timeout_seconds: float, max_bytes: int) -> bytes:
        self.calls += 1
        return self.payload


def _run(coroutine):
    return asyncio.run(coroutine)


def _key_json(*, n: str = "AQAB", e: str = "AQAB") -> str:
    return (
        '{"kid":"kid-a","kty":"RSA","use":"sig",'
        f'"alg":"RS256","n":"{n}","e":"{e}"}}'
    )


@pytest.mark.parametrize(
    "payload",
    [
        (
            '{"keys":[' + _key_json() + '],"keys":[' + _key_json() + "]}"
        ).encode(),
        (
            '{"keys":[' + _key_json() + '],"\\u006beys":[' + _key_json() + "]}"
        ).encode(),
        b'{"keys":[{"kid":"kid-a","kid":"kid-b","kty":"RSA","alg":"RS256","n":"AQAB","e":"AQAB"}]}',
        b'{"keys":[{"kid":"kid-a","\\u006bid":"kid-b","kty":"RSA","alg":"RS256","n":"AQAB","e":"AQAB"}]}',
        b'{"keys":[{"kid":"kid-a","kty":"RSA","alg":"RS256","alg":"RS256","n":"AQAB","e":"AQAB"}]}',
        b'{"keys":[{"kid":"kid-a","kty":"RSA","alg":"RS256","\\u0061lg":"RS256","n":"AQAB","e":"AQAB"}]}',
    ],
)
def test_duplicate_or_escaped_equivalent_jwks_members_are_refused(
    payload: bytes,
) -> None:
    fetcher = _Fetcher(payload)
    cache = BoundedJwksCache(
        policy=_policy(),
        fetcher=fetcher,
        monotonic=lambda: 100.0,
    )

    with pytest.raises(AuthError) as caught:
        _run(cache.key_for("kid-a"))

    assert caught.value.code is AuthErrorCode.JWKS_REFUSED
    assert fetcher.calls == 1


@pytest.mark.parametrize(
    "payload",
    [
        ('{"keys":[' + _key_json(n="AR") + "]}").encode(),
        ('{"keys":[' + _key_json(e="AR") + "]}").encode(),
        ('{"keys":[' + _key_json(n="AAEAAQ") + "]}").encode(),
        ('{"keys":[' + _key_json(e="AAEAAQ") + "]}").encode(),
        ('{"keys":[' + _key_json(n="AA") + "]}").encode(),
        ('{"keys":[' + _key_json(e="AA") + "]}").encode(),
    ],
)
def test_noncanonical_or_nonpositive_base64url_uint_is_refused(payload: bytes) -> None:
    cache = BoundedJwksCache(
        policy=_policy(),
        fetcher=_Fetcher(payload),
        monotonic=lambda: 100.0,
    )

    with pytest.raises(AuthError) as caught:
        _run(cache.key_for("kid-a"))

    assert caught.value.code is AuthErrorCode.JWKS_REFUSED


def test_canonical_base64url_uint_control_is_preserved() -> None:
    payload = ('{"keys":[' + _key_json() + "]}").encode()
    cache = BoundedJwksCache(
        policy=_policy(),
        fetcher=_Fetcher(payload),
        monotonic=lambda: 100.0,
    )

    assert _run(cache.key_for("kid-a")) == {
        "kid": "kid-a",
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": "AQAB",
        "e": "AQAB",
    }


def _principal(policy: ResourcePolicy, **overrides: object) -> VerifiedPrincipal:
    value = VerifiedPrincipal(
        policy_id=policy.policy_id,
        issuer=policy.issuer,
        issuer_digest=hashlib.sha256(policy.issuer.encode("utf-8")).hexdigest(),
        resource=policy.resource,
        subject_digest=policy.allowed_subject_digests[0],
        client_ref="2" * 64,
        scopes=policy.required_scopes,
        issued_at=1_788_000_000,
        expires_at=1_788_000_600,
        jti_digest="3" * 64,
    )
    return dataclasses.replace(value, **overrides)


class _BoundAuthenticator(JwtAuthenticator):
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


def _verifier(
    *,
    authenticator: JwtAuthenticator,
    policy: ResourcePolicy,
    sink: _Sink,
) -> MastermindTokenVerifier:
    return MastermindTokenVerifier(
        authenticator=authenticator,
        policy=policy,
        now=lambda: NOW,
        audit_sink=sink,
    )


def test_cross_policy_authenticator_is_refused_before_token_verification() -> None:
    policy_a = _policy("chairman-a")
    policy_b = _policy("chairman-b")
    authenticator = _BoundAuthenticator(
        policy=policy_a,
        result=_principal(policy_a),
    )
    sink = _Sink()
    verifier = _verifier(
        authenticator=authenticator,
        policy=policy_b,
        sink=sink,
    )

    assert _run(verifier.verify_token("raw-token")) is None
    assert authenticator.calls == []
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=policy_b.policy_id,
            code=AuthErrorCode.INTERNAL_ERROR.value,
            accepted=False,
        )
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"issuer_digest": "f" * 64},
        {"subject_digest": "e" * 64},
        {"scopes": ("mastermind.steward.read", "mastermind.extra")},
    ],
)
def test_final_principal_projection_rechecks_exact_policy_facts(
    overrides: dict[str, object],
) -> None:
    policy = _policy()
    authenticator = _BoundAuthenticator(
        policy=policy,
        result=_principal(policy, **overrides),
    )
    sink = _Sink()
    verifier = _verifier(
        authenticator=authenticator,
        policy=policy,
        sink=sink,
    )

    assert _run(verifier.verify_token("raw-token")) is None
    assert authenticator.calls == [("raw-token", NOW)]
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=policy.policy_id,
            code=AuthErrorCode.INTERNAL_ERROR.value,
            accepted=False,
        )
    ]


@pytest.mark.parametrize(
    ("subject_index", "accepted"),
    [(0, True), (2, True), (None, False)],
)
def test_subject_membership_compares_the_full_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    subject_index: int | None,
    accepted: bool,
) -> None:
    allowed = ("a" * 64, "b" * 64, "c" * 64)
    subject = allowed[subject_index] if subject_index is not None else "d" * 64
    policy = dataclasses.replace(
        _policy(),
        allowed_subject_digests=allowed,
    )
    authenticator = _BoundAuthenticator(
        policy=policy,
        result=_principal(policy, subject_digest=subject),
    )
    sink = _Sink()
    verifier = _verifier(
        authenticator=authenticator,
        policy=policy,
        sink=sink,
    )
    comparisons: list[tuple[str, str]] = []

    def _recording_compare_digest(left: str, right: str) -> bool:
        comparisons.append((left, right))
        return left == right

    monkeypatch.setattr(mcp_adapter.hmac, "compare_digest", _recording_compare_digest)

    access = _run(verifier.verify_token("raw-token"))

    assert (access is not None) is accepted
    # One issuer-digest comparison is followed by every allowlist comparison,
    # even when an earlier subject entry already matched.
    assert comparisons[1:] == [(subject, digest) for digest in allowed]


def test_mcp_adapter_refuses_non_jwt_authenticator_at_composition_time() -> None:
    policy = _policy()
    with pytest.raises(TypeError, match="JwtAuthenticator"):
        MastermindTokenVerifier(
            authenticator=object(),  # type: ignore[arg-type]
            policy=policy,
            now=lambda: NOW,
            audit_sink=_Sink(),
        )
