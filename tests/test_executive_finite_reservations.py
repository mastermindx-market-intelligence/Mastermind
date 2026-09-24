"""Actual SQLite finite reservation/dispatch and settlement boundaries."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from test_executive_finite_guards import (
    MutableClock, _register, _finite_root, _bound_definition, _issue, _arm,
    _orchestration_profile, _orchestration_attestation, _precomputed_admission_definition,
)
from control_plane.executive_runtime import Runtime, StateConflict, OrchestrationDispatchOutcome
from control_plane.operator_harness_contract import OperationId, ProcessIdentityObservation, TurnStartObservation
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation


def _snapshot(runtime):
    with sqlite3.connect(runtime.store.path) as c:
        return {table: c.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()
                for table in ('jobs','attempts','worker_quota_classes','harness_session_epochs','process_generations','events')}


def _claimed(base, *, cap=1, ttl=20, seal=True):
    clock = MutableClock()
    runtime = Runtime.at(base, clock=clock)
    _register(runtime, 'worker-a')
    envelope, root = _finite_root(runtime, 'CEO-RESERVATION-001')
    definition = _bound_definition(root, envelope, runtime=runtime, cap=cap,
                                   expires_at_ms=clock.value + ttl * 1000)
    context = _issue(definition)
    runtime.store.bind_finite_control_context(context)
    _arm(runtime, context)
    planner = runtime.jobs.create_cycle_planner(root.job_id, command_id=f'coo-cycle:{root.job_id}:create-planner:0')
    d = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1', worker_id='worker-a')
    assert isinstance(d, OrchestrationDispatchOutcome)
    profile = _orchestration_profile(d)
    if seal:
        runtime.operator_harness.seal_operator_harness_attempt(d.attempt.attempt_id,
            fence_generation=d.attempt.fence_generation, lease_token=d.lease_token, requested=profile)
    return runtime, clock, root, d, profile, context


def _lease(d):
    return dict(fence_generation=d.attempt.fence_generation, lease_token=d.lease_token)


def _start(runtime, d, profile):
    harness = runtime.operator_harness
    op = OperationId('ohf-op:reservation-start')
    epoch, generation = harness.reserve_start(d.attempt.attempt_id, operation_id=op, **_lease(d))
    assert harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id, operation_id=op,
        operation_kind='start_session', **_lease(d)) is True
    process = ProcessIdentityObservation(9301, 9301, 'start-9301', 'boot-a2f')
    provider_session = 'SESSION-9301'
    harness.bind_start_result(epoch=epoch, generation=generation, operation_id=op,
        provider_session_id=provider_session, process=process, **_lease(d))
    principal = OperatorPrincipalObservation(
        attempt_id=d.attempt.attempt_id, worker_id=str(d.attempt.worker_id),
        process_generation_id=generation.process_generation_id, provider_session_id=provider_session,
        process_identity={'pid':process.pid,'pgid':process.pgid,'process_start_identity':process.process_start_identity,'boot_id':process.boot_id},
        os_principal_name='fixture-principal-9301', os_principal_uid=9301,
        provider_home_identity={'path':'/tmp/a2f-codex-home-9301','device':9301,'inode':9302,'uid':9301,'gid':9301,'mode':0o700},
        observed_at_ms=runtime.store.now_ms())
    harness.seal_attestation(generation=generation, requested=profile,
        attestation=_orchestration_attestation(profile), principal_observation=principal, **_lease(d))
    return epoch, generation


def test_expired_start_reservation_writes_nothing(tmp_path):
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    clock.advance(seconds=21)
    before = _snapshot(runtime)
    with pytest.raises(StateConflict, match='expired'):
        runtime.operator_harness.reserve_start(d.attempt.attempt_id,
            operation_id=OperationId('ohf-op:expired-start'), **_lease(d))
    assert _snapshot(runtime) == before


def test_reserved_start_dispatch_rechecks_cutoff_and_replay_never_grants(tmp_path):
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    op = OperationId('ohf-op:delayed-start')
    refs = runtime.operator_harness.reserve_start(d.attempt.attempt_id, operation_id=op, **_lease(d))
    clock.advance(seconds=21)
    before = _snapshot(runtime)
    assert runtime.operator_harness.reserve_start(d.attempt.attempt_id, operation_id=op, **_lease(d)) == refs
    with pytest.raises(StateConflict, match='expired'):
        runtime.operator_harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id,
            operation_id=op, operation_kind='start_session', **_lease(d))
    assert _snapshot(runtime) == before


def test_final_slot_original_start_and_first_turn_then_compaction_refused(tmp_path):
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    epoch, generation = _start(runtime, d, profile)
    op = OperationId('ohf-op:first-turn')
    turn = runtime.operator_harness.reserve_turn(epoch=epoch, generation=generation, operation_id=op, **_lease(d))
    assert runtime.operator_harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id,
        operation_id=op, operation_kind='begin_turn', **_lease(d)) is True
    runtime.operator_harness.acknowledge_turn(turn=turn, operation_id=op,
        observation=TurnStartObservation('NATIVE-9301',True), **_lease(d))
    before = _snapshot(runtime)
    with pytest.raises(StateConflict, match='attempt cap'):
        runtime.operator_harness.reserve_checkpoint_operation(generation=generation,
            operation_id=OperationId('ohf-op:cap-compaction'), **_lease(d))
    assert _snapshot(runtime) == before
    assert runtime.jobs.finite_cycle_status(root.job_id)['spent'] == 1


def test_expired_first_turn_is_refused_after_real_start(tmp_path):
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    epoch, generation = _start(runtime, d, profile)
    clock.advance(seconds=21)
    before = _snapshot(runtime)
    with pytest.raises(StateConflict, match='expired'):
        runtime.operator_harness.reserve_turn(epoch=epoch, generation=generation,
            operation_id=OperationId('ohf-op:expired-turn'), **_lease(d))
    assert _snapshot(runtime) == before


def test_expired_current_owner_can_reserve_safety_stop(tmp_path):
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    epoch, generation = _start(runtime, d, profile)
    clock.advance(seconds=21)
    runtime.operator_harness.reserve_generation_operation(generation=generation,
        operation_id=OperationId('ohf-op:safety-stop'), operation_kind='graceful_stop', **_lease(d))
    assert runtime.jobs.finite_cycle_status(root.job_id)['spent'] == 1


@pytest.mark.parametrize('context_kind', ['foreign','admission'])
def test_incumbent_heartbeat_isolates_phase_and_actual_root(tmp_path, context_kind):
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    other = Runtime.at(tmp_path, clock=clock)
    if context_kind == 'foreign':
        # Actual second canonical root has its own owner-issued bound context.
        envelope2, root2 = _finite_root(other, 'CEO-RESERVATION-002')
        other.store.bind_finite_control_context(_issue(_bound_definition(root2,envelope2,runtime=other,
            expires_at_ms=clock.value+20000)))
    else:
        from test_executive_finite_guards import _v2_intent
        other.store.bind_finite_control_context(_issue(_precomputed_admission_definition(_v2_intent())))
    before = _snapshot(runtime)
    with pytest.raises(StateConflict, match='finite'):
        other.attempts.heartbeat_attempt(d.attempt.attempt_id, **_lease(d))
    assert _snapshot(runtime) == before


def test_dispatch_reread_cannot_grant_twice(tmp_path):
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    op = OperationId('ohf-op:one-dispatch')
    runtime.operator_harness.reserve_start(d.attempt.attempt_id, operation_id=op, **_lease(d))
    assert runtime.operator_harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id,
        operation_id=op, operation_kind='start_session', **_lease(d)) is True
    clock.advance(seconds=21)
    assert runtime.operator_harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id,
        operation_id=op, operation_kind='start_session', **_lease(d)) is False


def test_observational_first_issuance_distinguishes_fresh_reserved_and_issued(tmp_path):
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    before = _snapshot(runtime)
    value = runtime.jobs.validate_finite_first_issuance(root.job_id, d.attempt.attempt_id)
    assert value.authorized_first_launch is True and value.already_issued is False
    assert value.halt_reason is None and _snapshot(runtime) == before
    with pytest.raises(AttributeError):
        value.authorized_first_launch = False
    op = OperationId('ohf-op:read-reserved')
    runtime.operator_harness.reserve_start(d.attempt.attempt_id, operation_id=op, **_lease(d))
    reserved = _snapshot(runtime)
    value = runtime.jobs.validate_finite_first_issuance(root.job_id,d.attempt.attempt_id)
    assert value.authorized_first_launch is False and value.already_issued is False
    assert _snapshot(runtime) == reserved
    assert runtime.operator_harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id,
        operation_id=op, operation_kind='start_session', **_lease(d)) is True
    value = runtime.jobs.validate_finite_first_issuance(root.job_id,d.attempt.attempt_id)
    assert value.authorized_first_launch is False and value.already_issued is True


@pytest.mark.parametrize('which', ['reserve','dispatch'])
def test_lock_wait_resamples_finite_deadline(tmp_path, monkeypatch, which):
    import contextlib
    import threading
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    op = OperationId('ohf-op:lock-deadline')
    if which == 'dispatch':
        runtime.operator_harness.reserve_start(d.attempt.attempt_id, operation_id=op, **_lease(d))
    before = _snapshot(runtime)
    attempting = threading.Event()
    original = runtime.store.transaction
    @contextlib.contextmanager
    def signaled():
        attempting.set()
        with original() as connection:
            yield connection
    monkeypatch.setattr(runtime.store,'transaction',signaled)
    outcomes = []
    def execute():
        try:
            if which == 'reserve':
                result = runtime.operator_harness.reserve_start(d.attempt.attempt_id, operation_id=op, **_lease(d))
            else:
                result = runtime.operator_harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id,
                    operation_id=op, operation_kind='start_session', **_lease(d))
            outcomes.append(result)
        except Exception as exc:
            outcomes.append(exc)
    lock = sqlite3.connect(runtime.store.path)
    lock.execute('BEGIN IMMEDIATE')
    thread = threading.Thread(target=execute)
    thread.start()
    assert attempting.wait(5)
    clock.advance(seconds=21)
    lock.rollback(); lock.close(); thread.join(10)
    assert not thread.is_alive()
    assert len(outcomes)==1 and isinstance(outcomes[0],StateConflict)
    assert 'expired' in str(outcomes[0])
    assert _snapshot(runtime)==before


def test_two_connections_dispatch_exact_operation_at_most_once(tmp_path):
    import threading
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    other = Runtime.at(tmp_path,clock=clock)
    other.store.bind_finite_control_context(context)
    op = OperationId('ohf-op:race-dispatch')
    runtime.operator_harness.reserve_start(d.attempt.attempt_id,operation_id=op,**_lease(d))
    barrier = threading.Barrier(3)
    values = []
    def dispatch(owner):
        barrier.wait()
        try:
            values.append(owner.operator_harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id,
                operation_id=op,operation_kind='start_session',**_lease(d)))
        except Exception as exc:
            values.append(exc)
    threads=[threading.Thread(target=dispatch,args=(owner,)) for owner in (runtime,other)]
    for thread in threads:thread.start()
    barrier.wait()
    for thread in threads:thread.join(10)
    assert all(not thread.is_alive() for thread in threads)
    assert values.count(True)==1 and values.count(False)==1
    with runtime.store.read() as c:
        assert c.execute("SELECT COUNT(*) FROM events WHERE event_type='OHF_PROVIDER_DISPATCH_COMMITTED' AND attempt_id=?",(d.attempt.attempt_id,)).fetchone()[0]==1
    assert runtime.jobs.finite_cycle_status(root.job_id)['spent']==1


def test_allowed_start_rolls_back_allocations_on_receipt_failure(tmp_path,monkeypatch):
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    before=_snapshot(runtime)
    real=runtime.operator_harness._receipt
    def fail(*args,**kwargs):
        real(*args,**kwargs)
        raise RuntimeError('injected-after-receipt')
    monkeypatch.setattr(runtime.operator_harness,'_receipt',fail)
    with pytest.raises(RuntimeError,match='injected-after-receipt'):
        runtime.operator_harness.reserve_start(d.attempt.attempt_id,
            operation_id=OperationId('ohf-op:rollback'),**_lease(d))
    assert _snapshot(runtime)==before


def test_omitted_context_cannot_dispatch_reserved_armed_start(tmp_path):
    runtime, clock, root, d, profile, context = _claimed(tmp_path)
    op=OperationId('ohf-op:context-lost')
    runtime.operator_harness.reserve_start(d.attempt.attempt_id,operation_id=op,**_lease(d))
    other=Runtime.at(tmp_path,clock=clock)
    before=_snapshot(runtime)
    with pytest.raises(StateConflict,match='bound context'):
        other.operator_harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id,
            operation_id=op,operation_kind='start_session',**_lease(d))
    assert _snapshot(runtime)==before


def test_second_paid_slot_original_work_start_and_turn(tmp_path):
    from test_executive_finite_guards import _drive_to_admitted
    clock=MutableClock()
    state=_drive_to_admitted(tmp_path,clock,steps=1,cap=2)
    d=state.runtime.attempts.dispatch_cycle_job(state.work(0).job_id,
        command_id=state.dispatch_command(state.work(0).job_id,1),worker_id='worker-a')
    assert isinstance(d,OrchestrationDispatchOutcome)
    profile=_orchestration_profile(d)
    state.runtime.operator_harness.seal_operator_harness_attempt(d.attempt.attempt_id,
        requested=profile,**_lease(d))
    epoch,generation=_start(state.runtime,d,profile)
    op=OperationId('ohf-op:paid-second-turn')
    state.runtime.operator_harness.reserve_turn(epoch=epoch,generation=generation,
        operation_id=op,**_lease(d))
    assert state.runtime.operator_harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id,
        operation_id=op,operation_kind='begin_turn',**_lease(d)) is True
    assert state.runtime.jobs.finite_cycle_status(state.root.job_id)['spent']==2


def test_retained_legacy_process_identity_cannot_regain_first_issuance(tmp_path):
    runtime,clock,root,d,profile,context=_claimed(tmp_path,seal=False)
    # Use the actual legacy process owner before any OHF profile is sealed.
    runtime.attempts.record_process(d.attempt.attempt_id, pid=9501,pgid=9501,
        process_start_identity='prior-process',boot_id='prior-boot',**_lease(d))
    before=_snapshot(runtime)
    decision=runtime.jobs.validate_finite_first_issuance(root.job_id,d.attempt.attempt_id)
    assert decision.authorized_first_launch is False
    assert _snapshot(runtime)==before


def test_reserved_first_turn_dispatch_rechecks_deadline(tmp_path):
    runtime,clock,root,d,profile,context=_claimed(tmp_path)
    epoch,generation=_start(runtime,d,profile)
    op=OperationId('ohf-op:late-first-turn')
    runtime.operator_harness.reserve_turn(epoch=epoch,generation=generation,operation_id=op,**_lease(d))
    clock.advance(seconds=21)
    before=_snapshot(runtime)
    with pytest.raises(StateConflict,match='expired'):
        runtime.operator_harness.commit_provider_dispatch(attempt_id=d.attempt.attempt_id,
            operation_id=op,operation_kind='begin_turn',**_lease(d))
    assert _snapshot(runtime)==before


def test_terminal_and_abandoned_history_never_reauthorizes_original_launch(tmp_path):
    from test_executive_finite_guards import _complete_ohf_role,_plan_steps
    runtime,clock,root,d,profile,context=_claimed(tmp_path)
    plan={'schema_version':'mastermind.execution_plan/v1','root_job_id':root.job_id,
          'plan_attempt_id':d.attempt.attempt_id,'steps':_plan_steps(1)}
    _complete_ohf_role(runtime,d,plan,identity_seed=9502)
    before=_snapshot(runtime)
    value=runtime.jobs.validate_finite_first_issuance(root.job_id,d.attempt.attempt_id)
    assert value.authorized_first_launch is False and value.already_issued is True
    assert _snapshot(runtime)==before
