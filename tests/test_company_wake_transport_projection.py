"""Source-only transport tests for the Codex App Server company-read projection."""
from __future__ import annotations

import asyncio

import pytest

from control_plane.operator_harness_contract import AttentionCompanyReadProjection
from control_plane.wake_dispatcher import (
    TransportOutcome, TransportReceipt, WakeNudge, WakeTransportCompletion,
    normalize_transport_completion,
)
from integrations.executive_wake.codex_app_server import (
    CodexAppServerWakeDispatcher, CodexWakeDeliveryObservation,
)

NUDGE_ID = "NUDGE-" + "b" * 32
WAKE_ID = "WAKE-" + "a" * 32
_WAKE = {
    "session_alias": "EXECUTIVE-CEO-A", "reasoning_surface": "codex",
    "wake_transport": "codex-app-server", "binding_id": "bind-a",
    "binding_generation": 1, "native_handle": "thread-a",
    "account_label": "codex-pro-a", "destination_digest": "d" * 16,
    "obligation_ids": (WAKE_ID,), "attempt_command_ids": (WAKE_ID + ":delivery:1",),
    "nudge_id": NUDGE_ID,
}
_COMPANY = {
    "target_attempt_id": "ATT-a", "process_generation_id": "gen-a",
    "binding_id": "bind-a", "binding_generation": 1,
    "provider_session_id": "thread-a", "provider_native_turn_id": "turn-a",
    "nudge_id": NUDGE_ID, "consultation_ref": "consult-" + "c" * 32,
    "result_sha256": "1" * 64, "native_item_sha256": "2" * 64,
}


def _wake(**overrides) -> WakeNudge:
    return WakeNudge(**(_WAKE | overrides))


def _company(**overrides) -> AttentionCompanyReadProjection:
    return AttentionCompanyReadProjection(**(_COMPANY | overrides))


def _receipt(outcome=TransportOutcome.DELIVERED, reason_code="delivered"):
    return TransportReceipt(
        outcome=outcome, reason_code=reason_code,
        created_at="2026-10-04T00:00:00Z", details=(("nudge_id", NUDGE_ID),),
    )


def _observation(**overrides) -> CodexWakeDeliveryObservation:
    base = {
        "native_handle": "thread-a", "nudge_id": NUDGE_ID, "accepted": True,
        "delivered": True, "target_ack_projection": None,
        "company_read_projection": None,
    }
    return CodexWakeDeliveryObservation(**(base | overrides))


class _FakeClient:
    def __init__(self, observation, late_observation=None):
        self.observation, self.late_observation = observation, late_observation
        self.deliver_calls = self.reconcile_calls = 0

    async def deliver_wake(self, *, native_handle, nudge_id, opaque_ids, instruction):
        self.deliver_calls += 1
        return self.observation

    async def reconcile_wake(self, *, native_handle, nudge_id, opaque_ids):
        self.reconcile_calls += 1
        return self.late_observation

def test_nudge_propagates_company_projection_on_delivered_completion():
    company = _company()
    client = _FakeClient(_observation(company_read_projection=company))
    result = asyncio.run(CodexAppServerWakeDispatcher(client).nudge(_wake()))
    assert isinstance(result, WakeTransportCompletion)
    assert result.company_read_projection is company
    assert result.target_ack_projection is None
    assert result.receipt.outcome is TransportOutcome.DELIVERED
    assert result.receipt.details == (("nudge_id", NUDGE_ID),)
    assert client.deliver_calls == 1


def test_reconcile_propagates_late_company_projection_without_resubmission():
    company = _company()
    client = _FakeClient(
        _observation(), late_observation=_observation(company_read_projection=company)
    )
    result = asyncio.run(CodexAppServerWakeDispatcher(client).reconcile(_wake()))
    assert isinstance(result, WakeTransportCompletion)
    assert result.company_read_projection is company
    assert result.target_ack_projection is None
    assert result.receipt.details == (("nudge_id", NUDGE_ID),)
    assert client.reconcile_calls == 1
    assert client.deliver_calls == 0


def test_company_projection_is_hidden_from_repr():
    company = _company()
    completion = WakeTransportCompletion(receipt=_receipt(), company_read_projection=company)
    observation = _observation(company_read_projection=company)
    assert "company_read_projection" not in repr(completion)
    assert "company_read_projection" not in repr(observation)
    assert "consult-" not in repr(completion)

def test_normalize_transport_completion_never_promotes_company_to_ack():
    completion = WakeTransportCompletion(receipt=_receipt(), company_read_projection=_company())
    receipt, ack = normalize_transport_completion(completion)
    assert ack is None
    assert receipt is completion.receipt


@pytest.mark.parametrize(
    "build",
    [
        lambda: WakeTransportCompletion(receipt=_receipt(), company_read_projection=object()),
        lambda: WakeTransportCompletion(
            receipt=_receipt(TransportOutcome.ACCEPTED, "accepted"),
            company_read_projection=_company(),
        ),
        lambda: _observation(company_read_projection=object()),
        lambda: _observation(delivered=False, company_read_projection=_company()),
        lambda: _observation(company_read_projection=_company(provider_session_id="thread-x")),
        lambda: _observation(company_read_projection=_company(nudge_id="NUDGE-" + "e" * 32)),
    ],
)
def test_company_projection_refusals(build):
    with pytest.raises(ValueError):
        build()
