"""Signed-token, no-execution tests for the exclusive public ``/mcp`` audience.

``public_mcp_resource`` is an opt-in sealed installed-config key. When present
the Web-CEO v3 gateway serves ``POST /mcp`` and the per-host protected-resource
metadata for ``https://mcp.mastermind-x.com/mcp`` ONLY: a token minted for any
other configured audience (the primary connector resource, the OS Executive
resource or an OpenAI tunnel resource) must be refused there, and the challenge
must point at the public metadata document. Without the key nothing changes.

Every assertion uses a real signed temporary RS256 token and the existing
no-execution fixtures; there is no network, socket or install.
"""
from __future__ import annotations

import asyncio
import contextlib
import copy
import dataclasses
import json
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
finally:
    sys.path.pop(0)

from integrations.business_mcp_auth.contracts import AuthError, AuthErrorCode
from integrations.business_mcp_auth.metadata import protected_resource_metadata
from integrations.executive_mcp import server as transport_server
from integrations.executive_mcp import web_ceo_v3 as v3
from integrations.executive_mcp.server import OsStaticApp
from integrations.mastermind_executive_app import gateway
from ops.executive_os import executive_mcp_entry as entry

rsa_key = fixture.rsa_key
short_socket_root = fixture.short_socket_root

TUNNEL = (
    "https://tunnel-service.gateway.unified-0.internal.api.openai.org"
    "/v1/mcp/tunnel_" + "a" * 32
)
FOREIGN = "https://foreign.example.test/mcp"
PUBLIC_HOST_HEADERS = {"host": "mcp.mastermind-x.com", "accept": "application/json"}
MCP_HEADERS = {"accept": "application/json, text/event-stream"}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "source-proof", "version": "1"},
    },
}


class Sink:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


class FixedMdm:
    def list_macos_devices(self, *args: object, **kwargs: object) -> list[dict[str, Any]]:
        return []


def _assets() -> OsStaticApp:
    return OsStaticApp({
        "/os/": (b"<main>os</main>", "text/html; charset=utf-8"),
        "/os/assets/index-a.css": (b"body{}", "text/css; charset=utf-8"),
        "/os/assets/index-a.js": (b"void 0", "text/javascript; charset=utf-8"),
    })


def _bearer(token: str, **extra: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}", **extra}


@pytest.fixture
def settings(rsa_key: object, tmp_path: Path, short_socket_root: Path) -> Any:
    mastermind = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    fixture._git_repo(mastermind)
    (macro / "scripts").mkdir(parents=True)
    (macro / "scripts" / "agentos.py").write_text("")
    (macro / "agentos").mkdir()
    (macro / "agentos" / ".keep").write_text("")
    fixture._git_repo(macro)
    base = fixture._real_app_settings(
        rsa_key,
        mastermind_root=mastermind,
        macro_root=macro,
        ceo_ingress_socket_path=short_socket_root / "ceo-ingress.sock",
    )
    return dataclasses.replace(base, read_from_ceo_ingress=True)


@pytest.fixture(autouse=True)
def fake_jwks(rsa_key: object, monkeypatch: pytest.MonkeyPatch) -> None:
    # Every derived authenticator variant gets the same disposable signed-key
    # fixture; no JWKS network fetch.
    monkeypatch.setattr(
        gateway, "_default_jwks_cache", lambda _: fixture._FakeJwksCache(rsa_key)
    )


def _raw(*, public: bool = True, os_transport: bool = True, tunnels: tuple[str, ...] = (TUNNEL,)) -> dict[str, Any]:
    raw: dict[str, Any] = {"executive_mcp_profile": "web_ceo_v3"}
    if public:
        raw["public_mcp_resource"] = entry.PUBLIC_MCP_RESOURCE
    if os_transport:
        raw.update(
            os_executive_transport=True,
            os_executive_resource=entry.OS_EXECUTIVE_RESOURCE,
        )
    if tunnels:
        raw["executive_additional_resources"] = sorted(tunnels)
    return raw


def _configure(settings: Any, *, public: bool = True, os_transport: bool = True,
               tunnels: tuple[str, ...] = (TUNNEL,)) -> Any:
    raw = _raw(public=public, os_transport=os_transport, tunnels=tunnels)
    additional = entry.build_additional_policies(raw, settings.policies)
    public_policies = (
        entry.build_public_policies(raw, settings.policies, additional) if public else None
    )
    return dataclasses.replace(
        settings, additional_policies=additional, public_policies=public_policies
    )


def _build(configured: Any, *, os_transport: bool = True, os_resource: str | None = None) -> Any:
    return transport_server.build_web_ceo_v3_mcp_app(
        configured,
        audit_sink=Sink(),
        mdm_reader=FixedMdm(),
        session_target_projector=lambda *_: [],
        session_reply_handler=lambda *_: {},
        session_summon_handler=lambda *_: {},
        os_app=_assets(),
        enable_os_executive_transport=os_transport,
        os_executive_resource=(
            (os_resource or entry.OS_EXECUTIVE_RESOURCE) if os_transport else None
        ),
    )


@contextlib.asynccontextmanager
async def _client(app: Any) -> Any:
    async with app._fenced_app._app.router.lifespan_context(app._fenced_app._app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://mcp.mastermind-x.com",
        ) as http:
            yield http


def _challenge(response: httpx.Response) -> str:
    return response.headers["www-authenticate"]


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# /mcp accepts the public audience only
# --------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["submit", "read"])
def test_public_audience_token_is_accepted_at_mcp(settings: Any, rsa_key: object, kind: str) -> None:
    configured = _configure(settings)
    maker = fixture._submit_token if kind == "submit" else fixture._read_token
    token = maker(rsa_key, aud=entry.PUBLIC_MCP_RESOURCE)

    async def exercise() -> None:
        async with _client(_build(configured)) as http:
            initialized = await http.post(
                "http://127.0.0.1/mcp", headers=_bearer(token, **MCP_HEADERS), json=INITIALIZE
            )
            assert initialized.status_code == 200, initialized.text
            listed = await http.post(
                "http://127.0.0.1/mcp",
                headers=_bearer(
                    token,
                    host="127.0.0.1",
                    **MCP_HEADERS,
                    **{"mcp-protocol-version": "2025-06-18"},
                ),
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )
            assert listed.status_code == 200, listed.text
            names = {tool["name"] for tool in listed.json()["result"]["tools"]}
            assert names == set(v3.web_ceo_v3_tool_names())

    _run(exercise())


@pytest.mark.parametrize(
    "audience",
    [
        None,  # the primary connector resource (default aud)
        entry.OS_EXECUTIVE_RESOURCE,
        TUNNEL,
        FOREIGN,
        entry.PUBLIC_MCP_RESOURCE + "/other",
        entry.PUBLIC_MCP_RESOURCE + "/",
    ],
)
@pytest.mark.parametrize("kind", ["submit", "read"])
def test_non_public_audiences_are_refused_at_mcp(
    settings: Any, rsa_key: object, audience: str | None, kind: str
) -> None:
    configured = _configure(settings)
    maker = fixture._submit_token if kind == "submit" else fixture._read_token
    token = maker(rsa_key) if audience is None else maker(rsa_key, aud=audience)
    primary = configured.policies.submit.resource

    async def exercise() -> None:
        async with _client(_build(configured)) as http:
            response = await http.post(
                "http://127.0.0.1/mcp", headers=_bearer(token, **MCP_HEADERS), json=INITIALIZE
            )
            assert response.status_code == 401, response.text
            challenge = _challenge(response)
            assert f'resource_metadata="{entry.PUBLIC_MCP_METADATA_URL}"' in challenge
            for hidden in (primary, entry.OS_EXECUTIVE_RESOURCE, TUNNEL, "tunnel-service"):
                assert hidden not in challenge
                assert hidden not in response.text

    _run(exercise())


def test_missing_token_challenge_names_the_public_metadata(settings: Any) -> None:
    configured = _configure(settings)

    async def exercise() -> None:
        async with _client(_build(configured)) as http:
            response = await http.post(
                "http://127.0.0.1/mcp", headers=MCP_HEADERS, json=INITIALIZE
            )
            assert response.status_code == 401
            challenge = _challenge(response)
            assert challenge.startswith("Bearer ")
            assert f'resource_metadata="{entry.PUBLIC_MCP_METADATA_URL}"' in challenge
            assert TUNNEL not in challenge

    _run(exercise())


def test_public_metadata_advertises_only_the_public_resource(settings: Any) -> None:
    configured = _configure(settings)
    expected = protected_resource_metadata(configured.public_policies.submit)
    assert expected["resource"] == "https://mcp.mastermind-x.com/mcp"

    async def exercise() -> None:
        async with _client(_build(configured)) as http:
            response = await http.get(
                "/.well-known/oauth-protected-resource/mcp", headers=PUBLIC_HOST_HEADERS
            )
            assert response.status_code == 200, response.text
            assert response.json() == expected
            body = response.text
            for hidden in (TUNNEL, "tunnel-service", entry.OS_EXECUTIVE_RESOURCE,
                           configured.policies.submit.resource):
                assert hidden not in body
            # The primary metadata path is not served in public mode.
            primary_path = "/mcp/.well-known/oauth-protected-resource"
            assert (await http.get(primary_path, headers=PUBLIC_HOST_HEADERS)).status_code == 404

    _run(exercise())


# --------------------------------------------------------------------------
# Other routes keep their own exact-resource authenticators
# --------------------------------------------------------------------------

def test_public_audience_is_refused_by_the_os_routes(settings: Any, rsa_key: object) -> None:
    configured = _configure(settings)
    public = fixture._submit_token(rsa_key, aud=entry.PUBLIC_MCP_RESOURCE)
    os_token = fixture._submit_token(rsa_key, aud=entry.OS_EXECUTIVE_RESOURCE)

    async def exercise() -> None:
        async with _client(_build(configured)) as http:
            refused = await http.post(
                "/os/executive/context",
                headers=_bearer(public, **PUBLIC_HOST_HEADERS),
                json={},
            )
            assert refused.status_code == 401, refused.text
            control = await http.post(
                "/os/executive/context",
                headers=_bearer(os_token, **PUBLIC_HOST_HEADERS),
                json={},
            )
            assert control.status_code == 200, control.text

    _run(exercise())


def test_public_resource_cannot_be_named_as_the_os_resource(settings: Any) -> None:
    configured = _configure(settings)
    with pytest.raises(ValueError, match="one exact configured resource"):
        _build(configured, os_resource=entry.PUBLIC_MCP_RESOURCE)


def test_reconcile_route_is_absent_only_in_public_mode(settings: Any, rsa_key: object) -> None:
    submit = fixture._submit_token(rsa_key, aud=entry.PUBLIC_MCP_RESOURCE)
    default_token = fixture._submit_token(rsa_key)
    reconcile = "/v1/tools/submit_ceo_intent/reconcile"

    async def exercise() -> None:
        async with _client(_build(_configure(settings))) as http:
            response = await http.post(
                reconcile, headers=_bearer(submit, **PUBLIC_HOST_HEADERS), json={}
            )
            assert response.status_code == 404
        default = _configure(settings, public=False, os_transport=False, tunnels=())
        async with _client(_build(default, os_transport=False)) as http:
            response = await http.post(
                reconcile, headers=_bearer(default_token, **PUBLIC_HOST_HEADERS), json={}
            )
            assert response.status_code != 404

    _run(exercise())


# --------------------------------------------------------------------------
# Unconfigured default is unchanged
# --------------------------------------------------------------------------

def test_default_without_public_key_keeps_every_incumbent_audience(
    settings: Any, rsa_key: object
) -> None:
    configured = _configure(settings, public=False)
    assert configured.public_policies is None

    async def exercise() -> None:
        async with _client(_build(configured)) as http:
            for audience in (None, entry.OS_EXECUTIVE_RESOURCE, TUNNEL):
                token = (
                    fixture._submit_token(rsa_key)
                    if audience is None
                    else fixture._submit_token(rsa_key, aud=audience)
                )
                response = await http.post(
                    "http://127.0.0.1/mcp",
                    headers=_bearer(token, **MCP_HEADERS),
                    json=INITIALIZE,
                )
                assert response.status_code == 200, (audience, response.text)
            # The public audience is not configured, so it is refused.
            public = fixture._submit_token(rsa_key, aud=entry.PUBLIC_MCP_RESOURCE)
            refused = await http.post(
                "http://127.0.0.1/mcp",
                headers=_bearer(public, **MCP_HEADERS),
                json=INITIALIZE,
            )
            assert refused.status_code == 401
            missing = await http.post("http://127.0.0.1/mcp", headers=MCP_HEADERS, json=INITIALIZE)
            assert missing.status_code == 401
            assert (
                f'resource_metadata="{configured.policies.submit.resource_metadata_url}"'
                in _challenge(missing)
            )
            # No public metadata document exists unless the key is configured.
            absent = await http.get(
                "/.well-known/oauth-protected-resource/mcp", headers=PUBLIC_HOST_HEADERS
            )
            assert absent.status_code == 404

    _run(exercise())


# --------------------------------------------------------------------------
# Sealed-config validation
# --------------------------------------------------------------------------

def test_validate_public_mcp_resource_accepts_only_the_exact_public_audience() -> None:
    assert entry.validate_public_mcp_resource({"executive_mcp_profile": "web_ceo_v3"}) is None
    ok = {"executive_mcp_profile": "web_ceo_v3", "public_mcp_resource": entry.PUBLIC_MCP_RESOURCE}
    assert entry.validate_public_mcp_resource(ok) == "https://mcp.mastermind-x.com/mcp"
    bad_values = (
        entry.PUBLIC_MCP_RESOURCE + "/",
        entry.PUBLIC_MCP_RESOURCE + "/x",
        "http://mcp.mastermind-x.com/mcp",
        "https://mcp.mastermind-x.com",
        entry.OS_EXECUTIVE_RESOURCE,
        FOREIGN,
        TUNNEL,
        "",
        None,
        1,
    )
    for value in bad_values:
        with pytest.raises(ValueError, match="public MCP resource must be"):
            entry.validate_public_mcp_resource({**ok, "public_mcp_resource": value})
    for profile in (None, "web_ceo_v2", "web_ceo_sessions", "web_ceo", "executive", "release_control"):
        raw = {**ok}
        if profile is None:
            raw.pop("executive_mcp_profile")
        else:
            raw["executive_mcp_profile"] = profile
        with pytest.raises(ValueError, match="public MCP resource must be"):
            entry.validate_public_mcp_resource(raw)
    for refused in ("coo", "principal_ruling_target"):
        with pytest.raises(ValueError, match="public MCP resource must be"):
            entry.validate_public_mcp_resource({**ok, refused: {}})


def test_build_public_policies_derives_a_resource_only_variant(settings: Any) -> None:
    raw = _raw(os_transport=False, tunnels=())
    assert entry.build_public_policies({"executive_mcp_profile": "web_ceo_v3"}, settings.policies) is None
    public = entry.build_public_policies(raw, settings.policies)
    assert public.read.resource == public.submit.resource == entry.PUBLIC_MCP_RESOURCE
    assert (
        public.read.resource_metadata_url
        == public.submit.resource_metadata_url
        == entry.PUBLIC_MCP_METADATA_URL
    )
    for derived, primary in ((public.read, settings.policies.read), (public.submit, settings.policies.submit)):
        assert derived.policy_id == primary.policy_id
        assert derived.required_scopes == primary.required_scopes
        assert dataclasses.replace(
            derived,
            resource=primary.resource,
            resource_metadata_url=primary.resource_metadata_url,
        ) == primary


def test_build_public_policies_refuses_a_duplicate_resource(settings: Any) -> None:
    raw = _raw(os_transport=False, tunnels=())
    collided = dataclasses.replace(
        settings.policies,
        read=dataclasses.replace(settings.policies.read, resource=entry.PUBLIC_MCP_RESOURCE),
        submit=dataclasses.replace(settings.policies.submit, resource=entry.PUBLIC_MCP_RESOURCE),
    )
    with pytest.raises(ValueError, match="cannot duplicate"):
        entry.build_public_policies(raw, collided)
    other = entry.build_additional_policies(_raw(public=False, os_transport=False), settings.policies)
    clash = dataclasses.replace(
        other[0],
        read=dataclasses.replace(other[0].read, resource=entry.PUBLIC_MCP_RESOURCE),
        submit=dataclasses.replace(other[0].submit, resource=entry.PUBLIC_MCP_RESOURCE),
    )
    with pytest.raises(ValueError, match="cannot duplicate"):
        entry.build_public_policies(raw, settings.policies, (clash,))


def _document() -> dict[str, Any]:
    return {
        "schema": entry.CONFIG_SCHEMA,
        "release_sha": "1" * 40,
        "service_uid": 458,
        "port": 8443,
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "policies": {},
        "executive_mcp_profile": "web_ceo_v3",
    }


def test_installed_document_allowlist_accepts_the_public_key_only_when_valid() -> None:
    document = _document()
    assert entry.validate_document(copy.deepcopy(document)) is not None
    with_public = {**document, "public_mcp_resource": entry.PUBLIC_MCP_RESOURCE}
    assert entry.validate_document(copy.deepcopy(with_public))["public_mcp_resource"] == (
        entry.PUBLIC_MCP_RESOURCE
    )
    for value in (FOREIGN, TUNNEL, entry.OS_EXECUTIVE_RESOURCE):
        with pytest.raises(ValueError):
            entry.validate_document({**document, "public_mcp_resource": value})
    with pytest.raises(ValueError):
        entry.validate_document(
            {**with_public, "executive_mcp_profile": "web_ceo_v2"}
        )
    with pytest.raises(ValueError):
        entry.validate_document({**with_public, "unknown_extra_key": True})


# --------------------------------------------------------------------------
# AppSettings validation and builder confinement
# --------------------------------------------------------------------------

def test_app_settings_validate_the_public_policies(settings: Any) -> None:
    configured = _configure(settings, os_transport=False, tunnels=())
    public = configured.public_policies
    assert dataclasses.replace(settings, public_policies=public).public_policies is public

    with pytest.raises(ValueError, match="public_policies must be AppPolicies"):
        dataclasses.replace(settings, public_policies="not-policies")
    # The public resource may not repeat the primary resource.
    with pytest.raises(ValueError, match="must be unique"):
        dataclasses.replace(
            settings,
            public_policies=dataclasses.replace(
                public,
                read=dataclasses.replace(public.read, resource=settings.policies.read.resource),
                submit=dataclasses.replace(public.submit, resource=settings.policies.submit.resource),
            ),
        )
    # It may differ from the primary pair only by resource and metadata URL.
    with pytest.raises(ValueError, match="may differ only by resource"):
        dataclasses.replace(
            settings,
            public_policies=dataclasses.replace(
                public,
                submit=dataclasses.replace(
                    public.submit,
                    max_token_lifetime_seconds=public.submit.max_token_lifetime_seconds + 1,
                ),
            ),
        )


def test_public_mode_is_refused_by_every_other_builder(settings: Any) -> None:
    configured = _configure(settings, os_transport=False, tunnels=())
    match = "public MCP audience is not supported"
    sink = Sink()
    for build in (
        lambda: transport_server.build_executive_mcp_app(configured, audit_sink=sink),
        lambda: transport_server.build_web_ceo_mcp_app(configured, audit_sink=sink),
        lambda: transport_server.build_web_ceo_v2_mcp_app(configured, audit_sink=sink),
        lambda: transport_server.build_web_ceo_sessions_mcp_app(
            configured,
            audit_sink=sink,
            session_target_projector=lambda *_: [],
            session_reply_handler=lambda *_: {},
            session_summon_handler=lambda *_: {},
        ),
        lambda: transport_server.build_release_control_mcp_app(configured, audit_sink=sink),
        lambda: transport_server.build_coo_mcp_app(
            types.SimpleNamespace(executive=configured), audit_sink=sink
        ),
        lambda: transport_server.build_personal_read_mcp_app(
            dataclasses.replace(configured, read_from_ceo_ingress=True, read_only=False),
            audit_sink=sink,
        ),
    ):
        with pytest.raises(ValueError, match=match):
            build()


# --------------------------------------------------------------------------
# tools/call in public mode: direct tools and relayed inner refusals
# --------------------------------------------------------------------------

TOOL_HEADERS = {"host": "127.0.0.1", **MCP_HEADERS, "mcp-protocol-version": "2025-06-18"}
SEND_ARGUMENTS = {
    "target_ref": "codex:BIND-1",
    "instruction": "continue",
    "stop_condition": "return result",
    "operation_key": "public-audience-send-1",
}
SUBMIT_ARGUMENTS = {
    "operation_key": "public-audience-submit-1",
    "objective": "bounded task",
    "department": "executive-infrastructure",
    "priority": 0,
    "execution_profile": "research_only",
    "workstream": "WS:SESSION-BRIDGE",
}


class _RefusingJwks:
    """A key cache that never yields a key, so a verifier built on it refuses."""

    async def key_for(self, kid: str) -> Any:
        raise AuthError(AuthErrorCode.KEY_NOT_FOUND)


def _count_jwks(
    rsa_key: object,
    monkeypatch: pytest.MonkeyPatch,
    *,
    refuse_public_from: int | None = None,
) -> dict[str, int]:
    """Count JWKS-cache builds per resource.

    The outer ``/mcp`` authenticators build the public cache first and the
    inner App's variant chain builds its own afterwards, so
    ``refuse_public_from=2`` leaves the outer layer able to verify a public
    token while the inner App cannot: the only way to reach the relayed
    inner-refusal branch with a token the outer layer already accepted.
    """
    builds: dict[str, int] = {}

    def factory(policy: Any) -> Any:
        builds[policy.resource] = builds.get(policy.resource, 0) + 1
        if (
            refuse_public_from is not None
            and policy.resource == entry.PUBLIC_MCP_RESOURCE
            and builds[policy.resource] >= refuse_public_from
        ):
            return _RefusingJwks()
        return fixture._FakeJwksCache(rsa_key)

    monkeypatch.setattr(gateway, "_default_jwks_cache", factory)
    return builds


async def _tool_call(http: httpx.AsyncClient, token: str, name: str, arguments: dict[str, Any]) -> httpx.Response:
    return await http.post(
        "http://127.0.0.1/mcp",
        headers=_bearer(token, **TOOL_HEADERS),
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def _refusal_challenge(response: httpx.Response) -> tuple[str, str]:
    """The (challenge, serialized result) of a tool-level authentication refusal."""
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["isError"] is True, result
    return result["_meta"]["mcp/www_authenticate"][0], json.dumps(result)


def _assert_public_challenge(configured: Any, *texts: str) -> None:
    """No text may name the primary, OS or tunnel resource or its metadata."""
    for text in texts:
        for hidden in (
            configured.policies.read.resource_metadata_url,
            configured.policies.read.resource,
            entry.OS_EXECUTIVE_RESOURCE,
            TUNNEL,
            "tunnel-service",
        ):
            assert hidden not in text


def test_relayed_inner_refusal_challenge_is_rebuilt_from_the_public_metadata(
    settings: Any, rsa_key: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The outer /mcp layer accepts the public token; the inner App's own
    # verifier (which still carries every variant) then refuses it with a
    # challenge built from the PRIMARY policy. That challenge must never be
    # relayed: it would name the primary/tunnel metadata.
    configured = _configure(settings)
    builds = _count_jwks(rsa_key, monkeypatch, refuse_public_from=2)
    token = fixture._read_token(rsa_key, aud=entry.PUBLIC_MCP_RESOURCE)
    app = _build(configured)
    assert builds[entry.PUBLIC_MCP_RESOURCE] == 2, builds

    async def exercise() -> None:
        async with _client(app) as http:
            response = await _tool_call(http, token, "executive_state", {})
            challenge, serialized = _refusal_challenge(response)
            assert f'resource_metadata="{entry.PUBLIC_MCP_METADATA_URL}"' in challenge
            _assert_public_challenge(configured, challenge, serialized)

    _run(exercise())


def test_relayed_submit_scope_refusal_names_only_the_public_metadata(
    settings: Any, rsa_key: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = _configure(settings)
    _count_jwks(rsa_key, monkeypatch)
    read_only = fixture._read_token(rsa_key, aud=entry.PUBLIC_MCP_RESOURCE)

    async def exercise() -> None:
        async with _client(_build(configured)) as http:
            response = await _tool_call(http, read_only, "submit_ceo_intent", SUBMIT_ARGUMENTS)
            challenge, serialized = _refusal_challenge(response)
            assert f'resource_metadata="{entry.PUBLIC_MCP_METADATA_URL}"' in challenge
            assert gateway.SUBMIT_SCOPE in challenge
            _assert_public_challenge(configured, challenge, serialized)

    _run(exercise())


def test_direct_read_tool_accepts_the_public_audience(settings: Any, rsa_key: object) -> None:
    configured = _configure(settings)
    token = fixture._read_token(rsa_key, aud=entry.PUBLIC_MCP_RESOURCE)

    async def exercise() -> None:
        async with _client(_build(configured)) as http:
            response = await _tool_call(http, token, "session_targets", {"kind": "codex"})
            assert response.status_code == 200, response.text
            result = response.json()["result"]
            assert not result.get("isError"), result
            assert json.loads(result["content"][0]["text"])["ok"] is True

    _run(exercise())


@pytest.mark.parametrize(
    "audience",
    [None, entry.OS_EXECUTIVE_RESOURCE, TUNNEL, FOREIGN],
)
@pytest.mark.parametrize("tool", ["session_targets", "session_send"])
def test_direct_tools_refuse_every_non_public_audience(
    settings: Any, rsa_key: object, audience: str | None, tool: str
) -> None:
    configured = _configure(settings)
    maker = fixture._submit_token
    token = maker(rsa_key) if audience is None else maker(rsa_key, aud=audience)
    arguments = {"kind": "codex"} if tool == "session_targets" else SEND_ARGUMENTS

    async def exercise() -> None:
        async with _client(_build(configured)) as http:
            response = await _tool_call(http, token, tool, arguments)
            assert response.status_code == 401, response.text
            challenge = _challenge(response)
            assert f'resource_metadata="{entry.PUBLIC_MCP_METADATA_URL}"' in challenge
            _assert_public_challenge(configured, challenge, response.text)

    _run(exercise())


def test_direct_submit_tool_scope_refusal_uses_the_public_submit_challenge(
    settings: Any, rsa_key: object
) -> None:
    configured = _configure(settings)
    read_only = fixture._read_token(rsa_key, aud=entry.PUBLIC_MCP_RESOURCE)

    async def exercise() -> None:
        async with _client(_build(configured)) as http:
            response = await _tool_call(http, read_only, "session_send", SEND_ARGUMENTS)
            challenge, serialized = _refusal_challenge(response)
            assert f'resource_metadata="{entry.PUBLIC_MCP_METADATA_URL}"' in challenge
            assert gateway.SUBMIT_SCOPE in challenge
            _assert_public_challenge(configured, challenge, serialized)

    _run(exercise())
