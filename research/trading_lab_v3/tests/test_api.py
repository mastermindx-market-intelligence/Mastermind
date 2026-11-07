import json
import logging
import pytest
from fastapi.testclient import TestClient
from backend.server import app
from backend.fixtures import SAMPLE_PLAN
from backend.preflight import ContractError
import backend.server as server_module

client=TestClient(app)

def test_api_real_consumer_of_core():
    r=client.post('/api/preflight',json={'plan':SAMPLE_PLAN})
    assert r.status_code==200
    assert r.json()['preview']['value']=='5025.00'
    assert r.json()['state']=='REVIEW_NEEDED'
    assert r.headers['cache-control']=='no-store'

@pytest.mark.parametrize('origin',['https://evil.example','null','http://localhost.evil','http://127.0.0.1:9999'])
def test_origin_rejected(origin):
    assert client.post('/api/preflight',headers={'Origin':origin},json={'plan':SAMPLE_PLAN}).status_code==403

def test_dns_rebinding_host_refused():
    assert client.get('/api/demo',headers={'Host':'evil.example'}).status_code==403

@pytest.mark.parametrize('data',[{'plan':SAMPLE_PLAN,'user_id':'other'}, {'plan':SAMPLE_PLAN,'case':'live'},
 {'plan':{'cash':'1000000'}}, {'plan':SAMPLE_PLAN,'previous':[]}, []])
def test_contract_refused(data):
    assert client.post('/api/preflight',json=data).status_code==422

def test_duplicate_json_fields_refused():
    r=client.post('/api/preflight',content='{"plan":{},"plan":{}}',headers={'Content-Type':'application/json'})
    assert r.status_code==422

def test_no_plain_text_csrf():
    assert client.post('/api/preflight',content=json.dumps({'plan':SAMPLE_PLAN})).status_code==422

def test_body_bound():
    assert client.post('/api/preflight',json={'plan':{'thesis':'x'*40000}}).status_code==422

def test_no_trading_endpoint_masquerading_as_live():
    r=client.post('/api/execute',json={'plan':SAMPLE_PLAN})
    assert r.status_code==501 and r.json()['order_submitted'] is False

def test_bad_numbers_in_json_refused():
    for raw in ('NaN','Infinity','-Infinity'):
        assert client.post('/api/preflight',content='{"plan":{"amount":'+raw+'}}',headers={'Content-Type':'application/json'}).status_code==422

def test_api_amount_change_rechecks_economics_without_repeating_thesis_review():
    old=client.post('/api/preflight',json={'plan':SAMPLE_PLAN,'case':'reviewed_example'}).json()
    new=client.post('/api/preflight',json={'plan':{**SAMPLE_PLAN,'amount':'251'},'case':'reviewed_example','previous':old}).json()
    assert new['previous_still_current'] is False
    assert new['state']=='PREVIEW_READY'
    assert new['preview']['value']=='5045.10'
    changed=client.post('/api/preflight',json={'plan':{**SAMPLE_PLAN,'thesis':'A different mechanism'},'case':'reviewed_example'}).json()
    assert changed['state']=='REVIEW_NEEDED'


# Regression for the raw-exception disclosure finding on POST /api/preflight.
# EXCEPTION_MARKER is a unique synthetic, non-secret stand-in for any internal
# detail an unexpected exception could carry. The handler must never echo it in
# the response body, and the repair must not merely move the same text elsewhere.
EXCEPTION_MARKER='PR566_C1_SYNTHETIC_MARKER_7f3a9c2b'


def _raise_marker(exc_type):
    def _boom(*args,**kwargs):
        raise exc_type(EXCEPTION_MARKER)
    return _boom


@pytest.mark.parametrize('exc_type',[ContractError, ValueError, TypeError, KeyError])
def test_preflight_never_discloses_raw_exception_text(monkeypatch,caplog,exc_type):
    monkeypatch.setattr(server_module,'evaluate',_raise_marker(exc_type))
    with caplog.at_level(logging.DEBUG):
        r=client.post('/api/preflight',json={'plan':SAMPLE_PLAN})
    assert r.status_code==422
    body=r.json()
    assert body['error']=='INVALID_INPUT'
    assert body['execution_authority'] is False
    assert EXCEPTION_MARKER not in r.text,'raw exception text disclosed in response body: %s' % r.text
    assert exc_type.__name__ not in r.text,'exception class disclosed in response body: %s' % r.text
    assert 'Traceback' not in r.text
    assert EXCEPTION_MARKER not in caplog.text,'raw exception text logged: %s' % caplog.text
    detail=body.get('detail')
    assert isinstance(detail,str) and detail
    assert r.headers['cache-control']=='no-store'


def test_preflight_error_response_is_stable_across_caught_exception_classes(monkeypatch):
    bodies=[]
    for exc_type in (ContractError, ValueError, TypeError, KeyError):
        monkeypatch.setattr(server_module,'evaluate',_raise_marker(exc_type))
        r=client.post('/api/preflight',json={'plan':SAMPLE_PLAN})
        assert r.status_code==422
        bodies.append(r.text)
    assert len(set(bodies))==1,'error response is not stable across exception classes: %r' % (bodies,)
