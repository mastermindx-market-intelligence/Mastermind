"""Closed public DTOs cannot promote content, old receipts or input authority."""
import copy
import json
import pytest
from common import workspace_instruction_admission_contract as wire
from tests.test_workspace_member_bindings import principal,fixture

SELECTED={'work_ref':'WS:ONE','instruction_ref':'INS:DAILY-ONE'}
SOURCE={'repository':'mastermindx-market-intelligence/macro','commit':'a'*40,'path':'agentos/workstreams/WS-ONE.md','content_sha256':'b'*64}
COMMAND='mmos-instruction-pause-'+'1'*40


def receipt():return {'schema':wire.RECEIPT_SCHEMA,**SELECTED,'revision':'c'*64,'source':SOURCE,'command_id':COMMAND,'state':'PAUSED','event_id':1,'request_digest':'d'*64,'committed_at_ms':0}


def control():return {'schema':wire.CONTROL_SCHEMA,'selection':SELECTED,'availability':'AVAILABLE','state':'PAUSED','source':{**SOURCE,'commit':'e'*40},'instruction_revision':'f'*64,'permission':{'pause':True},'owner_context':{'principal_scope':'a'*64},'current_receipt':receipt(),'reason_codes':[]}


def test_current_revision_and_historical_pause_receipt_are_deliberately_distinct():
    body=control();assert wire.validate_control(body,SELECTED)==body
    body['current_receipt']['command_id']='an-original-private-runtime-command';assert wire.validate_control(body,SELECTED)==body
    unavailable=wire.unavailable(SELECTED);assert unavailable['source'] is None and unavailable['current_receipt'] is None
    identity={'principal_scope':'f'*64}
    assert wire.unavailable(SELECTED,'INSTRUCTION_NOT_SUPPLIED',owner_context=identity)['owner_context']==identity
    with pytest.raises(ValueError):wire.unavailable(SELECTED,'ACCESS_DENIED',owner_context=identity)


@pytest.mark.parametrize('mutation',[lambda b:b.update(permissions={'pause':True}),lambda b:b['permission'].update(resume=True),lambda b:b['permission'].update(pause=False),lambda b:b.update(state='RUNNING'),lambda b:b['owner_context'].update(principal='caller'),lambda b:b['current_receipt'].update(instruction_ref='INS:OTHER'),lambda b:b['current_receipt'].update(event_id=2**53),lambda b:b['current_receipt'].update(committed_at_ms=True),lambda b:b['source'].update(path='agentos/workstreams/WS-OTHER.md'),lambda b:b['selection'].update(instruction_ref='INS:BAD\n')])
def test_closed_current_body_rejects_foreign_unsafe_or_authority_invented_facts(mutation):
    body=copy.deepcopy(control());mutation(body)
    with pytest.raises(ValueError):wire.validate_control(body,SELECTED)


@pytest.mark.parametrize('mode,state',[('pause','COMMITTED'),('pause','NOT_DISPATCHED'),('pause','EFFECT_UNKNOWN'),('status','OBSERVED'),('status','NOT_OBSERVED'),('status','UNAVAILABLE')])
def test_all_finite_results_remain_distinct(mode,state):
    selected={**SELECTED,'command_id':COMMAND};found=state in {'COMMITTED','OBSERVED'}
    reasons=[] if found or state=='NOT_OBSERVED' else [wire.UNKNOWN if state=='EFFECT_UNKNOWN' else 'SOURCE_UNAVAILABLE']
    body={'schema':wire.ACTION_SCHEMA if mode=='pause' else wire.STATUS_SCHEMA,'selection':selected,'disposition' if mode=='pause' else 'state':state,'receipt':receipt() if found else None,'reason_codes':reasons}
    assert wire.validate_result(body,selected,status=mode=='status')==body
    body['receipt']=receipt() if not found else None
    with pytest.raises(ValueError):wire.validate_result(body,selected,status=mode=='status')


def test_wire_frames_are_closed_and_duplicate_keys_never_decode():
    frame={'schema':wire.CONTROL_FRAME_SCHEMA,'operation':wire.OPERATIONS['current'],'selection':SELECTED,'principal':principal(fixture()[1]),'admission_expires_at':1000}
    assert wire.decode_frame(json.dumps(frame).encode())==frame
    raw=json.dumps(frame).replace('"operation":','"operation":"forged","operation":').encode()
    with pytest.raises(ValueError):wire.decode_frame(raw)
    for changed in [{**frame,'url':'https://foreign'}, {**frame,'admission_expires_at':float('nan')},{**frame,'selection':{**SELECTED,'root_job_id':'JOB-001'}}]:
        with pytest.raises(ValueError):wire.validate_frame(changed)
