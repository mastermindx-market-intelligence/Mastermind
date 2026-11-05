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


@pytest.mark.parametrize("path", ["/api/whoami", "/api/v1/key", "/api/v1/credits"])
@pytest.mark.parametrize("mode", ["refusal", "malformed", "oversized"])
def test_metadata_refuses_invalid_or_unsafe_provider_reply(tmp_path, mode, path):
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
                headers = {"Authorization": "Bearer " + LOCAL}
                r = await client.get(path, headers=headers)
                await assert_one_metadata_admission(client, headers)
                assert r.status_code == (403 if mode == "refusal" else 502)
                assert "SENSITIVE-METADATA" not in r.text
                assert PROVIDER not in r.text
                assert LOCAL not in r.text
    asyncio.run(exercise())
    assert seen == [path]


async def assert_one_metadata_admission(client, headers):
    status = (await client.get("/statusz", headers=headers)).json()
    assert status["shared_used_in_window"] == 1
    assert status["pending"] == 0
    assert status["pending_bytes"] == 0
    assert len(status["slots"]) == 1
    assert status["slots"][0]["used_in_window"] == 1
    assert status["slots"][0]["inflight"] == 0


@pytest.mark.parametrize("path, field", [
    ("/api/v1/key", "limit"),
    ("/api/v1/key", "limit_remaining"),
    ("/api/v1/credits", "total_credits"),
    ("/api/v1/credits", "total_usage"),
])
@pytest.mark.parametrize("mode, value", [
    pytest.param("nested", {"secret_provider_key": "SENSITIVE-METADATA"}, id="nested"),
    pytest.param("array", ["SENSITIVE-METADATA"], id="array"),
    pytest.param("true", True, id="true"),
    pytest.param("false", False, id="false"),
    pytest.param("string", "1.0", id="string"),
    pytest.param("null", None, id="null"),
    pytest.param("nan", float("nan"), id="nan"),
    pytest.param("infinity", float("inf"), id="infinity"),
    pytest.param("negative_infinity", float("-inf"), id="negative_infinity"),
    pytest.param("missing", None, id="missing"),
])
def test_financial_metadata_requires_closed_scalar_fields(tmp_path, path, field, mode, value):
    seen = []
    payload = vendor_payload(path)
    if mode == "missing":
        del payload["data"][field]
    else:
        payload["data"][field] = value

    def upstream(request):
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer " + PROVIDER
        assert request.headers.get("idempotency-key") is None
        assert request.url.query == b""
        seen.append(request.url.path)
        # Raw JSON also exercises Python's permissive NaN/Infinity decoder.
        return httpx.Response(
            200, headers={"content-type": "application/json"},
            stream=httpx.ByteStream(json.dumps(payload).encode()),
        )

    app = create_app(
        settings(tmp_path, enable_account_metadata=True, max_inflight_per_key=1),
        transport=httpx.MockTransport(upstream),
    )

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://proxy",
            ) as client:
                headers = {"Authorization": "Bearer " + LOCAL}
                response = await client.get(path, headers=headers)
                await assert_one_metadata_admission(client, headers)
                assert response.status_code == 502
                assert response.json() == {
                    "error": {"message": "invalid provider account metadata"},
                }
                assert "SENSITIVE-METADATA" not in response.text
                assert PROVIDER not in response.text
                assert LOCAL not in response.text

    asyncio.run(exercise())
    assert seen == [path]


@pytest.mark.parametrize("path", ["/api/v1/key", "/api/v1/credits"])
@pytest.mark.parametrize("value", [
    pytest.param(0, id="zero"),
    pytest.param(1.25, id="fractional"),
    pytest.param(-1.25, id="negative_observation"),
    pytest.param(10 ** 400, id="exact_large_integer"),
])
def test_financial_metadata_preserves_finite_json_numbers(tmp_path, path, value):
    seen = []
    fields = (
        ("limit", "limit_remaining")
        if path == "/api/v1/key" else ("total_credits", "total_usage")
    )
    payload = vendor_payload(path)
    payload["data"].update({name: value for name in fields})

    def upstream(request):
        assert request.headers["authorization"] == "Bearer " + PROVIDER
        seen.append(request.url.path)
        return httpx.Response(
            200, headers={"content-type": "application/json"},
            stream=httpx.ByteStream(json.dumps(payload).encode()),
        )

    app = create_app(
        settings(tmp_path, enable_account_metadata=True),
        transport=httpx.MockTransport(upstream),
    )

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://proxy",
            ) as client:
                headers = {"Authorization": "Bearer " + LOCAL}
                response = await client.get(path, headers=headers)
                await assert_one_metadata_admission(client, headers)
                assert response.status_code == 200
                assert response.json() == {"data": {name: value for name in fields}}
                assert "NEVER-FORWARD" not in response.text

    asyncio.run(exercise())
    assert seen == [path]


@pytest.mark.parametrize("path", ["/api/v1/key", "/api/v1/credits"])
def test_financial_metadata_rejects_excessive_json_nesting(tmp_path, path):
    seen = []

    def upstream(request):
        seen.append(request.url.path)
        raw = b'{"data":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"
        return httpx.Response(
            200, headers={"content-type": "application/json"},
            stream=httpx.ByteStream(raw),
        )

    app = create_app(
        settings(tmp_path, enable_account_metadata=True),
        transport=httpx.MockTransport(upstream),
    )

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://proxy",
            ) as client:
                headers = {"Authorization": "Bearer " + LOCAL}
                response = await client.get(path, headers=headers)
                await assert_one_metadata_admission(client, headers)
                assert response.status_code == 502
                assert response.json() == {
                    "error": {"message": "invalid provider account metadata"},
                }

    asyncio.run(exercise())
    assert seen == [path]


@pytest.mark.parametrize("path", ["/api/whoami", "/api/v1/key", "/api/v1/credits"])
@pytest.mark.parametrize("mode", ["refusal", "redirect", "oversized"])
def test_metadata_close_failure_still_releases_admission(tmp_path, path, mode):
    seen, closed, read = [], [], []

    class FailingCloseStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            read.append("body")
            yield b"SENSITIVE-METADATA" + b"x" * (65 * 1024)

        async def aclose(self):
            closed.append("close")
            raise httpx.ReadError("fixture close failure")

    def upstream(request):
        assert request.headers["authorization"] == "Bearer " + PROVIDER
        seen.append(request.url.path)
        status = {"refusal": 403, "redirect": 302, "oversized": 200}[mode]
        return httpx.Response(
            status,
            headers={
                "content-type": "application/json",
                "location": "https://untrusted.example/never-follow",
            },
            stream=FailingCloseStream(),
        )

    app = create_app(
        settings(tmp_path, enable_account_metadata=True, max_inflight_per_key=1),
        transport=httpx.MockTransport(upstream),
    )

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://proxy",
            ) as client:
                headers = {"Authorization": "Bearer " + LOCAL}
                response = await client.get(path, headers=headers)
                # A failed close stays a failed cleanup, without stranding the
                # admission slot or pretending the provider operation succeeded.
                assert response.status_code == 500
                assert response.text == "Internal Server Error"
                assert "SENSITIVE-METADATA" not in response.text
                assert PROVIDER not in response.text
                assert LOCAL not in response.text
                await assert_one_metadata_admission(client, headers)

    asyncio.run(exercise())
    assert seen == [path]
    assert closed == ["close"]
    assert read == (["body"] if mode == "oversized" else [])
