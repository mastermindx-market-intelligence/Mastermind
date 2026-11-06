"""Pure explicit-field projection of already-validated canonical Agent OS records.

No event writer, state store, clock, parser, authority or transport. Implemented
from the original owned interface after an unqualified Fabric artifact export;
no acceptance or provenance is inherited from that refused export.
"""
from __future__ import annotations
import datetime as dt
import json
import re
from common import workspace_project_journal_contract as wire


def _date(value):
    if type(value) is dt.date: return value.isoformat()
    if not wire._date(value): raise ValueError('record_invalid')
    return value


def _text(value, limit=4096):
    if not wire._text(value,limit): raise ValueError('record_invalid')
    return value


def project_journal(records, *, work_ref, source, scanned, omitted=0, invalid=0):
    selected=wire.validate_selection({'work_ref':work_ref})
    try:
        origin=wire.validate_source(source)
        if (type(records) is not list or len(records)>256 or not all(wire._count(x) for x in (scanned,omitted,invalid))
                or scanned<len(records) or invalid>scanned): raise ValueError('record_invalid')
        rows=[]; seen=set()
        for item in records:
            if type(item) is not dict or set(item)!={'kind','record','path','content_sha256','committed_at'}: raise ValueError('record_invalid')
            rec=item['record']; kind=item['kind']; path=item['path']
            if type(rec) is not dict or kind not in ('DECISION','DISCOVERY','HANDOFF'): raise ValueError('record_invalid')
            association=rec.get('workstream') if kind=='HANDOFF' else rec.get('affects' if kind=='DECISION' else 'scope')
            associated=association==work_ref if type(association) is str else type(association) is list and work_ref in association
            if not associated: continue
            if kind=='HANDOFF':
                match=re.fullmatch(r'agentos/handoffs/([A-Za-z0-9_-]+)\.md',path) if type(path) is str else None
                if not match: raise ValueError('record_invalid')
                identifier='HND:'+match.group(1); title=_text(rec.get('mission')); why=actor=None
                actions=rec.get('next_actions',[])
                if type(actions) is not list or actions and type(actions[0]) is not str: raise ValueError('record_invalid')
                next_action=_text(actions[0]) if actions else None
                recorded_at=item['committed_at']
                if recorded_at is not None and not wire._timestamp(recorded_at): raise ValueError('record_invalid')
                time_basis='GIT_RECORD_COMMIT_TIME' if recorded_at is not None else 'UNAVAILABLE'
            else:
                key=rec.get('key')
                if type(key) is not str or re.fullmatch(wire._KEY,key) is None: raise ValueError('record_invalid')
                folder,prefix=('decisions','DEC') if kind=='DECISION' else ('discoveries','DSC')
                if path!=f'agentos/{folder}/{prefix}-{key}.md': raise ValueError('record_invalid')
                identifier=prefix+':'+key; next_action=None
                if kind=='DECISION':
                    title=_text(rec.get('answer')); why=_text(rec.get('rationale')); actor=_text(rec.get('decided_by'),256)
                    recorded_at=_date(rec.get('decided_at')); time_basis='DECLARED_DECISION_DATE'
                else:
                    title=_text(rec.get('claim')); why=_text(rec.get('so_what')); actor=None
                    recorded_at=_date(rec.get('verified_at')); time_basis='DECLARED_VERIFICATION_DATE'
            if identifier in seen: raise ValueError('record_invalid')
            seen.add(identifier)
            row={'id':identifier,'kind':kind,'title':title,'why':why,'next_action':next_action,'actor':actor,
                 'recorded_at':recorded_at,'time_basis':time_basis,'source':dict(origin,path=path,content_sha256=item['content_sha256'])}
            wire._entry(row,origin)
            rows.append(row)
        rows.sort(key=lambda row:(row['recorded_at'] or '',row['id']),reverse=True)
        body={'schema':wire.BODY_SCHEMA,'selection':selected,'availability':'AVAILABLE','source':origin,
              'journal':{'entries':rows[:32],'coverage':{'state':'BOUNDED_RECORD_SAMPLE','scanned':scanned,
               'matched':len(rows),'omitted':omitted+max(0,len(rows)-32),'invalid':invalid}},'reason_codes':[]}
        if len(json.dumps({'ok':True,'result':body},ensure_ascii=False,separators=(',',':')).encode())+1>wire.MAX_RESPONSE_BYTES:
            return wire.unavailable(work_ref,'CONTENT_OVER_BUDGET')
        return wire.validate_body(body)
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):
        return wire.unavailable(work_ref,'RECORD_INVALID')
