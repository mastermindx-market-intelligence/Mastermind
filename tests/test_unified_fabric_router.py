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
from ops.native_fabric.unified_router.routes import Route, RouteState, ordered_routes, select_route
from ops.native_fabric.unified_router.wire import (
    OpenAIStreamTranslator,
    WireTranslationError,
    anthropic_to_openai,
    anthropic_to_responses,
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
            # This inference may already have had an upstream effect. Only the
            # next independent request may use the alternative pool.
            assert first.status_code == 429
            second = await session.post("/v1/messages",
                                        headers={"Authorization": f"Bearer {TOKEN}"},
                                        json=anthropic_body("claude-opus-5-5"))
            assert second.status_code == 200
            status = await session.get("/statusz",
                                       headers={"Authorization": f"Bearer {TOKEN}"})
            body = status.json()
            claude_pool = next(r for r in body["routes"] if r["route_id"] == "claude_pool")
            assert claude_pool["cooling"] is True
            assert claude_pool["attempt_failed"] == 1
            assert body["failovers_total"] == 0
            assert body["attempts_total"] == 2
    assert seen == ["http://127.0.0.1:8312/v1/messages",
                    "http://127.0.0.1:8311/v1/messages"]


@run_async_test
async def test_alias_cascades_when_first_target_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRIC_EXPERIENTIAL_GATEWAY_TOKEN", "gw-token-bbbbbbbbbbbbbbbbbbbb")
    state = gateway_module.RouterState()
    monkeypatch.setattr("ops.native_fabric.unified_router.gateway.RouterState",
                        lambda: state)
    # A completed 429 ends this attempt. The next independent alias request
    # skips the cooling model's pool and can select the next family.
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


# --- Chairman 2026-11-09 wide-distribution ruling for deepseek-v4.1-flash ----
# labs_pool / opencode_go_1($40) / byteplus($50) weight 2, opencode_go_2($10)
# weight 1, all in one tier 20 for that slug only, with a caller affinity key
# present (clients send metadata.user_id) so the distribution must survive it.

FLASH = "deepseek-v4.1-flash"


def wide_distribution_routes():
    return [
        Route(route_id="labs_pool", kind="gateway", base_url="http://127.0.0.1:8311",
              wire="anthropic", models=(FLASH, "deepseek-v4-pro"), priority=20,
              model_priority={FLASH: 20}, model_weight={FLASH: 2.0}),
        Route(route_id="opencode_go_1", kind="credential_pool",
              base_url="https://opencode.ai/zen/go", wire="anthropic",
              models=(FLASH,), priority=25,
              model_priority={FLASH: 20}, model_weight={FLASH: 2.0}),
        Route(route_id="opencode_go_2", kind="credential_pool",
              base_url="https://opencode.ai/zen/go", wire="anthropic",
              models=(FLASH,), priority=25,
              model_priority={FLASH: 20}, model_weight={FLASH: 1.0}),
        Route(route_id="byteplus_coding", kind="credential_pool",
              base_url="https://ark.ap-southeast.bytepluses.com/api/coding",
              wire="anthropic", models=(FLASH, "deepseek-v4-pro"), priority=30,
              model_priority={FLASH: 20}, model_weight={FLASH: 2.0}),
    ]


def test_flash_uses_all_providers_at_configured_weights_despite_affinity():
    from collections import Counter
    state = RouteState()
    counts = Counter(
        select_route(wide_distribution_routes(), FLASH, state=state, now=1.0,
                     affinity_key="user_a_t3")[0].route_id
        for _ in range(4000))
    # Wide distribution: every provider serves the slug from one caller.
    assert set(counts) == {"labs_pool", "opencode_go_1",
                           "opencode_go_2", "byteplus_coding"}
    # 2:1:2:2 — the $10 plan carries half the $40 plan's share; labs and
    # byteplus stay level. Bounds are loose (random draw, 4000 samples).
    assert counts["opencode_go_2"] * 1.5 < counts["opencode_go_1"]
    assert counts["opencode_go_2"] * 1.5 < counts["byteplus_coding"]
    assert abs(counts["labs_pool"] - counts["byteplus_coding"]) < 0.15 * counts["labs_pool"]


def test_per_model_overrides_leave_other_model_tiers_untouched():
    state = RouteState()
    picks = {select_route(wide_distribution_routes(), "deepseek-v4-pro",
                          state=state, now=1.0, affinity_key="user_a_t3")[0].route_id
             for _ in range(200)}
    # byteplus (route-wide priority 30) must not join labs (20) for v4-pro.
    assert picks == {"labs_pool"}


def test_affinity_still_pins_within_a_single_provider_tier():
    flash_tier = [r for r in wide_distribution_routes()
                  if r.route_id in ("opencode_go_1", "opencode_go_2")]
    state = RouteState()
    picks = {select_route(flash_tier, FLASH, state=state, now=1.0,
                          affinity_key="user_a_t3")[0].route_id
             for _ in range(50)}
    assert len(picks) == 1


def test_cooling_provider_drops_out_and_distribution_continues():
    from collections import Counter
    routes = wide_distribution_routes()
    state = RouteState()
    state.record_failure("labs_pool", "http_429", now=1.0, cooldown_s=30.0)
    counts = Counter(
        select_route(routes, FLASH, state=state, now=2.0,
                     affinity_key="user_a_t3")[0].route_id
        for _ in range(2000))
    assert "labs_pool" not in counts
    assert set(counts) == {"opencode_go_1", "opencode_go_2", "byteplus_coding"}
    assert counts["opencode_go_2"] * 1.5 < counts["opencode_go_1"]


def test_routes_document_parses_per_model_overrides(tmp_path, monkeypatch):
    document = {"aliases": {}, "routes": [{
        "route_id": "opencode_go_1", "kind": "credential_pool",
        "base_url": "https://opencode.ai/zen/go", "wire": "anthropic",
        "priority": 25, "models": [FLASH],
        "model_priority": {FLASH: 20}, "model_weight": {FLASH: 2}}]}
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(document))
    monkeypatch.setenv("FABRIC_ROUTES_JSON", str(path))
    monkeypatch.setenv("FABRIC_ROUTER_TOKEN", TOKEN)
    cfg = gateway_module.settings_from_env()
    route = cfg.routes[0]
    assert route.model_weight == {FLASH: 2.0}
    assert route.effective_priority(FLASH) == 20
    assert route.effective_priority("DeepSeek-V4.1-Flash".lower()) == 20
    assert route.effective_weight(FLASH) == 2.0
    assert route.effective_priority("other-model") == 25  # route-wide default


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
            assert error["code"] == "FABRIC_ROUTE_CREDENTIAL"
            assert error["message"] == "fabric route unavailable: FABRIC_ROUTE_CREDENTIAL"
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


@run_async_test
async def test_custom_auth_and_session_headers_reach_upstream(tmp_path):
    """An opencode-style route: raw-key header + stable per-affinity session id."""
    (tmp_path / ".env").write_text("OPENCODE_TEST_KEY=oc_test_0123456789abcdef\n")
    oc_route = Route(route_id="opencode_go", kind="credential_pool",
                     base_url="https://opencode.example/zen/go", wire="anthropic",
                     models=("glm-5.3-flash",), priority=25,
                     env_key="OPENCODE_TEST_KEY",
                     auth_header="x-api-key", session_header="x-opencode-session")
    captured = []

    def handler(req):
        captured.append((str(req.url), dict(req.headers)))
        return httpx.Response(200, headers={"content-type": "application/json"},
                              stream=httpx.ByteStream(json.dumps(
                                  {"id": "m", "type": "message", "role": "assistant",
                                   "content": [{"type": "text", "text": "ok"}],
                                   "model": "glm-5.3-flash", "stop_reason": "end_turn",
                                   "usage": {}}).encode()))

    app = create_app(settings(tmp_path, routes=(oc_route,)),
                     transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            for user in ("user_a", "user_a", "user_b"):
                response = await session.post(
                    "/v1/messages", headers={"Authorization": f"Bearer {TOKEN}"},
                    json=anthropic_body("glm-5.3-flash",
                                        metadata={"user_id": user}))
                assert response.status_code == 200
    url, headers = captured[0]
    assert url == "https://opencode.example/zen/go/v1/messages"
    assert headers["x-api-key"] == "oc_test_0123456789abcdef"
    assert "authorization" not in headers
    assert headers["x-opencode-session"] == "fabric-user_a"
    assert captured[1][1]["x-opencode-session"] == "fabric-user_a"
    assert captured[2][1]["x-opencode-session"] == "fabric-user_b"
    assert all("Bearer" not in headers.get("authorization", "") for _, headers in captured)


@run_async_test
async def test_404_count_tokens_is_terminal_without_benching_generation(tmp_path, monkeypatch):
    # A missing count endpoint must neither replay the request nor make the
    # provider's otherwise healthy generation route unavailable.
    monkeypatch.setenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", "gw-token-aaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setenv("FABRIC_EXPERIENTIAL_GATEWAY_TOKEN", "gw-token-bbbbbbbbbbbbbbbbbbbb")
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if str(req.url).startswith("http://127.0.0.1:8312"):
            return streamed(404, {"error": {"type": "not_found_error"}})
        return streamed(200, {"input_tokens": 11})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages/count_tokens",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("claude-opus-5-5"))
            assert response.status_code == 404
            status = (await session.get("/statusz",
                                        headers={"Authorization": f"Bearer {TOKEN}"})).json()
            claude_pool = next(r for r in status["routes"] if r["route_id"] == "claude_pool")
            assert claude_pool["cooling"] is False
            assert claude_pool["attempt_failed"] == 1
            assert status["failovers_total"] == 0
    assert seen == ["http://127.0.0.1:8312/v1/messages/count_tokens"]


@run_async_test
async def test_non_retryable_400_passes_through_upstream_body(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", "gw-token-aaaaaaaaaaaaaaaaaaaa")

    def handler(req):
        return streamed(400, {"error": {"type": "invalid_request_error",
                                        "message": "max_tokens is required"}})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("claude-opus-5-5"))
            assert response.status_code == 400
            assert response.json()["error"]["message"] == "max_tokens is required"
            status = (await session.get("/statusz",
                                        headers={"Authorization": f"Bearer {TOKEN}"})).json()
            assert status["attempts_total"] == 1
            assert status["failovers_total"] == 0


@run_async_test
async def test_ladder_exhaustion_is_typed_503(tmp_path, monkeypatch):
    monkeypatch.delenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("FABRIC_EXPERIENTIAL_GATEWAY_TOKEN", raising=False)
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return streamed(200, {"id": "m", "content": []})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("claude-opus-5-5"))
            assert response.status_code == 503
            error = response.json()["error"]
            assert error["code"] == "FABRIC_ROUTE_CREDENTIAL"
            status = (await session.get("/statusz",
                                        headers={"Authorization": f"Bearer {TOKEN}"})).json()
            assert status["exhausted_total"] == 1
            assert status["failovers_total"] == 1
            assert status["attempts_total"] == 2
            assert sum(r["attempt_failed"] for r in status["routes"]) == 2
    assert seen == []


@run_async_test
async def test_injected_connect_error_does_not_prove_pre_send(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", "gw-token-aaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setenv("FABRIC_EXPERIENTIAL_GATEWAY_TOKEN", "gw-token-bbbbbbbbbbbbbbbbbbbb")
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if str(req.url).startswith("http://127.0.0.1:8312"):
            raise httpx.ConnectError("connection refused")
        return streamed(200, {"id": "m", "content": []})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("claude-opus-5-5"))
            assert response.status_code == 502
            assert response.json()["error"]["code"] == "FABRIC_UPSTREAM_EFFECT_UNKNOWN"
    assert seen == ["http://127.0.0.1:8312/v1/messages"]


@run_async_test
async def test_read_timeout_is_never_replayed(tmp_path, monkeypatch):
    # Mid-request transport failures are EFFECT_UNKNOWN: the request must not
    # be retried on another route even though another rung exists.
    monkeypatch.setenv("FABRIC_ANTHROPIC_GATEWAY_TOKEN", "gw-token-aaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setenv("FABRIC_EXPERIENTIAL_GATEWAY_TOKEN", "gw-token-bbbbbbbbbbbbbbbbbbbb")
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if str(req.url).startswith("http://127.0.0.1:8312"):
            raise httpx.ReadTimeout("timed out")
        return streamed(200, {"id": "m", "content": []})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("claude-opus-5-5"))
            assert response.status_code == 502
            assert response.json()["error"]["code"] == "FABRIC_UPSTREAM_EFFECT_UNKNOWN"
    assert seen == ["http://127.0.0.1:8312/v1/messages"]


@run_async_test
async def test_count_tokens_skips_non_anthropic_wire_rungs(tmp_path):
    write_auth_store(tmp_path)

    def handler(req):
        if req.url.scheme == "https" and req.url.host == "mm.example":
            return streamed(200, {"input_tokens": 7})
        return streamed(200, {"input_tokens": 99})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages/count_tokens",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("minimax-m3"))
            assert response.status_code == 501
            assert response.json()["error"]["code"] == "FABRIC_COUNT_TOKENS_WIRE"


@run_async_test
async def test_model_params_reach_openai_upstream(tmp_path):
    write_auth_store(tmp_path)
    (minimax,) = [r for r in settings(tmp_path).routes if r.route_id == "minimax_pool"]
    tuned = Route(**{**minimax.__dict__,
                     "model_params": {"minimax-m3": {"reasoning_effort": "medium"}}})
    captured = []

    def handler(req):
        captured.append(json.loads(req.content))
        return streamed(200, {"id": "c", "object": "chat.completion",
                              "model": "minimax-m3",
                              "choices": [{"index": 0, "finish_reason": "stop",
                                           "message": {"role": "assistant",
                                                       "content": "ok"}}],
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    app = create_app(settings(tmp_path, routes=(tuned,)),
                     transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body("minimax-m3"))
            assert response.status_code == 200
    assert captured[0]["reasoning_effort"] == "medium"
    assert captured[0]["model"] == "minimax-m3"


@run_async_test
async def test_models_listing_shows_labels(tmp_path):
    app = create_app(settings(tmp_path, model_labels=(("glm-5.3", "GLM-5.3 (Free)"),)))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.get("/v1/models",
                                         headers={"Authorization": f"Bearer {TOKEN}"})
            data = {m["id"]: m for m in response.json()["data"]}
            assert data["glm-5.3"]["display_name"] == "GLM-5.3 (Free)"
            assert data["claude-opus-5-5"]["display_name"] == "claude-opus-5-5"


def test_ordered_routes_tiers_then_weighted_ladder(monkeypatch):
    monkeypatch.setattr("ops.native_fabric.unified_router.routes.random.random", lambda: 0.5)
    routes = [
        Route(route_id="primary", kind="gateway", base_url="http://a",
              wire="anthropic", models=("m",), priority=10, weight=3.0),
        Route(route_id="backup", kind="gateway", base_url="http://b",
              wire="anthropic", models=("m",), priority=40, weight=1.0),
        Route(route_id="peer", kind="gateway", base_url="http://c",
              wire="anthropic", models=("m",), priority=10, weight=1.0),
    ]
    state = RouteState()
    ladder = ordered_routes(routes, "m", state=state, now=0.0)
    assert [r.route_id for r in ladder[:2]] == ["primary", "peer"]
    assert ladder[2].route_id == "backup"
    # A cooling top-tier route drops out of the ladder entirely.
    state.record_failure("primary", "http_429", now=1.0)
    ladder = ordered_routes(routes, "m", state=state, now=2.0)
    assert [r.route_id for r in ladder] == ["peer", "backup"]


@pytest.mark.parametrize("translate,collection,context_role,text_type", [
    (anthropic_to_openai, "messages", "system", "text"),
    (anthropic_to_responses, "input", "developer", "input_text"),
])
def test_inline_system_and_developer_messages_translate_and_empty_text_drops(
        translate, collection, context_role, text_type):
    # Preserve the actual T3 shape fixed by local source 88bc2054, on both wires.
    body = anthropic_body("minimax-m3", messages=[
        {"role": "system", "content": "context note"},
        {"role": "user", "content": [
            {"type": "text", "text": "", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "real question"}]},
        {"role": "assistant", "content": "answer"},
        {"role": "developer", "content": [{"type": "text", "text": "be terse"}]},
        {"role": "user", "content": "follow-up"},
    ])
    rows = translate(body)[collection]
    assert [m["role"] for m in rows] == [context_role, "user", "assistant", context_role, "user"]
    assert rows[1]["content"] == [{"type": text_type, "text": "real question"}]
    assert rows[3]["content"] == ("be terse" if collection == "messages" else
                                  [{"type": "input_text", "text": "be terse"}])


@pytest.mark.parametrize("translate", [anthropic_to_openai, anthropic_to_responses])
def test_unknown_role_still_refused_in_translation(translate):
    with pytest.raises(WireTranslationError, match="FABRIC_TRANSLATE_ROLE"):
        translate(anthropic_body("m", messages=[{"role": "wizard", "content": "hi"}]))


@pytest.mark.parametrize("translate", [anthropic_to_openai, anthropic_to_responses])
@pytest.mark.parametrize("role", ["system", "developer"])
@pytest.mark.parametrize("content", [
    [{"type": "image", "source": {"type": "base64", "data": "x"}}],
    [{"type": "text", "text": 42}],
    [{"type": "tool_use", "id": "t", "name": "f", "input": {}}],
    None,
])
def test_inline_context_never_silently_drops_unsupported_content(translate, role, content):
    with pytest.raises(WireTranslationError):
        translate(anthropic_body("m", messages=[{"role": role, "content": content}]))
