"""Offline two-organization isolation, capacity, cost and no-replay tests."""
import json
import threading

import httpx
import pytest

from brain import client, explabs_client, explabs_pool


_ORIGINS = {"fake-key-a": "http://127.0.0.1:18401",
            "fake-key-b": "http://127.0.0.1:18402"}
_TOKENS = {"fake-key-a": "fixture-scoped-gateway-a-0123456789",
           "fake-key-b": "fixture-scoped-gateway-b-0123456789"}


def _env(monkeypatch):
    monkeypatch.setenv("EXPLABS_POOL_ENABLED", "1")
    monkeypatch.setenv("EXPLABS_BASE_URL", explabs_client.BASE_URL)
    monkeypatch.setenv("EXPLABS_MODEL", "deepseek-v4.1-flash")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_SERVING_VERIFIED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ORG_SLUG", "org-a")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_MAX_INFLIGHT", "2")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_DAILY_CAP_USD", "10")
    monkeypatch.delenv("EXPLABS_API_KEY", raising=False)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_TRANSPORT", "shared_gateway")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_GATEWAY_ORIGIN", _ORIGINS["fake-key-a"])
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_GATEWAY_TOKEN", _TOKENS["fake-key-a"])
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_ENABLED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_SERVING_VERIFIED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_ORG_SLUG", "org-b")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_MAX_INFLIGHT", "2")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "10")
    monkeypatch.delenv("EXPLABS_API_KEY_2", raising=False)
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_TRANSPORT", "shared_gateway")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_GATEWAY_ORIGIN", _ORIGINS["fake-key-b"])
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_GATEWAY_TOKEN", _TOKENS["fake-key-b"])


def _transport(*, response=None, orgs=None, remaining=None, limits=None, seen_gets=None,
               expected_max_tokens=1500, on_request=None):
    calls = []
    orgs = orgs or {"fake-key-a": ("id-a", "org-a"), "fake-key-b": ("id-b", "org-b")}
    remaining = remaining or {"fake-key-a": 5.0, "fake-key-b": 5.0}
    limits = limits if limits is not None else {"fake-key-a": 10.0, "fake-key-b": 10.0}

    def serve(request):
        token = request.headers["Authorization"].removeprefix("Bearer ")
        key = next((label for label, value in _TOKENS.items() if value == token), None)
        assert key is not None
        assert str(request.url).startswith(_ORIGINS[key] + "/")
        assert request.headers["Authorization"] == "Bearer " + _TOKENS[key]
        assert key in orgs
        path = request.url.path
        if on_request is not None:
            override = on_request(request, key)
            if override is not None:
                return override
        if request.method == "GET":
            if seen_gets is not None:
                seen_gets.append((key, path))
            if path == "/api/whoami":
                oid, slug = orgs[key]
                return httpx.Response(200, json={"org_id": oid, "org_slug": slug})
            if path == "/v1/models":
                return httpx.Response(
                    200, json={"data": [{"id": "deepseek-v4.1-flash"}]},
                )
            if path == "/api/v1/key":
                return httpx.Response(
                    200, json={"data": {"limit": limits[key], "limit_remaining": remaining[key]}},
                )
            if path == "/api/v1/credits":
                return httpx.Response(
                    200, json={"data": {"total_credits": 20, "total_usage": 3}},
                )
            raise AssertionError(f"unexpected GET path: {path}")
        assert request.method == "POST" and path == "/v1/chat/completions"
        assert json.loads(request.content) == {
            "model": "deepseek-v4.1-flash",
            "messages": [{"role": "user", "content": "one independent task"}],
            "max_tokens": expected_max_tokens,
        }
        calls.append(key)
        if response is not None:
            custom = response(key, len(calls))
            if custom is not None:
                return custom
        return httpx.Response(200, json={
            "model": "deepseek-v4.1-flash",
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10,
                      "cost": 0.0001, "is_byok": False},
            "provider": "experiential_cloud",
        })
    return httpx.Client(transport=httpx.MockTransport(serve),
                        trust_env=False, follow_redirects=False), calls


def _thread_call(pool, name):
    result, done = [], threading.Event()

    def run():
        try:
            result.append(pool.complete("", "one independent task"))
        except Exception as exc:
            result.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    return thread, done, result


def test_slow_b_metadata_does_not_block_status_or_verified_a(monkeypatch):
    _env(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    armed = [False]
    observed = []

    def block_b(request, key):
        observed.append((threading.current_thread().name, request.method, key, request.url.path))
        if (armed[0] and key == "fake-key-b" and request.method == "GET"
                and request.url.path == "/api/v1/key"
                and threading.current_thread().name == "slow-b"):
            entered.set()
            assert release.wait(5)

    http, posts = _transport(on_request=block_b)
    pool = explabs_pool.AccountPool(http_client=http)
    pool.complete("", "one independent task")
    armed[0] = True
    slow = _thread_call(pool, "slow-b")
    fast = None
    diagnostics, diagnostic_done = [], threading.Event()

    def status():
        diagnostics.append(pool.status())
        diagnostic_done.set()

    diagnostic = None
    try:
        assert entered.wait(5)
        diagnostic = threading.Thread(target=status, daemon=True)
        diagnostic.start()
        assert diagnostic_done.wait(3), "one slot's GET held the global status lock"
        assert diagnostics[0]["2"]["metadata_busy"] is True
        fast = _thread_call(pool, "healthy-a")
        assert fast[1].wait(3), "one slot's GET blocked the healthy peer"
        assert isinstance(fast[2][0], explabs_client.Completion)
        assert fast[2][0].account_slot == "1"
        assert [(method, key, path) for name, method, key, path in observed
                if name == "healthy-a"] == [
            ("GET", "fake-key-a", "/api/v1/key"),
            ("POST", "fake-key-a", "/v1/chat/completions"),
        ]
        assert posts == ["fake-key-a", "fake-key-a"]
    finally:
        release.set()
        for pending in [slow] + ([fast] if fast is not None else []):
            pending[0].join(5)
            assert not pending[0].is_alive()
        if diagnostic is not None:
            diagnostic.join(5)
            assert not diagnostic.is_alive()
        http.close()
    assert isinstance(slow[2][0], explabs_client.Completion)
    assert slow[2][0].account_slot == "2"
    assert all(state["inflight"] == 0 and not state["metadata_busy"]
               for state in pool.status().values())


def test_initial_all_org_barrier_survives_a_busy_reader(monkeypatch):
    _env(monkeypatch)
    entered, release = threading.Event(), threading.Event()

    def block_b(request, key):
        if key == "fake-key-b" and request.url.path == "/api/whoami":
            entered.set()
            assert release.wait(5)

    http, posts = _transport(on_request=block_b)
    pool = explabs_pool.AccountPool(http_client=http)
    initial = _thread_call(pool, "initial-verification")
    independent = None
    try:
        assert entered.wait(5)
        independent = _thread_call(pool, "independent-before-barrier")
        assert independent[1].wait(3)
        assert isinstance(independent[2][0], explabs_client.ExperientialError)
        assert "initial_verification_required" in str(independent[2][0])
        assert posts == []
    finally:
        release.set()
        for pending in [initial] + ([independent] if independent is not None else []):
            pending[0].join(5)
            assert not pending[0].is_alive()
        http.close()
    assert isinstance(initial[2][0], explabs_client.Completion)
    assert len(posts) == 1
    assert all(state["inflight"] == 0 and not state["metadata_busy"]
               for state in pool.status().values())


def test_pool_disabled_by_default_even_with_a_key(monkeypatch):
    monkeypatch.setenv("EXPLABS_API_KEY", "fake-key-a")
    monkeypatch.delenv("EXPLABS_POOL_ENABLED", raising=False)
    assert explabs_pool.available() is False
    monkeypatch.setenv("BOT_LLM_BACKEND", "explabs")
    assert client.available() is False


def test_missing_second_key_rejects_without_any_network(monkeypatch):
    _env(monkeypatch)
    monkeypatch.delenv("EXPLABS_ACCOUNT_2_GATEWAY_TOKEN")
    http, calls = _transport()
    pool = explabs_pool.AccountPool(http_client=http)
    with pytest.raises(explabs_client.ExperientialError, match="explabs_pool_disabled"):
        pool.complete("", "one independent task")
    assert calls == []


def test_two_verified_orgs_alternate_when_equal(monkeypatch):
    _env(monkeypatch)
    http, calls = _transport()
    pool = explabs_pool.AccountPool(http_client=http)
    a = pool.complete("", "one independent task")
    b = pool.complete("", "one independent task")
    assert (a.account_slot, b.account_slot) == ("1", "2")
    assert calls == ["fake-key-a", "fake-key-b"]
    assert a.cost_usd == pytest.approx(0.0001)
    assert pool.status()["1"]["verified"] is True
    assert pool.status()["2"]["verified"] is True


def test_both_keys_must_be_different_organizations(monkeypatch):
    _env(monkeypatch)
    http, calls = _transport(orgs={
        "fake-key-a": ("same-id", "org-a"),
        "fake-key-b": ("same-id", "org-b"),
    })
    pool = explabs_pool.AccountPool(http_client=http)
    with pytest.raises(explabs_client.ExperientialError, match="explabs_pool_duplicate_org"):
        pool.complete("", "one independent task")
    assert calls == []


def test_org_identity_mismatch_blocks_initial_dispatch(monkeypatch):
    _env(monkeypatch)
    http, calls = _transport(orgs={
        "fake-key-a": ("id-a", "other-org"),
        "fake-key-b": ("id-b", "org-b"),
    })
    pool = explabs_pool.AccountPool(http_client=http)
    with pytest.raises(explabs_client.ExperientialError, match="explabs_pool_initial_verification_required"):
        pool.complete("", "one independent task")
    assert calls == []
    assert pool.status()["1"]["blocked"] == "explabs_pool_org_mismatch"


def test_key_daily_limit_holds_account_before_dispatch(monkeypatch):
    _env(monkeypatch)
    http, calls = _transport(remaining={"fake-key-a": 0.0, "fake-key-b": 5.0})
    pool = explabs_pool.AccountPool(http_client=http)
    result = pool.complete("", "one independent task")
    assert result.account_slot == "2"
    assert calls == ["fake-key-b"]


def test_concurrent_inflight_favors_less_busy_account(monkeypatch):
    _env(monkeypatch)
    http, calls = _transport()
    pool = explabs_pool.AccountPool(http_client=http)
    # Local reservation in one worker. Cross-host reservations belong to
    # the existing shared capacity owner, not this Brain adapter.
    pool._health["1"].inflight = 1
    result = pool.complete("", "one independent task")
    assert result.account_slot == "2"
    assert calls == ["fake-key-b"]


def test_measured_cost_preference_uses_real_usage_not_assumed_free(monkeypatch):
    _env(monkeypatch)
    http, calls = _transport()
    pool = explabs_pool.AccountPool(http_client=http)
    pool._health["1"].unit_cost_per_1k_tokens = 0.001
    pool._health["2"].unit_cost_per_1k_tokens = 0.050
    result = pool.complete("", "one independent task")
    assert result.account_slot == "1"
    assert calls == ["fake-key-a"]


def test_403_is_terminal_for_that_attempt_new_task_may_use_other(monkeypatch):
    _env(monkeypatch)
    def answer(key, count):
        if key == "fake-key-a":
            return httpx.Response(
                403, json={"error": {"code": "model_not_granted",
                                     "message": "secret provider text"}},
            )
        return None
    http, calls = _transport(response=answer)
    pool = explabs_pool.AccountPool(http_client=http)
    with pytest.raises(explabs_client.ExperientialError) as error:
        pool.complete("", "one independent task")
    assert error.value.status == 403
    assert error.value.code == "model_not_granted"
    assert "secret provider text" not in str(error.value)
    assert calls == ["fake-key-a"]  # No attempt-level fallback
    result = pool.complete("", "one independent task")  # Distinct new request
    assert result.account_slot == "2"
    assert calls == ["fake-key-a", "fake-key-b"]
    assert pool.status()["1"]["blocked"] is not None


def test_429_cooldown_does_not_replay_request(monkeypatch):
    _env(monkeypatch)
    def answer(key, count):
        if key == "fake-key-a":
            return httpx.Response(
                429,
                json={"error": {"code": "rate_limit_exceeded"}},
                headers={"Retry-After": "42"},
            )
        return None
    http, calls = _transport(response=answer)
    pool = explabs_pool.AccountPool(http_client=http, clock=lambda: 100.0)
    with pytest.raises(explabs_client.ExperientialError, match="explabs_http_429"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-a"]
    assert pool.status()["1"]["cooldown"] is True
    result = pool.complete("", "one independent task")
    assert result.account_slot == "2"
    assert calls == ["fake-key-a", "fake-key-b"]


def test_unknown_dispatch_result_holds_account_until_reconciled(monkeypatch):
    _env(monkeypatch)
    def answer(key, count):
        if key == "fake-key-a":
            raise httpx.ReadTimeout("not a confirmed no-effect result")
        return None
    http, calls = _transport(response=answer)
    pool = explabs_pool.AccountPool(http_client=http)
    with pytest.raises(explabs_client.ExperientialError, match="explabs_transport_error"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-a"]
    assert pool.status()["1"]["blocked"] == "explabs_transport_error"
    result = pool.complete("", "one independent task")
    assert result.account_slot == "2"
    assert len(calls) == 2


def test_local_model_backend_does_not_call_unconfigured_pool(monkeypatch):
    monkeypatch.setenv("BOT_LLM_BACKEND", "explabs")
    monkeypatch.delenv("EXPLABS_POOL_ENABLED", raising=False)
    assert client.call_model("", "one independent task") == (None, "explabs_unavailable")


def test_daily_spend_policy_is_required_before_selection(monkeypatch):
    _env(monkeypatch)
    monkeypatch.delenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD")
    http, calls = _transport()
    pool = explabs_pool.AccountPool(http_client=http)
    assert explabs_pool.available() is False
    with pytest.raises(explabs_client.ExperientialError, match="explabs_pool_disabled"):
        pool.complete("", "one independent task")
    assert calls == []


def test_gateway_enforced_daily_key_cap_must_match_policy(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_DAILY_CAP_USD", "5")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "5")
    http, calls = _transport()
    pool = explabs_pool.AccountPool(http_client=http)
    with pytest.raises(explabs_client.ExperientialError, match="initial_verification_required"):
        pool.complete("", "one independent task")
    assert calls == []
    assert pool.status()["1"]["blocked"] == "explabs_pool_gateway_cap_not_verified"
    assert pool.status()["2"]["blocked"] == "explabs_pool_gateway_cap_not_verified"


def test_missing_eligibility_cannot_migrate_original_attempt(monkeypatch):
    _env(monkeypatch)
    def answer(key, count):
        if key == "fake-key-a":
            return httpx.Response(402, json={"error": {"code": "card_required"}})
        return None
    http, calls = _transport(response=answer)
    pool = explabs_pool.AccountPool(http_client=http)
    with pytest.raises(explabs_client.ExperientialError, match="explabs_http_402"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-a"]
    assert pool.status()["1"]["blocked"] == "explabs_http_402:card_required"


def test_credentials_cannot_change_under_a_live_pool(monkeypatch):
    _env(monkeypatch)
    http, calls = _transport()
    pool = explabs_pool.AccountPool(http_client=http)
    pool.complete("", "one independent task")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_GATEWAY_TOKEN", "fixture-rotated-scoped-token-0123456789")
    with pytest.raises(explabs_client.ExperientialError, match="key_rotation_requires_restart"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-a"]


def test_verified_organization_identity_is_sticky(monkeypatch):
    _env(monkeypatch)
    orgs = {"fake-key-a": ("id-a", "org-a"), "fake-key-b": ("id-b", "org-b")}
    http, calls = _transport(orgs=orgs)
    now = [100.0]
    pool = explabs_pool.AccountPool(http_client=http, clock=lambda: now[0])
    pool.complete("", "one independent task")
    orgs["fake-key-b"] = ("unexpected-new-org", "org-b")
    now[0] += 65
    with pytest.raises(explabs_client.ExperientialError, match="org_identity_changed"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-a"]


def test_only_b_enabled_uses_b_without_probing_denied_account_a(monkeypatch):
    """Existing 403 on A is not a reason to probe A or block a verified B."""
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    observed_gets = []
    http, calls = _transport(
        limits={"fake-key-a": 10.0, "fake-key-b": 1.0},
        remaining={"fake-key-a": 5.0, "fake-key-b": 1.0},
        seen_gets=observed_gets,
    )
    pool = explabs_pool.AccountPool(http_client=http)
    assert explabs_pool.available() is True
    result = pool.complete("", "one independent task")
    assert result.account_slot == "2"
    assert calls == ["fake-key-b"]
    assert observed_gets
    assert all(key == "fake-key-b" for key, _ in observed_gets)
    assert sum(path == "/api/v1/key" for _, path in observed_gets) == 2
    assert pool.status()["1"]["verified"] is False


def test_no_enabled_org_prevents_any_api_request(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_ENABLED", "0")
    seen_gets = []
    http, calls = _transport(seen_gets=seen_gets)
    pool = explabs_pool.AccountPool(http_client=http)
    assert explabs_pool.available() is False
    with pytest.raises(explabs_client.ExperientialError, match="explabs_pool_disabled"):
        pool.complete("", "one independent task")
    assert calls == [] and seen_gets == []


def test_b_one_dollar_policy_blocks_uncapped_provider_key(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    seen_gets = []
    http, calls = _transport(
        limits={"fake-key-a": 10.0, "fake-key-b": None},
        seen_gets=seen_gets,
    )
    pool = explabs_pool.AccountPool(http_client=http)
    with pytest.raises(explabs_client.ExperientialError, match="initial_verification_required"):
        pool.complete("", "one independent task")
    assert calls == []
    assert all(key == "fake-key-b" for key, _ in seen_gets)
    assert pool.status()["2"]["blocked"] == "explabs_pool_gateway_cap_not_verified"


def test_b_one_dollar_policy_rejects_higher_provider_cap(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    http, calls = _transport(
        limits={"fake-key-a": 10.0, "fake-key-b": 1.01},
        remaining={"fake-key-a": 5.0, "fake-key-b": 1.0},
    )
    with pytest.raises(explabs_client.ExperientialError, match="initial_verification_required"):
        explabs_pool.AccountPool(http_client=http).complete("", "one independent task")
    assert calls == []


def test_b_daily_cap_zero_headroom_blocks_without_inference(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    http, calls = _transport(
        limits={"fake-key-a": 10.0, "fake-key-b": 1.0},
        remaining={"fake-key-a": 5.0, "fake-key-b": 0.0},
    )
    with pytest.raises(explabs_client.ExperientialError, match="no_eligible_account"):
        explabs_pool.AccountPool(http_client=http).complete("", "one independent task")
    assert calls == []


def test_revalidate_gateway_cap_before_each_independent_completion(monkeypatch):
    """A stale cached identity must not hide a provider daily-cap increase."""
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    limits = {"fake-key-a": 10.0, "fake-key-b": 1.0}
    remaining = {"fake-key-a": 5.0, "fake-key-b": 1.0}
    http, calls = _transport(limits=limits, remaining=remaining)
    pool = explabs_pool.AccountPool(http_client=http)
    assert pool.complete("", "one independent task").account_slot == "2"
    limits["fake-key-b"] = 5.0
    with pytest.raises(explabs_client.ExperientialError, match="gateway_cap_not_verified"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-b"]
    assert pool.status()["2"]["blocked"] == "explabs_pool_gateway_cap_not_verified"


def test_enabling_second_org_requires_new_pool_instance(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    http, calls = _transport(
        limits={"fake-key-a": 10.0, "fake-key-b": 1.0},
        remaining={"fake-key-a": 5.0, "fake-key-b": 1.0},
    )
    pool = explabs_pool.AccountPool(http_client=http)
    assert pool.complete("", "one independent task").account_slot == "2"
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "1")
    with pytest.raises(explabs_client.ExperientialError, match="key_rotation_requires_restart"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-b"]


def test_serving_receipt_required_before_enabling_b(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_SERVING_VERIFIED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    seen_gets = []
    http, calls = _transport(seen_gets=seen_gets)
    pool = explabs_pool.AccountPool(http_client=http)
    assert explabs_pool.available() is False
    with pytest.raises(explabs_client.ExperientialError, match="explabs_pool_disabled"):
        pool.complete("", "one independent task")
    assert calls == [] and seen_gets == []


def test_paid_daily_cap_429_is_held_not_treated_as_resettable_rate_limit(monkeypatch):
    _env(monkeypatch)

    def answer(key, count):
        if key == "fake-key-a":
            return httpx.Response(
                429,
                json={"error": {
                    "code": "insufficient_quota",
                    "message": "key_daily_cap reached",
                }},
                headers={"Retry-After": "5"},
            )
        return None

    http, calls = _transport(response=answer)
    pool = explabs_pool.AccountPool(http_client=http)
    with pytest.raises(explabs_client.ExperientialError, match="insufficient_quota"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-a"]  # Cannot transfer the failed attempt
    assert pool.status()["1"]["blocked"] == "explabs_http_429:insufficient_quota"
    assert pool.status()["1"]["cooldown"] is False


def test_included_free_gateway_cost_does_not_claim_paid_usage(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")

    def answer(key, count):
        return httpx.Response(200, json={
            "model": "deepseek-v4.1-flash",
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3,
                      "cost": 0.0, "is_byok": False},
            "provider": "experiential_cloud",
        })

    http, calls = _transport(
        response=answer,
        limits={"fake-key-a": 10.0, "fake-key-b": 1.0},
        remaining={"fake-key-a": 5.0, "fake-key-b": 1.0},
    )
    outcome = explabs_pool.AccountPool(http_client=http).complete("", "one independent task")
    assert outcome.cost_usd == 0.0
    assert outcome.is_byok is False
    assert (outcome.input_tokens, outcome.output_tokens) == (9, 3)
    assert calls == ["fake-key-b"]


def test_pre_dispatch_exhausted_key_is_skipped_for_new_work(monkeypatch):
    """No wasted dispatch to a stale cached key with zero daily headroom."""
    _env(monkeypatch)
    remaining = {"fake-key-a": 5.0, "fake-key-b": 5.0}
    http, calls = _transport(remaining=remaining)
    pool = explabs_pool.AccountPool(http_client=http)
    first = pool.complete("", "one independent task")
    assert first.account_slot == "1"
    remaining["fake-key-a"] = 0.0
    # Different, independent new call. It must not pick the now-exhausted A
    # based on the previous observation, nor replay the prior completion.
    second = pool.complete("", "one independent task")
    assert second.account_slot == "2"
    assert calls == ["fake-key-a", "fake-key-b"]
    assert pool.status()["1"]["key_remaining_usd"] == 0


def test_pre_dispatch_changed_provider_cap_isolated_to_one_account(monkeypatch):
    """One key's unsafe limit cannot prevent distinct new work on a safe peer."""
    _env(monkeypatch)
    limits = {"fake-key-a": 10.0, "fake-key-b": 10.0}
    remaining = {"fake-key-a": 5.0, "fake-key-b": 5.0}
    http, calls = _transport(limits=limits, remaining=remaining)
    pool = explabs_pool.AccountPool(http_client=http)
    first = pool.complete("", "one independent task")
    assert first.account_slot == "1"
    limits["fake-key-a"] = 11.0  # Exceeds local approved cap
    remaining["fake-key-a"] = 10.0
    second = pool.complete("", "one independent task")
    assert second.account_slot == "2"
    assert calls == ["fake-key-a", "fake-key-b"]
    assert pool.status()["1"]["blocked"] == "explabs_pool_gateway_cap_not_verified"


def test_unexpected_byok_serving_lane_holds_billing_exposure(monkeypatch):
    """A provider BYOK bill is NOT protected by the Experiential daily cap."""
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")

    def serve(key, count):
        return httpx.Response(200, json={
            "model": "deepseek-v4.1-flash",
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 4,
                "cost": 0,
                "is_byok": True,
            },
            "is_byok": True,
        })

    http, calls = _transport(
        response=serve,
        limits={"fake-key-a": 10.0, "fake-key-b": 1.0},
        remaining={"fake-key-a": 5.0, "fake-key-b": 1.0},
    )
    pool = explabs_pool.AccountPool(http_client=http)
    served = pool.complete("", "one independent task")
    assert served.text == "OK"
    assert served.is_byok is True
    assert pool.status()["2"]["blocked"] == "explabs_unexpected_byok"
    with pytest.raises(explabs_client.ExperientialError, match="no_eligible_account"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-b"]


def test_missing_gateway_cost_holds_account_for_billing_reconciliation(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")

    def serve(key, count):
        return httpx.Response(200, json={
            "model": "deepseek-v4.1-flash",
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            "is_byok": False,
        })

    http, calls = _transport(
        response=serve,
        limits={"fake-key-a": 10.0, "fake-key-b": 1.0},
        remaining={"fake-key-a": 5.0, "fake-key-b": 1.0},
    )
    pool = explabs_pool.AccountPool(http_client=http)
    served = pool.complete("", "one independent task")
    assert served.text == "OK"
    assert served.cost_usd is None
    assert pool.status()["2"]["blocked"] == "explabs_missing_gateway_cost"
    with pytest.raises(explabs_client.ExperientialError, match="no_eligible_account"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-b"]


def test_brain_client_to_pool_to_gateway_to_cost_ledger_b_only(monkeypatch):
    """Full Brain entrypoint through real pool + wire adapter with mocked HTTP."""
    _env(monkeypatch)
    monkeypatch.setenv("BOT_LLM_BACKEND", "explabs")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    http, calls = _transport(
        limits={"fake-key-a": 10.0, "fake-key-b": 1.0},
        remaining={"fake-key-a": 5.0, "fake-key-b": 1.0},
    )
    monkeypatch.setattr(explabs_pool, "_POOL", explabs_pool.AccountPool(http_client=http))
    from brain import cost_guard
    recorded = []
    monkeypatch.setattr(cost_guard, "record", lambda *a, **kw: recorded.append((a, kw)))

    assert client.backend() == "explabs"
    assert client.available()
    assert client.call_model("", "one independent task", role="analyst") == ("OK", None)
    assert calls == ["fake-key-b"]
    assert len(recorded) == 1
    args, kwargs = recorded[0]
    assert args[1] == pytest.approx(0.0001)
    assert kwargs["key_id"] == "explabs_account_2"
    assert kwargs["input_tokens"] == 10
    assert kwargs["output_tokens"] == 10
    assert kwargs["model"] == "deepseek-v4.1-flash"


def test_brain_client_denies_uncapped_b_before_inference(monkeypatch):
    """True Brain entrypoint refuses an uncertified $1 cap without a POST."""
    _env(monkeypatch)
    monkeypatch.setenv("BOT_LLM_BACKEND", "explabs")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    http, calls = _transport(limits={"fake-key-a": 10.0, "fake-key-b": None})
    monkeypatch.setattr(explabs_pool, "_POOL", explabs_pool.AccountPool(http_client=http))

    assert client.available()
    result, reason = client.call_model("", "one independent task", role="analyst")
    assert result is None
    assert reason == "explabs_pool_initial_verification_required"
    assert calls == []


def test_brain_client_honors_requested_output_ceiling(monkeypatch):
    """Mastermind's existing max_tokens now reaches the provider request."""
    _env(monkeypatch)
    monkeypatch.setenv("BOT_LLM_BACKEND", "explabs")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    http, calls = _transport(
        expected_max_tokens=384,
        limits={"fake-key-a": 10.0, "fake-key-b": 1.0},
        remaining={"fake-key-a": 5.0, "fake-key-b": 1.0},
    )
    monkeypatch.setattr(explabs_pool, "_POOL", explabs_pool.AccountPool(http_client=http))
    from brain import cost_guard
    monkeypatch.setattr(cost_guard, "record", lambda *a, **kw: None)
    assert client.call_model("", "one independent task", max_tokens=384) == ("OK", None)
    assert calls == ["fake-key-b"]


def test_invalid_output_ceiling_does_not_quarantine_account(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    seen_gets = []
    http, calls = _transport(
        limits={"fake-key-a": 10.0, "fake-key-b": 1.0},
        remaining={"fake-key-a": 5.0, "fake-key-b": 1.0},
        seen_gets=seen_gets,
    )
    pool = explabs_pool.AccountPool(http_client=http)
    with pytest.raises(explabs_client.ExperientialError, match="invalid_max_tokens"):
        pool.complete("", "one independent task", max_tokens=0)
    assert calls == [] and seen_gets == []
    assert pool.status()["2"]["blocked"] is None
    assert pool.complete("", "one independent task").text == "OK"


def test_missing_billing_lane_flag_holds_account_even_with_zero_cost(monkeypatch):
    """A zero USD cost with unknown BYOK status is not funding proof."""
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")

    def response(key, count):
        return httpx.Response(200, json={
            "model": "deepseek-v4.1-flash",
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 4, "cost": 0.0},
            # Deliberately absent is_byok: can never infer platform funding.
        })

    http, calls = _transport(
        response=response,
        limits={"fake-key-a": 10.0, "fake-key-b": 1.0},
        remaining={"fake-key-a": 5.0, "fake-key-b": 1.0},
    )
    pool = explabs_pool.AccountPool(http_client=http)
    served = pool.complete("", "one independent task")
    assert served.text == "OK"
    assert served.is_byok is None
    assert pool.status()["2"]["blocked"] == "explabs_unknown_funding_lane"
    with pytest.raises(explabs_client.ExperientialError, match="no_eligible_account"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-b"]
