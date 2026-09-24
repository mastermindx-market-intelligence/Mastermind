"""Actual Go offer reader/guard + model quote + quota interpretation + stream.

All credentials, approval inputs and inference output are synthetic. Neither this
fixture nor its resolved rule thresholds grants account/runtime authorization.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import pytest

from engine import provider_subscription_catalog_opencode as offers
from engine import provider_subscription_guard_opencode as guard
from engine.provider_subscription_usage_opencode import parse_opencode_go_usage
from control_plane.provider_model_economics import ApiRateCard
from control_plane.provider_offer_economics import (
    ReviewedApiOffer, TimeBoundRate, quote_temporal_offer, require_current_quote,
)
from control_plane.opencode_go_pooled_transport import AccountChoice, ProviderRequest, OpenCodeGoTransportContractError
from control_plane.opencode_go_stream import stream_single_account

NOW = datetime(2026, 9, 14, 0, 59, 50, tzinfo=timezone.utc)
MODEL = 'deepseek-v4.1-flash'
KEY = 'opencode.' + MODEL
SURFACE = 'opencode_go'
END = '2026-09-14T01:20:00Z'  # Synthetic review lease, not a vendor promise.
PEAK = tuple((d*1440+s,d*1440+e) for d in range(5) for s,e in ((60,240),(360,600)))


def snapshot():
    root = Path(offers.__file__).parents[1] / 'tests/fixtures/opencode_go'
    return offers.Metadata(
        offers.parse_models(json.loads((root/'inventory.json').read_text()), observed_at=NOW.isoformat()),
        offers.parse_terms((root/'terms.mdx').read_text(), observed_at=NOW.isoformat()))


def plan(metadata):
    model = next(m for m in metadata.terms.models if m.model_id == MODEL)
    assert model.protocol == 'openai-chat'
    off, previous = [], 0
    for start,end in PEAK:
        if start > previous:
            off.append((previous,start))
        previous=end
    off.append((previous,10080))
    rows=[]
    for rate in model.rates:
        assert rate.qualifier in {'Peak','Off-Peak'}
        card=ApiRateCard(rate.qualifier.lower(), SURFACE, 0, None,
            Decimal(rate.input), Decimal(rate.cached_input), None, Decimal(rate.output))
        rows.append(TimeBoundRate(card, '2026-09-14T00:00:00Z', END,
            PEAK if rate.qualifier == 'Peak' else tuple(off)))
    return ReviewedApiOffer(KEY,'opencode',MODEL,SURFACE,guard.model_offer_digest(metadata,MODEL),END,tuple(rows))


def exercise(tmp_path, *, expire=False, reprice=False, initial=NOW, changed_request=False):
    meta=snapshot()
    reviewed=plan(meta)
    clock={'at':initial}
    workspace=tmp_path/'same-workspace.txt'
    workspace.write_text('tool-7-completed')
    body=json.dumps({'model':MODEL,'stream':True,'messages':[
        {'role':'user','content':'continue'},
        {'role':'tool','tool_call_id':'tool-7','content':workspace.read_text()}]}).encode()
    request=ProviderRequest('chat/completions','unchanged-session',{},body)
    digest=hashlib.sha256(body).hexdigest()
    quote=quote_temporal_offer(reviewed,expected_offer_digest=reviewed.offer_digest,
        expected_model_key=KEY,expected_surface=SURFACE,request_digest=digest,
        now=initial.isoformat(),context_tokens=1000,input_tokens=1000,output_tokens=100)
    chosen=next(r for r in next(m for m in meta.terms.models if m.model_id==MODEL).rates
                if r.qualifier.lower()==quote.rate_id)
    debit=offers.estimate_quota_debit(quoted_usage_usd=str(quote.estimated_usage_usd),
        monthly_equivalent_usd=chosen.monthly_equivalent_usd,horizon_fractions=meta.terms.horizon_fractions)
    usage=parse_opencode_go_usage({'usage':{h:{'status':'ok','percent':v,'resetsAt':'2026-09-15T01:00:00Z'}
        for h,v in [('rolling',50),('weekly',20),('monthly',10)]}},observed_at=NOW)
    before=tuple(dict(x) for x in usage.quota_rows)
    trace=[]
    def check(req):
        guard.check_request_offer(meta,model_id=json.loads(req.body)['model'],protocol='openai-chat',
            now=clock['at'].isoformat(),expected_offer_digest=reviewed.offer_digest,
            expected_policy_digest=meta.terms.policy_digest,review_valid_until=END,
            promotion_valid_until=END,retention_valid_until=END)
        require_current_quote(quote,now=clock['at'].isoformat(),request_digest=hashlib.sha256(req.body).hexdigest(),
            offer_digest=guard.model_offer_digest(meta,MODEL),model_key=KEY,surface=SURFACE)
        trace.append('checked')
    def key(_):
        trace.append('key')
        if expire:
            clock['at']=datetime(2026,9,14,1,tzinfo=timezone.utc)
        return 'synthetic'
    class Reply:
        status=200
        def getheaders(self): return [('content-type','text/event-stream')]
        def read1(self,_): return b'data: [DONE]\n\n'
        def close(self): pass
    class Connection:
        sock=None
        def request(self,method,path,body,headers):
            trace.append('POST')
            assert body==request.body and headers['x-opencode-session']=='unchanged-session'
        def getresponse(self): return Reply()
        def close(self): pass
    if reprice:
        meta=replace(meta,terms=replace(meta.terms,economic_conditions_digest='f'*64))
    sent=replace(request,body=body.replace(b'continue',b'changed')) if changed_request else request
    try:
        result=stream_single_account(sent,choice=AccountChoice('go','a'*64,'account-a'),
            request_check=check,credential_loader=key,on_chunk=lambda _:None,
            connection_factory=lambda *a,**k:Connection())
    except OpenCodeGoTransportContractError:
        result=None
    assert tuple(dict(x) for x in usage.quota_rows)==before
    assert workspace.read_text()=='tool-7-completed'
    return result,trace,quote,debit


def test_actual_components_quote_interpret_and_stream_once(tmp_path):
    result,trace,quote,debit=exercise(tmp_path)
    assert result.terminal_observed and trace==['checked','key','checked','POST']
    assert quote.estimated_usage_usd==Decimal('.00021')
    assert Decimal(debit['five_hour'])==Decimal('.00175')


def test_price_boundary_during_credential_load_prevents_post(tmp_path):
    result,trace,_,_=exercise(tmp_path,expire=True)
    assert result is None and trace==['checked','key']


def test_new_economic_conditions_require_requote_before_credentials(tmp_path):
    result,trace,_,_=exercise(tmp_path,reprice=True)
    assert result is None and trace==[]


def test_request_body_cannot_reuse_another_quote(tmp_path):
    result,trace,_,_=exercise(tmp_path,changed_request=True)
    assert result is None and trace==[]


def test_fresh_peak_quote_doubles_estimated_burn_not_observed_usage(tmp_path):
    result,trace,quote,debit=exercise(tmp_path,initial=datetime(2026,9,14,1,tzinfo=timezone.utc))
    assert result.terminal_observed and trace.count('POST')==1
    assert quote.estimated_usage_usd==Decimal('.00042')
    assert Decimal(debit['five_hour'])==Decimal('.0035')


def test_promotional_allowance_revaluation_changes_only_future_estimate():
    fractions=('0.2','0.5','1')
    promotional=offers.estimate_quota_debit(quoted_usage_usd='.6',monthly_equivalent_usd='60',horizon_fractions=fractions)
    baseline=offers.estimate_quota_debit(quoted_usage_usd='.6',monthly_equivalent_usd='15',horizon_fractions=fractions)
    assert all(Decimal(baseline[h])==4*Decimal(promotional[h]) for h in promotional)


@pytest.mark.parametrize('expire,expected', [(False,200),(True,409)])
def test_real_harness_http_composes_quote_guard_usage_and_stream(tmp_path,monkeypatch,expire,expected):
    from functools import partial
    import http.client
    import threading
    from urllib.parse import urlsplit
    import sys
    from control_plane.opencode_go_harness_endpoint import GoHarnessEndpoint,HarnessBinding
    original=stream_single_account
    observed=[]
    failures=[]
    def through_endpoint(request,*,choice,request_check,credential_loader,on_chunk,connection_factory):
        receipt=[]
        def send(req,**kwargs):
            value=original(req,connection_factory=connection_factory,**kwargs)
            receipt.append(value)
            return value
        ep=GoHarnessEndpoint(HarnessBinding(request.session_id,MODEL,'openai-chat',choice,'p'*48),
            credential_loader=credential_loader,request_check=request_check,
            on_terminal_failure=failures.append,cancel=threading.Event(),stream=send)
        with ep:
            url=urlsplit(ep.base_url)
            conn=http.client.HTTPConnection(url.hostname,url.port,timeout=3)
            conn.request('POST','/v1/chat/completions',body=request.body,
                headers={'Authorization':'Bearer '+'p'*48,'Content-Type':'application/json'})
            result=conn.getresponse()
            status,body=result.status,result.read()
            conn.close()
            observed.append((status,body))
        if receipt:
            return receipt[0]
        raise OpenCodeGoTransportContractError('synthetic request was refused')
    monkeypatch.setattr(sys.modules[__name__],'stream_single_account',through_endpoint)
    result,trace,quote,debit=exercise(tmp_path,expire=expire)
    assert observed[0][0]==expected
    if expire:
        assert result is None and trace==['checked','key']
        assert failures==['request_admission_refused']
    else:
        assert result.terminal_observed
        assert trace==['checked','key','checked','POST']
        assert observed[0][1]==b'data: [DONE]\n\n' and failures==[]
        assert Decimal(debit['five_hour'])==Decimal('.00175')
