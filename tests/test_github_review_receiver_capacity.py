"""Real ASGI responses stay independent of slow secret, admission and Slack ports."""
import asyncio
import dataclasses
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from control_plane.github_review_intent import sign_webhook_body
from control_plane.github_review_intent_ingress import ReviewSourceReadDeferred
from integrations import github_review_ingress_asgi as receiver_module
from test_github_review_ingress_asgi import DELIVERY, SECRET, delivery, make


async def request(app):
    payload, sent = delivery(), []
    scope = {
        "type": "http", "method": "POST", "scheme": "https",
        "path": app._settings.delivery_path, "query_string": b"",
        "headers": [(b"host", b"review.example.com"),
                    (b"content-type", b"application/json"),
                    (b"x-github-event", b"pull_request"),
                    (b"x-github-delivery", DELIVERY.encode()),
                    (b"x-hub-signature-256", sign_webhook_body(secret=SECRET, body=payload).encode())],
    }
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}
    async def send(message):
        sent.append(message)
    await app(scope, receive, send)
    return sent[0]["status"], json.loads(sent[1]["body"]), dict(sent[0]["headers"])


async def drain(app):
    while app._inflight:
        await asyncio.gather(*tuple(app._inflight), return_exceptions=True)
        await asyncio.sleep(0)


def test_slow_secret_does_not_block_event_loop_and_saturation_touches_no_ports(monkeypatch):
    monkeypatch.setattr(receiver_module, "MAX_ACTIVE_ADMISSIONS", 1)
    app, secrets, pulls, fabric = make()
    entered, release = threading.Event(), threading.Event()
    original = secrets.webhook_secret

    def blocked(**kwargs):
        entered.set()
        assert release.wait(3)
        return original(**kwargs)

    secrets.webhook_secret = blocked

    async def exercise():
        first = asyncio.create_task(request(app))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            second = await asyncio.wait_for(request(app), timeout=1)
            assert second[0:2] == (503, {"schema": "mastermind.github_review_delivery_http.v1",
                                       "status": "ADMISSION_BUSY"})
            assert second[2][b"retry-after"] == b"1"
            assert pulls.calls == [] and fabric.calls == 0
        finally:
            release.set()
        assert (await first)[0] == 202
        await drain(app)
        assert secrets.calls == [4242] and fabric.calls == 1

    asyncio.run(exercise())


def test_timed_out_worker_keeps_slot_and_cannot_begin_late_admission(monkeypatch):
    monkeypatch.setattr(receiver_module, "MAX_ACTIVE_ADMISSIONS", 1)
    monkeypatch.setattr(receiver_module, "READ_DEADLINE_SECONDS", 0.03)
    app, secrets, pulls, fabric = make()
    entered, release = threading.Event(), threading.Event()
    original = pulls.read_pull_request

    def blocked(**kwargs):
        entered.set()
        assert release.wait(3)
        return original(**kwargs)

    pulls.read_pull_request = blocked

    async def exercise():
        first = asyncio.create_task(request(app))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            status, body, _ = await first
            assert status == 503 and body["status"] == "ADMISSION_EFFECT_UNKNOWN"
            assert (await request(app))[1]["status"] == "ADMISSION_BUSY"
            assert secrets.calls == [4242]
        finally:
            release.set()
        await drain(app)
        assert fabric.calls == 0
        pulls.read_pull_request = original
        monkeypatch.setattr(receiver_module, "READ_DEADLINE_SECONDS", 1.0)
        assert (await request(app))[0] == 202
        await drain(app)
        assert fabric.calls == 1

    asyncio.run(exercise())


def test_known_admission_ack_and_other_pr_are_not_delayed_by_slow_slack(monkeypatch):
    monkeypatch.setattr(receiver_module, "MAX_ACTIVE_ADMISSIONS", 1)
    monkeypatch.setattr(receiver_module, "MAX_ACTIVE_VISIBILITY", 1)
    app, _, pulls, fabric = make()
    entered, release = threading.Event(), threading.Event()

    class Visibility:
        calls = 0
        def notify_review_admitted(self, **kwargs):
            self.calls += 1
            entered.set()
            assert release.wait(3)
        def notify_review_refused(self, **kwargs):
            raise AssertionError("not a new admitted notice")

    visibility = Visibility()
    app._visibility = visibility
    original, head = pulls.read_pull_request, ["a" * 40]
    pulls.read_pull_request = lambda **kw: dataclasses.replace(original(**kw), head_sha=head[0])

    async def exercise():
        try:
            first = await asyncio.wait_for(request(app), timeout=1)
            assert first[0] == 202 and first[1]["visibility"] == "SCHEDULED_BEST_EFFORT"
            assert await asyncio.to_thread(entered.wait, 2)
            head[0] = "c" * 40
            second = await asyncio.wait_for(request(app), timeout=1)
            assert second[0] == 202 and second[1]["visibility"] == "DEFERRED_CAPACITY"
            assert fabric.calls == 2 and visibility.calls == 1
        finally:
            release.set()
        await drain(app)
        assert (await request(app))[1]["status"] == "ALREADY_ADMITTED"
        await drain(app)
        assert visibility.calls == 1

    asyncio.run(exercise())


def test_rate_deferral_returns_server_delay_before_any_admission():
    app, _, pulls, fabric = make()

    def limited(**kwargs):
        raise ReviewSourceReadDeferred("REVIEW_SOURCE_RATE_LIMITED", retry_after_seconds=120)

    pulls.read_pull_request = limited

    async def exercise():
        status, body, headers = await request(app)
        assert status == 503 and body["status"] == "ADMISSION_SOURCE_DEFERRED"
        assert headers[b"retry-after"] == b"120"
        assert fabric.calls == 0
        await drain(app)

    asyncio.run(exercise())


def test_executor_rejection_restores_capacity_before_any_port_call(monkeypatch):
    monkeypatch.setattr(receiver_module, "MAX_ACTIVE_ADMISSIONS", 1)
    app, secrets, pulls, fabric = make()

    async def exercise():
        loop = asyncio.get_running_loop()
        original = loop.run_in_executor

        def rejected(*args, **kwargs):
            raise RuntimeError("executor shutting down")

        monkeypatch.setattr(loop, "run_in_executor", rejected)
        assert (await request(app))[1]["status"] == "ADMISSION_UNAVAILABLE"
        await drain(app)
        assert secrets.calls == pulls.calls == [] and fabric.calls == 0
        monkeypatch.setattr(loop, "run_in_executor", original)
        assert (await request(app))[0] == 202
        await drain(app)
        assert fabric.calls == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("kind", ["admission", "visibility"])
def test_cancelled_pending_slot_bars_late_worker_entry(kind):
    semaphore = threading.BoundedSemaphore(1)
    assert semaphore.acquire(blocking=False)
    slot = receiver_module._WorkerSlot(semaphore)
    touched = []
    slot.release_if_unstarted()
    slot.release_if_unstarted()  # idempotent callback/creation-error cleanup
    with pytest.raises(receiver_module.ReviewIngressUnavailable, match="CANCELLED_BEFORE_START"):
        slot.run(lambda: touched.append(kind))
    assert touched == [] and semaphore.acquire(blocking=False)
    semaphore.release()


@pytest.mark.parametrize("kind", ["admission", "visibility"])
def test_running_slot_cannot_release_capacity_before_real_effect_returns(kind):
    semaphore = threading.BoundedSemaphore(1)
    assert semaphore.acquire(blocking=False)
    slot = receiver_module._WorkerSlot(semaphore)
    entered, release = threading.Event(), threading.Event()
    touched = []

    def effect():
        entered.set()
        assert release.wait(3)
        touched.append(kind)

    with ThreadPoolExecutor(max_workers=1) as executor:
        worker = executor.submit(slot.run, effect)
        try:
            assert entered.wait(2)
            slot.release_if_unstarted()
            assert not semaphore.acquire(blocking=False)
        finally:
            release.set()
        worker.result(timeout=2)
    slot.release_if_unstarted()
    assert touched == [kind] and semaphore.acquire(blocking=False)
    semaphore.release()


def test_cancelled_http_caller_does_not_release_running_admission_or_duplicate_it(monkeypatch):
    monkeypatch.setattr(receiver_module, "MAX_ACTIVE_ADMISSIONS", 1)
    app, _, _, fabric = make()
    entered, release = threading.Event(), threading.Event()
    original = fabric.admit_review_intent

    def blocked(**kwargs):
        entered.set()
        assert release.wait(3)
        return original(**kwargs)

    fabric.admit_review_intent = blocked

    async def exercise():
        first = asyncio.create_task(request(app))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert (await request(app))[1]["status"] == "ADMISSION_BUSY"
        finally:
            release.set()
        await drain(app)
        assert fabric.calls == 1
        assert (await request(app))[1]["status"] == "ALREADY_ADMITTED"
        await drain(app)
        assert fabric.calls == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("upstream_status,expected", [
    (429, "ADMISSION_SOURCE_DEFERRED"),
    (401, "ADMISSION_SOURCE_DEFERRED"),
    (503, "ADMISSION_UNAVAILABLE"),
])
def test_real_actor_permission_read_failure_is_http_deferral_not_permission_verdict(upstream_status, expected):
    import httpx
    from test_github_review_http_recovery import adapter
    app, _, _, fabric = make()
    requests = []

    def wire(req):
        requests.append(req)
        headers = {"retry-after": "120"} if upstream_status == 429 else {}
        return httpx.Response(upstream_status, headers=headers)

    github = adapter(wire)
    app._actors = app._pulls = github

    async def exercise():
        status, body, headers = await request(app)
        assert status == 503 and body["status"] == expected
        assert "reason" not in body and fabric.calls == 0
        assert all(req.url.path.endswith("/collaborators/alice/permission") for req in requests)
        assert len(requests) == (2 if upstream_status == 503 else 1)
        if upstream_status == 429:
            assert headers[b"retry-after"] == b"120"
        await drain(app)

    asyncio.run(exercise())
