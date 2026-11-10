from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
from collections.abc import Mapping

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.server.auth.provider import AccessToken

from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AUTH_POLICY_SCHEMA,
    AuthAuditEvent,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.business_mcp_auth.metadata import (
    mcp_auth_error_result,
    oauth_security_schemes,
    protected_resource_metadata,
    www_authenticate,
)


NOW = 1_788_000_100
ISSUED_AT = 1_788_000_000
EXPIRES_AT = 1_788_000_600
ISSUER = "https://identity.example.test/"
JWKS_URI = "https://identity.example.test/.well-known/jwks.json"
SUBJECT = "chairman-opaque"
OTHER_SUBJECT = "chairman-rollover"
CLIENT_ID = "chatgpt-business-client"

_REALMS: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "steward": (
        "mastermind-steward-v1",
        ("mastermind.steward.read",),
    ),
    "executive": (
        "mastermind-executive-v1",
        (
            "mastermind.executive.intent.submit",
            "mastermind.executive.read",
        ),
    ),
    "dialogue": (
        "mastermind-dialogue-v1",
        (
            "mastermind.dialogue.read",
            "mastermind.dialogue.write",
        ),
    ),
}


def _run(coroutine):
    return asyncio.run(coroutine)


def _base64url_uint(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return (
        base64.urlsafe_b64encode(value.to_bytes(width, "big"))
        .rstrip(b"=")
        .decode("ascii")
    )


def _rsa_jwk(
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str,
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
    return json.dumps(
        {"keys": list(keys)},
        separators=(",", ":"),
    ).encode("utf-8")


def _policy(
    realm: str,
    *,
    subject: str = SUBJECT,
    jwks_cache_ttl_seconds: int = 60,
) -> ResourcePolicy:
    policy_id, scopes = _REALMS[realm]
    resource = f"https://mcp.example.test/mcp/{realm}/v1"
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": policy_id,
            "resource": resource,
            "resource_metadata_url": (
                "https://mcp.example.test/.well-known/"
                f"oauth-protected-resource/mcp/{realm}/v1"
            ),
            "issuer": ISSUER,
            "authorization_servers": [ISSUER],
            "jwks_uri": JWKS_URI,
            "required_scopes": list(scopes),
            "allowed_subject_digests": [
                subject_digest(issuer=ISSUER, subject=subject)
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": jwks_cache_ttl_seconds,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _token(
    private_key: rsa.RSAPrivateKey,
    policy: ResourcePolicy,
    *,
    kid: str,
    subject: str = SUBJECT,
    scopes: tuple[str, ...] | None = None,
    client_id: str = CLIENT_ID,
    jti: str = "opaque-token-id",
) -> str:
    token_scopes = scopes if scopes is not None else tuple(reversed(policy.required_scopes))
    return jwt.encode(
        {
            "iss": policy.issuer,
            "sub": subject,
            "aud": policy.resource,
            "iat": ISSUED_AT,
            "nbf": ISSUED_AT,
            "exp": EXPIRES_AT,
            "scope": " ".join(token_scopes),
            "client_id": client_id,
            "jti": jti,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid, "typ": "at+jwt"},
    )


class _Clock:
    def __init__(self) -> None:
        self.wall = NOW
        self.steady = 100.0

    def now(self) -> int:
        return self.wall

    def monotonic(self) -> float:
        return self.steady

    def advance(self, seconds: int) -> None:
        self.wall += seconds
        self.steady += float(seconds)


class _Fetcher:
    def __init__(self, *responses: bytes | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    async def fetch(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> bytes:
        del timeout_seconds, max_bytes
        self.calls.append(url)
        await asyncio.sleep(0)
        if not self.responses:
            raise RuntimeError("unexpected fetch")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _Sink:
    def __init__(self) -> None:
        self.events: list[AuthAuditEvent] = []

    def emit(self, event: AuthAuditEvent) -> None:
        self.events.append(event)


def _verifier(
    policy: ResourcePolicy,
    fetcher: _Fetcher,
    clock: _Clock,
) -> tuple[MastermindTokenVerifier, BoundedJwksCache, _Sink]:
    cache = BoundedJwksCache(
        policy=policy,
        fetcher=fetcher,
        monotonic=clock.monotonic,
    )
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=cache)
    sink = _Sink()
    return (
        MastermindTokenVerifier(
            authenticator=authenticator,
            policy=policy,
            now=clock.now,
            audit_sink=sink,
        ),
        cache,
        sink,
    )


@pytest.fixture(scope="module")
def key_a() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def key_b() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_signed_steward_token_traverses_complete_resource_server_chain(
    key_a: rsa.RSAPrivateKey,
) -> None:
    policy = _policy("steward")
    fetcher = _Fetcher(_jwks(_rsa_jwk(key_a, kid="kid-a")))
    clock = _Clock()
    verifier, _cache, sink = _verifier(policy, fetcher, clock)
    token = _token(key_a, policy, kid="kid-a")

    access = _run(verifier.verify_token(token))

    assert isinstance(access, AccessToken)
    client_ref = hashlib.sha256(
        (ISSUER + "\nclient\n" + CLIENT_ID).encode("utf-8")
    ).hexdigest()
    assert access.model_dump() == {
        "token": token,
        "client_id": client_ref,
        "scopes": list(policy.required_scopes),
        "expires_at": EXPIRES_AT,
        "resource": policy.resource,
        "subject": policy.allowed_subject_digests[0],
        "claims": {
            "issuer_digest": hashlib.sha256(ISSUER.encode("utf-8")).hexdigest(),
            "client_ref": client_ref,
            "jti_digest": hashlib.sha256(
                b"opaque-token-id"
            ).hexdigest(),
        },
    }
    assert fetcher.calls == [JWKS_URI]
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=policy.policy_id,
            code="accepted",
            accepted=True,
        )
    ]
    rendered = json.dumps(dataclasses.asdict(sink.events[0]), sort_keys=True)
    for forbidden in (token, SUBJECT, CLIENT_ID):
        assert forbidden not in rendered
        assert forbidden not in repr(sink.events[0])


def test_valid_steward_token_is_refused_by_other_resource_realms(
    key_a: rsa.RSAPrivateKey,
) -> None:
    steward = _policy("steward")
    token = _token(key_a, steward, kid="kid-a")
    payload = _jwks(_rsa_jwk(key_a, kid="kid-a"))

    for realm in ("executive", "dialogue"):
        policy = _policy(realm)
        fetcher = _Fetcher(payload)
        verifier, _cache, sink = _verifier(policy, fetcher, _Clock())

        assert _run(verifier.verify_token(token)) is None
        assert fetcher.calls == [JWKS_URI]
        assert sink.events == [
            AuthAuditEvent(
                schema=AUTH_AUDIT_SCHEMA,
                policy_id=policy.policy_id,
                code=AuthErrorCode.RESOURCE_REFUSED.value,
                accepted=False,
            )
        ]


def test_executive_token_missing_submit_scope_is_refused(
    key_a: rsa.RSAPrivateKey,
) -> None:
    policy = _policy("executive")
    fetcher = _Fetcher(_jwks(_rsa_jwk(key_a, kid="kid-a")))
    verifier, _cache, sink = _verifier(policy, fetcher, _Clock())
    token = _token(
        key_a,
        policy,
        kid="kid-a",
        scopes=("mastermind.executive.read",),
    )

    assert _run(verifier.verify_token(token)) is None
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=policy.policy_id,
            code=AuthErrorCode.SCOPE_REFUSED.value,
            accepted=False,
        )
    ]


def test_subject_rollover_requires_new_policy_and_verifier(
    key_a: rsa.RSAPrivateKey,
) -> None:
    old_policy = _policy("steward")
    payload = _jwks(_rsa_jwk(key_a, kid="kid-a"))
    old_verifier, _old_cache, old_sink = _verifier(
        old_policy,
        _Fetcher(payload),
        _Clock(),
    )
    token = _token(
        key_a,
        old_policy,
        kid="kid-a",
        subject=OTHER_SUBJECT,
    )

    assert _run(old_verifier.verify_token(token)) is None
    assert old_sink.events[-1].code == AuthErrorCode.SUBJECT_REFUSED.value

    new_policy = _policy("steward", subject=OTHER_SUBJECT)
    new_verifier, _new_cache, new_sink = _verifier(
        new_policy,
        _Fetcher(payload),
        _Clock(),
    )
    accepted = _run(new_verifier.verify_token(token))

    assert isinstance(accepted, AccessToken)
    assert accepted.subject == new_policy.allowed_subject_digests[0]
    assert new_sink.events[-1].accepted is True

    assert _run(old_verifier.verify_token(token)) is None
    assert [event.code for event in old_sink.events] == [
        AuthErrorCode.SUBJECT_REFUSED.value,
        AuthErrorCode.SUBJECT_REFUSED.value,
    ]


def test_key_rotation_replaces_generation_and_removes_old_key(
    key_a: rsa.RSAPrivateKey,
    key_b: rsa.RSAPrivateKey,
) -> None:
    policy = _policy("steward")
    generation_a = _jwks(_rsa_jwk(key_a, kid="kid-a"))
    generation_b = _jwks(_rsa_jwk(key_b, kid="kid-b"))
    fetcher = _Fetcher(generation_a, generation_b)
    clock = _Clock()
    verifier, _cache, sink = _verifier(policy, fetcher, clock)
    token_a = _token(key_a, policy, kid="kid-a")
    token_b = _token(key_b, policy, kid="kid-b")

    assert isinstance(_run(verifier.verify_token(token_a)), AccessToken)
    clock.advance(61)
    assert isinstance(_run(verifier.verify_token(token_b)), AccessToken)
    assert _run(verifier.verify_token(token_a)) is None

    assert fetcher.calls == [JWKS_URI, JWKS_URI]
    assert [event.code for event in sink.events] == [
        "accepted",
        "accepted",
        AuthErrorCode.KEY_NOT_FOUND.value,
    ]


def test_expired_cache_outage_refuses_old_and_new_keys_without_stale_trust(
    key_a: rsa.RSAPrivateKey,
    key_b: rsa.RSAPrivateKey,
) -> None:
    policy = _policy("steward")
    fetcher = _Fetcher(
        _jwks(_rsa_jwk(key_a, kid="kid-a")),
        RuntimeError("secret upstream outage"),
    )
    clock = _Clock()
    verifier, _cache, sink = _verifier(policy, fetcher, clock)
    token_a = _token(key_a, policy, kid="kid-a")
    token_b = _token(key_b, policy, kid="kid-b")

    assert isinstance(_run(verifier.verify_token(token_a)), AccessToken)
    clock.advance(61)
    assert _run(verifier.verify_token(token_a)) is None
    assert _run(verifier.verify_token(token_b)) is None

    assert fetcher.calls == [JWKS_URI, JWKS_URI]
    assert [event.code for event in sink.events] == [
        "accepted",
        AuthErrorCode.JWKS_UNAVAILABLE.value,
        AuthErrorCode.JWKS_UNAVAILABLE.value,
    ]
    assert "secret" not in repr(sink.events)


def test_process_restart_refetches_and_retains_no_prior_auth_or_audit_state(
    key_a: rsa.RSAPrivateKey,
) -> None:
    policy = _policy("steward")
    payload = _jwks(_rsa_jwk(key_a, kid="kid-a"))
    token = _token(key_a, policy, kid="kid-a")

    first_fetcher = _Fetcher(payload)
    first_verifier, _first_cache, first_sink = _verifier(
        policy,
        first_fetcher,
        _Clock(),
    )
    assert isinstance(_run(first_verifier.verify_token(token)), AccessToken)

    second_fetcher = _Fetcher(payload)
    second_verifier, _second_cache, second_sink = _verifier(
        policy,
        second_fetcher,
        _Clock(),
    )
    assert second_sink.events == []
    assert isinstance(_run(second_verifier.verify_token(token)), AccessToken)

    assert first_fetcher.calls == [JWKS_URI]
    assert second_fetcher.calls == [JWKS_URI]
    assert first_sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=policy.policy_id,
            code="accepted",
            accepted=True,
        )
    ]
    assert second_sink.events == first_sink.events


@pytest.mark.parametrize("realm", ("steward", "executive", "dialogue"))
def test_all_realms_publish_exact_chatgpt_linking_metadata(realm: str) -> None:
    policy = _policy(realm)

    assert protected_resource_metadata(policy) == {
        "resource": policy.resource,
        "authorization_servers": [ISSUER],
        "scopes_supported": list(policy.required_scopes),
    }
    assert oauth_security_schemes(policy.required_scopes) == [
        {
            "type": "oauth2",
            "scopes": list(policy.required_scopes),
        }
    ]
    bare_challenge = www_authenticate(policy)
    assert bare_challenge == (
        f'Bearer resource_metadata="{policy.resource_metadata_url}"'
    )

    result = mcp_auth_error_result(
        policy,
        AuthError(AuthErrorCode.AUTHORIZATION_MISSING),
        required_scopes=policy.required_scopes,
    )
    assert result["isError"] is True
    challenge = result["_meta"]["mcp/www_authenticate"][0]  # type: ignore[index]
    assert f'resource_metadata="{policy.resource_metadata_url}"' in challenge
    assert f'scope="{" ".join(policy.required_scopes)}"' in challenge
    assert 'error="invalid_token"' in challenge
    assert "error_description=" in challenge
