"""Security and bounded one-shot callback transport, no actual external socket calls."""
from __future__ import annotations

import base64
import importlib
import json
import socket

import pytest

from integrations.session_bridge.web_reply_delivery import (
    PendingReplyCallback,
    prepare_reply_webhook_verification,
    verify_reply_webhook_challenge_response,
)

def api():
    return importlib.import_module("integrations.session_bridge.web_reply_callback_transport")

SECRET="whsec_"+base64.b64encode(b"k"*32).decode()
URL="https://receiver.example.com/mcp-events/callback_123"
NOW=1791766800
NONCE="challenge_0123456789abcdef"
MESSAGE="msg_verification_0123456789"

def packet():
    return prepare_reply_webhook_verification(
        callback=PendingReplyCallback(
            subscription_id="sub_original001",principal_ref="principal-001",
            request_ref="request-001",access_current=True,
            expires_at=NOW+120, signing_secret=SECRET),
        challenge=NONCE, message_id=MESSAGE,signed_at=NOW)

class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status=status
        self._body=body if body is not None else json.dumps({"challenge":NONCE}).encode()
    def read(self,amount=None):
        return self._body if amount is None else self._body[:amount]

class FakeConnection:
    def __init__(self, status=200, body=None, fail_phase=None):
        self.calls=[]
        self.response=FakeResponse(status,body)
        self.fail_phase=fail_phase
        self.closed=False
    def request(self,method,path,body,headers):
        self.calls.append((method,path,body,dict(headers)))
        if self.fail_phase=="send":
            raise OSError("possibly sent before acknowledgment")
    def getresponse(self):
        if self.fail_phase=="read":
            raise TimeoutError("timeout waiting for response")
        return self.response
    def close(self):
        self.closed=True

def resolver(*args,**kwargs):
    return [
        (socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_TCP,"",("93.184.215.14",443)),
    ]

def send(**kwargs):
    created=[]
    def make(host,port,address,timeout):
        created.append((host,port,address,timeout))
        fake=kwargs.pop("connection",None) or FakeConnection()
        created.append(fake)
        return fake
    receipt=api().send_once(URL,packet(),resolver=kwargs.pop("resolver",resolver),
                            connector=make,timeout_s=kwargs.pop("timeout_s",7))
    return receipt,created


def test_callback_challenge_posts_signed_exact_bytes_to_pinned_ip_and_does_not_follow_redirects():
    receipt, created=send()
    assert created[0]==("receiver.example.com",443,"93.184.215.14",7)
    conn=created[1]
    assert conn.closed
    method,path,body,headers=conn.calls[0]
    assert method=="POST" and path=="/mcp-events/callback_123"
    assert body==packet().body
    assert headers["Host"]=="receiver.example.com"
    assert headers["webhook-id"]==MESSAGE
    assert "webhook-signature" in headers
    assert receipt.status_code==200
    assert verify_reply_webhook_challenge_response(
        challenge=NONCE,response_body=receipt.response_body,status=receipt.status_code)
    assert receipt.response_truncated is False
    assert not hasattr(receipt,"parent_consumed")


def test_https_callback_url_preserves_query_and_nondefault_port_in_sni_host():
    created=[]
    def make(host,port,address,timeout):
        created.append((host,port,address))
        f=FakeConnection(); created.append(f); return f
    rr=lambda *args,**kw: [(socket.AF_INET,socket.SOCK_STREAM,6,"",("93.184.215.14",8443))]
    receipt=api().send_once("https://receiver.example.com:8443/cb?token=sample",
        packet(),resolver=rr,connector=make,timeout_s=7)
    assert created[0]==("receiver.example.com",8443,"93.184.215.14")
    assert created[1].calls[0][1]=="/cb?token=sample"
    assert created[1].calls[0][3]["Host"]=="receiver.example.com:8443"
    assert receipt.status_code==200


@pytest.mark.parametrize("addresses", [
    [("127.0.0.1",socket.AF_INET)],
    [("10.1.0.4",socket.AF_INET)],
    [("192.168.1.5",socket.AF_INET)],
    [("169.254.169.254",socket.AF_INET)],
    [("172.31.2.3",socket.AF_INET)],
    [("100.64.0.1",socket.AF_INET)],
    [("::1",socket.AF_INET6)],
    [("fe80::1",socket.AF_INET6)],
    [("fc00::1",socket.AF_INET6)],
    [("64:ff9b::a9fe:a9fe",socket.AF_INET6)],
    [("2002:a9fe:a9fe::",socket.AF_INET6)],
    [("93.184.215.14",socket.AF_INET),("127.0.0.1",socket.AF_INET)],
    [],
])
def test_internal_mixed_or_absent_dns_records_refused_before_connector(addresses):
    created=[]
    rr=lambda *args,**kw: [
        (af,socket.SOCK_STREAM,6,"",(ip,443,0,0) if af==socket.AF_INET6 else (ip,443))
        for ip,af in addresses
    ]
    with pytest.raises(api().CallbackDestinationRefused):
        api().send_once(URL,packet(),resolver=rr,
                        connector=lambda *a:created.append(a),timeout_s=7)
    assert not created


@pytest.mark.parametrize("url", [
    "http://receiver.example.com/cb", "https://127.0.0.1/cb",
    "https://localhost/cb", "https://user:secret@receiver.example.com/cb",
    "https://receiver.example.com/cb#frag", "https://receiver.example.com:bad/cb",
    "https://receiver.example.com/%0d%0aX-Header:evil",
])
def test_unsafe_urls_refused_without_dns_or_socket(url):
    called=[]
    with pytest.raises(api().CallbackDestinationRefused):
        api().send_once(url,packet(),resolver=lambda *a:called.append(a),
                        connector=lambda *a:called.append(a))
    assert not called


def test_webhook_redirect_is_reported_but_not_followed():
    conn=FakeConnection(status=302,body=b"Redirect")
    receipt,created=send(connection=conn)
    assert receipt.status_code==302
    assert conn.closed and len(conn.calls)==1
    assert api().classify_reply_webhook_response(receipt.status_code)=="REFUSED_NO_REDIRECT"


@pytest.mark.parametrize("phase",["send","read"])
def test_ambiguous_post_send_or_read_failure_is_effect_unknown_and_never_retried(phase):
    conn=FakeConnection(fail_phase=phase)
    with pytest.raises(api().CallbackEffectUnknown):
        send(connection=conn)
    assert conn.closed
    assert len(conn.calls)==1


def test_bounded_response_and_explicit_body_truncation_cannot_verify_challenge():
    conn=FakeConnection(body=b"A"*900)
    receipt,_=send(connection=conn)
    assert receipt.response_truncated
    assert len(receipt.response_body)<=513
    assert not verify_reply_webhook_challenge_response(
        challenge=NONCE,response_body=receipt.response_body,status=receipt.status_code)


def test_pinned_tls_connection_dials_exact_public_ip_and_preserves_certificate_hostname(monkeypatch):
    seen=[]
    class FakeTLS:
        check_hostname=True
        verify_mode=2
        def wrap_socket(self,sock,server_hostname):
            seen.append(("sni",server_hostname,sock))
            return ("tls-socket",sock)
    def fake_create_connection(addr,timeout):
        seen.append(("dial",addr,timeout))
        return "raw-socket"
    monkeypatch.setattr(socket,"create_connection",fake_create_connection)
    conn=api().PinnedHTTPSConnection("receiver.example.com",443,
                                   "93.184.215.14",timeout=7)
    conn._context=FakeTLS()
    conn.connect()
    assert seen[0]==("dial",("93.184.215.14",443),7)
    assert seen[1]==("sni","receiver.example.com","raw-socket")
    assert conn.sock==("tls-socket","raw-socket")


def test_no_transport_ownership_of_retry_queue_subscription_or_credential_source():
    module=api()
    assert not hasattr(module,"retry_delivery")
    assert not hasattr(module,"create_subscription")
    assert not hasattr(module,"credential_source")


def test_public_ipv6_connects_only_to_original_verified_address():
    created=[]
    def connect(host,port,address,timeout):
        created.append((host,port,address,timeout))
        conn=FakeConnection()
        created.append(conn)
        return conn
    def dns(*args,**kwargs):
        return [(socket.AF_INET6,socket.SOCK_STREAM,socket.IPPROTO_TCP,"",
                 ("2001:4860:4860::8888",443,0,0))]
    receipt=api().send_once(URL,packet(),resolver=dns,connector=connect)
    assert receipt.status_code==200
    assert created[0]==("receiver.example.com",443,"2001:4860:4860::8888",7)
    assert created[1].closed


def test_dns_record_count_over_bound_refused_before_any_connect():
    did_connect=[]
    def dns(*args,**kwargs):
        return [(socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_TCP,"",
                 ("93.184.215.14",443)) for _ in range(17)]
    with pytest.raises(api().CallbackDestinationRefused):
        api().send_once(URL,packet(),resolver=dns,
                        connector=lambda *a:did_connect.append(a))
    assert not did_connect


def test_malicious_signed_header_or_forged_packet_is_denied_pre_dns():
    from dataclasses import replace
    called=[]
    original=packet()
    forged=dict(original.headers)
    forged["webhook-id"]="id\r\nX-Injected: yes"
    with pytest.raises(api().CallbackDestinationRefused):
        api().send_once(URL,replace(original,headers=forged),
                        resolver=lambda *a:called.append(a))
    with pytest.raises(api().CallbackDestinationRefused):
        api().send_once(URL,object(),resolver=lambda *a:called.append(a))
    assert not called


def test_canonical_native_reply_projection_reaches_one_signed_original_request_transport():
    from test_session_bridge_web_reply_events import Resolver, project
    from integrations.session_bridge.web_reply_delivery import (
        VerifiedReplySubscription, prepare_reply_webhook,
    )
    projection=project(Resolver())
    subscription=VerifiedReplySubscription(
        subscription_id="sub_original001",principal_ref="principal-001",
        request_ref=projection["data"]["request_ref"],
        event_name=projection["name"],access_current=True,active=True,
        expires_at=NOW+120,signing_secrets=(SECRET,))
    packet=prepare_reply_webhook(subscription=subscription,
                                 event=projection,signed_at=NOW)
    # Exactly one signed canonical event, no double-dispatch or model-origin
    # callback destination. A 2xx is still transport only.
    connection=FakeConnection(status=202,body=b"")
    envelope=api().send_once(URL,packet,resolver=resolver,
                             connector=lambda *args:connection)
    assert len(connection.calls)==1 and connection.closed
    assert envelope.status_code==202
    assert envelope.response_body==b""
    assert projection["data"]["parent_consumed"] is False
    assert projection["eventId"]==packet.headers["webhook-id"]
    assert projection["data"]["read_ref"]=="native-return-read-001"


@pytest.mark.parametrize("changed", [
    {"webhook-id":"evt-"+"b"*64},
    {"webhook-timestamp":"soon"},
    {"webhook-signature":"v1,not-a-canonical-256-bit-signature"},
    {"X-MCP-Subscription-Id":"wrong-subscription"},
])
def test_tampered_signed_headers_are_refused_before_dns_or_send(changed):
    from dataclasses import replace
    source=packet()
    headers={**source.headers,**changed}
    fake=replace(source,headers=headers)
    consulted=[]
    with pytest.raises(api().CallbackDestinationRefused):
        api().send_once(URL,fake,
            resolver=lambda *a,**kw:consulted.append(("dns",a)),
            connector=lambda *a:consulted.append(("socket",a)))
    assert consulted==[]


@pytest.mark.parametrize("malformed", [
    b"not json",
    b'{"type":"terminated"}',
    b'{"type":"verification","challenge":"too-short"}',
    b'{"type":"verification","challenge":"challenge_0123456789abcdef","type":"verification"}',
])
def test_unrecognized_duplicate_key_or_incomplete_control_body_never_reaches_dns(malformed):
    from dataclasses import replace
    source=packet()
    fake=replace(source,body=malformed)
    consulted=[]
    with pytest.raises(api().CallbackDestinationRefused):
        api().send_once(URL,fake,
            resolver=lambda *a,**kw:consulted.append("dns"),
            connector=lambda *a:consulted.append("socket"))
    assert consulted==[]


def test_canonical_signed_event_is_accepted_without_altering_exact_payload_bytes():
    from test_session_bridge_web_reply_events import Resolver, project
    from integrations.session_bridge.web_reply_delivery import (
        VerifiedReplySubscription,prepare_reply_webhook,
    )
    event=project(Resolver())
    subscriber=VerifiedReplySubscription(
        subscription_id="sub_original001",principal_ref="principal-001",
        request_ref=event["data"]["request_ref"],event_name=event["name"],
        access_current=True,active=True,expires_at=NOW+300,
        signing_secrets=(SECRET,),
    )
    signed=prepare_reply_webhook(subscription=subscriber,event=event,signed_at=NOW)
    conn=FakeConnection(status=202,body=b"")
    receipt=api().send_once(URL,signed,resolver=resolver,
                            connector=lambda *a:conn)
    assert receipt.status_code==202
    assert conn.calls[0][2]==signed.body
    assert conn.closed
