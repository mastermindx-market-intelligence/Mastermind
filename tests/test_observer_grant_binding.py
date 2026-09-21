import pytest
from control_plane.visible_turn_projection import VisibleTurnProjection, TurnKey, ProjectionError

KEY = TurnKey('attempt','epoch','generation',1,'worker','local','native')
BINDING = dict(operation_id='owner-op', profile_digest='a'*64, permission_digest='b'*64, viewer_binding_digest='c'*64)

def test_enrollment_replay_conflict_and_revoke_never_remints():
    owner = VisibleTurnProjection()
    first = owner.enroll_observer(KEY, **BINDING)
    assert first['status'] == 'ACTIVE'
    assert owner.enroll_observer(KEY, **BINDING) == first
    changed = dict(BINDING, permission_digest='d'*64)
    with pytest.raises(ProjectionError, match='OBSERVER_CONFLICT'):
        owner.enroll_observer(KEY, **changed)
    owner.revoke_observer(KEY, **BINDING)
    assert owner.observer_status(KEY, **BINDING)['status'] == 'REVOKED'
    assert owner.enroll_observer(KEY, **BINDING)['status'] == 'REVOKED'
    assert owner.check_grant(first['reader_grant']) is None

def test_bound_grant_requires_binding_and_generation_invalidation_clears_authority():
    owner = VisibleTurnProjection()
    grant = owner.enroll_observer(KEY, **BINDING)['reader_grant']
    assert owner.check_observer_binding(grant, BINDING)
    assert not owner.check_observer_binding(grant, {})
    owner.invalidate_generation(KEY)
    assert owner.check_grant(grant) is None
    assert owner.observer_status(KEY, **BINDING)['status'] == 'INVALIDATED'

def test_status_has_no_enrollment_effect_and_viewer_budget_applies():
    owner = VisibleTurnProjection()
    assert owner.observer_status(KEY, **BINDING)['status'] == 'ABSENT'
    owner.enroll_observer(KEY, **BINDING)
    owner.enroll_observer(KEY, **dict(BINDING, operation_id='two'))
    with pytest.raises(ProjectionError) as error:
        owner.enroll_observer(KEY, **dict(BINDING, operation_id='three'))
    assert error.value.code == 'OVER_BUDGET'

def test_real_adapter_broker_derives_native_identity_and_bound_read_refuses_legacy_shape():
    import asyncio
    from types import SimpleNamespace
    from control_plane.codex_operator_adapter import CodexOperatorAdapter
    from control_plane.executive_worker_broker import ExecutiveWorkerBroker, BrokerStateError
    from control_plane.operator_harness_contract import TurnRef
    async def run():
        turn = TurnRef('local','epoch','generation','attempt')
        epoch = SimpleNamespace(attempt_id='attempt', session_epoch_id='epoch')
        generation = SimpleNamespace(process_generation_id='generation', generation_number=1, worker_id='worker')
        adapter = CodexOperatorAdapter.__new__(CodexOperatorAdapter)
        adapter._generations = {'generation': SimpleNamespace(epoch=epoch, generation=generation, turns={'local':'native'})}
        broker = ExecutiveWorkerBroker.__new__(ExecutiveWorkerBroker)
        broker._state_lock = asyncio.Lock()
        broker._observer_refusals = []
        broker._operator_run = SimpleNamespace(epoch=epoch, generation=generation, adapter=adapter)
        payload = dict(attempt='attempt',epoch='epoch',generation='generation',turn='local',**BINDING)
        enrolled = await broker._dispatch('ohf-observer-enroll', payload)
        assert enrolled['turn_key']['native_turn_id'] == 'native'
        assert await broker._dispatch('ohf-observer-status', payload) == enrolled
        wire = dict(attempt='attempt',epoch='epoch',generation='generation',turn='local', reader_grant=enrolled['reader_grant'],cursor=None,max_items=64)
        with pytest.raises(BrokerStateError):
            await broker._dispatch('ohf-observe-turn',wire)
        page = await broker._dispatch('ohf-observe-turn',dict(wire,**BINDING))
        assert page['retained_scope'] == ['generation','native']
        await broker._dispatch('ohf-observer-revoke',payload)
        with pytest.raises(BrokerStateError):
            await broker._dispatch('ohf-observe-turn',dict(wire,**BINDING))
    asyncio.run(run())
