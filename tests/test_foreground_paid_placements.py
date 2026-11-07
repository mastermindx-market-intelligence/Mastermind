"""Foreground continuation requires actual source DATA and Runtime enrollment.

The root custody read is a temporary-file fixture (no installed root is read).
Pinned bytes and file identity, PaidBindingSource normalization, current
catalogue, Runtime rows, and foreground plan completion are real. No provider
or capacity bootstrap is called, and these tests make no live admission claim.
"""
import asyncio
import copy
import dataclasses
import hashlib
import json

import pytest

from control_plane import executive_paid_fabric_composition as composition
from control_plane.executive_capacity_join import CapacityJoin, PROVIDER_CAPACITY_SCHEMA
from control_plane.executive_runtime import Runtime, StateConflict, WorkerStatus
from control_plane.model_router import ModelRouter
from control_plane.paid_fabric_admission import require_registered_paid_placements
from control_plane.paid_model_execution_contract import canonical, digest
from tests.test_paid_fabric_owner_wiring import material


def paid_fixture(tmp_path, monkeypatch, *, runtime=None):
    runtime = runtime or Runtime.at(tmp_path / "runtime")
    router = ModelRouter.load()
    placement = composition.PaidWorkPlacement('glm.paid.sealed-input', 'paid-read')
    member = composition.placement_member(router, placement)
    route = member['paid_execution_route']
    payload, *_ = material()
    source = copy.deepcopy(payload['paid_source_config'])
    source['execution_profile_digest'] = route['execution_profile_digest']
    physical = copy.deepcopy(payload['paid_physical_binding'])
    physical['execution_profile_digest'] = source['execution_profile_digest']
    physical['worker_source_config_digest'] = digest(source)
    document = {'schema_version': composition.PAID_BINDINGS_SCHEMA,
        'bindings': [{'physical_binding': physical, 'source_config': source, 'quota_class': 'paid-read'}]}
    path = tmp_path / 'bindings.json'
    path.write_bytes(canonical(document))
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    def read_fixture(selected, expected_sha):
        data = selected.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha:
            raise composition.FabricCompositionError('fixture pinned source changed')
        from control_plane.executive_fabric_composition import _identity
        return data, _identity(selected.stat())
    monkeypatch.setattr(composition, '_read_pinned', read_fixture)
    acquired = composition.PaidBindingSource.from_path(path, expected)
    metadata = dict(route, paid_execution_route=route,
        capacity_join=CapacityJoin(physical['host_ref'], source['capacity_capability_id'],
            PROVIDER_CAPACITY_SCHEMA, physical['worker_source_config_digest']).to_dict())
    runtime.workers.register_worker(physical['worker_id'], provider='glm', account_label='glm-account-1',
        worker_type='canonical-paid-fabric', capabilities=['read', 'research'],
        status=WorkerStatus.AVAILABLE,
        metadata=dict(service_managed=True, worker_source_config_digest=physical['worker_source_config_digest']),
        quota_classes={'paid-read': dict(provider='glm', model=route['model'], effort=route['effort'],
            cost_class=route['cost_class'], capabilities=['read', 'research'], metadata=metadata)})
    monkeypatch.setattr(composition.PaidBindingSource, 'client_for',
        lambda *_: pytest.fail('foreground registration check performed provider IO'))
    binding = {'work_placement_union': [member]}
    return runtime, acquired, (placement,), binding, path


def test_current_source_and_enrollment_are_read_without_bootstrap(tmp_path, monkeypatch):
    runtime, source, placements, binding, _ = paid_fixture(tmp_path, monkeypatch)
    before = [event.to_dict() for event in runtime.events.list_events()]
    require_registered_paid_placements(runtime, source, placements, binding)
    assert [event.to_dict() for event in runtime.events.list_events()] == before
    assert runtime.jobs.list_jobs() == [] and runtime.attempts.list_attempts() == []


@pytest.mark.parametrize('fault', [
    'missing_source', 'unacquired_source', 'source_bytes', 'source_inode',
    'cached_projection', 'empty_placements', 'different_quota', 'frozen_union',
    'worker_missing', 'worker_identity', 'quota_route',
])
def test_no_continuation_from_unqualified_or_changed_paid_binding(tmp_path, monkeypatch, fault):
    runtime, source, placements, binding, path = paid_fixture(tmp_path, monkeypatch)
    worker = source.bindings[0].worker_id
    if fault == 'missing_source': source = None
    elif fault == 'unacquired_source': source = dataclasses.replace(source, _origin=None)
    elif fault == 'source_bytes': path.write_bytes(path.read_bytes() + b'\n')
    elif fault == 'source_inode':
        replacement = path.with_suffix('.replacement')
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
    elif fault == 'cached_projection': source.bindings[0].binary['sha256'] = '0' * 64
    elif fault == 'empty_placements': placements = ()
    elif fault == 'different_quota': placements = (composition.PaidWorkPlacement('glm.paid.sealed-input', 'other'),)
    elif fault == 'frozen_union': binding = {'work_placement_union': []}
    else:
        # Deliberate temporary Runtime corruption proves stale physical/route
        # rows cannot substitute for the enrollment owner. Never host SQL.
        with runtime.store.transaction() as connection:
            if fault == 'worker_missing': connection.execute('DELETE FROM worker_quota_classes WHERE worker_id=?', (worker,))
            elif fault == 'worker_identity': connection.execute("UPDATE workers SET worker_type='manual' WHERE worker_id=?", (worker,))
            else: connection.execute("UPDATE worker_quota_classes SET model='other' WHERE worker_id=?", (worker,))
    with pytest.raises((StateConflict, composition.FabricCompositionError)):
        require_registered_paid_placements(runtime, source, placements, binding)
    assert runtime.jobs.list_jobs() == [] and runtime.attempts.list_attempts() == []


@pytest.mark.parametrize('status', [WorkerStatus.OFFLINE, WorkerStatus.DRAINING, WorkerStatus.RATE_LIMITED])
def test_registered_identity_does_not_override_capacity_owner(tmp_path, monkeypatch, status):
    runtime, source, placements, binding, _ = paid_fixture(tmp_path, monkeypatch)
    worker = source.bindings[0].worker_id
    runtime.workers.set_worker_status(worker, status, quota_class='paid-read')
    before = runtime.workers.get_quota_class(worker, 'paid-read')
    require_registered_paid_placements(runtime, source, placements, binding)
    assert runtime.workers.get_quota_class(worker, 'paid-read') == before
    assert before.status is status and runtime.attempts.list_attempts() == []


def test_shared_placement_keeps_each_worker_identity_without_requiring_all_available(tmp_path, monkeypatch):
    runtime, source, placements, binding, path = paid_fixture(tmp_path, monkeypatch)
    document = json.loads(path.read_bytes())
    row = copy.deepcopy(document['bindings'][0])
    current, physical = row['source_config'], row['physical_binding']
    current['worker_id'] = physical['worker_id'] = 'paid-other-worker'
    current['qualification']['boot_id'] = physical['qualification']['boot_id'] = 'other-qualified-boot'
    physical['worker_source_config_digest'] = digest(current)
    document['bindings'].append(row)
    path.write_bytes(canonical(document))
    source = composition.PaidBindingSource.from_path(path, hashlib.sha256(path.read_bytes()).hexdigest())
    route = binding['work_placement_union'][0]['paid_execution_route']
    runtime.workers.register_worker(physical['worker_id'], provider='glm', account_label='glm-account-2',
        worker_type='canonical-paid-fabric', capabilities=['read', 'research'],
        metadata=dict(service_managed=True, worker_source_config_digest=digest(current)),
        quota_classes={'paid-read': dict(provider='glm', model=route['model'], effort=route['effort'],
            cost_class=route['cost_class'], capabilities=['read', 'research'], metadata=dict(route,
                paid_execution_route=route, capacity_join=CapacityJoin(physical['host_ref'],
                    current['capacity_capability_id'], PROVIDER_CAPACITY_SCHEMA, digest(current)).to_dict()))})
    runtime.workers.set_worker_status(source.bindings[0].worker_id, WorkerStatus.OFFLINE, quota_class='paid-read')
    before = [event.to_dict() for event in runtime.events.list_events()]
    require_registered_paid_placements(runtime, source, placements, binding)
    assert runtime.workers.get_quota_class('paid-other-worker', 'paid-read').status is WorkerStatus.AVAILABLE
    assert [event.to_dict() for event in runtime.events.list_events()] == before


def test_original_paid_claim_remains_owned_during_registration_recheck(tmp_path, monkeypatch):
    from tests.test_paid_runtime_owner_integration import paid_cycle_claim
    from control_plane.executive_runtime import WorkerRegistry
    original = WorkerRegistry.register_worker
    def qualified_registration(self, worker_id, **kwargs):
        if kwargs['provider'] == 'glm':
            for quota in kwargs['quota_classes'].values():
                route = quota['metadata']['paid_execution_route']
                join = quota['metadata']['capacity_join']
                kwargs['metadata'] = dict(service_managed=True,
                    worker_source_config_digest=join['worker_source_config_digest'])
                quota['metadata'] = dict(route, paid_execution_route=route, capacity_join=join)
        return original(self, worker_id, **kwargs)
    monkeypatch.setattr(WorkerRegistry, 'register_worker', qualified_registration)
    runtime, root, job, claimed, current, *_ = paid_cycle_claim(tmp_path)
    physical = {**current, 'schema_version': 'mastermind.paid_fabric_host_binding/v1',
                'worker_source_config_digest': digest(current)}
    physical.pop('capacity_capability_id')
    path = tmp_path / 'held-bindings.json'
    path.write_bytes(canonical({'schema_version': composition.PAID_BINDINGS_SCHEMA,
        'bindings': [{'physical_binding': physical, 'source_config': current, 'quota_class': 'paid-read'}]}))
    from control_plane.executive_fabric_composition import _identity
    def root_read_fixture(selected, expected):
        data = selected.read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected
        return data, _identity(selected.stat())
    monkeypatch.setattr(composition, '_read_pinned', root_read_fixture)
    source = composition.PaidBindingSource.from_path(path, hashlib.sha256(path.read_bytes()).hexdigest())
    before = runtime.workers.get_quota_class('paid-subject', 'paid-read')
    assert before.status is WorkerStatus.BUSY and before.active_attempt_id == claimed.attempt.attempt_id
    require_registered_paid_placements(runtime, source,
        (composition.PaidWorkPlacement('glm.paid.sealed-input', 'paid-read'),), root.constraints)
    assert runtime.workers.get_quota_class('paid-subject', 'paid-read') == before
    assert runtime.jobs.get_job(job.job_id).current_attempt_id == claimed.attempt.attempt_id


def test_registered_paid_foreground_continues_after_exact_plan_completion(tmp_path, monkeypatch):
    from control_plane import foreground_operation as scope
    from control_plane.executive_coo_cycle import CooCycle, CooCycleOutcome
    from control_plane.executive_service import _ForegroundExecution
    from tests.test_foreground_operator_completion import service_at
    from tests.test_foreground_operation import frame, admit
    from tests import test_executive_os_phase1fc as roles
    async def run():
        service = service_at(tmp_path)
        runtime, source, placements, binding, _ = paid_fixture(tmp_path, monkeypatch, runtime=service.runtime)
        service.config = dataclasses.replace(service.config, coo_paid_work_placements=placements)
        service._paid_worker_binding_source = source
        monkeypatch.setattr(service, '_foreground_execution_state', lambda **kw: _ForegroundExecution('PAID_WORK', b'{}'))
        binding.update(operator_execution_profile_id='ordinary', operator_harness_armed=True)
        monkeypatch.setattr(service, '_coo_binding_for_root', lambda _: binding)
        f = frame('paid-plan-continuation')
        async with scope._session_bridge_foreground_dispatch(runtime, f, lambda: None) as operation:
            async with service._foreground_cycle_scope(operation):
                receipt = await admit(runtime, tmp_path, operation, f)
                root = receipt['job_id']
                async def finish(dispatched):
                    await asyncio.sleep(0)
                    plan = {'schema_version': 'mastermind.execution_plan/v1', 'root_job_id': root,
                        'plan_attempt_id': dispatched.attempt.attempt_id, 'steps': [{
                        'ordinal': 0, 'step_id': 'one', 'objective': 'Read one fact',
                        'business_impact': 'routine', 'review_required': False, 'requested_authorities': ['READ'],
                        'allowed_write_paths': [], 'validation_ids': [], 'attempt_limit': 1, 'cost_class': 'small'}]}
                    roles._complete_ohf_role(runtime, dispatched, plan, identity_seed=8400)
                    service._dispatch_tasks.pop(dispatched.job_id)
                def dispatch(job_id, command):
                    value = runtime.attempts.dispatch_cycle_job(job_id, command_id=command, worker_id='worker-a')
                    service._dispatch_tasks[job_id] = asyncio.create_task(finish(value))
                    return value
                cycle, actions = CooCycle(runtime, dispatcher=dispatch), []
                async def once(root_id):
                    if actions and actions[-1] == 'DISPATCHED':
                        return CooCycleOutcome(root_id, 'NO_NEW_WORK', None, None, {})
                    outcome = cycle.run_once(root_id)
                    actions.append(outcome.action)
                    return outcome
                monkeypatch.setattr(service, '_run_coo_cycle', once)
                result = await service._drive_foreground_cycle(operation, root)
                assert result['state'] == 'NO_NEW_WORK'  # not the old plan-only stop
                assert actions == ['PLANNER_CREATED', 'DISPATCHED']
                planner = next(job for job in runtime.jobs.list_jobs() if job.parent_job_id == root)
                runtime.validated_role_completion(planner.job_id, expected_attempt_id=planner.current_attempt_id)
                assert len(runtime.attempts.list_attempts()) == 1
    asyncio.run(run())
