"""Request normalization at the real Messages ingress, using an in-memory upstream."""
import asyncio
import json

import httpx
import pytest

from ops.native_fabric.unified_router.gateway import Settings, create_app
from ops.native_fabric.unified_router.routes import Route, WIRE_ANTHROPIC


@pytest.fixture
def send(tmp_path, monkeypatch):
    token = "synthetic-router-token-for-ingress-tests"
    monkeypatch.setenv("FIXTURE_UPSTREAM_KEY", "synthetic")
    route = Route(route_id="fixture", kind="gateway", base_url="https://fixture.invalid",
                  wire=WIRE_ANTHROPIC, models=("fixture-model",),
                  gateway_token_env="FIXTURE_UPSTREAM_KEY")
    forwarded = []

    def upstream(request):
        forwarded.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "msg_fixture", "type": "message", "content": []})

    app = create_app(Settings(proxy_token=token, state_dir=tmp_path, routes=(route,)),
                     transport=httpx.MockTransport(upstream))

    async def post(body):
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://router") as client:
                return await client.post("/v1/messages", headers={"x-api-key": token},
                                         json={"model": "fixture-model", "max_tokens": 16, **body})

    return lambda body: (asyncio.run(post(body)), forwarded)


@pytest.mark.parametrize("prefix", ["base", [{"type": "text", "text": "base",
                                             "cache_control": {"type": "ephemeral"}}]])
def test_message_options_are_stripped_and_system_order_is_preserved(send, prefix):
    user = {"role": "user", "content": [{"type": "text", "text": "first"}]}
    assistant = {"role": "assistant", "content": "reply"}
    directive = {"type": "text", "text": "second directive"}
    response, calls = send({
        "system": prefix, "messages": [user, {"role": "system", "content": "first directive"},
                                       {**assistant, "output_config": {}},
                                       {"role": "system", "content": [directive]}],
        "stop_sequences": ["STOP"], "temperature": 0,
        "context_management": {}, "unknown_option": True,
    })
    assert response.status_code == 200
    body, = calls
    original = [{"type": "text", "text": prefix}] if isinstance(prefix, str) else prefix
    assert body["system"] == original + [{"type": "text", "text": "first directive"}, directive]
    assert body["messages"] == [user, assistant]
    assert body["stop_sequences"] == ["STOP"] and body["temperature"] == 0
    assert "context_management" not in body and "unknown_option" not in body


@pytest.mark.parametrize("system,content", [
    (None, "directive"), (42, "directive"), ({"text": "base"}, "directive"),
    ("base", None), ("base", []), ("base", "  "),
    ("base", [{"type": "text", "text": "valid"}, {"type": "image"}]),
    ("base", [{"type": "text", "text": 7}]),
])
def test_unrepresentable_system_instruction_refused_before_forwarding(send, system, content):
    response, calls = send({"system": system, "messages": [
        {"role": "user", "content": "first"}, {"role": "system", "content": content}]})
    assert response.status_code == 400
    assert "FABRIC_INVALID_REQUEST" in response.text
    assert calls == []


def test_inline_system_without_a_prefix_keeps_all_text_blocks(send):
    blocks = [{"type": "text", "text": "instruction", "cache_control": {"type": "ephemeral"}}]
    response, calls = send({"messages": [{"role": "system", "content": blocks},
                                         {"role": "user", "content": "request"}]})
    assert response.status_code == 200
    body, = calls
    assert body["system"] == blocks
    assert body["messages"] == [{"role": "user", "content": "request"}]


@pytest.mark.parametrize("output_config", [
    {"effort": "low"},
    {"format": {"type": "json_schema", "schema": {
        "type": "object", "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"], "additionalProperties": False,
    }}},
    {"effort": "high", "format": {"type": "json_schema", "schema": {
        "type": "object", "properties": {"answer": {"type": "string"}},
        "required": ["answer"], "additionalProperties": False,
    }}},
])
def test_request_output_config_survives_message_option_cleanup(send, output_config):
    response, calls = send({
        "messages": [{"role": "user", "content": "request",
                      "output_config": {"effort": "medium"}}],
        "output_config": output_config,
        "unknown_option": True,
    })
    assert response.status_code == 200
    body, = calls
    assert body["output_config"] == output_config
    assert body["messages"] == [{"role": "user", "content": "request"}]
    assert "unknown_option" not in body
