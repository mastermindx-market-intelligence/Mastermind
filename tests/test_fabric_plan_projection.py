"""Pure plan-view contract over real Runtime types, with synthetic owner material."""
from __future__ import annotations

import copy
from dataclasses import asdict, replace
import json
from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import (
    BoundedAdmittedPlanSnapshot, BoundedRoleResultRootMetadata,
    RuntimeReadObservationReceipt,
)
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.fabric_plan_projection import FabricPlanProjectionError, project_admitted_plan


def _material(version=3, count=2):
    steps = []
    reserved = []
    for ordinal in range(count):
        deps = [f'step-{ordinal-1}'] if ordinal and version >= 3 else []
        step = {'ordinal': ordinal, 'step_id': f'step-{ordinal}',
                'objective': f'Read source evidence for item {ordinal}.',
                'business_impact': 'routine', 'review_required': False,
                'requested_authorities': ['READ'], 'allowed_write_paths': [],
                'validation_ids': [], 'attempt_limit': 1, 'cost_class': 'small'}
        if version >= 2:
            step['placement'] = {'provider_realm': 'codex', 'quota_class': 'private-quota'}
        if version >= 3:
            step['prerequisite_step_ids'] = deps
        steps.append(step)
        row = {'ordinal': ordinal, 'plan_step_id': step['step_id'], 'step_slots': 3,
               'review_required': True}
        if version >= 3:
            row.update(prerequisite_step_ids=deps,
                       initial_work_job_id=None if deps else 'JOB-003',
                       initial_work_command_id=None if deps else 'private-member-command')
        else:
            row.update(work_job_id='JOB-003', member_command_id='private-member-command')
        reserved.append(row)
    plan = {'schema_version': f'mastermind.execution_plan/v{version}',
            'root_job_id': 'JOB-001', 'plan_attempt_id': 'ATT-001', 'steps': steps}
    admission = {'schema_version': f'mastermind.coo_plan_admission/v{2 if version >= 3 else 1}',
                 'root_job_id': 'JOB-001', 'policy_sha': 'b' * 64,
                 'plan_attempt_id': 'ATT-001', 'plan_digest': canonical_digest(plan),
                 'steps': reserved, 'reserved_children_total': 3 * count,
                 'command_id': 'coo-cycle:JOB-001:admit-plan:ATT-001'}
    admission['reservation_digest'] = canonical_digest(admission)
    metadata = BoundedRoleResultRootMetadata('JOB-001', 'JOB-001', 'aggregation',
                 'ceo-intent:CEO-PLAN-FIXTURE', 'WS:PLAN-FIXTURE', 'c' * 64, 'd' * 64)
    snapshot = BoundedAdmittedPlanSnapshot('JOB-001', metadata, admission, plan, 'e' * 32)
    receipt = RuntimeReadObservationReceipt('mastermind.runtime_read_observation.v1',
                                          'SAME', 'e' * 32, 3, 3)
    return snapshot, receipt


def _refused(snapshot, receipt, code='SOURCE_UNAVAILABLE'):
    with pytest.raises(FabricPlanProjectionError) as error:
        project_admitted_plan(snapshot, receipt)
    assert error.value.code == code
    return error.value


@pytest.mark.parametrize('version', [1, 2, 3, 4])
def test_closed_plan_view_schema_order_effective_review_and_no_private_fields(version):
    snapshot, receipt = _material(version)
    original = copy.deepcopy((snapshot, receipt))
    view = project_admitted_plan(snapshot, receipt)
    assert set(view) == {'schema', 'plan_schema_version', 'admission_schema_version',
                         'root_job_id', 'plan_attempt_id', 'policy_sha', 'plan_digest',
                         'reservation_digest', 'admission_state', 'steps'}
    assert view['schema'] == 'mastermind.admitted_execution_plan_view.v1'
    assert view['admission_state'] == 'ADMITTED'
    assert view['plan_schema_version'] == snapshot.plan['schema_version']
    assert view['admission_schema_version'] == snapshot.admission['schema_version']
    assert view['plan_digest'] == snapshot.admission['plan_digest']
    assert view['reservation_digest'] == snapshot.admission['reservation_digest']
    for i, row in enumerate(view['steps']):
        assert set(row) == {'ordinal', 'step_id', 'objective', 'business_impact',
                            'review_required', 'prerequisite_step_ids'}
        assert row['ordinal'] == i and row['step_id'] == f'step-{i}'
        assert row['objective'] == snapshot.plan['steps'][i]['objective']
        assert row['review_required'] is True  # reservation strengthens false
        assert row['prerequisite_step_ids'] == ([f'step-{i-1}'] if i and version >= 3 else [])
    encoded = json.dumps(view)
    for private in ('private-quota', 'private-member-command', 'allowed_write_paths',
                    'requested_authorities', 'placement', 'source_digest', 'command_id'):
        assert private not in encoded
    assert (snapshot, receipt) == original
    view['steps'][0]['objective'] = 'consumer mutation'
    view['steps'][1]['prerequisite_step_ids'].append('alien')
    assert (snapshot, receipt) == original


@pytest.mark.parametrize('which', ['mapping_snapshot', 'shadow_snapshot', 'mapping_receipt', 'shadow_receipt', 'metadata'])
def test_foreign_types_refused(which):
    snapshot, receipt = _material()
    if which == 'mapping_snapshot': snapshot = asdict(snapshot)
    if which == 'shadow_snapshot': snapshot = SimpleNamespace(**asdict(snapshot))
    if which == 'mapping_receipt': receipt = asdict(receipt)
    if which == 'shadow_receipt': receipt = SimpleNamespace(**asdict(receipt))
    if which == 'metadata': snapshot = replace(snapshot, root_metadata=asdict(snapshot.root_metadata))
    _refused(snapshot, receipt)


@pytest.mark.parametrize('field,value,code', [
    ('state', 'CONFLICT', 'SOURCE_CHANGED'), ('state', 'UNKNOWN', 'SOURCE_UNAVAILABLE'),
    ('state', 'same', 'SOURCE_UNAVAILABLE'), ('schema', 'foreign', 'SOURCE_UNAVAILABLE'),
    ('source_identity', None, 'SOURCE_UNAVAILABLE'), ('source_identity', 'F' * 32, 'SOURCE_UNAVAILABLE'),
    ('source_identity', 'f' * 32, 'SOURCE_UNAVAILABLE'), ('source_identity', 'e' * 31, 'SOURCE_UNAVAILABLE'),
    ('before', True, 'SOURCE_UNAVAILABLE'), ('after', False, 'SOURCE_UNAVAILABLE'),
    ('before', -1, 'SOURCE_UNAVAILABLE'), ('before', 3.0, 'SOURCE_UNAVAILABLE'),
    ('after', 4, 'SOURCE_UNAVAILABLE'), ('before', None, 'SOURCE_UNAVAILABLE')])
def test_receipt_requires_exact_same_identity_and_nonbool_samples(field, value, code):
    snapshot, receipt = _material()
    _refused(snapshot, replace(receipt, **{field: value}), code)


@pytest.mark.parametrize('field,value', [('root_job_id','JOB-OTHER'), ('observation_source_identity',None),
                                         ('observation_source_identity','f'*32)])
def test_snapshot_identity_drift_refused(field, value):
    snapshot, receipt = _material()
    _refused(replace(snapshot, **{field: value}), receipt)


@pytest.mark.parametrize('objective,code', [
    ('agent_os_detail_redacted','CONTENT_WITHHELD'), ('','CONTENT_WITHHELD'),
    ('Bearer fixture-token','CONTENT_WITHHELD'), ('read /Users/fixture/private-note','CONTENT_WITHHELD'),
    ('secret\x00value','CONTENT_WITHHELD'), ('x'*4097,'CONTENT_OVER_BUDGET'),
    ('研究'*2049,'CONTENT_OVER_BUDGET')])
def test_unsafe_or_oversized_objective_withholds_whole_plan(objective, code):
    snapshot, receipt = _material()
    snapshot.plan['steps'][1]['objective'] = objective
    error = _refused(snapshot, receipt, code)
    assert objective not in str(error) if objective else True
    assert not hasattr(error, 'plan')


def test_text_owner_alteration_refuses_without_synthesized_objective(monkeypatch):
    import control_plane.fabric_plan_projection as projection
    monkeypatch.setattr(projection, '_safe_text', lambda value: 'replacement')
    snapshot, receipt = _material()
    _refused(snapshot, receipt, 'CONTENT_WITHHELD')


def test_text_boundary_uses_characters_and_accepts_unchanged_unicode():
    snapshot, receipt = _material(count=1)
    snapshot.plan['steps'][0]['objective'] = '研' * 4096
    view = project_admitted_plan(snapshot, receipt)
    assert view['steps'][0]['objective'] == '研' * 4096


@pytest.mark.parametrize('mutation', ['empty','nine','reversed','duplicate_id','bool_ordinal','bad_impact',
                                     'review_not_bool','reserved_id','reserved_ordinal','review_downgrade',
                                     'forward_dep','unknown_dep','duplicate_dep','dependency_drift'])
def test_step_shape_order_and_reservation_join_refused(mutation):
    snapshot, receipt = _material()
    a, p = snapshot.admission['steps'], snapshot.plan['steps']
    if mutation=='empty': a.clear(); p.clear()
    elif mutation=='nine':
        snapshot, receipt = _material(count=9)
    elif mutation=='reversed': p.reverse()
    elif mutation=='duplicate_id': p[1]['step_id']=p[0]['step_id']
    elif mutation=='bool_ordinal': p[0]['ordinal']=False
    elif mutation=='bad_impact': p[0]['business_impact']='private-impact'
    elif mutation=='review_not_bool': a[0]['review_required']=1
    elif mutation=='reserved_id': a[0]['plan_step_id']='foreign-step'
    elif mutation=='reserved_ordinal': a[0]['ordinal']=1
    elif mutation=='review_downgrade': p[0]['review_required']=True; a[0]['review_required']=False
    elif mutation=='forward_dep': p[0]['prerequisite_step_ids']=['step-1']; a[0]['prerequisite_step_ids']=['step-1']
    elif mutation=='unknown_dep': p[1]['prerequisite_step_ids']=['absent']; a[1]['prerequisite_step_ids']=['absent']
    elif mutation=='duplicate_dep': p[1]['prerequisite_step_ids']=['step-0','step-0']; a[1]['prerequisite_step_ids']=['step-0','step-0']
    elif mutation=='dependency_drift': a[1]['prerequisite_step_ids']=[]
    _refused(snapshot, receipt)


@pytest.mark.parametrize('owner,field,value', [('plan','schema_version','foreign'),
    ('admission','schema_version','mastermind.coo_plan_admission/v1'),
    ('plan','root_job_id','JOB-OTHER'),('admission','root_job_id','JOB-OTHER'),
    ('plan','plan_attempt_id','ATT-OTHER'),('admission','policy_sha','z'*64),
    ('admission','plan_digest','a'*63),('admission','reservation_digest',None)])
def test_plan_header_identities_and_schema_pair_refused(owner,field,value):
    snapshot, receipt = _material()
    getattr(snapshot, owner)[field]=value
    _refused(snapshot, receipt)


def test_real_runtime_snapshot_and_finalized_receipt(tmp_path):
    from tests.test_runtime_admitted_plan_read import _bound
    from tests.test_executive_terminal_return import _completed_planner
    runtime, planner, _ = _completed_planner(tmp_path)
    with _bound(runtime) as (reader, _, _):
        with reader.observe_bounded_read() as observation:
            snapshot = observation.read_admitted_plan_bounded(planner.root_job_id)
        view = project_admitted_plan(snapshot, observation.receipt)
    assert view['root_job_id'] == planner.root_job_id
    assert view['admission_state'] == 'ADMITTED'
    assert set(view) == {'schema', 'plan_schema_version', 'admission_schema_version',
                         'root_job_id', 'plan_attempt_id', 'policy_sha', 'plan_digest',
                         'reservation_digest', 'admission_state', 'steps'}
    assert all(set(step) == {'ordinal', 'step_id', 'objective', 'business_impact',
                            'review_required', 'prerequisite_step_ids'} for step in view['steps'])


@pytest.mark.parametrize('owner,field,value', [('plan','steps',None),('admission','steps',None),
    ('plan','steps',[None]),('admission','steps',[None]),('plan','root_job_id',[]),
    ('plan','schema_version',[]),('admission','policy_sha',[]),('plan','steps','invalid')])
def test_malformed_detached_material_has_closed_typed_refusal(owner,field,value):
    snapshot, receipt = _material()
    getattr(snapshot, owner)[field]=value
    _refused(snapshot, receipt)


def test_projector_does_not_reenter_runtime_policy_or_io(monkeypatch):
    import builtins
    from control_plane import executive_runtime as er
    snapshot, receipt = _material()
    def denied(*args, **kwargs):
        pytest.fail('pure projection attempted I/O or owner re-entry')
    monkeypatch.setattr(builtins, 'open', denied)
    monkeypatch.setattr(er.CooCyclePolicy, 'load', denied)
    monkeypatch.setattr(er.Runtime, 'observe_bounded_read', denied)
    monkeypatch.setattr(er, '_validated_plan_admission', denied)
    assert project_admitted_plan(snapshot, receipt)['admission_state'] == 'ADMITTED'


# Original independent review findings, exercised before repairing the candidate.
def test_review_objective_subclass_refuses_closed():
    snapshot, receipt = _material()
    snapshot.plan['steps'][0]['objective'] = type('TextSubclass', (str,), {})('Read source evidence.')
    _refused(snapshot, receipt, 'CONTENT_WITHHELD')


@pytest.mark.parametrize('owner', ['plan', 'admission'])
def test_review_schema_subclass_refuses_closed(owner):
    snapshot, receipt = _material()
    material = getattr(snapshot, owner)
    material['schema_version'] = type('SchemaSubclass', (str,), {})(material['schema_version'])
    _refused(snapshot, receipt)


@pytest.mark.parametrize('field,value', [('job_id', 'JOB-CHILD'),
    ('root_job_id', 'JOB-OTHER'), ('orchestration_role', 'programme'), ('work_ref', '')])
def test_review_self_root_metadata_join(field, value):
    snapshot, receipt = _material()
    snapshot = replace(snapshot, root_metadata=replace(snapshot.root_metadata, **{field: value}))
    _refused(snapshot, receipt)


def test_review_nonadjacent_dependency_is_preserved():
    snapshot, receipt = _material(count=3)
    snapshot.plan['steps'][2]['prerequisite_step_ids'] = ['step-0']
    snapshot.admission['steps'][2]['prerequisite_step_ids'] = ['step-0']
    view = project_admitted_plan(snapshot, receipt)
    assert view['steps'][2]['prerequisite_step_ids'] == ['step-0']


@pytest.mark.parametrize('impact', ['material', 'critical'])
def test_review_eight_steps_preserve_impact_and_strengthened_review(impact):
    snapshot, receipt = _material(count=8)
    for step in snapshot.plan['steps']:
        step['business_impact'] = impact
    view = project_admitted_plan(snapshot, receipt)
    assert len(view['steps']) == 8
    assert [s['ordinal'] for s in view['steps']] == list(range(8))
    assert all(s['business_impact'] == impact and s['review_required'] is True for s in view['steps'])


@pytest.mark.parametrize('version', [1, 2])
def test_review_reverse_schema_pairing_refuses(version):
    snapshot, receipt = _material(version)
    snapshot.admission['schema_version'] = 'mastermind.coo_plan_admission/v2'
    _refused(snapshot, receipt)


def test_review_foreign_receipt_schema_is_not_authenticated_conflict():
    snapshot, receipt = _material()
    _refused(snapshot, replace(receipt, schema='foreign', state='CONFLICT'))
