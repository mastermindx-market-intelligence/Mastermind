"""Closed inert event/request laws; no host or Runtime is opened."""
import copy
import hashlib
import json

import pytest
from control_plane import workstream_admission_contract as law


def request(): return law.make_pause_request("WS:ONE","pause-original","workspace:test")
def event():
    return {"event_id":7,"aggregate_type":"workstream","aggregate_id":"WS:ONE",
        "event_type":"WORKSTREAM_ADMISSION_SUSPENDED","command_id":"pause-original","actor":"workspace:test",
        "payload_json":json.dumps(law.make_pause_payload(request()),sort_keys=True,separators=(",",":"),ensure_ascii=False),
        "created_at_ms":42}

def invalid(call):
    with pytest.raises(ValueError,match="^WORKSTREAM_SUSPENSION_INVALID$") as error: call()
    assert str(error.value)==law.ERROR


def test_exact_request_hash_and_event_receipt_do_not_infer_authority_or_running_state():
    value=request()
    expected=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    assert law.request_digest(value)==expected
    record=event();receipt=law.parse_suspension_event(record)
    assert receipt=={"schema":law.RECEIPT_SCHEMA,"work_ref":"WS:ONE","state":"PAUSED","event_id":7,
        "command_id":"pause-original","request_digest":expected,"committed_at_ms":42}
    record["aggregate_id"]="WS:OTHER"
    assert receipt["work_ref"]=="WS:ONE"
    assert set(receipt)=={"schema","work_ref","state","event_id","command_id","request_digest","committed_at_ms"}

@pytest.mark.parametrize("value",[None,True,"WS:X","WS:one","WS:ONE\n","WS:ONE/../../private","WS:"+"A"*65])
def test_work_scope_must_be_canonical(value): invalid(lambda:law.canonical_work_ref(value))

@pytest.mark.parametrize("field,value",[("actor",None),("actor","viewer user"),("actor","a"*129),("command_id",True),("command_id","pause-original\n"),("command_id","")])
def test_request_identity_is_explicit_and_bounded(field,value):
    values={"work_ref":"WS:ONE","command_id":"pause-original","actor":"workspace:test"};values[field]=value
    invalid(lambda:law.make_pause_request(**values))

@pytest.mark.parametrize("mutation",["extra","missing","schema","operation"])
def test_digest_cannot_accept_another_request_shape(mutation):
    value=request()
    if mutation=="extra":value["granted"]=True
    elif mutation=="missing":del value["actor"]
    else:value[mutation]="foreign"
    invalid(lambda:law.request_digest(value))
    invalid(lambda:law.make_pause_payload(value))

@pytest.mark.parametrize("field,value",[("event_id",True),("event_id",0),("created_at_ms",False),("created_at_ms",-1),
    ("aggregate_type","job"),("aggregate_id","WS:OTHER"),("event_type","WORKSTREAM_RESUMED"),
    ("command_id","other-command"),("actor","other-actor"),("payload_json",{})])
def test_event_identity_drift_is_not_a_pause_receipt(field,value):
    record=event();record[field]=value;invalid(lambda:law.parse_suspension_event(record))

@pytest.mark.parametrize("mutation",["schema","state","digest","unknown_key","noncanonical","duplicate","nan","oversize"])
def test_payload_is_closed_canonical_bounded_and_value_free_on_failure(mutation):
    record=event();payload=json.loads(record["payload_json"])
    if mutation=="schema":payload["schema"]="foreign"
    elif mutation=="state":payload["state"]="PAUSING"
    elif mutation=="digest":payload["request_digest"]="f"*64
    elif mutation=="unknown_key":payload["private"]="never echo this"
    if mutation=="noncanonical":record["payload_json"]=" "+record["payload_json"]
    elif mutation=="duplicate":record["payload_json"]='{"schema":"duplicate",'+record["payload_json"][1:]
    elif mutation=="nan":record["payload_json"]='{"value":NaN}'
    elif mutation=="oversize":record["payload_json"]='{"private":"'+"漢"*2000+'"}'
    else:record["payload_json"]=json.dumps(payload,sort_keys=True,separators=(",",":"))
    invalid(lambda:law.parse_suspension_event(record))


def test_projection_and_validation_do_not_mutate_caller_inputs():
    value=request();original=copy.deepcopy(value);payload=law.make_pause_payload(value)
    assert value==original
    payload["work_ref"]="WS:CHANGED"
    assert value==original
    record=event();original=copy.deepcopy(record)
    law.parse_suspension_event(record)
    assert record==original
    record["unexpected"]=True
    invalid(lambda:law.parse_suspension_event(record))
