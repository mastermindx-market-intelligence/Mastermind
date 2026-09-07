"""Temporary E1 ASGI composition acceptance.

These tests use only in-process ASGI fixtures.  They never load an installed
runtime, socket, account, provider, or network target.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any


def _run(app: Any, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return events.pop(0) if events else {"type": "http.disconnect"}

    async def send(event: dict[str, Any]) -> None:
        sent.append(dict(event))

    asyncio.run(
        app(
            {
                "type": "http",
                "method": "POST",
                "path": "/v1/tools/executive_state",
                "raw_path": b"/v1/tools/executive_state",
                "headers": [],
            },
            receive,
            send,
        )
    )
    return sent


def test_bounded_request_coalesces_streamed_empty_frames_into_one_terminal_replay():
    """Both request guards retain the bounded payload, rather than every empty frame."""

    from integrations.executive_mcp.e1_http import BoundedE1App, BoundedRequestApp

    empty_frames = 10_000

    def streamed_receive(fragments: tuple[bytes, ...]) -> Any:
        cursor = 0

        async def receive() -> dict[str, Any]:
            nonlocal cursor
            if cursor < empty_frames:
                cursor += 1
                return {"type": "http.request", "body": b"", "more_body": True}
            fragment_index = cursor - empty_frames
            if fragment_index < len(fragments):
                cursor += 1
                return {
                    "type": "http.request",
                    "body": fragments[fragment_index],
                    "more_body": fragment_index + 1 < len(fragments),
                }
            return {"type": "http.disconnect"}

        return receive

    async def exercise() -> None:
        for wrapper in (BoundedE1App, BoundedRequestApp):
            for fragments, expected in (
                ((b"",), b""),
                ((b"left", b""), b"left"),
                ((b"left", b"", b"right"), b"leftright"),
            ):
                received: list[dict[str, Any]] = []
                sent: list[dict[str, Any]] = []

                async def inner(_scope: Any, receive: Any, send: Any) -> None:
                    received.extend((dict(await receive()), dict(await receive())))
                    await send({"type": "http.response.start", "status": 200, "headers": []})
                    await send({"type": "http.response.body", "body": b"ok", "more_body": False})

                async def send(event: dict[str, Any]) -> None:
                    sent.append(dict(event))

                await wrapper(inner)(
                    {
                        "type": "http",
                        "method": "POST",
                        "path": "/v1/tools/executive_state",
                        "raw_path": b"/v1/tools/executive_state",
                        "headers": [],
                    },
                    streamed_receive(fragments),
                    send,
                )

                assert received == [
                    {"type": "http.request", "body": expected, "more_body": False},
                    {"type": "http.disconnect"},
                ]
                assert sent[-1]["body"] == b"ok"

    asyncio.run(exercise())


def test_bounded_request_storage_does_not_grow_with_streamed_empty_frames():
    """Pausing before the terminal frame exposes a constant-size local buffer."""

    from integrations.executive_mcp.e1_http import BoundedE1App

    def direct_container_size(frame: Any, *excluded: object) -> int:
        excluded_ids = {id(value) for value in excluded}
        sizes = [
            len(value)
            for value in frame.f_locals.values()
            if id(value) not in excluded_ids and isinstance(value, (list, tuple, dict, set, bytearray))
        ]
        assert sizes
        return max(sizes)

    async def observe(empty_frames: int) -> tuple[int, Any]:
        cursor = 0
        before_terminal = asyncio.Event()
        release = asyncio.Event()

        async def receive() -> dict[str, Any]:
            nonlocal cursor
            if cursor == 0:
                cursor += 1
                return {"type": "http.request", "body": b"left", "more_body": True}
            if cursor <= empty_frames:
                cursor += 1
                return {"type": "http.request", "body": b"", "more_body": True}
            before_terminal.set()
            await release.wait()
            return {"type": "http.request", "body": b"right", "more_body": False}

        task = asyncio.create_task(BoundedE1App._bounded_request(receive))
        try:
            await before_terminal.wait()
            frame = task.get_coro().cr_frame
            assert frame is not None
            retained_size = direct_container_size(frame)
        finally:
            release.set()
            body = await task
        return retained_size, body

    small, small_body = asyncio.run(observe(1))
    large, large_body = asyncio.run(observe(10_000))

    assert small == large
    assert large <= 16
    assert small_body == large_body == b"leftright"


def test_e1_asgi_empty_response_frames_do_not_form_a_frame_buffer():
    """Pausing before the terminal response finds no empty-frame-sized collection."""

    from integrations.executive_mcp.e1_http import BoundedE1App

    def direct_container_size(frame: Any, *excluded: object) -> int:
        excluded_ids = {id(value) for value in excluded}
        sizes = [
            len(value)
            for value in frame.f_locals.values()
            if id(value) not in excluded_ids and isinstance(value, (list, tuple, dict, set, bytearray))
        ]
        assert sizes
        return max(sizes)

    async def observe(empty_frames: int) -> int:
        empty_frames_sent = asyncio.Event()
        release = asyncio.Event()
        sent: list[dict[str, Any]] = []
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/v1/tools/executive_state",
            "raw_path": b"/v1/tools/executive_state",
            "headers": [],
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"{}", "more_body": False}

        async def send(event: dict[str, Any]) -> None:
            sent.append(dict(event))

        async def inner(_scope: Any, _receive: Any, bounded_send: Any) -> None:
            await bounded_send({"type": "http.response.start", "status": 200, "headers": []})
            await bounded_send({"type": "http.response.body", "body": b"left", "more_body": True})
            for _ in range(empty_frames):
                await bounded_send({"type": "http.response.body", "body": b"", "more_body": True})
            empty_frames_sent.set()
            await release.wait()
            await bounded_send({"type": "http.response.body", "body": b"right", "more_body": False})

        app = BoundedE1App(inner)
        task = asyncio.create_task(app(scope, receive, send))
        try:
            await empty_frames_sent.wait()
            frame = task.get_coro().cr_frame
            assert frame is not None
            retained_size = direct_container_size(frame, scope, app)
        finally:
            release.set()
            await task

        assert sent[-1]["body"] == b"leftright"
        return retained_size

    small, large = asyncio.run(observe(1)), asyncio.run(observe(10_000))

    assert small == large
    assert large <= 16


def test_e1_asgi_coalesces_empty_response_fragments_without_changing_payload_order():
    """Entirely empty, terminal empty, and interleaved empties have one ordered body."""

    from integrations.executive_mcp.e1_http import BoundedE1App

    async def exercise() -> None:
        for fragments, expected in (
            ((b"",), b""),
            ((b"left", b""), b"left"),
            ((b"left", b"", b"right"), b"leftright"),
        ):
            sent: list[dict[str, Any]] = []

            async def receive() -> dict[str, Any]:
                return {"type": "http.request", "body": b"{}", "more_body": False}

            async def send(event: dict[str, Any]) -> None:
                sent.append(dict(event))

            async def inner(_scope: Any, _receive: Any, bounded_send: Any) -> None:
                await bounded_send({"type": "http.response.start", "status": 200, "headers": []})
                for index, body in enumerate(fragments):
                    await bounded_send(
                        {
                            "type": "http.response.body",
                            "body": body,
                            "more_body": index + 1 < len(fragments),
                        }
                    )

            await BoundedE1App(inner)(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/v1/tools/executive_state",
                    "raw_path": b"/v1/tools/executive_state",
                    "headers": [],
                },
                receive,
                send,
            )
            assert sent[-1] == {"type": "http.response.body", "body": expected, "more_body": False}

    asyncio.run(exercise())


def test_e1_asgi_refuses_incremental_body_overflow_before_inner_app_runs():
    """Removing receive accounting must let the oversized body reach the app."""

    from integrations.executive_mcp.e1_http import MAX_REQUEST_BYTES, BoundedE1App

    calls: list[str] = []

    async def inner(_scope: Any, _receive: Any, _send: Any) -> None:
        calls.append("inner")

    app = BoundedE1App(inner)
    sent = _run(
        app,
        [
            {"type": "http.request", "body": b"a" * MAX_REQUEST_BYTES, "more_body": True},
            {"type": "http.request", "body": b"b", "more_body": False},
        ],
    )

    assert calls == []
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    assert sent[-1]["body"] == b'{"ok":false,"error":{"code":"invalid_input","message":"request body exceeds 65536 bytes"}}'


def test_outer_request_limiter_refuses_overflow_before_manager_dispatch():
    """Removing the outer receive guard would let MCP buffer this body."""

    from integrations.executive_mcp.e1_http import MAX_REQUEST_BYTES, BoundedRequestApp

    calls: list[str] = []

    async def manager(_scope: Any, _receive: Any, _send: Any) -> None:
        calls.append("manager")

    sent = _run(
        BoundedRequestApp(manager),
        [{"type": "http.request", "body": b"x" * (MAX_REQUEST_BYTES + 1), "more_body": False}],
    )

    assert calls == []
    assert sent[0]["status"] == 413


def test_real_e1_outer_counts_multiframe_bodies_not_content_length_before_sdk_dispatch(tmp_path, monkeypatch):
    """The authenticated SDK edge admits exactly 65536 bytes and rejects all bad framing."""

    import json
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager as RealManager
    from integrations.executive_mcp.e1_http import MAX_REQUEST_BYTES
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    import integrations.executive_mcp.server as server_module

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    manager_calls: list[str] = []
    inner_calls: list[str] = []

    class CountingManager(RealManager):
        async def handle_request(self, scope: Any, receive: Any, send: Any) -> None:
            manager_calls.append(str(scope.get("path")))
            await super().handle_request(scope, receive, send)

    class ForbiddenInner:
        async def __call__(self, _scope: Any, _receive: Any, _send: Any) -> None:
            inner_calls.append("inner")
            raise AssertionError("tools/list must not reach the inner reader")

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(server_module, "StreamableHTTPSessionManager", CountingManager)
    monkeypatch.setattr(server_module, "build_e1_app", lambda _settings: ForbiddenInner())
    key = auth_fixture.rsa_key.__wrapped__()
    app = server_module.build_e1_mcp_app(
        AppSettings(
            policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
            mastermind_root=tmp_path / "mastermind", macro_root_flag=str(tmp_path / "macro"),
            runtime_root=tmp_path / "runtime", environ={}, ceo_ingress_socket_path=None,
            read_only=True, jwks_cache=auth_fixture._FakeJwksCache(key),
            clock=lambda: auth_fixture.NOW,
        ),
        audit_sink=Sink(),
    )
    bearer = f"Bearer {auth_fixture._read_token(key)}"
    request = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        separators=(",", ":"),
    ).encode("utf-8")
    exact = request + b" " * (MAX_REQUEST_BYTES - len(request))
    one_over = exact + b" "

    async def invoke(events: list[dict[str, Any]], content_length: bytes) -> list[dict[str, Any]]:
        cursor = 0
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            nonlocal cursor
            if cursor < len(events):
                event = events[cursor]
                cursor += 1
                return event
            return {"type": "http.disconnect"}

        async def send(event: dict[str, Any]) -> None:
            sent.append(dict(event))

        await app(
            {
                "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1", "scheme": "http", "method": "POST",
                "path": "/mcp", "raw_path": b"/mcp", "query_string": b"",
                "headers": [
                    (b"host", b"e1.local"), (b"authorization", bearer.encode("ascii")),
                    (b"accept", b"application/json, text/event-stream"),
                    (b"mcp-protocol-version", b"2025-06-18"),
                    (b"content-type", b"application/json"), (b"content-length", content_length),
                ],
                "client": ("127.0.0.1", 9000), "server": ("127.0.0.1", 9001),
            },
            receive,
            send,
        )
        return sent

    async def exercise() -> None:
        outer = app._app
        async with outer.router.lifespan_context(outer):
            exact_sent = await invoke(
                [
                    {"type": "http.request", "body": exact[:17_000], "more_body": True},
                    {"type": "http.request", "body": exact[17_000:], "more_body": False},
                ],
                b"0",
            )
            assert exact_sent[0]["status"] == 200
            assert manager_calls == ["/mcp"]
            malformed_json_sent = await invoke(
                [{"type": "http.request", "body": b"{", "more_body": False}], b"1"
            )
            assert malformed_json_sent[0]["status"] == 400
            assert manager_calls == ["/mcp", "/mcp"]
            assert inner_calls == []
            overflow_sent = await invoke(
                [
                    {"type": "http.request", "body": one_over[:MAX_REQUEST_BYTES], "more_body": True},
                    {"type": "http.request", "body": one_over[MAX_REQUEST_BYTES:], "more_body": False},
                ],
                b"1",
            )
            assert overflow_sent[0]["status"] == 413
            assert b"exceeds 65536 bytes" in overflow_sent[-1]["body"]
            disconnect_sent = await invoke([{"type": "http.disconnect"}], b"0")
            assert disconnect_sent[0]["status"] == 400
            malformed_sent = await invoke(
                [
                    {"type": "http.request", "body": b"{}", "more_body": True},
                    {"type": "http.response.start", "status": 200},
                ],
                b"2",
            )
            assert malformed_sent[0]["status"] == 400
            assert manager_calls == ["/mcp", "/mcp"]
            assert inner_calls == []

    asyncio.run(exercise())


def test_e1_asgi_refuses_output_overflow_without_a_partial_response():
    """Removing send accounting would expose a healthy-looking partial 200."""

    from integrations.executive_mcp.e1_http import MAX_RESPONSE_BYTES, BoundedE1App

    async def inner(_scope: Any, _receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"a" * MAX_RESPONSE_BYTES, "more_body": True})
        await send({"type": "http.response.body", "body": b"b", "more_body": False})

    sent = _run(
        BoundedE1App(inner),
        [{"type": "http.request", "body": b"{}", "more_body": False}],
    )

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 503
    assert sent[-1]["body"] == b'{"ok":false,"error":{"code":"output_too_large","message":"E1 response exceeds 262144 bytes"}}'


def test_e1_asgi_refuses_malformed_response_event_sequences_without_partial_success():
    """Malformed inner ASGI framing must not leak any preceding healthy event."""

    from integrations.executive_mcp.e1_http import BoundedE1App

    async def duplicate_start(_scope: Any, _receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": b"wrong", "more_body": False})

    async def body_before_start(_scope: Any, _receive: Any, send: Any) -> None:
        await send({"type": "http.response.body", "body": b"wrong", "more_body": False})

    async def body_after_final(_scope: Any, _receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": False})
        await send({"type": "http.response.body", "body": b"wrong", "more_body": False})

    async def incomplete(_scope: Any, _receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})

    for inner in (duplicate_start, body_before_start, body_after_final, incomplete):
        sent = _run(
            BoundedE1App(inner),
            [{"type": "http.request", "body": b"{}", "more_body": False}],
        )
        assert sent[0]["type"] == "http.response.start"
        assert sent[0]["status"] == 503
        assert sent[-1]["body"] == b'{"ok":false,"error":{"code":"backend_unavailable","message":"E1 response is unavailable"}}'


def test_e1_asgi_accepts_exact_multiframe_output_and_refuses_one_byte_more():
    """The byte ceiling applies to the whole emitted response, not each frame."""

    from integrations.executive_mcp.e1_http import MAX_RESPONSE_BYTES, BoundedE1App

    async def exact(_scope: Any, _receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"a" * (MAX_RESPONSE_BYTES // 2), "more_body": True})
        await send({"type": "http.response.body", "body": b"b" * (MAX_RESPONSE_BYTES // 2), "more_body": False})

    async def one_over(_scope: Any, _receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"a" * MAX_RESPONSE_BYTES, "more_body": True})
        await send({"type": "http.response.body", "body": b"b", "more_body": False})

    exact_sent = _run(
        BoundedE1App(exact),
        [{"type": "http.request", "body": b"{}", "more_body": False}],
    )
    assert exact_sent[0]["status"] == 200
    assert len(exact_sent[-1]["body"]) == MAX_RESPONSE_BYTES
    one_over_sent = _run(
        BoundedE1App(one_over),
        [{"type": "http.request", "body": b"{}", "more_body": False}],
    )
    assert one_over_sent[0]["status"] == 503


def test_e1_asgi_refuses_disconnect_before_the_inner_app_runs():
    """A disconnected request has no complete body to replay to the reader."""

    from integrations.executive_mcp.e1_http import BoundedE1App

    calls: list[str] = []

    async def inner(_scope: Any, _receive: Any, _send: Any) -> None:
        calls.append("inner")

    sent = _run(BoundedE1App(inner), [{"type": "http.disconnect"}])
    assert calls == []
    assert sent[0]["status"] == 400
    assert sent[-1]["body"] == b'{"ok":false,"error":{"code":"invalid_input","message":"request body is incomplete"}}'


def test_e1_mcp_tool_table_is_exactly_the_four_readers():
    """Adding a submit tool must break the E1 inventory before dispatch."""

    from integrations.executive_mcp.server import build_e1_tools

    assert [tool.name for tool in build_e1_tools()] == [
        "executive_state",
        "executive_inbox",
        "executive_job",
        "ceo_intent_status",
    ]


def test_e1_profile_has_its_own_pinned_four_read_fingerprint():
    """Reusing the legacy five-tool digest must fail this profile boundary."""

    from integrations.executive_mcp.e1_http import E1_PROFILE_SHA256
    from integrations.executive_mcp.schemas import SCHEMA_SNAPSHOT_SHA256

    assert E1_PROFILE_SHA256 == "c2dd209218852fe08d87de4c3b3da7f3ae41c1e1724f7fb8e1250a901e15aa6f"
    assert E1_PROFILE_SHA256 != SCHEMA_SNAPSHOT_SHA256


def test_real_e1_mcp_metadata_initialize_list_and_four_reader_calls(tmp_path, monkeypatch):
    """The outer builder must run the real pinned MCP HTTP protocol."""

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    import httpx
    from control_plane.executive_runtime import Runtime
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    import integrations.executive_mcp.server as server_module

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    key = auth_fixture.rsa_key.__wrapped__()
    runtime_root = tmp_path / "runtime"
    job_a = Runtime.at(runtime_root).jobs.create_job("temporary JobA", department="research", priority=1)
    settings = AppSettings(
        policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
        mastermind_root=tmp_path / "mastermind",
        macro_root_flag=str(tmp_path / "macro"),
        runtime_root=runtime_root,
        environ={}, ceo_ingress_socket_path=None, read_only=True,
        jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
    )
    forwarded: list[str] = []
    original_inner = server_module.build_e1_app
    def observe_inner(config):
        app = original_inner(config)
        async def observed(scope, receive, send):
            if scope.get("path", "").startswith("/v1/tools/"):
                forwarded.extend(value.decode() for key, value in scope["headers"] if key == b"authorization")
            await app(scope, receive, send)
        observed.aclose = app.aclose
        return observed
    monkeypatch.setattr(server_module, "build_e1_app", observe_inner)
    app = server_module.build_e1_mcp_app(settings, audit_sink=Sink())

    async def exercise() -> None:
        inner = app._app
        async with inner.router.lifespan_context(inner):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://e1.local") as client:
                assert (await client.get(auth_fixture.METADATA_PATH)).status_code == 200
                missing = await client.post("/mcp", json={"jsonrpc":"2.0","id":1,"method":"tools/list"})
                assert missing.status_code == 401 and "www-authenticate" in missing.headers
                denied = await client.post("/mcp", headers={"authorization": f"Bearer {auth_fixture._read_token(key, iss='https://wrong.example')}", "accept":"application/json, text/event-stream", "mcp-protocol-version":"2025-06-18"}, json={"jsonrpc":"2.0","id":11,"method":"tools/list"})
                assert denied.status_code in (401, 403) and "www-authenticate" in denied.headers
                widened = await client.post("/mcp", headers={"authorization": f"Bearer {auth_fixture._submit_token(key)}", "accept":"application/json, text/event-stream", "mcp-protocol-version":"2025-06-18"}, json={"jsonrpc":"2.0","id":12,"method":"tools/list"})
                assert widened.status_code in (401, 403) and "www-authenticate" in widened.headers
                duplicate = await client.post("/mcp", headers=[("authorization", f"Bearer {auth_fixture._read_token(key)}"), ("authorization", f"Bearer {auth_fixture._read_token(key)}"), ("accept", "application/json, text/event-stream"), ("mcp-protocol-version", "2025-06-18")], json={"jsonrpc":"2.0","id":13,"method":"tools/list"})
                assert duplicate.status_code == 401 and "www-authenticate" in duplicate.headers
                assert forwarded == []
                headers={"authorization": f"Bearer {auth_fixture._read_token(key)}", "accept":"application/json, text/event-stream", "mcp-protocol-version":"2025-06-18"}
                initialize = await client.post("/mcp", headers=headers, json={"jsonrpc":"2.0","id":2,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1"}}})
                assert initialize.status_code == 200
                listed = await client.post("/mcp", headers=headers, json={"jsonrpc":"2.0","id":3,"method":"tools/list"})
                assert sorted(item["name"] for item in listed.json()["result"]["tools"]) == ["ceo_intent_status", "executive_inbox", "executive_job", "executive_state"]
                for request_id, name, arguments in (
                    (4, "executive_state", {}),
                    (5, "executive_inbox", {}),
                    (6, "executive_job", {"job_id": job_a.job_id}),
                    (7, "ceo_intent_status", {"intent_id": "INTENT-A"}),
                ):
                    called = await client.post("/mcp", headers=headers, json={"jsonrpc":"2.0","id":request_id,"method":"tools/call","params":{"name":name,"arguments":arguments}})
                    assert called.status_code == 200, called.text
                    text = called.json()["result"]["content"][0]["text"]
                    envelope = __import__("json").loads(text)
                    assert envelope["tool"] == name
                    if name == "executive_job":
                        assert envelope["data"]["job"]["job_id"] == job_a.job_id
                assert forwarded and all(value == headers["authorization"] for value in forwarded)
    asyncio.run(exercise())


def test_real_e1_mcp_validates_outer_arguments_and_canonicalizes_inner_failures(tmp_path, monkeypatch):
    """The MCP handler is a strict one-request proxy, never an envelope forge."""

    from datetime import datetime, timezone
    import json
    import httpx
    import pytest
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from integrations.executive_mcp.e1_http import MAX_RESPONSE_BYTES
    from integrations.executive_mcp.schemas import (
        ServerMode,
        error_envelope,
        result_envelope,
        validate_tool_arguments as real_validate_tool_arguments,
    )
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    import integrations.executive_mcp.server as server_module

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    key = auth_fixture.rsa_key.__wrapped__()
    generated_at = (
        datetime.fromtimestamp(auth_fixture.NOW, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    settings = AppSettings(
        policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
        mastermind_root=tmp_path / "mastermind",
        macro_root_flag=str(tmp_path / "macro"),
        runtime_root=tmp_path / "runtime",
        environ={}, ceo_ingress_socket_path=None, read_only=True,
        jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
    )
    success = result_envelope(
        "executive_state", mode=ServerMode.READONLY, generated_at=generated_at,
        data={"from": "inner"},
    )
    preserved_error = error_envelope(
        "executive_state", mode=ServerMode.READONLY, generated_at=generated_at,
        code="not_found", message="the temporary record is absent",
    )
    integer_timestamp = result_envelope(
        "executive_state", mode=ServerMode.READONLY, generated_at=auth_fixture.NOW,
        data={"must": "not cross the E1 boundary"},
    )
    non_string_error_code = error_envelope(
        "executive_state", mode=ServerMode.READONLY, generated_at=generated_at,
        code="not_found", message="the type is intentionally malformed",
    )
    non_string_error_code["error"]["code"] = []
    non_finite_success = result_envelope(
        "executive_state", mode=ServerMode.READONLY, generated_at=generated_at,
        data={"not_json": float("nan")},
    )
    unavailable = error_envelope(
        "executive_state", mode=ServerMode.READONLY, generated_at=generated_at,
        code="backend_unavailable", message="E1 response is unavailable",
    )
    responses: list[tuple[int, bytes] | BaseException] = [
        (200, json.dumps(success).encode("utf-8")),
        (200, json.dumps(preserved_error).encode("utf-8")),
        (200, json.dumps(integer_timestamp).encode("utf-8")),
        (200, json.dumps(non_string_error_code).encode("utf-8")),
        (200, json.dumps(non_finite_success).encode("utf-8")),
        (200, b"{"),
        (200, b'{"not":"an E1 envelope"}'),
        (503, b'{"error":"unavailable"}'),
        httpx.ReadError("E1 connection vanished"),
        (200, json.dumps({"oversized": "x" * MAX_RESPONSE_BYTES}).encode("utf-8")),
    ]
    received: list[dict[str, Any]] = []
    validated: list[tuple[str, dict[str, Any]]] = []

    class ControlledInner:
        closed = 0

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            assert scope["path"] == "/v1/tools/executive_state"
            body = b""
            while True:
                event = await receive()
                assert event["type"] == "http.request"
                body += event.get("body", b"")
                if not event.get("more_body", False):
                    break
            received.append(json.loads(body))
            outcome = responses.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            status, response_body = outcome
            await send({
                "type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": response_body})

        async def aclose(self) -> None:
            self.closed += 1

    controlled_inner = ControlledInner()

    def observed_validate(name: str, arguments: Any) -> dict[str, Any]:
        normalized = real_validate_tool_arguments(name, arguments)
        validated.append((name, normalized))
        # This marker proves the inner request contains the shared validator's
        # result rather than the raw MCP argument mapping.
        return {**normalized, "validated_by_outer": True}

    monkeypatch.setattr(server_module, "build_e1_app", lambda _settings: controlled_inner)
    monkeypatch.setattr(
        server_module, "validate_tool_arguments", observed_validate, raising=False
    )
    app = server_module.build_e1_mcp_app(settings, audit_sink=Sink())
    headers = {
        "authorization": f"Bearer {auth_fixture._read_token(key)}",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18",
    }

    async def call(client: httpx.AsyncClient, request_id: int, arguments: dict[str, Any]) -> dict[str, Any]:
        response = await client.post(
            "/mcp", headers=headers,
            json={
                "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                "params": {"name": "executive_state", "arguments": arguments},
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        text = payload["result"]["content"][0]["text"]
        assert text, payload
        assert text.startswith("{"), payload
        return json.loads(text)

    async def exercise() -> None:
        outer = app._app
        async with outer.router.lifespan_context(outer):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://e1.local"
            ) as client:
                results = [await call(client, request_id, {}) for request_id in range(1, 11)]
                assert results[:2] == [success, preserved_error]
                assert results[2:] == [unavailable] * 8

    asyncio.run(exercise())
    assert validated == [("executive_state", {})] * 10
    assert received == [{"arguments": {"validated_by_outer": True}}] * 10
    assert controlled_inner.closed == 1


def test_real_e1_mcp_outer_authentication_matrix_refuses_before_the_inner_app(tmp_path, monkeypatch):
    """Outer A1 denials cannot be salvaged by the independently checked E1 app."""

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    import httpx
    from cryptography.hazmat.primitives.asymmetric import rsa
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies, READ_SCOPE
    import integrations.executive_mcp.server as server_module

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    key = auth_fixture.rsa_key.__wrapped__()
    settings = AppSettings(
        policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
        mastermind_root=tmp_path / "mastermind",
        macro_root_flag=str(tmp_path / "macro"),
        runtime_root=tmp_path / "runtime",
        environ={}, ceo_ingress_socket_path=None, read_only=True,
        jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
    )
    forwarded: list[str] = []
    original_inner = server_module.build_e1_app

    def observe_inner(config: Any) -> Any:
        app = original_inner(config)

        async def observed(scope: Any, receive: Any, send: Any) -> None:
            if scope.get("path", "").startswith("/v1/tools/"):
                forwarded.extend(
                    value.decode("ascii")
                    for header, value in scope["headers"]
                    if header.lower() == b"authorization"
                )
            await app(scope, receive, send)

        observed.aclose = app.aclose
        return observed

    monkeypatch.setattr(server_module, "build_e1_app", observe_inner)
    app = server_module.build_e1_mcp_app(settings, audit_sink=Sink())
    exact_bearer = f"Bearer {auth_fixture._read_token(key)}"
    offline_bearer = f"Bearer {auth_fixture._token(key, scope=f'{READ_SCOPE} offline_access')}"
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    denied_headers = [
        ("missing", None),
        ("duplicate", [exact_bearer, exact_bearer]),
        ("wrong issuer", f"Bearer {auth_fixture._read_token(key, iss='https://wrong.example.test')}"),
        ("wrong audience", f"Bearer {auth_fixture._read_token(key, aud='https://wrong.example.test/mcp')}"),
        ("wrong subject", f"Bearer {auth_fixture._read_token(key, sub='not-admitted')}"),
        ("wrong signature", f"Bearer {auth_fixture._token(wrong_key, scope=READ_SCOPE)}"),
        ("expired", f"Bearer {auth_fixture._read_token(key, iat=auth_fixture.NOW - 1000, exp=auth_fixture.NOW - 100)}"),
        ("not yet valid", f"Bearer {auth_fixture._read_token(key, iat=auth_fixture.NOW + 500, nbf=auth_fixture.NOW + 500, exp=auth_fixture.NOW + 800)}"),
        ("read plus submit", f"Bearer {auth_fixture._submit_token(key)}"),
    ]

    async def exercise() -> None:
        inner = app._app
        common_headers = {
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": "2025-06-18",
        }
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        async with inner.router.lifespan_context(inner):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://e1.local"
            ) as client:
                for label, bearer in denied_headers:
                    headers: dict[str, str] | list[tuple[str, str]]
                    if isinstance(bearer, list):
                        headers = [
                            *(common_headers.items()),
                            *( ("authorization", value) for value in bearer ),
                        ]
                    else:
                        headers = dict(common_headers)
                        if bearer is not None:
                            headers["authorization"] = bearer
                    response = await client.post("/mcp", headers=headers, json=request)
                    assert response.status_code in (401, 403), (label, response.status_code, response.text)
                    assert "www-authenticate" in response.headers, label
                    assert forwarded == [], label

                for request_id, bearer in ((2, exact_bearer), (3, offline_bearer)):
                    response = await client.post(
                        "/mcp",
                        headers={**common_headers, "authorization": bearer},
                        json={"jsonrpc": "2.0", "id": request_id, "method": "tools/list"},
                    )
                    assert response.status_code == 200, response.text

                called = await client.post(
                    "/mcp",
                    headers={**common_headers, "authorization": exact_bearer},
                    json={
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {"name": "executive_state", "arguments": {}},
                    },
                )
                assert called.status_code == 200, called.text

    asyncio.run(exercise())
    assert forwarded == [exact_bearer]


def test_real_e1_mcp_all_four_reads_and_write_aliases_never_reach_writer_components(tmp_path, monkeypatch):
    """E1 construction, reads, and denied writer aliases have zero writer reachability."""

    import json
    import httpx
    import pytest
    from control_plane.ceo_intent import submit_intent
    from control_plane.executive_runtime import Runtime
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    import integrations.executive_mcp.adapter as adapter_module
    from integrations.mastermind_executive_app import app as app_module
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.executive_mcp.e1_http import build_e1_app
    import integrations.executive_mcp.server as server_module

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    # Seeding is complete before writer sentinels are armed.  The observation
    # phase therefore proves the composed profile itself never mutates state.
    repository_root = tmp_path / "mastermind"
    macro_root = tmp_path / "macro"
    auth_fixture._git_repo(repository_root, content="repository")
    (macro_root / "scripts").mkdir(parents=True)
    (macro_root / "scripts" / "agentos.py").write_text("", encoding="utf-8")
    (macro_root / "agentos").mkdir()
    auth_fixture._git_repo(macro_root, content="macro")
    runtime = Runtime.at(tmp_path / "runtime")
    job = runtime.jobs.create_job("temporary E1 job", department="research", priority=1)
    intent = submit_intent(
        runtime,
        {
            "schema": "mastermind.ceo_intent.v1",
            "intent_id": "intent-e1-read-only",
            "actor": "ceo-sol",
            "objective": "Read a seeded temporary E1 receipt.",
            "department": "research",
            "priority": 1,
            "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
            "execution_contract": {"requested_authorities": ["READ"]},
        },
    )
    writer_touches: list[str] = []

    def writer_forbidden(name: str) -> None:
        writer_touches.append(name)
        raise AssertionError(f"E1 reached writer component {name}")

    class ForbiddenIngress:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            writer_forbidden("CeoIngressClient")

    class ForbiddenAdmissionRequest:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            writer_forbidden("AdmissionRequest")

    async def forbidden_admission(*_args: Any, **_kwargs: Any) -> Any:
        writer_forbidden("compose_admission")

    async def forbidden_reconcile(*_args: Any, **_kwargs: Any) -> Any:
        writer_forbidden("reconcile_by_request_ref")

    async def forbidden_transport(*_args: Any, **_kwargs: Any) -> Any:
        writer_forbidden("send_control_request")

    monkeypatch.setattr(app_module, "CeoIngressClient", ForbiddenIngress)
    monkeypatch.setattr(app_module, "AdmissionRequest", ForbiddenAdmissionRequest)
    monkeypatch.setattr(app_module, "compose_admission", forbidden_admission)
    monkeypatch.setattr(app_module, "reconcile_by_request_ref", forbidden_reconcile)
    monkeypatch.setattr(adapter_module, "send_control_request", forbidden_transport)

    forwarded: list[str] = []
    original_inner = server_module.build_e1_app

    class ObservedInner:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if scope.get("path", "").startswith("/v1/tools/"):
                forwarded.append(scope["path"])
            await self._inner(scope, receive, send)

        async def aclose(self) -> None:
            await self._inner.aclose()

    monkeypatch.setattr(
        server_module, "build_e1_app", lambda settings: ObservedInner(original_inner(settings))
    )
    key = auth_fixture.rsa_key.__wrapped__()
    settings = AppSettings(
        policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
        mastermind_root=repository_root, macro_root_flag=str(macro_root),
        runtime_root=tmp_path / "runtime", environ={}, ceo_ingress_socket_path=None,
        read_only=True, jwks_cache=auth_fixture._FakeJwksCache(key),
        clock=lambda: auth_fixture.NOW,
    )
    app = server_module.build_e1_mcp_app(settings, audit_sink=Sink())
    read_headers = {
        "authorization": f"Bearer {auth_fixture._read_token(key)}",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18",
    }

    async def exercise() -> None:
        outer = app._app
        async with outer.router.lifespan_context(outer):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://e1.local"
            ) as client:
                for request_id, name, arguments in (
                    (1, "executive_state", {}),
                    (2, "executive_inbox", {}),
                    (3, "executive_job", {"job_id": job.job_id}),
                    (4, "ceo_intent_status", {"intent_id": intent["intent_id"]}),
                ):
                    response = await client.post(
                        "/mcp", headers=read_headers,
                        json={
                            "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                            "params": {"name": name, "arguments": arguments},
                        },
                    )
                    assert response.status_code == 200, response.text
                    assert response.json()["result"]["isError"] is False
                    envelope = json.loads(response.json()["result"]["content"][0]["text"])
                    assert envelope["ok"] is True
                    assert envelope["tool"] == name
                    assert envelope["data"] is not None
                for path in (
                    "/v1/tools/submit_ceo_intent",
                    "/v1/tools/submit_ceo_intent/reconcile",
                    "/mcp/submit_ceo_intent",
                ):
                    response = await client.post(path, headers=read_headers, json={"arguments": {}})
                    assert response.status_code == 404, (path, response.status_code, response.text)
                denied = await client.post(
                    "/mcp", headers=read_headers,
                    json={
                        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
                        "params": {"name": "submit_ceo_intent", "arguments": {}},
                    },
                )
                assert denied.status_code == 200, denied.text
                assert denied.json()["result"]["isError"] is True
                wider = await client.post(
                    "/mcp",
                    headers={
                        **read_headers,
                        "authorization": f"Bearer {auth_fixture._submit_token(key)}",
                    },
                    json={"jsonrpc": "2.0", "id": 6, "method": "tools/list"},
                )
                assert wider.status_code in (401, 403), wider.text

        # Exercise the direct, fixed E1 route table under the SAME writer
        # sentinels.  The outer router's own 404 cannot prove these inner
        # aliases stayed away from admission construction.
        direct = build_e1_app(settings)
        wider_headers = {
            **read_headers,
            "authorization": f"Bearer {auth_fixture._submit_token(key)}",
        }
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=direct), base_url="http://e1.internal"
        ) as client:
            accepted = await client.post(
                "/v1/tools/executive_state", headers=read_headers, json={"arguments": {}}
            )
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["ok"] is True
            widened_reader = await client.post(
                "/v1/tools/executive_state", headers=wider_headers, json={"arguments": {}}
            )
            assert widened_reader.status_code in (401, 403), widened_reader.text
            for headers in (read_headers, wider_headers):
                for method, path in (
                    ("POST", "/v1/tools/submit_ceo_intent"),
                    ("POST", "/v1/tools/submit_ceo_intent?alias=1"),
                    ("POST", "/v1/tools/submit_ceo_intent%2Freconcile"),
                    ("POST", "/v1/tools//submit_ceo_intent"),
                    ("GET", "/v1/tools/submit_ceo_intent"),
                ):
                    response = await client.request(
                        method, path, headers=headers, json={"arguments": {}}
                    )
                    assert response.status_code == 404, (method, path, response.text)

        with pytest.raises(ValueError, match="refuses an ingress socket path"):
            AppSettings(
                policies=settings.policies, mastermind_root=repository_root,
                macro_root_flag=str(macro_root), runtime_root=tmp_path / "runtime",
                environ={}, ceo_ingress_socket_path=tmp_path / "must-not-bind.sock",
                read_only=True, jwks_cache=settings.jwks_cache, clock=settings.clock,
            )

    asyncio.run(exercise())
    assert forwarded == [
        "/v1/tools/executive_state", "/v1/tools/executive_inbox",
        "/v1/tools/executive_job", "/v1/tools/ceo_intent_status",
    ]
    assert writer_touches == []


def test_real_e1_mcp_accepts_loopback_host_with_port_without_weakening_host_fence(tmp_path):
    """A normal local listener port must not force clients to omit Host ports."""

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    import httpx
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.executive_mcp.server import build_e1_mcp_app

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    key = auth_fixture.rsa_key.__wrapped__()
    app = build_e1_mcp_app(
        AppSettings(
            policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
            mastermind_root=tmp_path / "mastermind",
            macro_root_flag=str(tmp_path / "macro"),
            runtime_root=tmp_path / "runtime",
            environ={}, ceo_ingress_socket_path=None, read_only=True,
            jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
        ),
        audit_sink=Sink(),
    )
    headers = {
        "authorization": f"Bearer {auth_fixture._read_token(key)}",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18",
    }

    async def exercise() -> None:
        inner = app._app
        async with inner.router.lifespan_context(inner):
            for base_url in ("http://127.0.0.1:9911", "http://[::1]:9911"):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url=base_url
                ) as client:
                    accepted = await client.post(
                        "/mcp", headers=headers,
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    )
                    assert accepted.status_code == 200, (base_url, accepted.text)
                    hostile = await client.post(
                        "/mcp", headers={**headers, "host": "attacker.example.test:9911"},
                        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    )
                    assert hostile.status_code == 421

    asyncio.run(exercise())


def test_real_e1_mcp_call_handler_refuses_without_the_sdk_current_request(tmp_path, monkeypatch):
    """No ContextVar, cache, or service identity may replace the current Request."""

    import pytest
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from mcp.server.lowlevel import Server as RealServer
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    import integrations.executive_mcp.server as server_module

    handlers: list[Any] = []

    class CapturingServer(RealServer):
        def call_tool(self):
            decorate = super().call_tool()

            def capture(handler: Any) -> Any:
                handlers.append(handler)
                return decorate(handler)

            return capture

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    key = auth_fixture.rsa_key.__wrapped__()
    monkeypatch.setattr(server_module, "Server", CapturingServer)
    server_module.build_e1_mcp_app(
        AppSettings(
            policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
            mastermind_root=tmp_path / "mastermind",
            macro_root_flag=str(tmp_path / "macro"),
            runtime_root=tmp_path / "runtime",
            environ={}, ceo_ingress_socket_path=None, read_only=True,
            jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
        ),
        audit_sink=Sink(),
    )

    assert len(handlers) == 1
    with pytest.raises(ValueError, match="current MCP request is unavailable"):
        asyncio.run(handlers[0]("executive_state", {}))


def test_real_e1_mcp_uses_one_stateless_manager_and_one_lifespan_run(tmp_path, monkeypatch):
    """Composition must not allocate a session manager per request or lifespan."""

    from contextlib import asynccontextmanager

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager as RealManager
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    import integrations.executive_mcp.server as server_module

    created: list[tuple[Any, dict[str, Any]]] = []
    entered: list[Any] = []

    class CapturingManager(RealManager):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            created.append((args, dict(kwargs)))
            super().__init__(*args, **kwargs)

        @asynccontextmanager
        async def run(self):
            entered.append(self)
            async with super().run():
                yield

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    key = auth_fixture.rsa_key.__wrapped__()
    monkeypatch.setattr(server_module, "StreamableHTTPSessionManager", CapturingManager)
    app = server_module.build_e1_mcp_app(
        AppSettings(
            policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
            mastermind_root=tmp_path / "mastermind",
            macro_root_flag=str(tmp_path / "macro"),
            runtime_root=tmp_path / "runtime",
            environ={}, ceo_ingress_socket_path=None, read_only=True,
            jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
        ),
        audit_sink=Sink(),
    )

    assert len(created) == 1
    assert created[0][1]["stateless"] is True
    assert created[0][1]["json_response"] is True

    async def exercise() -> None:
        inner = app._app
        async with inner.router.lifespan_context(inner):
            assert len(entered) == 1

    asyncio.run(exercise())
    assert len(entered) == 1


def test_e1_outer_lifespan_closes_its_real_read_gateway_when_idle(tmp_path, monkeypatch):
    """The HTTP consumer owns and drains the gateway it created."""

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from integrations.mastermind_executive_app import app as app_module
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.executive_mcp.server import build_e1_mcp_app

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    captured: list[Any] = []
    original_builder = app_module.build_read_gateway

    def capture_gateway(*args: Any, **kwargs: Any) -> Any:
        gateway = original_builder(*args, **kwargs)
        captured.append(gateway)
        return gateway

    key = auth_fixture.rsa_key.__wrapped__()
    monkeypatch.setattr(app_module, "build_read_gateway", capture_gateway)
    app = build_e1_mcp_app(
        AppSettings(
            policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
            mastermind_root=tmp_path / "mastermind",
            macro_root_flag=str(tmp_path / "macro"),
            runtime_root=tmp_path / "runtime",
            environ={}, ceo_ingress_socket_path=None, read_only=True,
            jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
        ),
        audit_sink=Sink(),
    )
    assert len(captured) == 1
    gateway = captured[0]

    async def exercise() -> None:
        inner = app._app
        async with inner.router.lifespan_context(inner):
            assert gateway._closed is False

    asyncio.run(exercise())
    assert gateway._closed is True
    assert gateway._read_attempts == set()


def test_e1_outer_lifespan_reports_real_gateway_close_timeout_for_entered_reader(tmp_path, monkeypatch):
    """Closing HTTP truthfully preserves the accepted active-reader timeout law."""

    import httpx
    import pytest
    import threading
    import integrations.executive_mcp.adapter as adapter_module
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from integrations.executive_mcp.schemas import GatewayError
    from integrations.mastermind_executive_app import app as app_module
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.executive_mcp.server import build_e1_mcp_app

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    started = threading.Event()
    release = threading.Event()
    captured: list[Any] = []
    original_builder = app_module.build_read_gateway

    def capture_blocking_gateway(*args: Any, **kwargs: Any) -> Any:
        gateway = original_builder(*args, **kwargs)
        gateway._packet_builder = lambda **_ignored: {
            "schema": "mastermind.ceo_boot_packet.v1",
            "mastermind": {}, "macro": {}, "strategic_state": None,
            "next_recommended_act": None, "handoffs": [],
        }

        def blocking_inbox(**_ignored: Any) -> dict[str, Any]:
            started.set()
            if not release.wait(2):
                raise AssertionError("reader was not released")
            return {
                "grounding": {}, "degraded": [], "attention": [],
                "runtime_counts": {"jobs": {"total": 0}},
            }

        gateway._inbox_builder = blocking_inbox
        captured.append(gateway)
        return gateway

    key = auth_fixture.rsa_key.__wrapped__()
    monkeypatch.setattr(app_module, "build_read_gateway", capture_blocking_gateway)
    monkeypatch.setattr(adapter_module, "_CLOSE_TIMEOUT_SECONDS", 0.02)
    app = build_e1_mcp_app(
        AppSettings(
            policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
            mastermind_root=tmp_path / "mastermind",
            macro_root_flag=str(tmp_path / "macro"),
            runtime_root=tmp_path / "runtime",
            environ={}, ceo_ingress_socket_path=None, read_only=True,
            jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
        ),
        audit_sink=Sink(),
    )
    gateway = captured[0]

    async def exercise() -> None:
        inner = app._app
        lifespan = inner.router.lifespan_context(inner)
        await lifespan.__aenter__()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://e1.local"
            ) as client:
                response_task = asyncio.create_task(
                    client.post(
                        "/mcp",
                        headers={
                            "authorization": f"Bearer {auth_fixture._read_token(key)}",
                            "accept": "application/json, text/event-stream",
                            "mcp-protocol-version": "2025-06-18",
                        },
                        json={
                            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "executive_state", "arguments": {}},
                        },
                    )
                )
                assert await asyncio.to_thread(started.wait, 1)
                with pytest.raises(GatewayError) as excinfo:
                    await lifespan.__aexit__(None, None, None)
                assert excinfo.value.code == "timeout"
                refused = await gateway.call("executive_state", {})
                assert refused["error"]["code"] == "backend_unavailable"
                release.set()
                completed = await response_task
                assert completed.status_code == 500
                await gateway.aclose()
        finally:
            release.set()

    asyncio.run(exercise())


def test_real_e1_mcp_four_readers_keep_repo_macro_and_runtime_roots_distinct(tmp_path, monkeypatch):
    """Every E1 reader uses the explicit temporary runtime, never repo state."""

    import json
    import httpx
    from control_plane.ceo_intent import submit_intent
    from control_plane.executive_runtime import Runtime
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.executive_mcp.server import build_e1_mcp_app

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    repository_root = tmp_path / "mastermind"
    macro_root = tmp_path / "macro-explicit"
    env_macro_root = tmp_path / "macro-env-decoy"
    runtime_root = tmp_path / "runtime-explicit"
    repository_sha = auth_fixture._git_repo(repository_root, content="repository-root")
    macro_sha = ""
    for root, content in ((macro_root, "macro-explicit"), (env_macro_root, "macro-env-decoy")):
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "agentos.py").write_text("", encoding="utf-8")
        (root / "agentos").mkdir()
        sha = auth_fixture._git_repo(root, content=content)
        if root == macro_root:
            macro_sha = sha
    monkeypatch.setenv("MASTERMIND_MACRO_ROOT", str(env_macro_root))

    runtime = Runtime.at(runtime_root)
    job_a = runtime.jobs.create_job("temporary Job A", department="research", priority=1)
    intent_receipt = submit_intent(
        runtime,
        {
            "schema": "mastermind.ceo_intent.v1",
            "intent_id": "intent-a-e1",
            "actor": "ceo-sol",
            "objective": "Read the temporary E1 intent only.",
            "department": "research",
            "priority": 1,
            "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
            "execution_contract": {"requested_authorities": ["READ"]},
        },
    )
    repository_runtime = Runtime.at(repository_root)
    repository_runtime.jobs.create_job("repository decoy one", department="research", priority=1)
    repository_runtime.jobs.create_job("repository decoy two", department="research", priority=1)
    job_b = repository_runtime.jobs.create_job("repository Job B", department="research", priority=1)

    key = auth_fixture.rsa_key.__wrapped__()
    app = build_e1_mcp_app(
        AppSettings(
            policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
            mastermind_root=repository_root,
            macro_root_flag=str(macro_root),
            runtime_root=runtime_root,
            environ={}, ceo_ingress_socket_path=None, read_only=True,
            jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
        ),
        audit_sink=Sink(),
    )
    headers = {
        "authorization": f"Bearer {auth_fixture._read_token(key)}",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18",
    }

    async def exercise() -> dict[str, dict[str, Any]]:
        inner = app._app
        async with inner.router.lifespan_context(inner):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://e1.local"
            ) as client:
                initialized = await client.post(
                    "/mcp", headers=headers,
                    json={
                        "jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18", "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    },
                )
                assert initialized.status_code == 200

                async def call(request_id: int, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                    response = await client.post(
                        "/mcp", headers=headers,
                        json={
                            "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                            "params": {"name": name, "arguments": arguments},
                        },
                    )
                    assert response.status_code == 200, response.text
                    return json.loads(response.json()["result"]["content"][0]["text"])

                return {
                    "state": await call(2, "executive_state", {}),
                    "inbox": await call(3, "executive_inbox", {}),
                    "job_a": await call(4, "executive_job", {"job_id": job_a.job_id}),
                    "intent_a": await call(5, "ceo_intent_status", {"intent_id": intent_receipt["intent_id"]}),
                    "job_b": await call(6, "executive_job", {"job_id": job_b.job_id}),
                }

    results = asyncio.run(exercise())
    assert results["state"]["tool"] == "executive_state"
    assert results["state"]["data"]["mastermind"]["root"] == str(repository_root)
    assert results["state"]["data"]["mastermind"]["sha"] == repository_sha
    assert results["state"]["data"]["macro"] == {
        "root": str(macro_root),
        "sha": macro_sha,
        "resolved_via": "flag",
    }
    assert results["state"]["data"]["runtime_counts"]["jobs"]["total"] == 2
    assert results["inbox"]["tool"] == "executive_inbox"
    assert results["inbox"]["data"]["grounding"]["mastermind"]["root"] == str(repository_root)
    assert results["inbox"]["data"]["grounding"]["macro"]["root"] == str(macro_root)
    assert results["job_a"]["data"]["job"]["job_id"] == job_a.job_id
    assert results["intent_a"]["data"]["intent_id"] == intent_receipt["intent_id"]
    assert results["job_b"]["ok"] is False
    assert results["job_b"]["error"]["code"] == "not_found"


def test_real_e1_mcp_invalid_temporary_runtime_never_falls_back_or_creates_artifacts(tmp_path, monkeypatch):
    """Missing, husk, and foreign runtime roots stay explicit read failures."""

    import json
    import sqlite3
    import httpx
    from control_plane.ceo_intent import submit_intent
    from control_plane.executive_inbox import DB_RELATIVE_PATH
    from control_plane.executive_runtime import Runtime
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from integrations.mastermind_executive_app import app as app_module
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.executive_mcp.server import build_e1_mcp_app

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    repository_root = tmp_path / "repository-decoy"
    repository_runtime = Runtime.at(repository_root)
    repository_runtime.jobs.create_job("repository decoy one", department="research", priority=1)
    repository_job = repository_runtime.jobs.create_job("repository Job B", department="research", priority=1)
    repository_intent = submit_intent(
        repository_runtime,
        {
            "schema": "mastermind.ceo_intent.v1",
            "intent_id": "intent-decoy-b",
            "actor": "ceo-sol",
            "objective": "Repository-only decoy intent.",
            "department": "research",
            "priority": 1,
            "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
            "execution_contract": {"requested_authorities": ["READ"]},
        },
    )
    case_roots = {
        "missing": tmp_path / "runtime-missing",
        "husk": tmp_path / "runtime-husk",
        "foreign": tmp_path / "runtime-foreign",
    }
    husk_db = case_roots["husk"] / DB_RELATIVE_PATH
    husk_db.parent.mkdir(parents=True)
    husk_db.write_bytes(b"")
    foreign_db = case_roots["foreign"] / DB_RELATIVE_PATH
    foreign_db.parent.mkdir(parents=True)
    with sqlite3.connect(foreign_db) as connection:
        connection.execute("CREATE TABLE foreign_runtime_only (value TEXT)")
    before_bytes = {
        name: (root / DB_RELATIVE_PATH).read_bytes()
        for name, root in case_roots.items()
        if (root / DB_RELATIVE_PATH).is_file()
    }

    captured: list[Any] = []
    original_builder = app_module.build_read_gateway

    def capture_gateway(*args: Any, **kwargs: Any) -> Any:
        gateway = original_builder(*args, **kwargs)
        gateway._packet_builder = lambda **_ignored: {
            "schema": "mastermind.ceo_boot_packet.v1",
            "mastermind": {}, "macro": {}, "strategic_state": None,
            "next_recommended_act": None, "handoffs": [],
        }
        captured.append(gateway)
        return gateway

    key = auth_fixture.rsa_key.__wrapped__()
    monkeypatch.setattr(app_module, "build_read_gateway", capture_gateway)

    async def exercise_case(name: str, runtime_root: Path) -> None:
        app = build_e1_mcp_app(
            AppSettings(
                policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
                mastermind_root=repository_root,
                macro_root_flag=str(tmp_path / "macro"),
                runtime_root=runtime_root,
                environ={}, ceo_ingress_socket_path=None, read_only=True,
                jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
            ),
            audit_sink=Sink(),
        )
        assert captured[-1].config.runtime_root == runtime_root.resolve()
        headers = {
            "authorization": f"Bearer {auth_fixture._read_token(key)}",
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": "2025-06-18",
        }
        inner = app._app
        async with inner.router.lifespan_context(inner):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://e1.local"
            ) as client:
                async def call(request_id: int, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
                    response = await client.post(
                        "/mcp", headers=headers,
                        json={
                            "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                            "params": {"name": tool, "arguments": arguments},
                        },
                    )
                    assert response.status_code == 200, (name, tool, response.text)
                    return json.loads(response.json()["result"]["content"][0]["text"])

                state = await call(1, "executive_state", {})
                inbox = await call(2, "executive_inbox", {})
                job = await call(3, "executive_job", {"job_id": repository_job.job_id})
                intent = await call(4, "ceo_intent_status", {"intent_id": repository_intent["intent_id"]})
        for envelope in (state, inbox, job, intent):
            assert envelope["mode"] == "readonly", (name, envelope)
        for envelope in (state, inbox):
            assert envelope["ok"] is True, (name, envelope)
            assert envelope["data"]["runtime_counts"] is None, (name, envelope)
            assert envelope["degraded"], (name, envelope)
        for envelope in (job, intent):
            assert envelope["ok"] is False, (name, envelope)
            assert envelope["error"]["code"] == "backend_unavailable", (name, envelope)

    async def exercise() -> None:
        for name, root in case_roots.items():
            await exercise_case(name, root)

    asyncio.run(exercise())
    assert not (case_roots["missing"] / DB_RELATIVE_PATH).exists()
    for name, before in before_bytes.items():
        assert (case_roots[name] / DB_RELATIVE_PATH).read_bytes() == before


def test_real_e1_mcp_unreadable_temporary_runtime_preserves_mode_hash_and_artifacts(tmp_path, monkeypatch):
    """A controlled permission denial degrades E1 reads without touching its temp DB.

    The test does not depend on the host user being unable to read a chmod'd
    file (that is not portable for privileged CI).  It creates a non-database
    temporary artifact, records its mode/hash/tree, then injects the same
    ``PermissionError`` at ``Runtime.at`` that a real readonly open would
    surface.  No SQLite connection is opened by this simulation.
    """

    import hashlib
    import json
    import os
    import httpx
    from control_plane.executive_inbox import DB_RELATIVE_PATH
    from control_plane.executive_runtime import Runtime
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from integrations.mastermind_executive_app import app as app_module
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.executive_mcp.server import build_e1_mcp_app

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    runtime_root = tmp_path / "runtime-unreadable"
    database = runtime_root / DB_RELATIVE_PATH
    database.parent.mkdir(parents=True)
    database.write_bytes(b"temporary E1 permission simulation; not a SQLite database\n")
    database.chmod(0o400)
    before_mode = database.stat().st_mode & 0o777
    before_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    before_artifacts = sorted(
        str(path.relative_to(runtime_root))
        for path in runtime_root.rglob("*")
    )
    runtime_attempts: list[tuple[Path, bool]] = []

    def denied_runtime_at(
        _cls: type[Runtime], root: Path | str | None = None, *, create: bool = True, **_kwargs: Any
    ) -> Runtime:
        runtime_attempts.append((Path(root).resolve(), create))
        raise PermissionError("temporary E1 runtime permission denied")

    # The static boot packet isolates this test's named temporary-runtime
    # failure from unrelated Git/Agent-OS collection availability.
    original_builder = app_module.build_read_gateway

    def capture_gateway(*args: Any, **kwargs: Any) -> Any:
        gateway = original_builder(*args, **kwargs)
        gateway._packet_builder = lambda **_ignored: {
            "schema": "mastermind.ceo_boot_packet.v1",
            "mastermind": {}, "macro": {}, "strategic_state": None,
            "next_recommended_act": None, "handoffs": [],
        }
        return gateway

    monkeypatch.setattr(app_module, "build_read_gateway", capture_gateway)
    monkeypatch.setattr(Runtime, "at", classmethod(denied_runtime_at))
    key = auth_fixture.rsa_key.__wrapped__()
    app = build_e1_mcp_app(
        AppSettings(
            policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
            mastermind_root=tmp_path / "repository", macro_root_flag=str(tmp_path / "macro"),
            runtime_root=runtime_root, environ={}, ceo_ingress_socket_path=None,
            read_only=True, jwks_cache=auth_fixture._FakeJwksCache(key),
            clock=lambda: auth_fixture.NOW,
        ),
        audit_sink=Sink(),
    )
    headers = {
        "authorization": f"Bearer {auth_fixture._read_token(key)}",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18",
    }

    async def exercise() -> dict[str, dict[str, Any]]:
        outer = app._app
        async with outer.router.lifespan_context(outer):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://e1.local"
            ) as client:
                async def call(request_id: int, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                    response = await client.post(
                        "/mcp", headers=headers,
                        json={
                            "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                            "params": {"name": name, "arguments": arguments},
                        },
                    )
                    assert response.status_code == 200, response.text
                    return json.loads(response.json()["result"]["content"][0]["text"])

                return {
                    "state": await call(1, "executive_state", {}),
                    "inbox": await call(2, "executive_inbox", {}),
                    "job": await call(3, "executive_job", {"job_id": "JOB-0001"}),
                    "intent": await call(4, "ceo_intent_status", {"intent_id": "intent-e1-read"}),
                }

    results = asyncio.run(exercise())
    for name in ("state", "inbox"):
        assert results[name]["ok"] is True
        assert results[name]["data"]["runtime_counts"] is None
        assert any("permission denied" in note for note in results[name]["degraded"])
    for name in ("job", "intent"):
        assert results[name]["ok"] is False
        assert results[name]["error"]["code"] == "backend_unavailable"
    assert runtime_attempts == [(runtime_root.resolve(), False)] * 4
    assert database.stat().st_mode & 0o777 == before_mode
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before_hash
    assert sorted(str(path.relative_to(runtime_root)) for path in runtime_root.rglob("*")) == before_artifacts
    assert os.access(database, os.F_OK)


def test_real_e1_mcp_rechecks_derived_runtime_db_symlink_before_all_four_readers(tmp_path, monkeypatch):
    """A moved explicit runtime cannot turn any E1 reader into a production read."""

    import json
    import httpx
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from integrations.mastermind_executive_app import app as app_module
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.executive_mcp.server import build_e1_mcp_app

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    captured: list[Any] = []
    original_builder = app_module.build_read_gateway

    def capture_gateway(*args: Any, **kwargs: Any) -> Any:
        gateway = original_builder(*args, **kwargs)
        gateway._packet_builder = lambda **_ignored: (_ for _ in ()).throw(AssertionError("packet read"))
        gateway._inbox_builder = lambda **_ignored: (_ for _ in ()).throw(AssertionError("inbox read"))
        gateway._runtime_factory = lambda _root: (_ for _ in ()).throw(AssertionError("runtime read"))
        captured.append(gateway)
        return gateway

    safe_runtime = tmp_path / "safe-runtime"
    production_alias = tmp_path / "runtime-moved-to-production"
    production_alias.symlink_to("/var/db/mastermind-executive")
    key = auth_fixture.rsa_key.__wrapped__()
    monkeypatch.setattr(app_module, "build_read_gateway", capture_gateway)
    app = build_e1_mcp_app(
        AppSettings(
            policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
            mastermind_root=tmp_path / "repository",
            macro_root_flag=str(tmp_path / "macro"),
            runtime_root=safe_runtime,
            environ={}, ceo_ingress_socket_path=None, read_only=True,
            jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
        ),
        audit_sink=Sink(),
    )
    gateway = captured[0]
    object.__setattr__(gateway.config, "read_runtime_root", production_alias)
    headers = {
        "authorization": f"Bearer {auth_fixture._read_token(key)}",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18",
    }

    async def exercise() -> None:
        inner = app._app
        async with inner.router.lifespan_context(inner):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://e1.local"
            ) as client:
                for request_id, name, arguments, expected_code in (
                    (1, "executive_state", {}, "invalid_input"),
                    (2, "executive_inbox", {}, "invalid_input"),
                    (3, "executive_job", {"job_id": "JOB-0001"}, "backend_unavailable"),
                    (4, "ceo_intent_status", {"intent_id": "intent-a-e1"}, "backend_unavailable"),
                ):
                    response = await client.post(
                        "/mcp", headers=headers,
                        json={
                            "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                            "params": {"name": name, "arguments": arguments},
                        },
                    )
                    assert response.status_code == 200, response.text
                    envelope = json.loads(response.json()["result"]["content"][0]["text"])
                    assert envelope["ok"] is False
                    # Boot-packet readers reject the changed configuration;
                    # runtime-db readers translate the same non-readable root
                    # into their established unavailable boundary.  Neither
                    # route falls back or discloses the production path.
                    assert envelope["error"]["code"] == expected_code
                    assert "/var/db/mastermind-executive" not in envelope["error"]["message"]
                    assert "/private/var/db/mastermind-executive" not in envelope["error"]["message"]

    asyncio.run(exercise())
    assert not safe_runtime.exists()


def test_real_inner_e1_accepts_only_the_four_literal_post_paths(tmp_path):
    """Raw, query, encoded, slash, and method aliases are not E1 reader paths."""

    import httpx
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from integrations.executive_mcp.e1_http import build_e1_app
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies

    key = auth_fixture.rsa_key.__wrapped__()
    app = build_e1_app(
        AppSettings(
            policies=AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy()),
            mastermind_root=tmp_path / "mastermind",
            macro_root_flag=str(tmp_path / "macro"),
            runtime_root=tmp_path / "runtime",
            environ={}, ceo_ingress_socket_path=None, read_only=True,
            jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
        )
    )

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://e1.internal"
        ) as client:
            for method, path in (
                ("GET", "/v1/tools/executive_state"),
                ("POST", "/v1/tools/executive_state?alias=1"),
                ("POST", "/v1/tools/executive_state/"),
                ("POST", "/v1/tools/executive%5fstate"),
                ("POST", "/v1/tools/executive_state%2F"),
                ("POST", "/v1/tools/submit_ceo_intent"),
            ):
                response = await client.request(method, path, json={"arguments": {}})
                assert response.status_code == 404, (method, path, response.status_code, response.text)
                assert response.json()["error"]["code"] == "not_found"

    asyncio.run(exercise())


def test_real_e1_mcp_concurrent_current_request_bearers_are_isolated_across_manager_generations(tmp_path, monkeypatch):
    """A stale auth ContextVar or reused request must never select E1 identity."""

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    import httpx
    from integrations.business_mcp_auth.claims import subject_digest
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.lowlevel import Server as RealServer
    import integrations.executive_mcp.server as server_module

    class Sink:
        def emit(self, _event: Any) -> None:
            pass

    key = auth_fixture.rsa_key.__wrapped__()
    subject_a = auth_fixture.SUBJECT
    subject_b = "e1-test-subject-b"
    read_policy = auth_fixture._read_policy(
        allowed_subject_digests=[
            subject_digest(issuer=auth_fixture.ISSUER, subject=subject_a),
            subject_digest(issuer=auth_fixture.ISSUER, subject=subject_b),
        ]
    )
    settings = AppSettings(
        policies=AppPolicies(read=read_policy, submit=auth_fixture._submit_policy()),
        mastermind_root=tmp_path / "mastermind",
        macro_root_flag=str(tmp_path / "macro"),
        runtime_root=tmp_path / "runtime",
        environ={}, ceo_ingress_socket_path=None, read_only=True,
        jwks_cache=auth_fixture._FakeJwksCache(key), clock=lambda: auth_fixture.NOW,
    )
    bearer_a = f"Bearer {auth_fixture._read_token(key, sub=subject_a)}"
    bearer_b = f"Bearer {auth_fixture._read_token(key, sub=subject_b)}"
    forwarded_by_app: list[list[tuple[str, str]]] = []
    handler_contexts: list[object] = []
    original_inner = server_module.build_e1_app

    class CapturingServer(RealServer):
        def call_tool(self):
            decorate = super().call_tool()

            def capture(handler: Any) -> Any:
                async def observed_handler(name: str, arguments: dict[str, Any] | None) -> list[Any]:
                    handler_contexts.append(auth_context_var.get())
                    return await handler(name, arguments)

                return decorate(observed_handler)

            return capture

    def observe_inner(config: Any) -> Any:
        app = original_inner(config)
        observed: list[tuple[str, str]] = []
        forwarded_by_app.append(observed)

        async def observed_app(scope: Any, receive: Any, send: Any) -> None:
            if scope.get("path", "").startswith("/v1/tools/"):
                observed.extend(
                    (scope["path"], value.decode("ascii"))
                    for key, value in scope["headers"]
                    if key.lower() == b"authorization"
                )
                await asyncio.sleep(0)
            await app(scope, receive, send)

        observed_app.aclose = app.aclose
        return observed_app

    monkeypatch.setattr(server_module, "build_e1_app", observe_inner)
    monkeypatch.setattr(server_module, "Server", CapturingServer)

    async def call_pair(app: Any) -> None:
        inner = app._app
        headers = {
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": "2025-06-18",
        }
        async with inner.router.lifespan_context(inner):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://e1.local"
            ) as client:
                initialized = await client.post(
                    "/mcp",
                    headers={**headers, "authorization": bearer_a},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    },
                )
                assert initialized.status_code == 200

                async def call_reader(request_id: int, name: str, bearer: str) -> None:
                    response = await client.post(
                        "/mcp",
                        headers={**headers, "authorization": bearer},
                        json={
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "tools/call",
                            "params": {"name": name, "arguments": {}},
                        },
                    )
                    assert response.status_code == 200, response.text
                    assert response.json()["result"]["content"][0]["type"] == "text"

                await asyncio.gather(
                    call_reader(2, "executive_state", bearer_a),
                    call_reader(3, "executive_inbox", bearer_b),
                )

    poisoned = object()
    poisoned_context = auth_context_var.set(poisoned)
    try:
        first_app = server_module.build_e1_mcp_app(settings, audit_sink=Sink())
        asyncio.run(call_pair(first_app))
        second_app = server_module.build_e1_mcp_app(settings, audit_sink=Sink())
        asyncio.run(call_pair(second_app))
    finally:
        auth_context_var.reset(poisoned_context)

    assert first_app is not second_app
    expected = {
        ("/v1/tools/executive_state", bearer_a),
        ("/v1/tools/executive_inbox", bearer_b),
    }
    assert [len(forwarded) for forwarded in forwarded_by_app] == [2, 2]
    assert [set(forwarded) for forwarded in forwarded_by_app] == [expected, expected]
    assert handler_contexts == [poisoned, poisoned, poisoned, poisoned]


def test_e1_cli_builds_read_only_app_and_dispatches_only_to_serve_boundary(tmp_path, monkeypatch):
    """Without the E1 branch this falls through to legacy stdio dispatch."""

    import dataclasses
    import json
    import scripts.executive_mcp as cli
    import integrations.executive_mcp.server as server_module
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "read": dataclasses.asdict(auth_fixture._read_policy()),
                "submit": dataclasses.asdict(auth_fixture._submit_policy()),
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}
    original_builder = server_module.build_e1_mcp_app

    def capture_real_builder(settings: Any, *, audit_sink: Any) -> Any:
        captured["settings"] = settings
        return original_builder(settings, audit_sink=audit_sink)

    async def reject_legacy_stdio(_gateway: Any) -> None:
        raise AssertionError("legacy stdio dispatch")

    monkeypatch.setattr(server_module, "build_e1_mcp_app", capture_real_builder)
    monkeypatch.setattr(
        cli,
        "_serve_e1",
        lambda app, host, port: captured.update(app=app, host=host, port=port) or 17,
        raising=False,
    )
    monkeypatch.setattr(server_module, "run_stdio", reject_legacy_stdio)

    result = cli.main(["--profile", "e1-read", "--mode", "readonly", "--policy", str(policy), "--repo-root", str(tmp_path / "repo"), "--macro-root", str(tmp_path / "macro"), "--read-runtime-root", str(tmp_path / "runtime"), "--host", "localhost", "--port", "9123"])

    assert result == 17
    assert captured["host"] == "localhost" and captured["port"] == 9123
    assert captured["settings"].read_only is True
    assert captured["settings"].policies.read.policy_id == "bsc-e1-test-read"


def test_e1_cli_refuses_production_coordinate_aliases_before_policy_io_or_composition(tmp_path, monkeypatch, capsys):
    """E1 startup never reads a policy or builds a gateway for an installed root."""

    import scripts.executive_mcp as cli
    import integrations.executive_mcp.server as server_module

    production_link = tmp_path / "production-runtime-link"
    production_link.symlink_to("/var/db/mastermind-executive")
    coordinate_aliases = (
        "/var/db/mastermind-executive/missing-leaf",
        "/private/var/db/mastermind-executive/missing-leaf",
        "/tmp/../var/db/mastermind-executive/missing-leaf",
        str(production_link / "missing-leaf"),
    )
    read_calls: list[Path] = []
    built: list[object] = []

    def forbidden_read(path: Path, *_args: Any, **_kwargs: Any) -> str:
        read_calls.append(path)
        raise AssertionError("policy IO must not occur")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    monkeypatch.setattr(
        server_module,
        "build_e1_mcp_app",
        lambda *_args, **_kwargs: built.append(object()) or object(),
    )
    base = {
        "--policy": str(tmp_path / "safe-policy.json"),
        "--repo-root": str(tmp_path / "safe-repo"),
        "--macro-root": str(tmp_path / "safe-macro"),
        "--read-runtime-root": str(tmp_path / "safe-runtime"),
    }
    flag_by_field = {
        "policy": "--policy",
        "repo": "--repo-root",
        "macro": "--macro-root",
        "runtime": "--read-runtime-root",
    }

    for field, flag in flag_by_field.items():
        for alias in coordinate_aliases:
            values = dict(base)
            values[flag] = alias
            argv = ["--profile", "e1-read", "--mode", "readonly"]
            for item in ("--policy", "--repo-root", "--macro-root", "--read-runtime-root"):
                argv.extend((item, values[item]))
            argv.extend(("--port", "9123"))
            assert cli.main(argv) == 2, (field, alias)
            assert capsys.readouterr().err.startswith("executive-mcp: invalid_input:")

    assert read_calls == []
    assert built == []


def test_e1_cli_describe_is_sdk_free_and_pins_the_advertised_profile(tmp_path, monkeypatch, capsys):
    """Describe must not load policy, build an app, or import a serving SDK."""

    import builtins
    import json
    import scripts.executive_mcp as cli

    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "mcp" or name.startswith("mcp.") or name in {
            "uvicorn",
            "integrations.executive_mcp.server",
            "integrations.mastermind_executive_app.app",
            "integrations.mastermind_executive_app.gateway",
        }:
            raise AssertionError(f"describe imported forbidden dependency {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("describe read policy")),
    )
    assert cli.main([
        "--profile", "e1-read", "--mode", "readonly", "--describe",
        "--policy", str(tmp_path / "unread-policy.json"),
        "--repo-root", str(tmp_path / "repo"),
        "--macro-root", str(tmp_path / "macro"),
        "--read-runtime-root", str(tmp_path / "runtime"),
        "--port", "9123",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "profile": "e1-read",
        "tools": ["executive_state", "executive_inbox", "executive_job", "ceo_intent_status"],
        "snapshot_sha256": "c2dd209218852fe08d87de4c3b3da7f3ae41c1e1724f7fb8e1250a901e15aa6f",
    }


def test_e1_cli_accepts_all_loopback_forms_and_refuses_invalid_ports(tmp_path, capsys):
    """Only a usable port and the reviewed loopback host vocabulary reach serve."""

    import scripts.executive_mcp as cli

    required = [
        "--profile", "e1-read", "--mode", "readonly", "--describe",
        "--policy", str(tmp_path / "policy.json"),
        "--repo-root", str(tmp_path / "repo"),
        "--macro-root", str(tmp_path / "macro"),
        "--read-runtime-root", str(tmp_path / "runtime"),
    ]
    for host in ("127.0.0.1", "localhost", "::1"):
        assert cli.main([*required, "--host", host, "--port", "9123"]) == 0
        capsys.readouterr()
    for port in ("0", "-1", "65536"):
        assert cli.main([*required, "--port", port]) == 2
        assert capsys.readouterr().err.startswith("executive-mcp: invalid_input:")


def test_read_only_app_settings_refuse_production_root_aliases_directly(tmp_path):
    """Direct E1 composition cannot bypass the CLI's configuration fence."""

    import pytest
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import test_mastermind_executive_app_asgi as auth_fixture
    finally:
        sys.path.pop(0)
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies

    production_link = tmp_path / "production-system-link"
    production_link.symlink_to("/Library/Application Support/MastermindExecutive")
    aliases = (
        "/var/db/mastermind-executive/missing-leaf",
        "/private/var/db/mastermind-executive/missing-leaf",
        "/tmp/../var/db/mastermind-executive/missing-leaf",
        str(production_link / "missing-leaf"),
    )
    policies = AppPolicies(read=auth_fixture._read_policy(), submit=auth_fixture._submit_policy())
    for field in ("mastermind_root", "macro_root_flag", "runtime_root"):
        for alias in aliases:
            values: dict[str, Path | str] = {
                "mastermind_root": tmp_path / "safe-repo",
                "macro_root_flag": str(tmp_path / "safe-macro"),
                "runtime_root": tmp_path / "safe-runtime",
            }
            values[field] = alias
            with pytest.raises(ValueError, match="refuses production configuration"):
                AppSettings(
                    policies=policies,
                    mastermind_root=values["mastermind_root"],
                    macro_root_flag=str(values["macro_root_flag"]),
                    runtime_root=values["runtime_root"],
                    environ={}, ceo_ingress_socket_path=None, read_only=True,
                )


def test_legacy_cli_describe_keeps_its_original_snapshot_payload(capsys):
    """The E1 selector must not add even a profile field to legacy describe."""

    import json
    import scripts.executive_mcp as cli
    from integrations.executive_mcp.schemas import SCHEMA_SNAPSHOT_SHA256, schema_snapshot, schema_snapshot_sha256

    assert cli.main(["--mode", "readonly", "--describe"]) == 0
    actual = json.loads(capsys.readouterr().out)
    expected = schema_snapshot()
    expected["snapshot_sha256"] = schema_snapshot_sha256()
    expected["pinned_snapshot_sha256"] = SCHEMA_SNAPSHOT_SHA256
    expected["mode"] = "readonly"
    assert actual == expected
