"""Real MCP SDK/HTTP tests; browser effects are explicit fixture owners."""
import asyncio
from contextlib import AsyncExitStack
from dataclasses import replace
import json
import hashlib
from pathlib import Path
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_browser_link.tool_contract import (
    LINK_TOOL_SCHEMA_DIGEST, INVENTORY_TOOL, OWNER_INVENTORY_SCHEMA, tool_catalog)
from integrations.mastermind_browser_plugin.catalog import SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.inventory_owner import ActiveBrowserResource
from integrations.mastermind_browser_plugin.link_inventory import LINK_ACTIONS
from integrations.mastermind_browser_plugin.owner_adapter import BrowserCallerBinding
from integrations.mastermind_browser_plugin.workbench_client import WorkbenchBrowserClientError, WorkbenchBrowserMcpEffectPort
from integrations.mastermind_browser_plugin.workbench_transport import WorkbenchHostRoute, WorkbenchHostTransport, parse_host_routes
from integrations.workbench_browser_mcp.app import create_authenticated_browser_server
from integrations.workbench_browser_mcp.resource_observation import ResourceObservation


class Keys:
    def __init__(self, jwk):
        self.jwk = jwk
    async def key_for(self, kid):
        if kid != "fixture":
            raise ValueError("unknown fixture")
        return self.jwk


class Audit:
    def emit(self, event):
        pass


class Host:
    def __init__(self, name):
        self.name = name
        self.now = int(time.time())
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.issuer = "https://identity." + name + ".test"
        self.resource = "https://" + name + ".test/browser"
        self.subject = subject_digest(issuer=self.issuer, subject="broker")
        self.client_id = "broker-" + name
        client_ref = hashlib.sha256((self.issuer + "\nclient\n" + self.client_id).encode()).hexdigest()
        self.broker = BrowserCallerBinding(self.subject, client_ref, self.resource)
        self.policy = load_resource_policy({
            "schema": "mastermind.business_mcp_auth_policy.v1",
            "policy_id": "fixture." + name, "resource": self.resource,
            "resource_metadata_url": "https://" + name + ".test/.well-known/oauth-protected-resource/browser",
            "issuer": self.issuer, "authorization_servers": [self.issuer],
            "jwks_uri": self.issuer + "/jwks", "required_scopes": ["workbench.action"],
            "allowed_subject_digests": [self.subject], "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 0, "max_token_lifetime_seconds": 3600,
            "jwks_cache_ttl_seconds": 60, "unknown_kid_refresh_cooldown_seconds": 1,
            "fetch_failure_backoff_seconds": 1})
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update(kid="fixture", alg="RS256", use="sig")
        self.auth = JwtAuthenticator(policy=self.policy, jwks_cache=Keys(jwk))
        self.token = jwt.encode({
            "iss": self.issuer, "sub": "broker", "aud": self.resource,
            "iat": self.now - 1, "exp": self.now + 600, "scope": "workbench.action",
            "client_id": self.client_id}, self.key, algorithm="RS256", headers={"kid": "fixture"})
        self.row = ActiveBrowserResource(
            backend="shared_human", browser_ref="inner-" + name + "-" + "b" * 64,
            host_ref=name, boot_ref="boot-" + name, profile_ref="profile-" + name,
            browser_instance_ref="a" * 64, connection_generation="generation-" + name,
            consent_ref="profile-consent", allowed_actions=LINK_ACTIONS,
            catalog_schema_digest=SCHEMA_DIGEST, backend_schema_digest=LINK_TOOL_SCHEMA_DIGEST,
            expires_at_ms=(self.now + 300) * 1000)
        self.calls, self.http_calls, self.applied = [], [], set()
        self.extra_rows = ()
        self.stall = None
        self.open_wires = 0
        self.started, self.cancelled = asyncio.Event(), asyncio.Event()
        self.server = create_authenticated_browser_server(
            authenticator=self.auth, policy=self.policy, now=lambda: self.now, audit_sink=Audit(),
            tool_catalog=tool_catalog(), expected_tool_schema_digest=LINK_TOOL_SCHEMA_DIGEST,
            prepare_resource=self.unexpected, start_resource=self.unexpected, reconcile_resource=self.unexpected,
            read_tool=self.read, prepare_action=self.prepare, run_action=self.run, reconcile_action=self.reconcile,
            observe_resources=self.observe, allowed_hosts=(name + ".test",))
        self.app = self.server.streamable_http_app()
        self.route = WorkbenchHostRoute(
            host_ref=name, mcp_url="https://" + name + ".test/mcp", resource=self.resource,
            broker_subject_digest=self.subject, broker_client_ref=self.broker.client_ref,
            backend_schema_digest=LINK_TOOL_SCHEMA_DIGEST, credential_file=Path("/fixture/credential"),
            timeout_seconds=2, max_concurrency=2)

    async def unexpected(self, *args):
        raise AssertionError("resource allocation is not an estate operation")

    def checked(self, caller):
        assert BrowserCallerBinding(caller.subject_digest, caller.client_ref, caller.resource) == self.broker

    async def observe(self, caller, request):
        self.checked(caller)
        self.calls.append(("observe", dict(request)))
        rows = sorted((self.row, *self.extra_rows), key=lambda row: (row.profile_ref, row.browser_instance_ref, row.browser_ref))
        if "browser_ref" in request:
            rows = [row for row in rows if row.browser_ref == request["browser_ref"]]
        if "after" in request:
            after = request["after"]
            rows = [row for row in rows if (row.profile_ref, row.browser_instance_ref, row.browser_ref)
                    > (after["profile_ref"], after["browser_instance_ref"], after["browser_ref"])]
        limit = request.get("limit", 1)
        return ResourceObservation(self.broker, self.name, self.row.boot_ref, self.now * 1000,
                                   tuple(rows[:limit]), "complete", len(rows) > limit).document()

    async def read(self, caller, browser_ref, tool, arguments):
        self.checked(caller)
        self.calls.append(("read", browser_ref, tool, dict(arguments)))
        if tool == INVENTORY_TOOL:
            return {"content": [], "isError": False, "structuredContent": {
                "schema": OWNER_INVENTORY_SCHEMA, "instance_id": self.row.browser_instance_ref,
                "connection_generation": self.row.connection_generation,
                "shared_tabs": [{"tab_id": 7, "origin": "https://example.test", "consent_id": "consent-7",
                                 "document_revision": 0, "state": "shared", "allow_create": True}]}}
        return {"content": [{"type": "text", "text": self.name}], "isError": False}

    async def prepare(self, caller, browser_ref, tool, arguments):
        self.checked(caller)
        self.calls.append(("prepare", browser_ref, tool, dict(arguments)))
        return "prepared-" + "a" * 48

    async def run(self, caller, browser_ref, action_ref):
        self.checked(caller)
        self.calls.append(("run", browser_ref, action_ref))
        self.applied.add((browser_ref, action_ref))
        if action_ref == self.stall:
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()
        return {"status": "OK", "effect_state": "APPLIED", "reconciled": False,
                "result": {"content": [{"type": "text", "text": "created-tab-9"}], "isError": False}}

    async def reconcile(self, caller, browser_ref, action_ref):
        self.checked(caller)
        self.calls.append(("reconcile", browser_ref, action_ref))
        return {"status": "OK", "effect_state": "APPLIED" if (browser_ref, action_ref) in self.applied else "NOT_APPLIED",
                "reconciled": True}

    def transport(self, fault=None, **changes):
        host = self
        class Wire(httpx.AsyncBaseTransport):
            def __init__(self):
                self.inner = httpx.ASGITransport(app=host.app)
                host.open_wires += 1
            async def handle_async_request(self, request):
                if fault == "offline":
                    raise httpx.ConnectError("fixture offline", request=request)
                payload = json.loads(await request.aread()) if request.method == "POST" else {}
                method, name = payload.get("method"), payload.get("params", {}).get("name")
                host.http_calls.append((method, name))
                is_run = method == "tools/call" and name == "run_browser_action"
                if is_run and fault in {404, 307, 308}:
                    return httpx.Response(fault, headers={"Location": "https://other.test/mcp"}, request=request)
                response = await self.inner.handle_async_request(request)
                if is_run and fault == "lost":
                    await response.aclose()
                    raise httpx.ReadError("fixture lost response", request=request)
                if method == "tools/list" and fault == "catalog":
                    raw = json.loads(await response.aread())
                    raw["result"]["tools"][0]["inputSchema"]["additionalProperties"] = True
                    await response.aclose()
                    return httpx.Response(200, json=raw, request=request)
                if method == "initialize" and fault == "stateful":
                    response.headers["mcp-session-id"] = "unexpected"
                return response
            async def aclose(self):
                await self.inner.aclose()
                host.open_wires -= 1
        return WorkbenchHostTransport(
            route=replace(self.route, **changes), now=lambda: self.now,
            http_transport_factory=Wire, credential_reader=lambda route, now: self.token)

    def port(self, transport):
        return WorkbenchBrowserMcpEffectPort(call_tool=transport.call_tool,
                                             expected_backend_schema_digest=LINK_TOOL_SCHEMA_DIGEST)


def test_sdk_two_independent_owners_and_authenticated_broker_observation():
    async def exercise():
        first, second = Host("host-one"), Host("host-two")
        async with AsyncExitStack() as stack:
            for host in (first, second):
                await stack.enter_async_context(host.app.router.lifespan_context(host.app))
            transports = [first.transport(), second.transport()]
            for item in transports:
                await stack.enter_async_context(item.opened())
            rows = await asyncio.gather(first.port(transports[0]).observe_resources({"limit": 10}),
                                        second.port(transports[1]).observe_resources({"limit": 10}))
            assert [row.host_ref for row in rows] == ["host-one", "host-two"]
            assert rows[0].broker != rows[1].broker
            assert all(len(host.calls) == 1 for host in (first, second))
    asyncio.run(exercise())


@pytest.mark.parametrize("fault", ["lost", 404, 307, 308])
def test_lost_or_refused_action_response_never_replays_and_reconciles_original(fault):
    async def exercise():
        host = Host("host-one")
        action = "action-" + "x" * 48
        async with host.app.router.lifespan_context(host.app):
            transport = host.transport(fault)
            async with transport.opened():
                port = host.port(transport)
                with pytest.raises(WorkbenchBrowserClientError):
                    await port.run_action(None, host.row.browser_ref, action)
                result = await port.reconcile_action(None, host.row.browser_ref, action)
                assert result["effect_state"] == ("APPLIED" if fault == "lost" else "NOT_APPLIED")
        assert host.http_calls.count(("tools/call", "run_browser_action")) == 1
        assert [row for row in host.calls if row[0] == "reconcile"] == [
            ("reconcile", host.row.browser_ref, action)]
        assert len([row for row in host.calls if row[0] == "run"]) == (1 if fault == "lost" else 0)
    asyncio.run(exercise())


def test_timeout_does_not_cancel_concurrent_same_host_action_and_releases_permit():
    async def exercise():
        host = Host("host-one")
        host.stall = "stalled-" + "s" * 48
        async with host.app.router.lifespan_context(host.app):
            transport = host.transport(timeout_seconds=1)
            async with transport.opened():
                port = host.port(transport)
                first = asyncio.create_task(port.run_action(None, host.row.browser_ref, host.stall))
                await asyncio.wait_for(host.started.wait(), 0.8)
                other = await port.run_action(None, host.row.browser_ref, "other-" + "o" * 48)
                assert other["effect_state"] == "APPLIED"
                assert other["result"]["content"][0]["text"] == "created-tab-9"
                with pytest.raises(WorkbenchBrowserClientError):
                    await first
                assert host.open_wires == 0
                # Local HTTP cancellation is not evidence that a remote action stopped.
                assert not host.cancelled.is_set()
                assert transport._permits._value == 2
                result = await port.reconcile_action(None, host.row.browser_ref, host.stall)
                assert result["effect_state"] == "APPLIED"
        assert len([row for row in host.calls if row[0] == "run"]) == 2
    asyncio.run(exercise())


@pytest.mark.parametrize("fault", ["catalog", "stateful"])
def test_catalog_and_stateless_contract_qualify_before_effect(fault):
    async def exercise():
        host = Host("host-one")
        async with host.app.router.lifespan_context(host.app):
            transport = host.transport(fault)
            async with transport.opened():
                with pytest.raises(WorkbenchBrowserClientError):
                    await host.port(transport).run_action(None, host.row.browser_ref, "a" * 32)
        assert not any(row[0] == "run" for row in host.calls)
        assert ("tools/call", "run_browser_action") not in host.http_calls
    asyncio.run(exercise())


def test_shutdown_cancels_original_local_call_without_replacement_dispatch():
    async def exercise():
        host = Host("host-one")
        host.stall = "stalled-" + "s" * 48
        async with host.app.router.lifespan_context(host.app):
            transport = host.transport()
            async with transport.opened():
                task = asyncio.create_task(host.port(transport).run_action(None, host.row.browser_ref, host.stall))
                await asyncio.wait_for(host.started.wait(), 1)
            assert task.cancelled()
            assert host.open_wires == 0
            assert not transport._active
        assert host.http_calls.count(("tools/call", "run_browser_action")) == 1
        assert len(host.applied) == 1
    asyncio.run(exercise())


def test_fixed_route_rejects_legacy_resource_tokens_and_duplicate_hosts():
    host = Host("host-one")
    with pytest.raises(ValueError):
        replace(host.route, mcp_url="legacy-token", resource="legacy-token")
    document = {"schema": "mastermind.browser_fabric_routes.v1", "routes": [
        {**host.route.__dict__, "credential_file": str(host.route.credential_file)}]}
    assert parse_host_routes(document) == (host.route,)
    document["routes"] *= 2
    with pytest.raises(ValueError):
        parse_host_routes(document)


def test_original_action_reconciles_after_unrelated_remote_catalog_upgrade():
    async def exercise():
        host = Host("host-one")
        action = "original-" + "a" * 48
        async with host.app.router.lifespan_context(host.app):
            transport = host.transport("lost")
            async with transport.opened():
                with pytest.raises(WorkbenchBrowserClientError):
                    await host.port(transport).run_action(None, host.row.browser_ref, action)
            upgraded = host.transport("catalog")
            async with upgraded.opened():
                result = await host.port(upgraded).reconcile_action(None, host.row.browser_ref, action)
                assert result["effect_state"] == "APPLIED"
        assert host.http_calls.count(("tools/call", "run_browser_action")) == 1
        assert host.http_calls.count(("tools/call", "reconcile_browser_action")) == 1
    asyncio.run(exercise())


def test_credential_reader_requires_owner_only_file_and_current_matching_resource(tmp_path):
    from integrations.mastermind_browser_plugin.workbench_transport import _credential, CREDENTIAL_SCHEMA
    from integrations.workbench_action_mcp.service import ServiceConfigurationError
    host = Host("host-one")
    path = tmp_path / "credential.json"
    route = replace(host.route, credential_file=path)
    document = {"schema": CREDENTIAL_SCHEMA, "resource": host.resource,
                "access_token": "fixture-credential-only", "expires_at": host.now + 60}
    path.write_text(json.dumps(document))
    path.chmod(0o600)
    assert _credential(route, host.now) == "fixture-credential-only"
    path.chmod(0o644)
    with pytest.raises(ServiceConfigurationError):
        _credential(route, host.now)
    path.chmod(0o600)
    with pytest.raises(WorkbenchBrowserClientError):
        _credential(route, host.now + 60)
    document["resource"] = "https://other.test/browser"
    path.write_text(json.dumps(document))
    with pytest.raises(WorkbenchBrowserClientError):
        _credential(route, host.now)


def test_raw_response_stream_is_bounded_before_sdk_json_materialization():
    from integrations.mastermind_browser_plugin.workbench_transport import _BoundedTransport
    from integrations.workbench_browser_mcp.app import MAX_RESULT_BYTES
    async def exercise():
        class Stream(httpx.AsyncByteStream):
            closed = False
            async def __aiter__(self):
                for _ in range(MAX_RESULT_BYTES // 1024 + 1):
                    yield b"x" * 1024
            async def aclose(self):
                self.closed = True
        stream = Stream()
        class Source(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                return httpx.Response(200, headers={"Content-Type": "application/json"},
                                      stream=stream, request=request)
        async with httpx.AsyncClient(transport=_BoundedTransport(Source())) as client:
            with pytest.raises(WorkbenchBrowserClientError, match="REMOTE_RESPONSE_TOO_LARGE"):
                await client.post("https://fixture.test/mcp", json={"id": 1})
        assert stream.closed
    asyncio.run(exercise())
