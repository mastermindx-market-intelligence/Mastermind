from __future__ import annotations

import hashlib
import json

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.studio_direct_mcp.cloud_auth_gateway import (
    STUDIO_DESIGN_SCOPE,
    StudioCloudGatewayError,
    UpstreamResult,
    create_studio_cloud_app,
)


ISSUER = "https://identity.studio.example.test/"
RESOURCE = "https://studio.example.test/mcp"
METADATA = "https://studio.example.test/.well-known/oauth-protected-resource"
SUBJECT = "fixture-subject"


class Audit:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


class Keys:
    def __init__(self, key):
        self.key = key

    async def key_for(self, kid):
        assert kid == "fixture-key"
        return self.key


class Forwarder:
    def __init__(self):
        self.calls = []

    async def call(self, *, method, body, headers):
        self.calls.append((method, body, dict(headers)))
        return UpstreamResult(
            status_code=200,
            headers=(
                ("content-type", "application/json"),
                ("mcp-session-id", "fixture-session"),
                ("x-hidden", "no"),
            ),
            body=b'{"ok":true}',
        )


def _policy():
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "studio-cloud-fixture",
            "resource": RESOURCE,
            "resource_metadata_url": METADATA,
            "issuer": ISSUER,
            "authorization_servers": [ISSUER],
            "jwks_uri": ISSUER + ".well-known/jwks.json",
            "required_scopes": [STUDIO_DESIGN_SCOPE],
            "allowed_subject_digests": [
                subject_digest(issuer=ISSUER, subject=SUBJECT)
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _verifier(policy, *, now=1_800_000_000):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private.public_key().public_numbers()
    def b64(value):
        raw=value.to_bytes((value.bit_length()+7)//8,"big")
        import base64
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    key={"kid":"fixture-key","kty":"RSA","use":"sig","alg":"RS256","n":b64(numbers.n),"e":b64(numbers.e)}
    auth=JwtAuthenticator(policy=policy,jwks_cache=Keys(key))
    audit=Audit()
    verifier=MastermindTokenVerifier(
        authenticator=auth,policy=policy,now=lambda:now,audit_sink=audit
    )
    return verifier,private,audit


def _token(private, policy, *, now=1_800_000_000, scope=STUDIO_DESIGN_SCOPE):
    return jwt.encode(
        {
            "iss": ISSUER,
            "sub": SUBJECT,
            "aud": RESOURCE,
            "iat": now-1,
            "exp": now+300,
            "scope": scope,
            "client_id": "fixture-client",
        },
        private,
        algorithm="RS256",
        headers={"kid":"fixture-key"},
    )


def test_metadata_is_public_exact_and_query_alias_refused():
    policy=_policy(); verifier,_private,_audit=_verifier(policy); fwd=Forwarder()
    client=TestClient(create_studio_cloud_app(policy=policy,verifier=verifier,forwarder=fwd))
    response=client.get("/.well-known/oauth-protected-resource",headers={"host":"studio.example.test"})
    assert response.status_code==200
    assert response.json()=={
        "resource":RESOURCE,
        "authorization_servers":[ISSUER],
        "scopes_supported":[STUDIO_DESIGN_SCOPE],
    }
    assert client.get("/.well-known/oauth-protected-resource?x=1").status_code==404
    assert fwd.calls==[]


def test_missing_and_wrong_scope_never_reach_studio():
    policy=_policy(); verifier,private,audit=_verifier(policy); fwd=Forwarder()
    client=TestClient(create_studio_cloud_app(policy=policy,verifier=verifier,forwarder=fwd))
    missing=client.post("/mcp",headers={"host":"studio.example.test"},json={})
    assert missing.status_code==401
    assert 'resource_metadata="' in missing.headers["www-authenticate"]
    wrong=_token(private,policy,scope="mastermind.studio.read")
    refused=client.post(
        "/mcp",
        headers={"host":"studio.example.test","authorization":"Bearer "+wrong},
        json={},
    )
    assert refused.status_code in (401,403)
    assert fwd.calls==[]
    assert audit.events


def test_valid_token_forwards_only_mcp_headers_and_body():
    policy=_policy(); verifier,private,_audit=_verifier(policy); fwd=Forwarder()
    client=TestClient(create_studio_cloud_app(policy=policy,verifier=verifier,forwarder=fwd))
    token=_token(private,policy)
    body=b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
    response=client.post(
        "/mcp",
        headers={
            "host":"studio.example.test",
            "authorization":"Bearer "+token,
            "content-type":"application/json",
            "accept":"application/json, text/event-stream",
            "mcp-protocol-version":"2025-03-26",
            "x-secret":"must-not-forward",
        },
        content=body,
    )
    assert response.status_code==200
    assert response.json()=={"ok":True}
    assert response.headers["mcp-session-id"]=="fixture-session"
    assert "x-hidden" not in response.headers
    assert len(fwd.calls)==1
    method,forwarded_body,headers=fwd.calls[0]
    assert method=="POST" and forwarded_body==body
    assert "authorization" not in headers and "x-secret" not in headers
    assert headers["mcp-protocol-version"]=="2025-03-26"


def test_host_path_method_and_oversize_refuse_before_forward():
    policy=_policy(); verifier,private,_audit=_verifier(policy); fwd=Forwarder()
    client=TestClient(create_studio_cloud_app(policy=policy,verifier=verifier,forwarder=fwd))
    token=_token(private,policy)
    auth={"authorization":"Bearer "+token}
    assert client.post("/mcp",headers={**auth,"host":"other.example.test"},json={}).status_code==421
    assert client.post("/mcp?x=1",headers={**auth,"host":"studio.example.test"},json={}).status_code==404
    assert client.get("/mcp",headers={**auth,"host":"studio.example.test"}).status_code in (404,405)
    assert fwd.calls==[]


def test_policy_must_be_exact_studio_design_scope():
    policy=_policy(); verifier,_private,_audit=_verifier(policy); fwd=Forwarder()
    bad=policy.__class__(**{**policy.__dict__,"required_scopes":("mastermind.studio.read",)})
    try:
        create_studio_cloud_app(policy=bad,verifier=verifier,forwarder=fwd)
    except StudioCloudGatewayError:
        pass
    else:
        raise AssertionError("foreign Studio scope was accepted")
