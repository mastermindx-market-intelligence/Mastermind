"""Offline evidence for the local Experiential proxy. No live provider calls."""
from __future__ import annotations

import asyncio
from functools import wraps
import json
import time

import httpx
import pytest

from ops.native_fabric.experiential_proxy.gateway import (
    QueueFull,
    QueueExpired,
    Settings,
    SlidingWindowAdmissions,
    create_app,
)

def run_async_test(fn):
    """Run async tests with stdlib asyncio in any pytest environment.

    functools.wraps preserves each fixture/parametrization signature.
    """
    @wraps(fn)
    def run(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return run


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


@run_async_test
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


@run_async_test
async def test_queued_instead_of_429_when_all_slots_reach_ceiling(tmp_path):
    seen = []

    def handler(req):
        seen.append(time.monotonic())
        return streamed_json({"ok": True})

    cfg = settings(tmp_path, api_keys=("upstream-A",), window_s=0.09)
    app = create_app(cfg, transport=httpx.MockTransport(handler))
    admitted_at = []
    async with app.router.lifespan_context(app):
        limiter = app.state.admissions
        original_acquire = limiter.acquire

        async def observe_reservation(*args, **kwargs):
            slot = await original_acquire(*args, **kwargs)
            # Capture the committed admission timestamp, before the next await.
            admitted_at.append(limiter.events[slot][-1])
            return slot

        limiter.acquire = observe_reservation
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            async def send():
                return await session.post("/v1/responses", headers={"Authorization": f"Bearer {TOKEN}"}, json={"model": "slug", "input": "hello"})
            responses = await asyncio.gather(send(), send(), send())
            assert [r.status_code for r in responses] == [200, 200, 200]
    assert len(seen) == 3
    # Clock time is measured at the durable RPM reservation, before forwarding;
    # provider arrival is not a reliable admission clock under CI scheduler jitter.
    assert len(admitted_at) == 3
    for earlier, later in zip(admitted_at, admitted_at[1:]):
        assert later - earlier >= cfg.window_s - 0.001


@run_async_test
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


@run_async_test
async def test_rejects_duplicate_keys_and_same_state_owner(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        settings(tmp_path, api_keys=("same", "same"))
    first = SlidingWindowAdmissions(settings(tmp_path))
    with pytest.raises(RuntimeError, match="another gateway"):
        SlidingWindowAdmissions(settings(tmp_path))
    first.close()


@run_async_test
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


@run_async_test
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
            assert (await session.get("/healthz")).json() == {"ok": True}
    assert requests == []


@run_async_test
async def test_openai_async_sdk_chat_and_sse(tmp_path):
    openai = pytest.importorskip("openai", reason="OpenAI SDK unavailable in isolated test container")
    AsyncOpenAI = getattr(openai, "AsyncOpenAI", None)
    if AsyncOpenAI is None:
        pytest.skip("OpenAI SDK is an uninstalled namespace package in this test environment")
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


@run_async_test
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


@run_async_test
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


@run_async_test
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


@run_async_test
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


@run_async_test
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


@run_async_test
async def test_cancelled_upstream_connect_releases_inflight_slot(tmp_path):
    started = asyncio.Event()

    async def blocked_provider(req):
        started.set()
        await asyncio.Future()  # simulate a provider request cancelled by the worker

    cfg = settings(tmp_path, api_keys=("upstream-A",), safe_rpm=3,
                   max_inflight_per_key=1, max_queue_wait_s=0.1)
    app = create_app(cfg, transport=httpx.MockTransport(blocked_provider))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            task = asyncio.create_task(session.post("/v1/responses", headers={"Authorization": f"Bearer {TOKEN}"}, json={"input": "x"}))
            await asyncio.wait_for(started.wait(), timeout=0.5)
            assert app.state.admissions._inflight == [1]
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert app.state.admissions._inflight == [0]


@run_async_test
async def test_key_fingerprints_are_salted_and_durable_without_plain_secrets(tmp_path):
    import hashlib
    import sqlite3

    cfg = settings(tmp_path, api_keys=("a-high-entropy-test-secret",))
    first = SlidingWindowAdmissions(cfg)
    first_hash = first.ids[0]
    first.close()
    with sqlite3.connect(tmp_path / "admissions.sqlite3") as db:
        salt, = db.execute("SELECT value FROM admission_meta WHERE name='credential_hash_salt'").fetchone()
        assert len(salt) == 32
        assert first_hash == hashlib.pbkdf2_hmac("sha256", b"a-high-entropy-test-secret", salt, 200_000).hex()
        assert b"a-high-entropy-test-secret" not in (tmp_path / "admissions.sqlite3").read_bytes()
    second = SlidingWindowAdmissions(cfg)
    assert second.ids[0] == first_hash
    second.close()


@run_async_test
@pytest.mark.parametrize("fail_on", ["http.response.start", "http.response.body"])
async def test_disconnect_before_first_stream_byte_releases_slot(tmp_path, fail_on):
    """ASGI failures before or during first body send cannot strand a slot."""
    provider_reads = []

    async def mock(req):
        provider_reads.append(req.url.path)
        return streamed_json({"ok": True})

    app = create_app(settings(tmp_path, api_keys=("upstream-A",)),
                     transport=httpx.MockTransport(mock))
    token = f"Bearer {TOKEN}".encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "scheme": "http", "method": "POST", "path": "/v1/responses",
        "raw_path": b"/v1/responses", "query_string": b"",
        "headers": [(b"authorization", token), (b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8311),
    }
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": b'{}', "more_body": False}
        await asyncio.Future()

    async def disconnected_send(message):
        if message["type"] == fail_on:
            raise RuntimeError("client disconnected during response")

    async with app.router.lifespan_context(app):
        with pytest.raises(RuntimeError, match="client disconnected"):
            await asyncio.wait_for(app(scope, receive, disconnected_send), 1)
        assert provider_reads == ["/v1/responses"]
        assert app.state.admissions._inflight == [0]


@run_async_test
async def test_disconnect_while_queued_drops_ticket_without_provider_call(tmp_path):
    """A departed HTTP client cannot spend provider credits after local backpressure."""
    upstream_calls = []

    def provider(req):
        upstream_calls.append(req.url.path)
        return streamed_json({"ok": True})

    cfg = settings(tmp_path, api_keys=("upstream-A",), safe_rpm=1,
                   window_s=0.5, max_queue_wait_s=0.35)
    app = create_app(cfg, transport=httpx.MockTransport(provider))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "scheme": "http", "method": "POST", "path": "/v1/responses",
        "raw_path": b"/v1/responses", "query_string": b"",
        "headers": [(b"authorization", f"Bearer {TOKEN}".encode()),
                    (b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8311),
    }

    async with app.router.lifespan_context(app):
        admission = app.state.admissions
        assert await admission.acquire(time.monotonic() + 0.05) == 0
        await admission.release(0)
        incoming = asyncio.Queue()
        await incoming.put({"type": "http.request", "body": b'{"input":"x"}',
                            "more_body": False})
        sent = []

        async def send(message):
            sent.append(message)

        task = asyncio.create_task(app(scope, incoming.get, send))
        for _ in range(100):
            if admission.pending == 1:
                break
            await asyncio.sleep(0.002)
        assert admission.pending == 1
        await incoming.put({"type": "http.disconnect"})
        await asyncio.wait_for(task, timeout=0.2)
        assert admission.pending == 0
        assert admission._inflight == [0]
        assert upstream_calls == []
        assert (await admission.snapshot())["slots"][0]["used_in_window"] == 1


@run_async_test
async def test_cancelled_queued_asgi_task_leaves_no_waiter_or_upstream_send(tmp_path):
    upstream_calls = []
    cfg = settings(tmp_path, api_keys=("upstream-A",), safe_rpm=1,
                   window_s=0.5, max_queue_wait_s=0.35)
    app = create_app(cfg, transport=httpx.MockTransport(
        lambda req: upstream_calls.append(req.url.path) or streamed_json({"ok": True})
    ))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "scheme": "http", "method": "POST", "path": "/v1/responses",
        "raw_path": b"/v1/responses", "query_string": b"",
        "headers": [(b"authorization", f"Bearer {TOKEN}".encode()),
                    (b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8311),
    }

    async with app.router.lifespan_context(app):
        admission = app.state.admissions
        assert await admission.acquire(time.monotonic() + 0.05) == 0
        await admission.release(0)
        incoming = asyncio.Queue()
        await incoming.put({"type": "http.request", "body": b"{}",
                            "more_body": False})

        async def send(_message):
            return None

        task = asyncio.create_task(app(scope, incoming.get, send))
        for _ in range(100):
            if admission.pending == 1:
                break
            await asyncio.sleep(0.002)
        assert admission.pending == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert admission.pending == 0
        assert admission._inflight == [0]
        assert upstream_calls == []


@run_async_test
async def test_local_status_requires_token_and_reports_no_credentials(tmp_path):
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: streamed_json({"ok": True})
    ))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as session:
            assert (await session.get("/statusz")).status_code == 401
            headers = {"Authorization": f"Bearer {TOKEN}"}
            initial = (await session.get("/statusz", headers=headers)).json()
            assert initial["pending"] == 0
            assert initial["slots"] == [
                {"slot": 1, "used_in_window": 0, "remaining_in_window": 1, "inflight": 0},
                {"slot": 2, "used_in_window": 0, "remaining_in_window": 1, "inflight": 0},
            ]
            assert (await session.get("/v1/models", headers=headers)).status_code == 200
            status = (await session.get("/statusz", headers=headers)).json()
            assert status["slots"][0]["used_in_window"] == 1
            assert status["slots"][1]["remaining_in_window"] == 1
            assert "upstream-A" not in json.dumps(status)
            assert "upstream-B" not in json.dumps(status)


@run_async_test
async def test_shared_org_ceiling_queues_across_keys_and_survives_restart(tmp_path):
    fake_time = [1000.0]
    cfg = settings(tmp_path, safe_rpm=3, safe_rpm_shared=1, window_s=0.1)
    first = SlidingWindowAdmissions(cfg, clock=lambda: fake_time[0])
    assert await first.acquire(time.monotonic() + 0.05) == 0
    await first.release(0)
    with pytest.raises(QueueExpired):
        await first.acquire(time.monotonic() + 0.015)
    assert (await first.snapshot())["shared_remaining_in_window"] == 0
    first.close()

    second = SlidingWindowAdmissions(cfg, clock=lambda: fake_time[0])
    with pytest.raises(QueueExpired):
        await second.acquire(time.monotonic() + 0.015)
    fake_time[0] += 0.11
    # Cursor placement is deliberately process-local; aggregate capacity is durable.
    slot = await second.acquire(time.monotonic() + 0.05)
    assert slot in (0, 1)
    await second.release(slot)
    second.close()


def test_shared_org_ceiling_rejects_nonpositive_values(tmp_path):
    with pytest.raises(ValueError, match="SAFE_RPM_SHARED"):
        settings(tmp_path, safe_rpm_shared=0)


@run_async_test
async def test_shared_org_ceiling_counts_retired_key_admissions_after_rotation(tmp_path):
    fake_time = [1500.0]
    first_config = settings(tmp_path, api_keys=("old-key", "shared-key"),
                            safe_rpm=3, safe_rpm_shared=1, window_s=0.1)
    first = SlidingWindowAdmissions(first_config, clock=lambda: fake_time[0])
    assert await first.acquire(time.monotonic() + 0.05) == 0
    await first.release(0)
    first.close()

    new_config = settings(tmp_path, api_keys=("replacement-key", "shared-key"),
                          safe_rpm=3, safe_rpm_shared=1, window_s=0.1)
    new = SlidingWindowAdmissions(new_config, clock=lambda: fake_time[0])
    assert (await new.snapshot())["shared_used_in_window"] == 1
    with pytest.raises(QueueExpired):
        await new.acquire(time.monotonic() + 0.015)
    fake_time[0] += 0.11
    slot = await new.acquire(time.monotonic() + 0.05)
    await new.release(slot)
    new.close()


@run_async_test
async def test_pending_byte_budget_rejects_oversized_queued_body(tmp_path):
    cfg = settings(tmp_path, api_keys=("upstream-A",), safe_rpm=1,
                   window_s=0.5, max_queue_wait_s=0.12, max_pending_bytes=5)
    limiter = SlidingWindowAdmissions(cfg)
    assert await limiter.acquire(time.monotonic() + 0.05) == 0
    await limiter.release(0)
    pending = asyncio.create_task(limiter.acquire(time.monotonic() + 0.10, weight=4))
    await asyncio.sleep(0.02)
    assert limiter.pending == 1
    with pytest.raises(QueueFull):
        await limiter.acquire(time.monotonic() + 0.03, weight=4)
    with pytest.raises(QueueExpired):
        await pending
    assert limiter.pending == 0
    assert (await limiter.snapshot())["pending_bytes"] == 0
    limiter.close()


@run_async_test
async def test_httpx_pool_matches_durable_admission_capacity(tmp_path):
    """No HTTPX default 100-connection bottleneck below the limiter's slots."""
    cfg = settings(tmp_path, api_keys=("upstream-A", "upstream-B"),
                   max_inflight_per_key=128)
    app = create_app(cfg)
    async with app.router.lifespan_context(app):
        pool = app.state.upstream._transport._pool
        assert pool._max_connections == 256
        assert pool._max_keepalive_connections <= pool._max_connections


@run_async_test
async def test_nonloopback_peer_cannot_read_health_status_or_spend(tmp_path):
    upstream_calls = []
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: upstream_calls.append(req) or streamed_json({"ok": True})
    ))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("198.51.100.2", 443)),
            base_url="http://proxy",
        ) as session:
            for url in ("/healthz", "/statusz", "/v1/models"):
                result = await session.get(url, headers={"Authorization": f"Bearer {TOKEN}"})
                assert result.status_code == 403
    assert upstream_calls == []


@run_async_test
async def test_oversized_provider_error_body_is_bounded_and_releases_slot(tmp_path):
    cfg = settings(tmp_path, api_keys=("upstream-A",), max_body_bytes=64)
    app = create_app(cfg, transport=httpx.MockTransport(
        lambda req: httpx.Response(429, headers={"content-type": "application/json"},
                                   stream=httpx.ByteStream(b"x" * 1024))
    ))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://proxy"
        ) as session:
            response = await session.get("/v1/models", headers={"Authorization": f"Bearer {TOKEN}"})
            assert response.status_code == 502
            assert response.json()["error"]["message"] == "upstream error response too large"
        assert app.state.admissions._inflight == [0]


def test_worker_sdk_binds_idempotency_to_one_logical_request(monkeypatch):
    pytest.importorskip("openai")
    from ops.native_fabric.experiential_proxy.worker_client import new_client
    monkeypatch.setenv("FABRIC_PROXY_TOKEN", TOKEN)
    monkeypatch.setenv("FABRIC_REQUEST_ID", "one-logical-call")
    with new_client() as sdk:
        assert sdk.default_headers["Idempotency-Key"] == "one-logical-call"
    with new_client(request_id="a-different-logical-call") as sdk:
        assert sdk.default_headers["Idempotency-Key"] == "a-different-logical-call"

@run_async_test
async def test_real_httpx_socket_pool_allows_all_admitted_connections(tmp_path, monkeypatch):
    """The real HTTPX connection pool must not starve locally admitted streams."""
    from ops.native_fabric.experiential_proxy import gateway as gateway_module
    arrived = 0
    both_arrived = asyncio.Event()

    async def fake_provider(reader, writer):
        nonlocal arrived
        try:
            await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=3)
            arrived += 1
            if arrived == 2:
                both_arrived.set()
            # A pool size of one deadlocks here and fails this regression.
            await asyncio.wait_for(both_arrived.wait(), timeout=3)
            payload = b'{"object":"list","data":[]}'
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                + b"Content-Length: " + str(len(payload)).encode()
                + b"\r\nConnection: close\r\n\r\n" + payload
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    upstream = await asyncio.start_server(fake_provider, host="127.0.0.1", port=0)
    async with upstream:
        port = upstream.sockets[0].getsockname()[1]
        # Explicitly target the ephemeral local fixture; zero vendor calls.
        monkeypatch.setattr(gateway_module, "UPSTREAM", f"http://127.0.0.1:{port}/v1")
        cfg = settings(tmp_path, api_keys=("upstream-A",), safe_rpm=2,
                       max_inflight_per_key=2, window_s=0.3, max_queue_wait_s=3)
        app = create_app(cfg)
        async with app.router.lifespan_context(app):
            assert app.state.upstream._transport._pool._max_connections == 2
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://proxy"
            ) as session:
                async def send():
                    return await session.get("/v1/models", headers={"Authorization": f"Bearer {TOKEN}"})
                responses = await asyncio.gather(send(), send())
                assert [r.status_code for r in responses] == [200, 200]
                assert [r.json() for r in responses] == [
                    {"object": "list", "data": []}, {"object": "list", "data": []}
                ]
        assert arrived == 2
