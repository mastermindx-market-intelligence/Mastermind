from __future__ import annotations

import base64
import inspect
import json
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from types import MethodType

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.server.auth.provider import AccessToken, TokenVerifier
from starlette.testclient import TestClient

from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AUTH_POLICY_SCHEMA,
    AuthAuditEvent,
    AuthErrorCode,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_secretary_mcp.adapter import StewardGrounding
from integrations.mastermind_steward_app.app import build_authenticated_app
from integrations.mastermind_steward_app.projection import (
    ControlRoomStewardReadPort,
    responsibility_ref_for,
)
from integrations.mastermind_steward_app.server import (
    REQUIRED_SCOPE,
    build_contract_server,
)


MCP_PATH = "/mcp/steward/v1"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp/steward/v1"
BASE_URL = "https://mcp.example.test"
ISSUER = "https://identity.example.test/"
JWKS_URI = "https://identity.example.test/.well-known/jwks.json"
SUBJECT = "chairman-opaque"
CLIENT_ID = "chatgpt-business-client"
NOW = 1_788_000_100
ISSUED_AT = 1_788_000_000
EXPIRES_AT = 1_788_000_600
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
TOOL_CALL_BODY = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {"name": "list_responsibilities", "arguments": {}},
}
MCP_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}
_UNSET = object()


class _ForeignVerifier(TokenVerifier):
    async def verify_token(self, token: str):
        del token
        return None


class _Fetcher:
    def __init__(self, *responses: bytes | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    async def fetch(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> bytes:
        del timeout_seconds, max_bytes
        self.calls.append(url)
        if not self.responses:
            raise RuntimeError("unexpected JWKS fetch")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _Sink:
    def __init__(self) -> None:
        self.events: list[AuthAuditEvent] = []

    def emit(self, event: AuthAuditEvent) -> None:
        self.events.append(event)


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
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-steward-v1",
            "resource": "https://mcp.example.test/mcp/steward/v1",
            "resource_metadata_url": (
                "https://mcp.example.test/.well-known/"
                "oauth-protected-resource/mcp/steward/v1"
            ),
            "issuer": ISSUER,
            "authorization_servers": [ISSUER],
            "jwks_uri": JWKS_URI,
            "required_scopes": list(scopes),
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


def _base64url_uint(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return (
        base64.urlsafe_b64encode(value.to_bytes(width, "big"))
        .rstrip(b"=")
        .decode("ascii")
    )


def _rsa_jwk(
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str,
) -> dict[str, object]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kid": kid,
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": _base64url_uint(numbers.n),
        "e": _base64url_uint(numbers.e),
    }


def _jwks(*keys: Mapping[str, object]) -> bytes:
    return json.dumps(
        {"keys": list(keys)}, separators=(",", ":")
    ).encode("utf-8")


def _token(
    private_key: rsa.RSAPrivateKey,
    policy,
    *,
    kid: str = "kid-a",
    issuer: str | None = None,
    audience: str | None = None,
    subject: str = SUBJECT,
    scopes: tuple[str, ...] | None = None,
    client_id: object = CLIENT_ID,
    azp: object = _UNSET,
    jti: str = "opaque-token-id",
) -> str:
    claims: dict[str, object] = {
        "iss": issuer if issuer is not None else policy.issuer,
        "sub": subject,
        "aud": audience if audience is not None else policy.resource,
        "iat": ISSUED_AT,
        "nbf": ISSUED_AT,
        "exp": EXPIRES_AT,
        "scope": " ".join(scopes or policy.required_scopes),
        "jti": jti,
    }
    if client_id is not _UNSET:
        claims["client_id"] = client_id
    if azp is not _UNSET:
        claims["azp"] = azp
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": kid, "typ": "at+jwt"},
    )


def _real_verifier(
    policy,
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str = "kid-a",
) -> tuple[MastermindTokenVerifier, _Fetcher, _Sink]:
    fetcher = _Fetcher(_jwks(_rsa_jwk(private_key, kid=kid)))
    cache = BoundedJwksCache(
        policy=policy,
        fetcher=fetcher,
        monotonic=lambda: 100.0,
    )
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=cache)
    sink = _Sink()
    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=policy,
        now=lambda: NOW,
        audit_sink=sink,
    )
    return verifier, fetcher, sink


def _stub_verifier(
    policy,
    result: AccessToken | None = None,
) -> tuple[MastermindTokenVerifier, list[str]]:
    fetcher = _Fetcher()
    cache = BoundedJwksCache(
        policy=policy,
        fetcher=fetcher,
        monotonic=lambda: 100.0,
    )
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=cache)
    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=policy,
        now=lambda: NOW,
        audit_sink=_Sink(),
    )
    calls: list[str] = []

    async def verify_token(_self, token: str):
        calls.append(token)
        return result

    verifier.verify_token = MethodType(verify_token, verifier)  # type: ignore[method-assign]
    return verifier, calls


def _build(*, result: AccessToken | None = None):
    policy = _policy()
    verifier, calls = _stub_verifier(policy, result)
    port = _Port()
    app = build_authenticated_app(
        build_contract_server(port),
        policy=policy,
        token_verifier=verifier,
    )
    return app, policy, calls, port


def _projection_snapshot() -> dict[str, object]:
    return {
        "schema": "mastermind.chairman_control_room.v1",
        "generated_at": "2026-09-01T12:04:00Z",
        "sources": {
            "agent_os_state_generated_at": "2026-09-01T12:03:00Z",
            "runtime_db_present": True,
            "bindings_path_present": True,
        },
        "degraded": [],
        "attention": {
            "chairman": [],
            "ceo": [
                {
                    "attention_id": "ATTENTION-RAW-001",
                    "kind": "decision",
                    "target": "ceo",
                    "source": "agent_os",
                    "job_id": None,
                    "workstream": "WS:ALPHA",
                    "status": None,
                    "reason": "Ship or hold the Alpha One rollout?",
                    "evidence": [],
                    "existing_next_actions": [],
                }
            ],
            "coo": [],
        },
        "work": [
            {
                "work_ref": "WS:ALPHA",
                "agent_os": {
                    "title": "Alpha program",
                    "program": "Alpha One",
                    "next_action": "Get the CEO ruling on ship vs hold",
                    "status": "in_progress",
                    "state": "in_progress",
                    "reason_code": "workstream_active",
                    "reason": "Authored workstream status is active.",
                    "depends_on": [],
                    "unmet_dependencies": [],
                },
                "executive": {
                    "jobs": [
                        {
                            "job_id": "JOB-RAW-001",
                            "status": "queued",
                            "workstream": "WS:ALPHA",
                        }
                    ],
                    "joined_by": "ceo_intent_provenance",
                },
                "github": {"prs": []},
                "attention_ids": ["ATTENTION-RAW-001"],
                "bindings": [
                    {
                        "binding_id": "11111111-1111-4111-8111-111111111111",
                        "work_ref": "WS:ALPHA",
                        "role": "ceo",
                        "provider": "chatgpt",
                        "seat_ref": "SEAT-RAW-001",
                        "locator_kind": "chat",
                        "observed_at": "2026-09-01T12:03:30Z",
                        "last_verified_at": "2026-09-01T12:04:30Z",
                    }
                ],
                "disagreements": [],
            }
        ],
        "unjoined_open_prs": [],
        "unbound_surfaces": [],
        "binding_conflicts": [],
    }


def _challenge(response) -> str:
    return response.headers["www-authenticate"]


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_authenticated_app_exposes_metadata_and_readiness_tracks_lifespan():
    app, policy, verifier_calls, port = _build()
    client = TestClient(app, base_url=BASE_URL)

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
    assert verifier_calls == []
    assert port.calls == []


def test_canonical_mcp_path_uses_a1_missing_and_invalid_token_challenges():
    app, policy, verifier_calls, port = _build()
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

    assert verifier_calls == ["invalid-token"]
    assert port.calls == []


def test_valid_bearer_is_required_scope_bound_and_request_auth_does_not_leak():
    policy = _policy()
    verifier, verifier_calls = _stub_verifier(policy, _access_token(policy))
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

        missing = client.post(MCP_PATH, headers=MCP_HEADERS, json=MCP_BODY)
        assert missing.status_code == 401
        assert missing.json() == {"error": "invalid_token"}

    assert verifier_calls == ["valid-token"]
    assert port.calls == []


def test_valid_token_without_steward_scope_gets_a1_insufficient_scope_challenge():
    policy = _policy()
    verifier, verifier_calls = _stub_verifier(
        policy,
        _access_token(
            policy,
            token="wrong-scope-token",
            scopes=("mastermind.executive.read",),
        ),
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
    assert verifier_calls == ["wrong-scope-token"]
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
    verifier, verifier_calls = _stub_verifier(
        policy, _access_token(policy, token="must-not-be-read")
    )
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
    assert verifier_calls == []
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
    verifier, verifier_calls = _stub_verifier(
        policy, _access_token(policy, token="must-not-be-read")
    )
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
    assert verifier_calls == []
    assert port.calls == []
    assert "attacker.test" not in response.text
    assert "must-not-be-read" not in response.text


def test_oversized_body_and_root_path_injection_refuse_before_verifier():
    oversized_policy = _policy()
    oversized_verifier, oversized_calls = _stub_verifier(
        oversized_policy,
        _access_token(oversized_policy, token="must-not-be-read"),
    )
    oversized_port = _Port()
    oversized_app = build_authenticated_app(
        build_contract_server(oversized_port),
        policy=oversized_policy,
        token_verifier=oversized_verifier,
    )
    headers = {
        **MCP_HEADERS,
        "authorization": "Bearer must-not-be-read",
    }

    with TestClient(oversized_app, base_url=BASE_URL) as client:
        oversized = client.post(
            MCP_PATH,
            headers=headers,
            content=b"x" * (1024 * 1024 + 1),
        )

    injected_policy = _policy()
    injected_verifier, injected_calls = _stub_verifier(
        injected_policy,
        _access_token(injected_policy, token="must-not-be-read"),
    )
    injected_port = _Port()
    injected_app = build_authenticated_app(
        build_contract_server(injected_port),
        policy=injected_policy,
        token_verifier=injected_verifier,
    )
    with TestClient(
        injected_app,
        base_url=BASE_URL,
        root_path="/injected-prefix",
    ) as client:
        injected = client.post(MCP_PATH, headers=headers, json=MCP_BODY)

    assert oversized.status_code == 413
    assert injected.status_code == 404
    assert oversized_calls == []
    assert oversized_port.calls == []
    assert injected_calls == []
    assert injected_port.calls == []


def test_authenticated_app_refuses_cross_realm_scope_policy():
    policy = _policy(scopes=("mastermind.executive.read",))
    verifier, _calls = _stub_verifier(policy)
    with pytest.raises(ValueError, match="exactly mastermind.steward.read"):
        build_authenticated_app(
            build_contract_server(_Port()),
            policy=policy,
            token_verifier=verifier,
        )


def test_authenticated_app_refuses_non_a1_verifier():
    with pytest.raises(TypeError, match="MastermindTokenVerifier"):
        build_authenticated_app(
            build_contract_server(_Port()),
            policy=_policy(),
            token_verifier=_ForeignVerifier(),
        )


def test_authenticated_app_has_no_operator_host_widening_parameter():
    assert "extra_allowed_hosts" not in inspect.signature(
        build_authenticated_app
    ).parameters


def test_real_signed_token_performs_one_authenticated_tool_call(
    rsa_key: rsa.RSAPrivateKey,
):
    policy = _policy()
    verifier, fetcher, sink = _real_verifier(policy, rsa_key)
    token = _token(rsa_key, policy)
    port = _Port()
    app = build_authenticated_app(
        build_contract_server(port),
        policy=policy,
        token_verifier=verifier,
    )

    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            MCP_PATH,
            headers={**MCP_HEADERS, "authorization": f"Bearer {token}"},
            json=TOOL_CALL_BODY,
        )
        missing = client.post(MCP_PATH, headers=MCP_HEADERS, json=TOOL_CALL_BODY)

    assert response.status_code == 200
    payload = response.json()
    structured = payload["result"]["structuredContent"]
    assert structured["schema"] == "mastermind.secretary_grounding_mcp_result.v2"
    assert structured["server_version"] == "2.0.0"
    assert structured["tool"] == "list_responsibilities"
    assert structured["ok"] is True
    assert structured["data"] == {
        "state": "UNKNOWN",
        "subjects": [],
        "reason_codes": ["NO_SOURCE"],
    }
    assert json.loads(payload["result"]["content"][0]["text"]) == structured
    assert port.calls == [("list_responsibilities", None)]
    assert fetcher.calls == [JWKS_URI]
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=policy.policy_id,
            code="accepted",
            accepted=True,
        )
    ]
    assert missing.status_code == 401
    assert missing.json() == {"error": "invalid_token"}
    assert token not in response.text
    assert token not in missing.text


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("list_responsibilities", {}),
        (
            "get_responsibility",
            {"responsibility_ref": responsibility_ref_for("WS:ALPHA")},
        ),
        ("get_attention", {}),
        (
            "get_current_runtime",
            {"responsibility_ref": responsibility_ref_for("WS:ALPHA")},
        ),
        (
            "explain_blocker",
            {"responsibility_ref": responsibility_ref_for("WS:ALPHA")},
        ),
        (
            "resolve_surface",
            {"responsibility_ref": responsibility_ref_for("WS:ALPHA")},
        ),
    ],
)
def test_real_control_room_port_crosses_exact_a1_asgi_for_each_nonempty_tool(
    tool_name: str,
    arguments: dict[str, str],
    rsa_key: rsa.RSAPrivateKey,
):
    policy = _policy()
    verifier, fetcher, sink = _real_verifier(policy, rsa_key)
    bearer = _token(rsa_key, policy)
    snapshot_calls: list[int] = []

    def provider():
        snapshot_calls.append(1)
        return _projection_snapshot()

    port = ControlRoomStewardReadPort(
        provider,
        clock=lambda: datetime(
            2026,
            9,
            1,
            12,
            5,
            0,
            tzinfo=timezone.utc,
        ),
        stale_after_seconds=900,
    )
    app = build_authenticated_app(
        build_contract_server(port),
        policy=policy,
        token_verifier=verifier,
    )
    body = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            MCP_PATH,
            headers={**MCP_HEADERS, "authorization": f"Bearer {bearer}"},
            json=body,
        )

    assert response.status_code == 200
    assert snapshot_calls == [1]
    assert fetcher.calls == [JWKS_URI]
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=policy.policy_id,
            code="accepted",
            accepted=True,
        )
    ]
    payload = response.json()["result"]
    structured = payload["structuredContent"]
    assert structured["schema"] == "mastermind.secretary_grounding_mcp_result.v2"
    assert structured["server_version"] == "2.0.0"
    assert structured["tool"] == tool_name
    assert structured["ok"] is True
    assert structured["error"] is None
    assert isinstance(structured["data"], dict)
    assert structured["data"]["subjects"]
    assert json.loads(payload["content"][0]["text"]) == structured

    wire = response.text
    for private in (
        bearer,
        "JOB-RAW-001",
        "ATTENTION-RAW-001",
        "11111111-1111-4111-8111-111111111111",
        "SEAT-RAW-001",
    ):
        assert private not in wire


@pytest.mark.parametrize(
    ("token_kwargs", "expected_code"),
    [
        ({"issuer": "https://wrong-issuer.example.test/"}, AuthErrorCode.ISSUER_REFUSED),
        ({"audience": "https://mcp.example.test/mcp/executive/v1"}, AuthErrorCode.RESOURCE_REFUSED),
        ({"scopes": ("mastermind.executive.read",)}, AuthErrorCode.SCOPE_REFUSED),
        ({"subject": "not-the-chairman"}, AuthErrorCode.SUBJECT_REFUSED),
        (
            {"client_id": "client-one", "azp": "client-two"},
            AuthErrorCode.TOKEN_CLAIMS_REFUSED,
        ),
    ],
)
def test_real_signed_token_claim_refusals_are_closed_and_secret_free(
    rsa_key: rsa.RSAPrivateKey,
    token_kwargs,
    expected_code: AuthErrorCode,
):
    policy = _policy()
    verifier, fetcher, sink = _real_verifier(policy, rsa_key)
    token = _token(rsa_key, policy, **token_kwargs)
    app = build_authenticated_app(
        build_contract_server(_Port()),
        policy=policy,
        token_verifier=verifier,
    )

    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            MCP_PATH,
            headers={**MCP_HEADERS, "authorization": f"Bearer {token}"},
            json=TOOL_CALL_BODY,
        )

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_token"}
    challenge = _challenge(response)
    assert 'error="invalid_token"' in challenge
    assert token not in response.text
    assert token not in challenge
    assert fetcher.calls == [JWKS_URI]
    assert sink.events == [
        AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=policy.policy_id,
            code=expected_code.value,
            accepted=False,
        )
    ]
    rendered_audit = repr(sink.events)
    for forbidden in (token, SUBJECT, CLIENT_ID, "client-one", "client-two"):
        assert forbidden not in rendered_audit
