"""Exact retained Macro vectors; DATA interoperability, never installed authority.

The packet is synthetic owner output. The result projection below is a NEW
explicitly synthetic result, not the original 50-byte result authorization.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import pytest
from common import memory_native_wire as wire
from common.memory_participant_view import selected_descriptors,project_original_result
from common.protected_memory_model_input import compile_memory_model_input,decode_memory_model_input
from control_plane import memory_native_issuer as facade
from control_plane import executive_memory_issuer as root
from control_plane import protected_memory_peer as peer
from tests.test_memory_native_issuer_owner import joined
from tests.test_native_memory_admission import claimed
from tests.test_protected_memory_peer import installed

FIXTURES=Path(__file__).parent/'fixtures/memory_native_v3_9fb08'
MANIFEST_SHA='899cca958901757b7d7d736c195f022abe769c6d656a025055c8dbf3123ac6f5'
PHASES=('01-qualification','02-absent','03-prepare','04-complete-lost-response',
        '05-current-input','06-result-authorization','07-current-access-advance','08-original-custody-corruption')

def pair(phase):
    manifest=(FIXTURES/'MANIFEST.json').read_bytes()
    assert hashlib.sha256(manifest).hexdigest()==MANIFEST_SHA
    row=next(v for v in json.loads(manifest)['vectors'] if v['phase']==phase)
    bodies={}
    for key,entry in row['payloads'].items():
        assert Path(entry['path']).name==entry['path']
        raw=(FIXTURES/entry['path']).read_bytes()
        assert len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256']
        bodies[key]=raw
    req=wire.decode_request(bodies['request.frame'])
    response=wire.decode_response(bodies['response.frame'],request=req)
    assert wire.canonical(req)==bodies['request.json']
    assert wire.canonical(response)==bodies['response.json']
    assert wire.encode_request(req)==bodies['request.frame']
    assert bodies['response.frame']==len(bodies['response.json']).to_bytes(4,'big')+bodies['response.json']
    return req,response

@pytest.mark.parametrize('phase',PHASES)
def test_whole_source_issued_request_response_and_frame_contract(phase):
    _,value=pair(phase)
    assert value['verification']==wire.FLAGS
    assert value['scientific_admission'] is False and value['retry_authorized'] is False
    if phase in ('01-qualification','02-absent','08-original-custody-corruption'):
        assert 'input' not in value and 'locator' not in value

def test_exact_current_access_continuation_preserves_packet_original_grant_and_case():
    _,first=pair('03-prepare');_,continued=pair('07-current-access-advance')
    # _State here is comparison DATA, not an issued NativeCaseCapability.
    state=facade._State(None,wire.canonical(first['issuer']),wire.canonical(first['locator']),
                       first['input']['sha256'],os.getpid())
    facade._same_source(state,continued)
    assert first['input']==continued['input'] and first['locator']==continued['locator']
    assert first['issuer']['recipient_grant_ref']==continued['issuer']['recipient_grant_ref']
    assert first['issuer']['current_selection_sha256']!=continued['issuer']['current_selection_sha256']

@pytest.mark.parametrize('field',['recipient_grant_ref','registration_ref','source_commit','installation_epoch','locator'])
def test_changed_original_binding_cannot_borrow_current_access_advancement(field):
    _,first=pair('03-prepare');_,value=pair('07-current-access-advance')
    state=facade._State(None,wire.canonical(first['issuer']),wire.canonical(first['locator']),
                       first['input']['sha256'],os.getpid())
    value=copy.deepcopy(value)
    if field=='locator':value['locator']['original_selection_sha256']='b'*64
    elif field.endswith('_ref'):value['issuer'][field]['sha256']='b'*64
    elif field=='source_commit':value['issuer'][field]='b'*40
    else:value['issuer'][field]='foreign-epoch'
    with pytest.raises(facade.NativeCaseRefused):facade._same_source(state,value)

def test_exact_native_packet_extractor_and_single_model_input_without_authority_append():
    _,value=pair('03-prepare');packet=wire.packet(value['input'],value['locator'])
    assert len(packet)==9846 and hashlib.sha256(packet).hexdigest()=='7ca590644be28c292858ac35e1907a707404cb8b0cb8db860b52aa29dd7fc6b0'
    descriptors=selected_descriptors(packet);assert len(descriptors)==10
    envelope=compile_memory_model_input(packet,model='glm-5.3-flash')
    assert decode_memory_model_input(envelope,expected_packet=packet,expected_model='glm-5.3-flash')['input'].encode()==packet
    synthetic=wire.canonical({'schema':'research_factory.market_memory_e0_participant_result.v1',
        'answer':'Explicitly new synthetic parser-only answer','citations':[descriptors[0]]})
    view=project_original_result(packet,synthetic,attempt_id='parser-only-attempt')
    assert view['verification']==wire.FLAGS and view['scientific_admission'] is False
    foreign=json.loads(synthetic);foreign['citations'][0]['capture_id']='foreign-capture'
    with pytest.raises(ValueError):project_original_result(packet,wire.canonical(foreign),attempt_id='parser-only-attempt')

def test_actual_disposable_runtime_refuses_foreign_raw_vector_without_splice_or_reprepare(joined,monkeypatch):
    runtime,_,_,intent,count=joined
    _,prepared=pair('03-prepare');fingerprint=prepared['issuer']['broker_service_fingerprint']
    transport=wire.canonical({'memory_native_issuer':{'schema':'mastermind.fixed_memory_issuer_transport.v2',
        'protocol':'memory.e0.native_issuer.v3','transport_profile':'memory.e0.protected_m2_service_ssh.v2',
        'service_key_fingerprint':fingerprint,'known_hosts_sha256':'a'*64}})
    monkeypatch.setattr(root,'_enrollment',lambda _:(transport,fingerprint,b'known',('fixture-only',)))
    observed=[]
    def exact_foreign(raw):
        req=wire.decode_request(raw);observed.append(req)
        phase='03-prepare' if req['action']=='prepare_case' else '04-complete-lost-response'
        return (FIXTURES/(phase+'.response.frame')).read_bytes()
    monkeypatch.setattr(root,'_exchange',exact_foreign)
    with pytest.raises(facade.NativeCaseRefused):facade.prepare_case(intent,version='v3')
    with pytest.raises(facade.NativeCaseRefused):facade.read_original_case(intent)
    with pytest.raises(facade.NativeCaseUnknown):facade.prepare_case(intent,version='v3')
    assert [r['action'] for r in observed]==['prepare_case','read_original_case']
    assert observed[0]['intent']['participant_binding_sha256']!='a'*64
    assert sum(e.event_type=='MEMORY_PREPARE_ATTEMPT' for e in runtime.events.list_events())==1
    assert len(runtime.jobs.list_jobs())==1
