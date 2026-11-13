"""Single-owner concurrency, circuit ordering and metering regressions."""
import asyncio
import dataclasses
import json
import time

import httpx
import pytest

from ops.native_fabric.unified_router import admission_state, gateway
from ops.native_fabric.unified_router.config_refresh import read_document
from ops.native_fabric.unified_router.model_policy import ModelPolicyState
from ops.native_fabric.unified_router.routes import RateWindow, Route, RouteState

TOKEN = "fixture-concurrency-router-token-abcdefghijklmnopqrstuvwxyz"
PAYLOAD = {"model": "model", "max_tokens": 32, "messages": [{"role": "user", "content": "fixture"}]}


def route(name="r", **kwargs):
    return Route(name, "gateway", "https://fixture.example", "anthropic", ("model",),
                 gateway_token_env="CONCURRENCY_FIXTURE_TOKEN", **kwargs)


def policy(routes=None, maximum=8):
    routes = routes or (route(),)
    return ModelPolicyState(routes, (), {"resources": {
        r.route_id: {"key": "subscription-"+r.route_id, "max_inflight": maximum}
        for r in routes}}, RateWindow(), RouteState())


def test_stale_success_and_failure_cannot_reset_or_reopen_newer_circuit():
    health = RouteState()
    now = time.monotonic()
    assert health.record_failure("r", "current", now=now, cooldown_s=10, generation=0)
    assert not health.record_success("r", generation=0, now=now+20)
    assert not health.record_failure("r", "old", now=now+20, cooldown_s=90, generation=0)
    assert health.consecutive_failures["r"] == 1 and health.last_failure["r"][1] == "current"
    assert not health.record_success("r", generation=1, now=now+5)
    assert health.record_success("r", generation=1, now=now+11)
    assert health.generations["r"] == 2 and health.consecutive_failures["r"] == 0
    assert not health.record_failure("r", "late", now=now+12, generation=1)


def test_cooldown_never_shortens_and_late_quota_observation_is_preserved():
    health = RouteState()
    now = time.monotonic()
    health.record_failure("r", "permission", now=now, cooldown_s=86400, escalate=False, generation=0)
    health.record_failure("r", "short", now=now+1, cooldown_s=30, generation=1)
    assert health.cooldown_until["r"] == now+86400
    assert health.record_failure("r", "quota", now=now+2, cooldown_s=172800,
        escalate=False, generation=0, quota=True)
    assert health.cooldown_until["r"] == now+172802


@pytest.mark.parametrize("permission_first", [False, True])
def test_permission_fence_is_preserved_in_both_response_orders(permission_first):
    health = RouteState(); now = time.monotonic()
    observations = [("generic", 30, False), ("permission", 86400, True)]
    if permission_first:
        observations.reverse()
    for index, (reason, delay, permission) in enumerate(observations):
        health.record_failure("r", reason, now=now+index, cooldown_s=delay,
            escalate=False, generation=0, permission=permission)
    assert health.cooldown_until["r"] >= now+86400
    assert not health.record_success("r", generation=0, now=now+60)


def test_recovery_allows_one_current_probe_and_survives_restart(tmp_path):
    p = policy(); r = p.routes["r"]; now = time.monotonic()
    p.route_state.record_failure("r", "fixture", now=now-20, cooldown_s=1, generation=0)
    old = p.begin(r, "model", PAYLOAD, None, "model:model", now)
    assert p.eta(r, "model", PAYLOAD, None, now) > 0
    with pytest.raises(ValueError, match="concurrency"):
        p.begin(r, "model", PAYLOAD, None, "model:model", now)
    p.finish(old, no_send=True)
    checkpoint = tmp_path / "admission.json"
    admission_state.write(checkpoint, admission_state.encode(p))
    restored = policy(); restored.configure_persistence(checkpoint)
    assert restored.persistence_restored and restored.route_state.consecutive_failures["r"] == 1
    current = restored.begin(r, "model", PAYLOAD, None, "model:model", now)
    assert restored.concurrency_eta(r) > 0
    restored.finish(current, success=True)
    assert restored.route_state.record_success("r", generation=current.circuit_generation)
    assert restored.route_state.consecutive_failures["r"] == 0


def test_shared_group_constrains_two_independent_quota_resources():
    routes = tuple(route(name, concurrency_group="shared-local", group_max_in_flight=1) for name in ("a", "b"))
    p = policy(routes); now = time.monotonic()
    first = p.begin(routes[0], "model", PAYLOAD, None, "model:model", now)
    assert p.concurrency_eta(routes[1]) > 0
    assert p.window.totals("subscription-a", now)[1] > 0
    assert p.window.totals("subscription-b", now) == (0, 0)
    with pytest.raises(ValueError, match="concurrency"):
        p.begin(routes[1], "model", PAYLOAD, None, "model:model", now)
    p.finish(first, no_send=True)
    assert p.concurrency_eta(routes[1]) == 0


def test_route_limit_composes_with_resource_limit():
    r = route(max_in_flight=1); p = policy((r,), maximum=4); now = time.monotonic()
    first = p.begin(r, "model", PAYLOAD, None, "model:model", now)
    assert p.concurrency_eta(r) > 0 and len(p.active) == 1
    p.finish(first, no_send=True)
    assert p.concurrency_eta(r) == 0


@pytest.mark.parametrize("kwargs", [{"max_in_flight": True}, {"max_in_flight": -1},
    {"max_in_flight": 1.5}, {"concurrency_group": "g"}, {"group_max_in_flight": 2},
    {"concurrency_group": "g", "group_max_in_flight": False}, {"concurrency_group": "has space", "group_max_in_flight": 2}])
def test_invalid_concurrency_fields_refuse(kwargs):
    with pytest.raises(ValueError):
        route(**kwargs)


def test_conflicting_group_ceilings_refuse():
    with pytest.raises(ValueError, match="conflicting"):
        policy((route("a", concurrency_group="g", group_max_in_flight=1),
                route("b", concurrency_group="g", group_max_in_flight=2)))


def test_metering_occupies_global_slots_without_quota_or_recovery_holds(tmp_path):
    p = policy(maximum=128); r = p.routes["r"]; now = time.monotonic()
    admissions = [p.begin(r, "model", PAYLOAD, None, "model:model", now, operation="count_tokens") for _ in range(128)]
    assert len(p.active) == 128 and p.concurrency_eta(r) > 0
    assert not p.window._pending and not any(p.window._samples.values())
    encoded = admission_state.encode(p)
    assert json.loads(encoded)["pending"] == []
    path = tmp_path / "admission.json"; admission_state.write(path, encoded)
    restored = policy(maximum=128); restored.configure_persistence(path)
    assert not restored.recovery_until
    for admission in admissions:
        p.finish(admission, success=True); p.finish(admission, success=True)
    assert not p.active and p.counters["metering_completed"] == 128
    assert p.counters["completed"] == 0 and not any(p.window._samples.values())


@pytest.mark.parametrize("cancel", [False, True])
def test_count_request_holds_resource_slot_and_releases_once(tmp_path, monkeypatch, cancel):
    monkeypatch.setenv("CONCURRENCY_FIXTURE_TOKEN", "fixture")
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def handler(request):
            calls.append(request); entered.set(); await release.wait()
            return httpx.Response(200, json={"input_tokens": 100000})
        r = route()
        cfg = gateway.Settings(TOKEN, tmp_path, routes=(r,), capacity_wait_s=0,
            model_routing={"resources": {"r": {"key": "subscription-r", "max_inflight": 1,
                "input_tpm": 1, "output_tpm": 1}}})
        app = gateway.create_app(cfg, transport=httpx.MockTransport(handler))
        p = app.state.model_policy
        p.route_state.consecutive_failures["r"] = 1
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)),
                                         base_url="http://router") as client:
                async def post():
                    return await client.post("/v1/messages/count_tokens", json=PAYLOAD, headers={"x-api-key": TOKEN})
                first = asyncio.create_task(post()); await asyncio.wait_for(entered.wait(), 2)
                assert len(p.active) == 1 and not p.window._pending
                second = await post()
                assert second.status_code == 503 and len(calls) == 1
                if cancel:
                    first.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await first
                else:
                    release.set(); reply = await first
                    assert reply.status_code == 200 and app.state.router_state.served == 1
                assert not p.active and not any(p.window._samples.values())
                assert p.route_state.consecutive_failures["r"] == 1
                assert not p.route_state.cooldown_until
                assert p.counters["metering_completed" if not cancel else "metering_failed"] == 1
    asyncio.run(run())


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_count_refusal_never_changes_inference_health(tmp_path, monkeypatch, status):
    monkeypatch.setenv("CONCURRENCY_FIXTURE_TOKEN", "fixture")
    async def run():
        cfg = gateway.Settings(TOKEN, tmp_path, routes=(route(),), capacity_wait_s=0)
        app = gateway.create_app(cfg, transport=httpx.MockTransport(lambda _: httpx.Response(status, json={"error": "fixture"})))
        p = app.state.model_policy; p.route_state.consecutive_failures["r"] = 2
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)), base_url="http://router") as client:
                reply = await client.post("/v1/messages/count_tokens", json=PAYLOAD, headers={"x-api-key": TOKEN})
                assert reply.status_code >= 400
        assert p.route_state.consecutive_failures["r"] == 2 and not p.route_state.generations
        assert not p.route_state.cooldown_until and not p.active and not any(p.window._samples.values())
    asyncio.run(run())


def test_late_real_gateway_success_cannot_clear_newer_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCURRENCY_FIXTURE_TOKEN", "fixture")
    async def run():
        first_entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def handler(request):
            calls.append(request)
            if len(calls) == 1:
                first_entered.set(); await release.wait()
                return httpx.Response(200, json={"type": "message", "content": [], "stop_reason": "end_turn",
                    "usage": {"input_tokens": 4, "output_tokens": 2}})
            return httpx.Response(429, headers={"retry-after": "60"})
        cfg = gateway.Settings(TOKEN, tmp_path, routes=(route(),), capacity_wait_s=0)
        app = gateway.create_app(cfg, transport=httpx.MockTransport(handler))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)), base_url="http://router") as client:
                async def post():
                    return await client.post("/v1/messages", json=PAYLOAD, headers={"x-api-key": TOKEN})
                first = asyncio.create_task(post()); await asyncio.wait_for(first_entered.wait(), 2)
                second = await post()
                assert second.status_code >= 400
                health = app.state.router_state.routes
                generation = health.generations["r"]; deadline = health.cooldown_until["r"]
                release.set(); assert (await first).status_code == 200
                assert health.generations["r"] == generation
                assert health.consecutive_failures["r"] == 1 and health.cooldown_until["r"] == deadline
    asyncio.run(run())


def test_active_limit_tightening_is_safe_but_group_reassignment_requires_drain(tmp_path):
    r = route(concurrency_group="g", group_max_in_flight=3, max_in_flight=3)
    document = {"routes": [dataclasses.asdict(r)]}
    document["routes"][0]["upstream_model"] = {}; document["routes"][0]["rate_limit"] = {}
    path = tmp_path / "routes.json"; path.write_text(json.dumps(document)); path.chmod(0o600)
    _, digest = read_document(path)
    cfg = gateway.Settings(TOKEN, tmp_path, routes=(r,), routes_path=path, routes_digest=digest)
    app = gateway.create_app(cfg); p = app.state.model_policy; now = time.monotonic()
    active = [p.begin(r, "model", PAYLOAD, None, "model:model", now) for _ in range(2)]
    document["routes"][0].update(group_max_in_flight=1, max_in_flight=1)
    path.write_text(json.dumps(document))
    assert app.state.config_refresh.refresh(app, gateway._routes_from_document, force=True)
    assert len(p.active) == 2 and p.concurrency_eta(p.routes["r"]) > 0
    document["routes"][0]["concurrency_group"] = "other"
    path.write_text(json.dumps(document))
    assert not app.state.config_refresh.refresh(app, gateway._routes_from_document, force=True)
    assert p.routes["r"].concurrency_group == "g"
    for admission in active:
        p.finish(admission, no_send=True)
    assert app.state.config_refresh.refresh(app, gateway._routes_from_document, force=True)
    assert p.routes["r"].concurrency_group == "other"
