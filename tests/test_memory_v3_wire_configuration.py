"""Prospective v3 DATA/config compatibility; no native grant or service effect.

The actual installed Control loader reads owned temporary files using its normal
closed validation. Temporary own-UID composition is its existing inert fixture,
not proof of installed root ownership, Linux identity, enrollment or permission.
"""
import copy
import hashlib
import time
import pytest
from common import memory_native_wire as wire
from control_plane import protected_memory_profile as profile
from scripts import executive_os_phase1c as cli
from tests.test_memory_native_wire import request,response,frame,issuer
from test_ceo_submit_armed_composition import _raw,_write


def stanzas():
    source=issuer(3);now=int(time.time())
    return {'memory_native_issuer':{'schema':'mastermind.fixed_memory_issuer_transport.v2',
        'protocol':'memory.e0.native_issuer.v3','transport_profile':'memory.e0.protected_m2_service_ssh.v2',
        'service_key_fingerprint':source['broker_service_fingerprint'],'known_hosts_sha256':'a'*64},
        'protected_memory_execution':{'schema':profile.SCHEMA,'profile_id':profile.PROFILE,
            'policy_sha256':hashlib.sha256(profile.canonical(profile.POLICY)).hexdigest(),
            'worker_id':'protected-worker','quota_class':'memory','provider':'glm','model':'glm-5.3-flash',
            'account_ref':'original-account','api_origin':'https://api.z.ai/api/paas/v4','credential_slot':'memory-model-01'},
        'memory_original_result_access':{'schema':'mastermind.memory_original_result_service_access.v1',
            'receiver_kind':'native_broker_service','principal_ref':source['registration_ref'],
            'ssh_key_fingerprint':source['broker_service_fingerprint'],'control_service_label':'com.mastermind.executive.control',
            'permissions':['read_original_child_result'],'scope':{
                'operation_id':'original-operation','native_root_id':'native-root','native_operator_run_id':'native-parent',
                'native_child_run_id':'native-child','job_id':'runtime-job','root_job_id':'runtime-root',
                'parent_job_id':None,'attempt_id':'runtime-attempt','pre_input_sha256':'b'*64,
                'input_sha256':'c'*64,'result_sha256':'d'*64},
            'not_before_seconds':now-1,'expires_at_seconds':now+1200}}


def test_actual_control_loader_accepts_only_known_closed_memory_stanzas_without_effect(tmp_path):
    data=stanzas();raw=_raw(tmp_path,**data)
    loaded=cli.load_control_config(_write(tmp_path,raw))
    for key in data:assert loaded[key]==data[key]
    assert loaded['runtime_root']==tmp_path/'runtime'
    assert not (tmp_path/'runtime').exists()


@pytest.mark.parametrize('damage',['unknown-key','transport-option','old-transport-v3','profile-secret',
    'profile-origin','recipient-user','permission-start','scope-extra','namespace-label','transport-key'])
def test_real_closed_loader_refuses_malformed_or_relabelled_memory_before_service(tmp_path,damage):
    data=stanzas()
    if damage=='unknown-key':data['memory_generic_reader']={}
    elif damage=='transport-option':data['memory_native_issuer']['options']=['ProxyCommand=untrusted']
    elif damage=='old-transport-v3':data['memory_native_issuer'].update(schema='mastermind.fixed_memory_issuer_transport.v1');del data['memory_native_issuer']['transport_profile']
    elif damage=='profile-secret':data['protected_memory_execution']['api_key']='INERT_NOT_A_REAL_KEY'
    elif damage=='profile-origin':data['protected_memory_execution']['api_origin']='https://untrusted.invalid/api/paas/v4'
    elif damage=='recipient-user':data['memory_original_result_access']['receiver_kind']='end_user'
    elif damage=='permission-start':data['memory_original_result_access']['permissions'].append('start')
    elif damage=='scope-extra':data['memory_original_result_access']['scope']['authenticated']=True
    elif damage=='namespace-label':data['memory_original_result_access']['scope']['root_job_id']=True
    else:data['memory_original_result_access']['ssh_key_fingerprint']=issuer(3)['broker_service_fingerprint'].replace('a','b')
    with pytest.raises(cli.ServiceError,match='protected Memory|fields drifted'):
        cli.load_control_config(_write(tmp_path,_raw(tmp_path,**data)))
    assert not (tmp_path/'runtime').exists()


@pytest.mark.parametrize('action',['qualify_current_case','prepare_case','current_input','authorize_result_disclosure','read_original_case'])
def test_explicit_v3_roundtrip_all_closed_actions(action):
    req=request(action,3);value=response(req)
    assert wire.decode_request(wire.encode_request(req))==req
    assert wire.decode_response(frame(value),request=req)==value
    if action=='qualify_current_case':
        assert set(value)=={'schema','status','action','operation_id','intent','issuer','verification','scientific_admission','retry_authorized'}


@pytest.mark.parametrize('damage',['input','locator','environment','options','grant','flags','foreign-intent','pending'])
def test_qualification_never_becomes_reusable_capability_or_private_input(damage):
    req=request('qualify_current_case',3);value=response(req)
    if damage=='flags':value['verification']['authenticated']=True
    elif damage=='foreign-intent':value['intent']['child_run_id']='foreign-child'
    elif damage=='pending':value['status']='ORIGINAL_CASE_STATE'
    else:value[damage]={}
    with pytest.raises(wire.WireRefused):wire.decode_response(frame(value),request=req)


@pytest.mark.parametrize('damage',['user','key','operation','intent','principal-extra'])
def test_v3_original_recipient_is_typed_exact_original_service_data(damage):
    req=request('authorize_result_disclosure',3);value=response(req);fact=value['authorization']['original_recipient']
    if damage=='user':fact['recipient_kind']='user'
    elif damage=='key':fact['ssh_key_fingerprint']='SHA256:forged'
    elif damage=='operation':fact['original_operation_id']='foreign-original'
    elif damage=='intent':fact['pre_input_intent_sha256']='e'*64
    else:fact['principal_ref']['role']='reviewer'
    with pytest.raises(wire.WireRefused):wire.decode_response(frame(value),request=req)


@pytest.mark.parametrize('version',[1,2])
def test_old_wire_versions_cannot_gain_v3_qualification_or_recipient(version):
    with pytest.raises(wire.WireRefused):wire.encode_request(request('qualify_current_case',version))
    req=request('authorize_result_disclosure',version);value=response(req)
    value['authorization']['original_recipient']=response(request('authorize_result_disclosure',3))['authorization']['original_recipient']
    with pytest.raises(wire.WireRefused):wire.decode_response(frame(value),request=req)
