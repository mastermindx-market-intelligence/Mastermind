"""Closed read DTO for source-backed project journals.

Owned implementation from the pre-dispatch interface. The refused Fabric
artifact export is not an input to this module and is not accepted evidence.
"""
from __future__ import annotations
import datetime as dt
import json
import re

BODY_SCHEMA = 'mastermind.workspace_project_journal.v1'
FRAME_SCHEMA = 'mastermind.workspace_project_journal_read.v1'
OPERATION = 'project_journal'
MAX_RESPONSE_BYTES = 131072
REPOSITORY = 'mastermindx-market-intelligence/macro'
REASON_CODES = ('SOURCE_UNAVAILABLE','SOURCE_CHANGED','RECORD_NOT_FOUND','RECORD_INVALID','CONTENT_OVER_BUDGET')
_KEY = r'[A-Z0-9]+(?:-[A-Z0-9]+)*'
_BODY_KEYS = {'schema','selection','availability','source','journal','reason_codes'}
_ENTRY_KEYS = {'id','kind','title','why','next_action','actor','recorded_at','time_basis','source'}
_COVER_KEYS = {'state','scanned','matched','omitted','invalid'}


def validate_selection(value):
    if (type(value) is not dict or set(value) != {'work_ref'}
            or type(value['work_ref']) is not str or not value['work_ref'].startswith('WS:')
            or not 2 <= len(value['work_ref'][3:]) <= 64
            or re.fullmatch(_KEY, value['work_ref'][3:]) is None):
        raise ValueError('invalid_input')
    return dict(value)


def _require(condition):
    if not condition: raise ValueError('invalid_project_journal')


def _hex(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',value) is not None


def _text(value, limit=4096):
    return type(value) is str and bool(value.strip()) and len(value)<=limit


def _date(value):
    if type(value) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}',value) is None: return False
    try: return dt.date.fromisoformat(value).isoformat()==value
    except ValueError: return False


def _timestamp(value):
    if (type(value) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})',value) is None): return False
    try: return dt.datetime.fromisoformat(value.replace('Z','+00:00')).utcoffset() is not None
    except ValueError: return False


def _count(value):
    return type(value) is int and 0<=value<=9007199254740991


def validate_source(value):
    _require(type(value) is dict and set(value)=={'repository','commit'})
    _require(value['repository']==REPOSITORY and _hex(value['commit'],40))
    return dict(value)


def unavailable(work_ref, reason):
    selected=validate_selection({'work_ref':work_ref})
    if type(reason) is not str or reason not in REASON_CODES: raise ValueError('invalid_input')
    return {'schema':BODY_SCHEMA,'selection':selected,'availability':'UNAVAILABLE',
            'source':None,'journal':None,'reason_codes':[reason]}


def _entry(value, origin):
    _require(type(value) is dict and set(value)==_ENTRY_KEYS)
    kind=value['kind']; _require(type(kind) is str and kind in ('DECISION','DISCOVERY','HANDOFF'))
    src=value['source']; _require(type(src) is dict and set(src)=={'repository','commit','path','content_sha256'})
    _require(src['repository']==origin['repository'] and src['commit']==origin['commit'] and _hex(src['content_sha256'],64))
    path=src['path']; _require(type(path) is str)
    patterns={'DECISION':('DEC','decisions/DEC-',_KEY),'DISCOVERY':('DSC','discoveries/DSC-',_KEY),
              'HANDOFF':('HND','handoffs/',r'[A-Za-z0-9_-]+')}
    prefix,folder,key_pattern=patterns[kind]
    match=re.fullmatch('agentos/'+folder+'('+key_pattern+r')\.md',path)
    _require(match is not None)
    _require(value['id']==prefix+':'+match.group(1) and _text(value['title']))
    _require(value['why'] is None or _text(value['why']))
    _require(value['next_action'] is None or _text(value['next_action']))
    _require(value['actor'] is None or _text(value['actor'],256))
    if kind=='DECISION':
        _require(value['why'] is not None and value['actor'] is not None and value['next_action'] is None)
        _require(value['time_basis']=='DECLARED_DECISION_DATE' and _date(value['recorded_at']))
    elif kind=='DISCOVERY':
        _require(value['why'] is not None and value['actor'] is None and value['next_action'] is None)
        _require(value['time_basis']=='DECLARED_VERIFICATION_DATE' and _date(value['recorded_at']))
    else:
        _require(value['why'] is None and value['actor'] is None)
        _require((value['recorded_at'] is None and value['time_basis']=='UNAVAILABLE') or
                 (_timestamp(value['recorded_at']) and value['time_basis']=='GIT_RECORD_COMMIT_TIME'))


def validate_body(value):
    _require(type(value) is dict and set(value)==_BODY_KEYS and value['schema']==BODY_SCHEMA)
    selected=validate_selection(value['selection'])
    if value['availability']=='UNAVAILABLE':
        reasons=value['reason_codes']
        _require(type(reasons) is list and len(reasons)==1 and type(reasons[0]) is str and reasons[0] in REASON_CODES)
        _require(value==unavailable(selected['work_ref'],reasons[0]))
    else:
        _require(value['availability']=='AVAILABLE' and type(value['reason_codes']) is list and not value['reason_codes'])
        origin=validate_source(value['source']); journal=value['journal']
        _require(type(journal) is dict and set(journal)=={'entries','coverage'})
        entries=journal['entries']; coverage=journal['coverage']
        _require(type(entries) is list and len(entries)<=32)
        _require(type(coverage) is dict and set(coverage)==_COVER_KEYS and coverage['state']=='BOUNDED_RECORD_SAMPLE')
        _require(all(_count(coverage[k]) for k in ('scanned','matched','omitted','invalid')))
        _require(coverage['scanned']>=coverage['matched']>=len(entries) and coverage['invalid']<=coverage['scanned'])
        _require(coverage['omitted']>=coverage['matched']-len(entries))
        ids=set()
        for row in entries:
            _entry(row,origin); _require(row['id'] not in ids); ids.add(row['id'])
    try: encoded=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
    except (ValueError,TypeError,OverflowError): raise ValueError('invalid_project_journal') from None
    _require(len(encoded)+1<=MAX_RESPONSE_BYTES)
    return value


def validate_frame(value):
    from common import executive_workspace_contract as workspace
    if (type(value) is not dict or set(value)!={'schema','operation','selection','principal'}
            or value['schema']!=FRAME_SCHEMA or value['operation']!=OPERATION): raise ValueError('invalid_input')
    selected=validate_selection(value['selection'])
    workspace.validate_frame({'schema':workspace.FRAME_SCHEMA,'operation':'programs',
                              'selection':None,'principal':value['principal']})
    if len(workspace.canonical(value))+1>workspace.MAX_REQUEST_BYTES: raise ValueError('invalid_input')
    return dict(value,selection=selected,principal=dict(value['principal'],scopes=list(value['principal']['scopes'])))
