"""Exception disclosure regressions with synthetic credentials and providers."""
from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from ops.native_fabric.unified_router import gateway
from ops.native_fabric.unified_router.routes import Route
from ops.native_fabric.unified_router.wire import (
    OpenAIStreamTranslator, ResponsesStreamTranslator, WireTranslationError,
    openai_to_anthropic, responses_to_anthropic)


@pytest.mark.parametrize("code", [
    "FABRIC_TRANSLATE_BLOCK", "FABRIC_STREAM_INCOMPLETE", "FABRIC_RESPONSE_INVALID"])
def test_registered_public_reason_is_preserved(code):
    assert gateway._public_reason(WireTranslationError(code), "FABRIC_TRANSLATE_INVALID") == code


@pytest.mark.parametrize("detail", [
    "FABRIC_PRIVATE_FIXTURE_SECRET", "/private/fixture/token=synthetic-secret"])
def test_unregistered_exception_text_is_never_a_public_reason(detail):
    result = gateway._public_reason(ValueError(detail), "FABRIC_TRANSLATE_INVALID")
    assert result == "FABRIC_TRANSLATE_INVALID"
    assert "PRIVATE" not in result and "synthetic-secret" not in result


@pytest.mark.parametrize("phase", [
    "model-selection", "openai-request", "openai-response",
    "responses-request", "responses-response"])
def test_each_translation_error_boundary_returns_only_registered_reason(tmp_path, monkeypatch, phase, caplog):
    token = "synthetic-router-test-token-32-characters"
    secret_detail = "FABRIC_PRIVATE_FIXTURE_SECRET"
    caplog.set_level(logging.INFO, logger=gateway.__name__)
    calls = []
    monkeypatch.setenv("SYNTHETIC_ROUTER_KEY", "synthetic-upstream-key")

    def refuse(*args, **kwargs):
        raise WireTranslationError(secret_detail)

    wire = "responses" if phase.startswith("responses") else "openai"
    route = Route(route_id="privacy-fixture", kind="oauth_pool" if wire == "responses" else "gateway",
                  base_url="https://synthetic.example", wire=wire, models=("m",),
                  gateway_token_env="SYNTHETIC_ROUTER_KEY", pool="fixture")
    store = tmp_path / "auth.json"
    store.write_text(json.dumps({"credential_pool": {"fixture": [
        {"id": "fixture-account", "label": "fixture", "access_token": "synthetic-access-token",
         "refresh_token": "synthetic-unused-refresh"}]}}))
    if phase == "model-selection":
        monkeypatch.setattr(gateway, "_model_candidates", refuse)
    elif phase == "openai-request":
        monkeypatch.setattr(gateway, "anthropic_to_openai", refuse)
    elif phase == "openai-response":
        monkeypatch.setattr(gateway, "openai_to_anthropic", refuse)
    elif phase == "responses-request":
        monkeypatch.setattr(gateway, "anthropic_to_responses", refuse)
    else:
        monkeypatch.setattr(gateway.ResponsesStreamTranslator, "to_message", refuse)

    def provider(request):
        calls.append(request)
        if wire == "responses":
            event = {"type": "response.completed", "response": {
                "id": "synthetic-response", "status": "completed", "output": [],
                "usage": {"input_tokens": 1, "output_tokens": 0}}}
            return httpx.Response(200, content=("data: "+json.dumps(event)+"\n\ndata: [DONE]\n\n").encode(),
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "fixture"},
                                                     "finish_reason": "stop"}]})

    app = gateway.create_app(gateway.Settings(proxy_token=token, state_dir=tmp_path,
        routes=(route,), auth_store=store), transport=httpx.MockTransport(provider))

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://proxy") as client:
                return await client.post("/v1/messages", headers={"authorization": "Bearer "+token},
                    json={"model": "m", "max_tokens": 16,
                          "messages": [{"role": "user", "content": "privacy fixture"}]})

    response = asyncio.run(exercise())
    assert response.status_code == (502 if phase.endswith("-response") else 400)
    assert secret_detail not in response.text
    assert "synthetic-secret" not in response.text
    assert len(calls) == int(phase.endswith("-response"))
    expected = ("FABRIC_INVALID_REQUEST", "FABRIC_TRANSLATE_INVALID")
    assert any(code in response.text for code in expected)
    assert secret_detail not in caplog.text
    assert "synthetic-access-token" not in caplog.text
    receipts = [json.loads(record.getMessage().removeprefix("FABRIC_TERMINAL "))
                for record in caplog.records if record.getMessage().startswith("FABRIC_TERMINAL ")]
    assert len(receipts) == int(phase != "model-selection")
    assert all(record["outcome"] != "served" for record in receipts)


@pytest.mark.parametrize("seam", ["openai-response", "openai-stream", "responses-response",
                                  "responses-message", "responses-stream"])
def test_malformed_tool_arguments_remain_refused_without_raw_logging(seam, capsys, caplog):
    raw = '{"PRIVATE_ARGUMENT_FIXTURE":'
    if seam == "openai-response":
        exercise = lambda: openai_to_anthropic({"choices": [{"message": {"tool_calls": [
            {"id": "call", "function": {"name": "fixture", "arguments": raw}}]}}]}, model="m")
    elif seam == "openai-stream":
        translator = OpenAIStreamTranslator(model="m")
        translator.feed({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call",
            "function": {"name": "fixture", "arguments": raw}}]}, "finish_reason": "tool_calls"}]})
        exercise = translator.finish
    elif seam == "responses-response":
        exercise = lambda: responses_to_anthropic({"output": [{"type": "function_call",
            "call_id": "call", "name": "fixture", "arguments": raw}]}, model="m")
    else:
        translator = ResponsesStreamTranslator(model="m")
        translator.feed({"type": "response.output_item.added", "item": {"type": "function_call",
            "call_id": "call", "name": "fixture", "arguments": raw}})
        translator.feed({"type": "response.completed", "response": {"status": "completed"}})
        exercise = translator.to_message if seam == "responses-message" else translator.finish
    with pytest.raises(WireTranslationError, match="^FABRIC_TRANSLATE_TOOL_ARGUMENTS$"):
        exercise()
    captured = capsys.readouterr()
    assert "PRIVATE_ARGUMENT_FIXTURE" not in captured.err + captured.out + caplog.text
