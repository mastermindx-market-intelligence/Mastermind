"""Behavioral regressions for the M2 resilience upgrade; no live credentials."""
import asyncio
import base64
import json
import os
import threading
import time
from dataclasses import replace

import httpx
import pytest

from ops.native_fabric.unified_router import codex_oauth, wire
from ops.native_fabric.unified_router.gateway import Settings, create_app
from ops.native_fabric.unified_router.routes import Route

TOKEN = "fixture-router-resilience-token-abcdefghijklmnopqrstuvwxyz"


def account(name="a", **extra):
    claims = {"exp": extra.pop("expires", time.time() + 3600),
              "https://api.openai.com/auth": {"chatgpt_account_id": name}}
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return dict(id=name, label=name, access_token=f"e30.{encoded}.sig",
                refresh_token=f"fixture-refresh-{name}", **extra)


def config(tmp_path, rows, fallback=False):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"credential_pool": {"openai-codex": rows}}))
    routes = (Route("codex", "oauth_pool", "https://fixture.example/codex", "responses",
                    ("model",), pool="openai-codex", priority=1),)
    if fallback:
        routes += (Route("fallback", "gateway", "https://fixture.example/fallback", "openai",
                         ("model",), gateway_token_env="RESILIENCE_FIXTURE_TOKEN", priority=100),)
    return Settings(TOKEN, tmp_path / "state", auth_store=auth, routes=routes,
                    capacity_wait_s=0.01)


def terminal(status="completed", reason=None):
    response = {"status": status, "model": "model", "usage": {
        "input_tokens": 9, "input_tokens_details": {"cached_tokens": 2}, "output_tokens": 3}}
    if reason:
        response["incomplete_details"] = {"reason": reason}
    return {"type": "response.incomplete" if status == "incomplete" else "response.completed",
            "response": response}


def sse(events):
    return "".join("data: " + (item if isinstance(item, str) else json.dumps(item)) + "\n\n"
                   for item in events).encode()


class Fragmented(httpx.AsyncByteStream):
    def __init__(self, body):
        self.body, self.closed = body, False

    async def __aiter__(self):
        for at in range(0, len(self.body), 7):
            yield self.body[at:at+7]

    async def aclose(self):
        self.closed = True


async def invoke(cfg, handler, stream=False, payload=None):
    app = create_app(cfg, transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
                                     base_url="http://router") as client:
            reply = await client.post("/v1/messages", headers={"x-api-key": TOKEN}, json=payload or {
                "model": "model", "max_tokens": 32, "stream": stream,
                "messages": [{"role": "user", "content": "fixture"}]})
    return reply, app


@pytest.mark.parametrize("hold,reason", [
    ({"last_status": "dead"}, "FABRIC_OAUTH_OWNER_HELD"),
    ({"expires": 1}, "FABRIC_OAUTH_REFRESH_REQUIRED"),
    ({"last_status": "exhausted"}, "FABRIC_OAUTH_ACCOUNTS_EXHAUSTED"),
    ({"last_status": "exhausted", "last_error_reset_at": "NaN"}, "FABRIC_OAUTH_ACCOUNTS_EXHAUSTED"),
])
def test_owner_preflight_has_no_send_or_provider_health_penalty(tmp_path, hold, reason):
    cfg = config(tmp_path, [account(**hold)])
    def handler(_):
        pytest.fail("ineligible credentials reached upstream")
    reply, app = asyncio.run(invoke(cfg, handler))
    assert reply.status_code == 503 and reply.json()["error"]["code"] == reason
    assert not app.state.router_state.routes.cooldown_until
    assert not app.state.model_policy.active and not app.state.router_state.rate_window._pending
    if reason in {"FABRIC_OAUTH_OWNER_HELD", "FABRIC_OAUTH_REFRESH_REQUIRED"}:
        assert "retry-after" not in reply.headers


def test_selection_skips_dead_expired_and_unknown_quota_rows(tmp_path):
    cfg = config(tmp_path, [account("a", last_status="dead"), account("b", expires=1),
        account("c", last_status="exhausted"), account("d")])
    sent = []
    def handler(request):
        sent.append(request.headers["chatgpt-account-id"])
        return httpx.Response(200, content=sse([terminal()]))
    reply, app = asyncio.run(invoke(cfg, handler))
    assert reply.status_code == 200 and sent == ["d"]
    assert app.state.router_state.served == 1


def test_owner_hold_uses_qualified_alternative_before_send(tmp_path, monkeypatch):
    monkeypatch.setenv("RESILIENCE_FIXTURE_TOKEN", "fixture")
    cfg = config(tmp_path, [account(last_status="dead")], fallback=True)
    paths = []
    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"},
            "finish_reason": "stop"}], "usage": {"prompt_tokens": 4, "completion_tokens": 2}})
    reply, app = asyncio.run(invoke(cfg, handler))
    assert reply.status_code == 200 and paths == ["/fallback/chat/completions"]
    assert "codex" not in app.state.router_state.routes.cooldown_until


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_selected_account_never_refreshes_or_replays_after_send(tmp_path, monkeypatch, status):
    monkeypatch.setenv("RESILIENCE_FIXTURE_TOKEN", "fixture")
    monkeypatch.setattr(codex_oauth, "refresh_account", lambda *a, **k: pytest.fail("refresh invoked"))
    cfg = config(tmp_path, [account("a"), account("b")], fallback=True)
    sent = []
    def handler(request):
        sent.append(request.headers["chatgpt-account-id"])
        return httpx.Response(status, json={"error": {"message": "PRIVATE_PROVIDER_BODY"}},
                              headers={"retry-after": "60"})
    reply, app = asyncio.run(invoke(cfg, handler))
    assert sent == ["a"] and "PRIVATE_PROVIDER_BODY" not in reply.text
    assert app.state.router_state.served == 0 and not app.state.model_policy.active
    if status == 429:
        rows = codex_oauth.read_accounts(cfg.auth_store, "openai-codex")
        assert rows[0].exhausted and not rows[1].exhausted
        assert "codex" not in app.state.router_state.routes.cooldown_until


@pytest.mark.parametrize("value", [None, "NaN", "inf", "-1"])
def test_429_without_verified_reset_remains_unknown_exhausted(tmp_path, value):
    cfg = config(tmp_path, [account()])
    def handler(_):
        return httpx.Response(429, headers={"retry-after": value} if value else {})
    reply, _ = asyncio.run(invoke(cfg, handler))
    assert reply.status_code == 503 and "retry-after" not in reply.headers
    assert codex_oauth.read_accounts(cfg.auth_store, "openai-codex")[0].exhausted_unknown


def test_late_account_bench_preserves_stronger_owner_state_and_deadline(tmp_path):
    cfg = config(tmp_path, [account(last_status="dead")])
    before = cfg.auth_store.read_text()
    assert codex_oauth.bench_row(cfg.auth_store, "openai-codex", "a", reset_at=time.time()+5, reason="http_429") == 0
    assert cfg.auth_store.read_text() == before
    longer = time.time()+1000
    cfg = config(tmp_path, [account(last_status="exhausted", last_error_reset_at=longer)])
    assert codex_oauth.bench_row(cfg.auth_store, "openai-codex", "a", reset_at=time.time()+5, reason="http_429") == longer
    assert os.stat(cfg.auth_store).st_mode & 0o777 == 0o600
    cfg = config(tmp_path, [account(last_status="exhausted")])
    before = cfg.auth_store.read_text()
    assert codex_oauth.bench_row(cfg.auth_store, "openai-codex", "a", reset_at=longer, reason="http_429") == 0
    assert cfg.auth_store.read_text() == before


def test_atomic_account_write_failure_preserves_store_and_refuses_symlink(tmp_path, monkeypatch):
    cfg = config(tmp_path, [account()])
    before = cfg.auth_store.read_bytes()
    def fail(*args):
        raise OSError("fixture replace failure")
    monkeypatch.setattr(codex_oauth.os, "replace", fail)
    with pytest.raises(OSError):
        codex_oauth.bench_row(cfg.auth_store, "openai-codex", "a", reset_at=time.time()+5, reason="http_429")
    assert cfg.auth_store.read_bytes() == before and not list(tmp_path.glob(".auth-router-*"))
    link = tmp_path / "link.json"
    link.symlink_to(cfg.auth_store)
    with pytest.raises(codex_oauth.OAuthPoolError):
        codex_oauth.bench_row(link, "openai-codex", "a", reset_at=time.time()+5, reason="http_429")


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("ending", [None, "invalid json", {"type": "response.failed"},
    {"type": "error"}, {"type": "response.completed", "response": {"status": "failed"}},
    terminal("incomplete", "unexpected")])
def test_failed_responses_never_complete_or_replay(tmp_path, stream, ending):
    cfg = config(tmp_path, [account("a"), account("b")])
    events = [{"type": "response.output_text.delta", "delta": "partial"}]
    if ending is not None:
        events.append(ending)
    body = Fragmented(sse(events))
    sent = []
    def handler(request):
        sent.append(request)
        return httpx.Response(200, stream=body)
    reply, app = asyncio.run(invoke(cfg, handler, stream))
    assert len(sent) == 1 and body.closed and app.state.router_state.served == 0
    assert not app.state.model_policy.active
    if stream:
        assert "event: error" in reply.text and "event: message_stop" not in reply.text
    else:
        assert reply.status_code == 502
    recent = list(app.state.model_policy.events)[-1]
    assert not recent.get("completed")


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("limit", [False, True])
def test_valid_responses_terminal_without_done_has_true_usage(tmp_path, stream, limit):
    cfg = config(tmp_path, [account()])
    body = Fragmented(sse([{"type": "response.output_text.delta", "delta": "OK"},
        terminal("incomplete", "max_output_tokens") if limit else terminal()]))
    reply, app = asyncio.run(invoke(cfg, lambda _: httpx.Response(200, stream=body), stream))
    assert reply.status_code == 200 and body.closed and app.state.router_state.served == 1
    expected = {"input_tokens": 7, "cache_read_input_tokens": 2, "output_tokens": 3}
    if stream:
        rows = [json.loads(line[6:]) for line in reply.text.splitlines() if line.startswith("data: ")]
        final = next(row for row in rows if row["type"] == "message_delta")
        assert final["usage"] == expected
        assert final["delta"]["stop_reason"] == ("max_tokens" if limit else "end_turn")
        assert next(row for row in rows if row["type"] == "message_start")["message"]["id"].startswith("msg_")
    else:
        assert reply.json()["usage"] == expected
        assert reply.json()["stop_reason"] == ("max_tokens" if limit else "end_turn")
    assert app.state.router_state.rate_window.totals("codex", time.monotonic()) == (9, 3)


def test_item_ids_preserve_interleaved_arguments_and_reject_conflicts():
    translator = wire.ResponsesStreamTranslator(model="m")
    for number in (1, 2):
        translator.feed({"type": "response.output_item.added", "item": {
            "type": "function_call", "id": f"item{number}", "call_id": f"call{number}",
            "name": "f", "arguments": '{"n":'}})
    for number in (2, 1):
        translator.feed({"type": "response.function_call_arguments.delta",
            "item_id": f"item{number}", "delta": str(number)+"}"})
    with pytest.raises(wire.WireTranslationError, match="TOOL_IDENTITY"):
        translator.feed({"type": "response.function_call_arguments.delta",
            "item_id": "item1", "call_id": "call2", "delta": " "})
    with pytest.raises(wire.WireTranslationError, match="TOOL_IDENTITY"):
        translator.feed({"type": "response.function_call_arguments.delta",
            "item_id": "unknown", "delta": " "})
    translator.feed(terminal())
    result = translator.to_message()
    assert [(block["id"], block["input"]) for block in result["content"]] == [
        ("call1", {"n": 1}), ("call2", {"n": 2})]


@pytest.mark.parametrize("item_id", ["duplicate", 7, ""])
def test_duplicate_or_invalid_item_ids_refuse(item_id):
    translator = wire.ResponsesStreamTranslator(model="m")
    translator.feed({"type": "response.output_item.added", "item": {
        "type": "function_call", "id": "duplicate", "call_id": "first", "name": "f"}})
    with pytest.raises(wire.WireTranslationError, match="TOOL_IDENTITY"):
        translator.feed({"type": "response.output_item.added", "item": {
            "type": "function_call", "id": item_id, "call_id": "second", "name": "f"}})


def test_openai_final_usage_after_finish_settles_and_preserves_client_id(tmp_path, monkeypatch):
    monkeypatch.setenv("RESILIENCE_FIXTURE_TOKEN", "fixture")
    cfg = config(tmp_path, [account()], fallback=True)
    cfg = replace(cfg, routes=(cfg.routes[1],))
    chunks = [{"choices": [{"delta": {"content": "OK"}, "finish_reason": "stop"}]},
        {"id": "late-upstream-id", "choices": [], "usage": {
            "prompt_tokens": 9, "completion_tokens": 3, "prompt_tokens_details": {"cached_tokens": 2}}}, "[DONE]"]
    bodies = []
    def handler(request):
        assert json.loads(request.content)["stream_options"]["include_usage"] is True
        body = Fragmented(sse(chunks)); bodies.append(body)
        return httpx.Response(200, stream=body)
    ids = []
    for _ in range(2):
        reply, app = asyncio.run(invoke(cfg, handler, True))
        rows = [json.loads(line[6:]) for line in reply.text.splitlines() if line.startswith("data: ")]
        ids.append(rows[0]["message"]["id"])
        final = next(row for row in rows if row["type"] == "message_delta")
        assert final["usage"] == {"input_tokens": 7, "cache_read_input_tokens": 2, "output_tokens": 3}
        assert app.state.router_state.rate_window.totals("fallback", time.monotonic()) == (9, 3)
        assert app.state.router_state.served == 1
    assert ids[0] != ids[1] and "late-upstream-id" not in ids and all(body.closed for body in bodies)


@pytest.mark.parametrize("mode", ["chat", "chat_stream", "responses", "responses_aggregate", "responses_stream"])
def test_malformed_arguments_never_logged_or_fabricated(mode, capsys):
    secret = '{"PRIVATE_ARGUMENT_VALUE":'
    with pytest.raises(wire.WireTranslationError, match="FABRIC_TRANSLATE_TOOL_ARGUMENTS"):
        if mode == "chat":
            wire.openai_to_anthropic({"choices": [{"finish_reason": "tool_calls", "message": {
                "tool_calls": [{"id": "c", "function": {"name": "f", "arguments": secret}}]}}]}, model="m")
        elif mode == "chat_stream":
            translator = wire.OpenAIStreamTranslator(model="m")
            translator.feed({"choices": [{"finish_reason": "tool_calls", "delta": {"tool_calls": [
                {"index": 0, "id": "c", "function": {"name": "f", "arguments": secret}}]}}]})
            translator.finish()
        elif mode == "responses":
            wire.responses_to_anthropic({"status": "completed", "output": [{"type": "function_call",
                "call_id": "c", "name": "f", "arguments": secret}]}, model="m")
        else:
            translator = wire.ResponsesStreamTranslator(model="m")
            translator.feed({"type": "response.output_item.added", "item": {
                "type": "function_call", "call_id": "c", "name": "f", "arguments": secret}})
            translator.feed(terminal())
            (translator.to_message if mode == "responses_aggregate" else translator.finish)()
    captured = capsys.readouterr()
    assert "PRIVATE_ARGUMENT_VALUE" not in captured.out + captured.err


@pytest.mark.parametrize("raw", [False, 0, [], [1], 7])
def test_native_non_object_arguments_are_not_replaced_with_empty_object(raw):
    with pytest.raises(wire.WireTranslationError, match="TOOL_ARGUMENTS"):
        wire._arguments(raw)


def test_invalid_tools_refuse_before_selection(tmp_path):
    cfg = config(tmp_path, [account()])
    reply, _ = asyncio.run(invoke(cfg, lambda _: pytest.fail("unexpected send"),
        payload={"model": "model", "max_tokens": 8, "messages": [], "tools": 7}))
    assert reply.status_code == 400


def test_cancelled_request_cannot_strand_completed_account_hold(tmp_path, monkeypatch):
    cfg = config(tmp_path, [account()])
    entered, release = threading.Event(), threading.Event()
    original = codex_oauth.bench_row
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(codex_oauth, "bench_row", blocked)
    sent = []
    def handler(request):
        sent.append(request)
        return httpx.Response(429) if len(sent) == 1 else httpx.Response(200, content=sse([terminal()]))
    async def run():
        app = create_app(cfg, transport=httpx.MockTransport(handler))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
                                         base_url="http://router") as client:
                async def post():
                    return await client.post("/v1/messages", headers={"x-api-key": TOKEN}, json={
                        "model": "model", "max_tokens": 8, "messages": [{"role": "user", "content": "fixture"}]})
                task = asyncio.create_task(post())
                assert await asyncio.to_thread(entered.wait, 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                release.set()
                await asyncio.gather(*app.state.router_state.oauth_bench_tasks)
                assert not app.state.router_state.oauth_bench
                # The incumbent owner subsequently clears the observed hold.
                cfg.auth_store.write_text(json.dumps({"credential_pool": {"openai-codex": [account()]}}))
                reply = await post()
                assert reply.status_code == 200 and len(sent) == 2
    asyncio.run(run())


def test_older_account_write_cannot_clear_newer_pending_hold(tmp_path, monkeypatch):
    cfg = config(tmp_path, [account()])
    entered = [threading.Event(), threading.Event()]
    release = [threading.Event(), threading.Event()]
    guard, calls = threading.Lock(), []
    original = codex_oauth.bench_row
    def blocked(*args, **kwargs):
        with guard:
            index = len(calls); calls.append(kwargs)
        entered[index].set()
        assert release[index].wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(codex_oauth, "bench_row", blocked)
    async def run():
        both = asyncio.Event()
        upstream_calls = []
        async def handler(request):
            upstream_calls.append(request)
            if len(upstream_calls) == 2:
                both.set()
            await both.wait()
            return httpx.Response(429, headers={"retry-after": "60"})
        app = create_app(cfg, transport=httpx.MockTransport(handler))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
                                         base_url="http://router") as client:
                async def post():
                    return await client.post("/v1/messages", headers={"x-api-key": TOKEN}, json={
                        "model": "model", "max_tokens": 8, "messages": [{"role": "user", "content": "fixture"}]})
                tasks = [asyncio.create_task(post()), asyncio.create_task(post())]
                assert all(await asyncio.gather(*(asyncio.to_thread(e.wait, 2) for e in entered)))
                release[0].set()
                done, pending = await asyncio.wait(tasks, timeout=2, return_when=asyncio.FIRST_COMPLETED)
                assert len(done) == 1 and len(pending) == 1
                assert ("codex", "a") in app.state.router_state.oauth_bench
                release[1].set()
                replies = await asyncio.gather(*tasks)
                assert all(reply.status_code == 503 for reply in replies)
                assert not app.state.router_state.oauth_bench
                assert codex_oauth.read_accounts(cfg.auth_store, "openai-codex")[0].exhausted_until >= max(c["reset_at"] for c in calls)
    asyncio.run(run())

