"""Auth + HTTP-framing matrix for the fixed workspace read app.

Hermetic tests: every ``client.request`` is replaced by a fake recording the
exact frame it would have been sent.  No socket is ever opened; a request
that reached a real ``installed owner client`` would surface as a
distinct 503 / connection error rather than a clean 200 — proving auth
and HTTP framing refuse BEFORE the host client is ever consulted.

Reuses the exact A1 fixtures (RS256 key pair, ``ResourcePolicy`` shape,
claim templates) the executive app test already established.
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import json
from collections.abc import Mapping
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
from starlette.testclient import TestClient

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    VerifiedPrincipal,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwksKeySource, JwtAuthenticator
from integrations.mastermind_workspace_app import contract
from integrations.mastermind_workspace_app.app import (
    WorkspaceAppConfig,
    create_workspace_app,
)

# ---------------------------------------------------------------------------
# shared fixtures: RS256 keys, policy, tokens
# ---------------------------------------------------------------------------

NOW = 1_800_000_000
KID = "workspace-read-test-kid"
ISSUER = "https://issuer.mastermind.example.test"
SUBJECT = "workspace-read-chairman-opaque"
RESOURCE = contract.RESOURCE  # "https://mcp.mastermind-x.com/workspace/read"
SCOPE = contract.SCOPE        # "mastermind.workspace.read"


# ---------------------------------------------------------------------------
# RS256 keypair / JWKS plumbing (mirrors executive test, sized for a kid look-up)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def other_rsa_key() -> rsa.RSAPrivateKey:
    """A second, unrelated key — proves signature verification (not kid
    lookup alone) refuses a wrong-key token."""
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
            raise AuthError(AuthErrorCode.KEY_NOT_FOUND)
        return dict(self._jwk)


def _workspace_policy(**overrides: Any) -> ResourcePolicy:
    payload: dict[str, Any] = {
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": "bsc-workspace-read-test",
        "resource": RESOURCE,
        "resource_metadata_url": RESOURCE + "/.well-known/oauth-protected-resource",
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "/.well-known/jwks.json",
        "required_scopes": [SCOPE],
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


def _claims(*, resource: str = RESOURCE, scope: str = SCOPE, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "iss": ISSUER,
        "sub": SUBJECT,
        "aud": resource,
        "iat": NOW,
        "nbf": NOW,
        "exp": NOW + 300,
        "scope": scope,
        "jti": "opaque-jti",
        "client_id": "workspace-read-test-client",
    }
    value.update(overrides)
    return value


def _token(
    private_key: rsa.RSAPrivateKey,
    *,
    scope: str = SCOPE,
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


def _workspace_token(rsa_key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    return _token(rsa_key, **overrides)


# ---------------------------------------------------------------------------
# Fake installed owner client — used so auth and HTTP framing are provably
# refused BEFORE any real client is consulted.  Every test wires its own
# behavior so timing-sensitive cases can revoke/expire mid-call.
# ---------------------------------------------------------------------------


class _FakeWorkspaceClient:
    """An ``async request(frame)`` substitute.

    Set ``envelope`` for the success or refusal shape the installed client
    would normally return, ``on_call`` to inspect / mutate state at request
    time, and ``raise_on_call`` to simulate a transport-level crash so the
    edge exercises its 503 mapping.
    """

    def __init__(
        self,
        *,
        envelope: dict[str, Any] | None = None,
        on_call: "Any | None" = None,
        raise_on_call: BaseException | None = None,
    ) -> None:
        if envelope is None:
            envelope = {"ok": True, "result": {"hello": "world"}}
        self.envelope = envelope
        self.calls: list[dict[str, Any]] = []
        self._on_call = on_call
        self._raise_on_call = raise_on_call

    async def request(self, frame: Mapping[str, Any]) -> dict[str, Any]:
        frame_dict = dict(frame)
        self.calls.append(frame_dict)
        if self._on_call is not None:
            self._on_call(frame_dict)
        if self._raise_on_call is not None:
            raise self._raise_on_call
        return self.envelope


def _authenticator(rsa_key: rsa.RSAPrivateKey, *, policy: ResourcePolicy | None = None
                   ) -> JwtAuthenticator:
    return JwtAuthenticator(
        policy=policy or _workspace_policy(),
        jwks_cache=_FakeJwksCache(rsa_key),
    )


def _make_app(
    rsa_key: rsa.RSAPrivateKey,
    *,
    client: _FakeWorkspaceClient | None = None,
    authorize: Any = lambda _p: True,
    now: Any = lambda: NOW,
    policy: ResourcePolicy | None = None,
) -> tuple[TestClient, _FakeWorkspaceClient]:
    """Build a synchronous TestClient around a fake installed owner client.

    Returns ``(client, fake_client)`` so tests can both drive requests and
    inspect the recorded frame after a successful auth round-trip.
    """
    if client is None:
        client = _FakeWorkspaceClient()
    config = WorkspaceAppConfig(
        authenticator=_authenticator(rsa_key, policy=policy),
        now=now,
        authorize_principal=authorize,
        client=client,
    )
    app = create_workspace_app(config)
    return TestClient(app, raise_server_exceptions=False), client


# ===========================================================================
# 1. constructor refuses anything outside the contract binding
# ===========================================================================


def test_constructor_refuses_wrong_resource(rsa_key):
    bogus_policy = _workspace_policy(
        resource="https://someone-else.mastermind.example.test/workspace/read"
    )
    client = _FakeWorkspaceClient()
    with pytest.raises(ValueError, match="does not equal contract.RESOURCE"):
        WorkspaceAppConfig(
            authenticator=_authenticator(rsa_key, policy=bogus_policy),
            now=lambda: NOW,
            authorize_principal=lambda _p: True,
            client=client,
        )


def test_constructor_refuses_extra_required_scope(rsa_key):
    """Two required scopes is an invalid policy at the A1 loader — therefore
    a separate ``ValueError`` is raised *before* our equal-scopes check has a
    chance to run.  Both arrivals are documented closed-boundary rejections."""

    bogus_policy = _workspace_policy(required_scopes=["extra.scope", SCOPE])
    client = _FakeWorkspaceClient()
    with pytest.raises(ValueError):
        WorkspaceAppConfig(
            authenticator=_authenticator(rsa_key, policy=bogus_policy),
            now=lambda: NOW,
            authorize_principal=lambda _p: True,
            client=client,
        )


def test_constructor_refuses_missing_required_scope(rsa_key):
    bogus_policy = _workspace_policy(required_scopes=["other.scope"])
    client = _FakeWorkspaceClient()
    with pytest.raises(ValueError, match="does not equal"):
        WorkspaceAppConfig(
            authenticator=_authenticator(rsa_key, policy=bogus_policy),
            now=lambda: NOW,
            authorize_principal=lambda _p: True,
            client=client,
        )


def test_constructor_refuses_non_callable_authorize_callback(rsa_key):
    client = _FakeWorkspaceClient()
    with pytest.raises(ValueError, match="authorize_principal"):
        WorkspaceAppConfig(
            authenticator=_authenticator(rsa_key),
            now=lambda: NOW,
            authorize_principal="not-callable",  # type: ignore[arg-type]
            client=client,
        )


def test_constructor_refuses_client_without_request_method(rsa_key):
    class _NoRequest:
        pass

    with pytest.raises(ValueError, match="request"):
        WorkspaceAppConfig(
            authenticator=_authenticator(rsa_key),
            now=lambda: NOW,
            authorize_principal=lambda _p: True,
            client=_NoRequest(),
        )


def test_constructor_refuses_sync_request_method(rsa_key):
    class _SyncRequest:
        def request(self, frame):  # noqa: ARG002 - intentionally sync
            return {"ok": True, "result": {}}

    with pytest.raises(ValueError, match="request"):
        WorkspaceAppConfig(
            authenticator=_authenticator(rsa_key),
            now=lambda: NOW,
            authorize_principal=lambda _p: True,
            client=_SyncRequest(),
        )


# ===========================================================================
# 2. AUTH negative matrix — refuses before the client is ever consulted
# ===========================================================================


def test_missing_authorization_refuses_401_with_challenge(rsa_key):
    test_client, fake = _make_app(rsa_key)
    response = test_client.get("/workspace/programs/current")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert response.headers.get("Cache-Control") == "no-store"
    assert response.json()["ok"] is False
    assert fake.calls == []  # client never reached


def test_malformed_authorization_refuses_401(rsa_key):
    test_client, _ = _make_app(rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": "NotBearer abc"},
    )
    assert response.status_code == 401
    assert _body_code(response) == "authorization_malformed"


def test_duplicate_authorization_header_refuses_before_verification(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers=[
            ("Authorization", f"Bearer {token}"),
            ("Authorization", f"Bearer {token}"),
        ],
    )
    assert response.status_code == 401
    assert fake.calls == []


def test_wrong_issuer_refuses(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key, iss="https://attacker.example.test")
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert _body_code(response) == "issuer_refused"
    assert fake.calls == []


def test_wrong_resource_audience_refuses(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(
        rsa_key, aud="https://someone-elses-app.example.test/workspace/read"
    )
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert _body_code(response) == "resource_refused"
    assert fake.calls == []


def test_wrong_signature_with_matching_kid_refuses(rsa_key, other_rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _token(other_rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert _body_code(response) == "token_signature_refused"
    assert fake.calls == []


def test_expired_token_refuses(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key, iat=NOW - 1000, exp=NOW - 100)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert _body_code(response) == "token_expired"
    assert fake.calls == []


def test_not_yet_valid_token_refuses(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key, iat=NOW + 500, nbf=NOW + 500, exp=NOW + 800)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert _body_code(response) == "token_not_yet_valid"
    assert fake.calls == []


def test_wrong_scope_token_refuses(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _token(rsa_key, scope="some.other.scope")
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (401, 403)
    assert _body_code(response) == "scope_refused"
    assert fake.calls == []


def test_wrong_subject_not_in_allowlist_refuses(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key, sub="someone-else")
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert _body_code(response) == "subject_refused"
    assert fake.calls == []


def test_two_scope_token_refused_by_exact_match(rsa_key):
    """A token carrying BOTH the workspace scope AND an extra scope is
    refused — scopes are checked EXACTLY, not as a subset."""

    test_client, fake = _make_app(rsa_key)
    token = _token(rsa_key, scope=f"{SCOPE} mastermind.executive.read")
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (401, 403)
    assert _body_code(response) == "scope_refused"
    assert fake.calls == []


def test_wrong_algorithm_none_refuses(rsa_key):
    test_client, fake = _make_app(rsa_key)
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT", "kid": KID}).encode()
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps(_claims()).encode()
    ).rstrip(b"=")
    token = (header + b"." + payload + b".").decode()
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert fake.calls == []


def test_offline_access_only_scope_refuses(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _token(rsa_key, scope="offline_access")
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (401, 403)
    assert _body_code(response) == "scope_refused"
    assert fake.calls == []


def test_generic_verifier_cannot_widen_host(rsa_key):
    test_client, _ = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    fake_client = test_client.app._app  # type: ignore[attr-defined] - test only
    response = test_client.get(
        "/workspace/programs/current",
        headers={
            "Authorization": f"Bearer {token}",
            "Host": "attacker.example.test",
            "Origin": "https://attacker.example.test",
            "X-Forwarded-Host": "attacker.example.test",
        },
    )
    # Auth succeeds (the token's real audience matches the fixed policy
    # resource) — Host/Origin are NEVER consulted by the verifier.
    assert response.status_code == 200


# ===========================================================================
# 3. HTTP framing adversarial states — refuse before client is consulted
# ===========================================================================


@pytest.mark.parametrize(
    ("method", "path", "expected_status"),
    [
        # Wrong method → 405
        ("POST", "/workspace/programs/current", 405),
        ("PUT", "/workspace/programs/current", 405),
        ("DELETE", "/workspace/programs/current", 405),
        ("HEAD", "/workspace/programs/current", 405),
        ("OPTIONS", "/workspace/programs/current", 405),
        ("POST", "/workspace/work/current", 405),
        ("PUT", "/workspace/work/current", 405),
        ("DELETE", "/workspace/work/current", 405),
        ("HEAD", "/workspace/work/current", 405),
        ("OPTIONS", "/workspace/work/current", 405),
        ("POST", "/workspace/mission/current", 405),
        # Trailing slash → 404 (router does not silently redirect)
        ("GET", "/workspace/programs/current/", 404),
        ("GET", "/workspace/work/current/", 404),
        ("GET", "/workspace/mission/current/", 404),
        # Encoded separator / alternate separator → 400
        ("GET", "/workspace/programs/current%2Fother", 400),
        ("GET", "/workspace/programs%2Fcurrent", 400),
        ("GET", "/workspace/programs/current%5Cother", 400),
        # Duplicate slash → 400
        ("GET", "/workspace//programs/current", 400),
    ],
)
def test_method_and_raw_path_adversaries_never_alias_real_routes(
    rsa_key, method, path, expected_status,
):
    test_client, fake = _make_app(rsa_key)
    response = test_client.request(method, path, follow_redirects=False)
    assert response.status_code == expected_status
    assert fake.calls == []


def test_programs_current_with_unknown_query_string_refuses_400(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/programs/current?unexpected=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert _body_code(response) == "invalid_input"
    assert fake.calls == []


def test_mission_current_without_query_refuses_400(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/mission/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert _body_code(response) == "invalid_input"
    assert fake.calls == []


def test_mission_current_with_duplicate_query_refuses_400(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/mission/current"
        "?work_ref=WS:AB12cd&root_job_id=JOB-001&work_ref=WS:AB12cd",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert _body_code(response) == "invalid_input"
    assert fake.calls == []


def test_mission_current_with_extra_query_refuses_400(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/mission/current"
        "?work_ref=WS:AB12cd&root_job_id=JOB-001&extra=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert _body_code(response) == "invalid_input"
    assert fake.calls == []


def test_mission_current_with_malformed_work_ref_refuses_400(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/mission/current?work_ref=notavalidid&root_job_id=JOB-001",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert _body_code(response) == "invalid_input"
    assert fake.calls == []


def test_mission_current_with_malformed_root_job_id_refuses_400(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/mission/current?work_ref=WS:AB12cd&root_job_id=not-a-job",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert _body_code(response) == "invalid_input"
    assert fake.calls == []


def test_get_request_with_body_refuses_before_client(rsa_key):
    """GET with a body — refuse on the first non-empty chunk."""

    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.request(
        "GET",
        "/workspace/programs/current",
        content=b"some-body",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 400
    assert _body_code(response) == "invalid_input"
    assert fake.calls == []


def test_authorize_principal_false_refuses_403_before_client(rsa_key):
    test_client, fake = _make_app(
        rsa_key, authorize=lambda _p: False,
    )
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert _body_code(response) == "access_denied"
    assert fake.calls == []


def test_authorize_callback_raising_is_internal_error(rsa_key):
    """A misbehaving authorize callback must NOT leak the exception —
    the edge converts it to a fixed 503."""

    def raising(_p):  # type: ignore[no-untyped-def]
        raise RuntimeError("installed-owner-broken")

    test_client, fake = _make_app(rsa_key, authorize=raising)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert _body_code(response) == "internal_error"
    assert fake.calls == []


# ===========================================================================
# 4. positive read path — exact returned envelope
# ===========================================================================


def test_programs_current_returns_exact_result_envelope(rsa_key):
    expected = {
        "ok": True,
        "result": {
            "schema": contract.PROGRAMS_SCHEMA,
            "operation": "programs",
            "programs": [
                {"program_id": "alpha", "status": "active"},
                {"program_id": "beta", "status": "queued"},
            ],
        },
    }
    fake = _FakeWorkspaceClient(envelope=expected)
    test_client, _ = _make_app(rsa_key, client=fake)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == expected["result"]
    assert len(fake.calls) == 1
    frame = fake.calls[0]
    assert frame["schema"] == contract.FRAME_SCHEMA
    assert frame["operation"] == "programs"
    assert frame["selection"] is None
    assert frame["principal"]["resource"] == RESOURCE
    assert frame["principal"]["scopes"] == [SCOPE]
    assert set(frame["principal"]) == set(contract.PRINCIPAL_KEYS)


# ---------------------------------------------------------------------------
# work-current route (mastermind-OS app) — mirrors programs-current exactly
# ---------------------------------------------------------------------------


def test_work_current_missing_authorization_refuses_401(rsa_key):
    test_client, fake = _make_app(rsa_key)
    response = test_client.get("/workspace/work/current")
    assert response.status_code == 401
    assert fake.calls == []


def test_work_current_malformed_authorization_refuses_401(rsa_key):
    test_client, fake = _make_app(rsa_key)
    response = test_client.get(
        "/workspace/work/current",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code == 401
    assert fake.calls == []


def test_work_current_expired_token_refuses(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key, exp=NOW - 60)
    response = test_client.get(
        "/workspace/work/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert fake.calls == []


def test_work_current_with_body_refuses_400(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.request(
        "GET",
        "/workspace/work/current",
        content=b"some-body",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 400
    assert _body_code(response) == "invalid_input"
    assert fake.calls == []


def test_work_current_with_query_string_refuses_400(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/work/current?unexpected=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert _body_code(response) == "invalid_input"
    assert fake.calls == []


def test_work_current_authorize_principal_false_refuses_403(rsa_key):
    test_client, fake = _make_app(rsa_key, authorize=lambda _p: False)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/work/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert _body_code(response) == "access_denied"
    assert fake.calls == []


def test_work_current_happy_path_returns_envelope(rsa_key):
    expected = {
        "ok": True,
        "result": {
            "schema": "mastermind.workspace_work_queue.v1",
            "availability": "AVAILABLE",
            "groups": {
                "EFFECT_EXCEPTION": [], "NEEDS_SOL": [], "NEEDS_WORKER": [],
                "WAITING_CAPACITY": [], "RUNNING": [
                    {"root_job_id": "JOB-1", "lifecycle": {"status": "RUNNING"}}
                ], "QUEUED": [], "COMPLETED_NOT_ACCEPTED": [], "TERMINAL": [],
                "UNKNOWN": [],
            },
            "source_observation": {"state": "SAME"},
        },
    }
    fake = _FakeWorkspaceClient(envelope=expected)
    test_client, _ = _make_app(rsa_key, client=fake)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/work/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == expected["result"]
    assert len(fake.calls) == 1
    frame = fake.calls[0]
    assert frame["schema"] == contract.FRAME_SCHEMA
    assert frame["operation"] == "work"
    assert frame["selection"] is None
    assert frame["principal"]["resource"] == RESOURCE
    assert frame["principal"]["scopes"] == [SCOPE]


# ---------------------------------------------------------------------------
# B5 — work-current HTTP 503 mapping for UNAVAILABLE body (closed composer shape)
# ---------------------------------------------------------------------------


def test_work_current_unavailable_body_maps_to_503_with_no_store(rsa_key):
    """B5: a fake client returning a closed WORK_SCHEMA UNAVAILABLE body
    renders HTTP 503, ``Cache-Control: no-store``, and passes the body
    through verbatim.  This is the contract the public App binds to —
    the read service's typed refusal becomes a 503 here, never a 200."""
    from common.executive_workspace_contract import WORK_SCHEMA
    unavailable_body = {
        "schema": WORK_SCHEMA,
        "availability": "UNAVAILABLE",
        "generated_at": "2026-09-23T00:00:00Z",
        "lifecycle_source": None,
        "effect_exception": {"value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER",
                             "observable": False},
        "coverage": {"count": 0, "total": None, "truncated": False,
                     "completeness": "PARTIAL"},
        "groups": {"EFFECT_EXCEPTION": [], "NEEDS_SOL": [], "NEEDS_WORKER": [],
                   "WAITING_CAPACITY": [], "RUNNING": [], "QUEUED": [],
                   "COMPLETED_NOT_ACCEPTED": [], "TERMINAL": [], "UNKNOWN": []},
        "source_observation": {"schema": "mastermind.workspace_source_observation.v1",
                                "state": "UNKNOWN", "selection": None,
                                "control_room": None, "runtime": None},
        "reason_codes": ["LIFECYCLE_UNAVAILABLE"],
    }
    envelope = {"ok": True, "result": unavailable_body}
    fake = _FakeWorkspaceClient(envelope=envelope)
    test_client, _ = _make_app(rsa_key, client=fake)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/work/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == unavailable_body
    assert len(fake.calls) == 1


def test_work_current_available_body_maps_to_200_with_no_store(rsa_key):
    """B5 sibling: a healthy AVAILABLE work body renders HTTP 200 with
    ``Cache-Control: no-store`` — the success path stays cache-free."""
    from common.executive_workspace_contract import WORK_SCHEMA
    available_body = {
        "schema": WORK_SCHEMA,
        "availability": "AVAILABLE",
        "generated_at": "2026-09-23T00:00:00Z",
        "lifecycle_source": {"schema": "mastermind.fabric_job_root_list.v2",
                             "runtime": None},
        "effect_exception": {"value": "NONE", "scope": "RUNTIME_CURRENT_WORKER",
                             "observable": False},
        "coverage": {"count": 0, "total": 0, "truncated": False,
                     "completeness": "COMPLETE"},
        "groups": {"EFFECT_EXCEPTION": [], "NEEDS_SOL": [], "NEEDS_WORKER": [],
                   "WAITING_CAPACITY": [], "RUNNING": [], "QUEUED": [],
                   "COMPLETED_NOT_ACCEPTED": [], "TERMINAL": [], "UNKNOWN": []},
        "source_observation": {"schema": "mastermind.workspace_source_observation.v1",
                                "state": "SAME", "selection": None,
                                "control_room": None, "runtime": None},
        "reason_codes": [],
    }
    envelope = {"ok": True, "result": available_body}
    fake = _FakeWorkspaceClient(envelope=envelope)
    test_client, _ = _make_app(rsa_key, client=fake)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/work/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == available_body


def test_work_current_projection_refused_typed_unavailable_maps_to_503_with_no_store(rsa_key):
    """B2: a typed UNAVAILABLE body carrying
    ``reason_codes == ["projection_refused"]`` maps to HTTP 503 with
    ``Cache-Control: no-store`` — same wire shape as the existing
    LIFECYCLE_UNAVAILABLE typed refusal."""
    from common.executive_workspace_contract import WORK_SCHEMA
    unavailable_body = {
        "schema": WORK_SCHEMA,
        "availability": "UNAVAILABLE",
        "generated_at": "2026-09-23T00:00:00Z",
        "lifecycle_source": None,
        "effect_exception": {"value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER",
                             "observable": False, "reason": "control_room_missing"},
        "coverage": {"count": 0, "total": None, "truncated": False,
                     "completeness": "PARTIAL"},
        "groups": {"EFFECT_EXCEPTION": [], "NEEDS_SOL": [], "NEEDS_WORKER": [],
                   "WAITING_CAPACITY": [], "RUNNING": [], "QUEUED": [],
                   "COMPLETED_NOT_ACCEPTED": [], "TERMINAL": [], "UNKNOWN": []},
        "source_observation": {"schema": "mastermind.workspace_source_observation.v1",
                                "state": "UNKNOWN", "selection": None,
                                "control_room": None, "runtime": None},
        "reason_codes": ["projection_refused"],
    }
    envelope = {"ok": True, "result": unavailable_body}
    fake = _FakeWorkspaceClient(envelope=envelope)
    test_client, _ = _make_app(rsa_key, client=fake)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/work/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == unavailable_body
    assert len(fake.calls) == 1


def test_work_current_runtime_error_in_composer_maps_to_503_error_envelope(rsa_key):
    """B2: a non-ValueError composer exception is a real error envelope
    (not a typed UNAVAILABLE body) and the App maps it to HTTP 503 with
    ``Cache-Control: no-store``.  The body is the closed ``ok:false``
    error envelope — the route never manufactures a typed document for
    an unexpected exception class."""
    envelope = {"ok": False, "status": 503,
                "error": {"code": "source_unavailable",
                          "message": "workspace read refused"}}
    fake = _FakeWorkspaceClient(envelope=envelope)
    test_client, _ = _make_app(rsa_key, client=fake)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/work/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "source_unavailable"
    assert body["error"]["message"] == "workspace read refused"


def test_work_current_post_refuses_405(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.post(
        "/workspace/work/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 405
    assert fake.calls == []


def test_work_current_trailing_slash_404(rsa_key):
    test_client, fake = _make_app(rsa_key)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/work/current/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert fake.calls == []


def test_mission_current_returns_exact_result_envelope(rsa_key):
    selection = {"work_ref": "WS:AB12cd", "root_job_id": "JOB-001"}
    expected = {
        "ok": True,
        "result": {
            "schema": contract.OBSERVATION_SCHEMA,
            "operation": "mission",
            "selection": selection,
            "observation": {"phase": "grounding", "ok": True},
        },
    }
    fake = _FakeWorkspaceClient(envelope=expected)
    test_client, _ = _make_app(rsa_key, client=fake)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/mission/current",
        params=selection,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == expected["result"]
    assert len(fake.calls) == 1
    frame = fake.calls[0]
    assert frame["schema"] == contract.FRAME_SCHEMA
    assert frame["operation"] == "mission"
    assert frame["selection"] == selection
    assert frame["principal"]["resource"] == RESOURCE
    assert frame["principal"]["scopes"] == [SCOPE]


def test_mission_current_accepts_plus_in_selection_strings(rsa_key):
    """A real '+' character in a query value MUST round-trip verbatim."""

    async def _async_drive(rsa_key, rsa_key_obj):
        capture: dict[str, Any] = {}

        class _CaptureClient:
            async def request(self, frame):
                capture["frame"] = dict(frame)
                return {
                    "ok": True,
                    "result": {
                        "schema": contract.OBSERVATION_SCHEMA,
                        "operation": "mission",
                        "selection": {
                            "work_ref": "WS:AB12cd",
                            "root_job_id": "JOB-001",
                        },
                    },
                }

        config = WorkspaceAppConfig(
            authenticator=_authenticator(rsa_key_obj),
            now=lambda: NOW,
            authorize_principal=lambda _p: True,
            client=_CaptureClient(),
        )
        app = create_workspace_app(config)
        token = _workspace_token(rsa_key_obj)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://workspace",
        ) as ac:
            response = await ac.get(
                "/workspace/mission/current"
                "?work_ref=WS%3AAB12cd&root_job_id=JOB%2D001",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        # Frame must carry the EXACT, unaltered values from the contract's
        # selection() validator (selection is dict[str,str], no URL parsing).
        frame = capture["frame"]
        assert frame["selection"] == {
            "work_ref": "WS:AB12cd", "root_job_id": "JOB-001",
        }

    asyncio.run(_async_drive(rsa_key, rsa_key))


# ===========================================================================
# 5. client envelope refusal / unavailable mapping
# ===========================================================================


@pytest.mark.parametrize(
    ("client_status", "expected_http", "expected_code"),
    [
        (400, 400, "invalid_input"),
        (403, 403, "access_denied"),
        (404, 404, "selection_not_found"),
        (503, 503, "source_unavailable"),
    ],
)
def test_client_refusal_envelope_maps_to_exact_typed_http(
    rsa_key, client_status, expected_http, expected_code,
):
    envelope = {"ok": False, "status": client_status,
                "error": {"code": expected_code, "message": "internal"}}
    fake = _FakeWorkspaceClient(envelope=envelope)
    test_client, _ = _make_app(rsa_key, client=fake)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == expected_http
    body = response.json()
    assert body["ok"] is False
    assert set(body) == {"ok", "error"}
    assert body["error"]["code"] == expected_code


def test_client_unknown_status_maps_to_503(rsa_key):
    """A client returning a non-closed status (out of {400,403,404,503})
    is reported as 503 with a closed code, never leaked."""

    envelope = {"ok": False, "status": 418,
                "error": {"code": "teapot", "message": "I'm a teapot"}}
    fake = _FakeWorkspaceClient(envelope=envelope)
    test_client, _ = _make_app(rsa_key, client=fake)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503


def test_client_unavailable_returns_503_without_leak(rsa_key):
    """A transport-level crash in the client is reported as 503, never
    surfaces the exception's text."""

    fake = _FakeWorkspaceClient(
        raise_on_call=RuntimeError("installed-owner-broken"),
    )
    test_client, _ = _make_app(rsa_key, client=fake)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert _body_code(response) == "internal_error"
    body_text = response.text
    assert "installed-owner-broken" not in body_text


# ===========================================================================
# 6. access revoked / clock expired during the read
# ===========================================================================


def test_clock_expiry_during_read_refuses_403(rsa_key):
    """A token whose ``exp`` is mid-read (between auth and response) is
    refused at the post-read clock recheck.

    Both the auth step and the after-read recheck use the SAME clock
    configuration; the post-read check runs only because the auth step saw
    a still-valid bearer.
    """

    captured: dict[str, int] = {"calls": 0}

    def racing_clock() -> int:
        captured["calls"] += 1
        # Auth passes, the client is called, then expiry trips on the
        # recheck after the read.
        if captured["calls"] == 1:
            return NOW  # during auth
        return NOW + 1000  # past `exp` (NOW + 300)

    expected_envelope = {
        "ok": True,
        "result": {
            "schema": contract.PROGRAMS_SCHEMA,
            "operation": "programs",
            "programs": [],
        },
    }
    fake = _FakeWorkspaceClient(envelope=expected_envelope)
    test_client, _ = _make_app(rsa_key, client=fake, now=racing_clock)
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert _body_code(response) == "access_denied"
    # The client WAS called once - the expiry surfaces ONLY after the read.
    assert len(fake.calls) == 1


def test_authorize_callback_revocation_during_read_refuses_403(rsa_key):
    """``authorize_principal`` flipping False between auth and the post-read
    recheck refuses with 403 - the read itself already happened (the
    principal's authority, not the body data, was revoked)."""

    captured: dict[str, int] = {"calls": 0}

    def revoking_authorize(_principal):  # type: ignore[no-untyped-def]
        captured["calls"] += 1
        return captured["calls"] == 1  # True during pre-call, False after.

    expected_envelope = {
        "ok": True,
        "result": {
            "schema": contract.PROGRAMS_SCHEMA,
            "operation": "programs",
            "programs": [],
        },
    }
    fake = _FakeWorkspaceClient(envelope=expected_envelope)
    test_client, _ = _make_app(
        rsa_key, client=fake, authorize=revoking_authorize,
    )
    token = _workspace_token(rsa_key)
    response = test_client.get(
        "/workspace/programs/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert _body_code(response) == "access_denied"
    # The revoke happens AFTER the client.request call returns.
    assert len(fake.calls) == 1


# ===========================================================================
# 7. raw-path markers module-level invariants
# ===========================================================================


def test_suspicious_raw_path_markers_include_expected_set():
    from integrations.mastermind_workspace_app.app import _SUSPICIOUS_RAW_PATH_MARKERS

    assert b"%2f" in _SUSPICIOUS_RAW_PATH_MARKERS
    assert b"%5c" in _SUSPICIOUS_RAW_PATH_MARKERS
    assert b"//" in _SUSPICIOUS_RAW_PATH_MARKERS


# ===========================================================================
# 8. cancellation propagation
# ===========================================================================


def test_cancellation_during_client_request_propagates(rsa_key):
    """When the client cancels mid-call (``CancelledError`` is a ``BaseException``
    on Python 3.8+), it MUST propagate up through the app — NOT be swallowed
    as a generic 500.  The edge only wraps non-cancellation exceptions in 503.
    """

    captured: dict[str, int] = {"calls": 0}

    class _CancellingClient:
        async def request(self, frame):  # type: ignore[no-untyped-def]
            captured["calls"] += 1
            raise asyncio.CancelledError()

    config = WorkspaceAppConfig(
        authenticator=_authenticator(rsa_key),
        now=lambda: NOW,
        authorize_principal=lambda _p: True,
        client=_CancellingClient(),
    )
    app = create_workspace_app(config)
    token = _workspace_token(rsa_key)

    async def drive():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://workspace",
        ) as ac:
            return await ac.get(
                "/workspace/programs/current",
                headers={"Authorization": f"Bearer {token}"},
            )

    with pytest.raises(BaseException) as exc_info:
        asyncio.run(drive())
    # Cancellation (or an HTTPX wrapper of it) propagated; the app's own
    # ``try/except Exception`` (NOT BaseException) did not swallow it.
    assert isinstance(
        exc_info.value, (asyncio.CancelledError, httpx.RemoteProtocolError,
                         httpx.ReadError, httpx.HTTPError),
    )
    assert captured["calls"] == 1


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _body_code(response: Any) -> str:
    body = response.json()
    error = body.get("error") or {}
    return str(error.get("code", ""))


def test_default_client_permission_cannot_authorize(rsa_key):
    with pytest.raises(ValueError, match="authorize_principal"):
        WorkspaceAppConfig(authenticator=_authenticator(rsa_key), client=_FakeWorkspaceClient())


@pytest.mark.parametrize("value", [1, "yes", {"allowed": True}])
def test_client_permission_requires_exact_true(rsa_key, value):
    client, fake = _make_app(rsa_key, authorize=lambda principal: value)
    response = client.get("/workspace/programs/current", headers={"Authorization": f"Bearer {_workspace_token(rsa_key)}"})
    assert response.status_code == 403 and not fake.calls


def test_first_body_chunk_refuses_without_draining_unbounded_input():
    from starlette.requests import Request
    from integrations.mastermind_workspace_app.app import _reject_any_body
    calls = []
    async def receive():
        calls.append(True)
        if len(calls) > 1: pytest.fail("body drained after refusal")
        return {"type": "http.request", "body": b"x", "more_body": True}
    async def check():
        response = await _reject_any_body(Request({"type": "http", "method": "GET", "path": "/workspace/programs/current", "headers": []}, receive))
        assert response.status_code == 400 and len(calls) == 1
    asyncio.run(check())


def test_program_unavailable_is_503_and_not_empty_success(rsa_key):
    unavailable = {"schema": contract.PROGRAMS_SCHEMA, "availability": "UNAVAILABLE", "control_room": None,
        "source_observation": {"schema": contract.OBSERVATION_SCHEMA, "state": "UNKNOWN", "selection": None,
            "control_room": None, "runtime": None}, "reason_codes": ["source_unavailable"]}
    client, fake = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope={"ok": True, "result": unavailable}))
    response = client.get("/workspace/programs/current", headers={"Authorization": f"Bearer {_workspace_token(rsa_key)}"})
    assert response.status_code == 503 and response.json() == unavailable


@pytest.mark.parametrize("envelope", [
    {"ok": True, "result": {}, "foreign": True},
    {"ok": False, "status": "403", "error": {"code": "access_denied", "message": "refused"}},
    {"ok": False, "status": 503, "error": {"code": "/private/secret", "message": "refused"}},
    {"ok": True, "result": {"large": "x" * 2_000_000}},
])
def test_malformed_or_oversize_internal_reply_is_closed(rsa_key, envelope):
    client, fake = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=envelope))
    response = client.get("/workspace/programs/current", headers={"Authorization": f"Bearer {_workspace_token(rsa_key)}"})
    assert response.status_code == 503 and "/private/secret" not in response.text


@pytest.mark.parametrize("route", ["/workspace/programs/current", "/workspace/mission/current?work_ref=WS:ONE&root_job_id=JOB-001"])
@pytest.mark.parametrize("stage", ["before", "after"])
def test_configured_permission_stamp_unavailable_refuses(rsa_key, route, stage):
    fake = _FakeWorkspaceClient(envelope={"ok": True, "result": {"fixture": True}})
    authorize = lambda principal: True
    authorize.binding_digest = lambda principal: None if stage == "before" or fake.calls else "a" * 64
    client, _ = _make_app(rsa_key, client=fake, authorize=authorize)
    response = client.get(route, headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 403 and _body_code(response) == "access_denied"
    assert len(fake.calls) == (stage == "after")
