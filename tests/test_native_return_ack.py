"""Only a causal native acknowledgment of this CONTINUE enables its reply."""
from dataclasses import replace

import pytest

from control_plane.wake_ledger import (
    AckMode, TrustedAckContext, DeliveryAttempt, LedgerPhase, ack_record,
    acknowledge, attempt_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from integrations.session_bridge.schemas import BridgeError
from tests.test_session_bridge_runtime_return import setup, advanced_identity, seed_wake
from tests.test_native_reply_runtime_fence import prepared


def consumed(s, binding, *, mode=AckMode.REASONING_SESSION, generation=None, key=None, delivered_only=False):
    identity = advanced_identity(s, predecessor_message_key=key or binding.request_message_key)
    requested = seed_wake(s, identity)
    obligation = requested.record.obligation
    repo = WakeLedgerRepository(s.runtime)
    attempt = DeliveryAttempt(obligation_id=obligation.obligation_id, attempt_n=1,
        attempt_command_id=obligation.obligation_id + ':A1', destination_digest='a'*64,
        route_digest='b'*64, binding_id=binding.binding_id,
        binding_generation=generation or binding.binding_generation, session_alias='EXECUTIVE-COO-A',
        reasoning_surface='codex', wake_transport='codex-app-server')
    for phase in (LedgerPhase.DELIVERY_ATTEMPT, LedgerPhase.ACCEPTED, LedgerPhase.DELIVERED):
        repo.append_record(attempt_record(attempt, phase))
    if delivered_only:
        return None
    trusted = TrustedAckContext(ack_mode=mode, target_seat=obligation.declared_target_seat,
        session_alias=attempt.session_alias, reasoning_surface='codex',
        binding_id=binding.binding_id,
        binding_generation=attempt.binding_generation if mode is AckMode.REASONING_SESSION else None,
        operator_authority_receipt='OP-HUMAN-TEST' if mode is AckMode.HUMAN_OPERATOR else None)
    ack = acknowledge(obligation, trusted=trusted, claimed_obligation_ids=(obligation.obligation_id,),
        delivered_command_id=obligation.obligation_id+':A1:DELIVERED' if mode is AckMode.REASONING_SESSION else None)
    return repo.append_record(ack_record(obligation, ack)).event.command_id


def require(s, binding, **kwargs):
    identity = s.target.physical.identity
    return s.owner.require_native_ack(binding, workspace_id=identity.workspace_id,
        channel_id=identity.channel_id, **kwargs)


def test_historical_ack_without_native_turn_evidence_cannot_register_callback(setup):
    s = setup
    binding, _ = prepared(s)
    command = consumed(s, binding)
    before = s.runtime.events.list_events()
    with pytest.raises(BridgeError):
        require(s, binding)
    with s.runtime.store.transaction() as conn:
        with pytest.raises(BridgeError):
            require(s, binding, connection=conn)
    assert s.runtime.events.list_events() == before


@pytest.mark.parametrize('case', ['none', 'delivered', 'human', 'wrong_continuation', 'generation', 'session'])
def test_ambient_or_unrelated_consumption_is_not_native_ack(setup, case):
    s = setup
    binding, _ = prepared(s)
    if case != 'none':
        consumed(s, binding, delivered_only=case=='delivered',
                 mode=AckMode.HUMAN_OPERATOR if case=='human' else AckMode.REASONING_SESSION,
                 key='asd-foreign-continue' if case=='wrong_continuation' else None,
                 generation=9 if case=='generation' else None)
    if case == 'session':
        s.facts.provider_session_id = '22222222-2222-4444-8888-999999999999'
    with pytest.raises(BridgeError):
        require(s, binding)
