"""Source-only Fable API principal security and budget qualification.

Never reaches Anthropic; this is not provider-credit or production proof.
"""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from types import SimpleNamespace

import pytest

from control_plane.fable_api_principal import (
    MODEL, CapacityReservation, FableApiEffectUnknown, FableApiIncomplete,
    FableApiPrincipal, FableApiRefused, FableRequest, ProviderDispatchReceipt,
)


class Route(Enum):
    FRONTIER_LEAD = "frontier_lead"


class Cognition(Enum):
    METERED_EXCEPTION = "METERED_EXCEPTION"


def _request(**overrides):
    fields = dict(root_id="root-1", attempt_id="attempt-1", question="What should be built?",
                  evidence_brief="The primary decision is disputed between docs A and B.",
                  source_refs=("https://github.com/example/repo/pull/1",),
                  frontier_witness="conflicting canonical owners across two separate products",
                  max_output_tokens=2000)
    fields.update(overrides)
    return FableRequest(**fields)


def _routing(*, enabled=True, cost=3.0, alias="fable.api.principal", model=MODEL):
    profile = SimpleNamespace(provider_alias="anthropic_api", model=model, worker_eligible=False)
    provider = SimpleNamespace(adapter_id="anthropic-api-principal", enabled=enabled,
                               autonomous_allowed=False)
    router = SimpleNamespace(model_aliases={"fable.api.principal": profile},
                             providers={"anthropic_api": provider})
    receipt = SimpleNamespace(why_metered="programmatic review of admitted frozen evidence",
        why_pro_chat_insufficient="exact machine-return binding not available in included chat",
        expected_max_cost=cost, hard_budget_cap=cost,
        budget_authority="capacity-envelope-1", stop_condition="one complete returned review")
    decision = SimpleNamespace(mode=Route.FRONTIER_LEAD, cognition_route=Cognition.METERED_EXCEPTION,
        preferred_model_aliases=(alias,), metered_cognition_receipt=receipt)
    return router, decision


def _response(**overrides):
    fields = dict(id="msg_test1", type="message", model=MODEL, stop_reason="end_turn",
                  content=[{"type":"text","text":"Proposed decision: test the seam with real receipts."}],
                  usage={"input_tokens":100,"output_tokens":150})
    fields.update(overrides)
    return json.dumps(fields).encode()


def _harness(*, enabled=True, cost=3.0, credential="sk-ant-test-do-not-use", send=None, dispatch=None,
             alias="fable.api.principal", model=MODEL):
    router, decision = _routing(enabled=enabled, cost=cost, alias=alias, model=model)
    events = []
    def reserve(root, attempt, authority, ceiling):
        events.append(("reserve", root, attempt, authority, ceiling))
        return CapacityReservation(root, attempt, authority, ceiling, "reservation-1")
    def load_key():
        events.append(("credential",))
        return credential
    def fake_dispatch(root, attempt, reservation, digest):
        events.append(("dispatch", root, attempt, reservation, digest))
        return ProviderDispatchReceipt(root, attempt, reservation, digest, "dispatch-1")
    def fake_send(headers, body):
        events.append(("send", dict(headers), body))
        return 200, _response()
    api = FableApiPrincipal(router=router, decision=decision,
                            bound_root_id="root-1", bound_attempt_id="attempt-1", reserve=reserve,
                            record_dispatch=dispatch or fake_dispatch,
                            credential_loader=load_key, send=send or fake_send)
    return api, events


def test_bounded_invocation_sends_once_only_after_capacity_reservation():
    api, events = _harness()
    outcome = api.invoke(_request())
    assert [x[0] for x in events] == ["reserve", "credential", "dispatch", "send"]
    assert outcome.model == MODEL and outcome.provider_message_id == "msg_test1"
    assert outcome.reservation_ref == "reservation-1"
    assert outcome.source_refs == ("https://github.com/example/repo/pull/1",)
    assert outcome.request_sha256 == hashlib.sha256(events[-1][2]).hexdigest()
    assert outcome.response_sha256 == hashlib.sha256(_response()).hexdigest()
    assert outcome.dispatch_ref == "dispatch-1"
    assert outcome.estimated_usd == pytest.approx((100 * 10 + 150 * 50)/1_000_000)
    sent = events[-1]
    assert sent[1]["anthropic-version"] == "2023-06-01"
    assert sent[1]["x-api-key"] == "sk-ant-test-do-not-use"
    payload = json.loads(sent[2])
    assert payload["model"] == MODEL and payload["stream"] is False
    assert "tools" not in payload and "tool_choice" not in payload
    assert payload["max_tokens"] == 2000
    assert sent[1]["x-api-key"] not in repr(outcome)
    with pytest.raises(FableApiRefused, match="already consumed"):
        api.invoke(_request())
    assert len([x for x in events if x[0] == "send"]) == 1


@pytest.mark.parametrize("change", [
    dict(enabled=False),
    dict(alias="frontier.orchestrator"),
    dict(model="claude-opus-5-5"),
])
def test_default_disabled_and_wrong_route_refuse_without_credentials(change):
    api, events = _harness(**change)
    with pytest.raises(FableApiRefused, match="not a qualified admitted route"):
        api.invoke(_request())
    assert events == []


@pytest.mark.parametrize("invalid", [
    {"question": "  "}, {"evidence_brief": ""},
    {"frontier_witness": ""}, {"task_complexity": "C1_ROUTINE_BOUNDED"},
    {"source_refs": ()}, {"source_refs": ("bad\nref",)},
    {"root_id": "/tmp/outside"}, {"attempt_id": "bad space"},
    {"max_output_tokens": 8193}, {"max_output_tokens": True},
    {"question": "a" * 270000},
])
def test_malformed_requests_never_reach_reservation(invalid):
    api, events = _harness()
    with pytest.raises(FableApiRefused):
        api.invoke(_request(**invalid))
    assert events == []


def test_worst_case_spend_rejected_before_reservation():
    api, events = _harness(cost=0.001)
    with pytest.raises(FableApiRefused, match="worst-case"):
        api.invoke(_request(max_output_tokens=8192))
    assert events == []


def test_validated_atomic_reservation_required_before_api_secret():
    router, decision = _routing()
    calls = []
    def bad_reserve(*args):
        calls.append("reserve")
        return CapacityReservation("wrong-root", "attempt-1", "capacity-envelope-1", 5, "r-1")
    api = FableApiPrincipal(router=router, decision=decision,
                            bound_root_id="root-1", bound_attempt_id="attempt-1",
                            record_dispatch=lambda *_: None,
                            reserve=bad_reserve, credential_loader=lambda: calls.append("secret"),
                            send=lambda *_: calls.append("send"))
    with pytest.raises(FableApiRefused, match="reservation identity"):
        api.invoke(_request())
    assert calls == ["reserve"]


def test_missing_credential_does_not_send():
    api, events = _harness(credential="")
    with pytest.raises(FableApiRefused, match="credential unavailable"):
        api.invoke(_request())
    assert [e[0] for e in events] == ["reserve", "credential"]


def test_lost_send_is_effect_unknown_without_retry():
    calls = []
    def broken(headers, body):
        calls.append("sent")
        raise TimeoutError("secret-sensitive transport error should not escape")
    api, events = _harness(send=broken)
    with pytest.raises(FableApiEffectUnknown, match="effect") as ei:
        api.invoke(_request())
    assert "secret-sensitive" not in str(ei.value)
    with pytest.raises(FableApiRefused, match="already consumed"):
        api.invoke(_request())
    assert calls == ["sent"]


@pytest.mark.parametrize("status,reply", [
    (429, b'blocked'), (500, b'error'),
    (200, b'not-json'),
    (200, _response(model="claude-opus-5-5")),
    (200, _response(stop_reason="max_tokens")),
    (200, _response(usage={"input_tokens":10,"output_tokens":2500})),
    (200, _response(content=[])),
    (200, _response(id="msg_invalid/with-slash")),
    (200, _response(content=[{"type":"text","text":"partial"}, {"type":"tool_use","id":"irrelevant"}])),
])
def test_noncomplete_provider_results_are_nonreplayable(status, reply):
    api, events = _harness(send=lambda *_: (status, reply))
    with pytest.raises(FableApiEffectUnknown):
        api.invoke(_request())
    with pytest.raises(FableApiRefused, match="already consumed"):
        api.invoke(_request())


def test_reject_unapproved_cognition_even_if_provider_enabled():
    router, decision = _routing()
    decision.cognition_route = "CHAT_INCLUDED_DEFAULT"
    api = FableApiPrincipal(router=router, decision=decision,
                            bound_root_id="root-1", bound_attempt_id="attempt-1",
                            record_dispatch=lambda *_: None,
                            reserve=lambda *_: None, credential_loader=lambda: "test-secret-12345",
                            send=lambda *_: (200, _response()))
    with pytest.raises(FableApiRefused, match="not a qualified"):
        api.invoke(_request())


def test_unapproved_budget_receipt_fails_closed():
    router, decision = _routing()
    decision.metered_cognition_receipt.budget_authority = ""
    api = FableApiPrincipal(router=router, decision=decision,
                            bound_root_id="root-1", bound_attempt_id="attempt-1",
                            record_dispatch=lambda *_: None,
                            reserve=lambda *_: None, credential_loader=lambda: "test-secret-12345",
                            send=lambda *_: (200, _response()))
    with pytest.raises(FableApiRefused, match="receipt incomplete"):
        api.invoke(_request())


def test_mismatched_original_attempt_refuses_before_any_capacity_effect():
    api, events = _harness()
    with pytest.raises(FableApiRefused, match="owner-bound original Attempt"):
        api.invoke(_request(root_id="other-root"))
    assert events == []


def test_sender_pins_tls_host_endpoint_and_never_redirects(monkeypatch):
    from control_plane import fable_api_principal as module
    calls = []

    class Response:
        status = 200
        def read(self, max_bytes):
            calls.append(("read", max_bytes))
            return b'{"ok":true}'

    class FakeConnection:
        def __init__(self, host, **kw):
            calls.append(("connect", host, kw["timeout"], kw["context"] is not None))
        def request(self, method, path, body, headers):
            calls.append(("request", method, path, body, dict(headers)))
        def getresponse(self):
            return Response()
        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(module.http.client, "HTTPSConnection", FakeConnection)
    status, raw = module.send_anthropic_once({"x-api-key":"unit-secret"}, b'{}')
    assert status == 200 and raw == b'{"ok":true}'
    assert calls[0][:2] == ("connect", "api.anthropic.com")
    assert calls[1][0:3] == ("request", "POST", "/v1/messages")
    assert len([x for x in calls if x[0] == "request"]) == 1
    assert calls[-1] == ("close",)


def test_sender_never_retries_when_network_fails(monkeypatch):
    from control_plane import fable_api_principal as module
    calls = []

    class FailingConnection:
        def __init__(self, host, **kw):
            calls.append("connect")
        def request(self, *args, **kw):
            calls.append("request")
            raise TimeoutError("external provider state uncertain")
        def close(self):
            calls.append("close")

    monkeypatch.setattr(module.http.client, "HTTPSConnection", FailingConnection)
    with pytest.raises(TimeoutError):
        module.send_anthropic_once({"x-api-key":"unit-secret"}, b'{}')
    assert calls == ["connect", "request", "close"]


def test_parallel_invokers_cannot_double_spend():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    api, events = _harness()
    ready = Barrier(12)
    def invoke(_index):
        ready.wait()
        try:
            answer = api.invoke(_request())
            return "ok" if answer.model == MODEL else "bad"
        except FableApiRefused:
            return "refused"

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(invoke, range(12)))
    assert results.count("ok") == 1
    assert results.count("refused") == 11
    assert len([e for e in events if e[0] == "send"]) == 1


def test_unconfirmed_dispatch_ledger_receipt_never_calls_provider():
    api, events = _harness(dispatch=lambda *_: None)
    with pytest.raises(FableApiEffectUnknown, match="dispatch acknowledgment invalid"):
        api.invoke(_request())
    assert not any(x[0] == "send" for x in events)


def test_failed_dispatch_ledger_write_requires_original_attempt_reconciliation():
    def broken_dispatch(*_args):
        raise RuntimeError("private runtime error must not escape")
    api, events = _harness(dispatch=broken_dispatch)
    with pytest.raises(FableApiEffectUnknown, match="dispatch record uncertain") as ei:
        api.invoke(_request())
    assert "private runtime" not in str(ei.value)
    assert not any(x[0] == "send" for x in events)
