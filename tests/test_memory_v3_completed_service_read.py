"""Actual disposable Runtime/receipts/files with explicit auth/transport premises.

Root installation/current Control/kernel observations and Linux native grants
are inert fixture substitutions. This is not installed, actual Linux transport,
end-user identity, provider truth or scientific acceptance. No live bytes read.
"""
import asyncio
import dataclasses
import hashlib
import json
import time
import pytest
from control_plane import protected_memory_execution as execution
from control_plane import protected_memory_original as original
from control_plane import protected_memory_completed_read as reader
from control_plane import protected_memory_profile as profile
from control_plane import paid_fabric_backend as paid
from control_plane import executive_peer_identity as peers
from tests.test_protected_memory_execution import joined
from tests.test_protected_memory_profile import configured
from tests.test_protected_memory_peer import installed
from tests.test_protected_memory_economic import economy


def install_fixture_service_policy(joined):
    runtime,_,lease,_,_,_,_,state,_=joined
    handle=original.completed_original_reference(runtime,lease.attempt.attempt_id)
    ref=original.current_reference(handle);held=original._REFERENCES[handle]
    native=json.loads(held.pre_input)['native_source_locator'];now=int(time.time())
    scope={k:ref[k] for k in ('operation_id','job_id','root_job_id','parent_job_id','attempt_id','pre_input_sha256','input_sha256','result_sha256')}
    scope.update(native_root_id=native['root_id'],native_operator_run_id=native['operator_run_id'],native_child_run_id=native['child_run_id'])
    recipient=ref['original_recipient']
    document=json.loads(state['config']['raw'])
    document['memory_original_result_access']={'schema':'mastermind.memory_original_result_service_access.v1',
        'receiver_kind':'native_broker_service','principal_ref':recipient['principal_ref'],
        'ssh_key_fingerprint':recipient['ssh_key_fingerprint'],'control_service_label':'com.mastermind.executive.control',
        'permissions':['read_original_child_result'],'scope':scope,'not_before_seconds':now-1,'expires_at_seconds':now+1200}
    replace_fixture_config(state,document)
    return ref


def replace_fixture_config(state,document):
    state['config']['raw']=profile.canonical(document)
    state['config']['owner']['configuration_sha256']=hashlib.sha256(state['config']['raw']).hexdigest()


@pytest.fixture
def completed_service(joined):
    runtime,_,lease,_,_,_,_,state,_=joined
    asyncio.run(state['supervisor'].run_protected_memory_case(lease))
    install_fixture_service_policy(joined)
    return joined


def test_genuine_completed_receipts_and_current_service_reopen_exact_original_without_lease_or_effect(completed_service):
    runtime,_,lease,actions,calls,_,_,state,_=completed_service
    before=list(runtime.events.list_events());prepared=actions.count('prepare_case');processes=len(calls)
    cap=reader.capture_completed_memory_read(state['supervisor'],lease.attempt.attempt_id)
    view=reader.read_completed_memory_result(cap)
    assert view['answer']=='Fixture untrusted answer'
    assert actions.count('prepare_case')==prepared and len(calls)==processes==1
    assert runtime.events.list_events()==before and runtime.attempts.get_attempt(lease.attempt.attempt_id).status.value=='COMPLETED'
    assert all(v is False for v in view['verification'].values()) and view['scientific_admission'] is False
    assert not hasattr(cap,'start') and not hasattr(cap,'prepare')


def test_new_current_control_epoch_can_read_same_original_service_without_cloning_original_lease(completed_service):
    runtime,_,lease,actions,calls,_,_,state,_=completed_service
    old=reader.capture_completed_memory_read(state['supervisor'],lease.attempt.attempt_id)
    current=state['installed'][1]
    current['observation']=dataclasses.replace(current['observation'],audit_token=b'B'*32,pidversion=current['observation'].pidversion+1)
    with pytest.raises(ValueError):reader.read_completed_memory_result(old)
    fresh=reader.capture_completed_memory_read(state['supervisor'],lease.attempt.attempt_id)
    assert reader.read_completed_memory_result(fresh)['answer']=='Fixture untrusted answer'
    assert len(calls)==1 and actions.count('prepare_case')==1
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).status.value=='COMPLETED'


@pytest.mark.parametrize('damage',['absent','expired','principal','key','foreign-parent','foreign-view','namespace','peer','linux-revoked'])
def test_missing_or_foreign_current_permission_withholds_private_body(completed_service,monkeypatch,damage):
    _,_,lease,_,calls,_,_,state,_=completed_service
    document=json.loads(state['config']['raw']);policy=document['memory_original_result_access']
    if damage=='absent':del document['memory_original_result_access']
    elif damage=='expired':policy.update(not_before_seconds=int(time.time())-2000,expires_at_seconds=int(time.time())-1)
    elif damage=='principal':policy['principal_ref']=dict(policy['principal_ref'],sha256='b'*64)
    elif damage=='key':policy['ssh_key_fingerprint']=policy['ssh_key_fingerprint'].replace('a','b')
    elif damage=='foreign-parent':policy['scope']['native_operator_run_id']='foreign-parent'
    elif damage=='foreign-view':policy['scope']['result_sha256']='e'*64
    elif damage=='namespace':document['runtime_root']='/unrelated/namespace'
    elif damage=='peer':state['installed'][1]['label']='unqualified-cli'
    else:state['disclosure_refused']=True
    replace_fixture_config(state,document)
    reads=[]
    monkeypatch.setattr(paid,'_private_read',lambda *_a:reads.append('private') or (_ for _ in ()).throw(AssertionError('no private read')))
    with pytest.raises(ValueError):reader.capture_completed_memory_read(state['supervisor'],lease.attempt.attempt_id)
    assert reads==[] and len(calls)==1


def test_late_current_permission_withdrawal_refuses_existing_read_capability(completed_service,monkeypatch):
    _,_,lease,_,_,_,_,state,_=completed_service
    cap=reader.capture_completed_memory_read(state['supervisor'],lease.attempt.attempt_id)
    state['disclosure_refused']=True;reads=[]
    monkeypatch.setattr(paid,'_private_read',lambda *_a:reads.append('private') or (_ for _ in ()).throw(AssertionError('no private read')))
    with pytest.raises(ValueError):reader.read_completed_memory_result(cap)
    assert reads==[]


@pytest.mark.parametrize('withdrawal',['policy','expiry'])
def test_policy_withdrawal_during_final_same_byte_result_reread_never_escapes_view(completed_service,monkeypatch,withdrawal):
    _,_,lease,_,_,_,_,state,_=completed_service
    cap=reader.capture_completed_memory_read(state['supervisor'],lease.attempt.attempt_id)
    actual=paid._private_read;result_reads=[]
    def withdraw_after_last_result_read(path,limit):
        raw=actual(path,limit)
        if path.name=='memory-original-result':
            result_reads.append(raw)
            if len(result_reads)==2:
                document=json.loads(state['config']['raw'])
                if withdrawal=='policy':
                    del document['memory_original_result_access']
                    replace_fixture_config(state,document)
                else:
                    deadline=document['memory_original_result_access']['expires_at_seconds']
                    from control_plane import protected_memory_result_access as access
                    monkeypatch.setattr(access.time,'time',lambda:deadline)
        return raw
    monkeypatch.setattr(paid,'_private_read',withdraw_after_last_result_read)
    with pytest.raises(ValueError):reader.read_completed_memory_result(cap)
    assert len(result_reads)==2 and result_reads[0]==result_reads[1]


def test_service_window_expiry_during_last_blocking_owner_probe_refuses_view(completed_service,monkeypatch):
    _,_,lease,_,_,_,_,state,_=completed_service
    cap=reader.capture_completed_memory_read(state['supervisor'],lease.attempt.attempt_id)
    from control_plane import memory_native_issuer as facade
    from control_plane import protected_memory_result_access as access
    deadline=json.loads(state['config']['raw'])['memory_original_result_access']['expires_at_seconds']
    actual=facade.describe_control_owner;probes=[]
    def expire_after_last_probe():
        value=actual();probes.append(value)
        if len(probes)==6:monkeypatch.setattr(access.time,'time',lambda:deadline)
        return value
    monkeypatch.setattr(facade,'describe_control_owner',expire_after_last_probe)
    with pytest.raises(ValueError):reader.read_completed_memory_result(cap)
    assert len(probes)==6


def test_v3_completed_access_advancement_keeps_original_native_grant_immutable(completed_service):
    _,_,lease,_,_,_,_,state,_=completed_service
    state['access_advanced']=True
    cap=reader.capture_completed_memory_read(state['supervisor'],lease.attempt.attempt_id)
    assert reader.read_completed_memory_result(cap)['answer']=='Fixture untrusted answer'
    state['grant_changed']=True
    with pytest.raises(ValueError):reader.read_completed_memory_result(cap)


@pytest.mark.parametrize('shape',['dict','clone','subclass'])
def test_no_dictionary_or_copied_nominal_object_is_completed_read_authority(completed_service,shape):
    _,_,lease,_,_,_,_,state,_=completed_service
    cap=reader.capture_completed_memory_read(state['supervisor'],lease.attempt.attempt_id)
    if shape=='dict':cap={'receiver_kind':'native_broker_service'}
    elif shape=='clone':cap=object.__new__(reader.CompletedMemoryRead)
    else:
        class Foreign(reader.CompletedMemoryRead):pass
        cap=object.__new__(Foreign)
    with pytest.raises(reader.CompletedReadRefused):reader.read_completed_memory_result(cap)
