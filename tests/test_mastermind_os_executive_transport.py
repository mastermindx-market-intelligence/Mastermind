"""Signed-token, no-execution tests for the fixed OS Executive transport.

These tests exercise the OS Executive HTTP transport against the existing
no-execution Unix/SQLite fixture (no live socket, no second scheduler, no
network, no installs).  The OS transport is the default-off v3 opt-in; this
file asserts its public fence, audit ordering, identity binding, durability of
the original request under inner loss, and compatibility with the existing
MCP catalog.

Every assertion is against a real signed temporary RS256 token and the
existing strict-v2 fixture - never a stub.
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
finally:
    sys.path.pop(0)

from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp import server as transport_server
from integrations.executive_mcp.server import OsStaticApp
from integrations.mastermind_executive_app.os_transport import (
    OsExecutiveTransportApp,
)

rsa_key = fixture.rsa_key
short_socket_root = fixture.short_socket_root
NOW = fixture.NOW
READ_SCOPE = fixture.READ_SCOPE
SUBMIT_SCOPE = fixture.SUBMIT_SCOPE

SUBMIT_PAYLOAD: dict[str, Any] = {
    "operation_key": "os-executive-transport-001",
    "objective": "Read the Q3 board packet and summarize open risks.",
    "department": "executive-infrastructure",
    "priority": 5,
    "execution_profile": "research_only",
}
_PUBLIC_HEADERS = {
    "host": "mcp.mastermind-x.com",
    "accept": "application/json",
}


class Sink:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


class FixedMdm:
    """Concrete fixed-shape MDM reader used by the existing v3 type gate."""

    def __init__(self) -> None:
        # The existing v3 reader calls list_macos_devices(...) to satisfy its
        # ownership contract; this fixture returns an empty canonical list.
        self.calls: list[tuple[object, ...]] = []

    def list_macos_devices(self, *args: object, **kwargs: object) -> list[dict[str, Any]]:
        self.calls.append(args)
        return []


class RecordingVerifier:
    """Wraps an audited submit verifier to observe what the outer bridge sent."""

    def __init__(self, verifier: MastermindTokenVerifier) -> None:
        self._verifier = verifier
        self.calls: list[str] = []

    async def verify_token_with_code(self, token: str) -> tuple[Any, Any]:
        self.calls.append(token)
        return await self._verifier.verify_token_with_code(token)


def headers(token: str, *, origin: str | None = None) -> dict[str, str]:
    values = {"authorization": f"Bearer {token}", **_PUBLIC_HEADERS}
    if origin is not None:
        values["origin"] = origin
    return values


def _assets() -> OsStaticApp:
    return OsStaticApp({
        "/os/": (b"<main>os</main>", "text/html; charset=utf-8"),
        "/os/assets/index-a.css": (b"body{}", "text/css; charset=utf-8"),
        "/os/assets/index-a.js": (b"void 0", "text/javascript; charset=utf-8"),
    })


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


def _v3_app(
    settings: Any,
    *,
    enabled: bool = True,
    os_app: OsStaticApp | None = None,
    audit_sink: Sink | None = None,
    mdm_reader: FixedMdm | None = None,
    os_resource: str | None = None,
) -> Any:
    return transport_server.build_web_ceo_v3_mcp_app(
        settings,
        audit_sink=audit_sink or Sink(),
        mdm_reader=mdm_reader or FixedMdm(),
        session_target_projector=lambda *_: [],
        session_reply_handler=lambda *_: {},
        session_summon_handler=lambda *_: {},
        os_app=os_app or _assets(),
        enable_os_executive_transport=enabled,
        os_executive_resource=(os_resource or settings.policies.submit.resource) if enabled else None,
    )


@contextlib.asynccontextmanager
async def client(
    settings: Any,
    *,
    enabled: bool = True,
    os_app: OsStaticApp | None = None,
    audit_sink: Sink | None = None,
    mdm_reader: FixedMdm | None = None,
    os_resource: str | None = None,
) -> Any:
    app = _v3_app(
        settings,
        enabled=enabled,
        os_app=os_app,
        audit_sink=audit_sink,
        mdm_reader=mdm_reader,
        os_resource=os_resource,
    )
    if not enabled or app.os_transport is None:
        yield app
        return
    transport = app.os_transport
    # Observe calls to the installed audited verifier, including refused tokens.
    # This is test instrumentation, not a public transport API.
    transport._submit_verifiers = tuple(RecordingVerifier(v) for v in transport._submit_verifiers)
    async with app._fenced_app._app.router.lifespan_context(app._fenced_app._app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://mcp.mastermind-x.com",
        ) as inner:
            inner.os_transport = transport
            yield inner


def _asgi(
    app: Any,
    *,
    method: str = "POST",
    path: str = "/os/executive/context",
    scheme: str = "https",
    host: bytes = b"mcp.mastermind-x.com",
    authorization: bytes | None = None,
    origin: bytes | None = None,
    raw_path: bytes | None = None,
    query: bytes = b"",
    body: bytes = b"{}",
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async def send(event: dict[str, Any]) -> None:
        events.append(event)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    header_items: list[tuple[bytes, bytes]] = [
        (b"host", host),
        (b"content-type", b"application/json"),
    ]
    if authorization is not None:
        header_items.append((b"authorization", authorization))
    if origin is not None:
        header_items.append((b"origin", origin))
    asyncio.run(app({
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "scheme": scheme, "method": method,
        "path": path,
        "raw_path": raw_path if raw_path is not None else path.encode("ascii"),
        "query_string": query, "headers": header_items,
        "client": ("127.0.0.1", 9000), "server": ("127.0.0.1", 9001),
    }, receive, send))
    return events


def test_default_off_and_wrong_profile_do_not_expose_routes(settings: Any) -> None:
    app = _v3_app(settings, enabled=False)
    assert app.os_transport is None
    assert not any(
        getattr(route, "path", "").startswith("/os/executive/")
        for route in app._fenced_app._app.routes
    )
    assert "/os/executive/context" not in app._fenced_app._routes
    with pytest.raises(ValueError, match="OS Executive transport requires"):
        transport_server.build_web_ceo_v3_mcp_app(
            settings,
            audit_sink=Sink(),
            mdm_reader=FixedMdm(),
            session_target_projector=lambda *_: [],
            session_reply_handler=lambda *_: {},
            session_summon_handler=lambda *_: {},
            os_app=None,
            enable_os_executive_transport=True,
        )


def test_transport_fences_path_host_origin_and_authorization(settings: Any, rsa_key: object) -> None:
    app = _v3_app(settings)
    token = fixture._submit_token(rsa_key).encode("ascii")
    assert _asgi(app, scheme="http")[0]["status"] == 403
    assert _asgi(app, host=b"wrong.example")[0]["status"] == 403
    assert _asgi(app, origin=b"https://wrong.example")[0]["status"] == 403
    assert _asgi(app, origin=b"https://mcp.mastermind-x.com")[0]["status"] == 403
    assert _asgi(app, authorization=b"Bearer " + token, query=b"?")[0]["status"] == 404
    assert _asgi(app, method="GET")[0]["status"] == 404
    assert _asgi(app, raw_path=b"/os/executive/%63ontext",
                  authorization=b"Bearer " + token)[0]["status"] == 404
    assert _asgi(app, path="/os/executive/context/",
                  authorization=b"Bearer " + token)[0]["status"] == 404
    events = _asgi(app, authorization=b"Bearer " + token)
    assert events[0]["status"] == 200
    assert events[0]["headers"][0][1] != b"text/html"
    response_body = b"".join(event.get("body", b"") for event in events)
    assert b"no-store" not in response_body


@pytest.mark.parametrize("claims", [
    {"scope": READ_SCOPE},
    {"aud": "https://foreign.example.test/mcp"},
    {"scope": f"{READ_SCOPE} {SUBMIT_SCOPE} admin"},
    {"sub": "not-allowed"},
])
def test_denied_tokens_stop_before_socket(settings: Any, rsa_key: object, claims: dict[str, Any]) -> None:
    async def exercise() -> None:
        async with client(settings) as inner:
            assert inner.os_transport is not None
            token = fixture._token(rsa_key, **{"scope": f"{READ_SCOPE} {SUBMIT_SCOPE}", **claims})
            response = await inner.post(
                "/os/executive/submit",
                headers=headers(token),
                json={"arguments": SUBMIT_PAYLOAD},
            )
            assert response.status_code in (401, 403), response.text
            assert inner.os_transport._submit_verifiers[0].calls
            assert response.headers["cache-control"] == "no-store"

    asyncio.run(exercise())


def test_audit_failure_refuses_before_inner_socket(settings: Any, rsa_key: object) -> None:
    class RefusingSink:
        def emit(self, event: Any) -> None:
            raise RuntimeError("audit refused")

    async def exercise() -> None:
        # Build directly so the RefusingSink reaches the OS verifier, then
        # wrap it via the same public attribute the tests use.
        app = transport_server.build_web_ceo_v3_mcp_app(
            settings,
            audit_sink=RefusingSink(),
            mdm_reader=FixedMdm(),
            session_target_projector=lambda *_: [],
            session_reply_handler=lambda *_: {},
            session_summon_handler=lambda *_: {},
            os_app=_assets(),
            enable_os_executive_transport=True,
            os_executive_resource=settings.policies.submit.resource,
        )
        assert app.os_transport is not None
        token = fixture._submit_token(rsa_key)
        async with app._fenced_app._app.router.lifespan_context(app._fenced_app._app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://mcp.mastermind-x.com",
            ) as inner:
                response = await inner.post(
                    "/os/executive/submit",
                    headers=headers(token),
                    json={"arguments": SUBMIT_PAYLOAD},
                )
                assert response.status_code == 401

    asyncio.run(exercise())


def test_context_is_stable_across_refresh_and_separates_identities(
    settings: Any, rsa_key: object,
) -> None:
    async def exercise() -> None:
        async with client(settings) as inner:
            assert inner.os_transport is not None
            first_token = fixture._submit_token(rsa_key)
            first = await inner.post(
                "/os/executive/context", headers=headers(first_token), json={}
            )
            assert first.status_code == 200, first.text
            first_body = first.json()
            assert first_body["schema"] == "mastermind.os.executive.owner_context.v1"
            refreshed_token = fixture._submit_token(
                rsa_key, jti="another-jti", iat=NOW + 1
            )
            refreshed = await inner.post(
                "/os/executive/context", headers=headers(refreshed_token), json={}
            )
            assert refreshed.status_code == 200, refreshed.text
            refreshed_body = refreshed.json()
            assert refreshed_body["principal_scope"] == first_body["principal_scope"]
            assert refreshed_body["verified_expiry"] == first_body["verified_expiry"]
            assert first_body["profile"]["name"] == "web_ceo_v3"
            assert first_body["profile"] == {"name": "web_ceo_v3", "server_version": "1.4.0"}
            different_token = fixture._submit_token(rsa_key, sub="different-subject")
            different = await inner.post(
                "/os/executive/context", headers=headers(different_token), json={}
            )
            assert different.status_code == 401

    asyncio.run(exercise())


def test_expired_and_access_projection_drift_are_withheld(settings: Any, rsa_key: object) -> None:
    async def exercise() -> None:
        async with client(settings) as inner:
            assert inner.os_transport is not None
            expired = fixture._submit_token(rsa_key, exp=NOW - 1)
            response = await inner.post(
                "/os/executive/context", headers=headers(expired), json={}
            )
            assert response.status_code == 401
            assert expired in inner.os_transport._submit_verifiers[0].calls

    asyncio.run(exercise())


@pytest.mark.parametrize("lose_reply", [False, True], ids=["accepted", "lost-reply"])
def test_strict_v2_original_launch_survives_reopen_without_duplicate(
    settings: Any, rsa_key: object, tmp_path: Path, short_socket_root: Path,
    lose_reply: bool,
) -> None:
    import hashlib
    import os
    import subprocess
    from control_plane import ceo_intent, ceo_request, executive_ceo_ingress as ingress
    from control_plane.executive_service import (
        CEO_WEB_CEO_V2_READ_SCHEMA, CeoIngressAppBinding, ExecutiveControlService,
    )
    from integrations.executive_mcp.web_ceo import WebCeoV2InstalledExecutiveReaders
    from integrations.mastermind_executive_app import gateway

    payload = {**SUBMIT_PAYLOAD, "workstream": "WS:OS-TRANSPORT-ORIGINAL"}
    root, macro = Path(settings.mastermind_root), Path(settings.macro_root_flag)
    sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()

    async def exercise() -> None:
        base = fixture._real_service(tmp_path, socket_root=short_socket_root,
                                     mastermind_root=root, macro_root=macro)
        grounding = fixture._RealGitGroundingProvider(mastermind_root=root, macro_root=macro)
        readers = WebCeoV2InstalledExecutiveReaders(
            repo_root=root, macro_root=macro, runtime_root=base.config.runtime_root)
        source = {
            "schema_version": "mastermind.executive_dialogue_source/v1",
            "work_ref": payload["workstream"],
            "commission_ref": {
                "repository": "mastermindx-market-intelligence/Mastermind",
                "commit": sha, "path": "README.md",
                "content_sha256": hashlib.sha256((root / "README.md").read_bytes()).hexdigest(),
            },
            "watch_mode": "turn_watch_v1",
        }
        source_state = [source]
        service = ExecutiveControlService(
            base.config, supervisor_factory=lambda runtime: fixture._NoExecutionSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "real.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=grounding, ceo_ingress_armed=False,
            ceo_ingress_dialogue_source_provider=lambda *_: source_state[0],
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=True, grounding_provider=grounding,
                read_provider=readers, read_schema=CEO_WEB_CEO_V2_READ_SCHEMA),
        )
        frames, acceptances, errors, handlers = [], [], [], set()

        async def proxy(reader, writer):
            task, upstream = asyncio.current_task(), None
            handlers.add(task)
            try:
                raw = await asyncio.wait_for(reader.readline(), 2)
                frame = json.loads(raw)
                frames.append(frame)
                response, upstream = await asyncio.open_unix_connection(
                    str(service.ceo_ingress_socket_path), limit=gateway._STREAM_LIMIT)
                upstream.write(raw)
                await upstream.drain()
                upstream.write_eof()
                reply = await asyncio.wait_for(response.readline(), 3)
                if frame["schema"] == ingress.SUBMIT_SCHEMA_V2:
                    acceptances.append(json.loads(reply))
                    if lose_reply:
                        return
                writer.write(reply)
                await writer.drain()
            except Exception as exc:
                errors.append(type(exc).__name__)
            finally:
                for stream in (upstream, writer):
                    if stream is not None:
                        stream.close()
                        try:
                            await asyncio.wait_for(stream.wait_closed(), .5)
                        except Exception:
                            stream.transport.abort()
                handlers.discard(task)

        server = None
        await service.start()
        try:
            server = await asyncio.start_unix_server(proxy, path=str(short_socket_root / "proxy.sock"))
            configured = dataclasses.replace(
                settings, ceo_ingress_socket_path=str(short_socket_root / "proxy.sock"),
                mastermind_root=tmp_path / "no-app-checkout", macro_root_flag=None,
                connect_timeout=.5, read_timeout=3,
            )
            token = fixture._submit_token(rsa_key)
            request_ref = ceo_request.app_request_ref(payload["operation_key"])
            intent_id = ceo_request.automated_intent_id(request_ref)
            async with client(configured) as inner:
                response = await inner.post("/os/executive/submit", headers=headers(token),
                                            json={"arguments": payload})
                assert response.status_code == (202 if lose_reply else 200), response.text
                outcome = response.json()
                assert outcome["request_ref"] == request_ref
                assert outcome["status"] == ("effect_unknown" if lose_reply else "accepted"), outcome
                if not lose_reply:
                    assert outcome["receipt"]["work_ref"] == payload["workstream"]
            assert len(acceptances) == 1 and acceptances[0]["ok"] is True, acceptances
            durable = ceo_intent.resolve_intent(service.runtime, intent_id)
            assert durable["schema"] == ceo_intent.RECEIPT_SCHEMA_V2
            assert durable["work_ref"] == payload["workstream"]
            assert durable["status"] == "QUEUED" and durable["dispatched"] is False
            jobs = service.runtime.jobs.list_jobs()
            assert len(jobs) == 1 and durable["job_id"] == jobs[0].job_id
            source_state[0] = None
            # Reopened app has only the original pointer; it makes a status read.
            async with client(configured) as reopened:
                response = await reopened.post(
                    "/os/executive/status", headers=headers(token),
                    json={"arguments": {"intent_id": intent_id}})
                assert response.status_code == 200, response.text
                assert response.json()["ok"] is True, response.text
                assert response.json()["data"] == durable
            assert sum(frame["schema"] == ingress.SUBMIT_SCHEMA_V2 for frame in frames) == 1
            assert service.runtime.jobs.list_jobs() == jobs
            assert service.runtime.attempts.list_attempts() == []
            assert service.runtime.workers.list_workers() == []
            assert not errors, errors
        finally:
            if server is not None:
                server.close()
                await server.wait_closed()
            if handlers:
                await asyncio.gather(*handlers, return_exceptions=True)
            await service.close()

    asyncio.run(exercise())


def test_overflow_body_is_refused(settings: Any, rsa_key: object) -> None:
    app = _v3_app(settings)
    token = fixture._submit_token(rsa_key).encode("ascii")
    oversized = b"{" + (b"x" * 70_000) + b"}"

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": oversized, "more_body": False}

    events: list[dict[str, Any]] = []

    async def send(event: dict[str, Any]) -> None:
        events.append(event)

    asyncio.run(app({
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "scheme": "https", "method": "POST",
        "path": "/os/executive/submit",
        "raw_path": b"/os/executive/submit",
        "query_string": b"",
        "headers": [
            (b"host", b"mcp.mastermind-x.com"),
            (b"content-type", b"application/json"),
            (b"authorization", b"Bearer " + token),
        ],
        "client": ("127.0.0.1", 9000), "server": ("127.0.0.1", 9001),
    }, receive, send))
    assert events[0]["status"] == 400
    body = b"".join(event.get("body", b"") for event in events)
    assert b"no-store" not in body
    assert b"65536" in body or b"transport budget" in body


def test_existing_mcp_catalog_and_security_remain_frozen(settings: Any, rsa_key: object) -> None:
    from integrations.executive_mcp import web_ceo_v3 as v3

    async def exercise() -> None:
        async with client(settings) as inner:
            token = fixture._read_token(rsa_key)
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            response = await inner.post(
                "http://127.0.0.1/mcp",
                headers={
                    "authorization": f"Bearer {token}", "host": "127.0.0.1",
                    "accept": "application/json, text/event-stream",
                    "mcp-protocol-version": "2025-06-18",
                },
                json=request,
            )
            assert response.status_code == 200, response.text
            listed = response.json()["result"]["tools"]
            assert {tool["name"] for tool in listed} == set(v3.web_ceo_v3_tool_names())
            for tool in listed:
                expected = (
                    [{"type": "oauth2", "scopes": [SUBMIT_SCOPE, READ_SCOPE]}]
                    if tool["name"] in {"submit_ceo_intent", "session_send", "session_summon"}
                    else [{"type": "oauth2", "scopes": [READ_SCOPE]}]
                )
                assert tool["securitySchemes"] == expected, tool

    asyncio.run(exercise())



@pytest.mark.parametrize("authorization", [b"Basic invalid", b"Bearer invalid"])
def test_refused_auth_never_reads_body(settings: Any, authorization: bytes) -> None:
    transport = _v3_app(settings).os_transport
    events = []
    async def receive():
        raise AssertionError("unauthenticated request must not allocate a body read")
    async def send(event):
        events.append(event)
    asyncio.run(transport({
        "type": "http", "method": "POST", "scheme": "https",
        "path": "/os/executive/context", "raw_path": b"/os/executive/context",
        "query_string": b"", "headers": [
            (b"host", b"mcp.mastermind-x.com"), (b"authorization", authorization)],
    }, receive, send))
    assert events[0]["status"] == 401
    assert (b"cache-control", b"no-store") in events[0]["headers"]


@pytest.mark.parametrize("mutation", ["ok", "request_ref", "intent_id", "work_ref", "extra"])
def test_malformed_submit_reply_is_original_unknown(settings: Any, rsa_key: object, mutation: str) -> None:
    from control_plane.ceo_request import app_request_ref, automated_intent_id
    request_ref = app_request_ref(SUBMIT_PAYLOAD["operation_key"])
    payload = {**SUBMIT_PAYLOAD, "workstream": "WS:ORIGINAL"}
    response = {"ok": True, "status": "accepted", "request_ref": request_ref,
                "receipt": {"dispatched": False, "intent_id": automated_intent_id(request_ref),
                            "work_ref": payload["workstream"]}}
    if mutation == "ok":
        response["ok"] = False
    elif mutation in ("intent_id", "work_ref"):
        response["receipt"][mutation] = "foreign"
    else:
        response[mutation] = "foreign"

    async def exercise():
        async with client(settings) as inner:
            async def malformed(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": json.dumps(response).encode()})
            inner.os_transport._inner_app = malformed
            result = await inner.post("/os/executive/submit", headers=headers(fixture._submit_token(rsa_key)),
                                      json={"arguments": payload})
            assert result.status_code == 202, result.text
            assert result.json()["status"] == "effect_unknown"
            assert result.json()["request_ref"] == request_ref
            assert "receipt" not in result.json()
    asyncio.run(exercise())


@pytest.mark.parametrize("drift", [False, True], ids=["foreign-intent", "auth-drift"])
def test_status_withholds_foreign_or_late_reply(settings: Any, rsa_key: object, drift: bool) -> None:
    from integrations.executive_mcp.schemas import result_envelope, ServerMode
    response = result_envelope("ceo_intent_status", mode=ServerMode.READONLY,
                               generated_at="2026-10-04T00:00:00Z",
                               data={"intent_id": "auto-" + ("a" if drift else "b") * 32})
    response["server_version"] = "1.4.0"
    async def exercise():
        async with client(settings) as inner:
            async def malformed(scope, receive, send):
                if drift:
                    async def unavailable(token):
                        return None
                    inner.os_transport._verified_binding = unavailable
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": json.dumps(response).encode()})
            inner.os_transport._inner_app = malformed
            result = await inner.post("/os/executive/status", headers=headers(fixture._submit_token(rsa_key)),
                                      json={"arguments": {"intent_id": "auto-" + "a" * 32}})
            assert result.status_code == (401 if drift else 503), result.text
            assert "data" not in result.json()
    asyncio.run(exercise())


def test_submit_auth_drift_after_possible_effect_retains_original_identity(settings: Any, rsa_key: object) -> None:
    from control_plane.ceo_request import app_request_ref
    async def exercise():
        async with client(settings) as inner:
            calls = []
            async def changed(scope, receive, send):
                calls.append(scope["path"])
                async def unavailable(token):
                    return None
                inner.os_transport._verified_binding = unavailable
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"{}"})
            inner.os_transport._inner_app = changed
            result = await inner.post("/os/executive/submit", headers=headers(fixture._submit_token(rsa_key)),
                                      json={"arguments": SUBMIT_PAYLOAD})
            assert result.status_code == 202, result.text
            assert result.json()["status"] == "effect_unknown"
            assert result.json()["request_ref"] == app_request_ref(SUBMIT_PAYLOAD["operation_key"])
            assert calls == ["/v1/tools/submit_ceo_intent"]
    asyncio.run(exercise())


def test_sealed_os_audience_rejects_tunnel_token_without_breaking_mcp(settings, rsa_key, monkeypatch):
    from ops.executive_os import executive_mcp_entry as entry
    from integrations.mastermind_executive_app import gateway
    # Each real authenticator gets the same disposable signed-key fixture; no network.
    monkeypatch.setattr(gateway, "_default_jwks_cache", lambda _: fixture._FakeJwksCache(rsa_key))
    raw = dict(executive_mcp_profile='web_ceo_v3', os_executive_transport=True,
               os_executive_resource=entry.OS_EXECUTIVE_RESOURCE)
    configured = dataclasses.replace(settings,
        additional_policies=entry.build_additional_policies(raw, settings.policies))
    async def check():
        async with client(configured, os_resource=entry.OS_EXECUTIVE_RESOURCE) as http:
            connector = fixture._submit_token(rsa_key)
            os_token = fixture._submit_token(rsa_key, aud=entry.OS_EXECUTIVE_RESOURCE)
            rejected = await http.post('/os/executive/context', headers=headers(connector), json={})
            assert rejected.status_code == 401
            accepted = await http.post('/os/executive/context', headers=headers(os_token), json={})
            assert accepted.status_code == 200
            foreign = fixture._submit_token(rsa_key, aud=entry.OS_EXECUTIVE_RESOURCE + '/other')
            assert (await http.post('/os/executive/context', headers=headers(foreign), json={})).status_code == 401
            # The unchanged incumbent connector remains authenticated for its own MCP catalog.
            result = await http.post('http://127.0.0.1/mcp', headers={'authorization': f'Bearer {connector}', 'accept': 'application/json, text/event-stream'},
                json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                      'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                                 'clientInfo': {'name': 'source-proof', 'version': '1'}}})
            assert result.status_code == 200
    asyncio.run(check())


def test_enabled_os_transport_requires_one_configured_audience(settings):
    for resource in (None, 'https://foreign.test/os/executive'):
        with pytest.raises(ValueError, match='one exact configured resource'):
            transport_server.build_web_ceo_v3_mcp_app(settings, audit_sink=Sink(),
                mdm_reader=FixedMdm(), session_target_projector=lambda *_: [],
                session_reply_handler=lambda *_: {}, session_summon_handler=lambda *_: {},
                os_app=_assets(), enable_os_executive_transport=True,
                os_executive_resource=resource)
