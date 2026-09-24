#!/usr/bin/env python3
"""Offline read-consumer for an already-filtered native-lane capture.

No provider, filesystem browser, shell, credential, network or lifecycle access.
Checks here enforce this document's shape/identity, not source authenticity or
current authorization. Use the existing source/auth owners for a hosted product.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA='mastermind.workspace_native_lane_capture_candidate.v1'
MAX_INPUT=1_500_000
MAX_TEXT=262_144
MAX_TOTAL=1_048_576
ROOT=Path(__file__).resolve().parent/'static'
SHA=re.compile(r'\A[0-9a-f]{64}\Z')
GIT_SHA=re.compile(r'\A[0-9a-f]{40}\Z')
LANE=re.compile(r'\A[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z')
CODE=re.compile(r'\A[A-Z][A-Z0-9_]{0,100}\Z')
REPOS={'macro':'mastermindx-market-intelligence/macro','terminal':'mastermindx-market-intelligence/mastermind-terminal'}

class CaptureError(ValueError):
    """Safe, fixed-code input error; never interpolate private input into it."""

def require(ok: bool, reason: str) -> None:
    if not ok: raise CaptureError(reason)

def string(v: Any, limit=256, nullable=False) -> str|None:
    if v is None and nullable: return None
    require(isinstance(v,str) and len(v)<=limit,'TEXT_FIELD_INVALID')
    require(not any(ord(c)<32 or 0xD800<=ord(c)<=0xDFFF for c in v),'TEXT_FIELD_INVALID')
    return v

def digest(v: Any, git=False, nullable=False) -> str|None:
    if v is None and nullable: return None
    require(isinstance(v,str) and bool((GIT_SHA if git else SHA).fullmatch(v)),'DIGEST_INVALID')
    return v

def timestamp(v: Any, nullable=False) -> str|None:
    if v is None and nullable: return None
    string(v,50)
    try: require(datetime.fromisoformat(v.replace('Z','+00:00')).tzinfo is not None,'TIME_INVALID')
    except ValueError: raise CaptureError('TIME_INVALID') from None
    return v

def codes(v: Any) -> list[str]:
    require(isinstance(v,list) and len(v)<=64,'ISSUES_INVALID')
    require(all(isinstance(x,str) and CODE.fullmatch(x) for x in v),'ISSUES_INVALID')
    return list(v)

def review(v: Any) -> dict|None:
    if v is None:return None
    require(isinstance(v,dict),'REVIEW_INVALID')
    require(v.get('reported_verdict') in ('PASS','FIX_REQUIRED','NO_REVIEW','UNKNOWN'),'REVIEW_INVALID')
    require(v.get('company_acceptance')=='NOT_ESTABLISHED','ACCEPTANCE_CANNOT_BE_PROMOTED')
    out={k:v[k] for k in ('reported_verdict','company_acceptance')}
    for k in ('blocker_count','major_count','minor_count'):
        require(type(v.get(k)) is int and 0<=v[k]<=64,'FINDING_COUNT_INVALID');out[k]=v[k]
    for k in ('checked_head','recorded_head_now'):out[k]=digest(v.get(k),git=True,nullable=True)
    out['issues']=codes(v.get('issues',[]))
    alias=v.get('final_alias')
    require(alias is None or alias in ('NOT_RECORDED','MATCHES_LAST_ROUND','DISAGREES_WITH_LAST_ROUND'),'ALIAS_INVALID')
    out['final_alias']=alias
    return out

def load_capture(raw: bytes) -> dict:
    require(isinstance(raw,bytes) and 0<len(raw)<=MAX_INPUT,'INPUT_BOUND')
    def pairs(entries):
        d={}
        for k,v in entries:
            require(k not in d,'DUPLICATE_JSON_KEY');d[k]=v
        return d
    def bad_constant(value):raise CaptureError('NONFINITE_JSON')
    try:d=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=bad_constant)
    except (UnicodeError,json.JSONDecodeError,RecursionError):raise CaptureError('JSON_INVALID') from None
    require(isinstance(d,dict),'OBJECT_REQUIRED')
    return d

def project_capture(c: dict) -> dict:
    require(isinstance(c,dict) and c.get('schema')==SCHEMA,'SCHEMA_UNSUPPORTED')
    require(c.get('authority')=='OBSERVATION_ONLY' and c.get('scope')=='one-explicit-native-lane','SCOPE_INVALID')
    caps=c.get('capabilities')
    require(isinstance(caps,dict) and set(caps)=={'send','live_stream','provider_control'}
            and all(caps[k] is False for k in caps),'CAPABILITY_UNSUPPORTED')
    lane=c.get('lane');require(isinstance(lane,dict),'LANE_INVALID')
    label=lane.get('label');require(isinstance(label,str) and LANE.fullmatch(label) and '..' not in label,'LANE_INVALID')
    ref='native-lane:'+label;require(lane.get('ref')==ref,'LANE_REF_INVALID')
    repo=lane.get('repo');require(isinstance(repo,str) and repo in REPOS and lane.get('repository')==REPOS[repo],'REPO_INVALID')
    require(type(lane.get('pr')) is int and 0<lane['pr']<10_000_000,'PR_INVALID')
    require(lane.get('executive_job_id') is None and lane.get('responsibility_ref') is None,'UNSUPPORTED_IDENTITY_JOIN')
    branch=string(lane.get('branch'),200)
    require(re.fullmatch(r'[A-Za-z0-9_./-]+',branch) and '..' not in branch and not branch.startswith('/'),'BRANCH_INVALID')
    v={'schema':SCHEMA,'authority':'OBSERVATION_ONLY','scope':c['scope'],'captured_at':timestamp(c.get('captured_at')),
       'lane':{'ref':ref,'label':label,'repo':repo,'repository':REPOS[repo],'pr':lane['pr'],'branch':branch,
               'head_before':digest(lane.get('head_before'),git=True),'executive_job_id':None,'responsibility_ref':None},
       'capabilities':{'send':False,'live_stream':False,'provider_control':False},'items':[],'relations':[],
       'review':review(c.get('review'))}
    items=c.get('items');require(isinstance(items,list) and len(items)<=16,'ITEM_BOUND')
    ids=set();rounds=set();allowed_edges=set();total=0
    for i in items:
        require(isinstance(i,dict),'ITEM_INVALID')
        n=i.get('round');stage=i.get('stage')
        require(type(n) is int and 1<=n<=99 and stage in ('fix','review'),'ITEM_ID_INVALID')
        rref=ref+f':round:{n}';key=rref+':'+stage
        require(i.get('id')==key and key not in ids,'ITEM_ID_CONFLICT');ids.add(key);rounds.add(n)
        allowed_edges.add((ref,rref,'RECORDED_ROUND'));allowed_edges.add((rref,key,'RECORDED_OUTPUT'))
        state=i.get('state');require(state in ('READABLE','UNAVAILABLE','WITHHELD'),'ITEM_STATE_INVALID')
        coverage=i.get('coverage');require(isinstance(coverage,dict),'COVERAGE_INVALID')
        require(coverage.get('file') in ('COMPLETE_FILE','NOT_ESTABLISHED'),'COVERAGE_INVALID')
        require(coverage.get('capture_truncation') in ('REPORTED_NOT_TRUNCATED','REPORTED_TRUNCATED','NOT_ESTABLISHED'),'COVERAGE_INVALID')
        require(coverage.get('provider_history')=='NOT_ESTABLISHED','HISTORY_NOT_PROVEN')
        require(i.get('provider_session_id') is None and i.get('provider_model') is None,'PROVIDER_NOT_PROVEN')
        text=None;display_hash=None;rep=i.get('representation')
        if state=='READABLE':
            text=i.get('text');require(isinstance(text,str),'BODY_INVALID')
            try: body=text.encode('utf-8')
            except UnicodeError:raise CaptureError('BODY_ENCODING_INVALID') from None
            require(len(body)<=MAX_TEXT,'BODY_BOUND');total+=len(body);require(total<=MAX_TOTAL,'TOTAL_BODY_BOUND')
            display_hash=digest(i.get('display_sha256'))
            require(hashlib.sha256(body).hexdigest()==display_hash,'BODY_DIGEST_MISMATCH')
            require(rep in ('RECORDED_TEXT','FILTERED_RECORDED_TEXT'),'REPRESENTATION_INVALID')
        else:rep='WITHHELD' if state=='WITHHELD' else None
        source=i.get('source');out_source=None
        if source is not None:
            require(isinstance(source,dict),'SOURCE_INVALID')
            require(source.get('ref')==ref+f'/r{n}_{stage}.out.md','SOURCE_REF_INVALID')
            require(type(source.get('bytes')) is int and 0<=source['bytes']<=MAX_TEXT,'SOURCE_BOUND')
            require(source.get('stable_during_read') is True and source.get('complete_file') is True,'SOURCE_CAPTURE_INVALID')
            out_source={'ref':source['ref'],'sha256':digest(source.get('sha256')),'bytes':source['bytes'],
                        'mtime':timestamp(source.get('mtime')),'stable_during_read':True,'complete_file':True}
        require(state!='READABLE' or out_source is not None,'SOURCE_REQUIRED')
        rc=i.get('reported_exit_code');require(rc is None or type(rc) is int and -255<=rc<=255,'EXIT_INVALID')
        item={'id':key,'round':n,'stage':stage,'title':'Builder output' if stage=='fix' else 'Reviewer output',
              'state':state,'text':text,'representation':rep,'display_sha256':display_hash,'source':out_source,
              'provider_model':None,'provider_session_id':None,'ended_at':timestamp(i.get('ended_at'),nullable=True),
              'reported_exit_code':rc,'coverage':{k:coverage[k] for k in ('file','capture_truncation','provider_history')},
              'issues':codes(i.get('issues',[]))}
        if 'review' in i:
            item['review']=review(i['review'])
            if item['review'] and item['review']['checked_head']:
                allowed_edges.add((key,'git:'+repo+':'+item['review']['checked_head'],'REVIEW_TARGET'))
        v['items'].append(item)
    require(len(rounds)<=8,'ROUND_BOUND')
    rels=c.get('relations');require(isinstance(rels,list) and len(rels)<=48,'RELATION_BOUND')
    seen=set()
    for e in rels:
        require(isinstance(e,dict) and e.get('basis')=='NATIVE_LANE_RECORD','RELATION_INVALID')
        key=(e.get('from'),e.get('to'),e.get('kind'))
        require(all(isinstance(x,str) for x in key) and key in allowed_edges and key not in seen,'RELATION_INVALID');seen.add(key)
        v['relations'].append({k:e[k] for k in ('from','to','kind','basis')})
    return v

def _b64hash(text: str) -> str:
    return base64.b64encode(hashlib.sha256(text.encode('utf-8')).digest()).decode('ascii')

def render_capture(raw: bytes) -> str:
    v=project_capture(load_capture(raw))
    v['capture_sha256']=hashlib.sha256(raw).hexdigest()
    return _render_document(v)

def render_connection_shell() -> str:
    """Public shell has no source content, reference, credential or endpoint."""
    return _render_document({'reader_bootstrap':'no-source'})

def _render_document(v: dict) -> str:
    data=json.dumps(v,ensure_ascii=True,allow_nan=False,separators=(',',':'))
    # A data block must never be escapable by a malicious captured </script>.
    data=data.replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e')
    css=(ROOT/'reader.css').read_text('utf-8');js=(ROOT/'reader.js').read_text('utf-8')
    shell=(ROOT/'reader.html').read_text('utf-8')
    policy="default-src 'none'; connect-src 'none'; img-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; script-src 'sha256-"+_b64hash(js)+"'; style-src 'sha256-"+_b64hash(css)+"'"
    values={'@@POLICY@@':policy,'@@CSS@@':css,'@@DATA@@':data,'@@JS@@':js}
    # One pass over the trusted template: markers in captured content are data.
    result=re.sub(r'@@(?:POLICY|CSS|DATA|JS)@@',lambda match:values[match.group()],shell)
    require(len(result.encode())<=2_000_000,'DOCUMENT_BOUND')
    return result

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    try:
        with args.capture.open('rb') as f:raw=f.read(MAX_INPUT+1)
        page=render_capture(raw)
        with args.output.open('x',encoding='utf-8') as f:f.write(page)
    except (CaptureError,OSError) as exc:
        print(json.dumps({'result':'REFUSED','reason':str(exc) if isinstance(exc,CaptureError) else 'LOCAL_FILE_OPERATION_FAILED'}))
        return 2
    print(json.dumps({'result':'GENERATED_READ_ONLY_CAPTURE','bytes':len(page.encode()),'sha256':hashlib.sha256(page.encode()).hexdigest()}))
    return 0

if __name__=='__main__':raise SystemExit(main())
