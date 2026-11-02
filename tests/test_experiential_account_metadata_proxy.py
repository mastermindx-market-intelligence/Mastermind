"""Account metadata uses the existing single-key gateway, never direct keys in clients.

HTTPX mocks are the only upstream; no provider traffic or account keys.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from ops.native_fabric.experiential_proxy.gateway import Settings, create_app


LOCAL = "local-scoped-account-proxy-token"
PROVIDER = "host-owned-provider-key-fixture"


def settings(tmp_path, **kw):
    data = {
        "api_keys": (PROVIDER,),
        "proxy_token": LOCAL,
        "state_dir": tmp_path,
        "safe_rpm": 5,
        "safe_rpm_shared": 3,
        "max_queue_wait_s": 0.04,
        "window_s": 60.0,
    }
    data.update(kw)
    return Settings(**data)


def vendor_payload(path):
    if path == "/api/whoami":
        return {"org_id": "org-b-test", "org_slug": "org-b",
                "secret_provider_key": "NEVER-FORWARD", "admin": True}
    if path == "/api/v1/key":
        return {"data": {"limit": 1.0, "limit_remaining": 0.95,
                         "name": "private-provider-key-label", "secret": "NEVER-FORWARD"}}
    if path == "/api/v1/credits":
        return {"data": {"total_credits": 4600, "total_usage": 0,
                         "internal_wallet": "NEVER-FORWARD"}}
    return {"error": {"message": "unreachable"}}


def test_disabled_metadata_has_no_provider_side_effect(tmp_path):
    seen = []
    app = create_app(settings(tmp_path), transport=httpx.MockTransport(
        lambda r: seen.append(r) or httpx.Response(200)))

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                          base_url="http://proxy") as client:
                assert (await client.get("/api/whoami")).status_code == 401
                assert (await client.get("/api/whoami",
                    headers={"Authorization": "Bearer wrong"})).status_code == 401
                h = {"Authorization": "Bearer " + LOCAL}
                assert (await client.get("/api/whoami", headers=h)).status_code == 404
                assert (await client.get("/api/v1/key", headers=h)).status_code == 404
                assert (await client.get("/api/v1/credits", headers=h)).status_code == 404
                assert (await client.get("/api/admin", headers=h)).status_code == 404
                assert (await client.get("/statusz", headers=h)).json()["shared_used_in_window"] == 0
    asyncio.run(exercise())
    assert not seen


def test_metadata_and_inference_use_same_org_rpm_with_secret_reduction(tmp_path):
    seen = []

    def upstream(request):
        assert request.headers["authorization"] == "Bearer " + PROVIDER
        assert request.headers.get("idempotency-key") is None
        assert request.url.query == b""
        seen.append(request.url.path)
        value = vendor_payload(request.url.path)
        return httpx.Response(200, headers={"content-type": "application/json"},
                              stream=httpx.ByteStream(json.dumps(value).encode()))

    app = create_app(settings(tmp_path, enable_account_metadata=True),
                     transport=httpx.MockTransport(upstream))

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                          base_url="http://proxy") as client:
                headers = {"Authorization": "Bearer " + LOCAL}
                r = await client.get("/api/whoami?secret=not-forwarded", headers=headers)
                assert r.status_code == 200 and r.json() == {
                    "org_id": "org-b-test", "org_slug": "org-b"}
                r = await client.get("/api/v1/key", headers=headers)
                assert r.status_code == 200 and r.json() == {
                    "data": {"limit": 1.0, "limit_remaining": 0.95}}
                r = await client.get("/api/v1/credits", headers=headers)
                assert r.status_code == 200 and r.json() == {
                    "data": {"total_credits": 4600, "total_usage": 0}}
                for response in (r,):
                    assert "NEVER-FORWARD" not in response.text
                status = (await client.get("/statusz", headers=headers)).json()
                assert status["shared_used_in_window"] == 3
                assert status["shared_rpm_cap"] == 3
                r = await client.post("/v1/responses", headers=headers,
                                      json={"model": "deepseek-v4.1-flash", "input": "mock"})
                assert r.status_code == 504
                assert (await client.get("/statusz", headers=headers)).json()["shared_used_in_window"] == 3
    asyncio.run(exercise())
    assert seen == ["/api/whoami", "/api/v1/key", "/api/v1/credits"]


def test_metadata_requires_one_provider_key_and_explicit_optin(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="exactly one provider key"):
        settings(tmp_path, api_keys=("one", "two"), enable_account_metadata=True)
    with pytest.raises(ValueError, match="enablement must be boolean"):
        settings(tmp_path, enable_account_metadata="true")
    monkeypatch.setenv("EXPLABS_ACCOUNT_METADATA_ENABLED", "true")
    with pytest.raises(ValueError, match="must be 0 or 1"):
        Settings.from_env()


@pytest.mark.parametrize("mode", ["refusal", "malformed", "oversized"])
def test_metadata_refuses_invalid_or_unsafe_provider_reply(tmp_path, mode):
    seen = []

    def upstream(request):
        seen.append(request.url.path)
        if mode == "refusal":
            return httpx.Response(403, json={"error": {"message": "SENSITIVE-METADATA"}})
        if mode == "malformed":
            return httpx.Response(200, headers={"content-type": "application/json"},
                                  content=b'{"data":{}}')
        return httpx.Response(200, headers={"content-type": "application/json"},
                              content=b'{"org_id":"x","org_slug":"y","padding":"' +
                              b"x" * (65 * 1024) + b'"}')

    app = create_app(settings(tmp_path, enable_account_metadata=True),
                     transport=httpx.MockTransport(upstream))

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                          base_url="http://proxy") as client:
                r = await client.get("/api/whoami",
                    headers={"Authorization": "Bearer " + LOCAL})
                assert r.status_code == (403 if mode == "refusal" else 502)
                assert "SENSITIVE-METADATA" not in r.text
                assert PROVIDER not in r.text
                assert LOCAL not in r.text
    asyncio.run(exercise())
    assert seen == ["/api/whoami"]
