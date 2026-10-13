"""Direct reconstruction proof; no recovered worker patch is used."""
import asyncio
import copy
from dataclasses import replace
import hashlib
import threading

import pytest

from integrations.research_read_mcp.port_adapter import ResearchPortAdapter, FAILURES
from integrations.research_read_mcp.contracts import ContractViolation
from tests.research_read_mcp.test_app import Harness, _result, KNOWN_REPORT
from integrations.research_read_mcp.app import create_authenticated_research_server

@pytest.fixture
def anyio_backend():
    return "asyncio"

SOURCE = {"state":"SOURCE_FRESH", "known_degradation":[], "report_count":2}
TEXT = "成本 change."
RAW = TEXT.encode()
PASSAGE = {"report_id":KNOWN_REPORT, "text":TEXT, "start_byte":3,"end_byte":3+len(RAW),
           "passage_text_sha256":hashlib.sha256(RAW).hexdigest(), "extracted_text_sha256":"c"*64,
           "segment_index":0, "source_pdf_sha256":"d"*64, "open_source_ref":"SECRET-NO-LEAK"}

class Service:
    def __init__(self):
        self.calls=[]; self.evidence={}; self.failure=None; self.side=None
    def observed(self, operation, kwargs):
        self.calls.append((operation,kwargs,threading.get_ident()))
        if self.failure:
            return {"ok":False,"code":self.failure,"message":"SECRET-NO-LEAK"}
    def status(self, **kwargs):
        failure=self.observed("status",kwargs)
        return failure or {"ok":True,"source":dict(SOURCE),"full_text_coverage":0.95,"rio_coverage":0.2}
    def search(self, **kwargs):
        failure=self.observed("search",kwargs)
        return failure or {"ok":True,"available":True,"source":dict(SOURCE),"coverage_state":"PREFIX_ONLY_LEGACY",
                           "candidates":[{"report_id":KNOWN_REPORT,"title":"fixture","institution":"Bank",
                                          "side":self.side,"published_at":None,"rank":1}]}
    def fetch(self, **kwargs):
        failure=self.observed("fetch",kwargs)
        start=kwargs['selectors']['segment_start']
        return failure or {"ok":True,"available":True,"source":dict(SOURCE),
                           "report":{"title":"fixture","institution":"Bank","side":"sell","published_at":"2026-10-12"},
                           "coverage_state":"FULL_TEXT","text_layer_state":"full","rio_state":"CURRENT","segment_count_total":2,
                           "text_revision":{"SECRET-NO-LEAK":"same producer revision"},
                           "segments":[] if start>=2 else [{"segment_index":start,"page_start":1,"page_end":1,
                                           "start_byte":start*len(RAW),"end_byte":(start+1)*len(RAW),"text":TEXT}]}
    def find_evidence(self, **kwargs):
        failure=self.observed("find_evidence",kwargs)
        state=self.evidence.get(kwargs['report_id'],"FOUND")
        row=copy.deepcopy(PASSAGE);row['report_id']=kwargs['report_id']
        return failure or {"ok":True,"source":dict(SOURCE),"evidence_state":state,"rio_state":"CURRENT",
                           "passages":[row] if state in {'FOUND','PARTIAL'} else []}

def setup(cap=1200):
    h=Harness();s=Service();a=ResearchPortAdapter(s,lambda digest:cap,'a'*40)
    return h,s,a,a.context_builder(h.full)

@pytest.mark.anyio
async def test_four_closed_projections_and_internal_revision_omitted():
    h,s,a,ctx=setup()
    status=await a('research_status',{},ctx)
    assert status['producer']['last_success_at'] is None and status['producer']['age_seconds'] is None
    search=await a('research_search',{'query':'fixture','from':'2026-01-01','to':'2026-12-31'},ctx)
    assert search['candidates'][0]['side'] is None
    assert s.calls[-1][1]['filters']=={'date_from':'2026-01-01','date_to':'2026-12-31'}
    fetch=await a('research_fetch',{'report_id':KNOWN_REPORT},ctx)
    assert fetch['next_segment_start']==1 and 'text_revision' not in fetch
    assert 'SECRET' not in str(fetch)
    evidence=await a('research_find_evidence',{'claim':'change','report_ids':[KNOWN_REPORT]},ctx)
    assert evidence['outcome']=='FOUND' and evidence['passages'][0]['byte_end']-3==len(RAW)
    assert evidence['passages'][0]['canonical_text_sha256']=='c'*64 and 'SECRET' not in str(evidence)
    assert all(call[2]!=threading.get_ident() for call in s.calls)

@pytest.mark.anyio
@pytest.mark.parametrize('states,outcome', [(['NOT_FOUND','UNAVAILABLE'],'UNAVAILABLE'),(['NOT_FOUND','NOT_FOUND'],'NOT_FOUND'),
                                           (['FOUND','UNAVAILABLE'],'PARTIAL'),(['PARTIAL','NOT_FOUND'],'PARTIAL')])
async def test_fanout_zero_passages_truth_and_order(states,outcome):
    h,s,a,ctx=setup();ids=[KNOWN_REPORT,'rpt-2']
    s.evidence=dict(zip(ids,states))
    result=await a('research_find_evidence',{'claim':'fixture','report_ids':ids,'limit':1},ctx)
    assert result['outcome']==outcome
    assert [c[1]['report_id'] for c in s.calls]==ids

@pytest.mark.anyio
async def test_implicit_bounded_search_never_claims_full_scope():
    h,s,a,ctx=setup();s.evidence[KNOWN_REPORT]='NOT_FOUND'
    assert (await a('research_find_evidence',{'claim':'fixture'},ctx))['outcome']=='UNAVAILABLE'
    s.evidence[KNOWN_REPORT]='FOUND'
    assert (await a('research_find_evidence',{'claim':'fixture'},ctx))['outcome']=='PARTIAL'

@pytest.mark.anyio
@pytest.mark.parametrize('code',list(FAILURES)+['UNKNOWN'])
async def test_total_sanitized_failure_projection(code):
    h,s,a,ctx=setup();s.failure=code
    with pytest.raises(ContractViolation) as error:
        await a('research_status',{},ctx)
    assert error.value.code==FAILURES.get(code,'INTERNAL_ERROR') and 'SECRET' not in str(error.value)

@pytest.mark.anyio
async def test_quote_recheck_before_source_and_concurrent_caller_isolation():
    h,s,a,ctx=setup(3)
    with pytest.raises(ContractViolation,match='NOT_ENTITLED'):
        await a('research_find_evidence',{'claim':'change','report_ids':[KNOWN_REPORT]},ctx)
    s.calls.clear();a.quote_limit=lambda digest:None
    with pytest.raises(ContractViolation,match='NOT_ENTITLED'):
        await a('research_find_evidence',{'claim':'change','report_ids':[KNOWN_REPORT]},ctx)
    assert not s.calls
    a.quote_limit=lambda digest:1200 if digest==ctx.principal_id else 1
    other=replace(ctx,principal_id='e'*64)
    results=await asyncio.gather(a('research_find_evidence',{'claim':'change','report_ids':[KNOWN_REPORT]},ctx),
                                 a('research_find_evidence',{'claim':'change','report_ids':[KNOWN_REPORT]},other),return_exceptions=True)
    assert results[0]['outcome']=='FOUND' and isinstance(results[1],ContractViolation)
    catalog=a.context_builder(h.catalog_only)
    assert catalog.entitlement=='preview' and catalog.scopes==frozenset({'status','search'})
    with pytest.raises(ContractViolation):
        await a('research_fetch',{'report_id':KNOWN_REPORT},catalog)

@pytest.mark.anyio
async def test_real_authenticated_http_four_tools_with_reconstructed_adapter():
    h,s,a,ctx=setup()
    h.app=create_authenticated_research_server(authenticator=h.auth,policy=h.policy,now=lambda:h.clock,audit_sink=h.audit,
          port=a,entitlement_resolver=h._resolver,context_builder=a.context_builder,allowed_hosts=('127.0.0.1','127.0.0.1:*'))
    await h.start()
    try:
        for name,args in [('research_status',{}),('research_search',{'query':'fixture'}),
                          ('research_fetch',{'report_id':KNOWN_REPORT}),('research_find_evidence',{'claim':'change','report_ids':[KNOWN_REPORT]})]:
            payload=_result(await h.call(name,args,token=h.token()))
            assert not payload.get('isError'),payload
    finally:
        await h.stop()
    assert len(s.calls)==4


def test_namespace_collision_refuses_before_factory_or_verifier(tmp_path, monkeypatch):
    import sys,types
    from integrations.research_read_mcp.port_adapter import compose_macro_service
    root=tmp_path.resolve()/('a'*40);root.mkdir()
    calls=[]
    monkeypatch.setitem(sys.modules,'engine',types.ModuleType('engine'))
    with pytest.raises(ContractViolation):
        compose_macro_service(str(root),'a'*40,'b'*40,release_verifier=lambda *x:calls.append(x))
    assert not calls


def test_local_store_configuration_refuses_before_factory(tmp_path,monkeypatch):
    from integrations.research_read_mcp.port_adapter import compose_macro_service
    root=tmp_path.resolve()/('a'*40);root.mkdir()
    monkeypatch.setenv('RESEARCH_LOCAL_STORE',str(tmp_path))
    with pytest.raises(ContractViolation):
        compose_macro_service(str(root),'a'*40,'b'*40,release_verifier=lambda *x:None)


@pytest.mark.anyio
async def test_adapter_uses_same_secure_current_grant_owner_before_passage_read(tmp_path):
    import os
    from integrations.research_read_mcp.runtime import CurrentGrantOwner
    from tests.research_read_mcp.test_runtime import parsed,write_grant
    from tests.research_read_mcp.test_app import CLOCK
    h,s,a,ctx=setup()
    path=tmp_path.resolve()/"grant.json"
    write_grant(path,h.policy.policy_id,ctx.principal_id,quote=1200)
    owner=CurrentGrantOwner(parsed(grant_path=str(path),policy_id=h.policy.policy_id),clock=lambda:CLOCK,owner_uid=os.geteuid())
    a.quote_limit=owner.quote_limit
    assert (await a('research_find_evidence',{'claim':'fixture','report_ids':[KNOWN_REPORT]},ctx))['outcome']=='FOUND'
    s.calls.clear()
    write_grant(path,h.policy.policy_id,ctx.principal_id,expires=CLOCK)
    with pytest.raises(ContractViolation,match='NOT_ENTITLED'):
        await a('research_find_evidence',{'claim':'fixture','report_ids':[KNOWN_REPORT]},ctx)
    assert not s.calls


@pytest.mark.anyio
async def test_cancellation_keeps_still_running_producer_slot_bounded():
    h,s,a,ctx=setup()
    gate=threading.Event()
    original=s.status
    def waiting(**kwargs):
        result=original(**kwargs)
        if not gate.wait(3):raise RuntimeError('synthetic worker timeout')
        return result
    s.status=waiting
    tasks=[asyncio.create_task(a('research_status',{},ctx)) for _ in range(4)]
    try:
        for _ in range(200):
            if len(s.calls)==4:break
            await asyncio.sleep(0.01)
        assert len(s.calls)==4
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):await tasks[0]
        fifth=asyncio.create_task(a('research_status',{},ctx));tasks.append(fifth)
        await asyncio.sleep(0.02)
        assert len(s.calls)==4
    finally:
        gate.set()
        await asyncio.gather(*tasks,return_exceptions=True)
    assert len(s.calls)==5


@pytest.mark.anyio
async def test_current_quote_revocation_between_fanout_reports_stops_next_read():
    h,s,a,ctx=setup();calls=[]
    def current(digest):
        calls.append(digest)
        return 1200 if len(calls)<3 else None
    a.quote_limit=current
    with pytest.raises(ContractViolation,match='NOT_ENTITLED'):
        await a('research_find_evidence',{'claim':'fixture','report_ids':[KNOWN_REPORT,'rpt-2']},ctx)
    assert len(s.calls)==1
