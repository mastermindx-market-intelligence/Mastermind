"""BSC-E1 ASGI edge — auth negative matrix + the real no-execution canary.

Two halves:

1. A fast, fully hermetic negative/positive AUTH + HTTP-framing matrix. Every
   app instance here points its dedicated-ingress socket path at a path with
   NOTHING listening, so a request that reached the real send path would
   surface as a distinct 500/connection failure rather than a clean
   401/403/200 — proving auth/framing refuses BEFORE any socket effect is
   even attempted.
2. The REAL acceptance canary: a genuine RS256-signed token, verified by the
   real A1 stack, driving a genuine HTTP request through the full ASGI app,
   whose admission path sends a real frame over a real (but freshly minted,
   TEMPORARY, no-execution) dedicated CeoIngress AF_UNIX socket backed by a
   real ``control_plane.executive_runtime.Runtime`` on ``tmp_path`` SQLite —
   mirroring the exact hermetic harness ``tests/test_executive_ceo_ingress.py``
   already uses (``ExecutiveControlService`` + a supervisor that never
   dispatches). No production socket is ever touched; nothing here installs
   anything.
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
from starlette.testclient import TestClient

from control_plane import ceo_boot_packet
from control_plane import executive_ceo_ingress as ceo_ingress
from control_plane.executive_runtime import Runtime
from control_plane.executive_service import ExecutiveControlService, ServiceConfig
from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    load_resource_policy,
    subject_digest,
)
from integrations.executive_mcp import schemas as mcp_schemas
from integrations.mastermind_executive_app.admission import STATUS_ACCEPTED, STATUS_CONFLICT
from integrations.mastermind_executive_app.app import AppSettings, create_app
from integrations.mastermind_executive_app.gateway import AppPolicies, READ_SCOPE, SUBMIT_SCOPE

# ---------------------------------------------------------------------------
# shared fixtures: RS256 keys, policies, tokens
# ---------------------------------------------------------------------------

NOW = 1_800_000_000
KID = "e1-test-kid"
ISSUER = "https://issuer.mastermind.example.test"
RESOURCE = "https://executive-app.mastermind.example.test/mcp"
METADATA_PATH = "/mcp/.well-known/oauth-protected-resource"
METADATA_URL = RESOURCE + "/.well-known/oauth-protected-resource"
SUBJECT = "chairman-opaque-e1"


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def other_rsa_key() -> rsa.RSAPrivateKey:
    """A second, unrelated key — used ONLY to sign a token claiming the SAME
    kid the fake JWKS cache serves, proving signature verification (not just
    kid lookup) is what refuses a wrong-key token."""

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _base64url_uint(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode()


def _rsa_jwk(private_key: rsa.RSAPrivateKey, *, kid: str = KID) -> dict[str, object]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kid": kid,
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": _base64url_uint(numbers.n),
        "e": _base64url_uint(numbers.e),
    }


class _FakeJwksCache:
    """Always serves ``rsa_key``'s public JWK for :data:`KID`; refuses any
    other kid.  Never touches the network."""

    def __init__(self, key: rsa.RSAPrivateKey, *, kid: str = KID) -> None:
        self._jwk = _rsa_jwk(key, kid=kid)
        self._kid = kid
        self.calls: list[str] = []

    async def key_for(self, kid: str) -> Mapping[str, object]:
        self.calls.append(kid)
        if kid != self._kid:
            from integrations.business_mcp_auth.contracts import AuthError, AuthErrorCode

            raise AuthError(AuthErrorCode.KEY_NOT_FOUND)
        return dict(self._jwk)


def _read_policy(**overrides: Any):
    payload = {
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": "bsc-e1-test-read",
        "resource": RESOURCE,
        "resource_metadata_url": RESOURCE + "/.well-known/oauth-protected-resource",
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "/.well-known/jwks.json",
        "required_scopes": [READ_SCOPE],
        "allowed_subject_digests": [subject_digest(issuer=ISSUER, subject=SUBJECT)],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 300,
        "unknown_kid_refresh_cooldown_seconds": 30,
        "fetch_failure_backoff_seconds": 5,
    }
    payload.update(overrides)
    return load_resource_policy(payload)


def _submit_policy(**overrides: Any):
    payload = {
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": "bsc-e1-test-submit",
        "resource": RESOURCE,
        "resource_metadata_url": RESOURCE + "/.well-known/oauth-protected-resource",
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "/.well-known/jwks.json",
        "required_scopes": sorted([SUBMIT_SCOPE, READ_SCOPE]),
        "allowed_subject_digests": [subject_digest(issuer=ISSUER, subject=SUBJECT)],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 300,
        "unknown_kid_refresh_cooldown_seconds": 30,
        "fetch_failure_backoff_seconds": 5,
    }
    payload.update(overrides)
    return load_resource_policy(payload)


def _claims(*, resource: str = RESOURCE, scope: str, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "iss": ISSUER,
        "sub": SUBJECT,
        "aud": resource,
        "iat": NOW,
        "nbf": NOW,
        "exp": NOW + 300,
        "scope": scope,
        "jti": "opaque-jti",
        "client_id": "e1-test-client",
    }
    value.update(overrides)
    return value


def _token(
    private_key: rsa.RSAPrivateKey,
    *,
    scope: str,
    algorithm: str = "RS256",
    headers: Mapping[str, object] | None = None,
    **claim_overrides: Any,
) -> str:
    complete_headers: dict[str, object] = {"kid": KID, "typ": "at+jwt"}
    if headers:
        complete_headers.update(headers)
    return jwt.encode(
        _claims(scope=scope, **claim_overrides),
        private_key,
        algorithm=algorithm,
        headers=complete_headers,
    )


def _read_token(rsa_key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    return _token(rsa_key, scope=READ_SCOPE, **overrides)


def _submit_token(rsa_key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    return _token(rsa_key, scope=f"{READ_SCOPE} {SUBMIT_SCOPE}", **overrides)


def _client(
    rsa_key: rsa.RSAPrivateKey,
    *,
    mastermind_root: Path,
    ceo_ingress_socket_path: str = "/tmp/never-used-e1.sock",
) -> tuple[TestClient, AppSettings]:
    """Build a TestClient whose dedicated-ingress socket path provably has
    nothing listening.  Every negative-auth test below therefore doubles as
    proof authentication refuses BEFORE any socket effect is attempted: a
    request that reached the real (nonexistent) socket would surface as a
    500/connection error, never a clean 401/403/200."""

    policies = AppPolicies(read=_read_policy(), submit=_submit_policy())
    settings = AppSettings(
        policies=policies,
        mastermind_root=mastermind_root,
        macro_root_flag=None,
        environ={},
        ceo_ingress_socket_path=ceo_ingress_socket_path,
        jwks_cache=_FakeJwksCache(rsa_key),
        clock=lambda: NOW,
    )
    app = create_app(settings)
    return TestClient(app, raise_server_exceptions=False), settings


# ===========================================================================
# 1. AUTH negative matrix (read endpoint)
# ===========================================================================


def test_missing_authorization_refuses_401_with_challenge(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    response = client.post("/v1/tools/executive_state", json={"arguments": {}})
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert response.json()["ok"] is False


def test_malformed_authorization_refuses_401(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    response = client.post(
        "/v1/tools/executive_state",
        json={"arguments": {}},
        headers={"Authorization": "NotBearer abc"},
    )
    assert response.status_code == 401


def test_duplicate_authorization_header_refuses_before_verification(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    # httpx/starlette TestClient sends a list of (name, value) header pairs
    # as-is, which can carry the SAME header name twice on the wire.
    response = client.post(
        "/v1/tools/executive_state",
        json={"arguments": {}},
        headers=[("Authorization", f"Bearer {token}"), ("Authorization", f"Bearer {token}")],
    )
    assert response.status_code == 401


def test_wrong_issuer_refuses(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key, iss="https://attacker.example.test")
    response = client.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "issuer_refused"


def test_wrong_resource_audience_refuses(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key, aud="https://someone-elses-app.example.test/mcp")
    response = client.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "resource_refused"


def test_wrong_algorithm_none_refuses(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    # PyJWT refuses to encode "none" with a key unless explicitly permitted;
    # construct the compact token by hand to prove the SERVER refuses it.
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT", "kid": KID}).encode()
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps(_claims(scope=READ_SCOPE)).encode()
    ).rstrip(b"=")
    token = (header + b"." + payload + b".").decode()
    response = client.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_wrong_key_refuses(rsa_key, other_rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    # Signed with a DIFFERENT private key but claims the SAME kid the fake
    # JWKS cache serves (rsa_key's public key) -- signature must not verify.
    token = _token(other_rsa_key, scope=READ_SCOPE)
    response = client.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_signature_refused"


def test_expired_token_refuses(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key, iat=NOW - 1000, exp=NOW - 100)
    response = client.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_expired"


def test_not_yet_valid_token_refuses(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key, iat=NOW + 500, nbf=NOW + 500, exp=NOW + 800)
    response = client.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_not_yet_valid"


def test_offline_access_only_scope_refuses(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _token(rsa_key, scope="offline_access")
    response = client.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code in (401, 403)
    assert response.json()["error"]["code"] == "scope_refused"


def test_wrong_subject_not_in_allowlist_refuses(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key, sub="someone-else")
    response = client.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "subject_refused"


def test_conflicting_client_id_and_azp_refuses(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key, client_id="client-a", azp="client-b")
    response = client.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_claims_refused"


def test_read_scope_only_cannot_call_submit_endpoint(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    response = client.post(
        "/v1/tools/submit_ceo_intent",
        json={"arguments": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (401, 403)
    assert response.json()["error"]["code"] == "scope_refused"


def test_two_scope_token_refused_by_exact_match_read_policy(rsa_key, tmp_path):
    """A submit-capable (two-scope) token is REFUSED by the READ policy's
    exact scope-set match -- proves scopes are checked exactly, not as a
    subset."""

    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _submit_token(rsa_key)
    response = client.post(
        "/v1/tools/executive_state",
        json={"arguments": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (401, 403)
    assert response.json()["error"]["code"] == "scope_refused"


def test_generic_verifier_cannot_widen_host(rsa_key, tmp_path):
    """A caller-authored Host/Origin header never widens or changes which
    policy resource is checked -- the audience check is against the FIXED
    policy resource, never anything derived from the request."""

    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    response = client.post(
        "/v1/tools/executive_state",
        json={"arguments": {}},
        headers={
            "Authorization": f"Bearer {token}",
            "Host": "attacker.example.test",
            "Origin": "https://attacker.example.test",
            "X-Forwarded-Host": "attacker.example.test",
        },
    )
    # Auth succeeds (the token's real audience matches the fixed policy
    # resource) regardless of the attacker-authored Host/Origin -- those
    # headers are simply never consulted.
    assert response.status_code == 200


# ===========================================================================
# 2. protected-resource metadata + HTTP framing adversarial states
# ===========================================================================


def test_metadata_get_serves_the_exact_public_read_policy_projection(rsa_key, tmp_path):
    """A missing public GET route, a copied projection, or authentication
    requirement would make this externally observable RFC 9728 contract fail.
    """

    client, settings = _client(rsa_key, mastermind_root=tmp_path)
    response = client.get(METADATA_PATH)

    assert response.status_code == 200
    assert response.json() == {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": [READ_SCOPE],
    }
    assert settings.jwks_cache.calls == []


def test_missing_tool_authentication_challenge_points_to_the_served_metadata_route(rsa_key, tmp_path):
    """A challenge that points at an unserved or different route strands the
    OAuth client before it can authenticate an otherwise unchanged tool call.
    """

    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    tool_response = client.post("/v1/tools/executive_state", json={"arguments": {}})
    metadata_response = client.get(METADATA_PATH)

    assert tool_response.status_code == 401
    assert f'resource_metadata="{METADATA_URL}"' in tool_response.headers["WWW-Authenticate"]
    assert metadata_response.status_code == 200


def test_metadata_route_never_proxies_authorization_server_discovery(rsa_key, tmp_path):
    """Registering an IdP discovery alias here would turn this resource server
    into an authorization-server proxy and widen the public attack surface.
    """

    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    response = client.get("/mcp/.well-known/oauth-authorization-server")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "expected_status"),
    [
        ("GET", METADATA_PATH + "/", 404),
        ("GET", METADATA_PATH + "?unexpected=1", 404),
        ("GET", METADATA_PATH + "%2Fother", 400),
        ("GET", METADATA_PATH + "%5Cother", 400),
        ("GET", METADATA_PATH.replace("/mcp/", "/mcp//"), 400),
        ("POST", METADATA_PATH, 404),
        ("HEAD", METADATA_PATH, 404),
        ("OPTIONS", METADATA_PATH, 404),
    ],
)
def test_metadata_near_matches_and_non_get_requests_never_alias_the_public_document(
    rsa_key, tmp_path, method, path, expected_status
):
    """A route normalizer, query-tolerant handler, or accidental HEAD/POST
    registration would widen the one intended public configuration document.
    """

    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    response = client.request(method, path, follow_redirects=False)

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "submit_overrides",
    [
        {"resource": "https://other-resource.mastermind.example.test/mcp"},
        {"resource_metadata_url": "https://executive-app.mastermind.example.test/other-metadata"},
        {
            "issuer": "https://other-issuer.mastermind.example.test",
            "authorization_servers": ["https://other-issuer.mastermind.example.test"],
            "jwks_uri": "https://other-issuer.mastermind.example.test/.well-known/jwks.json",
        },
    ],
)
def test_create_app_refuses_read_submit_policy_identity_drift(rsa_key, tmp_path, submit_overrides):
    """Two policy instances that identify different resources or authorization
    realms must not construct one incoherent app generation.
    """

    policies = AppPolicies(
        read=_read_policy(),
        submit=_submit_policy(**submit_overrides),
    )
    settings = AppSettings(
        policies=policies,
        mastermind_root=tmp_path,
        macro_root_flag=None,
        environ={},
        ceo_ingress_socket_path="/tmp/never-used-e1.sock",
        jwks_cache=_FakeJwksCache(rsa_key),
        clock=lambda: NOW,
    )

    with pytest.raises(ValueError, match="same resource identity"):
        create_app(settings)


@pytest.mark.parametrize(
    "metadata_url",
    [
        RESOURCE + "/.well-known%2foauth-protected-resource",
        RESOURCE + "/.well-known%5coauth-protected-resource",
        RESOURCE + "/.well-known/oauth-protected-%41resource",
        RESOURCE + "//.well-known/oauth-protected-resource",
    ],
)
def test_create_app_refuses_valid_a1_metadata_paths_the_raw_route_fence_cannot_serve(
    rsa_key, tmp_path, metadata_url
):
    """A1 preserves these URL spellings, but Starlette normalizes them while
    this edge intentionally refuses encoded separators and duplicate slashes.
    Construction must not advertise an exact metadata URL it cannot serve.
    """

    policies = AppPolicies(
        read=_read_policy(resource_metadata_url=metadata_url),
        submit=_submit_policy(resource_metadata_url=metadata_url),
    )
    settings = AppSettings(
        policies=policies,
        mastermind_root=tmp_path,
        macro_root_flag=None,
        environ={},
        ceo_ingress_socket_path="/tmp/never-used-e1.sock",
        jwks_cache=_FakeJwksCache(rsa_key),
        clock=lambda: NOW,
    )

    with pytest.raises(ValueError, match="not safely serveable"):
        create_app(settings)


def test_metadata_url_without_a_path_serves_the_http_root_exactly(rsa_key, tmp_path):
    """An authority-only HTTPS URL has the HTTP request path `/`; rejecting
    it would make one otherwise safe, validated URL form unservable.
    """

    metadata_url = "https://executive-app.mastermind.example.test"
    policies = AppPolicies(
        read=_read_policy(resource_metadata_url=metadata_url),
        submit=_submit_policy(resource_metadata_url=metadata_url),
    )
    settings = AppSettings(
        policies=policies,
        mastermind_root=tmp_path,
        macro_root_flag=None,
        environ={},
        ceo_ingress_socket_path="/tmp/never-used-e1.sock",
        jwks_cache=_FakeJwksCache(rsa_key),
        clock=lambda: NOW,
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["resource"] == RESOURCE


def test_create_app_revalidates_a_forged_policy_before_registering_metadata(rsa_key, tmp_path):
    """A frozen dataclass can be forged with object.__setattr__; accepting it
    would let a stale challenge and public metadata disagree at runtime.
    """

    forged_read = dataclasses.replace(_read_policy())
    object.__setattr__(
        forged_read,
        "resource_metadata_url",
        RESOURCE + "/not-a-valid metadata path",
    )
    policies = AppPolicies(read=forged_read, submit=_submit_policy())
    settings = AppSettings(
        policies=policies,
        mastermind_root=tmp_path,
        macro_root_flag=None,
        environ={},
        ceo_ingress_socket_path="/tmp/never-used-e1.sock",
        jwks_cache=_FakeJwksCache(rsa_key),
        clock=lambda: NOW,
    )

    with pytest.raises(ValueError, match="metadata policy refused"):
        create_app(settings)


def test_unknown_tool_name_refuses_404(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    response = client.post(
        "/v1/tools/not_a_real_tool", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_wrong_method_refuses_405(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    response = client.get("/v1/tools/executive_state", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 405


def test_trailing_slash_is_not_silently_aliased(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    response = client.post(
        "/v1/tools/executive_state/",
        json={"arguments": {}},
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert response.status_code != 307


def test_encoded_slash_raw_path_does_not_alias_a_different_route(rsa_key, tmp_path):
    """%2F must NEVER be silently decoded into a route-altering '/' -- proven
    directly: without the raw-path fence, Starlette's router decodes
    ``submit_ceo_intent%2Freconcile`` to ``submit_ceo_intent/reconcile`` and
    dispatches it to the LITERAL reconcile route (verified independently
    against a bare Starlette app during development). The fence must refuse
    this before either route -- or authentication -- ever runs."""

    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _submit_token(rsa_key)
    response = client.post(
        "/v1/tools/submit_ceo_intent%2Freconcile",
        json={"arguments": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_input"


def test_encoded_slash_refuses_even_with_no_authorization_header(rsa_key, tmp_path):
    """The raw-path fence runs BEFORE authentication -- an unauthenticated
    encoded-slash request is refused identically, never a 401."""

    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    response = client.post(
        "/v1/tools/submit_ceo_intent%2Freconcile", json={"arguments": {}}
    )
    assert response.status_code == 400


def test_backslash_in_path_is_refused():
    from integrations.mastermind_executive_app.app import _SUSPICIOUS_RAW_PATH_MARKERS

    assert b"%5c" in _SUSPICIOUS_RAW_PATH_MARKERS
    assert b"//" in _SUSPICIOUS_RAW_PATH_MARKERS


def test_malformed_json_body_refuses_400(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    response = client.post(
        "/v1/tools/executive_state",
        content=b"{not json",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    assert response.status_code == 400


def test_unexpected_top_level_body_key_refuses_400(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    response = client.post(
        "/v1/tools/executive_state",
        json={"arguments": {}, "extra": "attacker-value"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_oversized_body_refuses_413(rsa_key, tmp_path):
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    huge = {"arguments": {"padding": "x" * 200_000}}
    response = client.post(
        "/v1/tools/executive_state",
        content=json.dumps(huge).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    assert response.status_code == 413


# ===========================================================================
# 3. positive read path (proves the existing gateway/schemas are reused)
# ===========================================================================


def test_authenticated_read_call_reaches_the_existing_gateway(rsa_key, tmp_path):
    # A real (throwaway) git repo so ExecutiveMcpGateway's boot-packet read
    # has a real HEAD sha to report, exercising the ACTUAL reused read path
    # rather than a fake.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "e1@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "E1"], check=True)
    (tmp_path / "README.md").write_text("# fixture\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "fixture"], check=True)

    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    response = client.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["tool"] == "executive_state"
    assert body["schema"] == mcp_schemas.RESULT_SCHEMA


def test_all_five_tools_present_with_frozen_schema_digest():
    names = {spec.name for spec in mcp_schemas.TOOL_SPECS}
    assert names == {
        "executive_state",
        "executive_inbox",
        "executive_job",
        "ceo_intent_status",
        "submit_ceo_intent",
    }
    assert mcp_schemas.schema_snapshot_sha256() == (
        "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
    )
    for spec in mcp_schemas.TOOL_SPECS:
        annotations = spec.annotations
        assert annotations["destructiveHint"] is False
        assert annotations["idempotentHint"] is True
        assert annotations["openWorldHint"] is False
        assert annotations["readOnlyHint"] == spec.read_only


# ===========================================================================
# 4. the REAL acceptance canary: real RS256, real (temporary, no-execution)
#    dedicated CeoIngress + Runtime.  Never touches a production socket.
# ===========================================================================


@pytest.fixture
def short_socket_root():
    value = Path(tempfile.mkdtemp(prefix="bsc-e1-", dir="/tmp"))
    try:
        yield value
    finally:
        shutil.rmtree(value, ignore_errors=True)


def _git_repo(path: Path, *, content: str | None = None) -> str:
    """Init a one-commit repo at ``path``. ``content`` (default: the path's
    own name) seeds the commit so two repos created in the same wall-clock
    second never collide on an identical commit sha -- git's commit hash
    covers only tree+metadata, not the filesystem path, so two repos with
    byte-identical content and same-second timestamps ARE the same sha."""

    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "e1@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "E1"], check=True)
    (path / "README.md").write_text(f"# fixture: {content or path.name}\n")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", f"fixture: {content or path.name}"], check=True)
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], check=True, stdout=subprocess.PIPE, text=True
    ).stdout.strip()


class _NoExecutionSupervisor:
    """CeoIngress never dispatches through this path, so the supervisor is
    exercised only for restart reconciliation -- mirrors the identical fixture
    already used by ``tests/test_executive_ceo_ingress.py``."""

    def reconcile_restart(self, *, requeue_lost: bool = False) -> list[Any]:
        return []


class _RealGitGroundingProvider:
    """The SERVER side's injected grounding provider for this canary -- reads
    the SAME two real temp git repos the client-side app independently reads
    via ``gateway.observe_trusted_grounding``, so both sides agree by
    construction on real (not synthetic-literal) SHAs."""

    def __init__(self, *, mastermind_root: Path, macro_root: Path) -> None:
        self._mastermind_root = mastermind_root
        self._macro_root = macro_root

    def observe(self) -> dict[str, str]:
        return {
            "mastermind_sha": ceo_boot_packet.git_sha(self._mastermind_root),
            "macro_sha": ceo_boot_packet.git_sha(self._macro_root),
            "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA,
        }


def _service_config(tmp_path: Path, *, socket_root: Path) -> ServiceConfig:
    source, base_sha = _proof_source(tmp_path)
    return ServiceConfig(
        runtime_root=tmp_path / "runtime",
        socket_path=socket_root / "operator.sock",
        proof_source_repository=source,
        proof_workspace_root=tmp_path / "workspaces",
        proof_base_sha=base_sha,
        allowed_peer_uids=(os.geteuid(),),
        shutdown_grace_seconds=0.2,
    )


def _proof_source(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "proof-source"
    sha = _git_repo(source)
    return source, sha


def _real_service(
    tmp_path: Path,
    *,
    socket_root: Path,
    mastermind_root: Path,
    macro_root: Path,
    peer_uid: int | None = None,
    armed: bool = True,
) -> ExecutiveControlService:
    config = _service_config(tmp_path, socket_root=socket_root)

    def factory(_runtime: Runtime) -> _NoExecutionSupervisor:
        return _NoExecutionSupervisor()

    return ExecutiveControlService(
        config,
        supervisor_factory=factory,
        service_state="READY",
        ceo_ingress_socket_path=socket_root / "ceo-ingress.sock",
        ceo_ingress_peer_uid=peer_uid if peer_uid is not None else os.geteuid(),
        ceo_ingress_grounding_provider=_RealGitGroundingProvider(
            mastermind_root=mastermind_root, macro_root=macro_root
        ),
        ceo_ingress_armed=armed,
    )


def run(coro):
    return asyncio.run(coro)


def _async_client(app: Any) -> httpx.AsyncClient:
    """An HTTP client driving ``app`` on the SAME event loop as the caller.

    ``starlette.testclient.TestClient`` is synchronous: it drives its ASGI
    app from a portal thread with its OWN event loop. Calling it from inside
    a coroutine that also owns a real, concurrently-running
    ``ExecutiveControlService`` (this file's real-canary tests) starves that
    service's own asyncio tasks for the duration of the synchronous call --
    the connection is accepted at the OS level but never read by the
    service's accept loop, which manifests as a spurious client-side read
    timeout (independently confirmed during development: the identical
    ``CeoIngressClient`` call succeeds immediately when awaited directly on
    the SAME loop as the service). ``httpx.AsyncClient`` + ``ASGITransport``
    runs cooperatively on the current loop instead, so it never fights the
    service for that loop's attention.
    """

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://e1-test")


def _real_app_settings(
    rsa_key: rsa.RSAPrivateKey,
    *,
    mastermind_root: Path,
    macro_root: Path,
    ceo_ingress_socket_path: Path,
) -> AppSettings:
    return AppSettings(
        policies=AppPolicies(read=_read_policy(), submit=_submit_policy()),
        mastermind_root=mastermind_root,
        macro_root_flag=str(macro_root),
        environ={},
        ceo_ingress_socket_path=str(ceo_ingress_socket_path),
        jwks_cache=_FakeJwksCache(rsa_key),
        clock=lambda: NOW,
    )


def test_real_positive_canary_queues_zero_attempts_zero_workers(rsa_key, tmp_path, short_socket_root):
    mastermind_root = tmp_path / "mastermind"
    macro_root = tmp_path / "macro"
    _git_repo(mastermind_root)
    (macro_root / "scripts").mkdir(parents=True)
    (macro_root / "scripts" / "agentos.py").write_text("")
    (macro_root / "agentos").mkdir()
    _git_repo(macro_root)

    async def exercise():
        service = _real_service(
            tmp_path, socket_root=short_socket_root, mastermind_root=mastermind_root, macro_root=macro_root
        )
        await service.start()
        try:
            settings = _real_app_settings(
                rsa_key,
                mastermind_root=mastermind_root,
                macro_root=macro_root,
                ceo_ingress_socket_path=service.ceo_ingress_socket_path,
            )
            app = create_app(settings)
            token = _submit_token(rsa_key)
            payload = {
                "arguments": {
                    "operation_key": "e1-real-canary-001",
                    "objective": "Read the Q3 board packet and summarize open risks.",
                    "department": "executive-infrastructure",
                    "priority": 5,
                    "execution_profile": "research_only",
                }
            }
            async with _async_client(app) as client:
                response = await client.post(
                    "/v1/tools/submit_ceo_intent", json=payload, headers={"Authorization": f"Bearer {token}"}
                )
                assert response.status_code == 200
                body = response.json()
                assert body["ok"] is True
                assert body["status"] == STATUS_ACCEPTED
                receipt = body["receipt"]
                assert receipt["status"] == "QUEUED"
                assert receipt["dispatched"] is False
                job_id = receipt["job_id"]

                # Independent server-side read-back: zero Attempts, zero Workers.
                job = service.runtime.jobs.get_job(job_id)
                assert job is not None
                assert service.runtime.attempts.list_attempts() == []
                assert service.runtime.workers.list_workers() == []
                assert len(service.runtime.jobs.list_jobs()) == 1

                # Same request_ref + same payload -> stable duplicate readback.
                response_again = await client.post(
                    "/v1/tools/submit_ceo_intent", json=payload, headers={"Authorization": f"Bearer {token}"}
                )
                assert response_again.status_code == 200
                body_again = response_again.json()
                assert body_again["status"] == STATUS_ACCEPTED
                assert body_again["receipt"]["job_id"] == job_id
                assert body_again["receipt"]["duplicate"] is True

                # Same request_ref + CHANGED payload -> operation_conflict, zero
                # second Job.
                changed_payload = json.loads(json.dumps(payload))
                changed_payload["arguments"]["priority"] = 99
                response_conflict = await client.post(
                    "/v1/tools/submit_ceo_intent",
                    json=changed_payload,
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert response_conflict.status_code == 409
                assert response_conflict.json()["status"] == STATUS_CONFLICT
                assert service.runtime.jobs.list_jobs() == [job]
        finally:
            await service.close()

    run(exercise())


def test_real_grounding_mismatch_refuses_with_zero_job(rsa_key, tmp_path, short_socket_root):
    mastermind_root = tmp_path / "mastermind"
    macro_root = tmp_path / "macro"
    other_macro_root = tmp_path / "other-macro"
    _git_repo(mastermind_root)
    for root in (macro_root, other_macro_root):
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "agentos.py").write_text("")
        (root / "agentos").mkdir()
        _git_repo(root)

    async def exercise():
        # Server trusts `other_macro_root`'s sha; client (app) claims
        # `macro_root`'s sha -- an honest but DIFFERENT observation.
        service = _real_service(
            tmp_path,
            socket_root=short_socket_root,
            mastermind_root=mastermind_root,
            macro_root=other_macro_root,
        )
        await service.start()
        try:
            settings = _real_app_settings(
                rsa_key,
                mastermind_root=mastermind_root,
                macro_root=macro_root,
                ceo_ingress_socket_path=service.ceo_ingress_socket_path,
            )
            app = create_app(settings)
            token = _submit_token(rsa_key)
            payload = {
                "arguments": {
                    "operation_key": "e1-grounding-mismatch-001",
                    "objective": "Read the Q3 board packet and summarize open risks.",
                    "department": "executive-infrastructure",
                    "priority": 5,
                    "execution_profile": "research_only",
                }
            }
            async with _async_client(app) as client:
                response = await client.post(
                    "/v1/tools/submit_ceo_intent", json=payload, headers={"Authorization": f"Bearer {token}"}
                )
                body = response.json()
                assert body["status"] == "refused"
                assert body["error"]["code"] == "grounding_mismatch"
                assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_real_wrong_peer_uid_refuses_before_business_access(rsa_key, tmp_path, short_socket_root):
    mastermind_root = tmp_path / "mastermind"
    macro_root = tmp_path / "macro"
    _git_repo(mastermind_root)
    (macro_root / "scripts").mkdir(parents=True)
    (macro_root / "scripts" / "agentos.py").write_text("")
    (macro_root / "agentos").mkdir()
    _git_repo(macro_root)

    async def exercise():
        service = _real_service(
            tmp_path,
            socket_root=short_socket_root,
            mastermind_root=mastermind_root,
            macro_root=macro_root,
            peer_uid=os.geteuid() + 1,
        )
        await service.start()
        try:
            settings = _real_app_settings(
                rsa_key,
                mastermind_root=mastermind_root,
                macro_root=macro_root,
                ceo_ingress_socket_path=service.ceo_ingress_socket_path,
            )
            app = create_app(settings)
            token = _submit_token(rsa_key)
            payload = {
                "arguments": {
                    "operation_key": "e1-peer-denied-001",
                    "objective": "Read the Q3 board packet and summarize open risks.",
                    "department": "executive-infrastructure",
                    "priority": 5,
                    "execution_profile": "research_only",
                }
            }
            async with _async_client(app) as client:
                response = await client.post(
                    "/v1/tools/submit_ceo_intent", json=payload, headers={"Authorization": f"Bearer {token}"}
                )
                body = response.json()
                assert body["status"] == "refused"
                assert body["error"]["code"] == "peer_denied"
                assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    run(exercise())


def test_ingress_socket_entirely_absent_is_reported_ingress_unavailable(rsa_key, tmp_path):
    _git_repo(tmp_path / "mastermind")
    macro_root = tmp_path / "macro"
    (macro_root / "scripts").mkdir(parents=True)
    (macro_root / "scripts" / "agentos.py").write_text("")
    (macro_root / "agentos").mkdir()
    _git_repo(macro_root)

    settings = _real_app_settings(
        rsa_key,
        mastermind_root=tmp_path / "mastermind",
        macro_root=macro_root,
        ceo_ingress_socket_path=tmp_path / "nothing-here.sock",
    )
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=True)
    token = _submit_token(rsa_key)
    payload = {
        "arguments": {
            "operation_key": "e1-unavailable-001",
            "objective": "Read the Q3 board packet and summarize open risks.",
            "department": "executive-infrastructure",
            "priority": 5,
            "execution_profile": "research_only",
        }
    }
    response = client.post(
        "/v1/tools/submit_ceo_intent", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 503
    assert response.json()["status"] == "ingress_unavailable"


def test_reconcile_endpoint_never_5xxs_on_a_backend_contract_defect(rsa_key, tmp_path, monkeypatch):
    """If a receipt-shaped AdmissionError somehow escapes reconciliation (a
    backend contract defect -- e.g. a corrupted ``dispatched`` field), the
    HTTP edge must still answer with a bounded 400, never let the exception
    reach Starlette's generic 500 handler."""

    import integrations.mastermind_executive_app.app as app_module

    async def raising_reconcile(client, *, socket_path, request_ref):
        raise app_module.AdmissionError("backend_refused", "Executive CEO ingress backend refused the request")

    monkeypatch.setattr(app_module, "reconcile_by_request_ref", raising_reconcile)

    _git_repo(tmp_path)
    client, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _submit_token(rsa_key)
    response = client.post(
        "/v1/tools/submit_ceo_intent/reconcile",
        json={"request_ref": "req-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "backend_refused"


# ===========================================================================
# 5. restart statelessness
# ===========================================================================


def test_two_independent_app_instances_behave_identically(rsa_key, tmp_path):
    """A fresh AppSettings + create_app() call behaves exactly like the
    first -- proves there is no module-level cache/session surviving a
    process restart."""

    _git_repo(tmp_path)
    client_one, _ = _client(rsa_key, mastermind_root=tmp_path)
    client_two, _ = _client(rsa_key, mastermind_root=tmp_path)
    token = _read_token(rsa_key)
    response_one = client_one.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    response_two = client_two.post(
        "/v1/tools/executive_state", json={"arguments": {}}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response_one.status_code == response_two.status_code == 200
    # Neither instance's success depends on having seen the other's request.
    assert response_one.json()["ok"] is True
    assert response_two.json()["ok"] is True
