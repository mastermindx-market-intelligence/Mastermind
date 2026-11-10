"""Fixture-explicit root installation/credential metadata; actual Runtime claim.

These fixtures never read a live config or credential, enroll a service or call
any provider. Configuration is an explicit premise, not operational admission.
"""
import copy
import hashlib
import json
import pytest
from common.native_memory_intent_contract import SCHEMA
from control_plane import protected_memory_profile as profile
from control_plane import native_memory_admission as admission
from control_plane.executive_runtime import Runtime


@pytest.fixture
def configured(tmp_path,monkeypatch):
    value={'schema':profile.SCHEMA,'profile_id':profile.PROFILE,
        'policy_sha256':hashlib.sha256(profile.canonical(profile.POLICY)).hexdigest(),
        'worker_id':'protected-fixture','quota_class':'memory-read','provider':'glm','model':'glm-5.3-flash',
        'account_ref':'configured-fixture-account','api_origin':'https://api.z.ai/api/paas/v4','credential_slot':'memory-model-01'}
    metadata={'adapter_id':'protected-memory-model','execution_profile_id':profile.PROFILE,
        'execution_profile_digest':hashlib.sha256(profile.canonical(value)).hexdigest(),
        'capability_policy_version':'memory-fixture-v1','capability_policy_digest':value['policy_sha256']}
    runtime=Runtime.at(tmp_path/'runtime')
    runtime.workers.register_worker(value['worker_id'],provider='glm',account_label=value['account_ref'],
        worker_type='protected-memory-model',capabilities=['research'],quota_classes={value['quota_class']:{
            'provider':'glm','model':value['model'],'capabilities':['research'],'metadata':metadata}})
    job=runtime.jobs.create_job('Configured protected Memory source fixture',requested_authorities=['READ'],constraints={
        'eligible_quota_classes':[value['quota_class']],**{k:v for k,v in metadata.items() if k!='adapter_id'},
        'native_memory':{'schema':SCHEMA,'operation_id':'original-op','intent':{'study_id':'study','root_id':'native-root',
        'operator_run_id':'native-parent','child_run_id':'native-child'}}})
    lease=runtime.attempts.claim_job(job.job_id,worker_id=value['worker_id'],quota_class=value['quota_class'],lease_owner='fixture')
    assert lease is not None
    claim=admission.capture_memory_runtime_claim(runtime,lease)
    from tests.test_memory_native_wire import issuer
    source=issuer(3)
    raw=profile.canonical({'runtime_root':str(runtime.store.root),'protected_memory_execution':value,
        'memory_native_issuer':{'schema':'mastermind.fixed_memory_issuer_transport.v2',
            'protocol':'memory.e0.native_issuer.v3','service_key_fingerprint':source['broker_service_fingerprint'],
            'known_hosts_sha256':'a'*64,'transport_profile':'memory.e0.protected_m2_service_ssh.v2'}})
    state={'raw':raw,'credential':(1,2,3),'owner':{'service_label':'com.mastermind.executive.control',
        'configuration_sha256':hashlib.sha256(raw).hexdigest()}}
    monkeypatch.setattr(profile.os,'geteuid',lambda:450)
    monkeypatch.setattr(profile,'_read_config',lambda:state['raw'])
    monkeypatch.setattr(profile,'_credential_metadata',lambda:state['credential'])
    return runtime,job,claim,state


def test_actual_config_profile_current_runtime_and_nominal_owner_join(configured):
    runtime,_,claim,state=configured;before=runtime.events.list_events()
    cap=profile.load_protected_memory_profile(claim,state['owner'])
    value=profile.require_protected_memory_profile(cap,claim,state['owner'])
    assert value['profile_id']==profile.PROFILE
    assert runtime.events.list_events()==before
    assert 'key' not in repr(cap)

@pytest.mark.parametrize('damage',['config','credential','uid','claim','clone','origin','ordinary_account'])
def test_replaced_profile_or_context_cannot_open_protected_execution(configured,monkeypatch,damage):
    runtime,job,claim,state=configured
    cap=profile.load_protected_memory_profile(claim,state['owner'])
    if damage=='config':state['raw']+=b' '
    elif damage=='credential':state['credential']=(2,3,4)
    elif damage=='uid':monkeypatch.setattr(profile.os,'geteuid',lambda:501)
    elif damage=='claim':
        with runtime.store.transaction() as con:con.execute("UPDATE jobs SET status='CANCELLED' WHERE job_id=?",(job.job_id,))
    elif damage=='clone':cap=object.__new__(profile.ProtectedMemoryProfile)
    else:
        changed=json.loads(state['raw'])
        if damage=='origin':changed['protected_memory_execution']['api_origin']='https://api.z.ai.attacker.test/api/paas/v4'
        else:changed['protected_memory_execution']['account_ref']='ordinary-user-account'
        state['raw']=profile.canonical(changed);state['owner']['configuration_sha256']=hashlib.sha256(state['raw']).hexdigest()
    with pytest.raises(profile.MemoryProfileRefused):profile.require_protected_memory_profile(cap,claim,state['owner'])
