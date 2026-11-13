"""Discriminating capacity/fallback regressions; no live provider calls."""
import asyncio
import copy
import json
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from ops.native_fabric.unified_router.gateway import Settings, create_app, _quota_wall_s, _replay_safe
from ops.native_fabric.unified_router import gateway
from ops.native_fabric.unified_router.model_policy import AdmissionCapacityChanged
from ops.native_fabric.unified_router.provider_errors import classify
from ops.native_fabric.unified_router.routes import Route

KIMI, DS, QWEN, OPUS = "kimi-k3.1-pro", "deepseek-v4.1-flash", "qwen4-max-preview", "claude-opus-5-5"
TOKEN = "fixture-router-only-no-secret-123456789"


def config(tmp_path, *, persist=False):
    routes = tuple(Route(rid, "credential_pool", "https://" + host, wire, (model,),
                         env_key="FIXTURE_ONLY", priority=priority)
        for rid, host, wire, model, priority in (
            ("k1", "api.morphllm.com/v1", "openai", KIMI, 5),
            ("k2", "api.morphllm.com/v1", "openai", KIMI, 5),
            ("d1", "api.morphllm.com/v1", "openai", DS, 5),
            ("d2", "api.morphllm.com/v1", "openai", DS, 5),
            ("labs", "labs.example", "anthropic", DS, 20),
            ("q", "qwen.example", "anthropic", QWEN, 10),
            ("o", "opus.example", "anthropic", OPUS, 10)))
    resources = {rid: {"key": rid, "input_tpm": inp, "output_tpm": out,
        "input_basis": "uncached", "headroom": headroom, "max_inflight": cap,
        "strict_output_reservation": True, "alias_max_output_tokens": bound,
        "allow_one_oversize": False, "require_observed_cache": True, "provider_headers": True}
        for rid, inp, out, headroom, cap, bound in (
            ("k1", 24290, 6162, .9, 1, 4096), ("k2", 24290, 6162, .9, 1, 4096),
            ("d1", 400000, 70000, .95, 6, 16384), ("d2", 400000, 70000, .95, 6, 16384))}
    families = {name: {"match": [model], "targets": [QWEN, OPUS],
        "request_boundary_fallback": True, "preference_wait_s": 1.5,
        "return_to_primary_after_s": 300} for name, model in (("kimi", KIMI), ("deepseek", DS))}
    groups = {"fabric/kimi-preferred": {"routes": {KIMI: ["k1", "k2"], QWEN: ["q"], OPUS: ["o"]},
        "weights": {KIMI: 1000, QWEN: 1, OPUS: 1}, "strategy": "ordered", "fallback_models": [QWEN, OPUS]}}
    return Settings(TOKEN, tmp_path, routes=routes,
        aliases=(("fabric/kimi-preferred", (KIMI, QWEN, OPUS)),), capacity_wait_s=.03,
        free_hold_s=0, model_routing={"resources": resources, "groups": groups,
            "exact_route_allowlists": {KIMI: ["k1", "k2"], DS: ["d1", "d2"]},
            "persist_admission_state": persist,
            "overflow": {"enabled": True, "families": families,
                         "caps": {QWEN: {"max_inflight": 1, "max_new_sessions_per_hour": 4},
                                  OPUS: {"max_inflight": 1, "max_new_sessions_per_hour": 4}}}})


def body(model=KIMI, maximum=32768, long=False):
    messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": "fixture"} for i in range(7)]
    if long:
        messages[0]["content"] = "coding context " * 6000
    return {"model": model, "max_tokens": maximum, "messages": messages}


def plan(p, payload, session="s", elapsed=2):
    model = payload["model"]
    candidates = [(m, model) for m in p.aliases[model]] if model in p.aliases else [(model, "")]
    return p.plan(candidates, payload, session, "fixture-nonce", time.monotonic(), elapsed)


def state(tmp_path):
    return create_app(config(tmp_path)).state.model_policy


def success_response(request):
    payload = json.loads(request.content)
    if request.url.path.endswith("/chat/completions"):
        return httpx.Response(200, json={"id": "fixture", "model": payload["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 5}})
    return httpx.Response(200, json={"id": "fixture", "type": "message", "role": "assistant", "model": payload["model"],
        "content": [{"type": "text", "text": "OK"}], "stop_reason": "end_turn",
        "usage": {"input_tokens": 20, "output_tokens": 5}})


async def request(cfg, payload, handler, setup=None):
    app = create_app(cfg, transport=httpx.MockTransport(handler))
    if setup:
        setup(app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)), base_url="http://router") as client:
            result = await client.post("/v1/messages", json=payload, headers={"authorization": "Bearer " + TOKEN, "x-fabric-session-id": "fixture"})
    return result, app


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    monkeypatch.setattr(gateway, "_route_authorization", lambda *args: "fixture-only")


def test_established_kimi_impossible_output_uses_qwen_without_morph_send(tmp_path):
    calls = []
    response, app = asyncio.run(request(config(tmp_path), body(), lambda r: (calls.append(r), success_response(r))[1]))
    assert response.status_code == 200 and len(calls) == 1
    assert response.headers["x-fabric-resolved-model"] == QWEN
    assert response.headers["x-fabric-routing-reason"] == "overflow_output_budget"
    assert json.loads(calls[0].content)["max_tokens"] == 32768
    assert app.state.model_policy.events[-1]["requested_model"] == KIMI


def test_large_cold_context_is_preserved_in_fallback(tmp_path):
    payload = body(maximum=512, long=True)
    calls = []
    response, _ = asyncio.run(request(config(tmp_path), payload, lambda r: (calls.append(r), success_response(r))[1]))
    assert response.status_code == 200 and len(calls) == 1
    assert response.headers["x-fabric-routing-reason"] == "overflow_input_budget"
    assert json.loads(calls[0].content)["messages"] == payload["messages"]


def test_healthy_kimi_sibling_wins_before_fallback(tmp_path):
    p = state(tmp_path); payload = body(maximum=512); now = time.monotonic()
    p.begin(p.routes["k1"], KIMI, payload, "other", "model:" + KIMI, now)
    result = plan(p, payload)
    assert result[0][0][0].route_id == "k2"


def test_busy_seats_get_bounded_grace_then_fallback(tmp_path):
    p = state(tmp_path); payload = body(maximum=512); now = time.monotonic()
    for rid in ("k1", "k2"):
        p.begin(p.routes[rid], KIMI, payload, rid, "model:" + KIMI, now)
    assert plan(p, payload, elapsed=0)[2] == "FABRIC_AFFINITY_WAIT"
    assert plan(p, payload, elapsed=2)[0][0][1] == QWEN


def test_actual_active_turn_is_not_migrated(tmp_path):
    p = state(tmp_path); now = time.monotonic()
    active = p.begin(p.routes["k1"], KIMI, body(maximum=512), "s", "model:" + KIMI, now)
    assert plan(p, body())[2] == "FABRIC_SESSION_ACTIVE"
    p.finish(active, no_send=True)
    assert plan(p, body())[0][0][1] == QWEN


def test_sticky_fallback_respects_cap_and_uses_next_target(tmp_path):
    p = state(tmp_path); now = time.monotonic(); payload = body()
    plan(p, payload, "busy")
    p.begin(p.routes["q"], QWEN, payload, "busy", "model:" + KIMI, now)
    p.overflow.diverted["s"] = [QWEN, now, "kimi", KIMI, now]
    assert plan(p, payload)[0][0][1] == OPUS


def test_sticky_switch_charges_new_target_hourly_cap(tmp_path):
    p = state(tmp_path); now = time.monotonic(); payload = body()
    plan(p, payload, "busy")
    p.begin(p.routes["q"], QWEN, payload, "busy", "model:" + KIMI, now)
    for i in range(4):
        session = "switch-" + str(i)
        p.overflow.diverted[session] = [QWEN, now, "kimi", KIMI, now]
        result = plan(p, payload, session)
        assert result[0][0][1] == OPUS
        a = p.begin(p.routes["o"], OPUS, payload, session, "model:" + KIMI, time.monotonic())
        a.completed = True
        p.finish(a, success=True)
        assert len(p.overflow.cap_sessions[OPUS]) == i + 1
    p.overflow.diverted["s"] = [QWEN, now, "kimi", KIMI, now]
    assert not plan(p, payload)[0]


def test_sticky_switch_rechecks_new_target_hourly_cap_at_begin(tmp_path):
    from collections import deque
    p = state(tmp_path); now = time.monotonic(); payload = body()
    plan(p, payload, "busy")
    p.begin(p.routes["q"], QWEN, payload, "busy", "model:" + KIMI, now)
    p.overflow.diverted["s"] = [QWEN, now, "kimi", KIMI, now]
    assert plan(p, payload)[0][0][1] == OPUS
    p.overflow.cap_sessions[OPUS] = deque([now] * 4)
    with pytest.raises(AdmissionCapacityChanged):
        p.begin(p.routes["o"], OPUS, payload, "s", "model:" + KIMI, now)


def test_eight_qwen_lanes_cannot_consume_all_attempts_before_opus(tmp_path):
    cfg = config(tmp_path)
    q = next(r for r in cfg.routes if r.route_id == "q")
    cfg = replace(cfg, routes=(*cfg.routes, *(replace(q, route_id=f"q{i}") for i in range(7))), max_attempts=5)
    calls = []
    def handler(req):
        calls.append(req.url.host)
        return (httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
                if req.url.host == "qwen.example" else success_response(req))
    reply, _ = asyncio.run(request(cfg, body(), handler))
    assert reply.status_code == 200 and calls == ["qwen.example", "qwen.example", "opus.example"]


@pytest.mark.parametrize("model", [KIMI, DS])
def test_wide_primary_and_qwen_pools_leave_final_attempt_for_opus(tmp_path, model):
    cfg = config(tmp_path)
    primary = next(r for r in cfg.routes if r.models == (model,))
    q = next(r for r in cfg.routes if r.route_id == "q")
    extra = tuple(replace(primary, route_id=f"p{i}", base_url="https://extra-primary.example/v1", priority=20) for i in range(4))
    cfg.model_routing["exact_route_allowlists"][model].extend(r.route_id for r in extra)
    cfg = replace(cfg, routes=(*cfg.routes, *extra, *(replace(q, route_id=f"q{i}") for i in range(7))), max_attempts=5)
    calls = []
    def handler(req):
        calls.append(req.url.host)
        return success_response(req) if req.url.host == "opus.example" else httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
    reply, _ = asyncio.run(request(cfg, body(model, 512), handler))
    assert reply.status_code == 200
    assert calls == ["api.morphllm.com", "api.morphllm.com", "qwen.example", "qwen.example", "opus.example"]
    assert reply.headers["x-fabric-routing-reason"] == "overflow_safe_rejection"


def test_held_substitutes_preserve_later_same_model_candidates(tmp_path):
    cfg = config(tmp_path)
    d = next(r for r in cfg.routes if r.route_id == "d1")
    extra = replace(d, route_id="extra", base_url="https://extra-primary.example/v1", priority=20)
    cfg = replace(cfg, routes=(*cfg.routes, extra), max_attempts=5)
    cfg.model_routing["exact_route_allowlists"][DS].append("extra")
    cfg.model_routing["route_model_holds"] = {"q": {QWEN: "HELD"}, "o": {OPUS: "HELD"}}
    calls = []
    def handler(req):
        calls.append(req.url.host)
        return success_response(req) if req.url.host == "extra-primary.example" else httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
    reply, _ = asyncio.run(request(cfg, body(DS, 512), handler))
    assert reply.status_code == 200 and calls == ["api.morphllm.com", "api.morphllm.com", "extra-primary.example"]


def test_sticky_qwen_rejection_can_reach_opus_with_bounded_attempts(tmp_path):
    cfg = config(tmp_path)
    q = next(r for r in cfg.routes if r.route_id == "q")
    cfg = replace(cfg, routes=(*cfg.routes, *(replace(q, route_id=f"q{i}") for i in range(7))), max_attempts=5)
    calls = []
    def setup(app):
        session = gateway.session_key({"x-fabric-session-id": "fixture"}, body())
        app.state.model_policy.overflow.diverted[session] = [QWEN, time.monotonic(), "kimi", KIMI, time.monotonic()]
    def handler(req):
        calls.append(req.url.host)
        return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}}) if req.url.host == "qwen.example" else success_response(req)
    reply, _ = asyncio.run(request(cfg, body(), handler, setup))
    assert reply.status_code == 200 and calls == ["qwen.example", "qwen.example", "opus.example"]


def test_capacity_race_is_fenced_at_begin(tmp_path):
    p = state(tmp_path); payload = body(); now = time.monotonic()
    plan(p, payload)
    p.begin(p.routes["q"], QWEN, body(), "other", "model:" + KIMI, now)
    with pytest.raises(AdmissionCapacityChanged):
        p.begin(p.routes["q"], QWEN, payload, "s", "model:" + KIMI, now)
    assert len(p.active) == 1


@pytest.mark.parametrize("requested", [KIMI, "fabric/kimi-preferred"])
def test_stale_ladder_cannot_split_active_session_models(tmp_path, requested):
    p = state(tmp_path); now = time.monotonic(); payload = body(requested)
    plan(p, payload)
    profile = "model:" + KIMI if requested == KIMI else requested
    p.begin(p.routes["q"], QWEN, payload, "s", profile, now)
    with pytest.raises(AdmissionCapacityChanged):
        p.begin(p.routes["o"], OPUS, payload, "s", profile, now)
    assert len(p.active) == 1


def test_alias_removed_during_checkpoint_is_ineligible(tmp_path):
    p = state(tmp_path); profile = "fabric/kimi-preferred"; payload = body(profile, 512)
    a = p.begin(p.routes["k1"], KIMI, payload, "s", profile, time.monotonic())
    p.groups.pop(profile)
    assert not p.send_ready(a, time.monotonic())
    p.finish(a, no_send=True)


def test_model_change_does_not_inherit_other_profile_diversion(tmp_path):
    p = state(tmp_path); now = time.monotonic()
    p.overflow.diverted["s"] = [OPUS, now, "kimi", KIMI, now]
    assert plan(p, body(DS, maximum=512))[0][0][1] == DS


def test_recovered_primary_returns_after_stability_interval(tmp_path):
    p = state(tmp_path); now = time.monotonic()
    p.overflow.diverted["s"] = [QWEN, now, "kimi", KIMI, now - 301]
    assert plan(p, body(maximum=512))[0][0][1] == KIMI


def test_preferred_alias_returns_to_ready_primary_after_minimum_residence(tmp_path):
    p = state(tmp_path); now = time.monotonic(); profile = "fabric/kimi-preferred"
    p.overflow.diverted["s"] = [QWEN, now, "profile", profile, now - 301]
    p.sticky[(profile, "s")] = (QWEN, "q", now)
    payload = body(profile, 512)
    result = plan(p, payload)
    assert result[0][0][1] == KIMI and result[2] == "preferred_model_recovered"
    a = p.begin(result[0][0][0], KIMI, payload, "s", profile, now)
    a.completed = True
    p.finish(a, success=True)
    assert "s" not in p.overflow.diverted


def test_preferred_alias_keeps_actual_active_request_model(tmp_path):
    p = state(tmp_path); now = time.monotonic(); profile = "fabric/kimi-preferred"
    payload = body(profile, long=True)
    p.begin(p.routes["q"], QWEN, payload, "s", profile, now)
    p.overflow.diverted["s"][4] = now - 301
    result = plan(p, body(profile, 512))
    assert not result[0]  # Qwen diversion cap is one; don't split into live Kimi.


def test_excluded_labs_cannot_suppress_cross_model_fallback(tmp_path):
    p = state(tmp_path); now = time.monotonic()
    for rid in ("d1", "d2"):
        p.route_state.cooldown_until[rid] = now + 60
    assert "labs" not in [r.route_id for r in p.eligible_routes(DS)]
    assert plan(p, body(DS))[0][0][1] == QWEN


def test_eligible_same_model_provider_precedes_cross_model(tmp_path):
    p = state(tmp_path); now = time.monotonic()
    p.policy["exact_route_allowlists"][DS].append("labs")
    for rid in ("d1", "d2"):
        p.route_state.cooldown_until[rid] = now + 60
    assert plan(p, body(DS))[0][0][0].route_id == "labs"


def test_configured_funding_hold_prevents_provider_send(tmp_path):
    p = state(tmp_path); now = time.monotonic()
    p.policy["exact_route_allowlists"][DS].append("labs")
    p.policy["route_model_holds"] = {"labs": {DS: "PLAN_INCLUDED_FUNDING_UNVERIFIED"}}
    for rid in ("d1", "d2"):
        p.route_state.cooldown_until[rid] = now + 60
    assert plan(p, body(DS))[0][0][1] == QWEN
    assert p.snapshot()["route_model_holds"]["labs"][DS] == "PLAN_INCLUDED_FUNDING_UNVERIFIED"


def test_deepseek_reserves_full_output_and_independent_seat_capacity(tmp_path):
    p = state(tmp_path); now = time.monotonic(); payload = body(DS, maximum=32768)
    for i in range(2):
        a = p.begin(p.routes["d1"], DS, payload, str(i), "model:" + DS, now)
        assert a.output_estimate == 32768
    assert p.eta(p.routes["d1"], DS, payload, "new", now) > 0
    assert p.eta(p.routes["d2"], DS, payload, "new", now) == 0


def test_alias_fallback_cap_uses_same_active_ledger(tmp_path):
    p = state(tmp_path); payload = body("fabric/kimi-preferred", long=True)
    assert plan(p, payload)[0][0][1] == QWEN
    p.begin(p.routes["q"], QWEN, payload, "s", "fabric/kimi-preferred", time.monotonic())
    assert plan(p, body(), "other")[0][0][1] == OPUS


def test_no_send_rolls_back_hourly_diversion_charge(tmp_path):
    p = state(tmp_path); payload = body(); plan(p, payload)
    a = p.begin(p.routes["q"], QWEN, payload, "s", "model:" + KIMI, time.monotonic())
    assert len(p.overflow.cap_sessions[QWEN]) == 1
    p.finish(a, no_send=True)
    assert not p.overflow.cap_sessions[QWEN]


@pytest.mark.parametrize("code", ["insufficient_quota", "AccountQuotaExceeded", "credits_exhausted"])
def test_exhausted_direct_lane_holds_without_reset_and_skips_future_calls(tmp_path, code):
    calls = []
    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"code": code}})
        return success_response(req)
    def setup(app):
        p = app.state.model_policy
        p.sticky[("model:" + DS, gateway.session_key({"x-fabric-session-id": "fixture"}, body(DS)))] = (DS, "d1", time.monotonic())
    response, app = asyncio.run(request(config(tmp_path), body(DS, maximum=512), handler, setup))
    assert response.status_code == 200 and len(calls) == 2
    hold = app.state.router_state.routes.owner_holds["d1"]
    assert hold["category"] == "quota_exhausted"
    assert app.state.model_policy.eta(app.state.model_policy.routes["d1"], DS, body(DS, 512), None, time.monotonic()+999999) == float("inf")


@pytest.mark.parametrize("status,code", [(403, "model_not_granted"), (429, "org_under_review"), (400, "refusal")])
def test_policy_refusal_is_terminal_and_never_cross_provider_replayed(tmp_path, status, code):
    calls = []
    response, app = asyncio.run(request(config(tmp_path), body(maximum=512),
        lambda r: (calls.append(r), httpx.Response(status, json={"error": {"code": code}}))[1]))
    assert response.status_code == status and len(calls) == 1
    route_state = app.state.router_state.routes
    assert len(route_state.owner_holds) + len(route_state.model_holds) == (0 if code == "refusal" else 1)
    assert not app.state.model_policy.active


@pytest.mark.parametrize("status", [500, 502, 503, 504, 529])
def test_unknown_server_error_keeps_reservation_and_quarantine(tmp_path, status):
    calls = []
    response, app = asyncio.run(request(config(tmp_path), body(maximum=512),
        lambda r: (calls.append(r), httpx.Response(status, json={"error": {"code": "all_routes_failed"}}))[1]))
    p = app.state.model_policy
    assert response.status_code >= 500 and len(calls) == 1
    assert p.recovery_until and any(v > time.monotonic() for v in p.recovery_until.values())
    assert sum(p.window.totals(rid, time.monotonic())[1] for rid in ("k1", "k2")) == 512


@pytest.mark.parametrize("status", [503, 529])
def test_typed_admission_rejection_can_fallback(tmp_path, status):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={"error": {"type": "overloaded_error"}}) if len(calls) == 1 else success_response(req)
    response, app = asyncio.run(request(config(tmp_path), body(maximum=512), handler))
    assert response.status_code == 200 and len(calls) == 2
    assert not app.state.model_policy.recovery_until


def test_unknown_hosted_tool_is_not_safe_to_replay():
    assert not _replay_safe({"tools": [{"type": "future_hosted_tool_2027"}]})
    assert _replay_safe({"tools": [{"name": "local_function", "input_schema": {"type": "object"}}]})


def test_strict_checkpoint_failure_replans_to_non_strict_fallback(tmp_path):
    calls = []
    def setup(app):
        async def fail():
            app.state.model_policy.persistence_error = "fixture-disk-unavailable"
            return False
        app.state.model_policy.flush_checkpoint = fail
    response, app = asyncio.run(request(config(tmp_path), body(maximum=512),
        lambda r: (calls.append(r), success_response(r))[1], setup))
    assert response.status_code == 200 and len(calls) == 1
    assert response.headers["x-fabric-resolved-model"] == QWEN
    assert not app.state.model_policy.active


@pytest.mark.parametrize("hold", ["owner", "model", "cooldown", "configured", "allowlist"])
def test_new_hold_during_checkpoint_prevents_that_send(tmp_path, hold):
    calls, invalidated = [], []
    def setup(app):
        p = app.state.model_policy
        async def flush():
            if not invalidated:
                admission = next(iter(p.active.values()))
                invalidated.append(admission.route_id)
                if hold == "configured":
                    p.policy.setdefault("route_model_holds", {})[admission.route_id] = {KIMI: "PLAN_INCLUDED_FUNDING_UNVERIFIED"}
                elif hold == "allowlist":
                    p.policy["exact_route_allowlists"][KIMI].remove(admission.route_id)
                elif hold == "cooldown":
                    p.route_state.record_failure(admission.route_id, "quota", now=time.monotonic(), cooldown_s=600, escalate=False, quota=True)
                else:
                    p.route_state.hold(admission.route_id, "permission", "account_suspended", now=time.monotonic(), model=KIMI if hold == "model" else None)
            return True
        p.flush_checkpoint = flush
    def handler(req):
        calls.append(req)
        return success_response(req)
    reply, _ = asyncio.run(request(config(tmp_path), body(maximum=512), handler, setup))
    assert reply.status_code == 200 and len(calls) == 1
    assert reply.headers["x-fabric-route"] != invalidated[0]


def test_zero_retry_after_does_not_clear_unknown_exhaustion(tmp_path):
    calls = []
    def handler(req):
        calls.append(req)
        return (httpx.Response(429, headers={"retry-after": "0"}, json={"error": {"code": "insufficient_quota"}})
                if len(calls) == 1 else success_response(req))
    reply, app = asyncio.run(request(config(tmp_path), body(maximum=512), handler))
    assert reply.status_code == 200 and len(app.state.router_state.routes.owner_holds) == 1


def test_typed_503_retry_after_is_not_shortened(tmp_path):
    calls = []
    def handler(req):
        calls.append(req)
        return (httpx.Response(503, headers={"retry-after": "600"}, json={"error": {"type": "overloaded_error"}})
                if len(calls) == 1 else success_response(req))
    reply, app = asyncio.run(request(config(tmp_path), body(maximum=512), handler))
    assert reply.status_code == 200
    assert max(app.state.router_state.routes.cooldown_until.values()) - time.monotonic() > 590


def test_unknown_quota_and_hourly_cap_survive_restart(tmp_path):
    cfg = config(tmp_path, persist=True)
    app = create_app(cfg); p = app.state.model_policy
    p.route_state.hold("d1", "quota_exhausted", "insufficient_quota", now=time.monotonic())
    p.overflow.cap_sessions[QWEN] = __import__("collections").deque([time.monotonic()] * 4)
    p.async_checkpoints = False
    assert p.checkpoint()
    recovered = create_app(cfg).state.model_policy
    assert recovered.persistence_restored
    assert recovered.route_state.owner_holds["d1"]["category"] == "quota_exhausted"
    assert len(recovered.overflow.cap_sessions[QWEN]) == 4
    assert plan(recovered, body())[0][0][1] == OPUS


def test_quota_timestamp_is_provider_scoped_and_not_capped_at_six_hours():
    from datetime import datetime, timedelta, timezone
    timestamp = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    detail = ("Your limit resets at " + timestamp).encode()
    zai = Route("z", "credential_pool", "https://api.z.ai/api/anthropic", "anthropic", ("glm",))
    other = replace(zai, base_url="https://api.morphllm.com/v1")
    assert _quota_wall_s(detail, zai) > 86400
    assert _quota_wall_s(detail, other) is None
    assert _quota_wall_s(detail, replace(zai, base_url=""), "https://api.z.ai/v1/messages") > 86400


def test_model_permission_hold_does_not_disable_other_models(tmp_path):
    p = state(tmp_path); now = time.monotonic()
    p.routes["labs"] = replace(p.routes["labs"], models=(DS, KIMI))
    p.route_state.hold("labs", "permission", "model_not_granted", now=now, model=DS)
    assert p.eta(p.routes["labs"], DS, body(DS, 512), None, now) == float("inf")
    assert p.eta(p.routes["labs"], KIMI, body(maximum=512), None, now) == 0


@pytest.mark.parametrize("value", [-1, float("inf"), True, "five"])
def test_invalid_fallback_wait_refuses_configuration(tmp_path, value):
    cfg = config(tmp_path)
    cfg.model_routing["overflow"]["families"]["kimi"]["preference_wait_s"] = value
    with pytest.raises(ValueError):
        create_app(cfg)


def test_impossible_unconfigured_exact_request_fails_without_waiting(tmp_path):
    cfg = config(tmp_path)
    cfg.model_routing["overflow"]["enabled"] = False
    calls = []
    response, _ = asyncio.run(request(cfg, body(), lambda r: (calls.append(r), success_response(r))[1]))
    assert response.status_code == 503 and not calls
    assert response.json()["error"]["code"] == "FABRIC_REQUEST_EXCEEDS_CAPACITY"


@pytest.mark.parametrize("code", ["model_not_granted", "model_location_not_supported", "org_under_review"])
def test_stable_policy_code_beats_generic_429(code):
    failure = classify(429, json.dumps({"error": {"code": code}}).encode())
    assert failure.category == "permission" and not failure.retryable
