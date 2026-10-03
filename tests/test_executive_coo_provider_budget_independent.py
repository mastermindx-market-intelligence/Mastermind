import copy
import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import control_plane.executive_runtime as module
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry, COO_DOMAIN_EXECUTION_PROFILE
from control_plane.ceo_intent import submit_intent
from test_executive_coo_provider_budget import _v2_intent

EVENT = 'COO_PROVIDER_WORK_BUDGET_RESERVED'

def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

def root_only(tmp_path, name='CEO-R9-INDEPENDENT'):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(runtime, _v2_intent(intent_id=name))
    return runtime, runtime.jobs.get_job(receipt['job_id'])

def create(runtime, root):
    return runtime.jobs.create_cycle_domain(root.job_id, command_id=f'coo-cycle:{root.job_id}:create-domain:0')

def complete(tmp_path):
    runtime, root = root_only(tmp_path)
    return runtime, root, create(runtime, root)

def envelope(root_id, domain_id):
    policy = CooCyclePolicy.load()
    registry = ExecutionCapabilityRegistry.load()
    profile = registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    body = {
        'schema_version':'mastermind.executive_coo_provider_work_budget_reservation/v1',
        'root_job_id':root_id, 'domain_job_id':domain_id,
        'policy_schema_version':2, 'policy_sha256':policy.policy_sha256,
        'execution_profile_id':profile.profile_id, 'execution_profile_digest':profile.profile_digest,
        'capability_policy_version':registry.policy_version, 'capability_policy_digest':registry.policy_digest,
        'max_provider_work_units_per_root':32, 'reserved_domain_consumption_units':1,
        'spent_provider_work_units':0, 'available_provider_work_units':31,
        'reservation_status':'reservation_only',
    }
    body['reservation_digest'] = hashlib.sha256(wire(body).encode()).hexdigest()
    return body

def snapshot(runtime):
    # Every persisted row, not merely event count, in this disposable fixture.
    with runtime.store.read() as connection:
        tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {t: sorted([wire(dict(row)) for row in connection.execute('SELECT * FROM "'+t+'"')]) for t in tables}

def budget_row(runtime):
    with runtime.store.read() as connection:
        return dict(connection.execute('SELECT * FROM events WHERE event_type=?',(EVENT,)).fetchone())

def corrupt_fixture_event(runtime, changes):
    # Only an evidence-owned disposable database; restore its trigger verbatim.
    with sqlite3.connect(runtime.store.path) as connection:
        trigger = connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='events_are_immutable_update'").fetchone()[0]
        connection.execute('DROP TRIGGER events_are_immutable_update')
        assignments = ','.join(k+'=?' for k in changes)
        connection.execute('UPDATE events SET '+assignments+' WHERE event_type=?',(*changes.values(),EVENT))
        connection.execute(trigger)

def both_refuse_unchanged(runtime, root):
    before = snapshot(runtime)
    with pytest.raises(StateConflict): runtime.jobs.project_cycle_domain_provider_budget(root.job_id)
    with pytest.raises(StateConflict): create(runtime, root)
    assert snapshot(runtime) == before

def test_complete_expected_payload_and_exact_id_preexisting_refusal(tmp_path):
    valid, r, domain = complete(tmp_path/'valid')
    expected = envelope(r.job_id, domain.job_id)
    assert valid.jobs.project_cycle_domain_provider_budget(r.job_id) == expected
    fresh, root = root_only(tmp_path/'fresh')
    assert root.job_id == 'JOB-001' and domain.job_id == 'JOB-002'
    expected = envelope(root.job_id, 'JOB-002')
    with fresh.store.transaction() as connection:
        fresh.store.append_event(connection, aggregate_type='job', aggregate_id=root.job_id,
            event_type=EVENT, actor='coo', job_id=root.job_id, payload=expected,
            command_id=f'coo-cycle:{root.job_id}:reserve-provider-budget:0')
    assert json.loads(budget_row(fresh)['payload_json']) == expected
    before = snapshot(fresh)
    with pytest.raises(StateConflict, match='already exists for a new domain'): create(fresh, root)
    assert snapshot(fresh) == before
    assert [job.job_id for job in fresh.jobs.list_jobs()] == ['JOB-001']

@pytest.mark.parametrize('redigest',[False,True])
@pytest.mark.parametrize('field,value',[
    ('reserved_domain_consumption_units',True), ('spent_provider_work_units',False),
    ('max_provider_work_units_per_root',32.0), ('available_provider_work_units',31.0),
    ('policy_schema_version',2.0), ('reserved_domain_consumption_units',1.0),
    ('spent_provider_work_units',-0.0), ('spent_provider_work_units','0'),
])
def test_type_substitutions_refuse_even_with_self_consistent_digest(tmp_path, field, value, redigest):
    runtime, root, domain = complete(tmp_path)
    body = json.loads(budget_row(runtime)['payload_json'])
    body[field] = value
    if redigest:
        body.pop('reservation_digest')
        body['reservation_digest'] = hashlib.sha256(wire(body).encode()).hexdigest()
    corrupt_fixture_event(runtime, {'payload_json':wire(body)})
    both_refuse_unchanged(runtime, root)

@pytest.mark.parametrize('field,value',[
    ('actor','foreign'), ('aggregate_type','foreign'), ('aggregate_id','foreign'),
    ('job_id','foreign'), ('command_id','foreign'), ('attempt_id','foreign'),
    ('worker_id','foreign'), ('quota_class','foreign'), ('event_type','FOREIGN_EVENT'),
])
def test_every_budget_event_identity_field_is_checked(tmp_path, field, value):
    runtime, root, domain = complete(tmp_path)
    corrupt_fixture_event(runtime, {field:value})
    both_refuse_unchanged(runtime, root)

def test_two_roots_do_not_share_reservations_or_allow_cross_root_envelope(tmp_path):
    runtime, first, first_domain = complete(tmp_path)
    second = runtime.jobs.get_job(submit_intent(runtime,_v2_intent(intent_id='CEO-R9-SECOND'))['job_id'])
    second_domain = create(runtime,second)
    a=runtime.jobs.project_cycle_domain_provider_budget(first.job_id)
    b=runtime.jobs.project_cycle_domain_provider_budget(second.job_id)
    assert a==envelope(first.job_id,first_domain.job_id)
    assert b==envelope(second.job_id,second_domain.job_id)
    assert a['reservation_digest']!=b['reservation_digest']
    # Change only the first envelope to the second complete valid body.
    with sqlite3.connect(runtime.store.path) as connection:
        trigger=connection.execute("SELECT sql FROM sqlite_master WHERE name='events_are_immutable_update'").fetchone()[0]
        connection.execute('DROP TRIGGER events_are_immutable_update')
        connection.execute('UPDATE events SET payload_json=? WHERE event_type=? AND job_id=?',(wire(b),EVENT,first.job_id))
        connection.execute(trigger)
    both_refuse_unchanged(runtime,first)
    before=snapshot(runtime)
    assert runtime.jobs.project_cycle_domain_provider_budget(second.job_id)==b
    assert create(runtime,second).job_id==second_domain.job_id
    assert snapshot(runtime)==before

@pytest.mark.parametrize('failure',['created_after_append','budget_after_append','validation_after_append'])
def test_transaction_rolls_back_all_tables_after_late_failure(tmp_path, monkeypatch, failure):
    runtime, root = root_only(tmp_path)
    before=snapshot(runtime)
    original=type(runtime.store).append_event
    reached=[]
    def append(self,connection,**kwargs):
        value=original(self,connection,**kwargs)
        if ((failure=='created_after_append' and kwargs.get('event_type')=='JOB_CREATED') or
            (failure=='budget_after_append' and kwargs.get('event_type')==EVENT)):
            reached.append(kwargs['event_type'])
            raise RuntimeError('independent late append failure')
        return value
    monkeypatch.setattr(type(runtime.store),'append_event',append)
    if failure=='validation_after_append':
        def validate(connection,**kwargs):
            assert connection.execute('SELECT COUNT(*) FROM events WHERE event_type=?',(EVENT,)).fetchone()[0]==1
            reached.append('post_append_validation')
            raise RuntimeError('independent late validation failure')
        monkeypatch.setattr(module,'_validated_coo_provider_budget_event',validate)
    with pytest.raises(RuntimeError,match='independent late'): create(runtime,root)
    assert reached and snapshot(runtime)==before

def test_concurrent_same_command_has_one_domain_and_one_budget(tmp_path, monkeypatch):
    runtime, root=root_only(tmp_path)
    barrier=threading.Barrier(2)
    original=type(runtime.jobs).create_job
    def together(self,*args,**kwargs):
        barrier.wait(timeout=5)
        return original(self,*args,**kwargs)
    monkeypatch.setattr(type(runtime.jobs),'create_job',together)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:create(runtime,root),range(2)))
    assert results[0].job_id==results[1].job_id=='JOB-002'
    with runtime.store.read() as connection:
        assert connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==2
        assert connection.execute('SELECT COUNT(*) FROM events WHERE event_type=?',(EVENT,)).fetchone()[0]==1

def test_ordinary_planner_and_flat_job_stay_budget_free_and_seal_refuses(tmp_path):
    runtime, root=root_only(tmp_path)
    planner=runtime.jobs.create_cycle_planner(root.job_id,command_id=f'coo-cycle:{root.job_id}:create-planner:0')
    again=runtime.jobs.create_cycle_planner(root.job_id,command_id=f'coo-cycle:{root.job_id}:create-planner:0')
    assert planner.job_id==again.job_id
    flat=runtime.jobs.create_job('unchanged flat workflow',command_id='independent-flat')
    assert flat.orchestration_role is None
    with runtime.store.read() as connection:
        assert connection.execute('SELECT COUNT(*) FROM events WHERE event_type=?',(EVENT,)).fetchone()[0]==0
    before=snapshot(runtime)
    with pytest.raises(StateConflict): runtime.jobs.project_cycle_domain_provider_budget(root.job_id)
    with pytest.raises(StateConflict): runtime.jobs.seal_cycle_domain_consumption(root.job_id,domain_attempt_id='ATT-fake',observation={},command_id='independent-seal')
    assert snapshot(runtime)==before
