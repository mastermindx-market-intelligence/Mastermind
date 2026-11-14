"""Morph DeepSeek native Anthropic-wire contract. No provider credentials or calls."""
from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import replace

import httpx
import pytest

from ops.native_fabric.unified_router import gateway
from ops.native_fabric.unified_router.gateway import create_app
from ops.native_fabric.unified_router.morph_fallback_config import upgrade
from ops.native_fabric.unified_router.test_morph_fallback_upgrade import config, DS, TOKEN


def _document():
    ids = (["morph_ds", "morph_ds_2", "morph_kimi", "morph_kimi_2",
            "labs_pool", "labs_fable_free", "opencode_go_1",
            "opencode_go_2", "byteplus_coding", "byteplus_coding_2",
            "claude_pool"] +
           [f"bailian_{i}" for i in range(1, 9)] +
           [f"glm_chairman_{i}" for i in range(1, 7)])
    routes = [{"route_id": rid, "base_url": "https://api.morphllm.com/v1"
               if rid.startswith("morph") else "https://other.example",
               "wire": "openai" if rid.startswith("morph") else "anthropic"}
              for rid in ids]
    return {"routes": routes,
            "aliases": {"deepseek-v4-pro": [DS], DS: [DS]},
            "model_labels": {"deepseek-v4-pro": "DeepSeek V4 Pro"},
            "model_routing": {"resources": {rid: {} for rid in ids},
                "exact_route_allowlists": {}, "groups": {},
                "overflow": {"families": {"kimi": {}, "deepseek": {}}}}}


def test_upgrade_is_native_idempotent_and_pro_labeled_honestly():
    original = _document()
    baseline = copy.deepcopy(original)
    result = upgrade(original)
    routes = {r["route_id"]: r for r in result["routes"]}
    for rid in ("morph_ds", "morph_ds_2"):
        assert routes[rid]["wire"] == "anthropic"
        assert routes[rid]["base_url"] == "https://api.morphllm.com"
        assert "Native Anthropic Messages" in routes[rid]["notes"]
    assert routes["morph_kimi"]["wire"] == "openai"
    assert "deepseek-v4-pro" not in result["aliases"]
    assert "deepseek-v4-pro" not in result["model_labels"]
    assert "not V4 Pro" in result["model_labels"][DS]
    assert original == baseline
    assert upgrade(result) == result


def test_genuine_pro_alias_is_not_removed():
    original = _document()
    original["aliases"]["deepseek-v4-pro"] = ["actual-deepseek-v4-pro"]
    result = upgrade(original)
    assert result["aliases"]["deepseek-v4-pro"] == ["actual-deepseek-v4-pro"]


def test_non_morph_origin_cannot_be_retargeted_to_subscription():
    original = _document()
    next(r for r in original["routes"] if r["route_id"] == "morph_ds")["base_url"] = "https://different.example/v1"
    with pytest.raises(ValueError, match="unexpected upstream origin"):
        upgrade(original)


def _native_config(tmp_path):
    from ops.native_fabric.unified_router.test_morph_fallback_upgrade import config
    base = config(tmp_path)
    routes = tuple(replace(r, wire="anthropic", base_url="https://api.morphllm.com",
                           upstream_model=((DS, "morph-dsv41flash-1017"),))
                   if r.route_id in ("d1", "d2") else r for r in base.routes)
    return replace(base, routes=routes)


def _payload(messages, *, stream=False, effort="max"):
    return {"model": DS, "stream": stream, "max_tokens": 512,
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "output_config": {"effort": effort, "unknown_upstream_extension": "must_not_escape"},
            "tools": [{"name": "lookup", "description": "fixture",
                       "input_schema": {"type": "object",
                                        "properties": {"query": {"type": "string"}}}}],
            "messages": messages}


async def _two_turns(cfg, captured):
    def handler(req):
        data = json.loads(req.content)
        captured.append({"url": str(req.url), "data": data})
        assert req.url.path == "/v1/messages"  # NOT /v1/chat/completions
        assert req.url.host == "api.morphllm.com"
        assert data["model"] == "morph-dsv41flash-1017"
        assert data["thinking"] == {"type": "enabled", "budget_tokens": 1024}
        assert data["output_config"] == {"effort": "max"}
        if len(captured) == 1:
            content = [
                {"type": "thinking", "thinking": "synthetic-reasoning-only",
                 "signature": "fixture-signature"},
                {"type": "tool_use", "id": "toolu_fixture", "name": "lookup",
                 "input": {"query": "synthetic"}}]
            stop = "tool_use"
        else:
            assert data["messages"][1]["content"][0]["type"] == "thinking"
            assert data["messages"][1]["content"][0]["thinking"] == "synthetic-reasoning-only"
            assert data["messages"][1]["content"][0]["signature"] == "fixture-signature"
            assert data["messages"][1]["content"][1]["type"] == "tool_use"
            assert data["messages"][2]["content"][0]["tool_use_id"] == "toolu_fixture"
            content = [{"type": "text", "text": "completed"}]
            stop = "end_turn"
        return httpx.Response(200, json={"id": "fixture", "type": "message",
            "role": "assistant", "model": data["model"], "content": content,
            "stop_reason": stop, "usage": {"input_tokens": 15, "output_tokens": 20}})
    app = create_app(cfg, transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
                base_url="http://router") as client:
            headers = {"authorization": "Bearer " + TOKEN,
                       "x-fabric-session-id": "native-fixture"}
            first = await client.post("/v1/messages", json=_payload([
                {"role": "user", "content": "synthetic lookup"}]), headers=headers)
            assert first.status_code == 200, first.text
            assert first.headers["x-fabric-route"] in ("d1", "d2")
            blocks = first.json()["content"]
            assert [b["type"] for b in blocks] == ["thinking", "tool_use"]
            second = await client.post("/v1/messages", json=_payload([
                {"role": "user", "content": "synthetic lookup"},
                {"role": "assistant", "content": blocks},
                {"role": "user", "content": [{
                    "type": "tool_result", "tool_use_id": "toolu_fixture",
                    "content": "lookup result"}]}]), headers=headers)
            assert second.status_code == 200, second.text
            assert second.json()["content"][0]["text"] == "completed"


def test_multi_turn_native_thinking_and_tool_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "_route_authorization", lambda *args: "fixture-only")
    observed = []
    asyncio.run(_two_turns(_native_config(tmp_path), observed))
    assert len(observed) == 2


def test_only_morph_deepseek_receives_output_effort(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "_route_authorization", lambda *args: "fixture-only")
    from ops.native_fabric.unified_router.test_morph_fallback_upgrade import request, success_response
    captured = []
    cfg = config(tmp_path)
    def handler(req):
        data = json.loads(req.content)
        captured.append(data)
        return success_response(req)
    payload = {"model": "qwen4-max-preview", "max_tokens": 128,
               "output_config": {"effort": "max"},
               "messages": [{"role": "user", "content": "synthetic"}]}
    result, _ = asyncio.run(request(cfg, payload, handler))
    assert result.status_code == 200
    assert captured and "output_config" not in captured[0]


def test_upstream_invalid_request_code_visible_without_provider_body(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "_route_authorization", lambda *args: "fixture-only")
    from ops.native_fabric.unified_router.test_morph_fallback_upgrade import request
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(400, json={"error": {
            "code": "invalid_request_error",
            "message": "private provider message must never be echoed"}})
    result, _ = asyncio.run(request(_native_config(tmp_path), _payload([
        {"role": "user", "content": "synthetic failure"}]), handler))
    assert result.status_code == 400
    assert len(calls) == 1  # no replay of an invalid request to the second seat
    body = result.json()["error"]
    assert body["provider_code"] == "invalid_request_error"
    assert "invalid_request:invalid_request_error" in body["message"]
    assert "private provider message" not in result.text
