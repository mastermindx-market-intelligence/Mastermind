"""Offline two-organization isolation, capacity, cost and no-replay tests."""
import json

import httpx
import pytest

from brain import client, explabs_client, explabs_pool


def _env(monkeypatch):
    monkeypatch.setenv("EXPLABS_POOL_ENABLED", "1")
    monkeypatch.setenv("EXPLABS_BASE_URL", explabs_client.BASE_URL)
    monkeypatch.setenv("EXPLABS_MODEL", "deepseek-v4.1-flash")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_SERVING_VERIFIED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ORG_SLUG", "org-a")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_MAX_INFLIGHT", "2")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_DAILY_CAP_USD", "10")
    monkeypatch.setenv("EXPLABS_API_KEY", "fake-key-a")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_GATEWAY_BASE_URL", "http://127.0.0.1:18731/v1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_GATEWAY_PROXY_TOKEN",
                       "fixture-local-account-a-" + "a" * 24)
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_ENABLED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_SERVING_VERIFIED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_ORG_SLUG", "org-b")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_MAX_INFLIGHT", "2")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "10")
    monkeypatch.setenv("EXPLABS_API_KEY_2", "fake-key-b")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_GATEWAY_BASE_URL", "http://127.0.0.1:18732/v1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_GATEWAY_PROXY_TOKEN",
                       "fixture-local-account-b-" + "b" * 24)


def _transport(*, response=None, orgs=None, remaining=None, limits=None, seen_gets=None, expected_max_tokens=1500):
    calls = []
    orgs = orgs or {"fake-key-a": ("id-a", "org-a"), "fake-key-b": ("id-b", "org-b")}
    remaining = remaining or {"fake-key-a": 5.0, "fake-key-b": 5.0}
    limits = limits if limits is not None else {"fake-key-a": 10.0, "fake-key-b": 10.0}

    def serve(request):
        supplied = request.headers["Authorization"].removeprefix("Bearer ")
        path = request.url.path
        if request.method == "GET":
            key = supplied
            assert key in orgs
            assert request.url.host == "api.experientiallabs.ai"
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
        # Provider keys are ONLY used for read-only owner identity/cap reads.
        # The inference POST uses the host-owned gateway's scoped local bearer.
        if supplied == "fixture-local-account-a-" + "a" * 24:
            key = "fake-key-a"
            assert request.url.host == "127.0.0.1" and request.url.port == 18731
        elif supplied == "fixture-local-account-b-" + "b" * 24:
            key = "fake-key-b"
            assert request.url.host == "127.0.0.1" and request.url.port == 18732
        else:
            raise AssertionError("provider token must not go to the inference POST")
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
    return httpx.Client(transport=httpx.MockTransport(serve)), calls


def test_pool_disabled_by_default_even_with_a_key(monkeypatch):
    monkeypatch.setenv("EXPLABS_API_KEY", "fake-key-a")
    monkeypatch.delenv("EXPLABS_POOL_ENABLED", raising=False)
    assert explabs_pool.available() is False
    monkeypatch.setenv("BOT_LLM_BACKEND", "explabs")
    assert client.available() is False


def test_missing_second_key_rejects_without_any_network(monkeypatch):
    _env(monkeypatch)
    monkeypatch.delenv("EXPLABS_API_KEY_2")
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
    monkeypatch.setenv("EXPLABS_API_KEY_2", "fake-key-rotated")
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


# ---------------------------------------------------------------------------
# All new Brain inference must join the existing gateway's per-org RPM owner.
# The two provider keys are used only for read-only origin/cap probes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", [
    "EXPLABS_ACCOUNT_1_GATEWAY_BASE_URL",
    "EXPLABS_ACCOUNT_1_GATEWAY_PROXY_TOKEN",
    "EXPLABS_ACCOUNT_2_GATEWAY_BASE_URL",
    "EXPLABS_ACCOUNT_2_GATEWAY_PROXY_TOKEN",
])
def test_local_shared_gateway_is_required_before_any_account_probe(monkeypatch, missing):
    _env(monkeypatch)
    monkeypatch.delenv(missing)
    seen_gets = []
    http, calls = _transport(seen_gets=seen_gets)
    pool = explabs_pool.AccountPool(http_client=http)
    assert not explabs_pool.available()
    with pytest.raises(explabs_client.ExperientialError, match="explabs_pool_disabled"):
        pool.complete("", "one independent task")
    assert not seen_gets and not calls


@pytest.mark.parametrize("invalid", [
    "http://localhost:18732/v1",
    "http://127.0.0.1:18732/v1/../admin",
    "http://127.0.0.1:18732/v1%2fadmin",
    "http://127.0.0.1:18732/v1?token=bad",
    "https://api.experientiallabs.ai/v1",
    "http://203.0.113.10:18732/v1",
    "http://127.0.0.2:18732/v1",
    "http://127.0.0.1:18732/v1/",
    "http://127.0.0.1:0/v1",
    "http://127.0.0.1:80/v1",
])
def test_public_named_or_ambiguous_gateway_address_never_receives_token(monkeypatch, invalid):
    _env(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_GATEWAY_BASE_URL", invalid)
    seen_gets = []
    http, calls = _transport(seen_gets=seen_gets)
    pool = explabs_pool.AccountPool(http_client=http)
    assert not explabs_pool.available()
    with pytest.raises(explabs_client.ExperientialError, match="explabs_pool_disabled"):
        pool.complete("", "one independent task")
    assert not seen_gets and not calls


@pytest.mark.parametrize("duplicate_field", [
    "EXPLABS_ACCOUNT_2_GATEWAY_BASE_URL",
    "EXPLABS_ACCOUNT_2_GATEWAY_PROXY_TOKEN",
])
def test_distinct_organizations_require_distinct_gateway_admission_identity(
        monkeypatch, duplicate_field):
    _env(monkeypatch)
    suffix = duplicate_field.removeprefix("EXPLABS_ACCOUNT_2_")
    monkeypatch.setenv(duplicate_field, __import__("os").environ[
        "EXPLABS_ACCOUNT_1_" + suffix
    ])
    seen_gets = []
    http, calls = _transport(seen_gets=seen_gets)
    assert not explabs_pool.available()
    with pytest.raises(explabs_client.ExperientialError, match="explabs_pool_disabled"):
        explabs_pool.AccountPool(http_client=http).complete("", "one independent task")
    assert not seen_gets and not calls


@pytest.mark.parametrize("changed", [
    "EXPLABS_ACCOUNT_2_GATEWAY_BASE_URL",
    "EXPLABS_ACCOUNT_2_GATEWAY_PROXY_TOKEN",
])
def test_a_live_pool_refuses_gateway_route_or_token_rotation(monkeypatch, changed):
    _env(monkeypatch)
    http, calls = _transport()
    pool = explabs_pool.AccountPool(http_client=http)
    pool.complete("", "one independent task")
    assert calls == ["fake-key-a"]
    replacement = (
        "http://127.0.0.1:18733/v1" if changed.endswith("BASE_URL")
        else "fixture-rotated-local-token-" + "x" * 24
    )
    monkeypatch.setenv(changed, replacement)
    with pytest.raises(explabs_client.ExperientialError,
                       match="explabs_pool_gateway_route_changed"):
        pool.complete("", "one independent task")
    assert calls == ["fake-key-a"]


def test_pool_mode_refuses_direct_vendor_completion_without_shared_route(monkeypatch):
    _env(monkeypatch)
    requests = []
    http = httpx.Client(transport=httpx.MockTransport(
        lambda req: requests.append(req) or httpx.Response(200, json={})
    ))
    with pytest.raises(explabs_client.ExperientialError,
                       match="explabs_pool_requires_shared_gateway"):
        explabs_client.complete("", "one independent task", client=http,
                                api_key="fake-key-b")
    assert requests == []


def test_shared_gateway_receives_only_scoped_bearer_not_provider_key(monkeypatch):
    _env(monkeypatch)
    requests = []
    def local(req):
        requests.append(req)
        assert req.url.host == "127.0.0.1"
        assert req.url.path == "/v1/chat/completions"
        assert req.headers["Authorization"] == (
            "Bearer fixture-local-account-b-" + "b" * 24
        )
        assert "fake-key-b" not in str(req.headers)
        return httpx.Response(200, json={
            "model": "deepseek-v4.1-flash",
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0},
            "is_byok": False,
        })
    with httpx.Client(transport=httpx.MockTransport(local)) as client_http:
        result = explabs_client.complete(
            "", "one independent task", client=client_http,
            api_key="fake-key-b",
            shared_gateway_url="http://127.0.0.1:18732/v1",
            local_proxy_token="fixture-local-account-b-" + "b" * 24,
        )
    assert result.text == "OK"
    assert len(requests) == 1


def test_account_representation_cannot_expose_either_credential(monkeypatch):
    _env(monkeypatch)
    account = explabs_pool._configs()[1]
    assert "fake-key-b" not in repr(account)
    assert "fixture-local-account-b-" not in repr(account)
