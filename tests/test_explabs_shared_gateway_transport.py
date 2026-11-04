"""Brain B-only transport: one local gateway quota/secret owner, no vendor key.

The source SDK/HTTPX client stays real; only the upstream is an offline fixture.
"""
from __future__ import annotations

import json

import httpx
import pytest

from brain import explabs_client, explabs_pool


LOCAL_ORIGIN = "http://127.0.0.1:18311"
PROXY = "scoped-local-brain-proxy-token-0123456789"


def _set_b_only(monkeypatch):
    monkeypatch.setenv("EXPLABS_POOL_ENABLED", "1")
    monkeypatch.setenv("EXPLABS_MODEL", "deepseek-v4.1-flash")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_SERVING_VERIFIED", "0")
    monkeypatch.setenv("EXPLABS_API_KEY", "old-a-disabled-account-not-probed")
    monkeypatch.delenv("EXPLABS_ACCOUNT_1_Gateway_ORIGIN", raising=False)
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_ENABLED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_SERVING_VERIFIED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_ORG_SLUG", "org-b-fixture")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_MAX_INFLIGHT", "2")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_TRANSPORT", "shared_gateway")
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_GATEWAY_ORIGIN", LOCAL_ORIGIN)
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_GATEWAY_TOKEN", PROXY)
    monkeypatch.delenv("EXPLABS_API_KEY_2", raising=False)


def _handler(seen, *, deny_completion=False):
    def handle(r):
        assert str(r.url).startswith(LOCAL_ORIGIN + "/")
        assert r.headers.get("authorization") == "Bearer " + PROXY
        assert r.headers.get("idempotency-key") is None
        seen.append((r.method, r.url.path, bytes(r.content)))
        if r.method == "GET":
            if r.url.path == "/api/whoami":
                return httpx.Response(200, json={"org_id": "b-verified", "org_slug": "org-b-fixture"})
            if r.url.path == "/v1/models":
                return httpx.Response(200, json={"data": [{"id": "deepseek-v4.1-flash"}]})
            if r.url.path == "/api/v1/key":
                return httpx.Response(200, json={"data": {"limit": 1.0, "limit_remaining": 0.8}})
            if r.url.path == "/api/v1/credits":
                return httpx.Response(200, json={"data": {"total_credits": 4600, "total_usage": 0}})
        assert r.method == "POST" and r.url.path == "/v1/chat/completions"
        assert json.loads(r.content) == {
            "model": "deepseek-v4.1-flash",
            "messages": [{"role": "user", "content": "B-only fixture"}],
            "max_tokens": 200,
        }
        if deny_completion:
            return httpx.Response(403, json={"error": {"code": "model_not_granted",
                "message": "SENSITIVE_NEVER_EXPOSE"}})
        return httpx.Response(200, json={
            "model": "deepseek-v4.1-flash",
            "choices": [{"message": {"role": "assistant", "content": "success"}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 6, "cost": 0.0002,
                      "is_byok": False},
            "provider": "fixture-cloud",
        })
    return handle


def test_b_only_proxy_sends_all_metadata_and_one_completion_via_same_loopback(monkeypatch):
    _set_b_only(monkeypatch)
    seen = []
    with httpx.Client(transport=httpx.MockTransport(_handler(seen))) as cli:
        pool = explabs_pool.AccountPool(http_client=cli)
        result = pool.complete("", "B-only fixture", max_tokens=200)
    assert result.text == "success" and result.account_slot == "2"
    assert result.is_byok is False and result.cost_usd == pytest.approx(0.0002)
    assert len([x for x in seen if x[0] == "POST"]) == 1
    assert [x[1] for x in seen if x[0] == "GET"] == [
        "/api/whoami", "/v1/models", "/api/v1/key", "/api/v1/credits", "/api/v1/key",
    ]
    assert all(b"old-a-disabled-account" not in raw for _, _, raw in seen)


def test_provider_denial_latches_b_and_never_replays_or_moves_to_a(monkeypatch):
    _set_b_only(monkeypatch)
    seen = []
    with httpx.Client(transport=httpx.MockTransport(_handler(seen, deny_completion=True))) as cli:
        pool = explabs_pool.AccountPool(http_client=cli)
        with pytest.raises(explabs_client.ExperientialError) as exc:
            pool.complete("", "B-only fixture", max_tokens=200)
        assert "explabs_http_403:model_not_granted" in str(exc.value)
        assert "SENSITIVE_NEVER_EXPOSE" not in str(exc.value)
        with pytest.raises(explabs_client.ExperientialError):
            pool.complete("", "B-only fixture", max_tokens=200)
    assert len([x for x in seen if x[0] == "POST"]) == 1


@pytest.mark.parametrize("origin", [
    "https://api.experientiallabs.ai",
    "http://localhost:18311",
    "http://127.0.0.2:18311",
    "http://127.0.0.1",
    "http://127.0.0.1:0",
    "http://127.0.0.1:65536",
    "http://127.0.0.1:18311/v1",
    "http://127.0.0.1:18311?x=1",
    "http://127.0.0.1:18311/#frag",
    "http://user@127.0.0.1:18311",
    "http://127.0.0.1:18311\x0a",
    "http://127.0.0.1:18311/",
])
def test_proxy_origin_rejected_before_send(monkeypatch, origin):
    _set_b_only(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_GATEWAY_ORIGIN", origin)
    assert explabs_pool.available() is False
    with pytest.raises(explabs_client.ExperientialError):
        explabs_pool.AccountPool().complete("", "B-only fixture")
    with pytest.raises(explabs_client.ExperientialError, match="explabs_invalid_gateway_origin"):
        explabs_client.validated_shared_gateway_origin(origin)


def test_proxy_mode_refuses_raw_provider_key_on_brain_host(monkeypatch):
    _set_b_only(monkeypatch)
    monkeypatch.setenv("EXPLABS_API_KEY_2", "raw-provider-key-should-stay-host-only")
    assert explabs_pool.available() is False
    with pytest.raises(explabs_client.ExperientialError, match="provider_key_on_brain_host"):
        explabs_pool._configs()


def test_shared_gateway_must_be_separate_for_each_distinct_org(monkeypatch):
    _set_b_only(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ENABLED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_SERVING_VERIFIED", "1")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_ORG_SLUG", "org-a-fixture")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_DAILY_CAP_USD", "1")
    monkeypatch.delenv("EXPLABS_API_KEY", raising=False)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_TRANSPORT", "shared_gateway")
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_GATEWAY_ORIGIN", LOCAL_ORIGIN)
    monkeypatch.setenv("EXPLABS_ACCOUNT_1_GATEWAY_TOKEN", "second-local-token-0123456789abcdef")
    with pytest.raises(explabs_client.ExperientialError, match="duplicate_gateway_owner"):
        explabs_pool._configs()


def test_direct_mode_remains_the_existing_default(monkeypatch):
    _set_b_only(monkeypatch)
    monkeypatch.setenv("EXPLABS_ACCOUNT_2_TRANSPORT", "direct")
    monkeypatch.delenv("EXPLABS_ACCOUNT_2_GATEWAY_ORIGIN", raising=False)
    monkeypatch.delenv("EXPLABS_ACCOUNT_2_GATEWAY_TOKEN", raising=False)
    monkeypatch.setenv("EXPLABS_API_KEY_2", "fixture-direct-provider-key")
    a = explabs_pool._configs()
    assert len(a) == 1
    assert a[0].api_origin == "https://api.experientiallabs.ai"
    assert a[0].shared_gateway is False
    assert a[0].key == "fixture-direct-provider-key"
