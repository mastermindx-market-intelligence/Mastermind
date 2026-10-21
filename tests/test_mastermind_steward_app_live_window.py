"""Optional Live Window composition through the real Steward app factory.

Every key, token, claim, grant, page and audit sink here is a plainly labeled
synthetic nonproduction fixture. The real ``JwtAuthenticator`` /
``MastermindTokenVerifier`` classes, the real Steward factory and the real
accepted Reader seam are exercised; no registered client, enrollment,
production grant, provider, network or browser is involved.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import inspect
import json
from collections.abc import Sequence
from typing import Any

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_secretary_mcp.adapter import StewardGrounding
from integrations.mastermind_steward_app import app as steward_app_module
from integrations.mastermind_steward_app.app import build_authenticated_app
from integrations.mastermind_steward_app.live_window import (
    LIVE_WINDOW_SOURCE_KIND,
    LiveWindowConfig,
)
from integrations.mastermind_steward_app.server import (
    REQUIRED_SCOPE,
    build_contract_server,
)
from integrations.mastermind_window_reader.owner_read_resource import CONTENT_SCOPE
from tests.mastermind_window_reader.test_live_window import (
    REF,
    Source,
    build as build_window_reader,
)

HOST = "mcp.example.test"
ORIGIN = "https://" + HOST
STEWARD_RESOURCE = ORIGIN + "/mcp/steward/v1"
MCP_PATH = "/mcp/steward/v1"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp/steward/v1"
WINDOW_PATH = "/workspace/window/current"
WINDOW_RESOURCE = ORIGIN + WINDOW_PATH
STEWARD_ISSUER = "https://identity.example.test/"
STEWARD_SUBJECT = "chairman-opaque"
STEWARD_CLIENT = "chatgpt-business-client"
CONTENT_ISSUER = "https://content-issuer.example.test"
CONTENT_SUBJECT = "fixture-authorized-viewer"
CONTENT_CLIENT = "fixture-content-client"
KID = "fixture-key"
NOW = 1_788_000_100
WINDOW_TEXT = "Synthetic nonterminal window fragment."
OTHER_WINDOW_REF = "managed-window:some-other-source"
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
MCP_TOOL_BODY = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {"name": "list_responsibilities", "arguments": {}},
}
CONFIG_FIELDS = (
    "authenticator",
    "content_policy",
    "current_access",
    "read_source",
    "source_ref",
    "now",
    "allowed_origin",
    "audit_sink",
    "source_kind",
    "observation_binding",
)
# source_kind has its own closed literal; observation_binding is the one
# genuinely optional field (absent binding is the generic v1 shape, not an
# incomplete configuration).
COMPLETENESS_FIELDS = tuple(
    name
    for name in CONFIG_FIELDS
    if name not in ("source_kind", "observation_binding")
)


class _Fetcher:
    """One fixed synthetic JWKS document; no network, discovery or retry."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
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
        return self.payload


class _Sink:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


class _Port:
    """Minimal sentinel read port; the Steward MCP surface owns its own tests."""

    async def _empty(self) -> StewardGrounding:
        return StewardGrounding(state="UNKNOWN", facts=(), reason_codes=("NO_SOURCE",))

    async def list_responsibilities(self):
        return await self._empty()

    async def get_responsibility(self, responsibility_ref: str):
        del responsibility_ref
        return await self._empty()

    async def get_attention(self):
        return await self._empty()

    async def get_current_runtime(self, responsibility_ref: str):
        del responsibility_ref
        return await self._empty()

    async def explain_blocker(self, responsibility_ref: str):
        del responsibility_ref
        return await self._empty()

    async def resolve_surface(self, responsibility_ref: str):
        del responsibility_ref
        return await self._empty()


class _AuditSink:
    """The incumbent-shaped closed audit sink, owned by the caller."""

    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    def emit(self, event: Any) -> None:
        self.state["audit"].append(event)


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _base64url_uint(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode("ascii")


def _jwks(key: rsa.RSAPrivateKey) -> bytes:
    """One closed JWKS document; the incumbent cache rejects any extra member."""

    numbers = key.public_key().public_numbers()
    jwk = {
        "kid": KID,
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": _base64url_uint(numbers.n),
        "e": _base64url_uint(numbers.e),
    }
    return json.dumps({"keys": [jwk]}, separators=(",", ":")).encode()


def _cache(policy, key: rsa.RSAPrivateKey) -> BoundedJwksCache:
    return BoundedJwksCache(
        policy=policy, fetcher=_Fetcher(_jwks(key)), monotonic=lambda: 100.0
    )


def _steward_policy(*, scopes: Sequence[str] = (REQUIRED_SCOPE,)):
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-steward-fixture",
            "resource": STEWARD_RESOURCE,
            "resource_metadata_url": ORIGIN + METADATA_PATH,
            "issuer": STEWARD_ISSUER,
            "authorization_servers": [STEWARD_ISSUER],
            "jwks_uri": STEWARD_ISSUER + "jwks.json",
            "required_scopes": list(scopes),
            "allowed_subject_digests": [
                subject_digest(issuer=STEWARD_ISSUER, subject=STEWARD_SUBJECT)
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def _content_policy(
    *,
    scopes: Sequence[str] = (CONTENT_SCOPE,),
    resource: str = WINDOW_RESOURCE,
    issuer: str = CONTENT_ISSUER,
):
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-workspace-window-fixture",
            "resource": resource,
            "resource_metadata_url": (
                ORIGIN + "/.well-known/oauth-protected-resource/workspace/window/current"
            ),
            "issuer": issuer,
            "authorization_servers": [issuer],
            "jwks_uri": issuer + "/jwks",
            "required_scopes": list(scopes),
            "allowed_subject_digests": [
                subject_digest(issuer=issuer, subject=CONTENT_SUBJECT)
            ],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 0,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 1,
            "fetch_failure_backoff_seconds": 1,
        }
    )


def _steward_token(
    key: rsa.RSAPrivateKey,
    *,
    audience: str = STEWARD_RESOURCE,
    scopes: Sequence[str] = (REQUIRED_SCOPE,),
    subject: str = STEWARD_SUBJECT,
    issuer: str = STEWARD_ISSUER,
) -> str:
    return pyjwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "iat": NOW - 100,
            "nbf": NOW - 100,
            "exp": NOW + 600,
            "scope": " ".join(scopes),
            "client_id": STEWARD_CLIENT,
            "jti": "opaque-token-id",
        },
        key,
        algorithm="RS256",
        headers={"kid": KID, "typ": "at+jwt"},
    )


def _content_token(
    key: rsa.RSAPrivateKey,
    *,
    audience: str = WINDOW_RESOURCE,
    scopes: Sequence[str] = (CONTENT_SCOPE,),
    subject: str = CONTENT_SUBJECT,
    issuer: str = CONTENT_ISSUER,
    issued_at: int = NOW - 5,
    expires_at: int = NOW + 600,
) -> str:
    return pyjwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "iat": issued_at,
            "nbf": issued_at,
            "exp": expires_at,
            "scope": " ".join(scopes),
            "client_id": CONTENT_CLIENT,
            "jti": "fixture-content-request",
        },
        key,
        algorithm="RS256",
        headers={"kid": KID, "typ": "at+jwt"},
    )


def _steward_verifier(policy, key: rsa.RSAPrivateKey):
    return MastermindTokenVerifier(
        authenticator=JwtAuthenticator(policy=policy, jwks_cache=_cache(policy, key)),
        policy=policy,
        now=lambda: NOW,
        audit_sink=_Sink(),
    )


def _steward_app(*, live_window=None, policy=None, key: rsa.RSAPrivateKey | None = None):
    policy = _steward_policy() if policy is None else policy
    key = _key() if key is None else key
    return build_authenticated_app(
        build_contract_server(_Port()),
        policy=policy,
        token_verifier=_steward_verifier(policy, key),
        live_window=live_window,
    )


@dataclasses.dataclass
class _Mount:
    """One complete synthetic mount configuration and its fixture state."""

    config: LiveWindowConfig
    authenticator: JwtAuthenticator
    state: dict[str, Any]
    source: Source
    key: rsa.RSAPrivateKey

    def app(self):
        return _steward_app(live_window=self.config)


def _mount(
    *,
    key: rsa.RSAPrivateKey | None = None,
    source: Source | None = None,
    policy=None,
    source_ref: str = REF,
    allowed_origin: str = ORIGIN,
    source_kind: str = LIVE_WINDOW_SOURCE_KIND,
    sink=None,
) -> _Mount:
    key = _key() if key is None else key
    policy = _content_policy() if policy is None else policy
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=_cache(policy, key))
    source = Source() if source is None else source
    reader = build_window_reader(source)
    state: dict[str, Any] = {
        "reads": 0,
        "accesses": 0,
        "grant": True,
        "grant_epoch": "fixture-grant-v1",
        "now": NOW,
        "after_read": None,
        "after_final_access": None,
        "raw": None,
        "audit": [],
    }

    async def current_access(principal, ref):
        assert ref == REF
        assert principal.subject_digest == policy.allowed_subject_digests[0]
        state["accesses"] += 1
        if state["accesses"] == 2 and state["after_final_access"]:
            state["after_final_access"](state, authenticator)
        return (state["grant_epoch"],) if state["grant"] else None

    async def read_source():
        state["reads"] += 1
        if state["after_read"]:
            state["after_read"](state, authenticator)
        if state["raw"] is not None:
            return state["raw"]
        return await reader.read()

    config = LiveWindowConfig(
        authenticator=authenticator,
        content_policy=policy,
        current_access=current_access,
        read_source=read_source,
        source_ref=source_ref,
        now=lambda: int(state["now"]),
        allowed_origin=allowed_origin,
        audit_sink=_AuditSink(state) if sink is None else sink,
        source_kind=source_kind,
    )
    return _Mount(config=config, authenticator=authenticator, state=state, source=source, key=key)


async def _invoke(
    app,
    *,
    path: str,
    method: str = "GET",
    headers: Sequence[tuple[bytes, bytes]] | None = None,
    root_path: str = "",
    query: bytes = b"",
    body: bytes = b"",
    scheme: str = "https",
):
    messages: list[dict] = []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": scheme,
        "method": method,
        "path": path,
        "raw_path": path.encode("ascii"),
        "root_path": root_path,
        "query_string": query,
        "headers": list(headers) if headers is not None else [],
        "server": (HOST, 443),
        "client": ("127.0.0.1", 1234),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    start = next(item for item in messages if item["type"] == "http.response.start")
    raw = b"".join(
        item.get("body", b"")
        for item in messages
        if item["type"] == "http.response.body"
    )
    return start["status"], tuple(start.get("headers", ())), raw, messages


def _call(app, **kwargs):
    return asyncio.run(_invoke(app, **kwargs))


def _headers(*, token: str | None = None, host: str = HOST, extra=()) -> list:
    fields = [(b"host", host.encode("ascii"))]
    if token is not None:
        fields.append((b"authorization", ("Bearer " + token).encode("ascii")))
    fields.extend(extra)
    return fields


def _window(app, mount: _Mount, **kwargs):
    the_token = kwargs.pop("token", None)
    if the_token is None:
        the_token = _content_token(mount.key)
    headers = kwargs.pop("headers", None)
    if headers is None:
        headers = _headers(token=the_token)
    return _call(app, path=WINDOW_PATH, headers=headers, **kwargs)


def _route_table(app) -> list[tuple[str, tuple[str, ...]]]:
    return [(route.path, tuple(sorted(route.methods or ()))) for route in app.routes]


def _middleware_table(app) -> list[tuple[str, tuple[str, ...]]]:
    return [
        (item.cls.__name__, tuple(sorted(item.kwargs))) for item in app.user_middleware
    ]


def _exchange(app, **kwargs):
    status, headers, raw, _ = _call(app, **kwargs)
    return status, headers, raw


def _selftest_probes(token: str) -> list[dict]:
    """Paths the composition must never intercept, whatever the configuration."""

    return [
        {"path": "/healthz"},
        {"path": "/readyz"},
        {"path": METADATA_PATH},
        {"path": "/"},
        {"path": MCP_PATH, "method": "POST"},
        {"path": MCP_PATH + "/extra"},
        {"path": WINDOW_PATH + "/extra"},
        {"path": WINDOW_PATH[:-1]},
        {"path": WINDOW_PATH + "-suffix"},
        {"path": WINDOW_PATH.replace("window", "window2")},
        {"path": "/workspace"},
    ]


def test_factory_default_is_identical_with_and_without_the_option():
    token = _content_token(_key())
    implicit = _steward_app()
    explicit = _steward_app(live_window=None)

    assert _route_table(implicit) == _route_table(explicit)
    assert _middleware_table(implicit) == _middleware_table(explicit)
    for probe in _selftest_probes(token):
        headers = _headers(token=token)
        assert _exchange(implicit, headers=headers, **probe) == _exchange(
            explicit, headers=headers, **probe
        )
    status, _, raw, _ = _call(implicit, path=WINDOW_PATH, headers=_headers(token=token))
    assert status == 404 and raw == b'{"error":"not_found"}'


def test_enabling_adds_only_one_outermost_middleware_and_no_route():
    source = Source()
    source.publish("a", WINDOW_TEXT)
    mount = _mount(source=source)
    disabled = _steward_app()
    enabled = mount.app()

    assert _route_table(enabled) == _route_table(disabled)
    assert _middleware_table(enabled)[1:] == _middleware_table(disabled)
    assert _middleware_table(enabled)[0][0] == "LiveWindowDispatch"
    token = _content_token(mount.key)
    for probe in _selftest_probes(token):
        headers = _headers(token=token)
        assert _exchange(enabled, headers=headers, **probe) == _exchange(
            disabled, headers=headers, **probe
        )
    status, _, raw, _ = _window(enabled, mount)
    assert status == 200
    assert json.loads(raw)["view"]["items"][0]["text"] == WINDOW_TEXT
    assert mount.state["reads"] == 1


def test_signed_fixture_window_read_crosses_the_real_factory_and_fixed_source():
    key = _key()
    source = Source()
    source.publish("a", WINDOW_TEXT)
    mount = _mount(key=key, source=source)
    token = _content_token(key)

    status, headers, raw, _ = _window(mount.app(), mount)

    assert status == 200
    assert dict(headers)[b"cache-control"] == b"no-store"
    payload = json.loads(raw)
    assert payload["mode"] == "observed-turn-window" and payload["selection_ref"] == REF
    view = payload["view"]
    assert view["source_ref"] == REF
    assert view["scope"] == "one-managed-turn-window"
    assert view["history"] == "NOT_PROVEN" and view["acceptance"] == "NOT_PROJECTED"
    assert view["terminal"] is False
    assert view["capabilities"] == {
        "send": False,
        "provider_control": False,
        "history": False,
    }
    item = view["items"][0]
    assert item["text"] == WINDOW_TEXT and item["representation"] == "VISIBLE_TEXT"
    assert item["display_sha256"] == __import__("hashlib").sha256(
        WINDOW_TEXT.encode()
    ).hexdigest()
    assert token.encode() not in raw and CONTENT_SUBJECT.encode() not in raw
    assert mount.state["reads"] == 1 and mount.state["accesses"] == 2


def test_window_request_has_no_viewer_caused_start_resume_or_send():
    key = _key()
    source = Source()
    source.publish("a", WINDOW_TEXT, state="completed")
    mount = _mount(key=key, source=source)

    status, _, raw, messages = _window(mount.app(), mount)

    view = json.loads(raw)["view"]
    assert status == 200 and view["terminal"] is False
    assert all(value is False for value in view["capabilities"].values())
    assert mount.state["reads"] == 1 and mount.state["accesses"] == 2
    assert 1 <= source.reads <= 8
    assert len(messages) == 2


def test_non_get_window_request_passes_through_before_any_grant_or_source_work():
    """Only the exact GET mount is dispatched; a POST is the old stack's."""

    mount = _mount()
    disabled = _steward_app()
    request = {
        "path": WINDOW_PATH,
        "headers": _headers(token=_content_token(mount.key)),
        "method": "POST",
    }

    posted = _call(mount.app(), **request)

    assert posted[:3] == _exchange(disabled, **request)
    assert posted[0] == 404 and json.loads(posted[2]) == {"error": "not_found"}
    assert mount.state["reads"] == 0 and mount.state["accesses"] == 0
    assert all(WINDOW_TEXT.encode() not in m.get("body", b"") for m in posted[3])


def test_window_request_needs_no_network_process_or_filesystem_effect(monkeypatch):
    import builtins
    import socket
    import subprocess

    def prohibited(*_args, **_kwargs):
        raise AssertionError("external effect attempted by the window request")

    source = Source()
    source.publish("a", WINDOW_TEXT)
    mount = _mount(source=source)
    app = mount.app()

    monkeypatch.setattr(socket.socket, "connect", prohibited)
    monkeypatch.setattr(subprocess, "Popen", prohibited)
    monkeypatch.setattr(builtins, "open", prohibited)
    status, _, raw, _ = _window(app, mount)

    assert status == 200 and json.loads(raw)["view"]["terminal"] is False
    assert mount.state["reads"] == 1


def test_steward_routes_keep_their_own_auth_with_the_composition_enabled():
    steward_key = _key()
    policy = _steward_policy()
    mount = _mount()
    app = _steward_app(live_window=mount.config, policy=policy, key=steward_key)

    assert _call(app, path=METADATA_PATH, headers=_headers())[0] == 200
    assert _call(app, path="/healthz", headers=_headers())[0] == 200
    unauthenticated = _call(
        app,
        path=MCP_PATH,
        method="POST",
        headers=_headers(
            extra=[
                (b"content-type", b"application/json"),
                (b"accept", b"application/json"),
            ]
        ),
        body=json.dumps(MCP_TOOL_BODY).encode(),
    )
    assert unauthenticated[0] == 401
    assert json.loads(unauthenticated[2]) == {"error": "invalid_token"}

    with TestClient(app, base_url=ORIGIN) as client:
        response = client.post(
            MCP_PATH,
            headers={
                **MCP_HEADERS,
                "authorization": "Bearer " + _steward_token(steward_key),
            },
            json=MCP_TOOL_BODY,
        )

    structured = response.json()["result"]["structuredContent"]
    assert response.status_code == 200
    assert structured["schema"] == "mastermind.secretary_grounding_mcp_result.v2"
    assert structured["data"] == {
        "state": "UNKNOWN",
        "subjects": [],
        "reason_codes": ["NO_SOURCE"],
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"audience": STEWARD_RESOURCE},
        {"audience": "https://other.example.test/resource"},
        {"scopes": (REQUIRED_SCOPE,)},
        {"scopes": (REQUIRED_SCOPE, CONTENT_SCOPE)},
        {"subject": "somebody-else"},
        {"issuer": "https://wrong.example.test"},
        {"issued_at": NOW - 100, "expires_at": NOW - 1},
        {"issued_at": NOW + 10},
        {"expires_at": NOW + 2000},
    ],
)
def test_signed_but_policy_invalid_content_token_never_reads(changes):
    mount = _mount()
    token = _content_token(mount.key, **changes)

    status, _, raw, messages = _window(mount.app(), mount, token=token)

    assert status == 401 and mount.state["reads"] == 0
    assert WINDOW_TEXT.encode() not in raw
    assert all(WINDOW_TEXT.encode() not in m.get("body", b"") for m in messages)


def test_wrong_signature_never_reaches_the_source_grant_or_read():
    mount = _mount()
    stranger = _content_token(_key())

    status, _, raw, _ = _window(mount.app(), mount, token=stranger)

    assert status == 401 and mount.state["reads"] == 0 and mount.state["accesses"] == 0
    assert json.loads(raw) == {"error": "authentication_required"}


def test_missing_or_malformed_authorization_is_refused_without_a_source_read():
    mount = _mount()
    app = mount.app()

    missing = _call(app, path=WINDOW_PATH, headers=_headers())
    malformed = _call(
        app,
        path=WINDOW_PATH,
        headers=_headers(extra=[(b"authorization", b"Bearer\ttabbed")]),
    )
    unbound = _call(
        app,
        path=WINDOW_PATH,
        headers=_headers(extra=[(b"authorization", b"Basic fixture")]),
    )

    assert missing[0] == 401
    assert json.loads(missing[2]) == {"error": "authentication_required"}
    assert malformed[0] == 400
    assert json.loads(malformed[2]) == {"error": "invalid_request"}
    assert unbound[0] == 401
    assert json.loads(unbound[2]) == {"error": "authentication_required"}
    assert mount.state["reads"] == 0 and mount.state["accesses"] == 0


def test_current_grant_is_required_even_for_a_valid_resource_token():
    mount = _mount()
    mount.state["grant"] = False

    status, _, raw, _ = _window(mount.app(), mount)

    assert status == 401 and mount.state["reads"] == 0
    assert json.loads(raw) == {"error": "authentication_required"}


@pytest.mark.parametrize(
    "transition",
    ["revoke", "grant_epoch", "policy_id", "expire_during_read", "expire_during_grant"],
)
def test_grant_policy_or_turn_change_suppresses_the_entire_window_body(transition):
    source = Source()
    source.publish("a", WINDOW_TEXT)
    mount = _mount(source=source)

    def after_read(state, _auth):
        if transition == "revoke":
            state["grant"] = False
        elif transition == "grant_epoch":
            state["grant_epoch"] = "fixture-grant-v2"
        elif transition == "expire_during_read":
            state["now"] = NOW + 601

    def after_final_access(state, auth):
        if transition == "policy_id":
            auth._policy = dataclasses.replace(
                auth.policy, policy_id="different-content-policy"
            )
        elif transition == "expire_during_grant":
            state["now"] = NOW + 601

    mount.state["after_read"] = after_read
    mount.state["after_final_access"] = after_final_access
    token = _content_token(mount.key)

    status, _, raw, messages = _window(mount.app(), mount, token=token)

    assert mount.state["reads"] == 1
    assert status in (401, 403)
    assert WINDOW_TEXT.encode() not in raw
    assert token.encode() not in raw
    assert all(WINDOW_TEXT.encode() not in m.get("body", b"") for m in messages)


def test_source_binding_that_is_not_the_configured_window_is_refused():
    source = Source()
    source.publish("a", WINDOW_TEXT)
    mount = _mount(source=source)
    mount.state["raw"] = asyncio.run(
        build_window_reader(source, source_ref=OTHER_WINDOW_REF).read()
    )

    status, _, raw, _ = _window(mount.app(), mount)

    assert status == 502 and json.loads(raw) == {"error": "source_unavailable"}
    assert WINDOW_TEXT.encode() not in raw
    assert mount.state["reads"] == 1


def test_revoked_current_access_releases_no_retained_window_content():
    source = Source()
    source.publish("a", WINDOW_TEXT)
    mount = _mount(source=source)
    app = mount.app()

    granted = _window(app, mount)
    assert granted[0] == 200 and WINDOW_TEXT.encode() in granted[2]

    mount.state["grant"] = False
    revoked, _, raw, messages = _window(app, mount)

    assert revoked in (401, 403) and mount.state["reads"] == 1
    assert WINDOW_TEXT.encode() not in raw
    assert all(WINDOW_TEXT.encode() not in m.get("body", b"") for m in messages)


def test_audit_records_are_closed_and_carry_no_token_or_content():
    mount = _mount()
    token = _content_token(mount.key)

    assert _window(mount.app(), mount, token=token)[0] == 200

    records = mount.state["audit"]
    assert len(records) == 2
    for event in records:
        payload = dataclasses.asdict(event)
        assert set(payload) == {"schema", "policy_id", "code", "accepted"}
        assert payload["accepted"] is True and payload["code"] == "accepted"
        assert token not in json.dumps(payload)
        assert WINDOW_TEXT not in json.dumps(payload)


def test_exact_dispatch_leaves_every_other_path_byte_identical():
    mount = _mount()
    disabled = _steward_app()
    enabled = mount.app()
    token = _content_token(mount.key)

    for probe in _selftest_probes(token):
        headers = _headers(token=token)
        assert _exchange(enabled, headers=headers, **probe) == _exchange(
            disabled, headers=headers, **probe
        )
    assert mount.state["reads"] == 0 and mount.state["accesses"] == 0


def test_exact_window_request_with_foreign_scheme_or_host_is_reader_refused():
    mount = _mount()
    app = mount.app()
    token = _content_token(mount.key)

    plain = _window(app, mount, scheme="http")
    foreign = _call(
        app, path=WINDOW_PATH, headers=_headers(token=token, host="other.example.test")
    )

    assert plain[0] == 403 and json.loads(plain[2]) == {"error": "transport_refused"}
    assert foreign[0] == 403
    assert mount.state["reads"] == 0 and mount.state["accesses"] == 0


class _CountingReader:
    """Count requests reaching the Reader resource; the real Reader still runs."""

    def __init__(self) -> None:
        self.app = None
        self.calls = 0

    async def __call__(self, scope, receive, send) -> None:
        self.calls += 1
        assert self.app is not None
        await self.app(scope, receive, send)


def _counted_reader(monkeypatch) -> _CountingReader:
    """Wrap the Reader resource the real construction seam returns."""

    counted = _CountingReader()
    real = steward_app_module.live_window_reader

    def seam(config, **kwargs):
        reader, path = real(config, **kwargs)
        counted.app = reader
        return counted, path

    monkeypatch.setattr(steward_app_module, "live_window_reader", seam)
    return counted


NON_EXACT_WINDOW_REQUESTS = (
    ("query-string", {"query": b"x=1"}),
    ("root-path", {"root_path": "/injected"}),
    ("HEAD", {"method": "HEAD"}),
    ("OPTIONS", {"method": "OPTIONS"}),
    ("POST", {"method": "POST"}),
    ("trailing-slash", {"path": WINDOW_PATH + "/"}),
    ("percent-encoded", {"path": "/workspace/window/%63urrent"}),
)


@pytest.mark.parametrize("label,overrides", NON_EXACT_WINDOW_REQUESTS)
def test_non_exact_window_requests_pass_through_to_the_old_stack_byte_identically(
    label, overrides, monkeypatch
):
    """Dispatch is exact GET only; every other request is the old Steward stack."""

    mount = _mount()
    counted = _counted_reader(monkeypatch)
    enabled = mount.app()
    disabled = _steward_app()
    request = {
        "path": WINDOW_PATH,
        "headers": _headers(token=_content_token(mount.key)),
    }
    request.update(overrides)

    given = _call(enabled, **request)
    plain = _call(disabled, **request)

    assert given[0] == plain[0], label
    assert tuple(sorted(given[1])) == tuple(sorted(plain[1])), label
    assert given[2] == plain[2], label
    assert given[3] == plain[3], label
    assert counted.calls == 0, label
    assert mount.state["reads"] == 0 and mount.state["accesses"] == 0, label


def test_only_the_exact_configured_window_path_is_dispatched():
    source = Source()
    source.publish("a", WINDOW_TEXT)
    mount = _mount(source=source)
    enabled = mount.app()
    token = _content_token(mount.key)

    for path in [
        WINDOW_PATH + "/extra",
        WINDOW_PATH[:-1],
        WINDOW_PATH + "-suffix",
        WINDOW_PATH.replace("window", "window2"),
        "/workspace/window",
    ]:
        status, _, raw, _ = _call(enabled, path=path, headers=_headers(token=token))
        assert status == 404 and raw == b'{"error":"not_found"}'
    assert mount.state["reads"] == 0 and mount.state["accesses"] == 0


@pytest.mark.parametrize("field", COMPLETENESS_FIELDS)
def test_incomplete_configuration_is_refused_typed(field):
    mount = _mount()
    with pytest.raises(TypeError, match="incomplete live window configuration"):
        _steward_app(live_window=dataclasses.replace(mount.config, **{field: None}))


def test_non_configuration_object_cannot_be_a_mount_option():
    with pytest.raises(TypeError, match="LiveWindowConfig"):
        _steward_app(live_window={"source_ref": REF})
    parameters = inspect.signature(build_authenticated_app).parameters
    assert parameters["live_window"].default is None
    assert {"reader", "owner", "app", "resource", "source_kind"} & set(parameters) == set()
    assert {field.name for field in dataclasses.fields(LiveWindowConfig)} == set(
        CONFIG_FIELDS
    )


@pytest.mark.parametrize(
    "binding",
    [
        {"job_id": "JOB-1", "attempt_id": "ATT-" + "a" * 32},
        ("JOB-1", "ATT-" + "a" * 32),
        ["JOB-1", "ATT-" + "a" * 32],
        "JOB-1/ATT-" + "a" * 32,
        7,
    ],
)
def test_malformed_observation_binding_cannot_be_mounted(binding):
    mount = _mount()
    config = dataclasses.replace(mount.config, observation_binding=binding)
    with pytest.raises(ValueError, match="invalid observation binding"):
        _steward_app(live_window=config)


@pytest.mark.parametrize(
    "job_id,attempt_id",
    [
        ("JOB-not-canonical", "ATT-" + "a" * 32),
        ("JOB-1", "ATT-invalid"),
        ("JOB-" + "0" * 10, "ATT-" + "a" * 32),
    ],
)
def test_grammatically_invalid_typed_binding_cannot_be_mounted(job_id, attempt_id):
    from integrations.mastermind_window_reader.owner_read_resource import (
        ObservationBinding,
    )

    with pytest.raises(ValueError, match="invalid observation binding"):
        ObservationBinding(job_id=job_id, attempt_id=attempt_id)


def test_valid_typed_observation_binding_is_copied_into_the_reader():
    from integrations.mastermind_window_reader.owner_read_resource import (
        ObservationBinding,
    )

    mount = _mount()
    binding = ObservationBinding(job_id="JOB-42", attempt_id="ATT-" + "b" * 32)
    config = dataclasses.replace(mount.config, observation_binding=binding)
    app = _steward_app(live_window=config)
    token = _content_token(mount.key)
    status, _, raw, _ = _call(app, path=WINDOW_PATH, headers=_headers(token=token))
    assert status == 200
    document = json.loads(raw)
    assert document["schema"] == "mastermind.workspace.window_read_candidate.v2"
    assert document["observation_binding"] == {
        "job_id": "JOB-42",
        "attempt_id": "ATT-" + "b" * 32,
    }
    # The mount never aliases the caller's object.
    assert config.observation_binding is binding


@pytest.mark.parametrize("source_kind", ["recorded", "native-lane", "live_window"])
def test_recorded_or_unknown_source_kind_is_not_a_live_window_mount(source_kind):
    mount = _mount(source_ref="native-lane:fixture-recorded-lane", source_kind=source_kind)
    with pytest.raises(ValueError, match="live-window"):
        _steward_app(live_window=mount.config)


@pytest.mark.parametrize("reserved", ["/healthz", "/readyz", MCP_PATH, METADATA_PATH])
def test_window_path_cannot_shadow_steward_routes(reserved):
    mount = _mount(policy=_content_policy(resource=ORIGIN + reserved))
    with pytest.raises(ValueError, match="reserved application path"):
        _steward_app(live_window=mount.config)


def test_window_resource_on_another_origin_is_refused():
    foreign = "https://other.example.test" + WINDOW_PATH
    cross_host = _mount(
        policy=_content_policy(resource=foreign),
        allowed_origin="https://other.example.test",
    )
    with pytest.raises(ValueError, match="same existing host required"):
        _steward_app(live_window=cross_host.config)

    cross_origin = _mount(allowed_origin="https://other.example.test")
    with pytest.raises(ValueError, match="same existing host required"):
        _steward_app(live_window=cross_origin.config)


@pytest.mark.parametrize("scopes", [(REQUIRED_SCOPE,), (REQUIRED_SCOPE, CONTENT_SCOPE)])
def test_content_policy_scope_cannot_be_the_steward_scope(scopes):
    mount = _mount(policy=_content_policy(scopes=scopes))
    with pytest.raises(ValueError, match="content scope"):
        _steward_app(live_window=mount.config)


def test_live_window_composition_cannot_widen_the_steward_scope():
    widened = _steward_policy(scopes=("mastermind.extra", REQUIRED_SCOPE))
    mount = _mount()
    with pytest.raises(ValueError, match="exactly mastermind.steward.read"):
        _steward_app(live_window=mount.config, policy=widened)


def test_live_window_option_cannot_carry_a_reader_or_owner_object():
    mount = _mount()
    for name in ("reader", "owner", "app", "resource_path"):
        assert not hasattr(mount.config, name)
