"""Native five-tool transport, real A1 and temporary CeoIngress/Runtime.

No installed socket, provider, credential, or production service is used.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import dataclasses
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
finally:
    sys.path.pop(0)

from integrations.executive_mcp import server as transport
from integrations.mastermind_executive_app.app import create_app

rsa_key = fixture.rsa_key
short_socket_root = fixture.short_socket_root

PAYLOAD = {
    "operation_key": "mcp-app-canary-001",
    "objective": "Read the Q3 board packet and summarize open risks.",
    "department": "executive-infrastructure",
    "priority": 5,
    "execution_profile": "research_only",
}


class Sink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


@pytest.fixture
def settings(rsa_key, tmp_path, short_socket_root):
    mastermind = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    fixture._git_repo(mastermind)
    (macro / "scripts").mkdir(parents=True)
    (macro / "scripts" / "agentos.py").write_text("")
    (macro / "agentos").mkdir()
    # The installed reader binds the complete filesystem path set to HEAD. Keep
    # the fixture's Agent OS directory represented in Git instead of leaving an
    # untracked empty directory that production correctly refuses.
    (macro / "agentos" / ".keep").write_text("")
    fixture._git_repo(macro)
    return fixture._real_app_settings(
        rsa_key, mastermind_root=mastermind, macro_root=macro,
        ceo_ingress_socket_path=short_socket_root / "ceo-ingress.sock",
    )


@asynccontextmanager
async def connection(settings, *, sink=None):
    # Missing composition is an assertion failure, not an import/collection error.
    build = getattr(transport, "build_executive_mcp_app", None)
    assert callable(build), "the five-tool App/CeoIngress MCP composition is missing"
    app = build(settings, audit_sink=sink or Sink())
    async with app._app.router.lifespan_context(app._app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            yield client


def headers(token):
    return {
        "authorization": f"Bearer {token}",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18",
    }


async def rpc(client, token, method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        request["params"] = params
    response = await client.post("/mcp", headers=headers(token), json=request)
    assert response.status_code == 200, response.text
    assert "error" not in response.json(), response.text
    return response.json()["result"]


async def call(client, token, name, arguments):
    result = await rpc(client, token, "tools/call", {"name": name, "arguments": arguments})
    return result, json.loads(result["content"][0]["text"])


def test_native_scan_and_read_accept_both_existing_exact_policies(settings, rsa_key):
    """A normal OAuth scope upgrade must not break reads or hide submission."""
    async def exercise():
        async with connection(settings) as client:
            for token in (fixture._read_token(rsa_key), fixture._submit_token(rsa_key)):
                initialized = await rpc(client, token, "initialize", {
                    "protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "executive-test", "version": "1"},
                })
                assert "tools" in initialized["capabilities"]
                listed = await rpc(client, token, "tools/list")
                assert {t["name"] for t in listed["tools"]} == {
                    "executive_state", "executive_inbox", "executive_job",
                    "ceo_intent_status", "submit_ceo_intent",
                }
                _, body = await call(client, token, "executive_state", {})
                assert body["ok"] is True, body
                assert body["schema"] == "mastermind.executive_mcp_result.v1"
                assert body["tool"] == "executive_state"
    asyncio.run(exercise())


def test_native_default_jwks_generation_is_shared_across_outer_and_inner_auth(
    settings, rsa_key, monkeypatch
):
    """One OAuth authority gets one bounded key generation per MCP process."""

    from integrations.mastermind_executive_app import gateway as gateway_module

    created = []

    def fake_default(_policy):
        cache = fixture._FakeJwksCache(rsa_key)
        created.append(cache)
        return cache

    monkeypatch.setattr(gateway_module, "_default_jwks_cache", fake_default)
    default_settings = dataclasses.replace(settings, jwks_cache=None)
    app = transport.build_executive_mcp_app(default_settings, audit_sink=Sink())

    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
            ) as client:
                token = fixture._submit_token(rsa_key)
                initialized = await rpc(client, token, "initialize", {
                    "protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "executive-test", "version": "1"},
                })
                assert "tools" in initialized["capabilities"]
                _, body = await call(client, token, "executive_state", {})
                assert body["ok"] is True, body

    asyncio.run(exercise())

    # Outer MCP auth and the inner direct-App auth both received this exact cache.
    # The submit-capable token crosses read->submit fallback in both layers, so a
    # second factory call would prove the duplicated refresh plane still exists.
    assert len(created) == 1
    assert created[0].calls == [fixture.KID] * 6

def test_read_token_gets_submit_scope_challenge_before_socket_effect(settings, rsa_key):
    async def exercise():
        async with connection(settings) as client:
            result, body = await call(client, fixture._read_token(rsa_key), "submit_ceo_intent", PAYLOAD)
            assert result["isError"] is True
            assert body["error"]["code"] == "scope_refused"
            challenge = result["_meta"]["mcp/www_authenticate"][0]
            assert "mastermind.executive.intent.submit" in challenge
            assert "resource_metadata=" in challenge
            assert not Path(settings.ceo_ingress_socket_path).exists()
    asyncio.run(exercise())


@pytest.mark.parametrize("installed", [False, True])
def test_real_mcp_admission_duplicate_conflict_and_same_request_status(
    settings, rsa_key, tmp_path, short_socket_root, installed
):
    """The transport must preserve one real Job and the existing status path."""
    async def exercise():
        service = fixture._real_service(
            tmp_path, socket_root=short_socket_root,
            mastermind_root=Path(settings.mastermind_root), macro_root=Path(settings.macro_root_flag),
        )
        if installed:
            import os
            from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
            from integrations.executive_mcp.installed import InstalledExecutiveReaders
            readers = InstalledExecutiveReaders(
                repo_root=Path(settings.mastermind_root), macro_root=Path(settings.macro_root_flag),
                runtime_root=service.config.runtime_root,
            )
            service = ExecutiveControlService(
                service.config, supervisor_factory=lambda runtime: fixture._NoExecutionSupervisor(),
                ceo_ingress_socket_path=settings.ceo_ingress_socket_path,
                ceo_ingress_peer_uid=os.geteuid()+1000,
                ceo_ingress_grounding_provider=readers, ceo_ingress_armed=False,
                ceo_ingress_app_binding=CeoIngressAppBinding(
                    peer_uid=os.geteuid(), armed=True, grounding_provider=readers, read_provider=readers,
                ),
            )
        await service.start()
        try:
            bound = (dataclasses.replace(
                settings, read_from_ceo_ingress=True,
                mastermind_root=tmp_path/'no-network-process-checkout', macro_root_flag=None,
            ) if installed else dataclasses.replace(settings, runtime_root=tmp_path / "runtime"))
            async with connection(bound) as client:
                token = fixture._submit_token(rsa_key)
                _, body = await call(client, token, "submit_ceo_intent", PAYLOAD)
                assert body.get("status") == "accepted", body
                receipt = body["receipt"]
                assert receipt["status"] == "QUEUED"
                assert receipt["dispatched"] is False
                job_id = receipt["job_id"]
                for name, arguments in (
                    ("executive_state", {}), ("executive_inbox", {}),
                    ("executive_job", {"job_id": job_id}),
                    ("ceo_intent_status", {"intent_id": receipt["intent_id"]}),
                ):
                    _, read = await call(client, token, name, arguments)
                    assert read["ok"] is True, read
                    assert read["tool"] == name
                    if name == "executive_job":
                        assert read["data"]["job"]["job_id"] == job_id
                        assert read["data"]["attempt_count"] == 0
                    if name == "ceo_intent_status":
                        assert read["data"]["job_id"] == job_id
                _, duplicate = await call(client, token, "submit_ceo_intent", PAYLOAD)
                assert duplicate["receipt"]["job_id"] == job_id
                assert duplicate["receipt"]["duplicate"] is True
                _, conflict = await call(client, token, "submit_ceo_intent", {**PAYLOAD, "priority": 99})
                assert conflict["status"] == "operation_conflict"
                assert conflict["request_ref"] == body["request_ref"]
                status = await client.post(
                    "/v1/tools/submit_ceo_intent/reconcile", headers=headers(token),
                    json={"request_ref": body["request_ref"]},
                )
                assert status.status_code == 200, status.text
                assert status.json()["receipt"]["job_id"] == job_id
                assert len(service.runtime.jobs.list_jobs()) == 1
                assert service.runtime.attempts.list_attempts() == []
                assert service.runtime.workers.list_workers() == []
        finally:
            await service.close()
    asyncio.run(exercise())


def test_direct_app_and_temporary_e1_keep_their_existing_policy_boundaries(settings, rsa_key, tmp_path):
    """The new transport must not silently enable scope unions on old profiles."""
    async def exercise():
        app = create_app(settings)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response = await client.post("/v1/tools/executive_state", headers=headers(fixture._submit_token(rsa_key)), json={"arguments": {}})
                assert response.status_code == 403
        finally:
            await app.aclose()
        readonly = dataclasses.replace(settings, read_only=True, ceo_ingress_socket_path=None, runtime_root=tmp_path / "runtime")
        build = getattr(transport, "build_executive_mcp_app", None)
        assert callable(build)
        with pytest.raises(ValueError, match="read.only"):
            build(readonly, audit_sink=Sink())
    asyncio.run(exercise())


def test_discovery_and_tool_auth_describe_the_same_two_scope_resource(settings, rsa_key):
    async def exercise():
        async with connection(settings) as client:
            metadata = await client.get(fixture.METADATA_PATH)
            assert metadata.json()["scopes_supported"] == [
                "mastermind.executive.intent.submit", "mastermind.executive.read",
            ]
            listed = await rpc(client, fixture._read_token(rsa_key), "tools/list")
            for tool in listed["tools"]:
                scopes = ["mastermind.executive.read"]
                if tool["name"] == "submit_ceo_intent":
                    scopes = ["mastermind.executive.intent.submit", "mastermind.executive.read"]
                expected = [{"type": "oauth2", "scopes": scopes}]
                assert tool["securitySchemes"] == expected
                assert tool["_meta"]["securitySchemes"] == expected
    asyncio.run(exercise())


@pytest.mark.parametrize("lost_reply", ["malformed", "oversized", "exception", "wrong_identity"])
def test_lost_app_reply_preserves_effect_unknown_and_reconciles_one_real_job(
    settings, rsa_key, tmp_path, short_socket_root, monkeypatch, lost_reply
):
    """Loss after real admission cannot be reported as no effect or resent."""
    from integrations.mastermind_executive_app import app as app_module

    real_create = app_module.create_app

    def damaged_reply(config):
        app = real_create(config)

        async def wrapped(scope, receive, send):
            if scope.get("path") != "/v1/tools/submit_ceo_intent":
                await app(scope, receive, send)
                return
            events = []

            async def collect(event):
                events.append(event)

            await app(scope, receive, collect)
            if lost_reply == "exception":
                raise OSError("deliberate loss after real admission")
            body = b"".join(event.get("body", b"") for event in events)
            admitted = json.loads(body)
            assert admitted["status"] == "accepted"
            if lost_reply == "malformed":
                body = b"{"
            elif lost_reply == "oversized":
                body = b" " * 262145
            else:
                admitted["request_ref"] = "req-wrong"
                body = json.dumps(admitted).encode()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": body})

        wrapped.aclose = app.aclose
        return wrapped

    monkeypatch.setattr(app_module, "create_app", damaged_reply)

    async def exercise():
        service = fixture._real_service(
            tmp_path, socket_root=short_socket_root,
            mastermind_root=Path(settings.mastermind_root), macro_root=Path(settings.macro_root_flag),
        )
        await service.start()
        try:
            async with connection(settings) as client:
                token = fixture._submit_token(rsa_key)
                result, outcome = await call(client, token, "submit_ceo_intent", PAYLOAD)
                assert outcome["status"] == "effect_unknown", outcome
                assert result["isError"] is True
                assert outcome["request_ref"].startswith("req-")
                response = await client.post("/v1/tools/submit_ceo_intent/reconcile",
                    headers=headers(token), json={"request_ref": outcome["request_ref"]})
                assert response.status_code == 200
                settled = response.json()
                assert settled["status"] == "accepted"
                assert settled["request_ref"] == outcome["request_ref"]
                job_id = settled["receipt"]["job_id"]
                assert [j.job_id for j in service.runtime.jobs.list_jobs()] == [job_id]
                assert service.runtime.attempts.list_attempts() == []
                assert service.runtime.workers.list_workers() == []
        finally:
            await service.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("claims", [
    {"iss": "https://wrong.example.test"},
    {"aud": "https://wrong.example.test/mcp"},
    {"sub": "not-allowed"},
    {"scope": "mastermind.executive.read mastermind.executive.intent.submit admin"},
    {"iat": fixture.NOW - 600, "exp": fixture.NOW - 100},
])
def test_native_auth_refuses_untrusted_claims_before_dispatch(settings, rsa_key, claims):
    async def exercise():
        token = fixture._token(rsa_key, **{
            "scope": "mastermind.executive.read mastermind.executive.intent.submit", **claims,
        })
        async with connection(settings) as client:
            response = await client.post("/mcp", headers=headers(token), json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "submit_ceo_intent", "arguments": PAYLOAD},
            })
            assert response.status_code == 401
            assert not Path(settings.ceo_ingress_socket_path).exists()
    asyncio.run(exercise())


def test_audit_failure_refuses_even_a_valid_submit_token(settings, rsa_key):
    class BrokenSink:
        def emit(self, event):
            raise OSError("audit unavailable")

    async def exercise():
        async with connection(settings, sink=BrokenSink()) as client:
            response = await client.post("/mcp", headers=headers(fixture._submit_token(rsa_key)),
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            assert response.status_code == 401
    asyncio.run(exercise())


def test_native_routes_are_literal_private_and_bounded(settings, rsa_key):
    async def exercise():
        async with connection(settings) as client:
            auth = headers(fixture._submit_token(rsa_key))
            for path in ("/mcp/", "/%6dcp", "/mcp?extra=1", "/v1/tools/submit_ceo_intent",
                         "/v1/tools/submit_ceo_intent%2Freconcile"):
                response = await client.post(path, headers=auth, json={})
                assert response.status_code == 404, (path, response.text)
            response = await client.post("/mcp", headers={**auth, "host": "untrusted.example.test"}, json={})
            assert response.status_code == 421
            response = await client.post("/mcp", headers=[*auth.items(), ("authorization", auth["authorization"])], json={})
            assert response.status_code == 401
            response = await client.post("/mcp", headers=auth, content=b" " * 65537)
            assert response.status_code == 413
            response = await client.post("/v1/tools/submit_ceo_intent/reconcile", headers=auth, content=b" " * 65537)
            assert response.status_code == 413
            assert not Path(settings.ceo_ingress_socket_path).exists()
    asyncio.run(exercise())


def _www_authenticate(sent):
    for key, value in sent[0].get("headers", []):
        if key.lower() == b"www-authenticate":
            return value
    return None


async def _asgi(
    app,
    *,
    method="POST",
    path="/mcp",
    host=b"127.0.0.1",
    extra_headers=(),
    events=None,
    receive=None,
):
    pending = list(events) if events is not None else [{"type": "http.request", "body": b"", "more_body": False}]

    async def default_receive():
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    sent = []

    async def send(event):
        sent.append(dict(event))

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "http",
            "method": method,
            "path": path,
            "raw_path": path.encode("ascii") if path.isascii() else b"",
            "query_string": b"",
            "headers": [
                (b"host", host),
                (b"accept", b"application/json, text/event-stream"),
                *extra_headers,
            ],
            "client": ("127.0.0.1", 9000),
            "server": ("127.0.0.1", 9001),
        },
        receive or default_receive,
        send,
    )
    return sent


_EMPTY_FRAMES = {
    "cl0": ([(b"content-length", b"0")], [{"type": "http.request", "body": b"", "more_body": False}]),
    "omitted_cl": ((), [{"type": "http.request", "body": b"", "more_body": False}]),
    "chunked_empty": (
        [(b"transfer-encoding", b"chunked")],
        [
            {"type": "http.request", "body": b"", "more_body": True},
            {"type": "http.request", "body": b"", "more_body": False},
        ],
    ),
}
_NONEMPTY_BODIES = (
    ("initialize", b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'),
    ("list", b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'),
    ("call", b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"executive_state","arguments":{}}}'),
    ("whitespace", b" "),
    ("object", b"{}"),
)


def test_native_empty_post_guard_before_auth_and_http_contract(settings, rsa_key, monkeypatch):
    """Empty POST /mcp is 400 before Authentication/RequireAuth; nonempty stays 401."""

    from integrations.business_mcp_auth.metadata import protected_resource_metadata
    from integrations.executive_mcp import e1_http as e1_http_module

    monkeypatch.setattr(e1_http_module, "PREAUTH_RECEIVE_DEADLINE_SECONDS", 0.05)
    app = transport.build_executive_mcp_app(settings, audit_sink=Sink())

    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            for name, (extra, events) in _EMPTY_FRAMES.items():
                sent = await _asgi(app, extra_headers=extra, events=events)
                assert sent[0]["status"] == 400, (name, sent[0]["status"], sent[-1].get("body"))
                assert b"empty" in sent[-1]["body"]
                assert _www_authenticate(sent) is None

            challenges = []
            for name, body in _NONEMPTY_BODIES:
                sent = await _asgi(
                    app,
                    extra_headers=[(b"content-length", str(len(body)).encode())],
                    events=[{"type": "http.request", "body": body, "more_body": False}],
                )
                assert sent[0]["status"] == 401, (name, sent[0]["status"])
                challenge = _www_authenticate(sent)
                assert challenge
                challenges.append(challenge)
            assert len(set(challenges)) == 1

            misleading = await _asgi(
                app,
                extra_headers=[(b"content-length", b"0")],
                events=[{"type": "http.request", "body": b"{}", "more_body": False}],
            )
            assert misleading[0]["status"] == 401
            assert _www_authenticate(misleading) == challenges[0]

            overflow = await _asgi(
                app,
                extra_headers=[(b"content-length", b"65537")],
                events=[{"type": "http.request", "body": b"x" * 65537, "more_body": False}],
            )
            assert overflow[0]["status"] == 413
            assert b"65536" in overflow[-1]["body"]
            assert _www_authenticate(overflow) is None

            disconnected = await _asgi(app, events=[{"type": "http.disconnect"}])
            assert disconnected[0]["status"] == 400
            assert _www_authenticate(disconnected) is None

            async def stalled():
                await asyncio.sleep(1)
                return {"type": "http.request", "body": b"x", "more_body": False}

            deadline = await _asgi(app, receive=stalled)
            assert deadline[0]["status"] == 400
            assert b"deadline" in deadline[-1]["body"]
            assert _www_authenticate(deadline) is None

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
            ) as client:
                missing = await client.get("/mcp")
                assert missing.status_code == 404
                metadata = await client.get(fixture.METADATA_PATH)
                assert metadata.status_code == 200
                assert metadata.json() == protected_resource_metadata(settings.policies.submit)
                well_known = await client.get("/.well-known/oauth-protected-resource/mcp")
                assert well_known.status_code == 404
                token = fixture._read_token(rsa_key)
                initialized = await client.post(
                    "/mcp",
                    headers=headers(token),
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "executive-test", "version": "1"},
                        },
                    },
                )
                assert initialized.status_code == 200, initialized.text
                assert "result" in initialized.json()
                duplicate = await client.post(
                    "/mcp",
                    headers=[
                        ("authorization", f"Bearer {token}"),
                        ("authorization", f"Bearer {token}"),
                        ("accept", "application/json, text/event-stream"),
                        ("mcp-protocol-version", "2025-06-18"),
                    ],
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                )
                assert duplicate.status_code == 401
                assert "www-authenticate" in duplicate.headers

    asyncio.run(exercise())
