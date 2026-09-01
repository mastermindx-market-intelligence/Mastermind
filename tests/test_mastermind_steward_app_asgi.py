from __future__ import annotations

import time

import pytest
from mcp.server.auth.provider import AccessToken, TokenVerifier
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


MCP_PATH = "/mcp/steward/v1"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp/steward/v1"
BASE_URL = "https://mcp.example.test"
MCP_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "mastermind-test", "version": "1.0"},
    },
}
MCP_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}


class _Verifier(TokenVerifier):
    def __init__(self, result: AccessToken | None = None) -> None:
        self.result = result
        self.calls: list[str] = []

    async def verify_token(self, token: str):
        self.calls.append(token)
        return self.result


class _Port:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def _empty(self, method: str, responsibility_ref: str | None = None):
        self.calls.append((method, responsibility_ref))
        return StewardGrounding(
            state="UNKNOWN",
            facts=(),
            reason_codes=("NO_SOURCE",),
        )

    async def list_responsibilities(self):
        return await self._empty("list_responsibilities")

    async def get_responsibility(self, responsibility_ref: str):
        return await self._empty("get_responsibility", responsibility_ref)

    async def get_attention(self):
        return await self._empty("get_attention")

    async def get_current_runtime(self, responsibility_ref: str):
        return await self._empty("get_current_runtime", responsibility_ref)

    async def explain_blocker(self, responsibility_ref: str):
        return await self._empty("explain_blocker", responsibility_ref)

    async def resolve_surface(self, responsibility_ref: str):
        return await self._empty("resolve_surface", responsibility_ref)


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


def _access_token(
    policy,
    *,
    token: str = "valid-token",
    scopes: tuple[str, ...] = (REQUIRED_SCOPE,),
) -> AccessToken:
    return AccessToken(
        token=token,
        client_id="1" * 64,
        scopes=list(scopes),
        expires_at=int(time.time()) + 3600,
        resource=policy.resource,
        subject="2" * 64,
        claims={
            "issuer_digest": "3" * 64,
            "client_ref": "1" * 64,
            "jti_digest": None,
        },
    )


def _build(*, verifier: _Verifier | None = None):
    policy = _policy()
    selected_verifier = verifier or _Verifier()
    port = _Port()
    app = build_authenticated_app(
        build_contract_server(port),
        policy=policy,
        token_verifier=selected_verifier,
    )
    return app, policy, selected_verifier, port


def _challenge(response) -> str:
    return response.headers["www-authenticate"]


def test_authenticated_app_exposes_metadata_and_readiness_tracks_lifespan():
    app, policy, verifier, port = _build()
    client = TestClient(app, base_url=BASE_URL)

    # Construction or process reachability is not manager readiness.
    not_started = client.get("/readyz")
    assert not_started.status_code == 503
    assert not_started.json() == {
        "status": "not_ready",
        "service": "mastermind-steward",
        "mode": "authenticated-readonly",
    }

    with client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["mode"] == "authenticated-readonly"

        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        metadata = client.get(METADATA_PATH)
        assert metadata.status_code == 200
        assert metadata.json()["resource"] == policy.resource
        assert metadata.json()["scopes_supported"] == [REQUIRED_SCOPE]

    stopped = client.get("/readyz")
    assert stopped.status_code == 503
    assert verifier.calls == []
    assert port.calls == []


def test_canonical_mcp_path_uses_a1_missing_and_invalid_token_challenges():
    app, policy, verifier, port = _build()
    with TestClient(app, base_url=BASE_URL) as client:
        missing = client.post(MCP_PATH, headers=MCP_HEADERS, json=MCP_BODY)
        assert missing.status_code == 401
        assert missing.history == []
        assert missing.json() == {"error": "invalid_token"}
        missing_challenge = _challenge(missing)
        assert (
            f'resource_metadata="{policy.resource_metadata_url}"'
            in missing_challenge
        )
        assert f'scope="{REQUIRED_SCOPE}"' in missing_challenge
        assert 'error="invalid_token"' in missing_challenge
        assert "no valid access token" in missing_challenge

        invalid = client.post(
            MCP_PATH,
            headers={**MCP_HEADERS, "authorization": "Bearer invalid-token"},
            json=MCP_BODY,
        )
        assert invalid.status_code == 401
        assert invalid.history == []
        assert invalid.json() == {"error": "invalid_token"}
        invalid_challenge = _challenge(invalid)
        assert f'scope="{REQUIRED_SCOPE}"' in invalid_challenge
        assert 'error="invalid_token"' in invalid_challenge
        assert "invalid or no longer usable" in invalid_challenge
        assert "invalid-token" not in invalid.text
        assert "invalid-token" not in invalid_challenge

    assert verifier.calls == ["invalid-token"]
    assert port.calls == []


def test_valid_bearer_is_required_scope_bound_and_request_auth_does_not_leak():
    policy = _policy()
    verifier = _Verifier(_access_token(policy))
    port = _Port()
    app = build_authenticated_app(
        build_contract_server(port),
        policy=policy,
        token_verifier=verifier,
    )

    with TestClient(app, base_url=BASE_URL) as client:
        accepted = client.post(
            MCP_PATH,
            headers={**MCP_HEADERS, "authorization": "Bearer valid-token"},
            json=MCP_BODY,
        )
        assert accepted.status_code == 200
        assert accepted.history == []
        assert accepted.json()["result"]["protocolVersion"] == "2025-06-18"

        # A later request in the same TestClient must not inherit prior auth.
        missing = client.post(MCP_PATH, headers=MCP_HEADERS, json=MCP_BODY)
        assert missing.status_code == 401
        assert missing.json() == {"error": "invalid_token"}

    assert verifier.calls == ["valid-token"]
    assert port.calls == []


def test_valid_token_without_steward_scope_gets_a1_insufficient_scope_challenge():
    policy = _policy()
    verifier = _Verifier(
        _access_token(
            policy,
            token="wrong-scope-token",
            scopes=("mastermind.executive.read",),
        )
    )
    port = _Port()
    app = build_authenticated_app(
        build_contract_server(port),
        policy=policy,
        token_verifier=verifier,
    )

    with TestClient(app, base_url=BASE_URL) as client:
        refused = client.post(
            MCP_PATH,
            headers={
                **MCP_HEADERS,
                "authorization": "Bearer wrong-scope-token",
            },
            json=MCP_BODY,
        )

    assert refused.status_code == 403
    assert refused.history == []
    assert refused.json() == {"error": "insufficient_scope"}
    challenge = _challenge(refused)
    assert f'scope="{REQUIRED_SCOPE}"' in challenge
    assert 'error="insufficient_scope"' in challenge
    assert "does not include the required scope" in challenge
    assert "wrong-scope-token" not in refused.text
    assert "wrong-scope-token" not in challenge
    assert verifier.calls == ["wrong-scope-token"]
    assert port.calls == []


@pytest.mark.parametrize(
    ("method", "path", "headers", "body", "expected_status"),
    [
        ("GET", MCP_PATH, MCP_HEADERS, b"", 405),
        ("HEAD", MCP_PATH, MCP_HEADERS, b"", 405),
        ("OPTIONS", MCP_PATH, MCP_HEADERS, b"", 405),
        ("POST", MCP_PATH + "/", MCP_HEADERS, b"{}", 404),
        ("POST", "/mcp//steward/v1", MCP_HEADERS, b"{}", 404),
        ("POST", "/%6dcp/steward/v1", MCP_HEADERS, b"{}", 404),
        ("POST", MCP_PATH + "?next=https://attacker.test", MCP_HEADERS, b"{}", 404),
        ("POST", "/oauth/callback", MCP_HEADERS, b"{}", 404),
        (
            "POST",
            MCP_PATH,
            {"accept": "application/json", "content-type": "text/plain"},
            b"{}",
            415,
        ),
    ],
)
def test_transport_alias_method_and_content_type_refuse_before_authentication(
    method, path, headers, body, expected_status
):
    policy = _policy()
    verifier = _Verifier(_access_token(policy, token="must-not-be-read"))
    port = _Port()
    app = build_authenticated_app(
        build_contract_server(port),
        policy=policy,
        token_verifier=verifier,
    )
    request_headers = list(headers.items()) + [
        ("authorization", "Bearer must-not-be-read")
    ]

    with TestClient(app, base_url=BASE_URL) as client:
        response = client.request(
            method,
            path,
            headers=request_headers,
            content=body,
        )

    assert response.status_code == expected_status
    assert response.history == []
    assert verifier.calls == []
    assert port.calls == []
    assert "must-not-be-read" not in response.text


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        (
            [
                ("host", "attacker.test"),
                ("origin", "https://chatgpt.com"),
            ],
            421,
        ),
        (
            [
                ("host", "mcp.example.test"),
                ("origin", "https://attacker.test"),
            ],
            403,
        ),
        (
            [
                ("host", "mcp.example.test"),
                ("origin", "https://chatgpt.com"),
                ("origin", "https://chatgpt.com"),
            ],
            400,
        ),
        (
            [
                ("host", "mcp.example.test"),
                ("host", "mcp.example.test"),
                ("origin", "https://chatgpt.com"),
            ],
            400,
        ),
        (
            [
                ("host", "mcp.example.test"),
                ("origin", "https://chatgpt.com"),
                ("authorization", "Bearer one"),
                ("authorization", "Bearer two"),
            ],
            400,
        ),
    ],
)
def test_host_origin_and_duplicate_security_headers_refuse_before_verifier(
    headers, expected_status
):
    policy = _policy()
    verifier = _Verifier(_access_token(policy, token="must-not-be-read"))
    port = _Port()
    app = build_authenticated_app(
        build_contract_server(port),
        policy=policy,
        token_verifier=verifier,
    )
    request_headers = [
        ("accept", "application/json, text/event-stream"),
        ("content-type", "application/json"),
        *headers,
    ]
    if not any(name.lower() == "authorization" for name, _value in headers):
        request_headers.append(("authorization", "Bearer must-not-be-read"))

    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            MCP_PATH,
            headers=request_headers,
            content=b"{}",
        )

    assert response.status_code == expected_status
    assert response.history == []
    assert verifier.calls == []
    assert port.calls == []
    assert "attacker.test" not in response.text
    assert "must-not-be-read" not in response.text


def test_oversized_body_and_root_path_injection_refuse_before_verifier():
    policy = _policy()
    verifier = _Verifier(_access_token(policy, token="must-not-be-read"))
    port = _Port()
    app = build_authenticated_app(
        build_contract_server(port),
        policy=policy,
        token_verifier=verifier,
    )
    headers = {
        **MCP_HEADERS,
        "authorization": "Bearer must-not-be-read",
    }

    with TestClient(app, base_url=BASE_URL) as client:
        oversized = client.post(
            MCP_PATH,
            headers=headers,
            content=b"x" * (1024 * 1024 + 1),
        )
    with TestClient(
        app,
        base_url=BASE_URL,
        root_path="/injected-prefix",
    ) as client:
        injected = client.post(MCP_PATH, headers=headers, json=MCP_BODY)

    assert oversized.status_code == 413
    assert injected.status_code == 404
    assert verifier.calls == []
    assert port.calls == []


def test_authenticated_app_refuses_cross_realm_scope_policy():
    policy = _policy(scopes=("mastermind.executive.read",))
    try:
        build_authenticated_app(
            build_contract_server(_Port()),
            policy=policy,
            token_verifier=_Verifier(),
        )
    except ValueError as exc:
        assert "exactly mastermind.steward.read" in str(exc)
    else:
        raise AssertionError("cross-realm policy was accepted")
