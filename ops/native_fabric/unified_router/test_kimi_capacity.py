"""Adversarial admission tests; all inference is local MockTransport traffic."""
import asyncio
import dataclasses
import hashlib
import json
import math
import time
import threading
from pathlib import Path

import httpx
import pytest

from ops.native_fabric.unified_router.gateway import Settings, create_app, _routes_from_document
from ops.native_fabric.unified_router.model_policy import ModelPolicyState, prefix_signature
from ops.native_fabric.unified_router.routes import Route, RouteState, RateWindow
from ops.native_fabric.unified_router.overflow import Overflow
from ops.native_fabric.unified_router.config_refresh import read_document
from ops.native_fabric.unified_router.gateway import _retry_after_s

TOKEN = "test-only-router-token-abcdefghijklmnopqrstuvwxyz"
KIMI = "kimi-k3.1-pro"


def configuration(tmp_path):
    routes = tuple(Route(rid, "gateway", "https://api.morphllm.com/v1", "openai", (KIMI,),
        gateway_token_env="KIMI_TEST_TOKEN", session_header="x-session-id") for rid in ("seat1", "seat2"))
    routes += (Route("glm", "gateway", "https://fixture.example", "anthropic", ("glm-5.3",),
                     gateway_token_env="KIMI_TEST_TOKEN"),)
    groups = {name: {"strategy": "balanced", "capacity_aware": True,
        "weights": {KIMI: 100, "glm-5.3": 1}, "routes": {KIMI: ["seat1", "seat2"], "glm-5.3": ["glm"]}}
        for name in ("auto", "fabric/balanced", "fabric/kimi-preferred")}
    policy = {"groups": groups, "affinity_wait_s": 0, "resources": {
        rid: {"key": rid + "-kimi", "input_tpm": 24290, "output_tpm": 6162,
            "input_basis": "uncached", "max_inflight": 1, "allow_one_oversize": False,
            "headroom": 0.9, "strict_output_reservation": True, "alias_max_output_tokens": 4096,
            "require_observed_cache": True, "provider_headers": True} for rid in ("seat1", "seat2")}}
    return Settings(TOKEN, tmp_path, routes=routes, aliases=tuple((name, (KIMI, "glm-5.3")) for name in groups),
        model_routing=policy, capacity_wait_s=0.02)


def state(tmp_path):
    cfg = configuration(tmp_path)
    return cfg, ModelPolicyState(cfg.routes, cfg.aliases, cfg.model_routing, RateWindow(), RouteState())


def body(model="auto", maximum=32768):
    return {"model": model, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": maximum}


def headers(inp=24000, out=6000, input_limit=24290, output_limit=6162):
    return {"x-morph-ultra-uncached-input-limit": str(input_limit),
        "x-morph-ultra-uncached-input-remaining": str(inp),
        "x-morph-ultra-output-limit": str(output_limit),
        "x-morph-ultra-output-remaining": str(out)}


def response(request, *, out=100, finish="stop"):
    value = json.loads(request.content)
    return httpx.Response(200, headers=headers(), json={"id": "test", "model": value["model"],
        "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 30, "completion_tokens": out}})


def test_whole_output_ceiling_is_reserved_and_exact_ceiling_is_preserved(tmp_path):
    cfg, p = state(tmp_path); now = time.monotonic(); r = cfg.routes[0]
    assert p.estimate(r, KIMI, body(), None, now)[1] == 4096
    assert p.estimate(r, KIMI, body(KIMI), None, now)[1] == 32768
    assert math.isinf(p.eta(r, KIMI, body(KIMI), None, now))
    a = p.begin(r, KIMI, body(), "s", "auto", now)
    assert a.effective_max_tokens == 4096 and a.requested_max_tokens == 32768
    assert p.eta(r, KIMI, body(), "other", now) > 0
    assert p.eta(cfg.routes[1], KIMI, body(), "other", now) == 0
    assert p.window.totals("seat1-kimi", now)[1] == 4096


def test_one_cooling_seat_does_not_divert_a_ready_second_seat(tmp_path):
    cfg, p = state(tmp_path); now = time.monotonic()
    p.policy["overflow"] = {"enabled": True, "families": {"kimi": {"match": ["kimi-"], "target": "glm-5.3"}}}
    wrapped = Overflow(p)
    p.route_state.cooldown_until["seat1"] = now + 65
    wrapped._mark_unhealthy("kimi", now, "provider_429")
    request = body(KIMI, 128)
    ladder, _, decision, _ = wrapped.plan([(KIMI, "")], request, "new", "n", now,
                                           fingerprint=prefix_signature(request))
    assert ladder[0][0].route_id == "seat2" and decision == "exact_model"
    p.route_state.cooldown_until["seat2"] = now + 65
    ladder, _, decision, _ = wrapped.plan([(KIMI, "")], request, "next", "m", now,
                                           fingerprint=prefix_signature(request))
    assert ladder[0][1] == "glm-5.3" and decision == "overflow_new_session"


def test_provider_output_header_is_pre_completion_and_refunds_actual_usage(tmp_path):
    cfg, p = state(tmp_path); now = time.monotonic(); r = cfg.routes[0]
    a = p.begin(r, KIMI, body(), "s", "auto", now)
    p.observe_headers(r, headers(), a, now=now)
    view = p.provider_capacity["seat1-kimi"]
    assert view["output"]["remaining"] == pytest.approx(6162 * .9 - 4096)
    assert a.token not in view["input"]["reserved"]
    p.observe_usage(a, {"prompt_tokens": 30, "completion_tokens": 128}, "openai")
    p.finish(a, success=True)
    assert view["output"]["remaining"] == pytest.approx(6162 * .9 - 128)
    assert view["input"]["remaining"] == pytest.approx(24290 * .9)
    assert p.window.totals("seat1-kimi", time.monotonic()) == (30, 128)


def test_external_remaining_and_lower_limits_bound_new_admission(tmp_path):
    cfg, p = state(tmp_path); now = time.monotonic(); r = cfg.routes[0]
    p.observe_headers(r, headers(out=100), now=now)
    assert p.eta(r, KIMI, body(), None, now) == pytest.approx(60)
    p.observe_headers(r, headers(output_limit=1000), now=now)
    assert p.resources["seat1"]["output_tpm"] == 1000
    p.observe_headers(r, headers(output_limit=99999, out=99999), now=now)
    assert p.resources["seat1"]["output_tpm"] == 1000
    assert p.provider_capacity["seat1-kimi"]["output"]["limit"] == 900


@pytest.mark.parametrize("bad", ["NaN", "inf", "1.0", "True", "999999999999999999", "-5", "١٢"])
def test_malformed_headers_cannot_grant_capacity(tmp_path, bad):
    cfg, p = state(tmp_path); r = cfg.routes[0]; now = time.monotonic()
    p.observe_headers(r, headers(out=1), now=now)
    old = p.provider_capacity["seat1-kimi"]["output"].copy()
    p.observe_headers(r, {"x-morph-ultra-output-limit": bad, "x-morph-ultra-output-remaining": "9999"}, now=now + 1)
    assert p.provider_capacity["seat1-kimi"]["output"] == old


def test_unverified_first_cache_hit_is_not_admission_credit(tmp_path):
    cfg, p = state(tmp_path); now = time.monotonic(); r = cfg.routes[0]; request = body()
    cold = p.estimate(r, KIMI, request, "s", now)[0]
    a = p.begin(r, KIMI, request, "s", "auto", now)
    p.observe_usage(a, {"prompt_tokens": 30, "completion_tokens": 10}, "openai")
    p.finish(a, success=True)
    assert p.estimate(r, KIMI, request, "s", time.monotonic())[0] == cold


def test_aliases_sharing_a_seat_cannot_double_book(tmp_path):
    cfg, p = state(tmp_path); r = cfg.routes[0]; now = time.monotonic()
    alias = dataclasses.replace(r, route_id="same-seat-alias")
    p.routes[alias.route_id] = alias
    p.resources[alias.route_id] = dict(p.resources[r.route_id])
    p.begin(r, KIMI, body(), "s", "auto", now)
    assert p.eta(alias, KIMI, body(), "other", now) > 0


async def request_with(cfg, handler, payload, setup=None):
    app = create_app(cfg, transport=httpx.MockTransport(handler))
    key = hashlib.sha256(b"test-conversation").hexdigest()
    app.state.model_policy.sticky[(payload["model"], key)] = (KIMI, "seat1", time.monotonic())
    if setup:
        setup(app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)), base_url="http://test") as client:
            result = await client.post("/v1/messages", json=payload, headers={
                "authorization": "Bearer " + TOKEN, "x-session-id": "test-conversation"})
    return result, app


def test_wire_cap_is_enforced_after_model_overrides_and_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("KIMI_TEST_TOKEN", "fixture-only"); cfg = configuration(tmp_path); seen = []
    cfg = dataclasses.replace(cfg, routes=(dataclasses.replace(cfg.routes[0],
        model_params={KIMI: {"max_tokens": 99999, "max_completion_tokens": 99999}}), *cfg.routes[1:]))
    def handle(request):
        seen.append((json.loads(request.content), dict(request.headers)))
        return response(request, finish="length")
    result, app = asyncio.run(request_with(cfg, handle, body()))
    assert result.status_code == 200
    assert seen[0][0]["max_tokens"] == seen[0][0]["max_completion_tokens"] == 4096
    assert seen[0][1]["x-session-id"].startswith("fabric-")
    assert result.headers["x-fabric-requested-max-tokens"] == "32768"
    assert result.headers["x-fabric-effective-max-tokens"] == "4096"
    assert app.state.model_policy.events[-1]["finish_reason"] == "length"


def test_partial_stream_keeps_full_reservation_and_never_replays(tmp_path, monkeypatch):
    monkeypatch.setenv("KIMI_TEST_TOKEN", "fixture-only"); seen = []
    def handle(request):
        seen.append(request)
        return httpx.Response(200, content='data: {"choices":[{"delta":{"content":"partial"}}],"usage":{"prompt_tokens":30,"completion_tokens":1}}\n\n',
                              headers={"content-type": "text/event-stream"})
    result, app = asyncio.run(request_with(configuration(tmp_path), handle, dict(body(), stream=True)))
    assert "FABRIC_STREAM_INCOMPLETE" in result.text and len(seen) == 1
    p = app.state.model_policy
    assert p.window.totals("seat1-kimi", time.monotonic())[1] == 4096
    assert p.route_state.cooldown_until["seat1"] > time.monotonic()
    assert p.recovery_until["seat1-kimi"] > time.monotonic() + 950
    assert p.eta(p.routes["seat1"], KIMI, body(), None, time.monotonic() + 61) > 800
    assert p.eta(p.routes["seat2"], KIMI, body(), None, time.monotonic()) == 0


def test_known_rejection_and_pre_send_failure_do_not_quarantine_a_seat(tmp_path):
    cfg, p = state(tmp_path); now = time.monotonic()
    for sent in (True, False):
        a = p.begin(cfg.routes[0], KIMI, body(), "s", "auto", now)
        a.sent = sent
        p.finish(a, no_send=True)
    assert not p.recovery_until and not p.window._pending


@pytest.mark.parametrize("maximum", [True, False, 0, -1, 1.5, 1000001])
def test_invalid_output_limits_are_rejected_before_upstream(tmp_path, monkeypatch, maximum):
    monkeypatch.setenv("KIMI_TEST_TOKEN", "fixture-only"); calls = []
    def handle(request):calls.append(request);return response(request)
    result, _ = asyncio.run(request_with(configuration(tmp_path), handle, body(maximum=maximum)))
    assert result.status_code == 400 and not calls


def test_safe_limit_tightening_does_not_block_unrelated_admissions(tmp_path):
    cfg = configuration(tmp_path)
    def document(cfg):
        rows = [dataclasses.asdict(r) for r in cfg.routes]
        for row in rows:
            row["rate_limit"] = dict(row["rate_limit"]); row["upstream_model"] = dict(row["upstream_model"])
        return {"routes": rows, "aliases": dict(cfg.aliases), "model_routing": cfg.model_routing}
    doc = document(cfg); path = tmp_path / "routes.json"
    path.write_text(json.dumps(doc)); path.chmod(0o600)
    _, digest = read_document(path)
    app = create_app(dataclasses.replace(cfg, routes_path=path, routes_digest=digest))
    p = app.state.model_policy; a = p.begin(cfg.routes[0], KIMI, body(), "s", "auto", time.monotonic())
    doc["model_routing"]["resources"]["seat1"]["output_tpm"] = 5000
    doc["model_routing"]["resources"]["seat1"]["alias_max_output_tokens"] = 2048
    path.write_text(json.dumps(doc))
    assert app.state.config_refresh.refresh(app, _routes_from_document, force=True)
    assert a.effective_max_tokens == 4096
    assert p.estimate(cfg.routes[0], KIMI, body(), "other", time.monotonic())[1] == 2048
    assert p.eta(cfg.routes[2], "glm-5.3", body(), None, time.monotonic()) == 0


def test_restart_restores_charges_cooldowns_and_lower_limits(tmp_path):
    cfg, p = state(tmp_path); path = tmp_path / "admission.json"
    p.configure_persistence(path); p.recovery_until.clear()
    r = cfg.routes[0]; a = p.begin(r, KIMI, body(), "s", "auto", time.monotonic())
    p.observe_headers(r, headers(output_limit=6000), a)
    p.observe_usage(a, {"prompt_tokens": 30, "completion_tokens": 100}, "openai")
    p.finish(a, success=True)
    p.route_state.cooldown_until["seat1"] = time.monotonic() + 3600
    assert p.checkpoint()
    _, restored = state(tmp_path); restored.configure_persistence(path)
    assert restored.persistence_restored and not restored.persistence_error
    assert restored.window.totals("seat1-kimi", time.monotonic()) == (30, 100)
    assert restored.route_state.cooldown_until["seat1"] > time.monotonic() + 3590
    assert restored.resources["seat1"]["output_tpm"] == 6000


def test_unclean_restart_quarantines_uncertain_resource(tmp_path):
    cfg, p = state(tmp_path); path = tmp_path / "admission.json"
    p.configure_persistence(path); p.recovery_until.clear()
    p.begin(cfg.routes[0], KIMI, body(), "s", "auto", time.monotonic())
    _, restored = state(tmp_path); restored.configure_persistence(path)
    assert restored.recovery_until["seat1-kimi"] > time.monotonic() + 950
    assert restored.eta(cfg.routes[0], KIMI, body(), None, time.monotonic()) > 950
    assert restored.eta(cfg.routes[1], KIMI, body(), None, time.monotonic()) == 0


def test_corrupt_checkpoint_is_not_a_full_allowance(tmp_path):
    cfg, p = state(tmp_path); path = tmp_path / "admission.json"
    path.write_text('{"schema":"bad"}'); path.chmod(0o600)
    p.configure_persistence(path)
    assert p.persistence_error == "FABRIC_ADMISSION_CHECKPOINT_INVALID"
    assert math.isinf(p.eta(cfg.routes[0], KIMI, body(), None, time.monotonic()))
    assert not p.checkpoint() and path.read_text() == '{"schema":"bad"}'


def test_initial_install_waits_one_window_without_starving_other_models(tmp_path):
    cfg, p = state(tmp_path); p.configure_persistence(tmp_path / "missing.json")
    assert 59 < p.eta(cfg.routes[0], KIMI, body(), None, time.monotonic()) <= 60
    assert p.eta(cfg.routes[2], "glm-5.3", body(), None, time.monotonic()) == 0


def test_capacity_rank_reduces_demand_on_low_headroom(tmp_path):
    cfg, p = state(tmp_path); now = time.monotonic(); request = body(maximum=128)
    p.window.settle("seat1-kimi", now, 21000, 5300)
    p.window.settle("seat2-kimi", now, 21000, 5300)
    assert p.headroom(cfg.routes[0], now) < .05
    counts = {KIMI: 0, "glm-5.3": 0}
    for i in range(200):
        ladder, _, _, _ = p.plan([(KIMI, "auto"), ("glm-5.3", "auto")], request, None, str(i), now)
        counts[ladder[0][1]] += 1
    p.window._samples.clear()
    empty = sum(p.plan([(KIMI, "auto"), ("glm-5.3", "auto")], request, None, str(i), now)[0][0][1] == KIMI
                for i in range(200))
    assert counts[KIMI] < empty


@pytest.mark.parametrize("value", ["inf", "NaN", "-1", "1e309", "999999999999999999999"])
def test_malformed_retry_after_cannot_poison_admission_checkpoint(tmp_path, value):
    assert _retry_after_s(httpx.Response(429, headers={"retry-after": value})) is None
    cfg, p = state(tmp_path); p.configure_persistence(tmp_path / "admission.json")
    p.route_state.record_failure("glm", "fixture", now=time.monotonic(), cooldown_s=float(value), escalate=False)
    assert p.checkpoint() and not p.persistence_error


def test_valid_long_retry_after_is_preserved_across_restart(tmp_path):
    assert _retry_after_s(httpx.Response(429, headers={"retry-after": "1209600"})) == 1209600
    cfg, p = state(tmp_path); path = tmp_path / "admission.json"; p.configure_persistence(path)
    p.route_state.record_failure("seat1", "quota", now=time.monotonic(), cooldown_s=1209600, escalate=False)
    assert p.checkpoint()
    _, restored = state(tmp_path); restored.configure_persistence(path)
    assert restored.route_state.cooldown_until["seat1"] > time.monotonic() + 1209590


@pytest.mark.parametrize("mode", ['success', 'cancel', 'disconnect', 'deadline'])
def test_durable_send_barrier_does_not_block_health_or_send_abandoned_work(tmp_path, monkeypatch, mode):
    from ops.native_fabric.unified_router import admission_state
    monkeypatch.setenv('KIMI_TEST_TOKEN', 'fixture-only')
    entered, release = threading.Event(), threading.Event()
    original = admission_state.write
    writes, sends = [], []
    disconnected = {'value': False}
    if mode == 'disconnect':
        from starlette.requests import Request
        async def is_disconnected(self):
            return disconnected['value']
        monkeypatch.setattr(Request, 'is_disconnected', is_disconnected)
    def slow_write(path, raw):
        writes.append(json.loads(raw))
        if len(writes) == 1:
            entered.set()
            if not release.wait(5):
                raise OSError("controlled test persistence timeout")
        original(path, raw)
    monkeypatch.setattr(admission_state, "write", slow_write)
    def send(request):
        saved = json.loads((tmp_path / "admission-window-v1.json").read_text())
        assert saved['pending'], "upstream send preceded durable reservation"
        sends.append(request)
        return response(request)
    async def run():
        cfg = configuration(tmp_path)
        if mode == 'deadline':
            cfg = dataclasses.replace(cfg, upstream_timeout_s=.02)
        cfg.model_routing['persist_admission_state'] = True
        app = create_app(cfg, transport=httpx.MockTransport(send))
        p = app.state.model_policy; p.recovery_until.clear()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1)), base_url="http://test") as client:
                pending = asyncio.create_task(client.post('/v1/messages', json=body(KIMI, 128),
                    headers={'Authorization': 'Bearer ' + TOKEN}))
                try:
                    assert await asyncio.to_thread(entered.wait, 3), (pending.result().status_code, pending.result().text) if pending.done() else 'request still waiting'
                    assert not sends and not pending.done()
                    assert (await client.get('/healthz')).status_code == 200
                    if mode == 'cancel':
                        pending.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await pending
                        assert not p.active and not sends
                    elif mode == 'disconnect':
                        disconnected['value'] = True
                    elif mode == 'deadline':
                        await asyncio.sleep(.04)
                finally:
                    release.set()
                if mode != 'cancel':
                    result = await pending
                    expected = {'success': 200, 'disconnect': 499, 'deadline': 503}[mode]
                    assert result.status_code == expected
                    assert len(sends) == (1 if mode == 'success' else 0)
                    if mode == 'deadline':
                        assert result.json()['error']['code'] == 'FABRIC_ADMISSION_DEADLINE'
                assert await p.flush_checkpoint()
                saved = json.loads((tmp_path / 'admission-window-v1.json').read_text())
                assert not saved['pending'] and not p.active
                assert p.durable_revision == p.checkpoint_revision
    asyncio.run(run())


def test_async_checkpoint_coalesces_updates_without_stale_overwrite(tmp_path, monkeypatch):
    from ops.native_fabric.unified_router import admission_state
    entered, release = threading.Event(), threading.Event()
    original = admission_state.write
    writes = []
    def slow_write(path, raw):
        writes.append(json.loads(raw))
        if len(writes) == 1:
            entered.set()
            if not release.wait(5):
                raise OSError('controlled test persistence timeout')
        original(path, raw)
    monkeypatch.setattr(admission_state, 'write', slow_write)
    async def run():
        cfg, p = state(tmp_path); path = tmp_path / 'admission.json'
        p.configure_persistence(path); p.recovery_until.clear(); p.async_checkpoints = True
        a = p.begin(cfg.routes[0], KIMI, body(KIMI, 128), 's', KIMI, time.monotonic())
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            p.finish(a, no_send=True)
            for _ in range(20):
                assert p.checkpoint()
        finally:
            release.set()
        assert await p.flush_checkpoint()
        assert len(writes) == 2 and writes[0]['pending'] and not writes[-1]['pending']
        assert not json.loads(path.read_text())['pending']
        assert p.durable_revision == p.checkpoint_revision
    asyncio.run(run())


def test_async_checkpoint_failure_latches_without_retry_storm(tmp_path, monkeypatch):
    from ops.native_fabric.unified_router import admission_state
    attempts = []
    def unavailable(path, raw):
        attempts.append(path)
        raise OSError('controlled unavailable state store')
    monkeypatch.setattr(admission_state, 'write', unavailable)
    async def run():
        cfg, p = state(tmp_path); p.configure_persistence(tmp_path / 'admission.json')
        p.recovery_until.clear(); p.async_checkpoints = True
        p.begin(cfg.routes[0], KIMI, body(KIMI, 128), 's', KIMI, time.monotonic())
        assert not await p.flush_checkpoint()
        for _ in range(20):
            assert not p.checkpoint()
        assert not await p.flush_checkpoint()
        assert len(attempts) == 1 and p.persistence_error
        assert math.isinf(p.eta(cfg.routes[1], KIMI, body(KIMI, 128), None, time.monotonic()))
    asyncio.run(run())


def test_stalled_checkpoint_has_bounded_admission_wait(tmp_path, monkeypatch):
    from ops.native_fabric.unified_router import admission_state
    entered, release = threading.Event(), threading.Event()
    original = admission_state.write
    def blocked(path, raw):
        entered.set()
        if not release.wait(5):
            raise OSError('controlled test persistence timeout')
        original(path, raw)
    monkeypatch.setattr(admission_state, 'write', blocked)
    async def run():
        cfg, p = state(tmp_path); p.configure_persistence(tmp_path / 'admission.json')
        p.recovery_until.clear(); p.async_checkpoints = True
        a = p.begin(cfg.routes[0], KIMI, body(KIMI, 128), 's', KIMI, time.monotonic())
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            assert not await p.flush_checkpoint(timeout_s=.02)
            assert p.persistence_error == 'FABRIC_ADMISSION_CHECKPOINT_TIMEOUT'
            p.finish(a, no_send=True)
            assert not p.active
        finally:
            release.set()
            await p._checkpoint_task
    asyncio.run(run())
