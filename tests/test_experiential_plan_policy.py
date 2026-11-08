"""Plan enforcement at the actual gateway, using fixture-only upstream."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from ops.native_fabric.experiential_proxy.gateway import Settings, create_app
from control_plane.experiential_plan_policy import (
    FREE_CHAT_MODELS, FREE_NATIVE_MODELS, PAID_UNCENSORED_MODELS, plan_policy_digest, validate_plan_request,
)

TOKEN = "local-plan-policy-fixture-token"


def exercise(tmp_path, *, mode="free_only", endpoint="chat/completions",
             body=None, upstream_status=200, upstream_body=None):
    seen = []
    def upstream(request):
        assert request.headers.get("x-fabric-plan-policy") is None
        seen.append((request.url.path, request.content))
        data = upstream_body if upstream_body is not None else {"ok": True}
        return httpx.Response(upstream_status, headers={"content-type": "application/json"},
                              stream=httpx.ByteStream(json.dumps(data).encode()))
    cfg = Settings(api_keys=("provider-fixture",), proxy_token=TOKEN,
                   state_dir=tmp_path, plan_policy=mode, enable_account_metadata=True)
    app = create_app(cfg, transport=httpx.MockTransport(upstream))
    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://proxy") as client:
                headers = {"authorization": "Bearer " + TOKEN,
                           "x-plan-policy": "free_and_uncensored",
                           "x-fabric-plan-policy": plan_policy_digest(mode)}
                r = await client.post("/v1/" + endpoint, headers=headers, content=body)
                status = (await client.get("/statusz", headers=headers)).json()
                return r, status
    response, status = asyncio.run(run())
    return response, status, seen


@pytest.mark.parametrize("model", FREE_CHAT_MODELS)
@pytest.mark.parametrize("endpoint", ["responses", "chat/completions"])
def test_included_plain_model_is_recognized_but_funding_is_required(tmp_path, model, endpoint):
    body = json.dumps({"model": model, "input": "fixture"}).encode()
    r, status, seen = exercise(tmp_path, endpoint=endpoint, body=body)
    assert validate_plan_request("free_only", endpoint, body) == "free"
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PLAN_INCLUDED_FUNDING_UNVERIFIED"
    assert not seen
    assert status["slots"][0]["used_in_window"] == 0
    assert status["slots"][0]["inflight"] == 0


@pytest.mark.parametrize("model", PAID_UNCENSORED_MODELS)
def test_paid_models_need_deployment_optin(tmp_path, model):
    body = json.dumps({"model": model}).encode()
    r, status, seen = exercise(tmp_path, body=body)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PLAN_PAID_LANE_DISABLED"
    assert not seen
    assert status["slots"][0]["used_in_window"] == 0


@pytest.mark.parametrize("model", PAID_UNCENSORED_MODELS)
def test_paid_optin_preserves_selected_model(tmp_path, model):
    body = json.dumps({"model": model}).encode()
    r, _, seen = exercise(tmp_path, mode="free_and_uncensored", body=body)
    assert r.status_code == 200
    assert seen == [("/v1/chat/completions", body)]


@pytest.mark.parametrize("body,endpoint,reason", [
    (b'{"model":"deepseek-v4.1-flash:free"}', "responses", "PLAN_MODEL_NOT_ALLOWED"),
    (b'{"model":"glm-5.3-uncensored"}', "responses", "PLAN_MODEL_NOT_ALLOWED"),
    (b'{"model":"gpt-6-luna-decisions"}', "responses", "PLAN_MODEL_PROTOCOL_MISMATCH"),
    (b'{"model":"jev-latest"}', "responses", "PLAN_MODEL_PROTOCOL_MISMATCH"),
    (b'{"model":"clef"}', "systemone", "PLAN_MODEL_PROTOCOL_MISMATCH"),
    (b'{"model":"clef"}', "embeddings", "PLAN_MODEL_PROTOCOL_MISMATCH"),
    (b'{"model":"clef","model":"paid"}', "responses", "PLAN_DUPLICATE_JSON_FIELD"),
    (b'{"model":"clef","temperature":NaN}', "responses", "PLAN_INVALID_JSON"),
    (b'{"model":false}', "responses", "PLAN_EXACT_MODEL_REQUIRED"),
    (b'[]', "responses", "PLAN_JSON_OBJECT_REQUIRED"),
    (b'{', "responses", "PLAN_INVALID_JSON"),
    (b'{"model":"clef","fallbacks":["paid"]}', "responses", "PLAN_ROUTING_OVERRIDE_REFUSED"),
    (b'{"model":"clef","route_id":"paid-route"}', "responses", "PLAN_ROUTING_OVERRIDE_REFUSED"),
])
def test_refusal_is_before_rpm_and_send(tmp_path, body, endpoint, reason):
    r, status, seen = exercise(tmp_path, mode="free_and_uncensored", body=body, endpoint=endpoint)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == reason
    assert not seen
    assert status["slots"][0]["used_in_window"] == 0
    assert status["pending"] == 0


@pytest.mark.parametrize("model,endpoint", FREE_NATIVE_MODELS.items())
def test_native_decision_protocol_still_requires_verified_funding(tmp_path, model, endpoint):
    body = json.dumps({"model": model}).encode()
    r, _, seen = exercise(tmp_path, endpoint=endpoint, body=body)
    assert validate_plan_request("free_only", endpoint, body) == "free"
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PLAN_INCLUDED_FUNDING_UNVERIFIED"
    assert not seen


@pytest.mark.parametrize("code", [402, 403, 429, 500])
def test_provider_refusal_is_once_without_paid_spill(tmp_path, code):
    body = b'{"model":"deepseek-v4.1-flash-uncensored"}'
    r, status, seen = exercise(tmp_path, mode="free_and_uncensored",
                              body=body, upstream_status=code,
                              upstream_body={"error": {"code": "free_limit_reached"}})
    assert r.status_code == code
    assert r.json()["error"]["code"] == "free_limit_reached"
    assert len(seen) == 1
    assert status["slots"][0]["used_in_window"] == 1
    assert status["slots"][0]["inflight"] == 0


def test_legacy_does_not_rewrite_existing_routes(tmp_path):
    body = b'{"model":"old-explicit-model"}'
    r, _, seen = exercise(tmp_path, mode="legacy", body=body)
    assert r.status_code == 200
    assert seen[0][1] == body


def test_policy_cannot_be_misspelled(tmp_path):
    with pytest.raises(ValueError, match="EXPLABS_PLAN_POLICY"):
        Settings(api_keys=("fixture",), proxy_token=TOKEN,
                 state_dir=tmp_path, plan_policy="free")


def test_uncapped_daily_key_limit_stays_null_and_secret_free(tmp_path):
    seen = []
    def upstream(request):
        seen.append(request)
        return httpx.Response(200, json={"data": {
            "limit": None, "limit_remaining": None, "usage": 2,
            "secret": "DO-NOT-EXPOSE", "is_free_tier": False}})
    app = create_app(Settings(api_keys=("fixture",), proxy_token=TOKEN,
        state_dir=tmp_path, enable_account_metadata=True, plan_policy="free_only"),
        transport=httpx.MockTransport(upstream))
    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://proxy") as client:
                return await client.get("/api/v1/key",
                    headers={"authorization": "Bearer " + TOKEN})
    r = asyncio.run(run())
    assert r.status_code == 200
    assert r.json() == {"data": {"limit": None, "limit_remaining": None}}
    assert len(seen) == 1


@pytest.mark.parametrize("sent_mode", [None, "free_and_uncensored"])
def test_missing_or_drifted_policy_fails_before_send(tmp_path, sent_mode):
    seen = []
    app = create_app(Settings(api_keys=("fixture",), proxy_token=TOKEN,
        state_dir=tmp_path, plan_policy="free_only"),
        transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200)))
    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://proxy") as client:
                h = {"authorization": "Bearer " + TOKEN}
                if sent_mode:
                    h["x-fabric-plan-policy"] = plan_policy_digest(sent_mode)
                r = await client.post("/v1/responses", headers=h,
                                      json={"model": "clef"})
                status = (await client.get("/statusz", headers=h)).json()
                return r, status
    r, status = asyncio.run(run())
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PLAN_POLICY_MISMATCH"
    assert not seen and status["slots"][0]["used_in_window"] == 0


def test_sdk_helper_pins_policy_and_disables_retries(monkeypatch):
    pytest.importorskip("openai")
    from ops.native_fabric.experiential_proxy.worker_client import new_client
    monkeypatch.setenv("FABRIC_PROXY_TOKEN", TOKEN)
    monkeypatch.setenv("EXPLABS_PLAN_POLICY", "free_only")
    client = new_client(request_id="one-logical-fixture")
    try:
        assert client.max_retries == 0
        assert client.default_headers["X-Fabric-Plan-Policy"] == plan_policy_digest("free_only")
        assert client.default_headers["Idempotency-Key"] == "one-logical-fixture"
    finally:
        client.close()


def test_nested_gateway_controls_cannot_enable_provider_retry_or_fallback():
    import json
    from control_plane.experiential_plan_policy import validate_plan_request, PlanRequestRefused
    from ops.native_fabric.experiential53.experiential_transport import _build_request_frame
    bad = {"model": "deepseek-v4.1-flash-uncensored", "gateway": {
        "routing": {"allow_fallbacks": True}, "retry": {"max_total_attempts": 8}}}
    with pytest.raises(PlanRequestRefused, match="ROUTING_OVERRIDE"):
        validate_plan_request("free_and_uncensored", "chat/completions", json.dumps(bad).encode())
    good = _build_request_frame("bounded proof", None, 8, "deepseek-v4.1-flash-uncensored")
    assert validate_plan_request("free_and_uncensored", "chat/completions", good) == "paid_uncensored"
