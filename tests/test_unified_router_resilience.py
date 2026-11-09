"""Fault-injection tests: no real provider, credential or live service calls."""
from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import replace
from email.utils import formatdate
from contextlib import asynccontextmanager
from functools import wraps

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
    assert client.post.call_count == (0 if peer else 1)


@pytest.mark.parametrize("reset", [None, float("nan"), "unknown"])
def test_exhaustion_without_verified_reset_stays_unavailable(tmp_path, reset):
    path = oauth_store(tmp_path, last_status="exhausted", last_error_reset_at=reset)
    account = codex_oauth.read_accounts(path, "p")[0]
    assert account.exhausted and account.exhausted_unknown
