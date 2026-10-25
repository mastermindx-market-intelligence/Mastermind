"""Source-only Fable API principal security and budget qualification.

Never reaches Anthropic; this is not provider-credit or production proof.
"""
from __future__ import annotations

import json
from enum import Enum
from types import SimpleNamespace

import pytest

from control_plane.fable_api_principal import (
    MODEL, CapacityReservation, FableApiEffectUnknown, FableApiIncomplete,
    FableApiPrincipal, FableApiRefused, FableRequest,
)


class Route(Enum):
    FRONTIER_LEAD = "frontier_lead"


class Cognition(Enum):
    METERED_EXCEPTION = "METERED_EXCEPTION"


def _request(**overrides):
    fields = dict(root_id="root-1", attempt_id="attempt-1", question="What should be built?",
                  evidence_brief="The primary decision is disputed between docs A and B.",
                  source_refs=("https://github.com/example/repo/pull/1",), max_output_tokens=2000)
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


def _harness(*, enabled=True, cost=3.0, credential="sk-ant-test-do-not-use", send=None,
             alias="fable.api.principal", model=MODEL):
    router, decision = _routing(enabled=enabled, cost=cost, alias=alias, model=model)
    events = []
    def reserve(root, attempt, authority, ceiling):
        events.append(("reserve", root, attempt, authority, ceiling))
        return CapacityReservation(root, attempt, authority, ceiling, "reservation-1")
    def load_key():
        events.append(("credential",))
        return credential
    def fake_send(headers, body):
        events.append(("send", dict(headers), body))
        return 200, _response()
    api = FableApiPrincipal(router=router, decision=decision, reserve=reserve,
                            credential_loader=load_key, send=send or fake_send)
    return api, events


def test_bounded_invocation_sends_once_only_after_capacity_reservation():
    api, events = _harness()
    outcome = api.invoke(_request())
    assert [x[0] for x in events] == ["reserve", "credential", "send"]
    assert outcome.model == MODEL and outcome.provider_message_id == "msg_test1"
    assert outcome.reservation_ref == "reservation-1"
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
                            reserve=lambda *_: None, credential_loader=lambda: "test-secret-12345",
                            send=lambda *_: (200, _response()))
    with pytest.raises(FableApiRefused, match="not a qualified"):
        api.invoke(_request())


def test_unapproved_budget_receipt_fails_closed():
    router, decision = _routing()
    decision.metered_cognition_receipt.budget_authority = ""
    api = FableApiPrincipal(router=router, decision=decision,
                            reserve=lambda *_: None, credential_loader=lambda: "test-secret-12345",
                            send=lambda *_: (200, _response()))
    with pytest.raises(FableApiRefused, match="receipt incomplete"):
        api.invoke(_request())
