"""Real Runtime/port/consumer proof; typed hermetic transport is source evidence only.

All positive authority originates in the enabled-before-Root public R125 setup.
Corrupt evidence is appended through normal APIs; no Event update/delete or
SQL-manufactured positive, fresh provider turn, credit, completion or release.
"""
from __future__ import annotations

import dataclasses

import pytest

from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.executive_orchestration_result import RawRoleResultObservation
from control_plane.executive_runtime import AttemptLease, AttemptStatus, StateConflict
from control_plane.operator_harness_contract import (
    CandidateResult, EventCursor, LaunchDecision, NormalizedEvent, TurnRef, TurnStartObservation,
)
from control_plane.operator_harness_orchestrator import (
    OperatorHarnessOrchestrationError, OperatorHarnessOrchestrator,
    OperatorLaunchRefused, OperatorTurnReceipt,
)
from tests.test_executive_coo_r124_domain_turn import (
    TypedHermeticConsumptionAdapter, _append_negative_event,
    _fresh_orchestrator_for_domain_attempt, _real_consumption_context,
)
from tests.test_executive_coo_r125_domain_seal import ObservedConsumptionAdapter, _unchecked
from tests.test_executive_coo_r119_later_turn import _inventory


def _setup(tmp_path, monkeypatch, *, session_event=False):
    rt, root, domain, attempt, session, _, _, _, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    body = dict(schema_version="mastermind.executive_coo_domain_consumption/v1", root_job_id=root.job_id,
        domain_job_id=domain.job_id, domain_attempt_id=attempt, consumption_projection_digest=digest,
        consumed_result="工作與獨立審查已消化 · reviewed result")
    class SessionEventAdapter(ObservedConsumptionAdapter):
        def read_events(self, cursor, *, timeout_seconds=30.0):
            events, next_cursor = super().read_events(cursor, timeout_seconds=timeout_seconds)
            event = NormalizedEvent(cursor.attempt_id, cursor.session_epoch_id,
                cursor.process_generation_id, None, "session.metadata")
            return events + (event,), dataclasses.replace(next_cursor, local_sequence=next_cursor.local_sequence + 1)
    adapter_type = SessionEventAdapter if session_event else ObservedConsumptionAdapter
    adapter = adapter_type(session.observation.provider_session_id, body)
    orchestrator, lease = _fresh_orchestrator_for_domain_attempt(rt, attempt, adapter)
    receipt = orchestrator.run_domain_consumption_turn(session, operation_id=op,
        expected_consumption_projection_digest=digest)
    raw = adapter.observe_raw_role_result(receipt.turn)
    args = dict(observation=raw, domain_attempt_id=attempt, lease_token=lease.lease_token,
        command_id=f"coo-cycle:{root.job_id}:domain-consumption-seal:{attempt}:{receipt.turn.turn_id}")
    adapter.raw_calls.clear()  # Count this evidence consumer's reads separately.
    return (rt, root, domain, adapter, receipt, args), session, orchestrator.runtime, orchestrator, lease, op.command_id


def test_complete_result_through_real_port_replays_with_preserved_plan_and_identity(tmp_path, monkeypatch):
    ctx, session, port, orchestrator, lease, _ = _setup(tmp_path, monkeypatch)
    rt, root, domain, adapter, receipt, args = ctx
    initial = rt.events.get_event_by_command_id('orchestration-result-seal:' + session.attempt_id)
    before = _inventory(rt)
    sealed = orchestrator.seal_domain_consumption_result(session, receipt)
    after = _inventory(rt)
    assert sealed['consumption_result'] == adapter.body
    assert sealed['consumed_result_byte_length'] == len(adapter.body['consumed_result'].encode())
    assert lease.lease_token not in repr(sealed)
    assert len(after['events']) == len(before['events']) + 1
    for table in before:
        if table != 'events': assert before[table] == after[table], table
    assert rt.events.get_event_by_command_id(args['command_id']).payload == sealed
    assert rt.events.get_event_by_command_id(initial.command_id) == initial
    assert rt.attempts.get_attempt(session.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert rt.jobs.get_job(domain.job_id).current_attempt_id == session.attempt_id
    assert len(adapter.begin_turn_calls) == len(adapter.raw_calls) == 1
    assert orchestrator.seal_domain_consumption_result(session, receipt) == sealed
    assert _inventory(rt) == after
    fresh = OperatorHarnessOrchestrator(port, adapter, attestation_reader=lambda *_: session.observed)
    assert fresh.seal_domain_consumption_result(session, receipt) == sealed
    assert _inventory(rt) == after and len(adapter.begin_turn_calls) == 1
    assert adapter.raw_calls == [receipt.turn] * 3


@pytest.mark.parametrize('bad', ['attempt', 'turn_attempt', 'untyped_turn', 'fence', 'token', 'untyped_raw'])
def test_bound_port_rejects_foreign_lease_or_untyped_inputs_without_durable_effect(tmp_path, monkeypatch, bad):
    ctx, session, port, _, lease, _ = _setup(tmp_path, monkeypatch)
    rt, _, _, _, receipt, args = ctx
    attempt, turn, raw = session.attempt_id, receipt.turn, args['observation']
    if bad == 'attempt': attempt = 'foreign-attempt'
    if bad == 'turn_attempt': turn = dataclasses.replace(turn, attempt_id='foreign-attempt')
    if bad == 'untyped_turn': turn = dataclasses.asdict(turn)
    if bad == 'untyped_raw': raw = {'consumed_result': 'caller summary'}
    if bad == 'fence':
        port = ExecutiveOperatorHarnessPort(rt, AttemptLease(
            dataclasses.replace(lease.attempt, fence_generation=lease.attempt.fence_generation + 1), lease.lease_token))
    if bad == 'token': port = ExecutiveOperatorHarnessPort(rt, AttemptLease(lease.attempt, 'foreign-authority'))
    before = _inventory(rt)
    with pytest.raises(StateConflict): port.seal_operator_domain_consumption(attempt, turn, raw)
    assert _inventory(rt) == before


@pytest.mark.parametrize('bad', [
    'session_attempt', 'epoch_attempt', 'epoch', 'generation', 'generation_epoch',
    'epoch_worker', 'generation_worker', 'receipt_attempt', 'turn_attempt', 'turn',
    'cursor_attempt', 'cursor_epoch', 'cursor_generation', 'cursor_turn',
    'candidate_attempt', 'candidate_epoch', 'candidate_generation', 'event_turn',
    'ack', 'missing_native', 'nonallow', 'fabricated_allow', 'untyped_session', 'untyped_receipt', 'untyped_turn',
])
def test_foreign_local_receipts_refuse_before_any_adapter_observation(tmp_path, monkeypatch, bad):
    ctx, session, _, orchestrator, _, _ = _setup(tmp_path, monkeypatch)
    rt, _, _, adapter, receipt, _ = ctx
    if bad == 'session_attempt': session = dataclasses.replace(session, attempt_id='foreign')
    if bad.startswith('epoch_'):
        field = {'epoch_attempt': 'attempt_id', 'epoch_worker': 'worker_id'}[bad]
        session = dataclasses.replace(session, epoch=dataclasses.replace(session.epoch, **{field: 'foreign'}))
    if bad == 'epoch': session = dataclasses.replace(session, epoch=dataclasses.replace(session.epoch, session_epoch_id='foreign'))
    if bad == 'generation': session = dataclasses.replace(session, generation=dataclasses.replace(session.generation, process_generation_id='foreign'))
    if bad in {'generation_epoch', 'generation_worker'}:
        field = 'session_epoch_id' if bad == 'generation_epoch' else 'worker_id'
        session = dataclasses.replace(session, generation=dataclasses.replace(session.generation, **{field: 'foreign'}))
    if bad == 'receipt_attempt': receipt = dataclasses.replace(receipt, attempt_id='foreign')
    if bad in {'turn_attempt', 'turn'}:
        field = 'attempt_id' if bad == 'turn_attempt' else 'turn_id'
        receipt = dataclasses.replace(receipt, turn=dataclasses.replace(receipt.turn, **{field: 'foreign'}))
    if bad.startswith('cursor_') or bad.startswith('candidate_'):
        owner, suffix = bad.split('_', 1)
        field = {'attempt': 'attempt_id', 'epoch': 'session_epoch_id', 'generation': 'process_generation_id', 'turn': 'turn_id'}[suffix]
        receipt = dataclasses.replace(receipt, **{owner: dataclasses.replace(getattr(receipt, owner), **{field: 'foreign'})})
    if bad == 'event_turn': receipt = dataclasses.replace(receipt, events=(dataclasses.replace(receipt.events[0], turn_id='foreign'),))
    if bad == 'ack': receipt = dataclasses.replace(receipt, start=dataclasses.replace(receipt.start, acknowledged=False))
    if bad == 'missing_native': receipt = dataclasses.replace(receipt, start=dataclasses.replace(receipt.start, provider_native_turn_id=None))
    if bad == 'nonallow': session = dataclasses.replace(session, launch=dataclasses.replace(session.launch, decision=LaunchDecision.REFUSE_SERVED_MODEL_UNKNOWN))
    if bad == 'fabricated_allow': session = dataclasses.replace(session, launch=dataclasses.replace(session.launch, mismatch_reasons=('caller fiction',)))
    if bad == 'untyped_session': session = {}
    if bad == 'untyped_receipt': receipt = {}
    if bad == 'untyped_turn': receipt = dataclasses.replace(receipt, turn={})
    before = _inventory(rt)
    with pytest.raises(OperatorHarnessOrchestrationError): orchestrator.seal_domain_consumption_result(session, receipt)
    assert _inventory(rt) == before and adapter.raw_calls == []


@pytest.mark.parametrize('bad', ['missing_extension', 'untyped', 'foreign_session', 'foreign_turn', 'foreign_native', 'digest', 'body', 'float_bytes'])
def test_real_consumer_refuses_missing_or_altered_raw_without_durable_effect(tmp_path, monkeypatch, bad):
    ctx, session, port, _, _, _ = _setup(tmp_path, monkeypatch)
    rt, _, _, actual, receipt, args = ctx
    class AlteredAdapter(TypedHermeticConsumptionAdapter):
        def observe_raw_role_result(self, turn):
            raw = actual.observe_raw_role_result(turn)
            if bad == 'untyped': return {'raw': 'caller summary'}
            changes = {
                'foreign_session': {'provider_session_id': 'foreign'},
                'foreign_turn': {'turn_id': 'foreign'},
                'foreign_native': {'provider_native_turn_id': 'foreign'},
                'digest': {'canonical_result_digest': 'b' * 64},
                'body': {'canonical_result_json': '{}'},
                'float_bytes': {'canonical_result_byte_length': float(raw.canonical_result_byte_length)},
            }
            return _unchecked(raw, **changes[bad])
    adapter = TypedHermeticConsumptionAdapter() if bad == 'missing_extension' else AlteredAdapter()
    consumer = OperatorHarnessOrchestrator(port, adapter, attestation_reader=lambda *_: session.observed)
    before = _inventory(rt)
    with pytest.raises((OperatorHarnessOrchestrationError, StateConflict)):
        consumer.seal_domain_consumption_result(session, receipt)
    assert _inventory(rt) == before


@pytest.mark.parametrize('link', ['operation_id', 'candidate_event_command_id', 'unknown', 'foreign_native'])
def test_appended_affiliated_or_unknown_evidence_refuses_through_real_consumer(tmp_path, monkeypatch, link):
    ctx, session, _, orchestrator, _, op = _setup(tmp_path, monkeypatch)
    rt, _, _, adapter, receipt, _ = ctx
    event = rt.events.get_event_by_command_id(op)
    if link in {'unknown', 'foreign_native'}:
        kind = 'OPERATOR_OPERATION_EFFECT_UNKNOWN' if link == 'unknown' else 'OPERATOR_OPERATION_APPLIED'
        payload = {'phase': 'negative-fixture', 'detail': 'ambiguous'} if link == 'unknown' else {'provider_native_turn_id': 'foreign-native'}
        _append_negative_event(rt, event, command=op + ':negative-' + link, event_type=kind, payload=payload)
    else:
        payload = {link: op if link == 'operation_id' else 'ohf-candidate:' + receipt.turn.turn_id}
        with rt.store.transaction() as connection:
            rt.store.append_event(connection, aggregate_type='job', aggregate_id='foreign-root',
                job_id=None, attempt_id=None, worker_id=None, quota_class=None,
                event_type='COO_DOMAIN_CONSUMPTION_SEALED', actor='negative-fixture',
                command_id='negative-alias:' + link, payload=payload)
    before = _inventory(rt)
    with pytest.raises(StateConflict): orchestrator.seal_domain_consumption_result(session, receipt)
    assert _inventory(rt) == before and len(adapter.begin_turn_calls) == 1


@pytest.mark.parametrize('committed', [False, True])
def test_typed_receipt_cannot_substitute_for_missing_real_native_ack(tmp_path, monkeypatch, committed):
    rt, root, domain, attempt, session, _, original, lease, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    turn = original.runtime.begin_operator_domain_consumption_turn(attempt, session.generation, op,
        expected_consumption_projection_digest=digest)
    if committed: original.runtime.commit_operator_provider_dispatch(attempt, op, 'begin_turn')
    # Deliberately unobserved typed labels, never positive SQL/native evidence.
    adapter = ObservedConsumptionAdapter(session.observation.provider_session_id,
        dict(schema_version='mastermind.executive_coo_domain_consumption/v1', root_job_id=root.job_id,
            domain_job_id=domain.job_id, domain_attempt_id=attempt, consumption_projection_digest=digest,
            consumed_result='unobserved typed text'))
    class UnobservedAdapter(TypedHermeticConsumptionAdapter):
        def observe_raw_role_result(self, actual_turn):
            assert actual_turn == turn
            from control_plane.executive_orchestration_result import canonical_bytes
            import hashlib
            wire = canonical_bytes(adapter.body)
            return RawRoleResultObservation(attempt, turn.session_epoch_id, turn.process_generation_id,
                turn.turn_id, adapter.provider_session_id, 'unobserved-native', 'a' * 64,
                wire.decode(), hashlib.sha256(wire).hexdigest(), len(wire))
    receipt = OperatorTurnReceipt(attempt, turn, TurnStartObservation('unobserved-native', True), (),
        EventCursor(attempt, turn.session_epoch_id, turn.process_generation_id, 0, turn.turn_id),
        CandidateResult(attempt, turn.session_epoch_id, turn.process_generation_id, 'a' * 64, 'unobserved'))
    consumer = OperatorHarnessOrchestrator(ExecutiveOperatorHarnessPort(rt, lease), UnobservedAdapter(),
        attestation_reader=lambda *_: session.observed)
    before = _inventory(rt)
    with pytest.raises(StateConflict): consumer.seal_domain_consumption_result(session, receipt)
    assert _inventory(rt) == before


def test_committed_session_scoped_event_remains_valid_for_consumption(tmp_path, monkeypatch):
    ctx, session, _, consumer, _, _ = _setup(tmp_path, monkeypatch, session_event=True)
    rt, _, _, adapter, receipt, _ = ctx
    assert receipt.events[-1].turn_id is None
    sealed = consumer.seal_domain_consumption_result(session, receipt)
    assert sealed['consumption_result'] == adapter.body and len(adapter.begin_turn_calls) == 1
    before = _inventory(rt)
    assert consumer.seal_domain_consumption_result(session, receipt) == sealed
    assert _inventory(rt) == before


@pytest.mark.parametrize('all_ids', [False, True])
def test_coherent_foreign_session_and_turn_pair_refuses_before_raw_observation(tmp_path, monkeypatch, all_ids):
    ctx, session, _, consumer, _, _ = _setup(tmp_path, monkeypatch)
    rt, _, _, adapter, receipt, _ = ctx
    attempt = 'coherent-foreign-attempt'
    epoch = 'coherent-foreign-epoch' if all_ids else receipt.turn.session_epoch_id
    generation = 'coherent-foreign-generation' if all_ids else receipt.turn.process_generation_id
    turn_id = 'coherent-foreign-turn' if all_ids else receipt.turn.turn_id
    native = 'coherent-foreign-native' if all_ids else receipt.start.provider_native_turn_id
    foreign_session = dataclasses.replace(session, attempt_id=attempt,
        epoch=dataclasses.replace(session.epoch, attempt_id=attempt, session_epoch_id=epoch),
        generation=dataclasses.replace(session.generation, session_epoch_id=epoch, process_generation_id=generation),
        observation=dataclasses.replace(session.observation,
            provider_session_id='coherent-foreign-provider' if all_ids else session.observation.provider_session_id))
    foreign_receipt = dataclasses.replace(receipt, attempt_id=attempt,
        turn=TurnRef(turn_id, epoch, generation, attempt),
        start=dataclasses.replace(receipt.start, provider_native_turn_id=native),
        cursor=dataclasses.replace(receipt.cursor, attempt_id=attempt, session_epoch_id=epoch, process_generation_id=generation, turn_id=turn_id),
        candidate=dataclasses.replace(receipt.candidate, attempt_id=attempt, session_epoch_id=epoch, process_generation_id=generation),
        events=tuple(dataclasses.replace(e, attempt_id=attempt, session_epoch_id=epoch, process_generation_id=generation,
            turn_id=None if e.turn_id is None else turn_id) for e in receipt.events))
    before = _inventory(rt)
    with pytest.raises(OperatorHarnessOrchestrationError, match='bound RuntimePort Attempt'):
        consumer.seal_domain_consumption_result(foreign_session, foreign_receipt)
    assert adapter.raw_calls == [] and _inventory(rt) == before
    assert len(adapter.begin_turn_calls) == 1


@pytest.mark.parametrize('bad', ['absent', 'none', 'empty', 'whitespace', 'padded', 'bool', 'int', 'float', 'list', 'dict', 'string_subclass'])
def test_unknown_or_malformed_binding_refuses_even_matching_malformed_receipts(tmp_path, monkeypatch, bad):
    ctx, session, port, _, _, _ = _setup(tmp_path, monkeypatch)
    rt, _, _, adapter, receipt, _ = ctx
    class StringSubclass(str): pass
    values = dict(absent=None, none=None, empty='', whitespace=' ', padded=' ATT-foreign ',
        bool=True, int=1, float=1.0, list=[], dict={}, string_subclass=StringSubclass(session.attempt_id))
    value = values[bad]
    class MissingBinding:
        def seal_operator_domain_consumption(self, *args):
            pytest.fail('missing binding must never reach seal delegation')
    class MalformedBinding(MissingBinding):
        reads = 0
        @property
        def attempt_id(self):
            self.reads += 1
            return value
    proxy = MissingBinding() if bad == 'absent' else MalformedBinding()
    session = dataclasses.replace(session, attempt_id=value, epoch=dataclasses.replace(session.epoch, attempt_id=value))
    receipt = dataclasses.replace(receipt, attempt_id=value, turn=dataclasses.replace(receipt.turn, attempt_id=value),
        cursor=dataclasses.replace(receipt.cursor, attempt_id=value), candidate=dataclasses.replace(receipt.candidate, attempt_id=value),
        events=tuple(dataclasses.replace(e, attempt_id=value) for e in receipt.events))
    consumer = OperatorHarnessOrchestrator(proxy, adapter, attestation_reader=lambda *_: session.observed)
    before = _inventory(rt)
    with pytest.raises(OperatorHarnessOrchestrationError, match='bound RuntimePort Attempt'):
        consumer.seal_domain_consumption_result(session, receipt)
    assert adapter.raw_calls == [] and _inventory(rt) == before
    if bad != 'absent': assert proxy.reads == 1


@pytest.mark.parametrize('kind', ['epoch', 'generation', 'turn'])
@pytest.mark.parametrize('value', [None, '', ' ', False])
def test_coherent_malformed_current_identity_refuses_before_raw(tmp_path, monkeypatch, kind, value):
    ctx, session, _, consumer, _, _ = _setup(tmp_path, monkeypatch)
    rt, _, _, adapter, receipt, _ = ctx
    field = {'epoch': 'session_epoch_id', 'generation': 'process_generation_id', 'turn': 'turn_id'}[kind]
    if kind == 'epoch':
        session = dataclasses.replace(session, epoch=dataclasses.replace(session.epoch, session_epoch_id=value),
            generation=dataclasses.replace(session.generation, session_epoch_id=value))
    if kind == 'generation': session = dataclasses.replace(session, generation=dataclasses.replace(session.generation, process_generation_id=value))
    receipt = dataclasses.replace(receipt, turn=dataclasses.replace(receipt.turn, **{field: value}),
        cursor=dataclasses.replace(receipt.cursor, **{field: value}),
        events=tuple(dataclasses.replace(e, **{field: value}) for e in receipt.events))
    if kind != 'turn': receipt = dataclasses.replace(receipt, candidate=dataclasses.replace(receipt.candidate, **{field: value}))
    before = _inventory(rt)
    with pytest.raises(OperatorHarnessOrchestrationError, match='canonical initial G1'):
        consumer.seal_domain_consumption_result(session, receipt)
    assert adapter.raw_calls == [] and _inventory(rt) == before


@pytest.mark.parametrize('kind', ['epoch', 'generation'])
@pytest.mark.parametrize('value', [None, True, 1.0, 0, 2])
def test_initial_g1_numbers_are_exact_integers_before_raw(tmp_path, monkeypatch, kind, value):
    ctx, session, _, consumer, _, _ = _setup(tmp_path, monkeypatch)
    rt, _, _, adapter, receipt, _ = ctx
    if kind == 'epoch': session = dataclasses.replace(session, epoch=dataclasses.replace(session.epoch, epoch_number=value))
    else: session = dataclasses.replace(session, generation=dataclasses.replace(session.generation, generation_number=value))
    before = _inventory(rt)
    with pytest.raises(OperatorHarnessOrchestrationError, match='canonical initial G1'):
        consumer.seal_domain_consumption_result(session, receipt)
    assert adapter.raw_calls == [] and _inventory(rt) == before


@pytest.mark.parametrize('value', [None, '', ' ', ' padded ', True, 1])
def test_supplied_provider_session_is_not_coerced_before_raw(tmp_path, monkeypatch, value):
    ctx, session, _, consumer, _, _ = _setup(tmp_path, monkeypatch)
    rt, _, _, adapter, receipt, _ = ctx
    session = dataclasses.replace(session, observation=dataclasses.replace(session.observation, provider_session_id=value))
    before = _inventory(rt)
    with pytest.raises(OperatorHarnessOrchestrationError): consumer.seal_domain_consumption_result(session, receipt)
    assert adapter.raw_calls == [] and _inventory(rt) == before


@pytest.mark.parametrize('value', [True, None, -1, 1.0, '1'])
def test_cursor_sequence_is_exact_nonnegative_integer_before_raw(tmp_path, monkeypatch, value):
    ctx, session, _, consumer, _, _ = _setup(tmp_path, monkeypatch)
    rt, _, _, adapter, receipt, _ = ctx
    receipt = dataclasses.replace(receipt, cursor=dataclasses.replace(receipt.cursor, local_sequence=value))
    before = _inventory(rt)
    with pytest.raises(OperatorHarnessOrchestrationError): consumer.seal_domain_consumption_result(session, receipt)
    assert adapter.raw_calls == [] and _inventory(rt) == before


@pytest.mark.parametrize('field', ['requested', 'observed'])
def test_launch_nested_types_refuse_before_raw(tmp_path, monkeypatch, field):
    ctx, session, _, consumer, _, _ = _setup(tmp_path, monkeypatch)
    rt, _, _, adapter, receipt, _ = ctx
    session = dataclasses.replace(session, launch=dataclasses.replace(session.launch, **{field: None}))
    before = _inventory(rt)
    with pytest.raises(OperatorHarnessOrchestrationError): consumer.seal_domain_consumption_result(session, receipt)
    assert adapter.raw_calls == [] and _inventory(rt) == before
