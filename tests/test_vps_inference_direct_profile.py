"""Existing service App/MCP direct-view closure with synthetic auth/backend data.

The Runtime direct-view producer is not supplied by these fixtures.
"""
import asyncio
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from integrations.executive_mcp import inference as profile
from integrations.mastermind_executive_app.gateway import CeoIngressResponse
from tests.test_vps_inference_service import rsa_key, setup_app, call
from tests.test_vps_inference_direct_answer import OP,OBJECTIVE,fixture_response
from tests.test_fabric_inference_client import service_receipt


def args(reference):return {'operation_key':OP,'view':'service_inference','reference':deepcopy(reference)}


def test_existing_tool_advertises_and_validates_closed_direct_selection(tmp_path):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE);_,ref=fixture_response(receipt)
    value=args(ref)
    errors=list(Draft202012Validator(profile.TOOL_SPECS[2].input_schema).iter_errors(value))
    assert not errors,'existing service tool does not advertise direct result selection'
    assert profile.validate_arguments('executive_fabric',value)==value
    assert [t.name for t in profile.TOOL_SPECS]==['submit_service_intent','service_intent_status','executive_fabric']


@pytest.mark.parametrize('fault',['extra','path','missing_hash','raw_only','wrong_view','root_selector','bad_identity'])
def test_direct_selection_rejects_extra_or_unqualified_fields(tmp_path,fault):
    receipt=service_receipt(tmp_path,OP,OBJECTIVE);_,ref=fixture_response(receipt);value=args(ref)
    if fault=='extra':value['provider']='forbidden'
    if fault=='path':value['reference']['path']='/private/result'
    if fault=='missing_hash':value['reference'].pop('content_sha256')
    if fault=='raw_only':value['reference']['schema']='mastermind.executive_service_inference_result_ref.v1'
    if fault=='wrong_view':value['view']='all_results'
    if fault=='root_selector':value['root_job_id']=ref['job_id']
    if fault=='bad_identity':value['reference']['attempt_id']='../../private'
    with pytest.raises(Exception):profile.validate_arguments('executive_fabric',value)


def configure(rsa_key,tmp_path,*,fault=None):
    app,token,current=setup_app(rsa_key,tmp_path)
    receipt=service_receipt(tmp_path/'receipt',OP,OBJECTIVE);response,ref=fixture_response(receipt)
    frames=[];reads=[]
    async def send(path,frame):
        from control_plane import executive_inference_ingress as service
        frames.append(deepcopy(frame))
        if frame['schema']==service.STATUS_SCHEMA:
            if fault=='revoke_at_status':current['binding']=None
            return CeoIngressResponse('sent_ok',ok=True,result={'receipt':receipt,'terminal_result_ref':None if fault=='no_result' else ref})
        assert frame == {'schema':service.DIRECT_RESULT_SCHEMA,'operation_key':OP,'reference':ref}
        reads.append(deepcopy(frame))
        if fault=='read_error':raise RuntimeError('PRIVATE_BACKEND_DETAIL')
        if fault=='revoke_at_read':current['binding']=None
        data=deepcopy(response['data'])
        if fault=='substitution':data['document']['result']['answer']='substituted'
        if fault=='partial':data['content_complete']=False
        return CeoIngressResponse('sent_ok',ok=True,result=data)
    app._client.send_frame=send
    return app,token,current,ref,response,frames,reads


def test_enrolled_service_gets_exact_direct_view_not_an_aggregation(rsa_key,tmp_path):
    app,token,_,ref,response,frames,reads=configure(rsa_key,tmp_path)
    value=asyncio.run(call(app,token,'executive_fabric',args(ref)))
    assert value.status_code==200,value.text
    assert value.json()['data']==response['data']
    assert value.json()['server_version']=='1.2.0'
    assert len(frames)==2 and len(reads)==1
    assert 'role_result' not in value.text and value.json()['data']['acceptance']=='NOT_PROJECTED'


@pytest.mark.parametrize('fault,expected_reads',[('revoke_at_status',0),('revoke_at_read',1),('no_result',0),('read_error',1),('substitution',1),('partial',1)])
def test_direct_app_never_returns_unauthorized_unqualified_or_partial_answer(rsa_key,tmp_path,fault,expected_reads):
    app,token,_,ref,_,frames,reads=configure(rsa_key,tmp_path,fault=fault)
    value=asyncio.run(call(app,token,'executive_fabric',args(ref)))
    assert value.status_code in {403,503}
    assert 'data' not in value.json() and 'PRIVATE_BACKEND_DETAIL' not in value.text
    assert len(reads)==expected_reads and len(frames)==1+expected_reads


def test_foreign_valid_reference_is_refused_before_answer_read(rsa_key,tmp_path):
    app,token,_,ref,_,frames,reads=configure(rsa_key,tmp_path)
    foreign=args(ref);foreign['reference']['worker_id']='another-worker'
    value=asyncio.run(call(app,token,'executive_fabric',foreign))
    assert value.status_code==403 and len(frames)==1 and reads==[]


def test_disabled_service_never_reaches_status_or_result(rsa_key,tmp_path):
    app,token,current,ref,_,frames,reads=configure(rsa_key,tmp_path)
    current['binding']=None
    value=asyncio.run(call(app,token,'executive_fabric',args(ref)))
    assert value.status_code==403 and not frames and not reads


def test_actual_client_and_authenticated_asgi_profile_round_trip(rsa_key,tmp_path):
    from brain.fabric_inference_client import FabricInferenceClient
    from tests.test_fabric_inference_client import fixture_inference_request
    app,token,_,ref,response,frames,reads=configure(rsa_key,tmp_path)
    tools=[]
    async def transport(name,arguments):
        tools.append(name)
        result=await call(app,token,name,arguments)
        return result.json()
    result=asyncio.run(FabricInferenceClient(transport).answer(OP,OBJECTIVE,fixture_inference_request()))
    assert result==response['data']
    assert result['reference']==ref and result['document']['result']['answer'].startswith('Observed')
    assert tools==['service_intent_status','executive_fabric']
    assert len(frames)==3 and len(reads)==1
    assert frames[0]['schema'].endswith('status.v1')
    assert frames[1]['schema'].endswith('status.v1')
    assert frames[2]['schema'].endswith('read.v1')


def test_client_asgi_round_trip_refuses_identity_revoked_between_requests(rsa_key,tmp_path):
    from brain.fabric_inference_client import FabricInferenceClient,FabricUnavailable
    from tests.test_fabric_inference_client import fixture_inference_request
    app,token,current,_,_,frames,reads=configure(rsa_key,tmp_path)
    tools=[]
    async def transport(name,arguments):
        tools.append(name)
        result=await call(app,token,name,arguments)
        if name=='service_intent_status':current['binding']=None
        return result.json()
    with pytest.raises(FabricUnavailable):
        asyncio.run(FabricInferenceClient(transport).answer(OP,OBJECTIVE,fixture_inference_request()))
    assert tools==['service_intent_status','executive_fabric']
    assert len(frames)==1 and reads==[]
