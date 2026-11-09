"""Jev System One route joins the incumbent Experiential proxy admissions.

All provider responses and rate limits are fixtures; no provider network calls.
"""
from __future__ import annotations

import asyncio
import json

import httpx

from ops.native_fabric.experiential_proxy.gateway import Settings, create_app


LOCAL = "test-scoped-proxy-token-not-upstream"
UPSTREAM = "test-upstream-provider-key-not-local"


def run(coro):
    return asyncio.run(coro)


def settings(tmp_path, **overrides):
    cfg = {
        "api_keys": (UPSTREAM,),
        "proxy_token": LOCAL,
        "state_dir": tmp_path,
        "safe_rpm": 5,
        "safe_rpm_shared": 3,
        "window_s": 60.0,
        "max_queue_wait_s": 0.04,
        "max_pending": 3,
        "max_inflight_per_key": 3,
    }
    cfg.update(overrides)
    return Settings(**cfg)


def vendor_reply(path: str):
    if path == "/v1/systemone":
        return httpx.Response(200, headers={"content-type": "application/json"},
            stream=httpx.ByteStream(json.dumps({
                "model": "jev-latest",
                "answers": {"complexity": {"type": "choice",
                    "choice": "C1_ROUTINE_BOUNDED", "confidence": 0.98}},
                "usage": {"input_tokens": 41, "output_tokens": 7},
            }).encode()))
    return httpx.Response(200, headers={"content-type": "application/json"},
                          stream=httpx.ByteStream(b'{"ok":true}'))


def test_jev_and_responses_share_single_durable_rpm_domain(tmp_path):
    seen = []

    def provider(request):
        assert request.headers["authorization"] == "Bearer " + UPSTREAM
        assert request.headers.get("idempotency-key") is None
        seen.append((request.url.path, json.loads(request.content).get("model")))
        return vendor_reply(request.url.path)

    async def scenario():
        app = create_app(settings(tmp_path), transport=httpx.MockTransport(provider))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                          base_url="http://proxy") as client:
                head = {"Authorization": "Bearer " + LOCAL}
                jev = await client.post("/v1/systemone", headers={**head,
                    "Idempotency-Key": "not-guaranteed-for-systemone"},
                    json={"model": "jev-latest", "state": {"task": "fixture"},
                          "questions": {"complexity": {"type": "choice"}}})
                assert jev.status_code == 200, jev.text
                assert jev.json()["model"] == "jev-latest"
                for _ in range(2):
                    r = await client.post("/v1/responses", headers=head,
                                          json={"model": "deepseek-v4.1-flash",
                                                "input": "fixture", "stream": False})
                    assert r.status_code == 200
                status = await client.get("/statusz", headers=head)
                assert status.status_code == 200
                assert status.json()["shared_used_in_window"] == 3
                assert status.json()["shared_rpm_cap"] == 3
                fourth = await client.post("/v1/systemone", headers=head,
                                           json={"model": "jev-latest"})
                assert fourth.status_code == 504
    run(scenario())
    assert seen == [
        ("/v1/systemone", "jev-latest"),
        ("/v1/responses", "deepseek-v4.1-flash"),
        ("/v1/responses", "deepseek-v4.1-flash"),
    ]


def test_systemone_requires_local_auth_and_exact_path(tmp_path):
    seen = []
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda req: seen.append(req) or vendor_reply(req.url.path)
    ))

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                          base_url="http://proxy") as client:
                assert (await client.post("/v1/systemone", json={})).status_code == 401
                assert (await client.post("/v1/systemone",
                    headers={"Authorization": "Bearer bad-token"}, json={})).status_code == 401
                assert (await client.get("/v1/systemone",
                    headers={"Authorization": "Bearer " + LOCAL})).status_code == 404
                assert (await client.post("/v1/systemone/more",
                    headers={"Authorization": "Bearer " + LOCAL}, json={})).status_code == 404
                assert (await client.post("/v1/admin",
                    headers={"Authorization": "Bearer " + LOCAL}, json={})).status_code == 404
    run(scenario())
    assert not seen


def test_systemone_preserves_403_429_402_and_never_rotates(tmp_path):
    observed = []
    async def scenario():
        for case in (403, 429, 402):
            local_seen = []
            def refusal(req):
                local_seen.append(req)
                return httpx.Response(case, headers={"content-type": "application/json"},
                    stream=httpx.ByteStream(json.dumps(
                        {"error": {"code": f"fixture_{case}"}}).encode()))
            local_state = tmp_path/str(case)
            local_state.mkdir(mode=0o700)
            app = create_app(settings(local_state), transport=httpx.MockTransport(refusal))
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                              base_url="http://proxy") as client:
                    got = await client.post("/v1/systemone",
                        headers={"Authorization": "Bearer " + LOCAL},
                        json={"model": "jev-latest"})
                    assert got.status_code == case
                    assert got.json()["error"]["code"] == f"fixture_{case}"
            assert len(local_seen) == 1
            assert local_seen[0].headers["authorization"] == "Bearer " + UPSTREAM
            observed.append(case)
    run(scenario())
    assert observed == [403, 429, 402]


def test_systemone_does_not_forward_scoped_token_or_unsupported_idempotency(tmp_path):
    seen = []
    def provider(req):
        seen.append(req)
        return vendor_reply(req.url.path)
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(provider))

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                          base_url="http://proxy") as client:
                response = await client.post("/v1/systemone",
                    headers={"Authorization": "Bearer " + LOCAL,
                             "Idempotency-Key": "not-supported", "X-Secret": "child-metadata"},
                    json={"model": "jev-latest"})
                assert response.status_code == 200
    run(scenario())
    assert len(seen) == 1
    req = seen[0]
    assert req.headers["authorization"] == "Bearer " + UPSTREAM
    assert req.headers.get("idempotency-key") is None
    assert req.headers.get("x-secret") is None
    assert LOCAL.encode() not in req.content
