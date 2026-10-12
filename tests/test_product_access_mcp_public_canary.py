"""Opt-in real-public-endpoint MCP canary with disposable signed credentials.

This is not real product-user authentication, registration, installation,
a protected page/browser, a production grant or a release qualification.
Set MMX_PRODUCT_PUBLIC_CANARY=1 to run one bounded live observation.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from common.bounded_sync_executor import BoundedSyncExecutor
from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.product_access_mcp.app import create_authenticated_product_server
from integrations.product_access_mcp.contracts import (
    ProductCaller, ProductRefused, READ_SCOPE,
)
from integrations.product_access_mcp.runtime import PublicProductReadPort


class Keys:
    def __init__(self, jwk):
        self.jwk = jwk

    async def key_for(self, kid):
        if kid != "public-canary":
            raise ValueError("unknown fixture key")
        return self.jwk


class Audit:
    def __init__(self):
        self.rows = []

    def emit(self, event):
        self.rows.append(dataclasses.asdict(event))


@pytest.mark.skipif(
    os.environ.get("MMX_PRODUCT_PUBLIC_CANARY") != "1",
    reason="opt-in real public network observation; no normal CI network",
)
def test_native_signed_mcp_to_real_macro_and_terminal_public_sources():
    asyncio.run(_run())


async def _run():
    issuer = "https://fixture.product-canary.example"
    resource = "https://fixture-product-canary.example/mcp"
    sub = "canary-user"
    digest = subject_digest(issuer=issuer, subject=sub)
    current = int(time.time())
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="public-canary", alg="RS256", use="sig")
    policy = load_resource_policy({
        "schema": "mastermind.business_mcp_auth_policy.v1",
        "policy_id": "fixture.public.product.canary",
        "issuer": issuer,
        "resource": resource,
        "resource_metadata_url": (
            "https://fixture-product-canary.example/.well-known/oauth-protected-resource/mcp"
        ),
        "authorization_servers": [issuer],
        "jwks_uri": issuer + "/jwks",
        "required_scopes": [READ_SCOPE],
        "allowed_subject_digests": [digest],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 0,
        "max_token_lifetime_seconds": 600,
        "jwks_cache_ttl_seconds": 60,
        "unknown_kid_refresh_cooldown_seconds": 1,
        "fetch_failure_backoff_seconds": 1,
    })
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=Keys(jwk))
    # The ONLY permitted fixture grant is this signed identity reading these
    # already-public sources. It cannot authorize real product-user data.
    def public_fixture_grant(caller: ProductCaller, request):
        if (caller.subject_digest != digest or caller.resource != resource or
            caller.scopes != (READ_SCOPE,) or caller.expires_at <= int(time.time())):
            raise ProductRefused("PRODUCT_GRANT_CHANGED")
        original = (caller, tuple(sorted(request.items())))
        def check():
            if original != (caller, tuple(sorted(request.items()))) or (
                caller.expires_at <= int(time.time())
            ):
                raise ProductRefused("PRODUCT_GRANT_CHANGED")
        return check

    executor = BoundedSyncExecutor(max_concurrency=1)
    port = PublicProductReadPort(
        executor=executor, clock=lambda: __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc),
        timeout=9,
    )
    audit = Audit()
    server = create_authenticated_product_server(
        authenticator=authenticator, policy=policy, now=lambda: int(time.time()),
        audit_sink=audit, read_port=port,
        final_authorization=public_fixture_grant,
        allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
    )
    app = server.streamable_http_app()
    token = jwt.encode({
        "iss": issuer, "sub": sub, "aud": resource,
        "iat": current - 1, "exp": current + 300, "scope": READ_SCOPE,
        "client_id": "public-canary-client",
    }, pem, algorithm="RS256", headers={"kid": "public-canary"})
    observations = []
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as client:
                for product, view, expected in (
                    ("macro", "status", "macro.public_status"),
                    ("terminal", "market_risk", "terminal.public_risk_projection"),
                ):
                    response = await client.post("/mcp", headers={
                        "Authorization": "Bearer " + token,
                        "Accept": "application/json, text/event-stream",
                        "MCP-Protocol-Version": "2025-03-26",
                    }, json={
                        "jsonrpc": "2.0", "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "product_observe",
                            "arguments": {"product": product, "view": view},
                        },
                    })
                    assert response.status_code == 200
                    result = response.json()["result"]["structuredContent"]
                    assert result["source"]["source_id"] == expected
                    assert result["source"]["http_status"] >= 100
                    assert result["source"]["body_sha256"]
                    assert result["caller"]["subject_digest"] == digest
                    assert result["status"] in (
                        "OK", "PARTIAL", "STALE", "INVALID", "MISSING",
                        "UNAUTHORIZED", "FORBIDDEN", "DEPENDENCY_UNAVAILABLE",
                    )
                    assert "Bearer" not in json.dumps(result)
                    observations.append({
                        "product": product, "status": result["status"],
                        "http": result["source"]["http_status"],
                        "body_bytes": result["source"]["body_bytes"],
                        "digest": result["source"]["body_sha256"],
                    })
        assert len(observations) == 2
        assert audit.rows
        print("PUBLIC_MCP_CANARY", json.dumps(observations, separators=(",", ":")))
    finally:
        await executor.aclose(timeout=5)
