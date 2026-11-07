"""Closed public Memory locator retained by Runtime; grants no source authority."""
import json
import re

SCHEMA = 'mastermind.native_memory_runtime_intent.v1'
_IDS = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z', re.ASCII)

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')

def normalize_memory_runtime_intent(value):
    # These are untrusted correlation values retained on the admitted Job.
    # Linux's independently enrolled recipient grant must match every value.
    if (type(value) is not dict or set(value) != {'schema', 'operation_id', 'intent'}
            or type(value['schema']) is not str or value['schema'] != SCHEMA
            or type(value['operation_id']) is not str or not _IDS.fullmatch(value['operation_id'])):
        raise ValueError('native_memory_intent_invalid')
    intent = value['intent']
    keys = {'study_id', 'root_id', 'operator_run_id', 'child_run_id'}
    if type(intent) is not dict or set(intent) != keys:
        raise ValueError('native_memory_intent_invalid')
    for key in keys:
        if type(intent[key]) is not str or not _IDS.fullmatch(intent[key]):
            raise ValueError('native_memory_intent_invalid')
    return json.loads(_canonical(value))
