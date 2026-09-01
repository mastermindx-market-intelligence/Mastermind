from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Callable

import pytest
from mcp.server.auth.provider import AccessToken

from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AUTH_POLICY_SCHEMA,
    AuthAuditEvent,
    AuthError,
    AuthErrorCode,
    VerifiedPrincipal,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier


NOW = 1_788_000_100
RAW_TOKEN = "raw-bearer-token-must-not-enter-audit"
RAW_SUBJECT = "chairman-opaque"
RAW_CLIENT_ID = "chatgpt-business-client"


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
                subject_digest(issuer=issuer, subject=RAW_SUBJECT)
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _principal(**overrides: object) -> VerifiedPrincipal:
    policy = _policy()
    value = VerifiedPrincipal(
        policy_id=policy.policy_id,
        issuer=policy.issuer,
        issuer_digest="1" * 64,
        resource=policy.resource,
        subject_digest=policy.allowed_subject_digests[0],
        client_ref="2" * 64,
        scopes=policy.required_scopes,
        issued_at=1_788_000_000,
        expires_at=1_788_000_600,
        jti_digest="3" * 64,
    )
    return dataclasses.replace(value, **overrides)


class _Authenticator:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[object, int]] = []

    async def verify_token(self, token: object, *, now: int) -> VerifiedPrincipal:
        self.calls.append((token, now))
        await asyncio.sleep(0)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result  # type: ignore[return-value]


class _Sink:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[AuthAuditEvent] = []

    def emit(self, event: AuthAuditEvent) -> None:
        if self.fail:
            raise RuntimeError("secret audit transport detail")
        self.events.append(event)


def _run(coroutine):
    return asyncio.run(coroutine)


def _verifier(
    result: object,
    *,
    now: Callable[[], object] = lambda: NOW,
    sink: _Sink | None = None,
):
    authenticator = _Authenticator(result)
    audit_sink = sink or _Sink()
    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=_policy(),
        now=now,
        audit_sink=audit_sink,
    )
    return verifier, authenticator, audit_sink


def test_accepted_principal_maps_exactly_to_mcp_access_token() -> None:
    principal = _principal()
    verifier, authenticator, sink = _verifier(principal)

    access = _run(verifier.verify_token(RAW_TOKEN))

    assert isinstance(access, AccessToken)
    assert access.model_dump() == {
        "token": RAW_TOKEN,
        "client_id": principal.client_ref,
        "scopes": list(principal.scopes),
        "expires_at": principal.expires_at,
        "resource": principal.resource,
        "subject": principal.subject_digest,
        "claims": {
            "issuer_digest": principal.issuer_digest,
            "client_ref": principal.client_ref,
            "jti_digest": principal.jti_digest,
        },
    }
    assert authenticator.calls == [(RAW_TOKEN, NOW)]
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=_policy().policy_id,
            code="accepted",
            accepted=True,
        )
    ]


def test_absent_jti_remains_explicit_null_in_closed_claims() -> None:
    verifier, _authenticator, _sink = _verifier(_principal(jti_digest=None))

    access = _run(verifier.verify_token(RAW_TOKEN))

    assert isinstance(access, AccessToken)
    assert access.claims == {
        "issuer_digest": "1" * 64,
        "client_ref": "2" * 64,
        "jti_digest": None,
    }


@pytest.mark.parametrize(
    "code",
    [
        AuthErrorCode.AUTHORIZATION_MISSING,
        AuthErrorCode.TOKEN_SIGNATURE_REFUSED,
        AuthErrorCode.JWKS_UNAVAILABLE,
        AuthErrorCode.SCOPE_REFUSED,
        AuthErrorCode.SUBJECT_REFUSED,
    ],
)
def test_typed_auth_refusal_returns_none_and_emits_one_redacted_event(
    code: AuthErrorCode,
) -> None:
    verifier, authenticator, sink = _verifier(AuthError(code))

    access = _run(verifier.verify_token(RAW_TOKEN))

    assert access is None
    assert authenticator.calls == [(RAW_TOKEN, NOW)]
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=_policy().policy_id,
            code=code.value,
            accepted=False,
        )
    ]


def test_unexpected_authenticator_failure_is_closed_as_internal_error() -> None:
    verifier, authenticator, sink = _verifier(
        RuntimeError("secret provider exception")
    )

    assert _run(verifier.verify_token(RAW_TOKEN)) is None
    assert authenticator.calls == [(RAW_TOKEN, NOW)]
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=_policy().policy_id,
            code=AuthErrorCode.INTERNAL_ERROR.value,
            accepted=False,
        )
    ]


@pytest.mark.parametrize("bad_now", [True, 1.5, "1788000100", None])
def test_invalid_clock_value_fails_before_authentication(bad_now: object) -> None:
    verifier, authenticator, sink = _verifier(
        _principal(), now=lambda: bad_now
    )

    assert _run(verifier.verify_token(RAW_TOKEN)) is None
    assert authenticator.calls == []
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=_policy().policy_id,
            code=AuthErrorCode.INTERNAL_ERROR.value,
            accepted=False,
        )
    ]


def test_clock_exception_is_closed_without_authentication() -> None:
    def broken_clock() -> int:
        raise RuntimeError("secret clock detail")

    verifier, authenticator, sink = _verifier(
        _principal(), now=broken_clock
    )

    assert _run(verifier.verify_token(RAW_TOKEN)) is None
    assert authenticator.calls == []
    assert sink.events[0].code == AuthErrorCode.INTERNAL_ERROR.value


@pytest.mark.parametrize(
    "principal",
    [
        _principal(policy_id="other-policy"),
        _principal(issuer="https://other.example.test/"),
        _principal(resource="https://mcp.example.test/mcp/other/v1"),
        _principal(scopes=("mastermind.executive.read",)),
        object(),
    ],
)
def test_mismatched_or_untyped_principal_fails_closed(principal: object) -> None:
    verifier, authenticator, sink = _verifier(principal)

    assert _run(verifier.verify_token(RAW_TOKEN)) is None
    assert authenticator.calls == [(RAW_TOKEN, NOW)]
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=_policy().policy_id,
            code=AuthErrorCode.INTERNAL_ERROR.value,
            accepted=False,
        )
    ]


def test_accepted_audit_failure_prevents_token_escape() -> None:
    sink = _Sink(fail=True)
    verifier, authenticator, _sink = _verifier(_principal(), sink=sink)

    assert _run(verifier.verify_token(RAW_TOKEN)) is None
    assert authenticator.calls == [(RAW_TOKEN, NOW)]
    assert sink.events == []


def test_refusal_audit_failure_still_returns_none_without_exception() -> None:
    sink = _Sink(fail=True)
    verifier, authenticator, _sink = _verifier(
        AuthError(AuthErrorCode.SCOPE_REFUSED), sink=sink
    )

    assert _run(verifier.verify_token(RAW_TOKEN)) is None
    assert authenticator.calls == [(RAW_TOKEN, NOW)]
    assert sink.events == []


def test_audit_event_has_exact_closed_secret_free_shape() -> None:
    verifier, _authenticator, sink = _verifier(_principal())
    assert _run(verifier.verify_token(RAW_TOKEN)) is not None

    rendered = json.dumps(dataclasses.asdict(sink.events[0]), sort_keys=True)
    assert set(dataclasses.asdict(sink.events[0])) == {
        "schema",
        "policy_id",
        "code",
        "accepted",
    }
    for forbidden in (RAW_TOKEN, RAW_SUBJECT, RAW_CLIENT_ID, "secret"):
        assert forbidden not in rendered
        assert forbidden not in repr(sink.events[0])


def test_adapter_invokes_authenticator_exactly_once() -> None:
    verifier, authenticator, _sink = _verifier(_principal())

    assert _run(verifier.verify_token(RAW_TOKEN)) is not None
    assert authenticator.calls == [(RAW_TOKEN, NOW)]
