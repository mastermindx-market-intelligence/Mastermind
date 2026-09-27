"""Actual authenticated ASGI/MCP edge, with synthetic keys and GitHub only."""
from __future__ import annotations
import asyncio
import dataclasses
import json
import time
from contextlib import asynccontextmanager

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_github_app.models import AuthenticatedPrincipal
from integrations.mastermind_github_app.writer_gate_port import WRITER_GATE_SCOPE
from test_github_writer_gate_port import Owner

ISSUER = "https://identity.writer.example"
RESOURCE = "https://writer.example/mcp"

class Keys:
    def __init__(self, key): self.key = key
    async def key_for(self, kid):
        if kid != "fixture": raise ValueError("unknown key")
        return self.key

class Audit:
    def __init__(self): self.events = []
    def emit(self, event): self.events.append(dataclasses.asdict(event))

@pytest.fixture
def setup():
    owner = Owner()
    owner.now = int(time.time())
    owner.target = dataclasses.replace(owner.target, expires_at=owner.now + 600)
    subject = subject_digest(issuer=ISSUER, subject="automation-reader")
    owner.principal = AuthenticatedPrincipal(subject, (WRITER_GATE_SCOPE,))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid="fixture", alg="RS256", use="sig")
    policy = load_resource_policy({
        "schema": "mastermind.business_mcp_auth_policy.v1", "policy_id": "fixture.writer.read",
        "resource": RESOURCE, "resource_metadata_url": "https://writer.example/.well-known/oauth-protected-resource/mcp",
        "issuer": ISSUER, "authorization_servers": [ISSUER], "jwks_uri": ISSUER + "/jwks",
        "required_scopes": [WRITER_GATE_SCOPE], "allowed_subject_digests": [subject],
        "allowed_algorithms": ["RS256"], "clock_skew_seconds": 0, "max_token_lifetime_seconds": 3600,
        "jwks_cache_ttl_seconds": 60, "unknown_kid_refresh_cooldown_seconds": 1, "fetch_failure_backoff_seconds": 1})
    auth = JwtAuthenticator(policy=policy, jwks_cache=Keys(public))
    audit = Audit()
    def token(**changes):
        claims = {"iss": ISSUER, "aud": RESOURCE, "sub": "automation-reader", "client_id": "test-client",
                  "iat": owner.now - 1, "exp": owner.now + 60, "scope": WRITER_GATE_SCOPE}
        claims.update(changes)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "fixture"})
    return owner, policy, auth, audit, token

@asynccontextmanager
async def client_for(setup, *, armed=False, **changes):
    from integrations.mastermind_github_app.writer_gate_http import create_authenticated_writer_gate_server
    owner, policy, auth, audit, _ = setup
    kwargs = dict(authenticator=auth, policy=policy, now=lambda: owner.now, audit_sink=audit,
                  authority=owner, token_provider=owner, read_transport=owner.read,
                  allowed_hosts=("writer.example",), production_armed=armed)
    kwargs.update(changes)
    server = create_authenticated_writer_gate_server(**kwargs)
    app = server.streamable_http_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://writer.example") as client:
            yield client

async def rpc(client, token, method="tools/call", params=None, **headers):
    request_headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
                       "MCP-Protocol-Version": "2025-03-26"}
    if token is not None: request_headers["Authorization"] = "Bearer " + token
    request_headers.update(headers)
    if params is None: params = {"name": "source_continuity_writer_gate", "arguments": {"operation_key": "operation:test"}}
    return await client.post("/mcp", headers=request_headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})

def payload(response):
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    return result, json.loads(result["content"][0]["text"])

def test_authenticated_read_produces_canonical_receipt_without_token_output(setup):
    async def run():
        owner, _, _, audit, token = setup
        raw = token()
        async with client_for(setup, armed=True) as client:
            result, body = payload(await rpc(client, raw))
        assert result.get("isError", False) is False
        assert body["schema"] == "mastermind.source_continuity_writer_gate/v1"
        assert body["state"] == "TECHNICAL_WRITER_GATE_ACTIVE" and body["merge_authorized"] is False
        assert owner.token_calls == 1 and len(owner.calls) == 8
        encoded = json.dumps([body, audit.events])
        assert raw not in encoded and "synthetic-service-value" not in encoded
    asyncio.run(run())

@pytest.mark.parametrize("case", ["missing", "invalid", "wrong_signature", "wrong_subject", "wrong_audience", "wrong_scope", "expired"])
def test_bad_auth_never_reaches_service_identity_or_github(setup, case):
    async def run():
        owner, _, _, _, token = setup
        header, claims, signature = token().split(".")
        bad_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
        values = {"missing": None, "invalid": "not-a-token", "wrong_signature": ".".join((header, claims, bad_signature)), "wrong_subject": token(sub="foreign"),
                  "wrong_audience": token(aud="https://foreign.example/mcp"), "wrong_scope": token(scope="other.read"),
                  "expired": token(iat=owner.now - 60, exp=owner.now - 1)}
        async with client_for(setup, armed=True) as client:
            response = await rpc(client, values[case])
        assert response.status_code in {401, 403}
        assert owner.token_calls == 0 and owner.calls == []
    asyncio.run(run())

def test_default_disarm_and_closed_tool_catalog(setup):
    async def run():
        owner, _, _, _, token = setup
        async with client_for(setup) as client:
            listing = await rpc(client, token(), "tools/list", {})
            assert [t["name"] for t in listing.json()["result"]["tools"]] == ["source_continuity_writer_gate"]
            result, body = payload(await rpc(client, token()))
        assert result["isError"] and body == {"code": "PRODUCTION_DISARMED", "receipt": None}
        assert owner.token_calls == 0 and owner.calls == []
    asyncio.run(run())

@pytest.mark.parametrize("headers", [{"Host": "foreign.example"}, {"Origin": "https://foreign.example"}])
def test_transport_host_and_origin_refuse_before_github(setup, headers):
    async def run():
        owner, _, _, _, token = setup
        async with client_for(setup, armed=True) as client:
            response = await rpc(client, token(), **headers)
        assert response.status_code in {400, 403, 421}
        assert owner.token_calls == 0 and owner.calls == []
    asyncio.run(run())

def test_auth_expiry_during_first_remote_read_stops_further_reads(setup):
    async def run():
        owner, _, _, _, token = setup
        raw = token()
        original = owner.read
        def delayed(*args):
            response = original(*args)
            owner.now += 61
            return response
        async with client_for(setup, armed=True, read_transport=delayed) as client:
            result, body = payload(await rpc(client, raw))
        assert result["isError"] and body["receipt"] is None
        assert len(owner.calls) == 1
    asyncio.run(run())

def test_arbitrary_arguments_are_refused_without_reflection(setup):
    async def run():
        owner, _, _, _, token = setup
        params = {"name": "source_continuity_writer_gate", "arguments": {"operation_key": "operation:test", "token": "private-rejected-value"}}
        async with client_for(setup, armed=True) as client:
            response = await rpc(client, token(), params=params)
            result, body = payload(response)
        assert result["isError"] and body["code"] == "INPUT_REFUSED"
        assert "private-rejected-value" not in response.text
        assert owner.token_calls == 0 and owner.calls == []
    asyncio.run(run())


def test_protected_resource_metadata_names_only_existing_read_scope(setup):
    async def run():
        owner, _, _, _, _ = setup
        async with client_for(setup) as client:
            response = await client.get("/.well-known/oauth-protected-resource/mcp")
        assert response.status_code == 200
        body = response.json()
        assert body["resource"] == RESOURCE
        # The existing SDK serializes a root AnyUrl with a trailing slash.
        assert body["authorization_servers"] == [ISSUER + "/"]
        assert body["scopes_supported"] == [WRITER_GATE_SCOPE]
        assert owner.token_calls == 0 and owner.calls == []
    asyncio.run(run())


def test_auth_revocation_during_service_token_read_refuses_before_github(setup):
    async def run():
        owner, _, auth, _, token = setup
        original = owner.installation_token
        async def revoked():
            value = await original()
            auth._policy = dataclasses.replace(auth.policy, allowed_subject_digests=("f" * 64,))
            return value
        owner.installation_token = revoked
        async with client_for(setup, armed=True) as client:
            result, body = payload(await rpc(client, token()))
        assert result["isError"] and body["receipt"] is None
        assert owner.token_calls == 1 and owner.calls == []
    asyncio.run(run())


def test_two_overlapping_authenticated_requests_do_not_share_request_state(setup):
    async def run():
        owner, _, _, _, token = setup
        raw_a, raw_b = token(client_id="client-a"), token(client_id="client-b")
        async with client_for(setup, armed=True) as client:
            responses = await asyncio.gather(rpc(client, raw_a), rpc(client, raw_b))
        for response in responses:
            result, body = payload(response)
            assert not result.get("isError", False)
            assert body["branch_head_sha"] == owner.target.expected_head_sha
            assert raw_a not in response.text and raw_b not in response.text
        assert owner.token_calls == 2 and len(owner.calls) == 16
    asyncio.run(run())


@pytest.mark.parametrize("setting,value", [("production_armed", "true"), ("allowed_hosts", ()),
    ("allowed_hosts", ("*",)), ("allowed_origins", ("https://*",))])
def test_deployment_refuses_unsafe_or_ambiguous_configuration(setup, setting, value):
    async def run():
        owner, _, _, _, _ = setup
        with pytest.raises(ValueError):
            async with client_for(setup, **{setting: value}):
                pass
        assert owner.token_calls == 0 and owner.calls == []
    asyncio.run(run())
