"""Inert frozen wire vectors only; no issuer/auth/source or transport proof."""
import base64
import copy
import hashlib
import json
import pytest
from common import memory_native_wire as w
from common import protected_memory_model_input as model


def request(action='prepare_case',version=2):
    value={'schema':f'research_factory.market_memory_e0_native_issuer_request.v{version}',
        'action':action,'operation_id':'original-op','intent':{'study_id':'study','root_id':'native-root',
        'operator_run_id':'operator','child_run_id':'child','participant_binding_sha256':'a'*64}}
    if action in ('current_input','authorize_result_disclosure'): value['locator']=locator()
    if action=='authorize_result_disclosure':
        value['result_ref']={'attempt_id':'runtime-attempt','input_sha256':locator()['input_sha256'],
            'result_sha256':'b'*64,'result_bytes':12}
    return value

def rawpacket(): return 'Exact问题与sources'.encode()+w.SUFFIX

def locator():
    raw=rawpacket()
    return {'case_id':'case','installation_id':'installed','installation_epoch':'epoch',
        'original_selection_sha256':'a'*64,'original_intent_sha256':'c'*64,
        'input_sha256':hashlib.sha256(raw).hexdigest(),'input_bytes':len(raw)}

def issuer(version):
    ref={'schema':'native.ref.v1','object_id':'object','sha256':'d'*64,'bytes':12}
    return {'issuer_id':'MACRO_LINUX_NATIVE_E0_ISSUER','protocol':f'memory.e0.native_issuer.v{version}',
        'source_commit':'e'*40,'source_closure_sha256':'f'*64,'installation_id':'installed',
        'installation_epoch':'epoch','registration_ref':ref,'publication_ref':ref,
        'current_selection_sha256':'a'*64,'current_access_ref':ref,'recipient_grant_ref':ref,
        'broker_service_fingerprint':'SHA256:'+base64.b64encode(b'k'*32).decode().rstrip('='),
        'authority':'current_recipient_scoped_source_view_only'}

def response(req,state='COMPLETE'):
    action=req['action'];version=int(req['schema'][-1])
    value={'schema':f'research_factory.market_memory_e0_native_issuer_response.v{version}',
        'status':{'prepare_case':'CASE_PREPARED','current_input':'INPUT_CURRENT',
          'authorize_result_disclosure':'RESULT_DISCLOSURE_CURRENT','read_original_case':'ORIGINAL_CASE_STATE',
          'qualify_current_case':'CURRENT_CASE_QUALIFIED'}[action],
        'action':action,'operation_id':req['operation_id'],'intent':copy.deepcopy(req['intent']),
        'issuer':issuer(version),'verification':dict(w.FLAGS),'scientific_admission':False,'retry_authorized':False}
    if action=='qualify_current_case':return value
    loc=locator();raw=rawpacket()
    if action=='read_original_case': value['operation_state']=state
    if action!='read_original_case' or state=='COMPLETE': value['locator']=loc
    if action in ('prepare_case','current_input') or action=='read_original_case' and state=='COMPLETE':
        value['input']={'encoding':'base64','bytes':len(raw),'sha256':loc['input_sha256'],'body':base64.b64encode(raw).decode()}
    if action=='authorize_result_disclosure':
        value['result_ref']=copy.deepcopy(req['result_ref'])
        value['authorization']=dict(purpose='disclose_exact_original_untrusted_child_result',
            **{k:req['result_ref'][k] for k in ('input_sha256','result_sha256','result_bytes')})
        if version==3:value['authorization']['original_recipient']={
            'schema':'research_factory.market_memory_e0_original_recipient.v3','recipient_kind':'native_broker_service',
            'principal_ref':copy.deepcopy(issuer(3)['registration_ref']),
            'ssh_key_fingerprint':issuer(3)['broker_service_fingerprint'],
            'original_operation_id':req['operation_id'],'pre_input_intent_sha256':hashlib.sha256(w.canonical(req['intent'])).hexdigest()}
    return value

def frame(value):
    raw=w.canonical(value);return len(raw).to_bytes(4,'big')+raw

@pytest.mark.parametrize('version,action',[(v,a) for v in (1,2) for a in ('prepare_case','current_input','authorize_result_disclosure')]+[(2,'read_original_case')])
def test_closed_wire_roundtrip(version,action):
    req=request(action,version);before=copy.deepcopy(req)
    assert w.decode_request(w.encode_request(req))==req
    assert w.decode_response(frame(response(req)),request=req)==response(req)
    assert req==before

@pytest.mark.parametrize('state',['ABSENT','PENDING'])
def test_read_original_without_input_or_locator(state):
    req=request('read_original_case');value=response(req,state)
    assert w.decode_response(frame(value),request=req)==value
    value['locator']=locator()
    with pytest.raises(w.WireRefused):w.decode_response(frame(value),request=req)

@pytest.mark.parametrize('damage',['unknown','role','boolbytes','hash','double','echo','flags','version','fingerprint','result'])
def test_foreign_and_malformed_response_refuses(damage):
    req=request('authorize_result_disclosure' if damage=='result' else 'prepare_case');value=response(req)
    if damage=='unknown':value['raw_log']='SECRET'
    elif damage=='role':value['intent']['role']='reviewer'
    elif damage=='boolbytes':value['locator']['input_bytes']=True
    elif damage=='hash':value['input']['sha256']='b'*64
    elif damage=='double':
        raw=rawpacket()+w.SUFFIX;value['input'].update(body=base64.b64encode(raw).decode(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest());value['locator'].update(input_bytes=len(raw),input_sha256=value['input']['sha256'])
    elif damage=='echo':value['operation_id']='foreign'
    elif damage=='flags':value['verification']['authenticated']=True
    elif damage=='version':value['issuer']['protocol']='memory.e0.native_issuer.v1'
    elif damage=='fingerprint':value['issuer']['broker_service_fingerprint']='SHA256:forged'
    else:value['authorization']['result_sha256']='c'*64
    with pytest.raises(w.WireRefused,match='^memory_issuer_wire_refused$'):w.decode_response(frame(value),request=req)

@pytest.mark.parametrize('raw',[b'',b'\0\0\0\x02{}x',b'\0\0\0\x02{}'+b'\0\0\0\x02{}',b'\0\0\0\x02\xff\xff',b'\0\0\0\x0d{"x":1,"x":2}',b'\0\0\0\x03{}\n'])
def test_invalid_whole_frame(raw):
    with pytest.raises(w.WireRefused):w.decode_request(raw)

@pytest.mark.parametrize('selector',['task','slot','role','path','clock','authenticated','packet'])
def test_no_request_selector(selector):
    value=request();value[selector]=True
    with pytest.raises(w.WireRefused):w.encode_request(value)

@pytest.mark.parametrize('value',[{'deep':[[[[[[[[[[[[[[[[[[0]]]]]]]]]]]]]]]]]]}, {'nodes':[0]*8193}])
def test_depth_and_node_bounds(value):
    with pytest.raises(w.WireRefused):w.validate_request(value)

@pytest.mark.parametrize('state,reason',[('REFUSED','native_recipient_grant_unavailable'),('ORIGINAL_OPERATION_PENDING','original_operation_pending_no_replay')])
def test_refusal_has_no_private_content(state,reason):
    req=request();value={'schema':'research_factory.market_memory_e0_native_issuer_response.v2','status':state,'reason':reason,
        'verification':dict(w.FLAGS),'scientific_admission':False,'retry_authorized':False}
    assert w.decode_response(frame(value),request=req)==value
    value['input']='SECRET'
    with pytest.raises(w.WireRefused):w.decode_response(frame(value),request=req)

@pytest.mark.parametrize('prefix',[b'hello', '中文😀"\\\n'.encode(),b'x'*(65536-len(w.SUFFIX))])
def test_model_input_exact_complete_packet(prefix):
    packet=prefix+w.SUFFIX;raw=model.compile_memory_model_input(packet,model='glm-5.3-flash')
    assert model.decode_memory_model_input(raw,expected_packet=packet,expected_model='glm-5.3-flash')['input'].encode()==packet
    assert set(json.loads(raw))=={'model','input','max_output_tokens','stream'}

@pytest.mark.parametrize('damage',['append','double','oversize','nul','subclass','model','schemaappend'])
def test_model_cannot_reshape_native_input(damage):
    packet=rawpacket();name='glm-5.3'
    if damage=='append':packet+=b'extra'
    elif damage=='double':packet+=w.SUFFIX
    elif damage=='oversize':packet=b'x'*65536+w.SUFFIX
    elif damage=='nul':packet=b'\0'+packet
    elif damage=='subclass':
        class B(bytes):pass
        packet=B(packet)
    elif damage=='model':name='foreign'
    else:
        raw=w.canonical({'model':name,'input':packet.decode()+'RESULT_SCHEMA_JSON {}','stream':False,'max_output_tokens':8192})
        with pytest.raises(model.MemoryModelInputRefused):model.decode_memory_model_input(raw,expected_packet=packet,expected_model=name)
        return
    with pytest.raises(model.MemoryModelInputRefused):model.compile_memory_model_input(packet,model=name)
