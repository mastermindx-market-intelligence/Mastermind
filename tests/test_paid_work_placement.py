"""Existing host-union integration with the real, disabled paid source alias.

These are pure catalog/Runtime projection checks, never capacity admission.
"""
import copy
import json

import pytest

from control_plane import executive_runtime as er
from control_plane.executive_paid_fabric_composition import PaidWorkPlacement, placement_member
from control_plane.model_router import ModelRouter


def source():
    router = ModelRouter.load()
    member = placement_member(router, PaidWorkPlacement('glm.paid.sealed-input','paid-read'))
    review = router.resolve_model_alias('standard.review')
    base = {key:getattr(review,key) for key in (
        'execution_profile_id','execution_profile_digest','capability_policy_version',
        'capability_policy_digest','model','effort','cost_class')}
    base.update(provider=review.provider_alias,eligible_quota_classes=['codex-step'],
        preferred_model_aliases=[review.model_alias],routing_policy_version=router.policy_version)
    root = copy.deepcopy(base)
    root['work_placement_union'] = [{'provider_realm':'codex','quota_class':'codex-step'},member]
    return base, root, member


def projected(base, root, **placement):
    return er._project_work_placement(base, root,
        {'provider_realm':'glm','quota_class':'paid-read',**placement},
        raw_root_constraints=root,plan_schema_version='mastermind.execution_plan/v5')


def test_paid_host_member_projects_exact_alias_without_changing_codex_root():
    base, root, member = source()
    before = copy.deepcopy(root)
    union = er._normalise_work_placement_union(root['work_placement_union'])
    assert member in union
    value = projected(base,root)
    route = member['paid_execution_route']
    assert value['provider'] == 'glm'
    assert value['eligible_quota_classes'] == ['paid-read']
    assert value['preferred_model_aliases'] == ['glm.paid.sealed-input']
    assert value['execution_profile_id'] == 'fabric.paid.glm.sealed-input.v1'
    assert value['paid_execution_route'] == route
    assert er._normalise_constraints(value)['paid_execution_route'] == route
    assert root == before and root['execution_profile_id'] != value['execution_profile_id']


@pytest.mark.parametrize('change',[
    {'attended_route':{}}, {'provider_realm':'codex'},
    {'paid_execution_route':{}}, {'extra':'unadmitted'},
])
def test_union_refuses_mixed_unknown_or_wrong_provider_member(change):
    _,_,member = source()
    with pytest.raises(er.StateConflict):
        er._normalise_work_placement_union([{**member,**change}])


def test_paid_projection_cannot_change_model_or_inherit_attended_kind():
    base,root,_=source()
    with pytest.raises(er.StateConflict):
        projected(base,root,model='other-model')
    inherited={**base,'attended_route':{'old':'kind'}}
    value=projected(inherited,root,model='glm-5.3-flash')
    assert 'attended_route' not in value
    assert value['model']=='glm-5.3-flash'


@pytest.mark.parametrize('key,value',[
    ('execution_profile_id','sealed.worker.readonly.no-extensions.v1'),
    ('preferred_model_aliases',['standard.review']),
    ('provider','codex'),('model','other-model'),('execution_profile_digest','0'*64),
])
def test_constraint_route_and_catalog_identity_must_stay_equal(key,value):
    base,root,_=source();constraints=projected(base,root);constraints[key]=value
    with pytest.raises(er.StateConflict):
        er._normalise_constraints(constraints)


def test_capacity_must_advertise_identical_paid_route():
    base,root,member=source();constraints=projected(base,root)
    metadata={**member['paid_execution_route'],'model_alias':'glm.paid.sealed-input',
        'paid_execution_route':copy.deepcopy(member['paid_execution_route'])}
    row={'worker_id':'unit-worker','metadata_json':json.dumps(metadata)}
    assert er._capacity_matches_route(row,constraints)
    metadata['paid_execution_route']['model']='other-model'
    assert not er._capacity_matches_route({**row,'metadata_json':json.dumps(metadata)},constraints)
