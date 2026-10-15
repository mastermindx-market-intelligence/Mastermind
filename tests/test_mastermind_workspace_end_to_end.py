from __future__ import annotations

import base64
import json
from collections.abc import Mapping

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from control_plane.visible_turn_projection import TurnKey, VisibleTurnProjection
from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthAuditEvent,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_workspace_content.app import build_workspace_content_app
from integrations.mastermind_workspace_content.business import (
    CONTENT_SCOPE,
    build_business_workspace_content_resource,
)
from integrations.mastermind_workspace_content.live_window import ContentDecision
from integrations.mastermind_workspace_content.projection_source import ManagedTurnWindowSource

RESOURCE = "https://workspace.example.test/api/conversations/live"
ORIGIN = "https://workspace.example.test"
SOURCE_REF = "managed-window:test-turn"
ISSUER = "https://identity.example.test/"
SUBJECT = "chairman-opaque"
NOW = 1_788_000_100
KEY = TurnKey(
    attempt_id="attempt-1",
    session_epoch_id="epoch-1",
    process_generation_id="generation-1",
    generation_number=1,
    worker_id="worker-1",
    local_turn_id="local-1",
    native_turn_id="native-1",
)


class Fetcher:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def fetch(self, *, url: str, timeout_seconds: float, max_bytes: int) -> bytes:
        assert url == "https://identity.example.test/.well-known/jwks.json"
        assert timeout_seconds > 0 and max_bytes > len(self.payload)
        return self.payload


class Sink:
    def __init__(self) -> None:
        self.events: list[AuthAuditEvent] = []

    def emit(self, event: AuthAuditEvent) -> None:
        self.events.append(event)


def b64uint(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode()


def jwk(private_key: rsa.RSAPrivateKey) -> Mapping[str, object]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kid": "kid-a",
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": b64uint(numbers.n),
        "e": b64uint(numbers.e),
    }


def accepted_policy():
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-workspace-content-v1",
            "resource": RESOURCE,
            "resource_metadata_url": "https://workspace.example.test/.well-known/oauth-protected-resource/api/conversations/live",
            "issuer": ISSUER,
            "authorization_servers": [ISSUER],
            "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
            "required_scopes": [CONTENT_SCOPE],
            "allowed_subject_digests": [subject_digest(issuer=ISSUER, subject=SUBJECT)],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def token(private_key: rsa.RSAPrivateKey, policy) -> str:
    return jwt.encode(
        {
            "iss": policy.issuer,
            "sub": SUBJECT,
            "aud": policy.resource,
            "iat": NOW - 100,
            "nbf": NOW - 100,
            "exp": NOW + 500,
            "scope": CONTENT_SCOPE,
            "client_id": "workspace-test-client",
            "jti": "workspace-test-token",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "kid-a", "typ": "at+jwt"},
    )


def publish(projection: VisibleTurnProjection, text: str, *, completed: bool = False) -> None:
    projection.publish(
        KEY,
        method="item/completed" if completed else "item/updated",
        params={
            "item": {
                "type": "agentMessage",
                "id": "message-a",
                "sequence": 1,
                "text": text,
            }
        },
        native_turn_id=KEY.native_turn_id,
    )


def test_projection_to_authenticated_app_preserves_updates_and_revocation() -> None:
    projection = VisibleTurnProjection()
    reader_grant = projection.mint_grant(KEY)
    source = ManagedTurnWindowSource(
        projection=projection,
        key=KEY,
        reader_grant=reader_grant,
        source_ref=SOURCE_REF,
        classify=lambda item: ContentDecision("visible-response", item.text, "VISIBLE_TEXT"),
        observed_at=lambda: "2026-09-16T22:00:00+00:00",
        page_size=1,
        max_pages=8,
    )
    policy = accepted_policy()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cache = BoundedJwksCache(
        policy=policy,
        fetcher=Fetcher(json.dumps({"keys": [jwk(private_key)]}, separators=(",", ":")).encode()),
        monotonic=lambda: 100.0,
    )
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=cache)
    sink = Sink()

    async def current_access(_principal, source_ref):
        if source_ref == SOURCE_REF and source.is_current():
            return ("turn-key-digest", "grant-generation-1")
        return None

    resource = build_business_workspace_content_resource(
        authenticator=authenticator,
        policy=policy,
        current_access=current_access,
        read_source=source.read,
        source_ref=SOURCE_REF,
        now=lambda: NOW,
        allowed_origin=ORIGIN,
        audit_sink=sink,
    )
    app = build_workspace_content_app(resource=resource, policy=policy)
    client = TestClient(app, base_url=ORIGIN)
    headers = {"Authorization": f"Bearer {token(private_key, policy)}", "Origin": ORIGIN}

    publish(projection, "Draft")
    first = client.get("/api/conversations/live", headers=headers)
    publish(projection, "Corrected final", completed=True)
    final = client.get("/api/conversations/live", headers=headers)

    assert first.status_code == 200 and final.status_code == 200
    first_item = first.json()["view"]["items"][0]
    final_item = final.json()["view"]["items"][0]
    assert first_item["id"] == final_item["id"]
    assert first_item["text"] == "Draft"
    assert final_item["text"] == "Corrected final"
    assert final_item["state"] == "completed"

    projection.revoke_grant(reader_grant)
    revoked = client.get("/api/conversations/live", headers=headers)
    assert revoked.status_code == 401
    assert revoked.json() == {"error": "authentication_required"}
    assert sink.events[-1].accepted is False
