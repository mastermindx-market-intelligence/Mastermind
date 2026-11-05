"""Closed instruction-specific admission frames and public bodies; no authority."""
import json
import math
import re
from functools import wraps
from common.executive_workspace_contract import canonical,bounded_canonical
from common.workspace_project_admission_contract import validate_principal
from common.workspace_project_plan_contract import validate_selection,validate_source
from common.workspace_project_instructions_contract import instruction_ref
RECEIPT_SCHEMA="mastermind.instruction_admission_suspension_receipt.v1"

CONTROL_FRAME_SCHEMA='mastermind.workspace_instruction_admission_control_read.v1'
ACTION_FRAME_SCHEMA='mastermind.workspace_instruction_admission_action.v1'
STATUS_FRAME_SCHEMA='mastermind.workspace_instruction_admission_status.v1'
CONTROL_SCHEMA='mastermind.workspace_instruction_admission_control.v1'
ACTION_SCHEMA='mastermind.workspace_instruction_admission_action_result.v1'
STATUS_SCHEMA='mastermind.workspace_instruction_admission_status_result.v1'
PAUSE='pause_instruction_admission'
SCHEMAS={CONTROL_FRAME_SCHEMA:'current',ACTION_FRAME_SCHEMA:'pause',STATUS_FRAME_SCHEMA:'status'}
OPERATIONS={'current':'instruction_admission_control','pause':PAUSE,'status':'read_instruction_admission_pause_command'}
MAX_REQUEST_BYTES=16384
MAX_RESPONSE_BYTES=32768
REASONS={'ACCESS_DENIED','SOURCE_UNAVAILABLE','SOURCE_CHANGED','OWNER_NOT_READY','INSTRUCTION_NOT_SUPPLIED'}
UNKNOWN='OWNER_OUTCOME_UNCONFIRMED'


def _closed(fn):
    @wraps(fn)
    def checked(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (ValueError,TypeError,KeyError,OverflowError,RecursionError):raise ValueError('invalid_input') from None
    return checked


def _exact(value,keys):
    if type(value) is not dict or set(value)!=set(keys):raise ValueError('invalid_input')


def _hex(value,size):return type(value) is str and re.fullmatch('[0-9a-f]{'+str(size)+'}',value) is not None


@_closed
def selection(value,*,command=False):
    _exact(value,{'work_ref','instruction_ref'}|({'command_id'} if command else set()))
    validate_selection({'work_ref':value['work_ref']});instruction_ref(value['instruction_ref'])
    if command and (type(value['command_id']) is not str or re.fullmatch(r'mmos-instruction-pause-[0-9a-f]{40}',value['command_id']) is None):raise ValueError()
    return json.loads(canonical(value))


def is_frame(value):return type(value) is dict and type(value.get('schema')) is str and value['schema'] in SCHEMAS


@_closed
def validate_frame(value):
    if not is_frame(value):raise ValueError()
    mode=SCHEMAS[value['schema']]
    _exact(value,{'schema','operation','selection','principal','admission_expires_at'}|({'expected_revision','expected_source'} if mode=='pause' else set()))
    if value['operation']!=OPERATIONS[mode]:raise ValueError()
    selected=selection(value['selection'],command=mode!='current');validate_principal(value['principal'])
    expires=value['admission_expires_at']
    if type(expires) not in (int,float) or not math.isfinite(expires) or not 0<expires<2**53:raise ValueError()
    if mode=='pause':
        if not _hex(value['expected_revision'],64):raise ValueError()
        validate_source(value['expected_source'],selected['work_ref'])
    bounded_canonical(value,limit=MAX_REQUEST_BYTES-1)
    return json.loads(canonical(value))


@_closed
def receipt(value,expected):
    _exact(value,{'schema','work_ref','instruction_ref','revision','source','command_id','state','event_id','request_digest','committed_at_ms'})
    if (value['schema']!=RECEIPT_SCHEMA or value['state']!='PAUSED' or value['work_ref']!=expected['work_ref']
            or value['instruction_ref']!=expected['instruction_ref'] or not _hex(value['revision'],64)
            or not _hex(value['request_digest'],64) or type(value['command_id']) is not str
            or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',value['command_id']) is None
            or 'command_id' in expected and value['command_id']!=expected['command_id']):raise ValueError()
    validate_source(value['source'],expected['work_ref'])
    if type(value['event_id']) is not int or not 0<value['event_id']<2**53 or type(value['committed_at_ms']) is not int or not 0<=value['committed_at_ms']<2**53:raise ValueError()
    return json.loads(canonical(value))


@_closed
def validate_control(value,expected):
    _exact(value,{'schema','selection','availability','state','source','instruction_revision','permission','owner_context','current_receipt','reason_codes'})
    selected=selection(expected)
    if value['schema']!=CONTROL_SCHEMA or selection(value['selection'])!=selected:raise ValueError()
    facts=('state','source','instruction_revision','permission','current_receipt')
    if value['availability']=='UNAVAILABLE':
        if any(value[k] is not None for k in facts) or type(value['reason_codes']) is not list or len(value['reason_codes'])!=1 or value['reason_codes'][0] not in REASONS:raise ValueError()
        if value['owner_context'] is not None:
            if value['reason_codes']!=['INSTRUCTION_NOT_SUPPLIED']:raise ValueError()
            _exact(value['owner_context'],{'principal_scope'})
            if not _hex(value['owner_context']['principal_scope'],64):raise ValueError()
    elif value['availability']=='AVAILABLE':
        validate_source(value['source'],selected['work_ref'])
        if value['reason_codes']!=[] or not _hex(value['instruction_revision'],64):raise ValueError()
        _exact(value['permission'],{'pause'})
        if value['permission']['pause'] is not True:raise ValueError()
        _exact(value['owner_context'],{'principal_scope'})
        if not _hex(value['owner_context']['principal_scope'],64):raise ValueError()
        if value['state']=='PAUSED':receipt(value['current_receipt'],selected)
        elif value['state']!='NOT_SUSPENDED' or value['current_receipt'] is not None:raise ValueError()
    else:raise ValueError()
    bounded_canonical({'ok':True,'result':value},limit=MAX_RESPONSE_BYTES-1)
    return json.loads(canonical(value))


@_closed
def validate_result(value,expected,*,status=False):
    selected=selection(expected,command=True);field='state' if status else 'disposition'
    _exact(value,{'schema','selection',field,'receipt','reason_codes'})
    if value['schema']!=(STATUS_SCHEMA if status else ACTION_SCHEMA) or selection(value['selection'],command=True)!=selected:raise ValueError()
    state=value[field];found=state==('OBSERVED' if status else 'COMMITTED')
    if found:
        receipt(value['receipt'],selected)
        if value['reason_codes']!=[]:raise ValueError()
    else:
        if value['receipt'] is not None:raise ValueError()
        reasons=value['reason_codes']
        if status and state=='NOT_OBSERVED':
            if reasons!=[]:raise ValueError()
        elif not status and state=='EFFECT_UNKNOWN':
            if reasons!=[UNKNOWN]:raise ValueError()
        elif state!=('UNAVAILABLE' if status else 'NOT_DISPATCHED') or type(reasons) is not list or len(reasons)!=1 or reasons[0] not in REASONS:raise ValueError()
    bounded_canonical({'ok':True,'result':value},limit=MAX_RESPONSE_BYTES-1)
    return json.loads(canonical(value))


def unavailable(selected,reason='SOURCE_UNAVAILABLE',*,owner_context=None):
    return validate_control({'schema':CONTROL_SCHEMA,'selection':selected,'availability':'UNAVAILABLE','state':None,'source':None,'instruction_revision':None,'permission':None,'owner_context':owner_context,'current_receipt':None,'reason_codes':[reason]},selected)


def decode_frame(raw):
    if type(raw) is not bytes or len(raw)>MAX_REQUEST_BYTES:raise ValueError('invalid_input')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('invalid_input')
            result[key]=value
        return result
    def invalid(_):raise ValueError('invalid_input')
    try:return validate_frame(json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=invalid))
    except (UnicodeError,TypeError,ValueError):raise ValueError('invalid_input') from None


def validate_envelope(value,frame):
    _exact(value,{'ok','result'})
    if value['ok'] is not True:raise ValueError('source_unavailable')
    mode=SCHEMAS[frame['schema']]
    body=validate_control(value['result'],frame['selection']) if mode=='current' else validate_result(value['result'],frame['selection'],status=mode=='status')
    return {'ok':True,'result':body}


def withheld(frame,*,attempted=False,reason='SOURCE_UNAVAILABLE'):
    mode=SCHEMAS[frame['schema']];selected=frame['selection']
    if mode=='current':body=unavailable(selected,reason)
    elif mode=='status':body={'schema':STATUS_SCHEMA,'selection':selected,'state':'UNAVAILABLE','receipt':None,'reason_codes':[reason]}
    else:body={'schema':ACTION_SCHEMA,'selection':selected,'disposition':'EFFECT_UNKNOWN' if attempted else 'NOT_DISPATCHED','receipt':None,'reason_codes':[UNKNOWN if attempted else reason]}
    return validate_envelope({'ok':True,'result':body},frame)
