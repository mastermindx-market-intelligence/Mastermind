from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthAuditEvent,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_workspace_content.business import (
    CONTENT_SCOPE,
    build_business_workspace_content_resource,
)

RESOURCE = "https://workspace.example.test/api/conversations/live"
ORIGIN = "https://workspace.example.test"
ISSUER = "https://identity.example.test/"
JWKS_URI = "https://identity.example.test/.well-known/jwks.json"
SOURCE = "managed-window:test-turn"
SUBJECT = "chairman-opaque"
NOW = 1_788_000_100
ISSUED_AT = 1_788_000_000
EXPIRES_AT = 1_788_000_600


class Fetcher:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def fetch(self, *, url: str, timeout_seconds: float, max_bytes: int) -> bytes:
        assert url == JWKS_URI
        assert timeout_seconds > 0
        assert max_bytes > len(self.payload)
        return self.payload


class Sink:
    def __init__(self, *, fail: bool = False) -> None:
        self.events: list[AuthAuditEvent] = []
        self.fail = fail

    def emit(self, event: AuthAuditEvent) -> None:
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append(event)


def b64uint(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode("ascii")


def jwk(private_key: rsa.RSAPrivateKey, *, kid: str = "kid-a") -> Mapping[str, object]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kid": kid,
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": b64uint(numbers.n),
        "e": b64uint(numbers.e),
    }


def policy(*, scopes=(CONTENT_SCOPE,)):
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-workspace-content-v1",
            "resource": RESOURCE,
            "resource_metadata_url": "https://workspace.example.test/.well-known/oauth-protected-resource/api/conversations/live",
            "issuer": ISSUER,
            "authorization_servers": [ISSUER],
            "jwks_uri": JWKS_URI,
            "required_scopes": list(scopes),
            "allowed_subject_digests": [subject_digest(issuer=ISSUER, subject=SUBJECT)],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def token(private_key: rsa.RSAPrivateKey, accepted_policy, *, scopes=None) -> str:
    claims = {
        "iss": accepted_policy.issuer,
        "sub": SUBJECT,
        "aud": accepted_policy.resource,
        "iat": ISSUED_AT,
        "nbf": ISSUED_AT,
        "exp": EXPIRES_AT,
        "scope": " ".join(scopes or accepted_policy.required_scopes),
        "client_id": "workspace-test-client",
        "jti": "workspace-test-token",
    }
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "kid-a", "typ": "at+jwt"},
    )


def payload() -> bytes:
    return json.dumps(
        {
            "schema": "mastermind.workspace.visible_window.v1",
            "source_ref": SOURCE,
            "scope": "one-managed-turn-window",
            "observed_at": "2026-09-16T22:00:00+00:00",
            "epoch": "0" * 64,
            "terminal": False,
            "coverage": "OBSERVED_WINDOW",
            "history": "NOT_PROVEN",
            "acceptance": "NOT_PROJECTED",
            "capabilities": {"send": False, "provider_control": False, "history": False},
            "items": [],
            "gaps": [],
        },
        separators=(",", ":"),
    ).encode()


async def request(app, bearer: str):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/api/conversations/live",
            "raw_path": b"/api/conversations/live",
            "root_path": "",
            "query_string": b"",
            "headers": [
                (b"host", b"workspace.example.test"),
                (b"origin", ORIGIN.encode()),
                (b"authorization", f"Bearer {bearer}".encode()),
            ],
        },
        receive,
        send,
    )
    body = b"".join(message.get("body", b"") for message in sent[1:])
    return sent[0]["status"], json.loads(body)


def build(*, sink: Sink | None = None, scopes=(CONTENT_SCOPE,), now_func=None):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    accepted_policy = policy(scopes=scopes)
    fetcher = Fetcher(json.dumps({"keys": [jwk(private_key)]}, separators=(",", ":")).encode())
    cache = BoundedJwksCache(policy=accepted_policy, fetcher=fetcher, monotonic=lambda: 100.0)
    authenticator = JwtAuthenticator(policy=accepted_policy, jwks_cache=cache)
    audit = sink or Sink()
    access_calls = []

    async def current_access(principal, source_ref):
        access_calls.append((principal.subject_digest, source_ref))
        return ("turn-key-digest", "grant-generation-1")

    async def read_source():
        return payload()

    app = build_business_workspace_content_resource(
        authenticator=authenticator,
        policy=accepted_policy,
        current_access=current_access,
        read_source=read_source,
        source_ref=SOURCE,
        now=now_func or (lambda: NOW),
        allowed_origin=ORIGIN,
        audit_sink=audit,
    )
    return app, accepted_policy, private_key, audit, access_calls


def test_real_signed_content_scope_reads_fixed_source() -> None:
    app, accepted_policy, private_key, audit, access_calls = build()
    status, body = asyncio.run(request(app, token(private_key, accepted_policy)))

    assert status == 200
    assert body["selection_ref"] == SOURCE
    assert len(access_calls) == 2
    assert [event.accepted for event in audit.events] == [True, True]


def test_wrong_scope_token_is_refused_before_source_access() -> None:
    app, accepted_policy, private_key, audit, access_calls = build()
    status, body = asyncio.run(
        request(app, token(private_key, accepted_policy, scopes=("mastermind.steward.read",)))
    )

    assert status == 401
    assert body == {"error": "authentication_required"}
    assert access_calls == []
    assert audit.events and audit.events[-1].accepted is False


def test_failed_closed_audit_prevents_content_release() -> None:
    sink = Sink(fail=True)
    app, accepted_policy, private_key, _audit, access_calls = build(sink=sink)
    status, body = asyncio.run(request(app, token(private_key, accepted_policy)))

    assert status == 401
    assert body == {"error": "authentication_required"}
    assert len(access_calls) == 1


def test_token_expiry_between_source_read_and_final_authorization_refuses_release() -> None:
    values = iter((NOW, NOW, EXPIRES_AT + 31))
    app, accepted_policy, private_key, audit, access_calls = build(
        now_func=lambda: next(values)
    )

    status, body = asyncio.run(request(app, token(private_key, accepted_policy)))

    assert status == 403
    assert body == {"error": "access_changed"}
    assert len(access_calls) == 1
    assert audit.events[-1].accepted is False
