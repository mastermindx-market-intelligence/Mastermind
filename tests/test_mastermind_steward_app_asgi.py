from __future__ import annotations

from mcp.server.auth.provider import TokenVerifier
from starlette.testclient import TestClient

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    load_resource_policy,
    subject_digest,
)
from integrations.mastermind_secretary_mcp.adapter import StewardGrounding
from integrations.mastermind_steward_app.app import build_authenticated_app
from integrations.mastermind_steward_app.server import (
    REQUIRED_SCOPE,
    build_contract_server,
)


class _DenyVerifier(TokenVerifier):
    async def verify_token(self, token: str):
        del token
        return None


class _Port:
    async def _empty(self):
        return StewardGrounding(
            state="UNKNOWN",
            facts=(),
            reason_codes=("NO_SOURCE",),
        )

    async def list_responsibilities(self):
        return await self._empty()

    async def get_responsibility(self, responsibility_ref: str):
        del responsibility_ref
        return await self._empty()

    async def get_attention(self):
        return await self._empty()

    async def get_current_runtime(self, responsibility_ref: str):
        del responsibility_ref
        return await self._empty()

    async def explain_blocker(self, responsibility_ref: str):
        del responsibility_ref
        return await self._empty()

    async def resolve_surface(self, responsibility_ref: str):
        del responsibility_ref
        return await self._empty()


def _policy(*, scopes=(REQUIRED_SCOPE,)):
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
            "required_scopes": list(scopes),
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


def test_authenticated_app_exposes_public_metadata_and_requires_bearer_for_mcp():
    policy = _policy()
    app = build_authenticated_app(
        build_contract_server(_Port()),
        policy=policy,
        token_verifier=_DenyVerifier(),
    )
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["mode"] == "authenticated-readonly"

        metadata = client.get(
            "/.well-known/oauth-protected-resource/mcp/steward/v1"
        )
        assert metadata.status_code == 200
        assert metadata.json()["resource"] == policy.resource
        assert metadata.json()["scopes_supported"] == [REQUIRED_SCOPE]

        refused = client.post(
            "/mcp/steward/v1",
            headers={"content-type": "application/json"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        assert refused.status_code == 401
        assert refused.history == []
        assert refused.json()["error"] == "invalid_token"
        challenge = refused.headers["www-authenticate"]
        assert "resource_metadata=" in challenge

        sibling = client.post(
            "/mcp/steward/not-the-resource",
            headers={"content-type": "application/json"},
            json={"jsonrpc": "2.0", "id": 2, "method": "initialize"},
        )
        assert sibling.status_code == 404


def test_authenticated_app_refuses_cross_realm_scope_policy():
    policy = _policy(scopes=("mastermind.executive.read",))
    try:
        build_authenticated_app(
            build_contract_server(_Port()),
            policy=policy,
            token_verifier=_DenyVerifier(),
        )
    except ValueError as exc:
        assert "exactly mastermind.steward.read" in str(exc)
    else:
        raise AssertionError("cross-realm policy was accepted")
