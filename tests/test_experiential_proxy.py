"""Offline evidence for the local Experiential proxy. No live provider calls."""
from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from ops.native_fabric.experiential_proxy.gateway import (
    QueueExpired,
    Settings,
    SlidingWindowAdmissions,
    create_app,
)

TOKEN = "local-test-token-32-characters-minimum"


def streamed_json(payload):
    return httpx.Response(200, headers={"content-type": "application/json"}, stream=httpx.ByteStream(json.dumps(payload).encode()))


def settings(tmp_path, **kw):
    base = dict(
        api_keys=("upstream-A", "upstream-B"),
        proxy_token=TOKEN,
        state_dir=tmp_path,
        safe_rpm=1,
        window_s=0.07,
        max_pending=6,
        max_queue_wait_s=0.5,
    )
    base.update(kw)
    return Settings(**base)


@pytest.mark.asyncio
async def test_balances_keys_and_never_forwards_local_secret(tmp_path):
    seen = []

    def handler(req):
        seen.append((req.headers.get("authorization"), req.headers.get("idempotency-key"), json.loads(req.content)))
        return streamed_json({"id": "one", "object": "chat.completion", "created": 1,
                                         "model": "model", "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            for _ in range(2):
                response = await session.post("/v1/chat/completions",
                                              headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "job1"},
                                              json={"model": "model", "messages": [{"role": "user", "content": "ok"}]})
                assert response.status_code == 200
    assert [record[0] for record in seen] == ["Bearer upstream-A", "Bearer upstream-B"]
    assert all(record[1] == "job1" for record in seen)
    assert all(TOKEN not in str(record) for record in seen)


@pytest.mark.asyncio
async def test_queued_instead_of_429_when_all_slots_reach_ceiling(tmp_path):
    seen = []

    def handler(req):
        seen.append(time.monotonic())
        return streamed_json({"ok": True})

    app = create_app(settings(tmp_path, api_keys=("upstream-A",), window_s=0.09), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            async def send():
                return await session.post("/v1/responses", headers={"Authorization": f"Bearer {TOKEN}"}, json={"model": "slug", "input": "hello"})
            responses = await asyncio.gather(send(), send(), send())
            assert [r.status_code for r in responses] == [200, 200, 200]
    assert len(seen) == 3
    assert seen[1] - seen[0] >= 0.08
    assert seen[2] - seen[1] >= 0.08


@pytest.mark.asyncio
async def test_persistent_admission_survives_restart(tmp_path):
    cfg = settings(tmp_path, api_keys=("upstream-A",), window_s=0.11, max_queue_wait_s=0.02)
    first = SlidingWindowAdmissions(cfg)
    assert await first.acquire(time.monotonic() + 0.02) == 0
    first.close()
    second = SlidingWindowAdmissions(cfg)
    with pytest.raises(QueueExpired):
        await second.acquire(time.monotonic() + 0.02)
    await asyncio.sleep(0.12)
    assert await second.acquire(time.monotonic() + 0.1) == 0
    second.close()


@pytest.mark.asyncio
async def test_rejects_duplicate_keys_and_same_state_owner(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        settings(tmp_path, api_keys=("same", "same"))
    first = SlidingWindowAdmissions(settings(tmp_path))
    with pytest.raises(RuntimeError, match="another gateway"):
        SlidingWindowAdmissions(settings(tmp_path))
    first.close()


@pytest.mark.asyncio
async def test_provider_429_is_not_replayed_across_credentials(tmp_path):
    seen = []

    def handler(req):
        seen.append(req.headers["authorization"])
        return httpx.Response(429, headers={"retry-after": "60"}, json={"error": {"code": "org_under_review", "message": "review hold"}})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/chat/completions", headers={"Authorization": f"Bearer {TOKEN}"}, json={"model": "m"})
            assert response.status_code == 429
            assert response.headers["retry-after"] == "60"
            assert response.json()["error"]["code"] == "org_under_review"
    assert seen == ["Bearer upstream-A"]


@pytest.mark.asyncio
async def test_auth_and_allowlist_and_no_direct_upstream_contact(tmp_path):
    requests = []

    def handler(req):
        requests.append(req)
        return httpx.Response(200)

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            assert (await session.post("/v1/chat/completions", json={})).status_code == 401
            assert (await session.post("/v1/admin", headers={"Authorization": f"Bearer {TOKEN}"}, json={})).status_code == 404
            assert (await session.get("/healthz")).json() == {"ok": True, "key_slots": 2}
    assert requests == []


@pytest.mark.asyncio
async def test_openai_async_sdk_chat_and_sse(tmp_path):
    AsyncOpenAI = pytest.importorskip("openai", reason="OpenAI SDK unavailable in isolated test container").AsyncOpenAI
    chat_reply = {"id": "reply", "object": "chat.completion", "created": 1, "model": "exact-slug",
                  "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}

    def handler(req):
        payload = json.loads(req.content)
        if payload.get("stream"):
            content = ("data: " + json.dumps({"id": "stream-id", "object": "chat.completion.chunk", "created": 1,
                           "model": "exact-slug", "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}]})
                       + "\n\ndata: [DONE]\n\n")
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=httpx.ByteStream(content.encode()))
        return streamed_json(chat_reply)

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as sdk_transport:
            client = AsyncOpenAI(api_key=TOKEN, base_url="http://proxy/v1", http_client=sdk_transport, max_retries=0)
            r = await client.chat.completions.create(model="exact-slug", messages=[{"role": "user", "content": "say ok"}])
            assert r.choices[0].message.content == "ok"
            stream = await client.chat.completions.create(model="exact-slug", messages=[{"role": "user", "content": "say ok"}], stream=True)
            chunks = [chunk async for chunk in stream]
            assert chunks[0].choices[0].delta.content == "ok"


@pytest.mark.asyncio
async def test_inflight_capacity_waits_and_releases(tmp_path):
    cfg = settings(tmp_path, api_keys=("upstream-A",), safe_rpm=3, window_s=0.4,
                   max_inflight_per_key=1, max_queue_wait_s=0.15)
    limit = SlidingWindowAdmissions(cfg)
    assert await limit.acquire(time.monotonic() + 0.05) == 0
    pending = asyncio.create_task(limit.acquire(time.monotonic() + 0.12))
    await asyncio.sleep(0.02)
    assert limit.pending == 1
    await limit.release(0)
    assert await pending == 0
    await limit.release(0)
    limit.close()


@pytest.mark.asyncio
async def test_queue_full_fails_503_not_429(tmp_path):
    cfg = settings(tmp_path, api_keys=("upstream-A",), safe_rpm=1, window_s=0.3,
                   max_pending=1, max_queue_wait_s=0.13)
    app = create_app(cfg, transport=httpx.MockTransport(lambda req: streamed_json({"ok": True})))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            headers = {"Authorization": f"Bearer {TOKEN}"}
            assert (await session.get("/v1/models", headers=headers)).status_code == 200
            pending = asyncio.create_task(session.get("/v1/models", headers=headers))
            await asyncio.sleep(0.02)
            third = await session.get("/v1/models", headers=headers)
            assert third.status_code == 503
            assert third.json()["error"]["message"] == "local queue full"
            assert (await pending).status_code == 504


@pytest.mark.asyncio
async def test_raw_sse_passthrough_no_chunks_transformed(tmp_path):
    original = 'data: {"id":"abc","object":"chat.completion.chunk","choices":[]}\n\ndata: [DONE]\n\n'
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  stream=httpx.ByteStream(original.encode()))
    ))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/chat/completions", headers={"Authorization": f"Bearer {TOKEN}"},
                                          json={"model": "exact-slug", "stream": True, "messages": []})
            assert response.status_code == 200
            assert response.text == original
            assert response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.asyncio
async def test_compressed_upstream_error_is_not_double_decoded(tmp_path):
    import gzip

    body = json.dumps({"error": {"code": "insufficient_quota", "message": "not transient"}}).encode()
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(429, headers={"content-type": "application/json", "content-encoding": "gzip"},
                                   stream=httpx.ByteStream(gzip.compress(body)))
    ))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            response = await session.post("/v1/responses", headers={"Authorization": f"Bearer {TOKEN}"}, json={})
            assert response.status_code == 429
            assert "content-encoding" not in response.headers
            assert response.json()["error"]["code"] == "insufficient_quota"


@pytest.mark.asyncio
async def test_upstream_redirect_is_refused_without_following(tmp_path):
    seen = []

    def redirect(req):
        seen.append(req.url)
        return httpx.Response(302, headers={"location": "https://unexpected.invalid/"})

    app = create_app(settings(tmp_path), transport=httpx.MockTransport(redirect))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            r = await session.get("/v1/models", headers={"Authorization": f"Bearer {TOKEN}"})
            assert r.status_code == 502
    assert len(seen) == 1
