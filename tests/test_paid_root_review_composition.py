"""Source-only admission/serialization tests; no host registration or jobs sent."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from control_plane import executive_runtime as er
from control_plane.model_router import ModelRouter
from test_executive_os_phase1fc import _v3_execution_binding


def recipe():
    router=ModelRouter.load();alias=router.resolve_model_alias('standard.review')
    return {'schema_version':'mastermind.paid_subject_review_binding/v1',
        'model_alias':alias.model_alias,'eligible_quota_classes':['codex-default.review'],
        'provider':alias.provider_alias,'model':alias.model,'effort':alias.effort,
        'cost_class':alias.cost_class,'routing_policy_version':router.policy_version,
        **{k:getattr(alias,k) for k in ('execution_profile_id','execution_profile_digest',
            'capability_policy_version','capability_policy_digest')},'authorities':['READ']}


def test_recipe_is_detached_exact_catalogue_and_default_ceiling():
    value=recipe();normalized=er.normalize_paid_subject_review_binding(value)
    assert normalized==value and normalized is not value
    value['authorities'].append('RESEARCH');assert normalized['authorities']==['READ']
    constraints=er.paid_subject_review_constraints({'cost_class':'default',
        'paid_subject_review_binding':normalized,'base_sha':'a'*40})
    assert constraints['cost_class']=='default'
    assert constraints['preferred_model_aliases']==['standard.review']
    assert constraints['required_capabilities']==['read']
    with pytest.raises(er.StateConflict):
        er.paid_subject_review_constraints({'cost_class':'small','paid_subject_review_binding':normalized})


@pytest.mark.parametrize('change',[
    {'authorities':['READ','RESEARCH']},{'authorities':['READ','RUN_TESTS']},
    {'cost_class':'small'},{'model_alias':'coo.sealed'},
    {'execution_profile_id':'sealed.worker.write.no-extensions.v1'},
    {'execution_profile_digest':'f'*64},{'eligible_quota_classes':['a','b']},
    {'extra':'no'}, {'provider':'glm'}, {'routing_policy_version':'old'},
])
def test_recipe_refuses_widening_catalogue_drift_or_extra_fields(change):
    value=recipe();value.update(change)
    with pytest.raises(er.StateConflict):er.normalize_paid_subject_review_binding(value)


def test_recipe_is_v3_host_only_and_included_in_existing_binding_digest():
    binding=_v3_execution_binding();binding.update(cost_class='default',paid_subject_review_binding=recipe())
    normalized=er._constraints_with_host_execution_binding(None,binding)
    assert normalized['paid_subject_review_binding']==recipe()
    first=er.finite_host_binding_digest(normalized)
    changed=copy.deepcopy(normalized)
    changed['paid_subject_review_binding']['eligible_quota_classes']=['other-readonly']
    assert er.finite_host_binding_digest(changed)!=first
    with pytest.raises(er.StateConflict):
        er._constraints_with_host_execution_binding({'paid_subject_review_binding':recipe()},binding)
    binding.pop('work_placement_union');binding['host_execution_binding_version']=er.HOST_EXECUTION_BINDING_V2
    with pytest.raises(er.StateConflict):er._constraints_with_host_execution_binding(None,binding)


def capacity_fixture(tmp_path,*,shared=True):
    runtime=er.Runtime.at(tmp_path)
    runtime.workers.register_worker('same-worker',provider='codex',account_label='one-account',
        worker_type='codex-cli',capabilities=['read'],quota_classes={
            'ordinary':{'provider':'codex','capabilities':['read']},
            'readonly':{'provider':'codex','capabilities':['read'],
                'metadata':{'single_worker_capacity':True} if shared else {}}})
    jobs=[]
    for quota in ('ordinary','readonly'):
        job_id=runtime.jobs.create_job('Offline capacity unit',requested_authorities=['READ'],
            constraints={'eligible_quota_classes':[quota],'provider':'codex'})
        jobs.append(job_id.job_id)
    return runtime,jobs


@pytest.mark.parametrize('order',[(0,1),(1,0)])
def test_shared_worker_blocks_both_cross_quota_directions(tmp_path,order):
    runtime,jobs=capacity_fixture(tmp_path);quotas=('ordinary','readonly')
    first=runtime.attempts.claim_job(jobs[order[0]],worker_id='same-worker',quota_class=quotas[order[0]])
    assert first is not None
    assert runtime.attempts.claim_job(jobs[order[1]],worker_id='same-worker',quota_class=quotas[order[1]]) is None
    assert runtime.jobs.get_job(jobs[order[1]]).attempt_count==0


def test_shared_worker_simultaneous_claims_use_existing_atomic_transaction(tmp_path):
    runtime,jobs=capacity_fixture(tmp_path)
    def claim(index):
        return runtime.attempts.claim_job(jobs[index],worker_id='same-worker',quota_class=('ordinary','readonly')[index])
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,(0,1)))
    assert sum(result is not None for result in results)==1


def test_legacy_worker_without_new_shared_member_keeps_existing_quota_behavior(tmp_path):
    runtime,jobs=capacity_fixture(tmp_path,shared=False)
    assert runtime.attempts.claim_job(jobs[0],worker_id='same-worker',quota_class='ordinary') is not None
    assert runtime.attempts.claim_job(jobs[1],worker_id='same-worker',quota_class='readonly') is not None
