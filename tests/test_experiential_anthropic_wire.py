"""Offline evidence for the Experiential proxy Anthropic Messages surface.

No live provider calls. The operator-deployed catalogue is the whole funding
boundary; these tests prove admission, key rotation, streaming passthrough and
typed refusal before any RPM/slot reservation.
"""
from __future__ import annotations

import asyncio
import json
from functools import wraps

import httpx
import pytest

from ops.native_fabric.experiential_proxy.gateway import (
    Settings, create_app, anthropic_policy_digest, parse_anthropic_models,
)

TOKEN = "local-test-token-32-characters-minimum"
ADMITTED = ("glm-5.3", "claude-sonnet-latest")


def run_async_test(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return run


def streamed(payload, headers=None):
    merged = {"content-type": "application/json"}
    merged.update(headers or {})
    return httpx.Response(200, headers=merged,
                          stream=httpx.ByteStream(json.dumps(payload).encode()))


def settings(tmp_path, **kw):
    base = dict(
        api_keys=("upstream-A", "upstream-B"),
        proxy_token=TOKEN,
        state_dir=tmp_path,
        safe_rpm=10,
        window_s=1.0,
        anthropic_models=ADMITTED,
    )
    base.update(kw)
    return Settings(**base)


def anthropic_body(model="glm-5.3", **extra):
    body = {"model": model, "max_tokens": 16,
            "messages": [{"role": "user", "content": "ok"}]}
    body.update(extra)
    return body


@run_async_test
async def test_anthropic_messages_round_robins_keys_and_hides_local_token(tmp_path):
    seen = []

    def handler(req):
        seen.append((str(req.url), req.headers.get("authorization")))
        return streamed({"id": "msg_1", "type": "message", "role": "assistant",
                         "content": [{"type": "text", "text": "ok"}],
                         "model": "glm-5.3", "stop_reason": "end_turn"})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            for _ in range(2):
                response = await session.post("/v1/messages",
                                              headers={"Authorization": f"Bearer {TOKEN}"},
                                              json=anthropic_body())
                assert response.status_code == 200
                assert response.json()["content"][0]["text"] == "ok"
    assert [url for url, _ in seen] == [
        "https://api.experientiallabs.ai/v1/messages"] * 2
    assert [auth for _, auth in seen] == ["Bearer upstream-A", "Bearer upstream-B"]
    assert all(TOKEN not in str(record) for record in seen)


@run_async_test
async def test_anthropic_disabled_by_default_refuses_before_admission(tmp_path):
    seen = []

    def handler(req):
        seen.append(req)
        return streamed({})

    cfg = settings(tmp_path, anthropic_models=())
    app = create_app(cfg, transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body())
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "PLAN_ANTHROPIC_NOT_ENABLED"
    assert seen == []


@run_async_test
async def test_anthropic_non_admitted_model_is_refused_without_upstream_send(tmp_path):
    seen = []

    def handler(req):
        seen.append(req)
        return streamed({})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body(model="gpt-6.1-sol"))
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "PLAN_MODEL_NOT_ADMITTED"
    assert seen == []


@run_async_test
async def test_anthropic_routing_override_field_is_refused(tmp_path):
    def handler(req):
        raise AssertionError("must not be called")

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body(routing={"allow_fallbacks": True}))
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "PLAN_ROUTING_OVERRIDE_REFUSED"


@run_async_test
async def test_anthropic_binding_header_must_match_deployed_catalogue(tmp_path):
    def handler(req):
        return streamed({"id": "msg_1", "type": "message"})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            wrong = await session.post("/v1/messages",
                                       headers={"Authorization": f"Bearer {TOKEN}",
                                                "x-fabric-plan-policy": "deadbeef"},
                                       json=anthropic_body())
            assert wrong.status_code == 409
            assert wrong.json()["error"]["code"] == "PLAN_POLICY_MISMATCH"
            ok = await session.post("/v1/messages",
                                    headers={"Authorization": f"Bearer {TOKEN}",
                                             "x-fabric-plan-policy": anthropic_policy_digest(ADMITTED)},
                                    json=anthropic_body())
            assert ok.status_code == 200


@run_async_test
async def test_anthropic_count_tokens_uses_same_admission(tmp_path):
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return streamed({"input_tokens": 7})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages/count_tokens",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body(model="claude-sonnet-latest"))
            assert response.status_code == 200
            assert response.json()["input_tokens"] == 7
            refused = await session.post("/v1/messages/count_tokens",
                                         headers={"Authorization": f"Bearer {TOKEN}"},
                                         json=anthropic_body(model="kimi-k3"))
            assert refused.status_code == 403
    assert seen == ["https://api.experientiallabs.ai/v1/messages/count_tokens"]


@run_async_test
async def test_anthropic_sse_stream_passes_through_unchanged(tmp_path):
    chunks = [b'event: message_start\ndata: {"type":"message_start"}\n\n',
              b'event: content_block_delta\ndata: {"type":"content_block_delta"}\n\n']

    def handler(req):
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              stream=httpx.ByteStream(b"".join(chunks)))

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/messages",
                                          headers={"Authorization": f"Bearer {TOKEN}"},
                                          json=anthropic_body(stream=True))
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert b"".join(response.iter_bytes()) == b"".join(chunks)


@run_async_test
async def test_statusz_discloses_surface_without_models_or_keys(tmp_path):
    def handler(req):
        raise AssertionError("must not be called")

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.get("/statusz",
                                         headers={"Authorization": f"Bearer {TOKEN}"})
            assert response.status_code == 200
            body = response.json()
            assert body["anthropic_surface"] == "enabled"
            assert body["anthropic_policy_digest"] == anthropic_policy_digest(ADMITTED)
            assert "glm-5.3" not in json.dumps(body)
            assert "upstream-A" not in json.dumps(body)


def test_parse_anthropic_models_rejects_duplicates_and_bad_slugs():
    assert parse_anthropic_models("glm-5.3, claude-sonnet-latest") == (
        "glm-5.3", "claude-sonnet-latest")
    assert parse_anthropic_models("") == ()
    with pytest.raises(ValueError):
        parse_anthropic_models("glm-5.3,glm-5.3")
    with pytest.raises(ValueError):
        parse_anthropic_models("has space")
    with pytest.raises(ValueError):
        parse_anthropic_models("bad/slug")


def test_settings_rejects_duplicate_anthropic_models(tmp_path):
    with pytest.raises(ValueError):
        settings(tmp_path, anthropic_models=("glm-5.3", "glm-5.3"))
