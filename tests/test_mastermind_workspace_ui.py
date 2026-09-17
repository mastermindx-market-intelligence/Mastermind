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
from integrations.mastermind_workspace_content.ui import UI_PATH, WORKSPACE_HTML

RESOURCE = "https://workspace.example.test/api/conversations/live"
ORIGIN = "https://workspace.example.test"
SOURCE = "managed-window:test-turn"


class Owner:
    async def authorize(self, header: str, resource: str, source_ref: str):
        if header == "Bearer test" and resource == RESOURCE and source_ref == SOURCE:
            return ("policy", "subject", "grant-v1")
        return None

    async def read(self, source_ref: str) -> bytes:
        assert source_ref == SOURCE
        return b"{}"


def policy():
    issuer = "https://identity.example.test/"
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-workspace-content-v1",
            "resource": RESOURCE,
            "resource_metadata_url": "https://workspace.example.test/.well-known/oauth-protected-resource/api/conversations/live",
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


def application():
    accepted = policy()
    resource = WorkspaceContentResource(
        owner=Owner(),
        resource=accepted.resource,
        source_ref=SOURCE,
        allowed_origin=ORIGIN,
    )
    return build_workspace_content_app(resource=resource, policy=accepted)


def test_ui_is_source_free_and_has_no_provider_controls() -> None:
    lower = WORKSPACE_HTML.lower()
    assert "mastermind.workspace.content_read.v1" in WORKSPACE_HTML
    assert "window.mastermindWorkspace" in WORKSPACE_HTML
    assert "function connect(" in WORKSPACE_HTML
    assert SOURCE not in WORKSPACE_HTML
    for forbidden in (
        "send message",
        "resume agent",
        "stop agent",
        "approve result",
        "bearer ",
        "localstorage",
        "sessionstorage",
    ):
        assert forbidden not in lower


def test_ui_route_is_no_store_and_strictly_sandboxed() -> None:
    client = TestClient(application(), base_url=ORIGIN)
    response = client.get(UI_PATH)

    assert response.status_code == 200
    assert response.text == WORKSPACE_HTML
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    csp = response.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "connect-src 'self'" in csp
    assert "form-action 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_ui_script_is_valid_javascript() -> None:
    start = WORKSPACE_HTML.index("<script>") + len("<script>")
    end = WORKSPACE_HTML.index("</script>", start)
    script = WORKSPACE_HTML[start:end]
    # Written for the Node syntax-check subprocess in the verification command.
    assert "eval(" not in script
    assert "innerHTML" not in script
    assert "document.write" not in script
    json.dumps(script)
