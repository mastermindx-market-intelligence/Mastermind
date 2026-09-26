from __future__ import annotations

import json

from starlette.testclient import TestClient

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    load_resource_policy,
    subject_digest,
)
from integrations.mastermind_workspace_content.app import build_workspace_content_app
from integrations.mastermind_workspace_content.business import CONTENT_SCOPE
from integrations.mastermind_workspace_content.resource import WorkspaceContentResource

RESOURCE = "https://workspace.example.test/api/conversations/live"
METADATA = "https://workspace.example.test/.well-known/oauth-protected-resource/api/conversations/live"
ORIGIN = "https://workspace.example.test"
SOURCE = "managed-window:test-turn"


class Owner:
    async def authorize(self, header: str, resource: str, source_ref: str):
        if header == "Bearer test" and resource == RESOURCE and source_ref == SOURCE:
            return ("policy", "subject", "grant-v1")
        return None

    async def read(self, source_ref: str) -> bytes:
        assert source_ref == SOURCE
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


def policy():
    issuer = "https://identity.example.test/"
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-workspace-content-v1",
            "resource": RESOURCE,
            "resource_metadata_url": METADATA,
            "issuer": issuer,
            "authorization_servers": [issuer],
            "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
            "required_scopes": [CONTENT_SCOPE],
            "allowed_subject_digests": [subject_digest(issuer=issuer, subject="chairman")],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def app():
    accepted_policy = policy()
    resource = WorkspaceContentResource(
        owner=Owner(),
        resource=accepted_policy.resource,
        source_ref=SOURCE,
        allowed_origin=ORIGIN,
    )
    return build_workspace_content_app(resource=resource, policy=accepted_policy)


def test_app_mounts_fixed_content_and_metadata_without_mcp_scope_reuse() -> None:
    client = TestClient(app(), base_url=ORIGIN)
    response = client.get(
        "/api/conversations/live",
        headers={"Authorization": "Bearer test", "Origin": ORIGIN},
    )
    metadata = client.get("/.well-known/oauth-protected-resource/api/conversations/live")

    assert response.status_code == 200
    assert response.json()["selection_ref"] == SOURCE
    assert metadata.status_code == 200
    assert metadata.json()["resource"] == RESOURCE
    assert metadata.json()["scopes_supported"] == [CONTENT_SCOPE]


def test_app_refuses_unknown_path_query_and_wrong_method() -> None:
    client = TestClient(app(), base_url=ORIGIN)
    assert client.get("/unknown").status_code == 404
    assert client.get("/api/conversations/live?source=other").status_code == 404
    assert client.post("/api/conversations/live").status_code == 405


def test_health_and_readiness_do_not_claim_source_or_provider_health() -> None:
    client = TestClient(app(), base_url=ORIGIN)
    health = client.get("/healthz")
    ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "service": "mastermind-workspace-content",
        "mode": "authenticated-readonly",
    }
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
