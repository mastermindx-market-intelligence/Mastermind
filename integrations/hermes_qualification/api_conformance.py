"""H24-04 disposable signed-client conformance helpers.

This is a source-test adapter, never an authentication service or an enrollment
writer. Keys exist only in memory, issuers are reserved .test fixtures, and every
HTTP client has an explicit ASGI transport. The incumbent JwtAuthenticator,
Workspace/COO applications, schemas and SecretaryAccessClient remain the subjects
under test. Nothing in this module listens, installs, submits a provider request,
retries an effect, or makes a physically-exactly-once claim.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
from collections.abc import Mapping
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA, AuthError, AuthErrorCode, ResourcePolicy,
    load_resource_policy, subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_executive_app.coo_binding import COO_SCOPES
from integrations.mastermind_executive_app.gateway import READ_SCOPE, SUBMIT_SCOPE
from integrations.mastermind_workspace_app.contract import RESOURCE as WORKSPACE_RESOURCE
from integrations.mastermind_workspace_app.contract import SCOPE as WORKSPACE_SCOPE

SOURCE_BASE = "b54cb10e4abdd3766c62d4088f6a576ecfe80437"
FIXTURE_NOW = 1_800_000_000
FIXTURE_ISSUER = "https://issuer.h24.example.test"
CEO_RESOURCE = "https://executive.h24.example.test/mcp"
# Desired distinct fixture resource; the pinned COO composition rejects this join.
COO_RESOURCE = "https://executive.h24.example.test/mcp/coo"
# The pinned COO settings require shared metadata; this is explicitly a C34 gap.
FIXTURE_METADATA = CEO_RESOURCE + "/.well-known/oauth-protected-resource"
MISSION_PATH = "/workspace/mission/v3/current"


@dataclasses.dataclass(frozen=True)
class FixtureIdentity:
    """One distinct fixture subject AND OAuth client, with its own signing key."""

    label: str
    subject: str
    client_id: str
    kid: str
    _key: rsa.RSAPrivateKey = dataclasses.field(repr=False, compare=False)

    @classmethod
    def generate(cls, label: str) -> "FixtureIdentity":
        if label not in {"gb1", "secretary"}:
            raise ValueError("only the two declared fixture identities are supported")
        return cls(label, "h24-subject-" + label, "h24-client-" + label,
                   "h24-key-" + label,
                   rsa.generate_private_key(public_exponent=65537, key_size=2048))

    def public_jwk(self) -> dict[str, str]:
        numbers = self._key.public_key().public_numbers()

        def encoded(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        return {"kid": self.kid, "kty": "RSA", "use": "sig", "alg": "RS256",
                "n": encoded(numbers.n), "e": encoded(numbers.e)}

    def token(self, policy: ResourcePolicy, **claim_overrides: Any) -> str:
        """Sign synthetic claims; overrides exist solely for negative test cases."""
        if policy.issuer != FIXTURE_ISSUER:
            raise ValueError("fixture signing is restricted to the .test issuer")
        claims = {
            "iss": policy.issuer, "sub": self.subject, "client_id": self.client_id,
            "aud": policy.resource, "scope": " ".join(policy.required_scopes),
            "iat": FIXTURE_NOW, "nbf": FIXTURE_NOW, "exp": FIXTURE_NOW + 300,
            "jti": "fixture-" + self.label,
        }
        claims.update(claim_overrides)
        return jwt.encode(claims, self._key, algorithm="RS256",
                          headers={"kid": self.kid, "typ": "at+jwt"})


class FixturePublicKeys:
    """An in-memory public-key seam, not a JWKS server or issuer implementation."""

    def __init__(self, identities: tuple[FixtureIdentity, ...]):
        keys = [identity.public_jwk() for identity in identities]
        if len({key["kid"] for key in keys}) != len(keys):
            raise ValueError("duplicate fixture key identity")
        self._keys = {key["kid"]: key for key in keys}
        self.calls: list[str] = []

    async def key_for(self, kid: str) -> Mapping[str, object]:
        self.calls.append(kid)
        if kid not in self._keys:
            raise AuthError(AuthErrorCode.KEY_NOT_FOUND)
        return dict(self._keys[kid])


def fixture_policy(
    identities: tuple[FixtureIdentity, ...], *, facet: str,
) -> ResourcePolicy:
    """Use the real closed policy parser; legacy COO still shares CEO audience."""
    surfaces = {
        "workspace": (WORKSPACE_RESOURCE, (WORKSPACE_SCOPE,)),
        "ceo_read": (CEO_RESOURCE, (READ_SCOPE,)),
        "ceo_submit": (CEO_RESOURCE,
                       tuple(sorted((READ_SCOPE, SUBMIT_SCOPE)))),
        "coo": (COO_RESOURCE, COO_SCOPES),
        "coo_legacy": (CEO_RESOURCE, COO_SCOPES),
    }
    resource, scopes = surfaces[facet]
    return load_resource_policy({
        "schema": AUTH_POLICY_SCHEMA, "policy_id": "h24-" + facet.replace("_", "-"),
        "resource": resource,
        "resource_metadata_url": (
            WORKSPACE_RESOURCE + "/.well-known/oauth-protected-resource"
            if facet == "workspace" else FIXTURE_METADATA),
        "issuer": FIXTURE_ISSUER, "authorization_servers": [FIXTURE_ISSUER],
        "jwks_uri": FIXTURE_ISSUER + "/.well-known/jwks.json",
        "required_scopes": sorted(scopes),
        "allowed_subject_digests": sorted(subject_digest(
            issuer=FIXTURE_ISSUER, subject=identity.subject) for identity in identities),
        "allowed_algorithms": ["RS256"], "clock_skew_seconds": 0,
        "max_token_lifetime_seconds": 900, "jwks_cache_ttl_seconds": 300,
        "unknown_kid_refresh_cooldown_seconds": 30, "fetch_failure_backoff_seconds": 5,
    })


def authenticator(
    policy: ResourcePolicy, keys: FixturePublicKeys,
) -> JwtAuthenticator:
    """The production verifier is used unchanged; only its public key source is fake."""
    return JwtAuthenticator(policy=policy, jwks_cache=keys)


class FixtureAudit:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


@dataclasses.dataclass(frozen=True)
class HttpObservation:
    method: str
    path: str
    body: bytes


class ObservedAsgiTransport(httpx.AsyncBaseTransport):
    """Count actual ASGI invocations and optionally lose one completed response.

    No retry, deduplication or request-identity logic lives here. A response loss
    happens AFTER the real application has run, so tests cannot confuse it with
    a proven pre-send failure. Authorization headers/tokens are never recorded.
    """

    def __init__(self, app, *, lose_response_for: str | None = None):
        self._transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        self.lose_response_for = lose_response_for
        self.requests: list[HttpObservation] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        self.requests.append(HttpObservation(request.method, request.url.path, body))
        response = await self._transport.handle_async_request(request)
        if request.url.path == self.lose_response_for:
            self.lose_response_for = None
            await response.aclose()
            raise httpx.ReadTimeout("fixture lost the completed response", request=request)
        return response

    async def aclose(self):
        await self._transport.aclose()


def signed_asgi_client(app, token: str, *, transport=None, workspace=False) -> httpx.AsyncClient:
    """Host-injected client for SecretaryAccessClient, with no network fallback."""
    return httpx.AsyncClient(
        transport=transport or ObservedAsgiTransport(app),
        base_url="https://mcp.mastermind-x.com" if workspace else "http://127.0.0.1",
        headers={"authorization": "Bearer " + token},
        follow_redirects=False, trust_env=False, timeout=2.0,
    )


def rpc(method="tools/list", *, name=None, arguments=None) -> dict[str, Any]:
    value = {"jsonrpc": "2.0", "id": 1, "method": method}
    if name is not None:
        value["params"] = {"name": name, "arguments": arguments}
    return value


def rpc_headers() -> dict[str, str]:
    return {"accept": "application/json, text/event-stream",
            "mcp-protocol-version": "2025-06-18"}


def tool_payload(response: httpx.Response) -> dict[str, Any]:
    """Decode using the existing Secretary strict JSON parser, not a copied one."""
    from integrations.secretary_team_access.client import _strict_json
    outer = _strict_json(response.content)
    result = outer["result"]
    if outer.get("jsonrpc") != "2.0" or outer.get("id") != 1:
        raise ValueError("wrong fixture RPC correlation")
    content = result["content"]
    if len(content) != 1 or content[0].get("type") != "text":
        raise ValueError("unexpected fixture result shape")
    return _strict_json(content[0]["text"].encode("utf-8"))


def permission_receipt(label: str) -> str:
    """A synthetic enrollment receipt marker; no authority is minted here."""
    return hashlib.sha256(("h24-fixture-enrollment:" + label).encode()).hexdigest()


def route_resource_matrix() -> tuple[dict[str, Any], ...]:
    """Record the pinned incumbent contracts; do not create a routing registry."""
    from integrations.executive_mcp.coo import COO_TOOL_SPECS
    return (
        {"route": MISSION_PATH, "method": "GET", "audience": WORKSPACE_RESOURCE,
         "scopes": [WORKSPACE_SCOPE], "effect": "read current Mission"},
        {"route": "/mcp", "method": "POST", "audience": CEO_RESOURCE,
         "scopes": ["mastermind.executive.read"], "effect": "CEO tool catalogue/read"},
        {"route": "/mcp/coo", "method": "POST", "audience": CEO_RESOURCE, "integration_gap": "C34_SHARED_RESOURCE",
         "scopes": list(COO_SCOPES), "effect": "COO MCP",
         "tools": [spec.name for spec in COO_TOOL_SPECS]},
        {"route": "/v1/tools/executive_mandate", "method": "POST",
         "audience": CEO_RESOURCE, "integration_gap": "C34_SHARED_RESOURCE",
         "scopes": list(COO_SCOPES), "effect": "read mandate; same principal and receipt"},
        {"route": "/v1/tools/submit_principal_intent", "method": "POST",
         "audience": CEO_RESOURCE, "integration_gap": "C34_SHARED_RESOURCE",
         "scopes": list(COO_SCOPES),
         "effect": "fresh bounded admission; original req-coo"},
        {"route": "/v1/tools/principal_intent_status", "method": "POST",
         "audience": CEO_RESOURCE, "integration_gap": "C34_SHARED_RESOURCE",
         "scopes": list(COO_SCOPES),
         "effect": "authenticated original status; no fresh admission"},
        {"route": "/mcp/principal-ruling", "method": "POST",
         "audience": CEO_RESOURCE, "integration_gap": "C34_SHARED_RESOURCE",
         "scopes": list(COO_SCOPES),
         "effect": "separate fixed host obligation; bounded ruling"},
    )
