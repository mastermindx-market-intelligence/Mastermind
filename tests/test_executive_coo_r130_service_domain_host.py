"""Actual Service/Runtime host producer, without installation or provider calls."""
import dataclasses
import json
import pytest
from control_plane import ceo_intent
from control_plane.executive_agent_capabilities import (
    DEFAULT_CAPABILITY_POLICY_PATH, ExecutionCapabilityRegistry, COO_DOMAIN_EXECUTION_PROFILE,
)
from control_plane.executive_runtime import AttemptLease, AttemptStatus, Runtime, StateConflict
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.operator_harness_contract import NativeHelperPolicy
from control_plane.executive_service import ExecutiveControlService, ServiceError
from tests.test_executive_service import _config, _coo_intent
from tests.test_executive_coo_r119_later_turn import _inventory


def _host(tmp_path, monkeypatch, *, domain=True, enabled=True, quota='codex-coo-domain'):
    raw=json.loads(DEFAULT_CAPABILITY_POLICY_PATH.read_bytes())
    raw['profiles'][COO_DOMAIN_EXECUTION_PROFILE]['enabled']=enabled
    path=tmp_path/'current-domain-registry-before-root.json'
    path.write_text(json.dumps(raw))
    registry=ExecutionCapabilityRegistry.load(path)
    monkeypatch.setattr(ExecutionCapabilityRegistry,'load',classmethod(lambda cls,*args,**kwargs:registry))
    config=_config(tmp_path,coo_autonomy_armed=True,coo_operator_harness_armed=True,
        coo_domain_operator_armed=domain,coo_operator_quota_class=quota,
        operator_harness_binary_digest='a'*64,operator_harness_version='0.147.0')
    service=ExecutiveControlService(config,autonomy_guard=lambda:None)
    runtime=Runtime.at(config.runtime_root);service.runtime=runtime
    return service,runtime,registry


def _root(service, runtime, *, name='r130'):
    intent=_coo_intent(service.config,name)
    received=ceo_intent.submit_intent(runtime,intent,
        workspace_root=service.config.proof_workspace_root,
        execution_binding=service._coo_execution_binding)
    root=runtime.jobs.get_job(received['job_id'])
    assert root is not None and service._is_bound_coo_root(root)
    domain=runtime.jobs.create_cycle_domain(root.job_id,
        command_id=f'coo-cycle:{root.job_id}:create-domain:0')
    return root,domain


def test_actual_service_domain_host_binding_quota_and_public_claim_are_compatible(tmp_path,monkeypatch):
    service,rt,registry=_host(tmp_path,monkeypatch)
    alias=service._coo_execution_binding
    assert alias['operator_execution_profile_id']==COO_DOMAIN_EXECUTION_PROFILE
    legacy=registry.resolve('operator.appserver.readonly.docs-mcp.native-helper.v1')
    assert legacy.native_helper is not None
    service._register_worker();service._require_coo_worker_composed()
    quota=rt.workers.get_quota_class(service.config.worker_id,'codex-coo-domain')
    assert quota.metadata['execution_profile_id']==COO_DOMAIN_EXECUTION_PROFILE
    assert quota.metadata['execution_profile_digest']==registry.resolve(COO_DOMAIN_EXECUTION_PROFILE).profile_digest
    assert 'model_alias' not in quota.metadata
    assert quota.metadata['source_model_alias']=='coo.operator.readonly'
    root,domain=_root(service,rt)
    assert service._require_bound_coo_job(domain)==root
    outcome=rt.attempts.dispatch_cycle_job(domain.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{domain.job_id}:attempt:1',
        worker_id=service.config.worker_id,lease_owner='r130-actual-service-owner')
    assert outcome is not None and outcome.attempt.status is AttemptStatus.CLAIMED
    assert outcome.lease_token and outcome.attempt.quota_class=='codex-coo-domain'
    # The public CLAIMED outcome precedes Supervisor profile/grant binding and G1.
    assert outcome.attempt.requested_execution_profile is None
    for key in ('execution_profile_id','execution_profile_digest',
        'capability_policy_version','capability_policy_digest'):
        assert quota.metadata[key]==domain.constraints[key]
    supervisor=ExecutiveOperatorSupervisor(rt,adapter_factory=lambda loader:pytest.fail('provider factory'),
        prompt_source=object(),instance_id=outcome.attempt.lease_owner)
    requested=supervisor._requested_profile(domain,AttemptLease(outcome.attempt,outcome.lease_token))
    assert requested.requested_model==quota.model and requested.worker_id==service.config.worker_id
    assert requested.sandbox_policy=='read-only' and requested.network_policy=='disabled'
    assert requested.native_helper_policy is NativeHelperPolicy.DISABLED
    assert requested.allowed_write_paths==()
    assert len(rt.attempts.list_attempts(domain.job_id))==1
    assert rt.workers.get_quota_class(service.config.worker_id,'codex-coo-operator') is None
    assert 'lease_token' not in json.dumps(outcome.to_dict())


def test_default_off_keeps_exact_legacy_helper_binding_and_refuses_domain_child(tmp_path,monkeypatch):
    service,rt,registry=_host(tmp_path,monkeypatch,domain=False,quota='codex-coo-operator')
    profile=registry.resolve('operator.appserver.readonly.docs-mcp.native-helper.v1')
    assert service._coo_execution_binding['operator_execution_profile_id']==profile.profile_id
    assert service._coo_execution_binding['operator_execution_profile_digest']==profile.profile_digest
    service._register_worker()
    quota=rt.workers.get_quota_class(service.config.worker_id,'codex-coo-operator')
    assert quota.metadata['model_alias']=='coo.operator.readonly'
    root,domain=_root(service,rt)
    before=_inventory(rt)
    with pytest.raises(StateConflict,match='execution_profile_id'):
        service._require_bound_coo_job(domain)
    assert _inventory(rt)==before and not rt.attempts.list_attempts()


def test_disarmed_domain_profile_refuses_service_construction(tmp_path,monkeypatch):
    with pytest.raises(ValueError,match='production-disarmed'):
        _host(tmp_path,monkeypatch,enabled=False)


@pytest.mark.parametrize('flag',[1,'true',None])
def test_domain_flag_is_exact_boolean(tmp_path,flag):
    with pytest.raises(ValueError,match='coo_domain_operator_armed must be boolean'):
        _config(tmp_path,coo_domain_operator_armed=flag)


@pytest.mark.parametrize('autonomy,harness,quota',[(False,False,'codex-coo-domain'),
    (True,False,'codex-coo-domain'),(True,True,'codex-coo-operator'),
    (True,True,'CODEX-COO-OPERATOR'),(True,True,'Codex-Coo-Operator'),
    (True,True,'codex-coo-Operator')])
def test_domain_host_requires_both_arms_and_distinct_quota(tmp_path,autonomy,harness,quota):
    with pytest.raises(ValueError,match='requires'):
        _config(tmp_path,coo_domain_operator_armed=True,coo_autonomy_armed=autonomy,
            coo_operator_harness_armed=harness,coo_operator_quota_class=quota)


def test_domain_quota_addition_preserves_existing_legacy_capacity(tmp_path,monkeypatch):
    service,rt,registry=_host(tmp_path,monkeypatch,domain=False,quota='codex-coo-operator')
    service._register_worker()
    before=rt.workers.get_quota_class(service.config.worker_id,'codex-coo-operator')
    domain_service=ExecutiveControlService(dataclasses.replace(service.config,
        coo_domain_operator_armed=True,coo_operator_quota_class='codex-coo-domain'),autonomy_guard=lambda:None)
    domain_service.runtime=rt
    domain_service._register_worker();domain_service._require_coo_worker_composed()
    assert rt.workers.get_quota_class(service.config.worker_id,'codex-coo-operator')==before
    assert rt.workers.get_quota_class(service.config.worker_id,'codex-coo-domain').metadata['execution_profile_id']==COO_DOMAIN_EXECUTION_PROFILE


def test_domain_quota_collision_refuses_without_overwriting_current_entry(tmp_path,monkeypatch):
    service,rt,registry=_host(tmp_path,monkeypatch,domain=False,quota='legacy-custom-operator')
    service._register_worker();before=_inventory(rt)
    replacement=ExecutiveControlService(dataclasses.replace(service.config,coo_domain_operator_armed=True),autonomy_guard=lambda:None)
    replacement.runtime=rt
    with pytest.raises(StateConflict,match='differs|drift|different'):
        replacement._register_worker()
    assert _inventory(rt)==before


@pytest.mark.parametrize('bad',['profile','model','base','quota','parent','branch'])
def test_actual_host_refuses_widened_or_foreign_child_before_dispatch(tmp_path,monkeypatch,bad):
    service,rt,_=_host(tmp_path,monkeypatch);root,domain=_root(service,rt)
    c=dict(domain.constraints)
    fields={'profile':'execution_profile_id','model':'model','base':'base_sha','quota':'eligible_quota_classes'}
    if bad in fields:
        c[fields[bad]]=['foreign-quota'] if bad=='quota' else 'foreign'
        domain=dataclasses.replace(domain,constraints=c)
    elif bad=='parent':domain=dataclasses.replace(domain,parent_job_id='foreign-parent')
    else:domain=dataclasses.replace(domain,branch='foreign-branch')
    before=_inventory(rt)
    with pytest.raises(StateConflict):service._require_bound_coo_job(domain)
    assert _inventory(rt)==before and not rt.attempts.list_attempts()
