"""Real local HTTP harness consumer; provider/admission/credentials are fixtures."""
from dataclasses import replace
from functools import partial
import http.client
import json
import threading
from urllib.parse import urlsplit
import pytest
from control_plane.opencode_go_harness_endpoint import GoHarnessEndpoint, HarnessBinding
from control_plane.opencode_go_pooled_transport import AccountChoice, OpenCodeGoTransportContractError, OpenCodeGoEffectUnknown
from control_plane.opencode_go_stream import stream_single_account, StreamReceipt

CAP = 'c'*48
MODEL='glm-5.3-flash'
BODY=json.dumps({'model':MODEL,'stream':True,'messages':[{'role':'user','content':'continue'},{'role':'tool','tool_call_id':'old-tool','content':'already-completed'}]}).encode()
BINDING=HarnessBinding('same-session',MODEL,'openai-chat',AccountChoice('go','a'*64,'account-a'),CAP)


def call(endpoint, *, body=BODY, capability=CAP, path='/v1/chat/completions', headers=None, method='POST'):
    u=urlsplit(endpoint.base_url)
    connection=http.client.HTTPConnection(u.hostname,u.port,timeout=3)
    h={'Authorization':'Bearer '+capability,'Content-Type':'application/json'}
    h.update(headers or {})
    connection.request(method,path,body=body,headers=h)
    response=connection.getresponse()
    result=(response.status,response.read())
    connection.close()
    return result


def endpoint(*, stream=None, check=lambda r:None, failure=None):
    trace=[]
    def upstream(request,**kwargs):
        trace.append(request)
        kwargs['request_check'](request)
        kwargs['credential_loader'](kwargs['choice'].account_id)
        kwargs['request_check'](request)
        kwargs['on_chunk'](b'data: [DONE]\n\n')
        return StreamReceipt('account-a','a'*64,200,14,True)
    ep=GoHarnessEndpoint(BINDING,credential_loader=lambda a:trace.append('key') or 'synthetic-upstream-key',
        request_check=check,on_terminal_failure=failure or (lambda k:trace.append(k)),
        cancel=threading.Event(),stream=stream or upstream)
    return ep,trace


def test_real_http_consumer_retains_body_session_and_does_not_forward_client_secret():
    ep,trace=endpoint()
    with ep:
        status,body=call(ep)
        assert status==200 and body==b'data: [DONE]\n\n'
        assert trace[0].body==BODY and trace[0].session_id=='same-session'
        assert 'Authorization' not in trace[0].headers
        assert ep.base_url.startswith('http://127.0.0.1:')
    assert not any(t.name in {'go-endpoint','go-request'} and t.is_alive() for t in threading.enumerate())


def test_consecutive_successful_turns_keep_same_endpoint_and_binding():
    ep,trace=endpoint()
    with ep:
        first=ep.base_url
        assert call(ep)[0]==200
        second=BODY.replace(b'continue',b'next turn')
        assert call(ep,body=second)[0]==200
        assert ep.base_url==first
    requests=[r for r in trace if not isinstance(r,str)]
    assert [r.body for r in requests]==[BODY,second]
    assert {r.session_id for r in requests}=={'same-session'}


def test_real_progressive_delivery_before_provider_finishes():
    first_received=threading.Event()
    def upstream(req,**kw):
        kw['on_chunk'](b'data: {"choices":[]}\n\n')
        assert first_received.wait(2)
        kw['on_chunk'](b'data: [DONE]\n\n')
        return StreamReceipt('account-a','a'*64,200,35,True)
    ep,_=endpoint(stream=upstream)
    with ep:
        u=urlsplit(ep.base_url)
        c=http.client.HTTPConnection(u.hostname,u.port,timeout=3)
        c.request('POST','/v1/chat/completions',body=BODY,headers={'Authorization':'Bearer '+CAP,'Content-Type':'application/json'})
        r=c.getresponse()
        assert r.status==200
        assert r.read1(128)==b'data: {"choices":[]}\n\n'
        first_received.set()
        assert r.read()==b'data: [DONE]\n\n'
        c.close()


@pytest.mark.parametrize('kwargs',[
    {'capability':'wrong'}, {'path':'/v1/responses'}, {'body':BODY.replace(MODEL.encode(),b'other')},
    {'body':BODY.replace(b'true',b'false')}, {'body':b'not-json'},
    {'headers':{'Origin':'https://example.com'}}, {'method':'GET'},
])
def test_unbound_requests_never_reach_credential_or_stream(kwargs):
    ep,trace=endpoint()
    with ep:
        assert call(ep,**kwargs)[0] in {400,401,405}
        assert trace==[]
        assert not ep.stopped_forwarding


def test_effect_unknown_latches_before_failure_callback_and_client_retry_is_not_forwarded():
    calls=[]
    events=[]
    def upstream(req,**kwargs):
        calls.append(req)
        raise OpenCodeGoEffectUnknown('account-a',('account-a',))
    ep,_=endpoint(stream=upstream,failure=lambda k: events.append((k,ep.stopped_forwarding)))
    with ep:
        assert call(ep)[0]==409
        for _ in range(5):
            assert call(ep)[0]==409
    assert len(calls)==1 and events==[('effect_unknown',True)]


def test_partial_stream_failure_blocks_further_upstream_requests():
    calls=[]
    def upstream(req,**kwargs):
        calls.append(req)
        kwargs['on_chunk'](b'data: {"choices":[]}\n\n')
        raise OpenCodeGoEffectUnknown('account-a',('account-a',))
    ep,_=endpoint(stream=upstream)
    with ep:
        with pytest.raises(http.client.IncompleteRead):
            call(ep)
        assert call(ep)[0]==409
    assert len(calls)==1


def test_failed_failure_callback_does_not_reopen_transport():
    def fail(_):raise RuntimeError('sink failed')
    def upstream(*a,**kw):raise OpenCodeGoEffectUnknown('account-a',('account-a',))
    ep,_=endpoint(stream=upstream,failure=fail)
    with ep:
        assert call(ep)[0]==409
        assert ep.stopped_forwarding
        assert ep.failure_notification_failed
        assert call(ep)[0]==409


def test_admission_refusal_is_terminal_for_this_worker_endpoint():
    def refuse(_):raise OpenCodeGoTransportContractError('not admitted')
    ep,trace=endpoint(check=refuse)
    with ep:
        assert call(ep)[0]==409
        assert call(ep)[0]==409
    assert 'key' not in trace
    assert 'request_admission_refused' in trace


def test_uses_actual_streaming_edge_and_second_admission_check():
    trace=[]
    class Reply:
        status=200
        def getheaders(self):return [('content-type','text/event-stream')]
        def read1(self,_):return b'data: [DONE]\n\n'
        def close(self):pass
    class Connection:
        sock=None
        def request(self,method,path,body,headers):
            trace.append('POST')
            assert headers['Authorization']=='Bearer synthetic-upstream-key'
            assert headers['x-opencode-session']=='same-session'
            assert body==BODY
        def getresponse(self):return Reply()
        def close(self):pass
    ep,_=endpoint(stream=partial(stream_single_account,connection_factory=lambda *a,**k:Connection()),check=lambda r:trace.append('checked'))
    with ep:
        assert call(ep)[0]==200
    assert trace==['checked','checked','POST']


def test_concurrent_request_does_not_queue_or_send_second_inference():
    entered,release=threading.Event(),threading.Event()
    calls=[]
    def upstream(req,**kwargs):
        calls.append(req)
        entered.set()
        assert release.wait(2)
        kwargs['on_chunk'](b'data: [DONE]\n\n')
        return StreamReceipt('account-a','a'*64,200,14,True)
    ep,_=endpoint(stream=upstream)
    results=[]
    with ep:
        t=threading.Thread(target=lambda:results.append(call(ep)[0]))
        t.start()
        assert entered.wait(2)
        with pytest.raises((http.client.RemoteDisconnected,ConnectionResetError)):
            call(ep)
        release.set()
        t.join(3)
        assert not t.is_alive()
    assert len(calls)==1 and results==[200]


def test_capability_not_in_binding_repr_and_restart_refused():
    assert CAP not in repr(BINDING)
    ep,_=endpoint()
    with ep:pass
    ep.close()
    with pytest.raises(OpenCodeGoTransportContractError,match='restart'):
        ep.__enter__()


@pytest.mark.parametrize('capability',['', 'short', 'x'*257,'a b'+'x'*35])
def test_invalid_client_capability_refuses_before_listening(capability):
    with pytest.raises(OpenCodeGoTransportContractError):
        GoHarnessEndpoint(replace(BINDING,client_capability=capability),credential_loader=lambda _:None,
            request_check=lambda _:None,on_terminal_failure=lambda _:None,cancel=threading.Event())


@pytest.mark.parametrize("protocol,path,headers,terminal", [
    ("anthropic","messages",{"x-api-key":CAP},b'event: message_stop\ndata: {"type":"message_stop"}\n\n'),
    ("responses","responses",{"Authorization":"Bearer "+CAP},b'data: {"type":"response.completed","response":{"status":"completed"}}\n\n'),
])
def test_actual_protocol_stream_and_client_auth(protocol,path,headers,terminal):
    calls=[]
    class Reply:
        status=200
        def getheaders(self):return [("content-type","text/event-stream")]
        def read1(self,_):return terminal
        def close(self):pass
    class Connection:
        sock=None
        def request(self,method,path,body,headers):
            calls.append((path,headers))
            assert headers["Authorization"]=="Bearer upstream-fixture"
            assert CAP not in str(headers)
        def getresponse(self):return Reply()
        def close(self):pass
    ep=GoHarnessEndpoint(replace(BINDING,protocol=protocol),credential_loader=lambda _:"upstream-fixture",
        request_check=lambda _:None,on_terminal_failure=lambda _:None,cancel=threading.Event(),
        stream=partial(stream_single_account,connection_factory=lambda *a,**k:Connection()))
    with ep:
        url=urlsplit(ep.base_url)
        c=http.client.HTTPConnection(url.hostname,url.port,timeout=3)
        c.request("POST","/v1/"+path,body=BODY,headers={**headers,"Content-Type":"application/json"})
        r=c.getresponse()
        assert r.status==200 and r.read()==terminal
        c.close()
    assert len(calls)==1 and calls[0][0]=="/zen/go/v1/"+path


def test_conflicting_local_auth_headers_are_refused():
    ep,trace=endpoint()
    with ep:
        assert call(ep,headers={"x-api-key":CAP})[0]==401
    assert trace==[]


@pytest.mark.parametrize('changes', [{'account_id':'account-b'}, {'pool_generation':'b'*64}])
def test_stream_receipt_cannot_change_bound_identity(changes):
    count=[]
    def upstream(req,**kwargs):
        count.append(req)
        return replace(StreamReceipt('account-a','a'*64,200,0,True),**changes)
    ep,_=endpoint(stream=upstream)
    with ep:
        assert call(ep)[0]==409
        assert ep.stopped_forwarding
        assert call(ep)[0]==409
    assert len(count)==1


def test_reentrant_cleanup_reports_uncertainty_and_outer_owner_can_close():
    def upstream(req,**kwargs):
        raise OpenCodeGoEffectUnknown('account-a',('account-a',))
    ep,_=endpoint(stream=upstream,failure=lambda _:ep.close())
    with ep:
        assert call(ep)[0]==409
        assert ep.stopped_forwarding and ep.failure_notification_failed
    assert not any(t.name in {'go-endpoint','go-request'} and t.is_alive() for t in threading.enumerate())
