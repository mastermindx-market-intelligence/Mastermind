"""Offline evidence for the unified fabric router. No live provider calls."""
from __future__ import annotations

import asyncio
import json
from functools import wraps
from pathlib import Path

import httpx
import pytest

from ops.native_fabric.unified_router import gateway as gateway_module
from ops.native_fabric.unified_router.gateway import Settings, create_app
from ops.native_fabric.unified_router.routes import Route, RouteState, select_route
from ops.native_fabric.unified_router.wire import (
    OpenAIStreamTranslator,
    WireTranslationError,
    anthropic_to_openai,
    openai_to_anthropic,
)

TOKEN = "router-test-token-32-characters-min"


def run_async_test(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return run


def routes(tmp_path, auth=None):
    auth = auth or tmp_path / "auth.json"
    return (
        Route(route_id="claude_pool", kind="gateway", base_url="http://127.0.0.1:8312",
              wire="anthropic", models=("claude-opus-5-5", "claude-haiku-5-5"),
              priority=10, gateway_token_env="FABRIC_ANTHROPIC_GATEWAY_TOKEN"),
        Route(route_id="labs_pool", kind="gateway", base_url="http://127.0.0.1:8311",
              wire="anthropic", models=("glm-5.3", "claude-opus-5-5"),
              priority=20, gateway_token_env="FABRIC_EXPERIENTIAL_GATEWAY_TOKEN"),
        Route(route_id="minimax_pool", kind="credential_pool",
              base_url="https://mm.example/v1",
              wire="openai", models=("minimax-m3",), priority=10,
              pool="minimax", api_key_label="MINIMAX_API_KEY"),
    )


def settings(tmp_path, **kw):
    base = dict(proxy_token=TOKEN, state_dir=tmp_path,
                routes=routes(tmp_path),
                aliases=(("fabric/fast", ("claude-haiku-5-5", "glm-5.3")),
                         ("fabric/frontier", ("claude-opus-5-5",))),
                auth_store=tmp_path / "auth.json")
    base.update(kw)
    return Settings(**base)


def streamed(status, payload, content_type="application/json"):
    return httpx.Response(status, headers={"content-type": content_type},
                          stream=httpx.ByteStream(json.dumps(payload).encode()))


def write_auth_store(tmp_path):
    (tmp_path / "auth.json").write_text(json.dumps({
        "credential_pool": {"minimax": [
            {"label": "MINIMAX_API_KEY", "api_key": "mm-key-0123456789abcdef"}]}}))
    return tmp_path / "auth.json"


def anthropic_body(model="claude-opus-5-5", **extra):
    body = {"model": model, "max_tokens": 64,
            "messages": [{"role": "user", "content": "hello"}]}
    body.update(extra)
    return body


@run_async_test
async def test_exact_model_routes_to_dedicated_tier(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", "gw-token-aaaaaaaaaaaaaaaaaaaa")
    seen = []

    def handler(req):
        seen.append((str(req.url), req.headers.get("authorization")))
        return httpx.Response(200, headers={"content-type": "application/json"},
                              stream=httpx.ByteStream(json.dumps(
                                  {"id": "m", "type": "message", "role": "assistant",
                                   "content": [{"type": "text", "text": "ok"}],
                                   "model": "claude-haiku-5-5", "stop_reason": "end_turn",
                                   "usage": {}}).encode()))

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("claude-haiku-5-5"))
            assert response.status_code == 200
    assert seen[0][0] == "http://127.0.0.1:8312/v1/messages"
    assert seen[0][1] == "Bearer gw-token-aaaaaaaaaaaaaaaaaaaa"


@run_async_test
async def test_caller_token_never_reaches_upstream_and_auth_is_required(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", "gw-token-aaaaaaaaaaaaaaaaaaaa")
    captured = []

    def handler(req):
        captured.append(dict(req.headers))
        return streamed(200, {"id": "m", "content": []})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            ok = await session.post("/v1/messages",
                                    headers={"Authorization": f"Bearer {TOKEN}"},
                                    json=anthropic_body())
            assert ok.status_code == 200
            anonymous = await session.post("/v1/messages", json=anthropic_body())
            assert anonymous.status_code == 401
            bad = await session.get("/v1/models")
            assert bad.status_code == 401
    assert all(TOKEN not in str(headers) for headers in captured)
    assert all("gw-token-aaaaaaaaaaaaaaaaaaaa" in str(h) for h in captured)


@run_async_test
async def test_429_cools_route_and_fails_over_to_next_tier(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", "gw-token-aaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setenv("FABRIC_EXPERIENTIAL_GATEWAY_TOKEN", "gw-token-bbbbbbbbbbbbbbbbbbbb")
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if str(req.url).startswith("http://127.0.0.1:8312"):
            return streamed(429, {"error": "rate_limited"})
        return streamed(200, {"id": "m", "content": []})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            first = await session.post("/v1/messages",
                                       headers={"Authorization": f"Bearer {TOKEN}"},
                                       json=anthropic_body("claude-opus-5-5"))
            assert first.status_code == 429  # surfaced, never replayed
            second = await session.post("/v1/messages",
                                        headers={"Authorization": f"Bearer {TOKEN}"},
                                        json=anthropic_body("claude-opus-5-5"))
            assert second.status_code == 200
    assert seen == ["http://127.0.0.1:8312/v1/messages",
                    "http://127.0.0.1:8311/v1/messages"]


@run_async_test
async def test_alias_cascades_when_first_target_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRIC_EXPERIENTIAL_GATEWAY_TOKEN", "gw-token-bbbbbbbbbbbbbbbbbbbb")
    state = gateway_module.RouterState()
    monkeypatch.setattr("ops.native_fabric.unified_router.gateway.RouterState",
                        lambda: state)
    # haiku (claude pool) fails once; fabric/fast must fall through to glm-5.3.
    monkeypatch.setenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", "gw-token-aaaaaaaaaaaaaaaaaaaa")
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if str(req.url).startswith("http://127.0.0.1:8312"):
            return streamed(429, {"error": "rate_limited"})
        return streamed(200, {"id": "m", "content": []})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            first = await session.post("/v1/messages",
                                       headers={"Authorization": f"Bearer {TOKEN}"},
                                       json=anthropic_body("fabric/fast"))
            assert first.status_code == 429
            second = await session.post("/v1/messages",
                                        headers={"Authorization": f"Bearer {TOKEN}"},
                                        json=anthropic_body("fabric/fast"))
            assert second.status_code == 200
    assert seen == ["http://127.0.0.1:8312/v1/messages",
                    "http://127.0.0.1:8311/v1/messages"]


@run_async_test
async def test_unknown_model_is_typed_refusal(tmp_path, monkeypatch):
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={})))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("nope-model"))
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "FABRIC_MODEL_UNKNOWN"


@run_async_test
async def test_openai_route_translates_request_and_response(tmp_path):
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={
            "id": "chatcmpl-1", "choices": [{"index": 0, "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": "let me check",
                    "tool_calls": [{"id": "call_1", "type": "function",
                        "function": {"name": "read_file",
                                     "arguments": "{\"path\":\"x\"}"}}]}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7}})

    write_auth_store(tmp_path)
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    body = anthropic_body("minimax-m3", system="be brief", tools=[
        {"name": "read_file", "description": "read",
         "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}}])
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=body)
            assert response.status_code == 200
    assert captured["url"] == "https://mm.example/v1/chat/completions"
    sent = captured["body"]
    assert sent["messages"][0] == {"role": "system", "content": "be brief"}
    assert sent["tools"][0]["function"]["name"] == "read_file"
    assert sent["tools"][0]["function"]["parameters"]["type"] == "object"
    result = response.json()
    assert result["content"][0] == {"type": "text", "text": "let me check"}
    assert result["content"][1]["type"] == "tool_use"
    assert result["content"][1]["input"] == {"path": "x"}
    assert result["stop_reason"] == "tool_use"
    assert result["usage"] == {"input_tokens": 11, "output_tokens": 7}


@run_async_test
async def test_openai_stream_translates_to_anthropic_sse(tmp_path):
    chunks = [
        b'data: {"choices":[{"delta":{"content":"he"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"y"}}]}\n\n',
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_9","function":{"name":"run","arguments":"{\\"a\\":"}}]}}]}\n\n',
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"1}"}}]},"finish_reason":"tool_calls"}]}\n\n',
        b'data: {"usage":{"prompt_tokens":3,"completion_tokens":5}}\n\n',
        b'data: [DONE]\n\n',
    ]

    def handler(req):
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              stream=httpx.ByteStream(b"".join(chunks)))

    write_auth_store(tmp_path)
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("minimax-m3", stream=True))
            assert response.headers["content-type"].startswith("text/event-stream")
            events = response.text
    assert "event: message_start" in events
    assert "text_delta" in events and '"text":"he"' in events and '"text":"y"' in events
    assert '"type":"tool_use"' in events and '"name":"run"' in events
    assert "input_json_delta" in events and '"partial_json":"{\\"a\\":1}"' in events
    assert '"stop_reason":"tool_use"' in events
    assert "event: message_stop" in events


@run_async_test
async def test_count_tokens_passthrough_anthropic_and_refused_openai(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", "gw-token-aaaaaaaaaaaaaaaaaaaa")
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(200, json={"input_tokens": 5})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            ok = await session.post("/v1/messages/count_tokens",
                                    headers={"Authorization": f"Bearer {TOKEN}"},
                                    json=anthropic_body("claude-opus-5-5"))
            assert ok.status_code == 200 and ok.json()["input_tokens"] == 5
            refused = await session.post("/v1/messages/count_tokens",
                                         headers={"Authorization": f"Bearer {TOKEN}"},
                                         json=anthropic_body("minimax-m3"))
            assert refused.status_code == 501
    assert seen == ["http://127.0.0.1:8312/v1/messages/count_tokens"]


@run_async_test
async def test_models_lists_union_and_aliases_and_statusz_reports_health(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", "gw-token-aaaaaaaaaaaaaaaaaaaa")
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={})))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            models = (await session.get("/v1/models",
                                        headers={"Authorization": f"Bearer {TOKEN}"})).json()
            ids = [m["id"] for m in models["data"]]
            assert "claude-opus-5-5" in ids and "glm-5.3" in ids and "minimax-m3" in ids
            assert "fabric/fast" in ids and "fabric/frontier" in ids
            status = (await session.get("/statusz",
                                        headers={"Authorization": f"Bearer {TOKEN}"})).json()
            assert status["ok"] is True
            assert {r["route_id"] for r in status["routes"]} == {
                "claude_pool", "labs_pool", "minimax_pool"}
            assert all("token" not in json.dumps(r) for r in status["routes"])


def test_affinity_is_stable_per_user():
    from ops.native_fabric.unified_router.routes import affinity_route
    ids = ["a", "b", "c"]
    assert len({affinity_route(ids, f"user-{i}") for i in range(12)}) >= 2
    assert affinity_route(ids, "u") == affinity_route(ids, "u")


def test_translation_round_trip_tools():
    body = {"model": "m", "max_tokens": 8, "system": "s",
            "messages": [
                {"role": "user", "content": "do it"},
                {"role": "assistant", "content": [
                    {"type": "text", "text": "calling"},
                    {"type": "tool_use", "id": "t1", "name": "f", "input": {"x": 1}}]},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "42"}]}],
            "tools": [{"name": "f", "input_schema": {"type": "object"}}]}
    sent = anthropic_to_openai(body)
    assert sent["messages"][2]["tool_calls"][0]["function"]["name"] == "f"
    assert sent["messages"][3] == {"role": "tool", "tool_call_id": "t1", "content": "42"}
    result = openai_to_anthropic(
        {"id": "c", "choices": [{"finish_reason": "stop",
                                 "message": {"content": "done", "tool_calls": []}}],
         "usage": {"prompt_tokens": 1, "completion_tokens": 2}}, model="m")
    assert result["content"] == [{"type": "text", "text": "done"}]
    assert result["stop_reason"] == "end_turn"


@run_async_test
async def test_config_file_route_uses_incumbent_config_and_rewrites_model(tmp_path):
    config = tmp_path / "mm.json"
    config.write_text(json.dumps({
        "api_key": "cfg-key-0123456789abcdef",
        "anthropic_base_url": "https://vendor.example/anthropic"}))
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["auth"] = req.headers.get("authorization")
        captured["body"] = json.loads(req.content)
        return streamed(200, {"id": "m", "content": [{"type": "text", "text": "ok"}],
                              "stop_reason": "end_turn", "usage": {}})

    route = Route(route_id="vendor_cfg", kind="config_file", base_url="",
                  wire="anthropic", models=("MiniMax-M3",),
                  config_path=str(config), key_pointer="api_key",
                  base_url_pointer="anthropic_base_url",
                  upstream_model=(("minimax-m3", "MiniMax-M3"),))
    cfg = settings(tmp_path, routes=(route,), aliases=())
    app = create_app(cfg, transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("minimax-m3"))
            assert response.status_code == 200
    assert captured["url"] == "https://vendor.example/anthropic/v1/messages"
    assert captured["auth"] == "Bearer cfg-key-0123456789abcdef"
    assert captured["body"]["model"] == "MiniMax-M3"


def test_route_matching_is_case_insensitive_and_exact():
    route = Route(route_id="r", kind="gateway", base_url="http://x", wire="anthropic",
                  models=("glm-5.3", "GLM-5.3-Flash"),
                  upstream_model=(("glm-5.3-flash", "GLM-5.3-Flash"),))
    assert route.serves("GLM-5.3") and route.serves("glm-5.3-flash")
    assert not route.serves("glm-5.3x")
    assert route.wire_model("GLM-5.3-FLASH") == "GLM-5.3-Flash"


def test_config_file_route_key_pointers(tmp_path):
    from ops.native_fabric.unified_router.routes import config_file_route_key
    config = tmp_path / "pool.json"
    config.write_text(json.dumps({"token-plan": {"api_keys": [
        {"name": "a", "api_key": "key-a"}, {"name": "b", "api_key": "key-b"}]}}))
    key, base = config_file_route_key(str(config), "token-plan.api_keys.1.api_key")
    assert key == "key-b" and base == ""
    with pytest.raises(ValueError):
        config_file_route_key(str(config), "token-plan.missing")


@run_async_test
async def test_missing_model_is_bounded_constant_refusal(tmp_path):
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={})))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json={"max_tokens": 8, "messages": []})
            assert response.status_code == 400
            error = response.json()["error"]
            assert error["message"] == "FABRIC_EXACT_MODEL_REQUIRED"
            assert error["type"] == "invalid_request_error"


@run_async_test
async def test_credential_failure_never_leaks_path_detail(tmp_path):
    missing = tmp_path / "absent-glm-config.json"
    config_route = Route(route_id="glm_missing", kind="config_file",
                         base_url="https://api.example/api/anthropic",
                         wire="anthropic", models=("glm-5.3",), priority=1,
                         config_path=str(missing), key_pointer="api_key")
    app = create_app(settings(tmp_path, routes=(config_route,)),
                     transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("glm-5.3"))
            assert response.status_code == 503
            error = response.json()["error"]
            assert error["code"] == "credential_unavailable"
            assert error["message"] == "fabric route unavailable: credential_unavailable"
            assert str(missing) not in response.text
            assert "api.example" not in response.text


@run_async_test
async def test_openai_translation_refusal_keeps_constant_reason(tmp_path):
    write_auth_store(tmp_path)
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={})))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post(
                "/v1/messages", headers={"Authorization": f"Bearer {TOKEN}"},
                json=anthropic_body("minimax-m3",
                                    messages=[{"role": "wizard", "content": "hi"}]))
            assert response.status_code == 400
            error = response.json()["error"]
            assert error["message"] == "FABRIC_TRANSLATE_ROLE"
            assert error["type"] == "invalid_request_error"


@run_async_test
async def test_non_constant_exception_text_never_reaches_client(tmp_path, monkeypatch):
    write_auth_store(tmp_path)
    hostile = "translation exploded at /Users/chriswong/.glm/config.json key sk-ant-abcdefghij"

    def raise_hostile(body):
        raise WireTranslationError(hostile)

    monkeypatch.setattr(gateway_module, "anthropic_to_openai", raise_hostile)
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={})))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("minimax-m3"))
            assert response.status_code == 400
            error = response.json()["error"]
            assert error["message"] == "FABRIC_TRANSLATE_INVALID"
            for fragment in ("/Users/chriswong", "sk-ant-", "exploded"):
                assert fragment not in response.text


@run_async_test
async def test_openai_response_translation_failure_is_bounded_502(tmp_path):
    write_auth_store(tmp_path)
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: streamed(200, {"id": "c", "object": "chat.completion",
                                   "choices": [], "usage": {}})))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("minimax-m3"))
            assert response.status_code == 502
            error = response.json()["error"]
            assert error["message"] == "translation failed: FABRIC_TRANSLATE_RESPONSE"
            assert error["type"] == "fabric_route_error"
