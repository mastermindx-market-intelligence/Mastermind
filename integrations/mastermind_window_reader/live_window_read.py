"""Bounded viewer of an existing managed-turn owner; not a history or auth store.

The application owner supplies an exact-bound read operation and synchronous
content classifier. This module never constructs a provider/owner or mints a
reader grant. Every call produces a finite observed-window view, not a globally
atomic transcript snapshot. Native identifiers and cursors stay inside it.
"""
from __future__ import annotations
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
from control_plane.visible_turn_projection import ReadResult, VisibleItem, ProjectionError

SCHEMA='mastermind.workspace.visible_window_candidate.v1'
REF=re.compile(r'\Amanaged-window:[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z')
HEX=re.compile(r'\A[0-9a-f]{64}\Z')
MAX_BYTES=1_200_000
MAX_SAFE_INTEGER=2**53-1
class WindowError(ValueError):pass

def require(ok,code):
    if not ok:raise WindowError(code)

def stamp(value):
    require(isinstance(value,str) and len(value)<=50,'TIME_INVALID')
    try:require(datetime.fromisoformat(value.replace('Z','+00:00')).tzinfo is not None,'TIME_INVALID')
    except (ValueError,TypeError):raise WindowError('TIME_INVALID') from None
    return value

def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()

@dataclass(frozen=True)
class ContentDecision:
    """A decision from the configured content owner, not model/caller metadata."""
    kind: str
    text: str | None
    representation: str

class WindowReader:
    def __init__(self,*,read_page,source_ref,expected_scope,classify,now,page_size=64,max_pages=8):
        if not all(callable(x) for x in (read_page,classify,now)):raise TypeError('existing read and content owners required')
        require(isinstance(source_ref,str) and REF.fullmatch(source_ref) and '..' not in source_ref,'SOURCE_INVALID')
        require(type(expected_scope) is tuple and len(expected_scope)==2 and all(type(x) is str and 0<len(x)<=256 for x in expected_scope),'SCOPE_INVALID')
        require(type(page_size) is int and 1<=page_size<=64 and type(max_pages) is int and 1<=max_pages<=16,'BOUND_INVALID')
        self._read=read_page;self._classify=classify;self._ref=source_ref;self._scope=expected_scope
        self._now=now;self._size=page_size;self._pages=max_pages

    async def read(self)->bytes:
        # No data survives this request. The source read must already bind the
        # full TurnKey and current grant; retained_scope is an extra consistency check.
        cursor=None;epoch=None;terminal=False;items={};gaps=set();coverage='OBSERVED_WINDOW'
        for index in range(self._pages):
            try:p=await self._read(cursor,self._size)
            except ProjectionError:raise WindowError('SOURCE_READ_REFUSED') from None
            require(isinstance(p,ReadResult) and p.retained_scope==self._scope,'SCOPE_MISMATCH')
            require(type(p.terminal) is bool and type(p.resync_required) is bool,'SOURCE_INVALID')
            require(type(p.publication_epoch) is str and 0<len(p.publication_epoch)<=256,'EPOCH_INVALID')
            if epoch is None:epoch=p.publication_epoch
            require(epoch==p.publication_epoch,'EPOCH_CHANGED')
            require(type(p.items) is tuple and len(p.items)<=self._size,'SOURCE_BOUND')
            require(type(p.gaps) is tuple and len(p.gaps)<=256,'GAP_BOUND')
            require(type(p.next_cursor) is str and 0<len(p.next_cursor)<=2048,'CURSOR_INVALID')
            if terminal:require(p.terminal,'TERMINAL_REGRESSED')
            terminal=p.terminal
            for gap in p.gaps:
                require(type(gap.from_publication_sequence) is int and type(gap.to_publication_sequence) is int and
                        0<=gap.from_publication_sequence<=gap.to_publication_sequence<=MAX_SAFE_INTEGER,'GAP_INVALID')
                # The reason is source text; only a fixed user-facing code escapes.
                gaps.add((gap.from_publication_sequence,gap.to_publication_sequence))
            require(len(gaps)<=256,'GAP_BOUND')
            if p.resync_required and not p.gaps:raise WindowError('SOURCE_RESYNC_REQUIRED')
            for item in p.items:
                require(isinstance(item,VisibleItem) and type(item.source_item_id) is str and 0<len(item.source_item_id)<=256,'ITEM_INVALID')
                require(type(item.source_sequence) is int and 0<=item.source_sequence<=MAX_SAFE_INTEGER and
                        type(item.publication_sequence) is int and 0<item.publication_sequence<=MAX_SAFE_INTEGER,'ORDER_INVALID')
                require(item.state in ('partial','completed') and type(item.text) is str,'ITEM_INVALID')
                try:n=len(item.text.encode('utf-8'))
                except UnicodeError:raise WindowError('TEXT_INVALID') from None
                require(type(item.byte_length) is int and item.byte_length==n and n<=16384,'ITEM_BOUND')
                old=items.get(item.source_item_id)
                if old:
                    if item.publication_sequence<old.publication_sequence:raise WindowError('SOURCE_ORDER_REGRESSED')
                    if item.publication_sequence==old.publication_sequence:require(item==old,'ITEM_CONFLICT')
                items[item.source_item_id]=item
                require(len(items)<=256,'WINDOW_BOUND')
            if not p.items:break
            require(p.next_cursor!=cursor,'CURSOR_STALLED')
            cursor=p.next_cursor
        else:coverage='READ_LIMIT_REACHED'
        if gaps:coverage='GAP_PRESENT'
        public=[];total=0
        for item in sorted(items.values(),key=lambda i:(i.source_sequence,i.publication_sequence)):
            decision=self._classify(item)
            require(type(decision) is ContentDecision,'CONTENT_DECISION_REQUIRED')
            require(decision.kind in ('visible-response','withheld'),'CONTENT_KIND_REFUSED')
            if decision.kind=='withheld':
                require(decision.text is None and decision.representation=='WITHHELD','CONTENT_DECISION_INVALID')
                text=None;h=None
            else:
                require(type(decision.text) is str and decision.representation in ('VISIBLE_TEXT','FILTERED_VISIBLE_TEXT'),'CONTENT_DECISION_INVALID')
                require(decision.representation!='VISIBLE_TEXT' or decision.text==item.text,'FALSE_VERBATIM')
                text=decision.text
                try:n=len(text.encode('utf-8'))
                except UnicodeError:raise WindowError('TEXT_INVALID') from None
                total+=n;require(n<=16384 and total<=1048576,'TEXT_BOUND');h=digest(text)
            # Display keys derive from the existing source identity; not a new registry.
            key=digest(self._ref+'\0'+epoch+'\0'+item.source_item_id)
            public.append(dict(id='visible:'+key,source_sequence=item.source_sequence,
                publication_sequence=item.publication_sequence,state=item.state,kind=decision.kind,
                text=text,representation=decision.representation,display_sha256=h))
        result=dict(schema=SCHEMA,source_ref=self._ref,scope='one-managed-turn-window',
            observed_at=stamp(self._now()),epoch=digest(epoch),terminal=terminal,
            coverage=coverage,history='NOT_PROVEN',acceptance='NOT_PROJECTED',
            capabilities={'send':False,'provider_control':False,'history':False},items=public,
            gaps=[dict(first=a,last=b,reason='SOURCE_REPORTED_GAP') for a,b in sorted(gaps)])
        clean=project_window(result)
        raw=json.dumps(clean,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
        require(len(raw)<=MAX_BYTES,'RESPONSE_BOUND')
        return raw

def project_window(value:dict)->dict:
    """Strict wire validation, not an authority or source-authentication decision."""
    keys={'schema','source_ref','scope','observed_at','epoch','terminal','coverage','history','acceptance','capabilities','items','gaps'}
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA,'WINDOW_SCHEMA')
    require(type(value['source_ref']) is str and REF.fullmatch(value['source_ref']) and '..' not in value['source_ref'],'SOURCE_INVALID')
    require(value['scope']=='one-managed-turn-window' and value['history']=='NOT_PROVEN' and value['acceptance']=='NOT_PROJECTED','CLAIM_REFUSED')
    stamp(value['observed_at']);require(type(value['epoch']) is str and HEX.fullmatch(value['epoch']),'EPOCH_INVALID')
    require(type(value['terminal']) is bool and value['coverage'] in ('OBSERVED_WINDOW','READ_LIMIT_REACHED','GAP_PRESENT'),'COVERAGE_INVALID')
    require(type(value['capabilities']) is dict and set(value['capabilities'])=={'send','provider_control','history'} and
            all(v is False for v in value['capabilities'].values()),'CAPABILITY_REFUSED')
    require(type(value['items']) is list and len(value['items'])<=256,'ITEM_BOUND')
    ids=set();total=0
    for i in value['items']:
        require(type(i) is dict and set(i)=={'id','source_sequence','publication_sequence','state','kind','text','representation','display_sha256'},'ITEM_INVALID')
        require(type(i['id']) is str and re.fullmatch(r'visible:[0-9a-f]{64}',i['id']) and i['id'] not in ids,'ITEM_ID_INVALID');ids.add(i['id'])
        require(type(i['source_sequence']) is int and 0<=i['source_sequence']<=MAX_SAFE_INTEGER and type(i['publication_sequence']) is int and 0<i['publication_sequence']<=MAX_SAFE_INTEGER,'ORDER_INVALID')
        require(i['state'] in ('partial','completed') and i['kind'] in ('visible-response','withheld'),'ITEM_INVALID')
        if i['kind']=='withheld':require(i['text'] is None and i['display_sha256'] is None and i['representation']=='WITHHELD','CONTENT_REFUSED')
        else:
            require(type(i['text']) is str and i['representation'] in ('VISIBLE_TEXT','FILTERED_VISIBLE_TEXT'),'CONTENT_INVALID')
            try:n=len(i['text'].encode('utf-8'))
            except UnicodeError:raise WindowError('TEXT_INVALID') from None
            total+=n;require(n<=16384 and total<=1048576 and i['display_sha256']==digest(i['text']),'TEXT_BOUND')
    require(type(value['gaps']) is list and len(value['gaps'])<=256,'GAP_BOUND')
    for g in value['gaps']:
        require(type(g) is dict and set(g)=={'first','last','reason'} and g['reason']=='SOURCE_REPORTED_GAP' and
                type(g['first']) is int and type(g['last']) is int and 0<=g['first']<=g['last']<=MAX_SAFE_INTEGER,'GAP_INVALID')
    require(not value['gaps'] or value['coverage']=='GAP_PRESENT','COVERAGE_INVALID')
    # Isolate the validated plain representation from caller mutation.
    return json.loads(json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')))
