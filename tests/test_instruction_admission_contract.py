"""Pure receipt/source law; an event shape never proves persisted commit."""
import copy
import json
import pytest
from control_plane import instruction_admission_contract as law
from common.executive_workspace_contract import canonical

SOURCE={'repository':'mastermindx-market-intelligence/macro','commit':'a'*40,'path':'agentos/workstreams/WS:WRONG.md','content_sha256':'b'*64}
SOURCE['path']='agentos/workstreams/WS-PROJECT-ONE.md'

def request(**changes):
    values=dict(work_ref='WS:PROJECT-ONE',instruction_ref='INS:DAILY-ONE',revision='c'*64,source=copy.deepcopy(SOURCE),command_id='pause-original',actor='workspace:'+'d'*64)
    values.update(changes);return law.make_pause_request(**values)

def event():
    value=request();return {'event_id':1,'aggregate_type':'workstream_instruction','aggregate_id':'WS:PROJECT-ONE/INS:DAILY-ONE',
        'event_type':'WORKSTREAM_INSTRUCTION_ADMISSION_SUSPENDED','command_id':value['command_id'],'actor':value['actor'],
        'payload_json':canonical(law.make_pause_payload(value)).decode(),'created_at_ms':0}


def test_stable_identity_and_full_request_fingerprint_without_text_or_authority():
    value=request();other=request(revision='f'*64)
    assert law.aggregate_identity(value['work_ref'],value['instruction_ref'])==law.aggregate_identity(other['work_ref'],other['instruction_ref'])
    assert law.request_digest(value)!=law.request_digest(other)
    receipt=law.parse_suspension_event(event());assert receipt['state']=='PAUSED' and receipt['revision']==value['revision']
    assert not {'text','actor','active','permission'}&set(receipt)
    value['source']['commit']='f'*40;assert law.parse_suspension_event(event())['source']['commit']=='a'*40


@pytest.mark.parametrize('field,bad',[('work_ref','WS:PROJECT-ONE\n'),('work_ref','WS:lower'),('instruction_ref','INS:ONE\n'),('instruction_ref','INS:X'),
    ('revision','c'*64+'\n'),('revision',True),('actor','x\n'),('command_id','x\n'),('source',{**SOURCE,'commit':'A'*40}),('source',{**SOURCE,'path':'/private/source'})])
def test_changed_or_malformed_selectors_fail_closed(field,bad):
    with pytest.raises(ValueError,match='^INSTRUCTION_SUSPENSION_INVALID$'):request(**{field:bad})


@pytest.mark.parametrize('field,bad',[('event_id',True),('event_id',0),('created_at_ms',False),('created_at_ms',-1),('aggregate_type','workstream'),
    ('aggregate_id','WS:OTHER/INS:DAILY-ONE'),('event_type','UNKNOWN'),('actor','another-principal'),('command_id','another-command'),('payload_json','{}'),('payload_json','x'*4097)])
def test_foreign_or_incomplete_events_never_become_receipts(field,bad):
    value=event();value[field]=bad
    with pytest.raises(ValueError,match='^INSTRUCTION_SUSPENSION_INVALID$'):law.parse_suspension_event(value)


@pytest.mark.parametrize('change',['revision','digest','extra','duplicate','spacing','nan','schema','state'])
def test_closed_canonical_event_payload(change):
    value=event();payload=json.loads(value['payload_json'])
    if change=='revision':payload['revision']='f'*64
    elif change=='digest':payload['request_digest']='f'*64
    elif change=='extra':payload['text']='private instruction text'
    elif change=='schema':payload['schema']='another'
    elif change=='state':payload['state']='RESUMED'
    if change=='duplicate':value['payload_json']=value['payload_json'][:-1]+',"state":"PAUSED"}'
    elif change=='spacing':value['payload_json']=json.dumps(payload)
    elif change=='nan':value['payload_json']='{"schema":NaN}'
    else:value['payload_json']=canonical(payload).decode()
    with pytest.raises(ValueError):law.parse_suspension_event(value)
