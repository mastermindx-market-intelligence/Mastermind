"""Real local open/close probes; realm issuer is an explicit inert fixture.

No provider call, real secret or host enrollment occurs. Mode-000 harmless
sentinels exercise actual kernel EACCES under the current non-root user.
"""
import copy
import dataclasses
import hashlib
import os
from pathlib import Path

import pytest

from control_plane import executive_canary as canary
from control_plane import codex_provider_realm as realm
from tests.test_fabric_attended_secret_canary import inputs


@pytest.fixture
def assigned(tmp_path, monkeypatch):
    uid,gid=os.getuid(),os.getgid()
    assert uid != 0, 'real denial fixture requires ordinary non-root test user'
    home=tmp_path/'provider-home';home.mkdir(mode=0o700)
    credential=home/'provider-credential';credential.write_bytes(b'harmless-fixture');credential.chmod(0o600)
    config=canary.SecretCanaryConfig(uid,gid,uid+1,gid+1,'MM_TEST_PROBE_SENTINEL','c'*64,
        tmp_path/'admin',tmp_path/'db',tmp_path/'other',tmp_path/'production',home)
    protected=[config.administrative_checkout_sentinel,*canary._database_paths(config.executive_database),
        config.other_worker_home_sentinel,config.forbidden_production_sentinel]
    for p in protected:p.write_bytes(b'harmless-denied-fixture');p.chmod(0)
    _,args=inputs();args['provider_home']=home
    binding=canary.AttendedCanaryBinding(**args)
    owner=realm.SubscriptionRealmOwner(tmp_path/'inert-config','a'*64,realm._SUBSCRIPTION_REALM_OWNER_SEAL)
    observation={'worker_id':binding.spec.worker_id,'binding_id':binding.harness_binding_id,'control_uid':uid+1}
    monkeypatch.setattr(realm.SubscriptionRealmOwner,'observe',lambda self:dict(observation))
    monkeypatch.setattr(realm,'_native_read_config',lambda *a:{'worker_uid':uid,'worker_gid':gid,
        'control_gid':gid+1,'provider_home':str(home)})
    return config,binding,owner,credential,protected


def test_actual_open_only_probe_produces_new_committed_v2(assigned,monkeypatch):
    config,binding,owner,credential,protected=assigned
    real_read=os.read;inode=credential.stat().st_ino
    def no_secret_read(fd,count):
        assert os.fstat(fd).st_ino != inode
        return real_read(fd,count)
    monkeypatch.setattr(os,'read',no_secret_read)
    result=canary.run_attended_secret_canary(config,binding,realm_owner=owner)
    assert result['schema_version'].endswith('/v2')
    assert result['realm_binding']['run_id']==binding.spec.run_id
    assert canary.validate_attended_secret_canary_binding(config,binding,canary.PrincipalIdentity.current(),result)==result
    changed=copy.deepcopy(result);changed['observed_at']='2020-01-01T00:00:00Z'
    with pytest.raises(canary.SecretCanaryError):
        canary.validate_attended_secret_canary_binding(config,binding,canary.PrincipalIdentity.current(),changed)


@pytest.mark.parametrize('field',['run_id','job_id','worker_id'])
def test_other_assignment_cannot_consume_receipt(assigned,field):
    config,binding,owner,_,_=assigned
    value=canary.run_attended_secret_canary(config,binding,realm_owner=owner)
    wrong=dataclasses.replace(binding,spec=dataclasses.replace(binding.spec,**{field:'other'}))
    with pytest.raises(canary.SecretCanaryError):
        canary.validate_attended_secret_canary_binding(config,wrong,canary.PrincipalIdentity.current(),value)


@pytest.mark.parametrize('fault',['readable','missing','environment','public_credential','hardlink','symlink','public_home','wrong_principal','wrong_physical','wrong_binding','wrong_owner'])
def test_actual_guard_failures_never_issue_v2(assigned,monkeypatch,fault):
    config,binding,owner,credential,protected=assigned
    if fault=='readable':protected[0].chmod(0o600)
    if fault=='missing':protected[0].unlink()
    if fault=='environment':monkeypatch.setenv(config.control_environment_sentinel,'harmless')
    if fault=='public_credential':credential.chmod(0o644)
    if fault=='hardlink':os.link(credential,credential.with_name('second-link'))
    if fault=='symlink':
        data=credential.read_bytes();credential.unlink();target=credential.with_name('target');target.write_bytes(data);credential.symlink_to(target)
    if fault=='public_home':credential.parent.chmod(0o755)
    if fault=='wrong_principal':config=dataclasses.replace(config,expected_worker_uid=config.expected_worker_uid+2)
    if fault=='wrong_physical':binding=dataclasses.replace(binding,physical_binding_sha256='invalid')
    if fault=='wrong_binding':binding=dataclasses.replace(binding,harness_binding_id='glm-coding-plan.claude-code-anthropic')
    if fault=='wrong_owner':owner=object()
    with pytest.raises((canary.SecretCanaryError,realm.ProviderRealmError)):
        canary.run_attended_secret_canary(config,binding,realm_owner=owner)


def test_governed_spec_keeps_original_grant(assigned):
    from control_plane.worker_execution_contract import OrchestrationLaunchSpec
    config,binding,owner,_,_=assigned
    values={f.name:getattr(binding.spec,f.name) for f in dataclasses.fields(binding.spec)}
    spec=OrchestrationLaunchSpec(**values,effective_grant_digest='d'*64)
    binding=dataclasses.replace(binding,spec=spec)
    receipt=canary.run_attended_secret_canary(config,binding,realm_owner=owner)
    assert binding.spec.effective_grant_digest=='d'*64
    assert canary.validate_attended_secret_canary_binding(config,binding,canary.PrincipalIdentity.current(),receipt)==receipt


def test_same_size_private_replacement_during_probe_refuses(assigned,monkeypatch):
    config,binding,owner,credential,_=assigned
    original=canary._probe_protected_paths
    def swap(*args,**kwargs):
        original(*args,**kwargs)
        new=credential.with_name('replacement');new.write_bytes(b'x'*credential.stat().st_size);new.chmod(0o600)
        os.replace(new,credential)
    monkeypatch.setattr(canary,'_probe_protected_paths',swap)
    with pytest.raises(canary.SecretCanaryError,match='CHANGED_DURING_PROBE'):
        canary.run_attended_secret_canary(config,binding,realm_owner=owner)
