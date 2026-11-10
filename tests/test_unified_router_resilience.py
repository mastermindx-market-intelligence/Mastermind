"""Fault-injection tests: no real provider, credential or live service calls."""
from __future__ import annotations

import asyncio
import base64
import fcntl
import json
import socket
import sys
import time
import threading
from dataclasses import replace
from email.utils import formatdate
from contextlib import asynccontextmanager
from functools import wraps
from unittest.mock import MagicMock

import httpx
import pytest
from starlette.requests import Request

from ops.native_fabric.unified_router.gateway import Settings, create_app
from ops.native_fabric.unified_router.routes import (
    Route, RouteState, affinity_route, retry_after_seconds, select_route)
from ops.native_fabric.unified_router.streaming import SSEDecoder
from ops.native_fabric.unified_router.wire import (
    OpenAIStreamTranslator, ResponsesStreamTranslator, WireTranslationError)
from ops.native_fabric.unified_router import codex_oauth
from ops.native_fabric.unified_router import gateway

TOKEN = "offline-router-token-32-characters"
HEADERS = {"authorization": "Bearer " + TOKEN}


def async_test(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return run


def route(name="a", **kwargs):
    return Route(route_id=name, kind="gateway", wire="anthropic",
                 base_url="https://upstream.example", models=("m",),
                 gateway_token_env="OFFLINE_GATEWAY_TOKEN", **kwargs)


def config(tmp_path, **kwargs):
    values = dict(proxy_token=TOKEN, state_dir=tmp_path, routes=(route(),),
                  auth_store=tmp_path / "auth.json")
    values.update(kwargs)
    return Settings(**values)


@asynccontextmanager
async def client(app):
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://proxy") as session:
            yield session


def body(**extra):
    return dict(model="m", max_tokens=16,
                messages=[{"role": "user", "content": "offline probe"}], **extra)


@async_test
async def test_status_uses_the_same_clock_as_cooldown(tmp_path):
    app = create_app(config(tmp_path))
    app.state.router_state.routes.record_failure("a", "http_429", now=time.monotonic())
    async with client(app) as session:
        status = (await session.get("/statusz", headers=HEADERS)).json()
    assert status["routes"][0]["cooling"] is True


@async_test
async def test_http_failure_never_counts_as_success(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    app = create_app(config(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(503, json={"error": "overloaded"})))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS, json=body())
    assert response.status_code == 503
    assert app.state.router_state.served == 0
    assert app.state.router_state.failed == 1


@async_test
async def test_openai_eof_cannot_fabricate_success(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    item = Route(route_id="a", kind="gateway", wire="openai", models=("m",),
                 base_url="https://upstream.example", gateway_token_env="OFFLINE_GATEWAY_TOKEN")
    app = create_app(config(tmp_path, routes=(item,)), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, content=b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
                                  headers={"content-type": "text/event-stream"})))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS, json=body(stream=True))
    assert "message_stop" not in response.text
    assert "FABRIC_STREAM_INCOMPLETE" in response.text
    assert app.state.router_state.served == 0


@async_test
async def test_oauth_5xx_never_replays_under_another_account(tmp_path):
    (tmp_path / "auth.json").write_text(json.dumps({"credential_pool": {"p": [
        {"id": "one", "label": "one", "access_token": "fixture-one", "refresh_token": "r1"},
        {"id": "two", "label": "two", "access_token": "fixture-two", "refresh_token": "r2"}]}}))
    item = Route(route_id="oauth", kind="oauth_pool", wire="responses", models=("m",),
                 base_url="https://upstream.example", pool="p")
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(503, json={"error": "ambiguous failure"})

    app = create_app(config(tmp_path, routes=(item,)), transport=httpx.MockTransport(handler))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS, json=body())
    assert response.status_code == 503
    assert len(calls) == 1


class CloseTrackedStream(httpx.AsyncByteStream):
    def __init__(self):
        self.closes = 0

    async def __aiter__(self):
        yield b'event: message_start\ndata: {"type":"message_start"}\n\n'
        await asyncio.Event().wait()

    async def aclose(self):
        self.closes += 1


async def direct_response(app):
    async def receive():
        return {"type": "http.request", "body": json.dumps(body(stream=True)).encode(),
                "more_body": False}
    scope = {"type": "http", "asgi": {"spec_version": "2.4"}, "method": "POST",
             "path": "/v1/messages", "scheme": "http", "query_string": b"",
             "server": ("proxy", 80), "client": ("127.0.0.1", 50000),
             "headers": [(b"authorization", HEADERS["authorization"].encode())]}
    endpoint = next(r.endpoint for r in app.routes if r.path == "/v1/messages")
    response = await endpoint(Request(scope, receive))
    return response, scope, receive


@async_test
async def test_cancelled_iterator_closes_upstream(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    stream = CloseTrackedStream()
    app = create_app(config(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})))
    async with app.router.lifespan_context(app):
        response, _, _ = await direct_response(app)
        await anext(response.body_iterator)
        await response.body_iterator.aclose()
    assert stream.closes == 1
    assert app.state.router_state.served == 0
    assert app.state.router_state.in_flight == 0
    assert app.state.router_state.cancelled == 1


@async_test
async def test_disconnect_before_generator_start_closes_upstream(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    stream = CloseTrackedStream()
    app = create_app(config(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})))
    async with app.router.lifespan_context(app):
        response, scope, receive = await direct_response(app)

        async def disconnected_send(message):
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await response(scope, receive, disconnected_send)
    assert stream.closes == 1
    assert app.state.router_state.served == 0
    assert app.state.router_state.in_flight == 0
    assert app.state.router_state.cancelled == 1


def test_half_open_admits_one_probe_and_release_is_idempotent():
    state = RouteState()
    state.record_failure("a", "http_503", now=100, cooldown_s=1)
    now = state.cooldown_until["a"] + .1
    permit = state.acquire(route(), now=now)
    assert permit is not None and permit.probe
    assert state.circuit("a", now) == "half_open"
    assert state.acquire(route(), now=now) is None
    state.release(permit)
    state.release(permit)
    assert state.in_flight["a"] == 0
    assert state.circuit("a", now) == "probe_ready"
    assert state.acquire(route(), now=now) is not None


def test_old_success_and_failure_cannot_mutate_new_circuit_generation():
    state = RouteState()
    old_a = state.acquire(route(), now=100)
    old_b = state.acquire(route(), now=100)
    state.record_failure("a", "http_503", now=101, generation=old_b.generation)
    deadline = state.cooldown_until["a"]
    state.record_success("a", generation=old_a.generation)
    assert state.cooldown_until["a"] == deadline
    state.release(old_a)
    state.release(old_b)
    probe = state.acquire(route(), now=deadline + 1)
    state.record_success("a", generation=probe.generation)
    state.release(probe)
    state.record_failure("a", "late_failure", now=deadline + 2, generation=old_a.generation)
    assert state.circuit("a", deadline + 3) == "closed"
    assert state.in_flight["a"] == 0


def test_explicit_shared_group_is_not_multiplied_across_routes():
    state = RouteState()
    a = route("a", concurrency_group="account", group_max_in_flight=1)
    b = route("b", concurrency_group="account", group_max_in_flight=1)
    fallback = route("c", priority=200)
    permit = state.acquire(a, now=100)
    assert state.acquire(b, now=100) is None
    selected, _ = select_route([a, b, fallback], "m", state=state, now=100)
    assert selected == fallback
    state.release(permit)
    assert state.acquire(b, now=100) is not None


def test_affinity_yields_to_load_and_ignores_zero_weight():
    state = RouteState()
    a, b = route("a"), route("b")
    first, _ = select_route([a, b], "m", state=state, now=100, affinity_key="session")
    state.acquire(first, now=100)
    second, _ = select_route([a, b], "m", state=state, now=100, affinity_key="session")
    assert first != second
    selected, _ = select_route([replace(a, weight=0), b], "m", state=RouteState(),
                               now=100, affinity_key="session")
    assert selected == b


def test_rendezvous_only_remaps_callers_whose_route_disappeared():
    for index in range(100):
        key = f"session-{index}"
        before = affinity_route(["a", "b", "c"], key)
        after = affinity_route(["c", "a"], key)
        if before != "b":
            assert after == before


@pytest.mark.parametrize("value", ["NaN", "inf", "-inf", "bad-date"])
def test_invalid_retry_after_is_not_a_deadline(value):
    assert retry_after_seconds(value, wall_now=100) is None


def test_retry_after_date_and_monotonic_deadline_never_retry_early():
    assert retry_after_seconds("120", wall_now=100) == 120
    assert retry_after_seconds(formatdate(250, usegmt=True), wall_now=100) == 150
    state = RouteState()
    state.record_failure("a", "http_429", now=10, retry_after_s=7200)
    assert state.cooldown_until["a"] >= 7210
    previous = state.cooldown_until["a"]
    state.record_failure("a", "http_503", now=20, cooldown_s=1)
    assert state.cooldown_until["a"] >= previous


@pytest.mark.parametrize("kwargs", [{"weight": float("nan")}, {"weight": float("inf")},
                                    {"max_in_flight": -1}, {"max_in_flight": True},
                                    {"concurrency_group": "x"}])
def test_invalid_route_limits_refuse_configuration(kwargs):
    with pytest.raises(ValueError):
        route(**kwargs)


def test_conflicting_group_ceilings_refuse_configuration(tmp_path):
    with pytest.raises(ValueError, match="ceilings"):
        config(tmp_path, routes=(route("a", concurrency_group="x", group_max_in_flight=1),
                                  route("b", concurrency_group="x", group_max_in_flight=2)))


@async_test
async def test_global_bulkhead_refuses_before_another_upstream_send(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def handler(req):
        calls.append(req)
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"id": "m", "content": []})

    app = create_app(config(tmp_path, max_in_flight=1), transport=httpx.MockTransport(handler))
    async with client(app) as session:
        first = asyncio.create_task(session.post("/v1/messages", headers=HEADERS, json=body()))
        await asyncio.wait_for(entered.wait(), 1)
        try:
            second = await asyncio.wait_for(session.post("/v1/messages", headers=HEADERS,
                                                         json=body()), 1)
            assert second.status_code == 503
            assert second.json()["error"]["code"] == "FABRIC_ROUTER_BUSY"
            assert len(calls) == 1
            status = (await session.get("/statusz", headers=HEADERS)).json()
            assert status["in_flight"] == 1
        finally:
            release.set()
            await first
    assert app.state.router_state.in_flight == 0
    assert app.state.router_state.served == 1


@async_test
async def test_headers_are_not_success_while_body_is_unfinished(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    stream = CloseTrackedStream()
    app = create_app(config(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})))
    async with app.router.lifespan_context(app):
        response, _, _ = await direct_response(app)
        assert app.state.router_state.served == 0
        assert app.state.router_state.in_flight == 1
        await response.lifecycle.close()
        await response.lifecycle.close()
    assert app.state.router_state.in_flight == 0
    assert stream.closes == 1


@async_test
async def test_anthropic_terminal_error_is_failed_and_never_replayed(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, content=b'event: error\ndata: {"type":"error","error":{"type":"overloaded_error"}}\n\n',
                              headers={"content-type": "text/event-stream"})

    app = create_app(config(tmp_path), transport=httpx.MockTransport(handler))
    async with client(app) as session:
        reply = await session.post("/v1/messages", headers=HEADERS, json=body(stream=True))
    assert "FABRIC_UPSTREAM_STREAM_ERROR" in reply.text and "message_stop" not in reply.text
    assert len(calls) == 1
    assert app.state.router_state.served == 0
    assert app.state.router_state.failed == 1


@async_test
async def test_keepalives_cannot_evade_total_deadline(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")

    class Heartbeats(CloseTrackedStream):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(.005)
                yield b": keepalive\n\n"

    stream = Heartbeats()
    app = create_app(config(tmp_path, request_timeout_s=.025), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})))
    async with client(app) as session:
        reply = await asyncio.wait_for(session.post("/v1/messages", headers=HEADERS,
                                                    json=body(stream=True)), 1)
    assert "FABRIC_UPSTREAM_EFFECT_UNKNOWN" in reply.text
    assert "message_stop" not in reply.text
    assert stream.closes == 1 and app.state.router_state.in_flight == 0


def test_sse_split_utf8_crlf_multiline_and_bounded_unterminated_event():
    raw = 'event: content\r\ndata: {"text":\r\ndata: "你好"}\r\n\r\n'.encode()
    decoder = SSEDecoder(256)
    output = []
    for byte in raw:
        output.extend(decoder.feed(bytes([byte])))
    decoder.finish()
    assert output == [("content", '{"text":\n"你好"}')]
    with pytest.raises(WireTranslationError, match="TOO_LARGE"):
        SSEDecoder(10).feed(b"data: " + b"x" * 20)


@pytest.mark.parametrize("terminal", ["response.failed", "error"])
def test_responses_failures_do_not_complete(terminal):
    translator = ResponsesStreamTranslator(model="m")
    with pytest.raises(WireTranslationError):
        translator.feed({"type": terminal})
    with pytest.raises(WireTranslationError, match="INCOMPLETE"):
        translator.to_message()


def test_responses_item_id_retains_tool_arguments():
    translator = ResponsesStreamTranslator(model="m")
    translator.feed({"type": "response.output_item.added", "item": {
        "type": "function_call", "id": "item-1", "call_id": "call-1", "name": "read_file"}})
    translator.feed({"type": "response.function_call_arguments.delta",
                     "item_id": "item-1", "delta": '{"path":"x"}'})
    translator.feed({"type": "response.completed", "response": {"status": "completed"}})
    assert translator.to_message()["content"][0]["input"] == {"path": "x"}


def test_responses_incomplete_is_explicit_max_tokens():
    translator = ResponsesStreamTranslator(model="m")
    translator.feed({"type": "response.incomplete", "response": {
        "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}})
    assert translator.to_message()["stop_reason"] == "max_tokens"


@async_test
async def test_transport_failure_releases_local_permit_without_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    calls = []

    def handler(req):
        calls.append(req)
        raise httpx.ReadError("fixture connection lost", request=req)

    app = create_app(config(tmp_path), transport=httpx.MockTransport(handler))
    async with client(app) as session:
        reply = await session.post("/v1/messages", headers=HEADERS, json=body())
    assert reply.status_code == 502 and len(calls) == 1
    assert app.state.router_state.in_flight == 0
    assert app.state.router_state.served == 0


@async_test
async def test_count_tokens_uses_an_eligible_anthropic_route(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    a = replace(route("a", priority=10), wire="openai")
    b = route("b", priority=20)
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"input_tokens": 4})

    app = create_app(config(tmp_path, routes=(a, b)), transport=httpx.MockTransport(handler))
    async with client(app) as session:
        reply = await session.post("/v1/messages/count_tokens", headers=HEADERS, json=body())
    assert reply.status_code == 200 and reply.headers["x-fabric-route"] == "b"
    assert len(seen) == 1 and seen[0].url.path.endswith("count_tokens")


def test_tool_only_stream_starts_at_content_block_zero():
    translator = OpenAIStreamTranslator(model="m")
    translator.feed({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call",
        "function": {"name": "f", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}]})
    events = translator.finish()
    starts = [json.loads(data) for kind, data in events if kind == "content_block_start"]
    assert starts[0]["index"] == 0


@pytest.mark.parametrize("content", [b'{"type":"error","error":{}}', b'{"id":', b'{"other":true}'])
@async_test
async def test_nonstream_invalid_200_never_heals_probe(tmp_path, monkeypatch, content):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    app = create_app(config(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, content=content)))
    state = app.state.router_state.routes
    state.record_failure("a", "previous_failure", now=time.monotonic()-100)
    async with client(app) as session:
        reply = await session.post("/v1/messages", headers=HEADERS, json=body())
    assert reply.status_code == 502
    assert app.state.router_state.served == 0
    assert state.consecutive_failures["a"] == 2


def oauth_store(tmp_path, **extra):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"credential_pool": {"p": [dict(
        id="one", label="one", access_token="fixture", refresh_token="r1", **extra)]}}))
    return path


def test_account_bench_never_shortens_under_locked_readback(tmp_path):
    path = oauth_store(tmp_path)
    deadline = time.time()+7200
    codex_oauth.bench_row(path, "p", "one", reset_at=deadline, reason="http_429")
    codex_oauth.bench_row(path, "p", "one", reset_at=time.time()+30, reason="http_429")
    assert codex_oauth.read_accounts(path, "p")[0].exhausted_until == deadline


@pytest.mark.parametrize("peer", [False, True])
def test_refresh_preserves_concurrent_quota_hold(tmp_path, peer):
    from unittest.mock import MagicMock
    path = oauth_store(tmp_path)
    original = codex_oauth.read_accounts(path, "p")[0]
    deadline = time.time()+7200
    codex_oauth.bench_row(path, "p", "one", reset_at=deadline, reason="http_429")
    if peer:
        doc = json.loads(path.read_text())
        doc["credential_pool"]["p"][0]["refresh_token"] = "r2"
        path.write_text(json.dumps(doc))
    response = MagicMock(status_code=200)
    response.json.return_value = {"access_token": "new-access", "refresh_token": "r2"}
    client = MagicMock()
    client.post.return_value = response
    updated = codex_oauth.refresh_account(path, "p", original, token_url="https://auth.example/token",
                                          client_id="fixture", client=client)
    assert updated.exhausted and updated.exhausted_until == deadline
    assert codex_oauth.read_accounts(path, "p")[0].exhausted_until == deadline
    assert client.post.call_count == 0


@pytest.mark.parametrize("reset", [None, float("nan"), "unknown"])
def test_exhaustion_without_verified_reset_stays_unavailable(tmp_path, reset):
    path = oauth_store(tmp_path, last_status="exhausted", last_error_reset_at=reset)
    account = codex_oauth.read_accounts(path, "p")[0]
    assert account.exhausted and account.exhausted_unknown


@pytest.mark.parametrize("removed", ["refresh_token", "access_token"])
def test_refresh_cannot_restore_credentials_removed_by_owner(tmp_path, removed):
    path = oauth_store(tmp_path)
    original = codex_oauth.read_accounts(path, "p")[0]
    doc = json.loads(path.read_text())
    del doc["credential_pool"]["p"][0][removed]
    path.write_text(json.dumps(doc))
    token_client = MagicMock()
    with pytest.raises(codex_oauth.OAuthPoolError, match="removed"):
        codex_oauth.refresh_account(path, "p", original, token_url="https://auth.example/token",
                                   client_id="fixture", client=token_client)
    token_client.post.assert_not_called()
    assert removed not in json.loads(path.read_text())["credential_pool"]["p"][0]


def test_atomic_auth_write_keeps_old_document_on_replace_failure(tmp_path, monkeypatch):
    path = oauth_store(tmp_path)
    old = path.read_bytes()

    def fail_replace(*args):
        raise OSError("fixture replace failure")

    monkeypatch.setattr(codex_oauth.os, "replace", fail_replace)
    with pytest.raises(OSError):
        codex_oauth.bench_row(path, "p", "one", reset_at=time.time()+30, reason="http_429")
    assert path.read_bytes() == old
    assert not list(tmp_path.glob(".auth-router-*"))


def test_auth_write_is_private_and_does_not_replace_symlink(tmp_path):
    path = oauth_store(tmp_path)
    codex_oauth.bench_row(path, "p", "one", reset_at=time.time()+30, reason="http_429")
    assert path.stat().st_mode & 0o777 == 0o600
    link = tmp_path / "linked-auth.json"
    link.symlink_to(path)
    with pytest.raises(codex_oauth.OAuthPoolError, match="regular file"):
        codex_oauth.bench_row(link, "p", "one", reset_at=time.time()+60, reason="http_429")
    assert link.is_symlink()


def expired_jwt():
    return "fixture." + base64.urlsafe_b64encode(b'{"exp":0}').decode().rstrip("=") + ".fixture"


def oauth_route():
    return Route(route_id="oauth", kind="oauth_pool", wire="responses", models=("m",),
                 base_url="https://upstream.example", pool="p")


@pytest.mark.parametrize("status", [401, 403])
@async_test
async def test_auth_refusal_never_refreshes_or_replays_inference(tmp_path, monkeypatch, status):
    oauth_store(tmp_path)
    token_client = MagicMock()
    monkeypatch.setattr(codex_oauth, "refresh_account", token_client)
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={"error": "fixture auth refusal"})

    app = create_app(config(tmp_path, routes=(oauth_route(),)), transport=httpx.MockTransport(handler))
    async with client(app) as session:
        reply = await session.post("/v1/messages", headers=HEADERS, json=body())
    assert reply.status_code == status and len(calls) == 1
    token_client.assert_not_called()
    assert app.state.router_state.served == 0


def test_unknown_incomplete_reason_never_leaves_translator_completed():
    translator = ResponsesStreamTranslator(model="m")
    with pytest.raises(WireTranslationError, match="INCOMPLETE"):
        translator.feed({"type": "response.incomplete", "response": {
            "status": "incomplete", "incomplete_details": {"reason": "unknown"}}})
    with pytest.raises(WireTranslationError, match="INCOMPLETE"):
        translator.to_message()


@async_test
async def test_expired_pool_refuses_without_refresh_and_adopts_owner_rotation(tmp_path, monkeypatch):
    path = oauth_store(tmp_path)
    doc = json.loads(path.read_text())
    doc["credential_pool"]["p"][0]["access_token"] = expired_jwt()
    path.write_text(json.dumps(doc))
    original = path.read_bytes()
    refresh = MagicMock(side_effect=AssertionError("router cannot refresh tokens"))
    monkeypatch.setattr(codex_oauth, "refresh_account", refresh)
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, content=b'data: {"type":"response.completed","response":{"status":"completed"}}\n\n',
                              headers={"content-type": "text/event-stream"})

    app = create_app(config(tmp_path, routes=(oauth_route(),)), transport=httpx.MockTransport(handler))
    async with client(app) as session:
        refused = await session.post("/v1/messages", headers=HEADERS, json=body())
        assert refused.status_code == 503
        assert refused.json()["error"]["code"] == "FABRIC_OAUTH_OWNER_REFRESH_REQUIRED"
        assert "retry-after" not in refused.headers
        assert calls == [] and path.read_bytes() == original
        assert app.state.router_state.routes.circuit("oauth", time.monotonic()) == "closed"
        # Simulate the incumbent owner completing a rotation; the router reads it live.
        doc["credential_pool"]["p"][0]["access_token"] = "owner-new-access"
        doc["credential_pool"]["p"][0]["refresh_token"] = "owner-new-refresh"
        path.write_text(json.dumps(doc))
        reply = await session.post("/v1/messages", headers=HEADERS, json=body())
    assert reply.status_code == 200 and len(calls) == 1
    assert calls[0].headers["authorization"] == "Bearer owner-new-access"
    refresh.assert_not_called()


@async_test
async def test_owner_held_preferred_route_uses_eligible_fallback_before_send(tmp_path, monkeypatch):
    oauth_store(tmp_path, last_status="dead")
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={"id": "m", "content": []})

    app = create_app(config(tmp_path, routes=(replace(oauth_route(), priority=10),
                                              route("fallback", priority=20))),
                     transport=httpx.MockTransport(handler))
    async with client(app) as session:
        reply = await session.post("/v1/messages", headers=HEADERS, json=body())
    assert reply.status_code == 200 and reply.headers["x-fabric-route"] == "fallback"
    assert len(calls) == 1 and calls[0].url.path == "/v1/messages"
    assert app.state.router_state.in_flight == 0


@async_test
async def test_pool_selection_skips_expired_account_before_send(tmp_path):
    path = oauth_store(tmp_path)
    doc = json.loads(path.read_text())
    row = doc["credential_pool"]["p"][0]
    row["access_token"] = expired_jwt()
    doc["credential_pool"]["p"].append(dict(id="two", label="two",
        access_token="eligible-token", refresh_token="r2"))
    path.write_text(json.dumps(doc))
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(503, json={"error": "fixture"})

    app = create_app(config(tmp_path, routes=(oauth_route(),)), transport=httpx.MockTransport(handler))
    async with client(app) as session:
        await session.post("/v1/messages", headers=HEADERS, json=body())
    assert len(calls) == 1 and calls[0].headers["authorization"] == "Bearer eligible-token"


def test_late_429_cannot_replace_owner_dead_state(tmp_path):
    path = oauth_store(tmp_path, last_status="dead", last_status_at=time.time())
    original = path.read_bytes()
    codex_oauth.bench_row(path, "p", "one", reset_at=time.time()+30, reason="http_429")
    assert path.read_bytes() == original
    assert codex_oauth.read_accounts(path, "p")[0].owner_held


def test_bench_timestamp_participates_in_incumbent_stale_write_merge(tmp_path):
    path = oauth_store(tmp_path)
    before = time.time()
    codex_oauth.bench_row(path, "p", "one", reset_at=before+30, reason="http_429")
    row = json.loads(path.read_text())["credential_pool"]["p"][0]
    assert before <= row["last_status_at"] <= time.time()


@async_test
async def test_slow_credential_admission_is_inside_global_bulkhead(tmp_path, monkeypatch):
    path = oauth_store(tmp_path)
    accounts = codex_oauth.read_accounts(path, "p")
    entered, release = threading.Event(), threading.Event()
    reads = []

    def slow_read(*args):
        reads.append(True)
        entered.set()
        assert release.wait(1)
        return accounts

    monkeypatch.setattr(codex_oauth, "read_accounts", slow_read)
    app = create_app(config(tmp_path, routes=(oauth_route(),), max_in_flight=1),
                     transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    async with client(app) as session:
        first = asyncio.create_task(session.post("/v1/messages", headers=HEADERS, json=body()))
        assert await asyncio.to_thread(entered.wait, 1)
        try:
            refused = await session.post("/v1/messages", headers=HEADERS, json=body())
            assert refused.status_code == 503 and len(reads) == 1
            assert refused.json()["error"]["code"] == "FABRIC_ROUTER_BUSY"
        finally:
            release.set()
            await first
    assert app.state.router_state.in_flight == 0


@async_test
async def test_slow_request_body_is_inside_global_bulkhead(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def upload():
        yield b'{"model":'
        started.set()
        await release.wait()
        yield b'"m","messages":[],"max_tokens":16}'

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "m", "content": []})

    app = create_app(config(tmp_path, max_in_flight=1), transport=httpx.MockTransport(handler))
    async with client(app) as session:
        first = asyncio.create_task(session.post("/v1/messages", headers=HEADERS, content=upload()))
        await asyncio.wait_for(started.wait(), 1)
        try:
            assert app.state.router_state.in_flight == 1
            second = await session.post("/v1/messages", headers=HEADERS, json=body())
            assert second.status_code == 503
            assert second.json()["error"]["code"] == "FABRIC_ROUTER_BUSY"
            assert not calls
        finally:
            release.set()
            await first
    assert len(calls) == 1
    assert app.state.router_state.in_flight == 0


@async_test
async def test_request_body_deadline_refuses_without_upstream_or_circuit_effect(tmp_path):
    async def upload():
        yield b'{"model":'
        await asyncio.Event().wait()

    calls = []
    app = create_app(config(tmp_path, request_body_timeout_s=.02), transport=httpx.MockTransport(
        lambda request: calls.append(request)))
    async with client(app) as session:
        reply = await asyncio.wait_for(session.post("/v1/messages", headers=HEADERS, content=upload()), 1)
    assert reply.status_code == 408
    assert reply.json()["error"]["code"] == "FABRIC_REQUEST_BODY_TIMEOUT"
    assert not calls
    assert app.state.router_state.in_flight == 0
    assert app.state.router_state.refused == 1
    assert app.state.router_state.routes.consecutive_failures == {}


@async_test
async def test_disconnected_upload_releases_global_slot_without_upstream(tmp_path):
    started = asyncio.Event()

    async def upload():
        yield b'{"model":'
        started.set()
        await asyncio.Event().wait()

    app = create_app(config(tmp_path))
    async with client(app) as session:
        task = asyncio.create_task(session.post("/v1/messages", headers=HEADERS, content=upload()))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert app.state.router_state.in_flight == 0
    assert app.state.router_state.cancelled == 1
    assert app.state.router_state.selected == 0
    assert app.state.router_state.routes.consecutive_failures == {}


@async_test
async def test_asgi_disconnect_during_upload_releases_global_slot(tmp_path):
    app = create_app(config(tmp_path))
    incoming = iter((
        {"type": "http.request", "body": b'{"model":', "more_body": True},
        {"type": "http.disconnect"},
    ))

    async def receive():
        return next(incoming)

    scope = {"type": "http", "method": "POST", "path": "/v1/messages",
             "scheme": "http", "query_string": b"", "server": ("proxy", 80),
             "client": ("127.0.0.1", 50000),
             "headers": [(b"authorization", HEADERS["authorization"].encode())]}
    endpoint = next(r.endpoint for r in app.routes if r.path == "/v1/messages")
    response = await endpoint(Request(scope, receive))
    assert response.status_code == 400
    assert json.loads(response.body)["error"]["code"] == "FABRIC_REQUEST_DISCONNECTED"
    assert app.state.router_state.in_flight == 0
    assert app.state.router_state.cancelled == 1
    assert app.state.router_state.selected == 0


@async_test
async def test_deeply_nested_body_is_a_bounded_caller_refusal(tmp_path):
    app = create_app(config(tmp_path))
    depth = sys.getrecursionlimit() + 100
    async with client(app) as session:
        reply = await session.post("/v1/messages", headers=HEADERS,
                                   content=b'[' * depth + b'0' + b']' * depth)
    assert reply.status_code == 400
    assert reply.json()["error"]["code"] == "FABRIC_INVALID_REQUEST"
    assert app.state.router_state.in_flight == 0
    assert app.state.router_state.selected == 0


def test_explicit_refresh_wait_is_bounded_and_cancellable(tmp_path):
    path = oauth_store(tmp_path)
    account = codex_oauth.read_accounts(path, "p")[0]
    token_client = MagicMock()
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(codex_oauth.OAuthPoolError, match="cancelled"):
        codex_oauth.refresh_account(path, "p", account, token_url="https://auth.example/token",
                                   client_id="fixture", client=token_client, cancelled=cancelled)
    with open(tmp_path / "auth.json.lock", "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        with pytest.raises(codex_oauth.OAuthPoolError, match="deadline"):
            codex_oauth.refresh_account(path, "p", account, token_url="https://auth.example/token",
                                       client_id="fixture", client=token_client,
                                       deadline=time.monotonic()+.02)
    token_client.post.assert_not_called()


@async_test
async def test_older_bench_write_completion_cannot_shorten_new_local_hold(tmp_path, monkeypatch):
    oauth_store(tmp_path)
    both_sent = asyncio.Event()
    first_bench, second_bench = threading.Event(), threading.Event()
    release_first, release_second = threading.Event(), threading.Event()
    calls = []

    async def handler(req):
        calls.append(req)
        index = len(calls)
        if index == 1:
            await both_sent.wait()
        else:
            both_sent.set()
            assert await asyncio.to_thread(first_bench.wait, 1)
        return httpx.Response(429, headers={"retry-after": "30" if index == 1 else "7200"})

    def delayed_bench(*args, reset_at, **kwargs):
        if reset_at-time.time() < 100:
            first_bench.set()
            assert release_first.wait(1)
        else:
            second_bench.set()
            assert release_second.wait(1)
        return reset_at

    monkeypatch.setattr(codex_oauth, "bench_row", delayed_bench)
    app = create_app(config(tmp_path, routes=(oauth_route(),)), transport=httpx.MockTransport(handler))
    async with client(app) as session:
        first = asyncio.create_task(session.post("/v1/messages", headers=HEADERS, json=body()))
        second = asyncio.create_task(session.post("/v1/messages", headers=HEADERS, json=body()))
        try:
            assert await asyncio.to_thread(second_bench.wait, 1)
            release_first.set()
            done, _ = await asyncio.wait((first, second), timeout=1, return_when=asyncio.FIRST_COMPLETED)
            assert len(done) == 1
            assert app.state.router_state.oauth_bench[("oauth", "one")]-time.time() > 7000
        finally:
            release_first.set()
            release_second.set()
            await asyncio.gather(first, second)
    assert len(calls) == 2 and app.state.router_state.in_flight == 0


def test_selection_evidence_explains_exclusions_without_reserving_capacity():
    from ops.native_fabric.unified_router.routes import decide_route
    state = RouteState(cooldown_until={"cool": 110}, probes={"probe"},
                       in_flight={"full": 1}, group_in_flight={"shared": 1})
    items = [route("drain", weight=0), route("cool"), route("probe"),
             route("full", max_in_flight=1),
             route("group", concurrency_group="shared", group_max_in_flight=1),
             route("fallback", priority=200),
             replace(route("other"), models=("other-model",))]
    result = decide_route(items, "m", state=state, now=100, affinity_key="private-session")
    assert result.route.route_id == "fallback" and result.reason == ""
    assert result.evidence["matched_routes"] == 6
    assert result.evidence["excluded"] == {
        "drained": 1, "circuit_open": 1, "probe_occupied": 1,
        "route_limit": 1, "group_limit": 1}
    assert result.evidence["eligible_routes"] == 1
    assert result.evidence["selected_priority"] == 200
    assert result.evidence["tie_break"] == "single_route_in_tier"
    assert state.in_flight == {"full": 1} and state.probes == {"probe"}
    assert "private-session" not in json.dumps(result.evidence)


def test_selection_evidence_does_not_draw_an_extra_random_choice(monkeypatch):
    from ops.native_fabric.unified_router import routes as route_module
    draws = []

    def draw():
        draws.append(True)
        return .75

    monkeypatch.setattr(route_module.random, "random", draw)
    items = [route("a"), route("b", weight=3)]
    result = route_module.decide_route(items, "m", state=RouteState(), now=100)
    assert result.route.route_id == "b" and len(draws) == 1
    assert result.evidence["tie_break"] == "weighted_random"
    assert result.evidence["least_pressure_routes"] == 2
    selected, reason = select_route(items, "m", state=RouteState(), now=100)
    assert selected == result.route and reason == result.reason and len(draws) == 2
    only = route_module.decide_route(items[:1], "m", state=RouteState(), now=100)
    assert only.route == items[0] and len(draws) == 3


def test_selection_evidence_distinguishes_pressure_from_affinity():
    from ops.native_fabric.unified_router.routes import decide_route
    items = [route("a"), route("b")]
    first = decide_route(items, "m", state=RouteState(), now=100, affinity_key="private")
    assert first.evidence["tie_break"] == "weighted_rendezvous"
    state = RouteState(in_flight={first.route.route_id: 1})
    second = decide_route(items, "m", state=state, now=100, affinity_key="private")
    assert second.route != first.route
    assert second.evidence["tie_break"] == "lowest_local_pressure"
    assert second.evidence["priority_routes"] == 2


@async_test
async def test_selection_diagnostics_follow_alias_path_and_keep_inputs_private(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "fixture-secret-key")
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={"id": "fixture", "content": []})

    app = create_app(config(tmp_path, aliases=(("fabric/test", ("missing", "m")),)),
                     transport=httpx.MockTransport(handler))
    async with client(app) as session:
        payload = dict(body(metadata={"user_id": "private-affinity"}), model="fabric/test")
        response = await session.post("/v1/messages", headers=HEADERS, json=payload)
        assert response.status_code == 200 and len(calls) == 1
        status = (await session.get("/statusz", headers=HEADERS)).json()
        evidence = status["selection"]["last"]
        assert evidence["candidate_index"] == 2 and evidence["candidate_total"] == 2
        assert evidence["selected_route"] == "a" and evidence["configured_alias"] is True
        assert status["selection"]["evaluations_total"] == 2
        assert status["selection"]["outcomes"] == {"FABRIC_MODEL_UNKNOWN": 1, "SELECTED": 1}
        for i in range(25):
            refused = await session.post("/v1/messages", headers=HEADERS,
                                         json=dict(body(), model=f"private-unknown-{i}"))
            assert refused.status_code == 503
        final = (await session.get("/statusz", headers=HEADERS)).json()
    assert len(calls) == 1
    assert len(final["selection"]["outcomes"]) == 2
    assert final["selection"]["last"]["selected_route"] is None
    evidence_json = json.dumps(final)
    assert "private-unknown" not in evidence_json and "private-affinity" not in evidence_json
    assert "fixture-secret-key" not in evidence_json
    assert len(json.dumps(final["selection"])) < 1500


@async_test
async def test_selection_diagnostics_separate_oauth_preflight_from_local_health(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    oauth_store(tmp_path, last_status="exhausted", last_error_reset_at=time.time()+3600)
    calls = []
    owner_reads = []
    real_read = codex_oauth.read_accounts

    def read_owner(*args):
        owner_reads.append(True)
        return real_read(*args)

    monkeypatch.setattr(codex_oauth, "read_accounts", read_owner)

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={"id": "fixture", "content": []})

    app = create_app(config(tmp_path, routes=(replace(oauth_route(), priority=10),
                                              route("fallback", priority=20))),
                     transport=httpx.MockTransport(handler))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS, json=body())
        reads_after_request = len(owner_reads)
        status = (await session.get("/statusz", headers=HEADERS)).json()
        again = (await session.get("/statusz", headers=HEADERS)).json()
    assert response.status_code == 200 and len(calls) == 1
    assert len(owner_reads) == reads_after_request == 1
    assert again["selection"]["evaluations_total"] == status["selection"]["evaluations_total"]
    evidence = status["selection"]["last"]
    assert evidence["owner_preflight_excluded"] == 1
    assert evidence["matched_routes"] == 1 and evidence["selected_route"] == "fallback"
    assert evidence["scope"] == "local_after_owner_preflight"
    assert status["provider_quota_authority"] is False


def test_latency_histograms_are_bounded_and_reject_invalid_samples():
    state = gateway.RouterState(route_ids=frozenset({"a"}))
    for value in (0., 10., 10.1, 50., 1800000., 1800001.):
        state.observe_latency("a", "completion_ms", value)
    before = json.dumps(state.latency_histograms)
    for value in (float("inf"), float("nan"), -1.):
        state.observe_latency("a", "completion_ms", value)
    state.observe_latency("a", "unbounded-user-metric", 12.)
    state.observe_latency("unbounded-user-route", "completion_ms", 12.)
    assert json.dumps(state.latency_histograms) == before
    buckets = state.latency_histograms["a"]["completion_ms"]
    assert len(buckets) == len(gateway.LATENCY_BUCKET_UPPER_MS)+1
    assert buckets[0] == 2 and buckets[1] == 2 and buckets[-2:] == [1, 1]
    assert sum(buckets) == 6
    json.dumps(state.latency, allow_nan=False)


@async_test
async def test_status_latency_bins_are_labelled_success_only(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    replies = iter([200, 503])
    app = create_app(config(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(next(replies), json={"id": "fixture", "content": []})))
    async with client(app) as session:
        await session.post("/v1/messages", headers=HEADERS, json=body())
        await session.post("/v1/messages", headers=HEADERS, json=body())
        status = (await session.get("/statusz", headers=HEADERS)).json()
    assert status["served_total"] == 1 and status["failed_total"] == 1
    hist = status["routes"][0]["latency_histogram"]
    assert hist["population"] == "successful_completions"
    assert hist["bucket_upper_ms"][-1] is None
    assert sum(hist["counts"]["completion_ms"]) == 1
    assert sum(hist["counts"]["headers_ms"]) == 1


@pytest.mark.parametrize("owner_state,reset,reason", [
    ("dead", None, "FABRIC_OAUTH_OWNER_HELD"),
    ("exhausted", None, "FABRIC_OAUTH_QUOTA_UNKNOWN"),
    ("exhausted", 3600, "FABRIC_OAUTH_ACCOUNTS_EXHAUSTED"),
])
@async_test
async def test_selection_diagnostics_preserve_owner_refusal_with_empty_selector_input(
        tmp_path, owner_state, reset, reason):
    oauth_store(tmp_path, last_status=owner_state,
                last_error_reset_at=time.time()+reset if reset else None)
    calls = []
    app = create_app(config(tmp_path, routes=(oauth_route(),)),
                     transport=httpx.MockTransport(lambda req: calls.append(req)))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS, json=body())
        status = (await session.get("/statusz", headers=HEADERS)).json()
    assert response.status_code == 503 and response.json()["error"]["code"] == reason
    evidence = status["selection"]["last"]
    assert evidence["selector_reason"] == "FABRIC_MODEL_UNKNOWN"
    assert evidence["owner_preflight_excluded"] == 1 and evidence["matched_routes"] == 0
    assert evidence["preflight_refusal"] == reason
    assert evidence["local_permit_acquired"] is False and not calls


@async_test
async def test_preselection_refusal_never_relabels_an_older_route_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    app = create_app(config(tmp_path, max_in_flight=1), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={"id": "fixture", "content": []})))
    async with client(app) as session:
        await session.post("/v1/messages", headers=HEADERS, json=body())
        prior = dict(app.state.router_state.last_selection)
        app.state.router_state.in_flight = 1
        response = await session.post("/v1/messages", headers=HEADERS, json=body())
        status = (await session.get("/statusz", headers=HEADERS)).json()
        app.state.router_state.in_flight = 0
    assert response.status_code == 503
    assert app.state.router_state.last_selection == prior
    assert status["selection"]["not_run"] == {"FABRIC_ROUTER_BUSY": 1}
    assert status["selection"]["last"]["sequence"] == 1


def test_model_overrides_preserve_other_models_and_global_drain(monkeypatch):
    a = replace(route("a", priority=10), models=("m", "other"),
                model_priority={" M ": 20}, model_weight={"m": 0})
    b = replace(route("b", priority=15), models=("m", "other"))
    assert select_route([a, b], "m", state=RouteState(), now=100)[0] == b
    assert select_route([a, b], "other", state=RouteState(), now=100)[0] == a
    assert RouteState().acquire(a, now=100, model="m") is None
    drained = replace(a, weight=0, model_weight={"m": 9})
    assert select_route([drained], "m", state=RouteState(), now=100) == (
        None, "FABRIC_ROUTES_DRAINED")
    assert RouteState().acquire(drained, now=100, model="m") is None


@pytest.mark.parametrize("overrides", [
    {"weight": True}, {"weight": float("nan")}, {"priority": True},
    {"model_priority": {"missing": 10}}, {"model_priority": {"m": 1.5}},
    {"model_weight": {"m": float("inf")}}, {"model_weight": {"m": -1}},
    {"model_weight": {"m": True}}, {"model_weight": {"m": 1, " M ": 2}},
    {"model_params": {"m": {"messages": []}}},
    {"model_params": {"m": {"model": "other"}}},
    {"model_params": {"m": {"stream": False}}},
    {"model_params": {"m": {"reasoning_effort": []}}},
])
def test_model_policy_rejects_ambiguous_or_unsafe_configuration(overrides):
    with pytest.raises(ValueError):
        replace(route(), **overrides)


def test_model_weight_controls_pressure_and_cross_provider_distribution(monkeypatch):
    from ops.native_fabric.unified_router import routes as route_module
    a = replace(route("a"), model_weight={"m": 3}, base_url="https://a.example")
    b = replace(route("b"), base_url="https://b.example")
    draws = iter([.1, .9, .5])
    monkeypatch.setattr(route_module.random, "random", lambda: next(draws))
    first = route_module.decide_route([a, b], "m", state=RouteState(), now=100,
                                     affinity_key="same-private-session")
    second = route_module.decide_route([a, b], "m", state=RouteState(), now=100,
                                      affinity_key="same-private-session")
    assert [first.route.route_id, second.route.route_id] == ["a", "b"]
    assert first.evidence["tie_break"] == second.evidence["tie_break"] == "weighted_random"
    state = RouteState(in_flight={"a": 2, "b": 1})
    assert select_route([a, b], "m", state=state, now=100)[0] == a


@async_test
async def test_model_tuning_targets_public_slug_after_wire_translation(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    item = replace(route(), wire="openai", upstream_model=(("m", "vendor-model"),),
                   model_params={"m": {"reasoning_effort": "medium"}})
    calls = []
    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{
            "message": {"content": "ok"}, "finish_reason": "stop"}]})
    app = create_app(config(tmp_path, routes=(item,), aliases=(("fabric/test", ("m",)),),
                            model_labels=((" M ", "Friendly Model"), (" FABRIC/TEST ", "Friendly Alias"))),
                     transport=httpx.MockTransport(handler))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS, json=body())
        catalog = (await session.get("/v1/models", headers=HEADERS)).json()
        status = (await session.get("/statusz", headers=HEADERS)).json()
    assert response.status_code == 200
    assert calls[0]["model"] == "vendor-model"
    assert calls[0]["reasoning_effort"] == "medium"
    assert catalog["data"][0]["id"] == "m"
    assert catalog["data"][0]["display_name"] == "Friendly Model"
    assert catalog["data"][1]["display_name"] == "Friendly Alias"
    assert status["labels"] == {"m": "Friendly Model", "fabric/test": "Friendly Alias"}
    assert status["routes"][0]["model_params"] == {"m": ["reasoning_effort"]}
    with pytest.raises(ValueError):
        config(tmp_path, model_labels=(("m", "First"), (" M ", "Conflicting")))


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
@async_test
async def test_proven_connection_failure_preserves_global_and_group_reservations(
        tmp_path, monkeypatch, error_type):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    a = replace(route("a", priority=1, concurrency_group="shared", group_max_in_flight=1),
                base_url="https://a.example")
    b = replace(a, route_id="b", priority=2, base_url="https://b.example")
    calls = []
    app = None
    def handler(req):
        calls.append(req.url.host)
        state = app.state.router_state
        assert state.in_flight == 1 and state.routes.group_in_flight["shared"] == 1
        if req.url.host == "a.example":
            assert state.routes.in_flight["a"] == 1
            raise error_type("synthetic pre-send failure", request=req)
        assert state.routes.in_flight["a"] == 0 and state.routes.in_flight["b"] == 1
        return httpx.Response(200, json={"id": "fixture", "content": []})
    async def transport_phase(self, req):
        return handler(req)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", transport_phase)
    app = create_app(config(tmp_path, routes=(a, b), max_in_flight=1))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS, json=body())
        status = (await session.get("/statusz", headers=HEADERS)).json()
    assert response.status_code == 200 and response.headers["x-fabric-route"] == "b"
    assert calls == ["a.example", "b.example"]
    state = app.state.router_state
    assert state.in_flight == state.routes.group_in_flight["shared"] == 0
    assert all(value == 0 for value in state.routes.in_flight.values())
    assert state.attempts == 2 and state.failovers == 1 and state.served == 1
    assert state.failed == state.refused == 0
    assert ("a" in state.routes.cooldown_until) is (error_type is not httpx.PoolTimeout)
    assert status["selection"]["last"]["previous_attempts_excluded"] == 1
    assert status["upstream_send_calls_total"] == 2


@pytest.mark.parametrize("status", [401, 402, 403, 404, 408, 409, 425, 429, 500, 502, 503, 504, 529])
@async_test
async def test_http_response_never_enters_another_provider_or_alias(tmp_path, monkeypatch, status):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    a = replace(route("a", priority=1), base_url="https://a.example")
    b = replace(route("b", priority=2), base_url="https://b.example")
    c = replace(route("c"), base_url="https://c.example", models=("other",))
    calls = []
    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(status, json={"error": "synthetic provider outcome"})
    app = create_app(config(tmp_path, routes=(a, b, c),
                            aliases=(("fabric/test", ("m", "other")),)),
                     transport=httpx.MockTransport(handler))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS,
                                      json={**body(), "model": "fabric/test"})
    assert response.status_code == status
    assert calls == ["a.example"]
    assert app.state.router_state.failovers == 0
    assert app.state.router_state.in_flight == 0


@pytest.mark.parametrize("error_type", [httpx.ReadError, httpx.ReadTimeout,
                                       httpx.WriteError, httpx.WriteTimeout,
                                       httpx.RemoteProtocolError])
@async_test
async def test_ambiguous_transport_never_fails_over(tmp_path, monkeypatch, error_type):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    calls = []
    def handler(req):
        calls.append(req)
        raise error_type("synthetic ambiguity", request=req)
    app = create_app(config(tmp_path, routes=(route("a", priority=1), route("b", priority=2))),
                     transport=httpx.MockTransport(handler))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS, json=body())
    assert response.status_code == 502 and len(calls) == 1
    assert response.json()["error"]["code"] == "FABRIC_UPSTREAM_EFFECT_UNKNOWN"
    assert app.state.router_state.failovers == 0 and app.state.router_state.in_flight == 0


@async_test
async def test_attempt_bound_exhausts_without_leaking_a_permit(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    items = tuple(route(name, priority=index, concurrency_group="shared", group_max_in_flight=1)
                  for index, name in enumerate(("a", "b", "c")))
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ConnectError("synthetic connection refusal", request=req)
    async def transport_phase(self, req):
        return handler(req)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", transport_phase)
    app = create_app(config(tmp_path, routes=items, max_attempts=2))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS, json=body())
    assert response.status_code == 503 and len(calls) == 2
    state = app.state.router_state
    assert state.attempts == 2 and state.failovers == 1 and state.exhausted == 1
    assert state.refused == 1 and state.failed == 0
    assert state.in_flight == state.routes.group_in_flight["shared"] == 0
    assert all(value == 0 for value in state.routes.in_flight.values())


@pytest.mark.parametrize("cancel", [False, True])
@async_test
async def test_local_credential_failover_holds_one_global_slot_through_admission(
        tmp_path, monkeypatch, cancel):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    entered, release = asyncio.Event(), asyncio.Event()
    original = gateway._run_in_executor
    async def executor(fn, *args, **kwargs):
        if fn is gateway._route_authorization and args[0].route_id == "b":
            entered.set()
            await release.wait()
        return await original(fn, *args, **kwargs)
    monkeypatch.setattr(gateway, "_run_in_executor", executor)
    a = replace(route("a", priority=1), gateway_token_env="MISSING_SYNTHETIC_KEY")
    b = route("b", priority=2)
    app = create_app(config(tmp_path, routes=(a, b), max_in_flight=1),
                     transport=httpx.MockTransport(
                         lambda req: httpx.Response(200, json={"id": "fixture", "content": []})))
    async with client(app) as session:
        task = asyncio.create_task(session.post("/v1/messages", headers=HEADERS, json=body()))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            state = app.state.router_state
            assert state.in_flight == 1 and state.routes.in_flight == {"a": 0, "b": 1}
            assert "a" not in state.routes.cooldown_until
            busy = await session.post("/v1/messages", headers=HEADERS, json=body())
            assert busy.status_code == 503 and busy.json()["error"]["code"] == "FABRIC_ROUTER_BUSY"
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                release.set()
                assert (await task).status_code == 200
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    assert app.state.router_state.in_flight == 0
    assert all(value == 0 for value in app.state.router_state.routes.in_flight.values())


@async_test
async def test_alias_fallback_occurs_only_before_any_inference_effect(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    a = replace(route("a"), gateway_token_env="MISSING_SYNTHETIC_KEY")
    b = replace(route("b"), models=("other",))
    calls = []
    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(200, json={"id": "fixture", "content": []})
    app = create_app(config(tmp_path, routes=(a, b),
                            aliases=(("fabric/test", ("m", "other")),)),
                     transport=httpx.MockTransport(handler))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS,
                                      json={**body(), "model": "fabric/test"})
    assert response.status_code == 200 and len(calls) == 1
    assert calls[0]["model"] == "other"
    assert response.headers["x-fabric-model"] == "other"
    assert app.state.router_state.failovers == 1


@async_test
async def test_total_deadline_does_not_restart_after_connection_failover(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    a, b = route("a", priority=1), route("b", priority=2)
    calls = []
    async def handler(req):
        calls.append(req)
        if len(calls) == 1:
            await asyncio.sleep(.02)
            raise httpx.ConnectError("synthetic pre-send failure", request=req)
        await asyncio.Event().wait()
    async def transport_phase(self, req):
        return await handler(req)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", transport_phase)
    app = create_app(config(tmp_path, routes=(a, b), request_timeout_s=.2))
    async with client(app) as session:
        response = await asyncio.wait_for(session.post(
            "/v1/messages", headers=HEADERS, json=body()), 2)
    assert response.status_code == 502 and len(calls) == 2
    assert app.state.router_state.failed == 1
    assert app.state.router_state.in_flight == 0
    assert all(value == 0 for value in app.state.router_state.routes.in_flight.values())


@async_test
async def test_real_httpx_connect_refusal_transmits_one_inference_request(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    # Own the refused port without listening; no race with a different local
    # process can turn the first connection into a real inference service.
    refused = socket.socket()
    refused.bind(("127.0.0.1", 0))
    received = []

    async def provider(reader, writer):
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
            length = next(int(line.split(b":", 1)[1]) for line in header.split(b"\r\n")
                          if line.lower().startswith(b"content-length:"))
            assert 0 < length < 4096
            received.append(json.loads(await reader.readexactly(length)))
            body_bytes = b'{"id":"fixture","content":[]}'
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         + b"Connection: close\r\nContent-Length: " + str(len(body_bytes)).encode()
                         + b"\r\n\r\n" + body_bytes)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(provider, "127.0.0.1", 0)
    try:
        a = replace(route("a", priority=1), base_url=f"http://127.0.0.1:{refused.getsockname()[1]}")
        b = replace(route("b", priority=2), base_url=f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}")
        app = create_app(config(tmp_path, routes=(a, b), max_in_flight=1))
        async with client(app) as session:
            response = await session.post("/v1/messages", headers=HEADERS, json=body())
        assert response.status_code == 200 and response.headers["x-fabric-route"] == "b"
        assert len(received) == 1 and received[0]["model"] == "m"
        assert app.state.router_state.upstream_send_calls == 2
        assert app.state.router_state.failovers == 1 and app.state.router_state.in_flight == 0
    finally:
        server.close()
        await server.wait_closed()
        refused.close()


@async_test
async def test_injected_transport_cannot_claim_pre_send_failure_after_an_effect(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_GATEWAY_TOKEN", "test-key")
    calls = []
    def untrusted_transport(req):
        calls.append(req)
        raise httpx.ConnectError("synthetic misclassified post-effect error", request=req)
    app = create_app(config(tmp_path, routes=(route("a", priority=1), route("b", priority=2))),
                     transport=httpx.MockTransport(untrusted_transport))
    async with client(app) as session:
        response = await session.post("/v1/messages", headers=HEADERS, json=body())
    assert response.status_code == 502 and len(calls) == 1
    assert response.json()["error"]["code"] == "FABRIC_UPSTREAM_EFFECT_UNKNOWN"
    assert app.state.router_state.failovers == 0 and app.state.router_state.in_flight == 0
