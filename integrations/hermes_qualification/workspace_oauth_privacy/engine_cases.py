"""Real pinned Hermes OAuth bodies + MCP 2.3/httpx2 2.15.1, in-process HTTP.

The authorization server, protected HTTP resources, consent/callback UI, PM
help text and version label are declared fixture edges. The original provider,
SDK generator, PKCE, storage, atomic JSON writer and file refresh fence execute.
No socket, real account, installed role, model or production request is used.
Run this file explicitly in the separately pinned engine environment.
"""
from __future__ import annotations

import ast
import asyncio
import base64
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import importlib
import importlib.metadata
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest

from integrations.hermes_qualification.workspace_oauth_privacy import qualify

ROOT = Path(__file__).parent
FIXTURES = ROOT / "fixtures"
PROVENANCE = json.loads((FIXTURES / "provenance.json").read_bytes())
DEPENDENCIES = {
    "mcp.client.auth.oauth2": "c513a99b46d5d15e17add81a465749fccc0e84d0",
    "mcp.shared._httpx_utils": "7107e5e535e591e56fa1c7c7b78fb812d7cb0f4b",
    "mcp.client.streamable_http": "053f1f10a93c9bbfb5bd398a13d034cdfd113669",
    "mcp.client.session": "ac0263df739e7f37ded2648063f947f2510877b2",
    "mcp_types._types": "5852d9bba3162caeb0b5399850aa176de9acaa02",
    "httpx2._auth": "8418bf04c950d1adb15b56f27c1f7f4497fb6920",
    "httpx2._client": "2103d36e3416d7c000a0fd5ec26c390b8beb6e91",
}
ISSUER = "https://issuer.example"
CLIENT = "inert-client"
PRINCIPAL_SCOPE = "1" * 64
PROTOCOL = "2025-11-25"


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def test_actual_dependency_versions_and_release_source_bodies():
    assert importlib.metadata.version("mcp") == "2.3.0"
    assert importlib.metadata.version("httpx2") == "2.15.1"
    for name, expected in DEPENDENCIES.items():
        assert blob(Path(inspect.getfile(importlib.import_module(name))).read_bytes()) == expected


def edge(monkeypatch, name, **values):
    module = ModuleType(name)
    module.__dict__.update(values)
    monkeypatch.setitem(sys.modules, name, module)
    parent, _, attribute = name.rpartition(".")
    if parent in sys.modules:
        monkeypatch.setattr(sys.modules[parent], attribute, module, raising=False)
    return module


@pytest.fixture
def engine(tmp_path, monkeypatch):
    assert importlib.metadata.version("mcp") == "2.3.0"
    assert importlib.metadata.version("httpx2") == "2.15.1"
    sources = {}
    for path, row in PROVENANCE["files"].items():
        data = (FIXTURES / row["fixture"]).read_bytes()
        assert len(data) == row["bytes"] and blob(data) == row["git_blob"]
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        sources[path] = data
    sources.update(qualify.prepare_sources({p: sources[p] for p in qualify.PATHS}))
    vendor = tmp_path / "derived"
    for path, data in sources.items():
        target = vendor / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for name in ("tools", "agent", "hermes_cli"):
        edge(monkeypatch, name, __path__=[str(vendor / name)])
    edge(monkeypatch, "pm", install_hint=lambda *_a, **_k: "unused package help fixture")
    edge(monkeypatch, "hermes_yaml")  # No YAML operation occurs in these OAuth flows.
    edge(monkeypatch, "hermes_cli.version_info", get_version_info=lambda: SimpleNamespace(base_version="source-fixture"))
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, vendor / path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        parent, _, attribute = name.rpartition(".")
        if parent in sys.modules:
            monkeypatch.setattr(sys.modules[parent], attribute, module, raising=False)
        spec.loader.exec_module(module)
        return module
    hc = load("hermes_constants", "hermes_constants.py")
    load("hermes_dir_acl", "hermes_dir_acl.py")
    home = tmp_path / "profile"
    home.mkdir(mode=0o700)
    token = hc.set_hermes_home_override(home)
    load("utils", "utils.py")  # Actual atomic JSON writer and URL helpers.
    load("tools.mcp_dashboard_oauth", "tools/mcp_dashboard_oauth.py")
    mo = load("tools.mcp_oauth", "tools/mcp_oauth.py")
    load("tools.mcp_oauth_provider", "tools/mcp_oauth_provider.py")
    manager_module = load("tools.mcp_oauth_manager", "tools/mcp_oauth_manager.py")
    core = edge(monkeypatch, "tools.mcp_tool", sdk_httpx=lambda: httpx2,
        _JSONRPC_METHOD_NOT_FOUND=-32601, _MCP_NEW_HTTP=True,
        _MCP_HTTP_AVAILABLE=True, _DEFAULT_CONNECT_TIMEOUT=30,
        LATEST_HANDSHAKE_VERSION=PROTOCOL, _ensure_mcp_sdk=lambda: None)
    redact = load("agent.redact", "agent/redact.py")
    edge(monkeypatch, "tools.mcp_tool_common", _core=core, _exc_str=str,
        _sanitize_error=lambda text: redact.redact_sensitive_text(text, force=True))
    edge(monkeypatch, "tools.mcp_tool_node_abi", NodeAbiMismatchError=type("NodeAbiMismatchError", (RuntimeError,), {}))
    errors = load("tools.mcp_tool_errors", "tools/mcp_tool_errors.py")
    m = manager_module
    oauth = dict(client_id=CLIENT, scope=m.WORKSPACE_PRIMARY_SCOPE,
        workspace=dict(schema=m.WORKSPACE_OAUTH_SCHEMA, resource=m.WORKSPACE_RESOURCE,
            identity_url=m.WORKSPACE_IDENTITY_URL, scope=m.WORKSPACE_SCOPE, principal_scope=PRINCIPAL_SCOPE))
    e = SimpleNamespace(vendor=vendor, home=home, hc=hc, mo=mo, m=m, core=core,
                        errors=errors, redact=redact, oauth=oauth, load=load)
    oracle = Oracle(e)
    e.oracle = oracle
    callback_slots = []
    def configure(cfg, storage):
        port = 42000 + len(callback_slots)
        callback_slots.append({})
        cfg["_resolved_port"] = port
        return port
    def redirect_factory(port, **_kwargs):
        async def redirect(url):
            mo._raise_if_non_interactive("Fixture consent requires explicit attendance.")
            query = parse_qs(urlsplit(url).query)
            oracle.consents.append(query)
            assert query["client_id"] == [CLIENT]
            resource = query["resource"][0]
            assert query["scope"] == [oracle.scope(resource)]
            if oracle.consent_hook:
                await oracle.consent_hook(resource)
            code = "fixture-code-" + str(len(oracle.codes) + 1)
            oracle.codes[code] = query
            callback_slots[port - 42000].update(code=code, state=query["state"][0])
        return redirect
    def callback_factory(port, *_args, **_kwargs):
        from mcp.client.auth.oauth2 import AuthorizationCodeResult
        async def callback():
            value = callback_slots[port - 42000]
            return AuthorizationCodeResult(code=value["code"], state=value["state"], iss=ISSUER)
        return callback
    monkeypatch.setattr(mo, "_configure_callback_port", configure)
    monkeypatch.setattr(mo, "_make_redirect_handler", redirect_factory)
    monkeypatch.setattr(mo, "_make_callback_waiter", callback_factory)
    monkeypatch.setattr(mo, "_stdin_is_console", lambda: False)
    try:
        yield e
    finally:
        hc.reset_hermes_home_override(token)


class Oracle:
    """Inert authorization server/resources; no production credential or grant."""
    def __init__(self, e):
        self.e = e
        self.codes, self.tokens, self.requests = {}, {}, []
        self.consents = []
        self.generation = 0
        self.hook = self.consent_hook = None
        self.redirect_resource = None
        self.principal_scope = PRINCIPAL_SCOPE
        self.stream = None
        self.rpc = False
        self.rpc_tool = "fixture_read"
        self.rpc_tools = None
        self.rpc_text = "inert-current-context-response"
        self.server_info = {"name": "inert-protected-coo", "version": "1"}
        self.token_scope = "selected"
        self.authorization_endpoint = ISSUER + "/authorize"
        self.require_timeout = True

    def scope(self, resource):
        m = self.e.m
        assert resource in {m.WORKSPACE_RESOURCE, m.WORKSPACE_PRIMARY_RESOURCE}
        return m.WORKSPACE_SCOPE if resource == m.WORKSPACE_RESOURCE else m.WORKSPACE_PRIMARY_SCOPE

    def metadata_url(self, resource):
        return "https://mcp.mastermind-x.com/.well-known/oauth-protected-resource" + urlsplit(resource).path

    async def __call__(self, request):
        m = self.e.m
        url = str(request.url)
        self.requests.append((request.method, url, dict(request.headers), bytes(request.content)))
        if self.require_timeout:
            assert isinstance(request.extensions.get("timeout"), dict)
        if self.hook:
            response = await self.hook(request)
            if response is not None:
                return response
        for resource, target in ((m.WORKSPACE_RESOURCE, m.WORKSPACE_IDENTITY_URL),
                                 (m.WORKSPACE_PRIMARY_RESOURCE, m.WORKSPACE_PRIMARY_URL)):
            if url == self.metadata_url(resource):
                assert m.WORKSPACE_HEADER not in request.headers
                return httpx2.Response(200, json=dict(resource=resource, authorization_servers=[ISSUER],
                    scopes_supported=self.scope(resource).split(), bearer_methods_supported=["header"]))
            if url != target:
                continue
            if self.redirect_resource == resource:
                return httpx2.Response(307, headers={"location": target + "/other"})
            pair = self.tokens.get(resource)
            if pair is None or request.headers.get("authorization") != "Bearer " + pair["access_token"]:
                return httpx2.Response(401, headers={"WWW-Authenticate":
                    'Bearer resource_metadata="' + self.metadata_url(resource) + '", scope="' + self.scope(resource) + '"'})
            if resource == m.WORKSPACE_RESOURCE:
                assert m.WORKSPACE_HEADER not in request.headers
                return httpx2.Response(200, json=dict(schema="mastermind.native_draft_identity.v1",
                    principal_scope=self.principal_scope, expires_at_ms=int((time.time() + 300) * 1000)))
            assert request.headers[m.WORKSPACE_HEADER] == "Bearer " + self.tokens[m.WORKSPACE_RESOURCE]["access_token"]
            if self.rpc:
                if request.method != "POST":
                    return httpx2.Response(405)
                message = json.loads(request.content)
                if "id" not in message:
                    assert message["method"] == "notifications/initialized"
                    return httpx2.Response(202)
                if message["method"] == "initialize":
                    result = dict(protocolVersion=PROTOCOL, capabilities={"tools": {}},
                                  serverInfo=self.server_info)
                elif message["method"] == "tools/list":
                    result = {"tools": self.rpc_tools or [{"name": self.rpc_tool, "description": "Inert fixture only",
                                        "inputSchema": {"type": "object", "properties": {}}}]}
                else:
                    assert message["method"] == "tools/call" and message["params"]["name"] == self.rpc_tool
                    result = {"content": [{"type": "text", "text": self.rpc_text}], "isError": False}
                return httpx2.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": result})
            if self.stream:
                return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=self.stream)
            return httpx2.Response(200, json={"fixture": "authenticated-coo-response"})
        assert m.WORKSPACE_HEADER not in request.headers
        if url == ISSUER + "/.well-known/oauth-authorization-server":
            return httpx2.Response(200, json=dict(issuer=ISSUER, authorization_endpoint=self.authorization_endpoint,
                token_endpoint=ISSUER + "/token", response_types_supported=["code"],
                grant_types_supported=["authorization_code", "refresh_token"],
                token_endpoint_auth_methods_supported=["none"], code_challenge_methods_supported=["S256"]))
        if url == ISSUER + "/token":
            fields = parse_qs(request.content.decode(), strict_parsing=True)
            resource = fields["resource"][0]
            assert fields["client_id"] == [CLIENT]
            if fields["grant_type"] == ["authorization_code"]:
                code = self.codes.pop(fields["code"][0])
                expected = base64.urlsafe_b64encode(hashlib.sha256(fields["code_verifier"][0].encode()).digest()).rstrip(b"=").decode()
                assert code["code_challenge"] == [expected]
                assert code["resource"] == [resource]
                assert code["redirect_uri"] == fields["redirect_uri"]
            else:
                assert fields["grant_type"] == ["refresh_token"]
                assert fields["refresh_token"] == [self.tokens[resource]["refresh_token"]]
            self.generation += 1
            pair = dict(access_token="inert-access-" + str(self.generation),
                refresh_token="inert-refresh-" + str(self.generation), token_type="Bearer",
                expires_in=3600, scope=self.scope(resource))
            if self.token_scope != "selected":
                if self.token_scope is None:
                    pair.pop("scope")
                else:
                    pair["scope"] = self.token_scope
            self.tokens[resource] = pair
            return httpx2.Response(200, json=pair)
        raise AssertionError("unplanned fixture request " + url)


def new_auth(e):
    return e.m.get_manager().get_workspace_provider(e.m.WORKSPACE_PRIMARY_SERVER,
                                                  e.m.WORKSPACE_PRIMARY_URL, e.oauth)


@asynccontextmanager
async def client(e, auth):
    build = e.errors._make_redirect_header_stripper(httpx2, httpx2.URL(e.m.WORKSPACE_PRIMARY_URL),
        strict=True, configured_header_names={e.m.WORKSPACE_HEADER}, fixed_workspace_oauth=True)
    async with build(auth=auth, timeout=httpx2.Timeout(5.0), follow_redirects=True,
                     transport=httpx2.MockTransport(e.oracle)) as value:
        yield value


async def send(e, value):
    return await value.post(e.m.WORKSPACE_PRIMARY_URL,
        headers={"MCP-Protocol-Version": PROTOCOL}, json={"inert_fixture": True})


async def authorize(e):
    with e.mo.force_interactive_oauth():
        auth = new_auth(e)
        async with client(e, auth) as value:
            response = await send(e, value)
            assert response.status_code == 200
    assert auth.verified()
    return auth


def test_two_actual_sdk_authorizations_use_one_client_and_original_stores(engine):
    e = engine
    auth = asyncio.run(authorize(e))
    assert len(e.oracle.tokens) == 2 and e.oracle.generation == 2
    for provider, resource in ((auth._primary, e.m.WORKSPACE_PRIMARY_RESOURCE),
                               (auth._workspace, e.m.WORKSPACE_RESOURCE)):
        assert provider.context.server_url == resource
        assert provider.context.storage._hermes_home == e.home
        assert provider.context.storage._tokens_path().is_file()
        assert provider.context.storage._meta_path().is_file()
        assert provider.context.lock.value == 1
        assert provider._hermes_fence is None
    assert all(e.m.WORKSPACE_HEADER not in headers for _method, url, headers, _body in e.oracle.requests
               if url != e.m.WORKSPACE_PRIMARY_URL)


def test_unattended_missing_companion_refuses_without_opening_consent(engine):
    e = engine
    with pytest.raises(e.mo.OAuthNonInteractiveError):
        new_auth(e)
    assert e.oracle.requests == [] and e.oracle.codes == {}


@pytest.mark.parametrize("selected", ["workspace", "primary"])
def test_each_resource_refreshes_its_original_rotating_token(engine, selected):
    e = engine
    async def run():
        auth = await authorize(e)
        provider = getattr(auth, "_" + selected)
        stored = await provider.context.storage.get_tokens()
        await provider.context.storage.set_tokens(stored.model_copy(update={"expires_in": 0}))
        provider.context.token_expiry_time = time.time() - 1
        before = len(e.oracle.requests)
        async with client(e, auth) as value:
            assert (await send(e, value)).status_code == 200
        grants = [parse_qs(body.decode()) for _method, url, _headers, body in e.oracle.requests[before:]
                  if url == ISSUER + "/token"]
        assert len(grants) == 1 and grants[0]["grant_type"] == ["refresh_token"]
        assert grants[0]["resource"] == [provider.context.server_url]
        assert e.oracle.generation == 3
        assert provider._hermes_fence is None and provider.context.lock.value == 1
    asyncio.run(run())


@pytest.mark.parametrize("selected", ["WORKSPACE_RESOURCE", "WORKSPACE_PRIMARY_RESOURCE"])
def test_protected_same_origin_redirect_never_reaches_destination(engine, selected):
    e = engine
    async def run():
        auth = await authorize(e)
        e.oracle.redirect_resource = getattr(e.m, selected)
        async with client(e, auth) as value:
            with pytest.raises(e.m.WorkspaceOAuthError, match="^WORKSPACE_OAUTH_UNAVAILABLE$"):
                await send(e, value)
        assert not auth.verified()
        assert not any(url.endswith("/other") for _, url, _, _ in e.oracle.requests)
    asyncio.run(run())


def test_foreign_identity_is_withheld_before_primary_request(engine):
    e = engine
    async def run():
        auth = await authorize(e)
        e.oracle.requests.clear()
        e.oracle.principal_scope = "2" * 64
        async with client(e, auth) as value:
            with pytest.raises(e.m.WorkspaceOAuthError):
                await send(e, value)
        assert not any(url == e.m.WORKSPACE_PRIMARY_URL for _, url, _, _ in e.oracle.requests)
    asyncio.run(run())


def test_cached_tokens_without_metadata_refuse_hidden_second_client(engine, monkeypatch):
    e = engine
    async def run():
        auth = await authorize(e)
        auth._workspace.context.storage._meta_path().unlink()
        e.m.get_manager().evict(e.m.WORKSPACE_SERVER)
        next_auth = new_auth(e)
        async def forbidden(*_a, **_k):
            pytest.fail("fixed variant must not open the donor's prefetch client")
        monkeypatch.setattr(next_auth._workspace, "_prefetch_oauth_metadata", forbidden)
        async with client(e, next_auth) as value:
            with pytest.raises(e.m.WorkspaceOAuthError):
                await send(e, value)
        assert not next_auth.verified()
    asyncio.run(run())


def test_eviction_and_restore_of_same_entry_invalidates_suspended_flow(engine):
    e = engine
    async def run():
        auth = await authorize(e)
        async def hook(request):
            if str(request.url) == e.m.WORKSPACE_IDENTITY_URL:
                manager = e.m.get_manager()
                entry = manager.evict(e.m.WORKSPACE_SERVER)
                manager.restore_entry(e.m.WORKSPACE_SERVER, entry)
        e.oracle.hook = hook
        e.oracle.requests.clear()
        async with client(e, auth) as value:
            with pytest.raises(e.m.WorkspaceOAuthError):
                await send(e, value)
        assert not any(url == e.m.WORKSPACE_PRIMARY_URL for _, url, _, _ in e.oracle.requests)
        assert auth._workspace.context.lock.value == 1
    asyncio.run(run())


def test_cancelling_waiter_does_not_release_other_flows_refresh_fence(engine):
    e = engine
    async def run():
        auth = await authorize(e)
        provider = auth._workspace
        stored = await provider.context.storage.get_tokens()
        await provider.context.storage.set_tokens(stored.model_copy(update={"expires_in": 0}))
        provider.context.token_expiry_time = time.time() - 1
        reached, release = asyncio.Event(), asyncio.Event()
        async def hook(request):
            if str(request.url) == ISSUER + "/token":
                reached.set()
                await release.wait()
        e.oracle.hook = hook
        async with client(e, auth) as value:
            first = asyncio.create_task(send(e, value))
            await asyncio.wait_for(reached.wait(), 2)
            fd = provider._hermes_fence
            lease = provider._hermes_fence_lease
            assert fd is not None and lease is not None
            second = asyncio.create_task(send(e, value))
            await asyncio.sleep(0)
            second.cancel()
            with pytest.raises(asyncio.CancelledError):
                await second
            assert provider._hermes_fence == fd and provider._hermes_fence_lease is lease
            release.set()
            assert (await asyncio.wait_for(first, 2)).status_code == 200
        assert provider._hermes_fence is None and provider.context.lock.value == 1
        async with client(e, auth) as value:
            assert (await send(e, value)).status_code == 200
    asyncio.run(run())


def test_cross_task_generator_close_balances_original_context_semaphore(engine):
    e = engine
    async def run():
        auth = await authorize(e)
        request = httpx2.Request("GET", e.m.WORKSPACE_IDENTITY_URL,
                                headers={"MCP-Protocol-Version": PROTOCOL})
        flow = auth._workspace.async_auth_flow(request)
        assert await flow.__anext__() is request
        assert auth._workspace.context.lock.value == 1
        await asyncio.create_task(flow.aclose())
        assert auth._workspace.context.lock.value == 1
        assert auth._workspace._hermes_fence is None
        async with client(e, auth) as value:
            assert (await send(e, value)).status_code == 200
    asyncio.run(run())


def test_primary_event_stream_is_not_buffered_by_auth_adapter(engine):
    e = engine
    class Stream(httpx2.AsyncByteStream):
        read = False
        async def __aiter__(self):
            self.read = True
            yield b"data: fixture\n\n"
    async def run():
        auth = await authorize(e)
        e.oracle.stream = stream = Stream()
        async with client(e, auth) as value:
            request = value.build_request("GET", e.m.WORKSPACE_PRIMARY_URL,
                                         headers={"MCP-Protocol-Version": PROTOCOL})
            response = await value.send(request, stream=True, follow_redirects=False)
            assert response.status_code == 200 and stream.read is False
            assert e.m.WORKSPACE_HEADER not in request.headers
            await response.aclose()
    asyncio.run(run())


def test_cold_restart_refresh_keeps_both_exact_resource_operands(engine):
    e = engine
    async def run():
        auth = await authorize(e)
        for provider in (auth._primary, auth._workspace):
            stored = await provider.context.storage.get_tokens()
            await provider.context.storage.set_tokens(stored.model_copy(update={"expires_in": 0}))
        e.m.reset_manager_for_tests()
        cold = new_auth(e)
        assert cold._primary.context.protected_resource_metadata is None
        assert cold._workspace.context.protected_resource_metadata is None
        e.oracle.requests.clear()
        async with client(e, cold) as value:
            assert (await send(e, value)).status_code == 200
        grants = [parse_qs(body.decode()) for _, url, _, body in e.oracle.requests if url == ISSUER + "/token"]
        assert len(grants) == 2 and all(g["grant_type"] == ["refresh_token"] for g in grants)
        assert {g["resource"][0] for g in grants} == {e.m.WORKSPACE_RESOURCE, e.m.WORKSPACE_PRIMARY_RESOURCE}
    asyncio.run(run())


@pytest.mark.parametrize("change", ["profile", "config", "workspace_credential"])
def test_drift_during_identity_or_primary_authorization_refuses_same_invocation(engine, change):
    e = engine
    async def run():
        auth = await authorize(e)
        e.oracle.requests.clear()
        home_token = None
        async def hook(request):
            nonlocal home_token
            if str(request.url) == e.m.WORKSPACE_IDENTITY_URL:
                if change == "profile":
                    home_token = e.hc.set_hermes_home_override(e.home.parent / "other-profile")
                elif change == "config":
                    changed = deepcopy(e.oauth)
                    changed["workspace"]["principal_scope"] = "3" * 64
                    e.m.get_manager().get_workspace_provider(e.m.WORKSPACE_PRIMARY_SERVER,
                                                           e.m.WORKSPACE_PRIMARY_URL, changed)
                else:
                    stored = await auth._workspace.context.storage.get_tokens()
                    await auth._workspace.context.storage.set_tokens(stored.model_copy(update={"access_token": "inert-replacement"}))
        e.oracle.hook = hook
        try:
            async with client(e, auth) as value:
                with pytest.raises(e.m.WorkspaceOAuthError):
                    await send(e, value)
        finally:
            if home_token is not None:
                e.hc.reset_hermes_home_override(home_token)
        assert all(provider.context.storage._hermes_home == e.home for provider in (auth._primary, auth._workspace))
        assert not any(url == e.m.WORKSPACE_PRIMARY_URL for _, url, _, _ in e.oracle.requests)
    asyncio.run(run())


def test_workspace_rotation_during_primary_consent_is_not_relabelled_verified(engine):
    e = engine
    async def run():
        with e.mo.force_interactive_oauth():
            auth = new_auth(e)
            async def change(resource):
                if resource == e.m.WORKSPACE_PRIMARY_RESOURCE:
                    stored = await auth._workspace.context.storage.get_tokens()
                    await auth._workspace.context.storage.set_tokens(stored.model_copy(update={"access_token": "unverified-new-access"}))
            e.oracle.consent_hook = change
            async with client(e, auth) as value:
                with pytest.raises(e.m.WorkspaceOAuthError):
                    await send(e, value)
        assert not auth.verified()
        assert not any(url == e.m.WORKSPACE_PRIMARY_URL and "authorization" in headers
                       for _, url, headers, _ in e.oracle.requests)
        assert all(provider.context.lock.value == 1 for provider in (auth._primary, auth._workspace))
    asyncio.run(run())


def test_cancelled_second_consent_has_no_overall_authentication(engine):
    e = engine
    async def run():
        reached = asyncio.Event()
        async def hold(resource):
            if resource == e.m.WORKSPACE_PRIMARY_RESOURCE:
                reached.set()
                await asyncio.Event().wait()
        e.oracle.consent_hook = hold
        with e.mo.force_interactive_oauth():
            auth = new_auth(e)
            async with client(e, auth) as value:
                task = asyncio.create_task(send(e, value))
                await asyncio.wait_for(reached.wait(), 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        assert not auth.verified()
        assert auth._workspace.context.storage.has_cached_tokens()
        assert not auth._primary.context.storage.has_cached_tokens()
        assert all(provider.context.lock.value == 1 and provider._hermes_fence is None
                   for provider in (auth._primary, auth._workspace))
    asyncio.run(run())


@pytest.mark.parametrize("bad", ["resource_parent", "challenge_scope_expansion", "prm_scope_expansion", "redirect", "error_body"])
def test_unapproved_discovery_and_token_failures_are_closed(engine, bad):
    e = engine
    async def run():
        async def hook(request):
            if bad in {"challenge_scope_expansion", "prm_scope_expansion"} and str(request.url) == e.m.WORKSPACE_IDENTITY_URL:
                challenge = 'Bearer resource_metadata="' + e.oracle.metadata_url(e.m.WORKSPACE_RESOURCE) + '"'
                if bad == "challenge_scope_expansion":
                    challenge += ', scope="mastermind.workspace.read mastermind.workspace.write"'
                return httpx2.Response(401, headers={"WWW-Authenticate": challenge})
            if bad in {"resource_parent", "prm_scope_expansion"} and str(request.url) == e.oracle.metadata_url(e.m.WORKSPACE_RESOURCE):
                return httpx2.Response(200, json=dict(
                    resource="https://mcp.mastermind-x.com/workspace" if bad == "resource_parent" else e.m.WORKSPACE_RESOURCE,
                    authorization_servers=[ISSUER], scopes_supported=["mastermind.workspace.write"]
                        if bad == "prm_scope_expansion" else [e.m.WORKSPACE_SCOPE]))
            if str(request.url) == ISSUER + "/token":
                if bad == "redirect":
                    return httpx2.Response(307, headers={"location": "https://foreign.example/capture"})
                if bad == "error_body":
                    return httpx2.Response(400, text="echo inert-sensitive-server-body")
        e.oracle.hook = hook
        with e.mo.force_interactive_oauth():
            auth = new_auth(e)
            async with client(e, auth) as value:
                with pytest.raises(e.m.WorkspaceOAuthError, match="^WORKSPACE_OAUTH_UNAVAILABLE$"):
                    await send(e, value)
        assert not auth.verified()
        assert not any("foreign.example" in url for _, url, _, _ in e.oracle.requests)
        if "scope_expansion" in bad:
            assert e.oracle.consents == [] and e.oracle.codes == {} and e.oracle.tokens == {}
            assert not any(url == ISSUER + "/token" for _, url, _, _ in e.oracle.requests)
    asyncio.run(run())


def selected_source(e, path, names, values):
    """Execute named complete donor definitions; other UI/runtime edges explicit."""
    data = (e.vendor / path).read_bytes()
    tree = ast.parse(data, filename=str(e.vendor / path))
    body = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name in names]
    assert {node.name for node in body} == set(names)
    tree = ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module="__future__",
        names=[ast.alias(name="annotations")], level=0), *body], type_ignores=[]))
    namespace = dict(values)
    exec(compile(tree, str(e.vendor / path), "exec"), namespace)
    return namespace


def test_original_auth_park_observes_both_existing_credential_stamps(engine):
    e = engine
    auth = asyncio.run(authorize(e))
    tree = ast.parse((e.vendor / "tools/mcp_tool_server_run.py").read_bytes())
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_arm_auth_park")
    namespace = {"_errors": e.errors}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), "original-auth-park", "exec"), namespace)
    owner = SimpleNamespace(_auth_type="oauth", name=e.m.WORKSPACE_PRIMARY_SERVER,
        _config={"url": e.m.WORKSPACE_PRIMARY_URL, "oauth": e.oauth})
    namespace["_arm_auth_park"](owner, e.m.WorkspaceOAuthError())
    reader, initial = owner._auth_park
    assert reader.credential_stamp() == initial
    for provider in (auth._primary, auth._workspace):
        async def rotate():
            stored = await provider.context.storage.get_tokens()
            await provider.context.storage.set_tokens(stored.model_copy(update={"expires_in": 12}))
        before = reader.credential_stamp()
        asyncio.run(rotate())
        assert reader.credential_stamp() != before
    assert e.errors._is_auth_error(e.m.WorkspaceOAuthError())


@pytest.mark.parametrize("partial", [False, True, "cache_only"])
def test_original_explicit_login_requires_both_real_resource_flows(engine, partial):
    e = engine
    messages = []
    def probe(name, config, *, connect_timeout, details):
        assert connect_timeout > e.mo.login_connect_timeout(config)
        if partial == "cache_only":
            details["workspace_oauth_verified"] = False
            return [("inert", "no authenticated probe")]
        async def run():
            auth = e.m.get_manager().get_workspace_provider(name, config["url"], config["oauth"])
            async with client(e, auth) as value:
                await send(e, value)
            details["workspace_oauth_verified"] = auth.verified()
        asyncio.run(run())
        return [("inert", "controlled MCP probe")]
    if partial is True:
        async def reject(request):
            if str(request.url) == ISSUER + "/token" and parse_qs(request.content.decode())["resource"] == [e.m.WORKSPACE_PRIMARY_RESOURCE]:
                return httpx2.Response(400, text="inert-secret-body")
        e.oracle.hook = reject
    namespace = selected_source(e, "hermes_cli/mcp_config.py", {"_reauth_oauth_server", "_oauth_tokens_present"},
        dict(asyncio=asyncio, get_hermes_home=e.hc.get_hermes_home,
            _error=messages.append, _warning=messages.append, _info=messages.append, _success=messages.append,
            _probe_single_server=probe, redact_mcp_probe_text=lambda _: "redacted fixture error"))
    result = namespace["_reauth_oauth_server"](e.m.WORKSPACE_PRIMARY_SERVER,
        dict(url=e.m.WORKSPACE_PRIMARY_URL, auth="oauth", oauth=e.oauth))
    assert result is (partial is False)
    if partial:
        assert "WORKSPACE_OAUTH_UNAVAILABLE" in messages
        assert not any("Authenticated" in message for message in messages)


def test_existing_cli_header_redactor_masks_complete_companion_fields(engine):
    e = engine
    path = e.vendor / "hermes_cli/mcp_config.py"
    tree = ast.parse(path.read_bytes())
    names = {"_credential_header_names", "_probe_redaction_res", "_mask_header_field_value", "redact_mcp_probe_text",
             "_sub_mapping_header", "_sub_unquoted_mapping_header", "_sub_wire_header", "_sub_bare_scheme"}
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            keep.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id in {"_AUTH_SCHEME_PREFIX_RE", "_DIGEST_PARAM_NAMES",
                "_DIGEST_PARAM", "_DIGEST_PARAMS", "_PROBE_REDACTION_RES"} for target in targets):
                keep.append(node)
    import re
    namespace = {"re": re, "Optional": __import__("typing").Optional}
    exec(compile(ast.fix_missing_locations(ast.Module(body=keep, type_ignores=[])), str(path), "exec"), namespace)
    secret = "inertCompanionValueStart" + "x" * 32 + "ValueEnd"
    for value in ("x-mastermind-workspace-authorization: Bearer " + secret,
                  json.dumps({"X-Mastermind-Workspace-Authorization": "Bearer " + secret}),
                  repr({"x-mastermind-workspace-authorization": "Bearer " + secret})):
        result = namespace["redact_mcp_probe_text"](value)
        assert secret not in result and secret[:6] not in result and secret[-4:] not in result


@pytest.mark.parametrize("endpoint", [ISSUER + "/authorize?scope=mastermind.workspace.write",
    ISSUER + "/authorize#scope=mastermind.workspace.write", "https://user:pass@issuer.example/authorize",
    "http://issuer.example/authorize"])
def test_actual_consent_endpoint_must_have_only_sdk_operands(engine, endpoint):
    e = engine
    e.oracle.authorization_endpoint = endpoint
    async def run():
        with e.mo.force_interactive_oauth():
            auth = new_auth(e)
            async with client(e, auth) as value:
                with pytest.raises(e.m.WorkspaceOAuthError):
                    await send(e, value)
        assert e.oracle.consents == [] and e.oracle.tokens == {}
        assert not any(url == ISSUER + "/token" for _, url, _, _ in e.oracle.requests)
    asyncio.run(run())


@pytest.mark.parametrize("stage", ["exchange", "refresh", "cache"])
@pytest.mark.parametrize("scope", ["mastermind.workspace.read mastermind.workspace.write", None])
def test_explicit_grant_scope_is_required_before_fixed_token_persistence_or_use(engine, stage, scope):
    e = engine
    async def run():
        auth = None
        if stage != "exchange":
            auth = await authorize(e)
        if stage == "cache":
            tokens = await auth._workspace.context.storage.get_tokens()
            await auth._workspace.context.storage.set_tokens(tokens.model_copy(update={"scope": scope}))
            e.m.reset_manager_for_tests()
        elif stage == "refresh":
            stored = await auth._workspace.context.storage.get_tokens()
            await auth._workspace.context.storage.set_tokens(stored.model_copy(update={"expires_in": 0}))
            auth._workspace.context.token_expiry_time = time.time() - 1
            e.oracle.token_scope = scope
        else:
            e.oracle.token_scope = scope
        e.oracle.requests.clear()
        with e.mo.force_interactive_oauth():
            selected = new_auth(e)
            async with client(e, selected) as value:
                if stage == "refresh" and scope is None:
                    # Original RFC refresh behavior preserves the explicit
                    # prior scope; no invented grant or new storage behavior.
                    response = await send(e, value)
                    assert response.status_code == 200 and selected.verified()
                else:
                    with pytest.raises(e.m.WorkspaceOAuthError):
                        await send(e, value)
                    assert not selected.verified()
                    assert not any(url == e.m.WORKSPACE_IDENTITY_URL and "authorization" in headers
                                   for _, url, headers, _ in e.oracle.requests)
                    if stage == "exchange":
                        assert not selected._workspace.context.storage.has_cached_tokens()
                    elif stage == "refresh":
                        stored = await selected._workspace.context.storage.get_tokens()
                        assert stored.scope == e.m.WORKSPACE_SCOPE
    asyncio.run(run())


def transport_owner(e, monkeypatch):
    """Actual donor transport methods and real SDK; only IO/lifecycle edges.

    The existing live-endpoint lookup, proxy selection, connection-identity
    digest and serving-loop owner are explicit fixture edges. HTTP socket IO
    becomes MockTransport. The original owned client, body cap, redirect hook,
    auth generator, Streamable HTTP, JSON-RPC and ClientSession all execute.
    """
    import logging
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    calls = []
    def io_transport(**kwargs):
        calls.append(kwargs)
        assert kwargs == {"verify": True}
        return httpx2.MockTransport(e.oracle)
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", io_transport)
    monkeypatch.setattr(e.core, "streamable_http_client", streamable_http_client, raising=False)
    values = dict(asyncio=asyncio, asynccontextmanager=asynccontextmanager,
        logger=logging.getLogger("fixture-hermes-transport"), _core=e.core,
        _registration=SimpleNamespace(_identity_digest=lambda _: "explicit-fixture-connection-identity"),
        _live_endpoint=lambda _: None, _mcp_proxy_mounts=lambda *_a, **_k: None)
    for name in ("_apply_identity_header", "_make_redirect_header_stripper", "_make_http_rejection_recorder",
                 "_make_mcp_body_cap_transport", "_MCP_HTTP_MAX_BODY_BYTES", "_resolve_client_cert"):
        values[name] = getattr(e.errors, name)
    namespace = selected_source(e, "tools/mcp_tool_transport.py",
        {"_present", "_http_endpoint", "_connect_inputs", "MCPServerTransportMixin"}, values)
    class Owner(namespace["MCPServerTransportMixin"]):
        def __init__(self):
            self.name = e.m.WORKSPACE_PRIMARY_SERVER
            self._auth_type, self._sse_fallback, self._ever_connected = "oauth", False, False
        async def _serve_transport(self, transport, label, timeout):
            assert label == "HTTP" and timeout == 5
            async with transport as streams:
                async with ClientSession(streams[0], streams[1], read_timeout_seconds=5) as session:
                    initialized = await session.initialize()
                    listed = await session.list_tools()
                    result = await session.call_tool(e.oracle.rpc_tool, arguments=getattr(e, "rpc_arguments", {}))
                    if hasattr(e, "after_rpc"):
                        e.after_rpc(self, session, initialized, listed, result)
                    return initialized, listed, result
    owner = Owner()
    config = dict(url=e.m.WORKSPACE_PRIMARY_URL, auth="oauth", oauth=deepcopy(e.oauth),
                  transport="streamable-http", strict_redirect_headers=True, connect_timeout=5)
    return owner, config, calls


def test_real_donor_transport_runs_sdk_initialize_discovery_and_call_on_one_owned_client(engine, monkeypatch):
    e = engine
    e.oracle.rpc = True
    owner, config, constructions = transport_owner(e, monkeypatch)
    async def run():
        with e.mo.force_interactive_oauth():
            initialized, listed, result = await owner._run_http(config)
        assert initialized.server_info.name == "inert-protected-coo"
        assert [tool.name for tool in listed.tools] == ["fixture_read"]
        assert result.content[0].text == "inert-current-context-response" and not result.is_error
        assert owner._workspace_oauth.verified()
        assert constructions == [{"verify": True}]
        assert owner._http_rejection.get("body", "") == ""
        assert all(e.m.WORKSPACE_HEADER not in headers for _, url, headers, _ in e.oracle.requests
                   if url != e.m.WORKSPACE_PRIMARY_URL)
    asyncio.run(run())


@pytest.mark.parametrize("bad", ["sse", "latched_sse", "legacy_client", "unowned_client", "no_strict",
    "tls_off", "static_header", "endpoint_file", "identity_header", "client_cert", "no_oauth"])
def test_fixed_transport_refuses_alternate_credential_or_transport_before_client_io(engine, monkeypatch, bad):
    e = engine
    owner, config, constructions = transport_owner(e, monkeypatch)
    if bad == "sse": config["transport"] = "sse"
    elif bad == "latched_sse": owner._sse_fallback = True
    elif bad == "legacy_client": e.core._MCP_NEW_HTTP = False
    elif bad == "unowned_client": monkeypatch.setattr(e.core, "sdk_httpx", lambda: SimpleNamespace(__name__="httpx"))
    elif bad == "no_strict": config["strict_redirect_headers"] = False
    elif bad == "tls_off": config["ssl_verify"] = False
    elif bad == "static_header": config["headers"] = {"Authorization": "inert-forbidden"}
    elif bad == "endpoint_file": config["server_json"] = "/inert/alternate.json"
    elif bad == "identity_header": config["identity_header"] = {"name": "X-Identity", "value": "inert"}
    elif bad == "client_cert": config["client_cert"] = "/inert/cert.pem"
    elif bad == "no_oauth": owner._auth_type = config["auth"] = "none"
    async def run():
        with e.mo.force_interactive_oauth(), pytest.raises(e.m.WorkspaceOAuthError):
            await owner._run_http(config)
    asyncio.run(run())
    assert constructions == [] and e.oracle.requests == [] and e.oracle.consents == []


def test_legacy_single_resource_provider_keeps_original_scope_and_refresh_behavior(engine):
    e = engine
    e.oracle.require_timeout = False  # The new bounded timeout belongs only to the fixed adapter.
    e.oracle.token_scope = e.m.WORKSPACE_SCOPE + " mastermind.workspace.write"
    async def run():
        with e.mo.force_interactive_oauth():
            provider = e.m.get_manager().get_or_build_provider("ordinary-server", e.m.WORKSPACE_RESOURCE,
                {"client_id": CLIENT, "scope": e.m.WORKSPACE_SCOPE})
            assert not getattr(provider, "_hermes_workspace_single_client", False)
            async with httpx2.AsyncClient(auth=provider, transport=httpx2.MockTransport(e.oracle), timeout=5) as value:
                response = await value.get(e.m.WORKSPACE_IDENTITY_URL, headers={"MCP-Protocol-Version": PROTOCOL})
                assert response.status_code == 200 and provider.context.current_tokens.scope == e.oracle.token_scope
                provider.context.token_expiry_time = time.time() - 1
                response = await value.get(e.m.WORKSPACE_IDENTITY_URL, headers={"MCP-Protocol-Version": PROTOCOL})
                assert response.status_code == 200
        assert provider._hermes_fence is None and provider.context.lock.value == 1
        assert e.oracle.generation == 2 and len(e.oracle.consents) == 1
        assert all(e.m.WORKSPACE_HEADER not in headers for _, _, headers, _ in e.oracle.requests)
    asyncio.run(run())


def current_receiver_fixture():
    data = (ROOT / "current-context-fixture.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == "222570f3427d876404338d6859a2581792d64cb1d2d6137456bab0f9914ea130"
    value = json.loads(data)
    assert value["receiver_mcp"] == "1.28.1"
    assert value["schema"] == "mastermind.hermes_current_context_sdk_fixture.v1"
    return value


def test_real_sdk23_delivers_recorded_signed_receiver_bytes_through_native_decoder_and_capture(engine, monkeypatch):
    from common import coo_agentos_context_contract as wire
    from integrations.executive_mcp.coo import COO_CURRENT_CONTEXT_TOOL_SPECS
    from integrations.hermes_harness import native_executive_consumer as consumer
    from integrations.hermes_harness.native_agentos_context import decode_context_result
    from integrations.hermes_harness.native_mcp import render_consumer_mcp_server
    import threading
    e = engine
    recorded = current_receiver_fixture()
    publication = consumer.publication_from_document(recorded["publication"])
    e.oauth = render_consumer_mcp_server(publication)["oauth"]
    e.oracle.principal_scope = e.oauth["workspace"]["principal_scope"]
    e.oracle.rpc, e.oracle.rpc_tool = True, wire.CURRENT_TOOL
    e.oracle.rpc_tools = [{"name": spec.name, "inputSchema": deepcopy(spec.input_schema),
                           "annotations": deepcopy(spec.annotations)} for spec in COO_CURRENT_CONTEXT_TOOL_SPECS]
    e.oracle.server_info = {"name": publication.mcp.server_name, "version": publication.mcp.server_version}
    e.oracle.rpc_text = recorded["sdk_result"]["content"][0]["text"]
    e.rpc_arguments = {"work_ref": publication.work_ref}
    owner, config, constructions = transport_owner(e, monkeypatch)
    calls = []
    def consume(serving, session, initialized, listed, result):
        raw, receipt = decode_context_result(result, publication)
        assert hashlib.sha256(raw).hexdigest() == recorded["bundle_sha256"]
        assert receipt["source_mode"] == "CANONICAL_PROJECT_DATA"
        assert receipt["compiler_code_commit"] != receipt["data_commit"]
        serving.session, serving.initialize_result = session, initialized
        serving._tools, serving._config = listed.tools, config
        monkeypatch.setattr(e.core, "_lock", threading.RLock(), raising=False)
        monkeypatch.setattr(e.core, "_servers", {"fixture::coo": serving}, raising=False)
        edge(monkeypatch, "tools.mcp_tool_loop", _running_loop=asyncio.get_running_loop)
        edge(monkeypatch, "tools.mcp_tool_scope", _resolve_server_key=lambda _: "fixture::coo")
        captured = consumer.capture_native_mcp_owner(publication, include_guard=True)
        assert captured[:3] == (serving, session, asyncio.get_running_loop())
        assert captured[3]() is True
        serving._config = {**config, "oauth": {**config["oauth"], "workspace": {}}}
        assert captured[3]() is False
        serving._config = config
        calls.append(receipt["bundle_sha256"])
    e.after_rpc = consume
    async def run():
        with e.mo.force_interactive_oauth():
            await owner._run_http(config)
    asyncio.run(run())
    assert calls == [recorded["bundle_sha256"]] and constructions == [{"verify": True}]


def test_sdk23_errors_partial_results_and_conflicting_content_cannot_become_native_context():
    from mcp import types
    from integrations.hermes_harness import native_executive_consumer as consumer
    from integrations.hermes_harness.native_agentos_context import decode_context_result
    from integrations.hermes_runtime.errors import RuntimeRefusal
    recorded = current_receiver_fixture()
    publication = consumer.publication_from_document(recorded["publication"])
    good = types.CallToolResult.model_validate(recorded["sdk_result"])
    assert decode_context_result(good, publication)[1]["bundle_sha256"] == recorded["bundle_sha256"]
    changes = [{"is_error": True}, {"result_type": "input_required"}, {"result_type": "unknown"},
               {"structured_content": {}}, {"meta": {}}, {"content": good.content * 2}]
    for change in changes:
        with pytest.raises(RuntimeRefusal):
            decode_context_result(good.model_copy(update=change), publication)
    for result in (good.model_copy(update={"is_error": True}), good.model_copy(update={"result_type": "input_required"})):
        assert consumer._native_result_body(result) is None
    assert consumer._native_result_body(good) == json.loads(good.content[0].text)
