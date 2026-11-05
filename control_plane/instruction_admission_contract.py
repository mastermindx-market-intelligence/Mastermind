"""Closed law for the existing Event owner's stable instruction Pause.

This module performs no I/O and grants no permission. Only an actual committed
Runtime event may become a receipt. Authored revision changes never resume it.
"""
from __future__ import annotations
import hashlib
import json
import re
from functools import wraps
from common.workspace_project_plan_contract import validate_selection,validate_source
from common.workspace_project_instructions_contract import instruction_ref

REQUEST_SCHEMA='mastermind.instruction_admission_suspension.request.v1'
PAYLOAD_SCHEMA='mastermind.instruction_admission_suspension.v1'
RECEIPT_SCHEMA='mastermind.instruction_admission_suspension_receipt.v1'
ERROR='INSTRUCTION_SUSPENSION_INVALID'


def _closed(fn):
    @wraps(fn)
    def checked(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (ValueError,TypeError,KeyError,OverflowError,RecursionError):raise ValueError(ERROR) from None
    return checked


def _canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def _token(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',value) is None:raise ValueError(ERROR)
    return value


@_closed
def canonical_work_ref(value):return validate_selection({'work_ref':value})['work_ref']


@_closed
def canonical_instruction_ref(value):return instruction_ref(value)


@_closed
def aggregate_identity(work_ref,instruction_ref):return canonical_work_ref(work_ref)+'/'+canonical_instruction_ref(instruction_ref)


@_closed
def make_pause_request(work_ref,instruction_ref,revision,source,command_id,actor):
    selected=canonical_work_ref(work_ref);ref=canonical_instruction_ref(instruction_ref)
    if type(revision) is not str or re.fullmatch(r'[0-9a-f]{64}',revision) is None:raise ValueError(ERROR)
    source=validate_source(source,selected)
    return {'schema':REQUEST_SCHEMA,'operation':'pause','work_ref':selected,'instruction_ref':ref,'revision':revision,
        'source':source,'command_id':_token(command_id),'actor':_token(actor)}


def _request(value):
    if (type(value) is not dict or set(value)!={'schema','operation','work_ref','instruction_ref','revision','source','command_id','actor'}
            or value['schema']!=REQUEST_SCHEMA or value['operation']!='pause'):raise ValueError(ERROR)
    return make_pause_request(*(value[k] for k in ('work_ref','instruction_ref','revision','source','command_id','actor')))


@_closed
def request_digest(request):return hashlib.sha256(_canonical(_request(request))).hexdigest()


@_closed
def make_pause_payload(request):
    value=_request(request)
    return {'schema':PAYLOAD_SCHEMA,'state':'PAUSED',**{k:value[k] for k in ('work_ref','instruction_ref','revision','source')},'request_digest':request_digest(value)}


def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError(ERROR)
        result[key]=value
    return result


@_closed
def parse_suspension_event(event):
    if type(event) is not dict or set(event)!={'event_id','aggregate_type','aggregate_id','event_type','command_id','actor','payload_json','created_at_ms'}:raise ValueError(ERROR)
    if (event['aggregate_type']!='workstream_instruction' or event['event_type']!='WORKSTREAM_INSTRUCTION_ADMISSION_SUSPENDED'
            or type(event['event_id']) is not int or event['event_id']<=0
            or type(event['created_at_ms']) is not int or event['created_at_ms']<0 or type(event['payload_json']) is not str):raise ValueError(ERROR)
    raw=event['payload_json'].encode('utf-8')
    if len(raw)>4096:raise ValueError(ERROR)
    payload=json.loads(raw,object_pairs_hook=_pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError(ERROR)))
    if type(payload) is not dict or set(payload)!={'schema','state','work_ref','instruction_ref','revision','source','request_digest'}:raise ValueError(ERROR)
    request=make_pause_request(*(payload[k] for k in ('work_ref','instruction_ref','revision','source')),event['command_id'],event['actor'])
    expected=make_pause_payload(request)
    if payload!=expected or _canonical(payload)!=raw or event['aggregate_id']!=aggregate_identity(request['work_ref'],request['instruction_ref']):raise ValueError(ERROR)
    return {'schema':RECEIPT_SCHEMA,**{k:request[k] for k in ('work_ref','instruction_ref','revision','source','command_id')},
        'state':'PAUSED','event_id':event['event_id'],'request_digest':expected['request_digest'],'committed_at_ms':event['created_at_ms']}
