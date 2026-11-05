"""Brain B-only transport: one local gateway quota/secret owner, no vendor key.

The source SDK/HTTPX client stays real; only the upstream is an offline fixture.
"""
from __future__ import annotations

import json
import threading
from types import SimpleNamespace

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
    monkeypatch.delenv("EXPLABS_ACCOUNT_1_GATEWAY_ORIGIN", raising=False)
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
    with httpx.Client(transport=httpx.MockTransport(_handler(seen)),
                      trust_env=False, follow_redirects=False) as cli:
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
    with httpx.Client(transport=httpx.MockTransport(_handler(seen, deny_completion=True)),
                      trust_env=False, follow_redirects=False) as cli:
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


@pytest.mark.parametrize("transport", [None, "", "direct"])
def test_enabled_pool_requires_explicit_shared_transport_before_any_request(monkeypatch, transport):
    _set_b_only(monkeypatch)
    if transport is None:
        monkeypatch.delenv("EXPLABS_ACCOUNT_2_TRANSPORT")
    else:
        monkeypatch.setenv("EXPLABS_ACCOUNT_2_TRANSPORT", transport)
    monkeypatch.delenv("EXPLABS_ACCOUNT_2_GATEWAY_ORIGIN", raising=False)
    monkeypatch.delenv("EXPLABS_ACCOUNT_2_GATEWAY_TOKEN", raising=False)
    monkeypatch.setenv("EXPLABS_API_KEY_2", "fixture-direct-provider-key")
    seen = []
    assert explabs_pool.available() is False
    with httpx.Client(transport=httpx.MockTransport(_handler(seen)),
                      trust_env=False, follow_redirects=False) as cli:
        with pytest.raises(explabs_client.ExperientialError,
                           match="explabs_pool_disabled") as error:
            explabs_pool.AccountPool(http_client=cli).complete("", "B-only fixture")
    assert error.value.code == "explabs_pool_shared_gateway_transport_required"
    assert seen == []


def test_standalone_direct_client_remains_available_with_pool_off(monkeypatch):
    monkeypatch.setenv("EXPLABS_POOL_ENABLED", "0")
    monkeypatch.setenv("EXPLABS_BASE_URL", explabs_client.BASE_URL)
    seen = []

    def direct(request):
        seen.append((request.method, str(request.url)))
        assert request.headers["authorization"] == "Bearer standalone-fixture-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.001,
                      "is_byok": False}})

    with httpx.Client(transport=httpx.MockTransport(direct),
                      trust_env=False, follow_redirects=False) as cli:
        result = explabs_client.complete("", "direct fixture", client=cli,
                                         api_key="standalone-fixture-key")
    assert result.text == "OK"
    assert seen == [("POST", explabs_client.BASE_URL + "/chat/completions")]


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_success_shaped_redirect_is_not_an_account_pool_completion(monkeypatch, status):
    _set_b_only(monkeypatch)
    seen = []
    normal = _handler(seen)

    def redirect(request):
        response = normal(request)
        if request.method == "POST":
            return httpx.Response(
                status, headers={"location": "https://never-contacted.invalid/PRIVATE_SENTINEL"},
                json=response.json(),
            )
        return response

    with httpx.Client(transport=httpx.MockTransport(redirect),
                      follow_redirects=False, trust_env=False) as client:
        pool = explabs_pool.AccountPool(http_client=client)
        with pytest.raises(explabs_client.ExperientialError,
                           match="explabs_upstream_redirect_refused") as exc:
            pool.complete("", "B-only fixture", max_tokens=200)
    assert exc.value.status == status
    assert "PRIVATE_SENTINEL" not in str(exc.value)
    assert len([row for row in seen if row[0] == "POST"]) == 1
    assert seen[-1][1] == "/v1/chat/completions"


@pytest.mark.parametrize("status", [301, 302, 307, 308])
@pytest.mark.parametrize("shared", [False, True])
def test_redirect_refuses_before_decoding_or_following(status, shared):
    seen = []

    def fixture(request):
        seen.append((request.method, str(request.url)))
        return httpx.Response(
            status, headers={"location": "https://never-contacted.invalid/PRIVATE_SENTINEL"},
            content=b"not a completion or JSON document",
        )

    with httpx.Client(transport=httpx.MockTransport(fixture),
                      follow_redirects=False, trust_env=False) as client:
        with pytest.raises(explabs_client.ExperientialError,
                           match="explabs_upstream_redirect_refused") as exc:
            explabs_client.chat_completion(
                [{"role": "user", "content": "fixture"}], client=client,
                api_key=PROXY, shared_gateway_origin=LOCAL_ORIGIN if shared else None,
                max_tokens=8,
            )
    expected = LOCAL_ORIGIN + "/v1/chat/completions" if shared else explabs_client.BASE_URL + "/chat/completions"
    assert seen == [("POST", expected)]
    assert exc.value.status == status
    assert "PRIVATE_SENTINEL" not in str(exc.value)


@pytest.fixture
def b_gateway(monkeypatch):
    """Real pool/serializer over one strict, non-networked gateway fixture."""
    _set_b_only(monkeypatch)
    fixture = SimpleNamespace(now=100.0, hook=None, wire=[], seen=[])
    fixture.normal = _handler(fixture.seen)

    def route(request):
        assert str(request.url).startswith(LOCAL_ORIGIN + "/")
        assert request.headers["authorization"] == "Bearer " + PROXY
        fixture.wire.append((request.method, request.url.path))
        if fixture.hook is not None:
            response = fixture.hook(request)
            if response is not None:
                return response
        return fixture.normal(request)

    with httpx.Client(transport=httpx.MockTransport(route),
                      trust_env=False, follow_redirects=False) as cli:
        fixture.pool = explabs_pool.AccountPool(http_client=cli, clock=lambda: fixture.now)
        yield fixture


def _call(fixture):
    return fixture.pool.complete("", "B-only fixture", max_tokens=200)


def _start_call(fixture, name):
    result, done = [], threading.Event()

    def run():
        try:
            result.append(_call(fixture))
        except Exception as exc:
            result.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    return thread, done, result


def _join_calls(*calls):
    for thread, _, _ in calls:
        thread.join(5)
        assert not thread.is_alive(), "fixture worker did not release its reservation"


def _assert_idle(fixture):
    state = fixture.pool.status()["2"]
    assert state["inflight"] == 0
    assert state["metadata_busy"] is False


def test_bound_account_repr_and_diagnostics_never_expose_gateway_bearer(b_gateway):
    _call(b_gateway)
    assert PROXY not in repr(explabs_pool._configs())
    assert PROXY not in repr(b_gateway.pool._bindings)
    assert PROXY not in json.dumps(b_gateway.pool.status())
    assert "old-a-disabled-account-not-probed" not in repr(b_gateway.pool._bindings)


@pytest.mark.parametrize("change", ["origin", "token", "org", "slot", "set", "transport"])
def test_live_pool_binding_changes_refuse_before_another_request(monkeypatch, b_gateway, change):
    _call(b_gateway)
    before = list(b_gateway.wire)
    stem = "EXPLABS_ACCOUNT_2"
    if change == "origin":
        monkeypatch.setenv(stem + "_GATEWAY_ORIGIN", "http://127.0.0.1:18312")
    elif change == "token":
        monkeypatch.setenv(stem + "_GATEWAY_TOKEN", "different-scoped-token-0123456789")
    elif change == "org":
        monkeypatch.setenv(stem + "_ORG_SLUG", "another-organization")
    elif change == "transport":
        monkeypatch.setenv(stem + "_TRANSPORT", "direct")
    else:
        monkeypatch.delenv("EXPLABS_API_KEY", raising=False)
        for suffix, value in {
            "ENABLED": "1", "SERVING_VERIFIED": "1", "MAX_INFLIGHT": "2",
            "DAILY_CAP_USD": "1", "TRANSPORT": "shared_gateway",
            "ORG_SLUG": "org-b-fixture" if change == "slot" else "other-org",
            "GATEWAY_ORIGIN": LOCAL_ORIGIN if change == "slot" else "http://127.0.0.1:18312",
            "GATEWAY_TOKEN": PROXY if change == "slot" else "other-scoped-token-0123456789",
        }.items():
            monkeypatch.setenv("EXPLABS_ACCOUNT_1_" + suffix, value)
        if change == "slot":
            monkeypatch.setenv(stem + "_ENABLED", "0")
    with pytest.raises(explabs_client.ExperientialError) as error:
        _call(b_gateway)
    assert PROXY not in str(error.value)
    assert b_gateway.wire == before
    _assert_idle(b_gateway)


@pytest.mark.parametrize("phase", ["initial", "cap"])
@pytest.mark.parametrize("failure", [503, 504, "timeout"])
def test_metadata_availability_cools_down_without_permission_poisoning(b_gateway, phase, failure):
    if phase == "cap":
        _call(b_gateway)
    before = len(b_gateway.wire)
    endpoint = "/api/whoami" if phase == "initial" else "/api/v1/key"

    def unavailable(request):
        if request.method == "GET" and request.url.path == endpoint:
            if failure == "timeout":
                raise httpx.ReadTimeout("SECRET_UPSTREAM_TEXT", request=request)
            return httpx.Response(failure, json={"error": "SECRET_UPSTREAM_TEXT"})

    b_gateway.hook = unavailable
    with pytest.raises(explabs_client.ExperientialError) as error:
        _call(b_gateway)
    assert "SECRET_UPSTREAM_TEXT" not in str(error.value)
    status = b_gateway.pool.status()["2"]
    assert status["verified"] is False
    assert status["blocked"] is None and status["cooldown"] is True
    assert b_gateway.wire[before:] == [("GET", endpoint)]
    after_failure = len(b_gateway.wire)
    with pytest.raises(explabs_client.ExperientialError):
        _call(b_gateway)
    assert len(b_gateway.wire) == after_failure
    b_gateway.now += 61
    b_gateway.hook = None
    assert _call(b_gateway).account_slot == "2"
    assert b_gateway.wire[after_failure:] == [
        ("GET", "/api/whoami"), ("GET", "/v1/models"),
        ("GET", "/api/v1/key"), ("GET", "/api/v1/credits"),
        ("GET", "/api/v1/key"), ("POST", "/v1/chat/completions"),
    ]
    _assert_idle(b_gateway)


@pytest.mark.parametrize("phase", ["initial", "cap"])
@pytest.mark.parametrize("failure", [401, 402, 403, 404, 429, 502,
    "invalid_cap", "oversized_cap", "invalid_json", "transport"])
def test_hard_metadata_failures_stay_held_after_clock_advance(b_gateway, phase, failure):
    if phase == "cap":
        _call(b_gateway)
    before = len(b_gateway.wire)

    def hard_failure(request):
        if request.method != "GET" or request.url.path != "/api/v1/key":
            return None
        if failure == "transport":
            raise httpx.ConnectError("SECRET_UPSTREAM_TEXT", request=request)
        if failure == "invalid_json":
            return httpx.Response(200, content=b"SECRET_NOT_JSON")
        if failure in {"invalid_cap", "oversized_cap"}:
            return httpx.Response(200, json={"data": {
                "limit": 2 if failure == "invalid_cap" else 10 ** 400,
                "limit_remaining": 0.8}})
        return httpx.Response(failure, json={"error": "SECRET_UPSTREAM_TEXT"})

    b_gateway.hook = hard_failure
    with pytest.raises(explabs_client.ExperientialError) as error:
        _call(b_gateway)
    assert "SECRET_" not in str(error.value)
    status = b_gateway.pool.status()["2"]
    assert status["blocked"] is not None and status["cooldown"] is False
    assert status["verified"] is False
    assert all(method == "GET" for method, _ in b_gateway.wire[before:])
    held_wire = list(b_gateway.wire)
    b_gateway.hook = None
    b_gateway.now += 61
    with pytest.raises(explabs_client.ExperientialError):
        _call(b_gateway)
    assert b_gateway.wire == held_wire
    _assert_idle(b_gateway)


def test_verified_org_identity_stays_bound_after_metadata_cooldown(b_gateway):
    _call(b_gateway)
    b_gateway.hook = lambda request: (
        httpx.Response(503) if request.url.path == "/api/v1/key" else None)
    with pytest.raises(explabs_client.ExperientialError):
        _call(b_gateway)
    b_gateway.now += 61
    before = len(b_gateway.wire)
    b_gateway.hook = lambda request: (
        httpx.Response(200, json={"org_id": "changed-b-id", "org_slug": "org-b-fixture"})
        if request.url.path == "/api/whoami" else None)
    with pytest.raises(explabs_client.ExperientialError, match="org_identity_changed"):
        _call(b_gateway)
    assert b_gateway.pool.status()["2"]["blocked"] == "explabs_pool_org_identity_changed"
    assert all(method == "GET" for method, _ in b_gateway.wire[before:])
    held_wire = list(b_gateway.wire)
    b_gateway.hook = None
    b_gateway.now += 61
    with pytest.raises(explabs_client.ExperientialError):
        _call(b_gateway)
    assert b_gateway.wire == held_wire
    _assert_idle(b_gateway)


@pytest.mark.parametrize("name,value", [
    ("EXPLABS_POOL_ENABLED", "0"),
    ("EXPLABS_ACCOUNT_2_GATEWAY_ORIGIN", "http://127.0.0.1:18312"),
    ("EXPLABS_ACCOUNT_2_GATEWAY_TOKEN", "rotated-scoped-token-0123456789"),
    ("EXPLABS_ACCOUNT_2_ORG_SLUG", "another-org"),
    ("EXPLABS_ACCOUNT_2_ENABLED", "0"),
    ("EXPLABS_ACCOUNT_2_SERVING_VERIFIED", "0"),
    ("EXPLABS_ACCOUNT_2_TRANSPORT", "direct"),
    ("EXPLABS_ACCOUNT_2_MAX_INFLIGHT", "3"),
    ("EXPLABS_ACCOUNT_2_DAILY_CAP_USD", "0.5"),
    ("EXPLABS_MODEL", "another-model"),
])
def test_configuration_change_during_cap_read_cannot_publish_or_dispatch(
        monkeypatch, b_gateway, name, value):
    _call(b_gateway)
    entered, release = threading.Event(), threading.Event()
    before = len(b_gateway.wire)

    def block(request):
        if request.method == "GET" and request.url.path == "/api/v1/key":
            entered.set()
            assert release.wait(5), "test did not release cap reader"

    b_gateway.hook = block
    pending = _start_call(b_gateway, "configuration-reader")
    try:
        assert entered.wait(5)
        monkeypatch.setenv(name, value)
    finally:
        release.set()
        _join_calls(pending)
    assert len(pending[2]) == 1 and isinstance(pending[2][0], explabs_client.ExperientialError)
    assert b_gateway.wire[before:] == [("GET", "/api/v1/key")]
    assert b_gateway.pool.status()["2"]["verified"] is False
    _assert_idle(b_gateway)


def test_disable_after_first_probe_prevents_every_subsequent_get(monkeypatch, b_gateway):
    def disable(request):
        if request.url.path == "/api/whoami":
            monkeypatch.setenv("EXPLABS_POOL_ENABLED", "0")

    b_gateway.hook = disable
    with pytest.raises(explabs_client.ExperientialError, match="explabs_pool_disabled"):
        _call(b_gateway)
    assert b_gateway.wire == [("GET", "/api/whoami")]
    _assert_idle(b_gateway)


def test_busy_metadata_reader_cannot_lend_its_cap_proof(monkeypatch, b_gateway):
    _call(b_gateway)
    entered, release_get = threading.Event(), threading.Event()
    reader_ready, borrower_ready = threading.Event(), threading.Event()
    release_reader, release_borrower = threading.Event(), threading.Event()
    before = len(b_gateway.wire)

    def block(request):
        if (request.url.path == "/api/v1/key"
                and threading.current_thread().name == "cap-owner"):
            entered.set()
            assert release_get.wait(5)

    original = b_gateway.pool._refresh_candidate_headroom

    def pause_before_selection(*args, **kwargs):
        value = original(*args, **kwargs)
        if threading.current_thread().name == "cap-owner":
            reader_ready.set()
            assert release_reader.wait(5)
        else:
            borrower_ready.set()
            assert release_borrower.wait(5)
        return value

    monkeypatch.setattr(b_gateway.pool, "_refresh_candidate_headroom", pause_before_selection)
    b_gateway.hook = block
    owner = _start_call(b_gateway, "cap-owner")
    borrower = None
    try:
        assert entered.wait(5)
        borrower = _start_call(b_gateway, "cap-borrower")
        assert borrower_ready.wait(5)
        release_get.set()
        assert reader_ready.wait(5)
        assert b_gateway.pool.status()["2"]["metadata_busy"] is False
        release_borrower.set()
        assert borrower[1].wait(5)
        assert isinstance(borrower[2][0], explabs_client.ExperientialError)
        assert b_gateway.wire[before:] == [("GET", "/api/v1/key")]
    finally:
        release_get.set()
        release_borrower.set()
        release_reader.set()
        _join_calls(owner, *([borrower] if borrower is not None else []))
    assert isinstance(owner[2][0], explabs_client.Completion)
    assert b_gateway.wire[before:] == [("GET", "/api/v1/key"),
                                       ("POST", "/v1/chat/completions")]
    _assert_idle(b_gateway)


@pytest.mark.parametrize("hold,late", [
    ("403", "success"), ("403", 503), ("403", 504), ("403", "timeout"),
    ("byok", "success"), ("missing_cost", "success"), ("unknown_lane", "success"),
])
def test_actual_inference_hold_wins_over_late_metadata(b_gateway, hold, late):
    _call(b_gateway)
    post_entered, get_entered = threading.Event(), threading.Event()
    release_post, release_get = threading.Event(), threading.Event()
    before = len(b_gateway.wire)

    def overlap(request):
        caller = threading.current_thread().name
        if caller == "serving" and request.method == "POST":
            post_entered.set()
            assert release_post.wait(5)
            if hold == "403":
                return httpx.Response(403, json={"error": {"code": "model_not_granted",
                    "message": "SECRET_UPSTREAM_TEXT"}})
            payload = b_gateway.normal(request).json()
            if hold == "byok":
                payload["usage"]["is_byok"] = True
            elif hold == "missing_cost":
                del payload["usage"]["cost"]
            else:
                del payload["usage"]["is_byok"]
            return httpx.Response(200, json=payload)
        if caller == "metadata" and request.method == "GET" and request.url.path == "/api/v1/key":
            get_entered.set()
            assert release_get.wait(5)
            if late == "timeout":
                raise httpx.ReadTimeout("SECRET_UPSTREAM_TEXT", request=request)
            if late != "success":
                return httpx.Response(late, json={"error": "SECRET_UPSTREAM_TEXT"})

    b_gateway.hook = overlap
    serving = _start_call(b_gateway, "serving")
    metadata = None
    try:
        assert post_entered.wait(5)
        metadata = _start_call(b_gateway, "metadata")
        assert get_entered.wait(5)
        release_post.set()
        assert serving[1].wait(5)
        expected_hold = {
            "403": "explabs_http_403:model_not_granted", "byok": "explabs_unexpected_byok",
            "missing_cost": "explabs_missing_gateway_cost", "unknown_lane": "explabs_unknown_funding_lane",
        }[hold]
        assert b_gateway.pool.status()["2"]["blocked"] == expected_hold
    finally:
        release_post.set()
        release_get.set()
        _join_calls(serving, *([metadata] if metadata is not None else []))
    assert isinstance(serving[2][0], explabs_client.ExperientialError if hold == "403"
                      else explabs_client.Completion)
    assert metadata is not None and isinstance(metadata[2][0], explabs_client.ExperientialError)
    assert "metadata_unavailable" not in str(metadata[2][0])
    assert sum(method == "POST" for method, _ in b_gateway.wire[before:]) == 1
    assert b_gateway.pool.status()["2"]["blocked"] == expected_hold
    held_wire = list(b_gateway.wire)
    b_gateway.hook = None
    b_gateway.now += 61
    with pytest.raises(explabs_client.ExperientialError):
        _call(b_gateway)
    assert b_gateway.wire == held_wire
    _assert_idle(b_gateway)
