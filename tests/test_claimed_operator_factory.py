"""Claim-selected operator construction through real disposable Runtime owners."""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError,
)
from control_plane.executive_runtime import AttemptStatus, WorkerStatus
from control_plane.executive_supervisor import ReconcileStatus
from test_executive_operator_supervisor import (
    _ActiveAdapter, _PromptSource, _RecoveryAdapter,
    _seed_dispatchable_operator_planner, _seed_expired_g1,
)


def test_claimed_factory_receives_actual_selected_worker_before_execution(tmp_path):
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path)
    original = runtime.workers.get_worker('worker-a')
    quota = runtime.workers.get_quota_class('worker-a', 'codex-coo-operator')
    descriptor = {key: getattr(quota, key) for key in (
        'provider', 'model', 'effort', 'cost_class', 'capabilities', 'metadata')}
    runtime.workers.register_worker('worker-b', provider=original.provider,
        account_label='independent-fixture-b', worker_type=original.worker_type,
        capabilities=original.capabilities, quota_classes={'codex-coo-operator': descriptor})
    runtime.workers.set_worker_status('worker-a', WorkerStatus.OFFLINE)
    calls = []
    def factory(attempt, requested, loader, *, recovery):
        assert attempt == runtime.attempts.get_attempt(attempt.attempt_id)
        assert requested.worker_id == attempt.worker_id == 'worker-b'
        assert attempt.status is AttemptStatus.CLAIMED and recovery is False
        assert not hasattr(attempt, 'lease_token')
        adapter = _ActiveAdapter(runtime, loader, cancel_during_collect=False)
        calls.append((attempt, adapter))
        return adapter
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=factory, prompt_source=_PromptSource())
    outcome = asyncio.run(supervisor.start_cycle_job(planner.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1'))
    assert outcome.attempt.status is AttemptStatus.COMPLETED
    assert outcome.attempt.worker_id == 'worker-b'
    assert len(calls) == 1 and calls[0][1].begin_turn_calls == 1
    assert calls[0][1].stop_calls == 1


@pytest.mark.parametrize('with_turn', [False, True])
def test_recovery_factory_receives_original_worker_and_sealed_profile(tmp_path, with_turn):
    clock, runtime, root, planner, dispatch, profile, epoch = _seed_expired_g1(
        tmp_path, observed_dead=False, with_turn=with_turn)
    calls = []
    def factory(attempt, requested, loader, *, recovery):
        assert attempt.attempt_id == dispatch.attempt.attempt_id
        assert requested == profile and requested.worker_id == attempt.worker_id
        assert recovery is True
        adapter = _RecoveryAdapter(runtime, profile, loader, live_existing=True)
        calls.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=factory, prompt_source=_PromptSource())
    assert supervisor.reconcile_restart()[0].status is ReconcileStatus.AWAITING_LEASE_EXPIRY
    assert not calls
    clock.advance(3)
    result = supervisor.reconcile_restart()
    assert result[0].status is ReconcileStatus.OPERATOR_RECOVERED
    assert len(calls) == 1 and calls[0].resume_calls == 0
    assert runtime.attempts.get_attempt(dispatch.attempt.attempt_id).status is AttemptStatus.COMPLETED


@pytest.mark.parametrize('mutation', ['cancel', 'exception'])
def test_construction_refusal_never_falls_back_or_starts_provider(tmp_path, mutation):
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path)
    calls = []
    def factory(attempt, requested, loader, *, recovery):
        calls.append(attempt.attempt_id)
        if mutation == 'exception':
            raise RuntimeError('private endpoint diagnostic')
        runtime.jobs.cancel_job(attempt.job_id)
        return _ActiveAdapter(runtime, loader, cancel_during_collect=False)
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=factory, prompt_source=_PromptSource())
    with pytest.raises(ExecutiveOperatorSupervisorError):
        asyncio.run(supervisor.start_cycle_job(planner.job_id,
            command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1'))
    assert len(calls) == 1
    with runtime.store.read() as connection:
        assert connection.execute('SELECT COUNT(*) FROM harness_session_epochs').fetchone()[0] == 0


@pytest.mark.parametrize('kwargs', [
    {}, {'adapter_factory': 1}, {'claimed_adapter_factory': 1},
    {'adapter_factory': lambda _: None, 'claimed_adapter_factory': lambda *a, **k: None},
])
def test_exactly_one_callable_factory_is_required_before_runtime_access(kwargs):
    with pytest.raises(ExecutiveOperatorSupervisorError, match='exactly one'):
        ExecutiveOperatorSupervisor(object(), prompt_source=_PromptSource(), **kwargs)


def claimed(tmp_path):
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path)
    result = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1',
        lease_owner='fixture-claimed')
    from control_plane.executive_runtime import AttemptLease
    lease = AttemptLease(result.attempt, result.lease_token)
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=lambda *a, **k: None, prompt_source=_PromptSource())
    return runtime, supervisor, lease, supervisor._requested_profile(planner, lease)


@pytest.mark.parametrize('field,value', [
    ('worker_id', 'foreign'), ('job_id', 'JOB-999'), ('quota_class', 'foreign'),
    ('fence_generation', 999), ('lease_owner', 'foreign'),
    ('authority_policy_hash', 'f' * 64),
])
def test_stale_claim_refuses_before_factory(tmp_path, field, value):
    runtime, supervisor, lease, requested = claimed(tmp_path)
    supervisor._claimed_adapter_factory = lambda *a, **k: pytest.fail('stale claim reached factory')
    bad = dataclasses.replace(lease, attempt=dataclasses.replace(lease.attempt, **{field: value}))
    with pytest.raises(ExecutiveOperatorSupervisorError, match='no longer current'):
        supervisor._adapter_for_attempt(bad, requested, lambda turn: '', recovery=False)


@pytest.mark.parametrize('field,value', [('worker_id', 'foreign'), ('authority_policy_hash', 'f' * 64)])
def test_foreign_requested_profile_refuses_before_factory(tmp_path, field, value):
    _, supervisor, lease, requested = claimed(tmp_path)
    supervisor._claimed_adapter_factory = lambda *a, **k: pytest.fail('foreign profile reached factory')
    with pytest.raises(ExecutiveOperatorSupervisorError, match='no longer current'):
        supervisor._adapter_for_attempt(lease, dataclasses.replace(requested, **{field: value}),
            lambda turn: '', recovery=False)


@pytest.mark.parametrize('field,value', [
    ('status', AttemptStatus.CANCEL_REQUESTED), ('fence_generation', 999),
    ('requested_execution_profile_digest', 'f' * 64),
    ('placement_snapshot_digest', 'e' * 64),
    ('execution_principal_snapshot_digest', 'd' * 64),
])
def test_changed_binding_after_construction_refuses(tmp_path, monkeypatch, field, value):
    runtime, supervisor, lease, requested = claimed(tmp_path)
    get_attempt = runtime.attempts.get_attempt
    calls = []
    def factory(attempt, profile, loader, *, recovery):
        calls.append(attempt.attempt_id)
        monkeypatch.setattr(runtime.attempts, 'get_attempt',
            lambda key: dataclasses.replace(get_attempt(key), **{field: value}))
        return object()
    supervisor._claimed_adapter_factory = factory
    with pytest.raises(ExecutiveOperatorSupervisorError):
        supervisor._adapter_for_attempt(lease, requested, lambda turn: '', recovery=False)
    assert len(calls) == 1


def test_callback_cannot_mutate_canonical_snapshot_or_profile(tmp_path):
    runtime, supervisor, lease, requested = claimed(tmp_path)
    before = dataclasses.asdict(lease.attempt)
    marker = object()
    def factory(attempt, profile, loader, *, recovery):
        attempt.launch_metadata['not-authoritative'] = True
        object.__setattr__(profile, 'worker_id', 'foreign-copy')
        return marker
    supervisor._claimed_adapter_factory = factory
    assert supervisor._adapter_for_attempt(lease, requested, lambda turn: '', recovery=False) is marker
    assert dataclasses.asdict(lease.attempt) == before
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).launch_metadata == before['launch_metadata']
    assert requested.worker_id == lease.attempt.worker_id


def test_factory_error_does_not_leak_endpoint_diagnostics(tmp_path):
    _, supervisor, lease, requested = claimed(tmp_path)
    def factory(*args, **kwargs):
        raise OSError('/private/credential-route detail')
    supervisor._claimed_adapter_factory = factory
    with pytest.raises(ExecutiveOperatorSupervisorError) as failure:
        supervisor._adapter_for_attempt(lease, requested, lambda turn: '', recovery=False)
    assert str(failure.value) == 'claimed operator construction refused'
    assert failure.value.__suppress_context__ is True


@pytest.mark.parametrize('with_turn', [False, True])
def test_recovery_cancellation_keeps_original_binding_without_fresh_profile_lookup(tmp_path, monkeypatch, with_turn):
    clock, runtime, root, planner, dispatch, profile, epoch = _seed_expired_g1(
        tmp_path, observed_dead=False, with_turn=with_turn)
    runtime.jobs.cancel_job(planner.job_id)
    calls = []
    def factory(attempt, requested, loader, *, recovery):
        assert recovery and attempt.status is AttemptStatus.CANCEL_REQUESTED
        assert requested == profile
        adapter = _RecoveryAdapter(runtime, profile, loader, live_existing=True)
        calls.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=factory, prompt_source=_PromptSource())
    monkeypatch.setattr(supervisor, '_requested_profile',
        lambda *a: pytest.fail('containment required a fresh profile'))
    clock.advance(3)
    supervisor.reconcile_restart()
    assert runtime.attempts.get_attempt(dispatch.attempt.attempt_id).status is AttemptStatus.CANCELLED
    assert len(calls) == 1 and calls[0].resume_calls == 0
    assert calls[0].cancel_calls == 1


def test_nonbinding_heartbeat_metadata_is_not_false_claim_drift(tmp_path, monkeypatch):
    runtime, supervisor, lease, requested = claimed(tmp_path)
    get_attempt = runtime.attempts.get_attempt
    marker = object()
    def factory(attempt, profile, loader, *, recovery):
        monkeypatch.setattr(runtime.attempts, 'get_attempt', lambda key:
            dataclasses.replace(get_attempt(key), version=attempt.version + 1))
        return marker
    supervisor._claimed_adapter_factory = factory
    assert supervisor._adapter_for_attempt(lease, requested, lambda turn: '', recovery=False) is marker
