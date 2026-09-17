from __future__ import annotations

import json

import pytest

from control_plane.opencode_go_pooled_transport import (
    AccountChoice,
    OpenCodeGoEffectUnknown,
    OpenCodeGoPoolUnavailable,
    OpenCodeGoPooledTransport,
    OpenCodeGoTransportContractError,
    ProviderRequest,
    UpstreamResponse,
    classify_pre_effect_refusal,
    prepare_upstream_request,
)


GENERATION = "a" * 64


def error_response(status: int, error_type: str) -> UpstreamResponse:
    return UpstreamResponse(
        status=status,
        headers={},
        body=json.dumps({"type": "error", "error": {"type": error_type, "message": "x"},
                         "metadata": {"workspace": "synthetic-workspace", "limitName": "5 hour"}}).encode(),
    )


def ok_response() -> UpstreamResponse:
    return UpstreamResponse(200, {"content-type": "application/json"}, b'{"ok":true}')


def request() -> ProviderRequest:
    return ProviderRequest(
        path="chat/completions",
        session_id="mmx-session-123",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer caller-secret",
            "Host": "wrong.example",
            "Content-Length": "999",
            "x-opencode-session": "caller-overwrite",
        },
        body=b'{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"hello"}]}',
    )


def test_only_go_quota_refusal_is_a_rollover_signal():
    assert classify_pre_effect_refusal(error_response(429, "GoUsageLimitError")) == "usage_limit"
    assert classify_pre_effect_refusal(error_response(401, "AuthError")) is None
    assert classify_pre_effect_refusal(error_response(429, "RateLimitError")) is None
    assert classify_pre_effect_refusal(error_response(401, "CreditsError")) is None
    assert classify_pre_effect_refusal(error_response(403, "RegionError")) is None
    assert classify_pre_effect_refusal(UpstreamResponse(429, {}, b"not-json")) is None


def test_prepare_request_replaces_secret_and_session_headers_without_mutating_body():
    prepared = prepare_upstream_request(
        request(),
        choice=AccountChoice("opencode-go", GENERATION, "acct-a"),
        credential="private-a",
    )
    lower = {key.lower(): value for key, value in prepared.headers.items()}
    assert prepared.url == "https://opencode.ai/zen/go/v1/chat/completions"
    assert lower["authorization"] == "Bearer private-a"
    assert lower["x-opencode-session"] == "mmx-session-123"
    assert lower["user-agent"] == "Mastermind-X/1.0"
    assert "host" not in lower
    assert "content-length" not in lower
    assert b"deepseek-v4.1-flash" in prepared.body
    assert b"hello" in prepared.body


def test_usage_limit_rolls_a_to_b_with_same_session_and_body():
    resolve_calls = []
    sends = []

    def resolver(value):
        resolve_calls.append(value)
        account = "acct-a" if len(resolve_calls) == 1 else "acct-b"
        return AccountChoice("opencode-go", GENERATION, account)

    def sender(value):
        sends.append(value)
        if value.account_id == "acct-a":
            return error_response(429, "GoUsageLimitError")
        return ok_response()

    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=resolver,
        credential_loader=lambda account: f"secret-{account}",
        sender=sender,
        max_rollovers=2,
    )
    receipt = transport.execute(request(), sticky_account_id="acct-a")
    assert receipt.account_id == "acct-b"
    assert receipt.attempted_accounts == ("acct-a", "acct-b")
    assert receipt.rollover_count == 1
    assert receipt.pool_exhausted is False
    assert resolve_calls[1].excluded_account_ids == ("acct-a",)
    assert resolve_calls[1].reason == "usage_limit"
    assert resolve_calls[1].sticky_account_id is None
    assert sends[0].body == sends[1].body == request().body
    assert sends[0].headers["x-opencode-session"] == sends[1].headers["x-opencode-session"]
    assert sends[0].headers["Authorization"] != sends[1].headers["Authorization"]


def test_three_member_waterfall_can_reach_c():
    accounts = iter(("acct-a", "acct-b", "acct-c"))
    sent = []

    def resolver(_value):
        return AccountChoice("opencode-go", GENERATION, next(accounts))

    def sender(value):
        sent.append(value.account_id)
        if value.account_id != "acct-c":
            return error_response(429, "GoUsageLimitError")
        return ok_response()

    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=resolver,
        credential_loader=lambda account: account + "-secret",
        sender=sender,
        max_rollovers=2,
    )
    receipt = transport.execute(request())
    assert sent == ["acct-a", "acct-b", "acct-c"]
    assert receipt.account_id == "acct-c"
    assert receipt.rollover_count == 2


def test_three_exhausted_members_return_last_real_429_without_hidden_fourth_retry():
    accounts = iter(("acct-a", "acct-b", "acct-c"))
    sent = []

    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=lambda _value: AccountChoice("opencode-go", GENERATION, next(accounts)),
        credential_loader=lambda account: account + "-secret",
        sender=lambda value: sent.append(value.account_id) or error_response(429, "GoUsageLimitError"),
        max_rollovers=2,
    )
    receipt = transport.execute(request())
    assert sent == ["acct-a", "acct-b", "acct-c"]
    assert receipt.response.status == 429
    assert receipt.pool_exhausted is False
    assert receipt.stop_reason == "rollover_budget_exhausted"
    assert receipt.rollover_count == 2


def test_auth_refusal_and_other_401_never_switch_accounts():
    accounts = iter(("acct-a", "acct-b"))
    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=lambda _value: AccountChoice("opencode-go", GENERATION, next(accounts)),
        credential_loader=lambda account: account + "-secret",
        sender=lambda value: error_response(401, "AuthError") if value.account_id == "acct-a" else ok_response(),
        max_rollovers=1,
    )
    assert transport.execute(request()).account_id == "acct-a"

    calls = []
    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=lambda _value: AccountChoice("opencode-go", GENERATION, "acct-a"),
        credential_loader=lambda _account: "secret",
        sender=lambda value: calls.append(value.account_id) or error_response(401, "CreditsError"),
        max_rollovers=2,
    )
    receipt = transport.execute(request())
    assert calls == ["acct-a"]
    assert receipt.response.status == 401


def test_sender_exception_is_effect_unknown_and_never_calls_resolver_again():
    resolve_calls = []

    def resolver(value):
        resolve_calls.append(value)
        return AccountChoice("opencode-go", GENERATION, "acct-a" if len(resolve_calls) == 1 else "acct-b")

    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=resolver,
        credential_loader=lambda _account: "secret",
        sender=lambda _value: (_ for _ in ()).throw(TimeoutError("ambiguous")),
        max_rollovers=2,
    )
    with pytest.raises(OpenCodeGoEffectUnknown) as caught:
        transport.execute(request())
    assert caught.value.attempted_accounts == ("acct-a",)
    assert len(resolve_calls) == 1


def test_500_and_generic_429_do_not_trigger_account_switch():
    for response in (UpstreamResponse(500, {}, b"oops"), error_response(429, "RateLimitError")):
        resolve_calls = []
        transport = OpenCodeGoPooledTransport(
            pool_id="opencode-go",
            resolver=lambda value: resolve_calls.append(value) or AccountChoice("opencode-go", GENERATION, "acct-a"),
            credential_loader=lambda _account: "secret",
            sender=lambda _value, response=response: response,
            max_rollovers=2,
        )
        receipt = transport.execute(request())
        assert receipt.account_id == "acct-a"
        assert len(resolve_calls) == 1


def test_membership_generation_cannot_change_mid_logical_request():
    choices = iter(
        (
            AccountChoice("opencode-go", GENERATION, "acct-a"),
            AccountChoice("opencode-go", "b" * 64, "acct-b"),
        )
    )
    sends = []
    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=lambda _value: next(choices),
        credential_loader=lambda _account: "secret",
        sender=lambda value: sends.append(value.account_id) or error_response(429, "GoUsageLimitError"),
        max_rollovers=2,
    )
    with pytest.raises(OpenCodeGoTransportContractError, match="generation changed"):
        transport.execute(request())
    assert sends == ["acct-a"]


def test_resolver_cannot_repeat_excluded_account():
    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=lambda _value: AccountChoice("opencode-go", GENERATION, "acct-a"),
        credential_loader=lambda _account: "secret",
        sender=lambda _value: error_response(429, "GoUsageLimitError"),
        max_rollovers=2,
    )
    with pytest.raises(OpenCodeGoTransportContractError, match="repeated an excluded"):
        transport.execute(request())


def test_no_capacity_is_typed_and_does_not_touch_credentials_or_sender():
    touched = []
    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=lambda _value: None,
        credential_loader=lambda _account: touched.append("credential") or "secret",
        sender=lambda _value: touched.append("send") or ok_response(),
        max_rollovers=2,
    )
    with pytest.raises(OpenCodeGoPoolUnavailable):
        transport.execute(request())
    assert touched == []


def test_invalid_local_credential_fails_before_provider_effect():
    touched = []
    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=lambda _value: AccountChoice("opencode-go", GENERATION, "acct-a"),
        credential_loader=lambda _account: "",
        sender=lambda _value: touched.append("send") or ok_response(),
        max_rollovers=2,
    )
    with pytest.raises(OpenCodeGoTransportContractError, match="credential unavailable"):
        transport.execute(request())
    assert touched == []


def test_no_next_member_after_safe_refusal_preserves_last_real_response():
    calls = []

    def resolver(value):
        calls.append(value)
        if len(calls) == 1:
            return AccountChoice("opencode-go", GENERATION, "acct-a")
        return None

    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=resolver,
        credential_loader=lambda _account: "secret",
        sender=lambda _value: error_response(429, "GoUsageLimitError"),
        max_rollovers=2,
    )
    receipt = transport.execute(request())
    assert receipt.response.status == 429
    assert receipt.account_id == "acct-a"
    assert receipt.attempted_accounts == ("acct-a",)
    assert receipt.pool_exhausted is True


def test_resolver_failure_is_pre_effect_contract_error():
    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=lambda _value: (_ for _ in ()).throw(RuntimeError("capacity unavailable")),
        credential_loader=lambda _account: "secret",
        sender=lambda _value: ok_response(),
        max_rollovers=2,
    )
    with pytest.raises(OpenCodeGoTransportContractError, match="resolution failed"):
        transport.execute(request())


def test_credential_loader_exception_is_pre_effect_and_does_not_send():
    touched = []
    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=lambda _value: AccountChoice("opencode-go", GENERATION, "acct-a"),
        credential_loader=lambda _account: (_ for _ in ()).throw(OSError("missing")),
        sender=lambda _value: touched.append("send") or ok_response(),
        max_rollovers=2,
    )
    with pytest.raises(OpenCodeGoTransportContractError, match="credential unavailable"):
        transport.execute(request())
    assert touched == []


def test_duplicate_case_insensitive_header_is_rejected_before_send():
    value = request()
    bad = ProviderRequest(
        value.path,
        value.session_id,
        {"User-Agent": "one", "user-agent": "two"},
        value.body,
    )
    with pytest.raises(OpenCodeGoTransportContractError, match="duplicate request header"):
        prepare_upstream_request(
            bad,
            choice=AccountChoice("opencode-go", GENERATION, "acct-a"),
            credential="secret",
        )

def test_malformed_sender_response_is_effect_unknown_and_never_replayed():
    calls = []
    transport = OpenCodeGoPooledTransport(
        pool_id="opencode-go",
        resolver=lambda value: calls.append(value) or AccountChoice("opencode-go", GENERATION, "acct-a"),
        credential_loader=lambda _account: "secret",
        sender=lambda _value: UpstreamResponse(200, {}, "not-bytes"),
        max_rollovers=2,
    )
    with pytest.raises(OpenCodeGoEffectUnknown):
        transport.execute(request())
    assert len(calls) == 1


def test_non_bytes_request_body_is_rejected_before_send():
    value = ProviderRequest("chat/completions", "session-1", {}, "not-bytes")
    with pytest.raises(OpenCodeGoTransportContractError, match="request body must be bytes"):
        prepare_upstream_request(
            value,
            choice=AccountChoice("opencode-go", GENERATION, "acct-a"),
            credential="secret",
        )
