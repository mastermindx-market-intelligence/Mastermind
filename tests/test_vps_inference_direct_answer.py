"""Exact direct-answer contract/client proof; transport and answers are fixtures.

This suite does not claim Runtime result production or provider execution.
"""
import asyncio
from copy import deepcopy
import hashlib

import pytest
from control_plane import executive_inference_io as io
from control_plane import executive_inference_contract as contract
from brain.fabric_inference_client import FabricInferenceClient, FabricUnavailable
from tests.test_fabric_inference_client import service_receipt, fixture_inference_request

REF_V2='mastermind.executive_service_inference_result_ref.v2'
VIEW='mastermind.fabric_service_inference_result_view.v1'
OP='direct-answer-fixture'
OBJECTIVE='Original bounded research'


def raw_result(job='JOB-001',text='Observed 铜 🧠; research evidence only.'):
    return {'schema_version':io.WORKER_RESULT_SCHEMA,'job_id':job,'run_id':'ATT-'+'a'*32,
            'worker_id':'fixture-worker','status':'COMPLETED','answer':text}


def reference(result):
    digest=hashlib.sha256(io.canonical_bytes(result)).hexdigest()
    try:
        return io.result_reference(job_id=result['job_id'],attempt_id=result['run_id'],worker_id=result['worker_id'],
            result_sha256='b'*64,content_sha256=digest)
    except TypeError:pytest.fail('canonical-content-bound direct reference is not implemented')


def fixture_response(receipt):
    result=raw_result(receipt['job_id']);ref=reference(result)
    document=io.result_document(reference=ref,result=result,max_output_chars=4096,raw_result_sha256=ref['result_sha256'])
    data={'schema':VIEW,'operation_ref':contract.intent_id(OP),'reference':ref,'request_fingerprint':receipt['fingerprint'],
          'generation':{'schema':'mastermind.runtime_read_observation.v1','state':'SAME','source_identity':'c'*32,'before':2,'after':2},
          'availability':'AVAILABLE','execution_status':'COMPLETED','content_complete':True,'acceptance':'NOT_PROJECTED','document':document}
    wrapper={'schema':'mastermind.executive_mcp_result.v1','tool':'executive_fabric','ok':True,'server_version':'fixture',
             'mode':'readonly','generated_at':'2026-10-12T02:00:00Z','grounding':{},'data':data,'degraded':[],'bounded':[],'error':None}
    return wrapper,ref


def test_v1_reference_is_unchanged_and_content_hash_has_a_distinct_name():
    r=raw_result()
    old=io.result_reference(job_id=r['job_id'],attempt_id=r['run_id'],worker_id=r['worker_id'],result_sha256='b'*64)
    assert old['schema']==io.RESULT_REF_SCHEMA
    assert set(old)=={'schema','job_id','attempt_id','worker_id','result_sha256'}
    new=reference(r)
    assert new['schema']==REF_V2 and new['result_sha256']=='b'*64
    assert new['content_sha256']==hashlib.sha256(io.canonical_bytes(r)).hexdigest()
    assert new['content_sha256']!=new['result_sha256']


def test_direct_document_verifies_content_digest_and_returns_an_isolated_copy():
    result=raw_result();ref=reference(result)
    document=io.result_document(reference=ref,result=result,max_output_chars=4096,raw_result_sha256='b'*64)
    value=io.validate_result_document(document,job_id=result['job_id'],max_output_chars=4096)
    assert value==document and value is not document
    value['result']['answer']='changed';assert document['result']['answer']==result['answer']
    document['result']['answer']='substituted answer'
    with pytest.raises(io.InferenceIOError):io.validate_result_document(document,job_id=result['job_id'],max_output_chars=4096)


def test_raw_digest_comparison_does_not_substitute_for_content_integrity():
    result=raw_result();ref=reference(result);result['answer']='different content'
    with pytest.raises(io.InferenceIOError):
        io.result_document(reference=ref,result=result,max_output_chars=4096,raw_result_sha256='b'*64)


@pytest.mark.parametrize('value',[None,True,'short','g'*64,1])
def test_invalid_canonical_content_hash_refuses(value):
    r=raw_result()
    try:
        with pytest.raises(io.InferenceIOError):
            io.result_reference(job_id=r['job_id'],attempt_id=r['run_id'],worker_id=r['worker_id'],result_sha256='b'*64,content_sha256=value)
    except TypeError:pytest.fail('content hash input validation not implemented')


def validate(response,receipt,ref):
    helper=getattr(contract,'validate_direct_result',None)
    assert callable(helper),'missing exact direct-result consumer validator'
    return helper(response,operation_key=OP,receipt=receipt,reference=ref,max_output_chars=4096)


@pytest.mark.parametrize('fault',['none','answer','operation','job','attempt','worker','raw_digest','content_digest','fingerprint','generation','partial','running','accepted','wrapper','bounded','degraded','extra','missing','limit'])
def test_direct_view_requires_the_complete_original_binding(tmp_path,fault):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE);response,ref=fixture_response(receipt)
    expected=deepcopy(ref);data=response['data']
    if fault=='answer':data['document']['result']['answer']='substituted'
    if fault=='operation':data['operation_ref']=contract.intent_id('foreign-operation')
    if fault in {'job','attempt','worker','raw_digest','content_digest'}:
        field={'job':'job_id','attempt':'attempt_id','worker':'worker_id','raw_digest':'result_sha256','content_digest':'content_sha256'}[fault]
        data['reference'][field]='foreign'
    if fault=='fingerprint':data['request_fingerprint']='f'*64
    if fault=='generation':data['generation']['after']=3
    if fault=='partial':data['content_complete']=False
    if fault=='running':data['execution_status']='RUNNING'
    if fault=='accepted':data['acceptance']='ACCEPTED'
    if fault=='wrapper':response['ok']=False
    if fault=='bounded':response['bounded']=['answer']
    if fault=='degraded':response['degraded']=['source']
    if fault=='extra':data['extra']='invented'
    if fault=='missing':del data['document']
    if fault=='limit':data['document']['result']['answer']='x'*4097
    if fault=='none':
        result=validate(response,receipt,expected)
        assert result==data and result is not data
        assert result['document']['result']['answer']==raw_result()['answer']
    else:
        with pytest.raises(ValueError):validate(response,receipt,expected)


def test_recomputed_content_hash_cannot_replace_status_selected_reference(tmp_path):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE);response,ref=fixture_response(receipt);expected=deepcopy(ref)
    response['data']['document']['result']['answer']='different but internally consistent result'
    replacement=reference(response['data']['document']['result'])
    response['data']['reference']=replacement;response['data']['document']['reference']=deepcopy(replacement)
    with pytest.raises(ValueError):validate(response,receipt,expected)


def test_client_reads_exact_answer_without_submission_and_preserves_original_request(tmp_path):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE);response,ref=fixture_response(receipt)
    wire=fixture_inference_request();before=deepcopy(wire);calls=[]
    async def tool(name,args):
        calls.append((name,deepcopy(args)))
        if name=='service_intent_status':
            return {'ok':True,'status':'accepted','request_ref':contract.intent_id(OP),'receipt':receipt,'terminal_result_ref':ref}
        assert name=='executive_fabric'
        assert args=={'view':'service_inference','operation_key':OP,'reference':ref}
        return response
    client=FabricInferenceClient(tool)
    method=getattr(client,'answer',None);assert callable(method),'client lacks the direct-answer path'
    value=asyncio.run(method(OP,OBJECTIVE,wire))
    assert value==response['data'] and wire==before
    assert [n for n,_ in calls]==['service_intent_status','executive_fabric']


@pytest.mark.parametrize('fault',['wrong_request','wrong_objective','missing_ref','old_raw_only_ref','foreign_receipt','read_timeout'])
def test_client_never_submits_or_accepts_unbound_answers(tmp_path,fault):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE);response,ref=fixture_response(receipt);calls=[]
    wire=fixture_inference_request();objective=OBJECTIVE
    if fault=='wrong_request':wire['input_text']='different request'
    if fault=='wrong_objective':objective='different objective'
    if fault=='missing_ref':ref=None
    if fault=='old_raw_only_ref':ref={'schema':io.RESULT_REF_SCHEMA,**{k:v for k,v in ref.items() if k not in {'schema','content_sha256'}}}
    if fault=='foreign_receipt':receipt=service_receipt(tmp_path/'foreign','foreign-operation',OBJECTIVE)
    async def tool(name,args):
        calls.append(name)
        if name=='service_intent_status':return {'ok':True,'status':'accepted','request_ref':contract.intent_id(OP),'receipt':receipt,'terminal_result_ref':ref}
        assert name=='executive_fabric'
        if fault=='read_timeout':raise TimeoutError('private transport detail')
        return response
    client=FabricInferenceClient(tool);method=getattr(client,'answer',None);assert callable(method),'missing direct-answer client'
    with pytest.raises(FabricUnavailable) as error:asyncio.run(method(OP,objective,wire))
    assert 'private transport' not in str(error.value) and 'submit_service_intent' not in calls
    if fault!='read_timeout':assert calls==['service_intent_status']


def test_client_read_cancellation_does_not_become_a_new_submit(tmp_path):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE);_,ref=fixture_response(receipt);calls=[]
    async def tool(name,args):
        calls.append(name)
        if name=='service_intent_status':return {'ok':True,'status':'accepted','request_ref':contract.intent_id(OP),'receipt':receipt,'terminal_result_ref':ref}
        raise asyncio.CancelledError()
    method=getattr(FabricInferenceClient(tool),'answer',None);assert callable(method),'missing direct-answer client'
    with pytest.raises(asyncio.CancelledError):asyncio.run(method(OP,OBJECTIVE,fixture_inference_request()))
    assert calls==['service_intent_status','executive_fabric']


def test_transport_cannot_mutate_the_client_reference_before_validation(tmp_path):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE);response,ref=fixture_response(receipt)
    original_ref=deepcopy(ref)
    async def tool(name,args):
        if name=='service_intent_status':return {'ok':True,'status':'accepted','request_ref':contract.intent_id(OP),'receipt':receipt,'terminal_result_ref':ref}
        changed=deepcopy(response)
        changed['data']['document']['result']['answer']='transport-substituted content'
        replacement=reference(changed['data']['document']['result'])
        args['reference'].clear();args['reference'].update(replacement)
        changed['data']['reference']=replacement;changed['data']['document']['reference']=deepcopy(replacement)
        return changed
    with pytest.raises(FabricUnavailable):
        asyncio.run(FabricInferenceClient(tool).answer(OP,OBJECTIVE,fixture_inference_request()))
    assert ref==original_ref


def test_complete_wrapper_budget_is_enforced_even_with_small_answer(tmp_path):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE);response,ref=fixture_response(receipt)
    response['grounding']={'oversize':'x'*(contract.MAX_RESULT_BYTES+1)}
    with pytest.raises(ValueError):validate(response,receipt,ref)


def test_unicode_and_key_order_have_one_canonical_content_identity():
    output=raw_result(text='Gold 铜 🧠 \n "quoted" evidence')
    reversed_output=dict(reversed(list(output.items())))
    assert reference(output)==reference(reversed_output)
    ref=reference(output)
    document=io.result_document(reference=ref,result=reversed_output,max_output_chars=4096,raw_result_sha256='b'*64)
    assert io.validate_result_document(document,job_id=output['job_id'],max_output_chars=4096)==document


def test_callback_cannot_rebind_original_request_by_mutating_shared_receipt(tmp_path):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE);response,ref=fixture_response(receipt)
    original_fingerprint=receipt['fingerprint'];calls=[]
    async def tool(name,args):
        calls.append(name)
        if name=='service_intent_status':
            return {'ok':True,'status':'accepted','request_ref':contract.intent_id(OP),'receipt':receipt,'terminal_result_ref':ref}
        receipt['fingerprint']='f'*64
        changed=deepcopy(response);changed['data']['request_fingerprint']=receipt['fingerprint']
        return changed
    with pytest.raises(FabricUnavailable):
        asyncio.run(FabricInferenceClient(tool).answer(OP,OBJECTIVE,fixture_inference_request()))
    assert receipt['fingerprint']!=original_fingerprint
    assert calls==['service_intent_status','executive_fabric']


def test_validated_submission_receipt_is_an_isolated_original_request_binding(tmp_path):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE)
    request={'operation_key':OP,'objective':OBJECTIVE,'inference_request':fixture_inference_request()}
    validated=contract.validate_submission_receipt(receipt,request)
    assert validated==receipt and validated is not receipt
    before=deepcopy(validated)
    receipt['fingerprint']='f'*64;receipt['grounding']['mastermind_sha']='9'*40
    assert validated==before
