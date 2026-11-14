"""Real authenticated reply-host subscription and retained-policy composition.

Disposable Runtime and generated test JWT; native T3 and HTTPS peers are fake.
No installed account, native worker, subscription, callback or Dot is touched.
"""
import asyncio
import dataclasses
import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.reply_subscription_private_contract import PRIVATE_SCHEMA
from control_plane.executive_runtime import Runtime
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.session_bridge.installed_reply_events import RuntimeReplyEventHost
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from integrations.session_bridge.runtime_reply_authorization import policy_fingerprint
from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher
from integrations.session_bridge.runtime_return import RuntimeSessionReturn
from integrations.session_bridge.t3_native_client import Run, T3NativeClient, Unavailable
from integrations.session_bridge.t3_reply_events import T3OriginalReplySource
from integrations.session_bridge.web_reply_event_rpc import EventSubscribeRequest, EventUnsubscribeRequest
from integrations.session_bridge.web_reply_subscription_owner import owner_key
from tests.test_t3_native_client import Native, SCHEMAS, SCOPE, THREAD
from tests.test_session_bridge_reply_event_host_integration import authenticated_receiver, URL, SECRET


@pytest.fixture
def t3_host(tmp_path, authenticated_receiver):
    auth = authenticated_receiver
    runtime = Runtime.at(tmp_path)
    native = Native()
    client = T3NativeClient(SCOPE, native, SCHEMAS)
    async def access(principal, scope):
        if owner_key(principal) != owner_key(auth.principal) or scope != SCOPE:
            raise Unavailable('fixture native grant denied')
        return client
    source = T3OriginalReplySource(runtime, access, current=lambda value: value,
        clock=lambda: auth.now[0], enabled=True)
    fabric = RuntimeFabricTargetProjector(runtime)
    codex = RuntimeCodexTargetProjector(fabric, owner_configured=lambda: False)
    owner = RuntimeSessionReturn(runtime, fabric=fabric, codex=codex,
        socket_path=Path('/private/tmp/unused-t3-host-fixture.sock'), t3_replies=source)
    binding = asyncio.run(source.bind(auth.principal, Run(THREAD, 'run-1', 'original-request', 'launched')))
    sent = []
    class HTTPS:
        def request(self, method, path, body=None, headers=None):
            packet = json.loads(body)
            sent.append((packet, headers))
            self.body = (json.dumps({'challenge': packet['challenge']}).encode()
                if packet.get('type') == 'verification' else b'accepted')
        def getresponse(self):
            return SimpleNamespace(status=200, read=lambda limit: self.body)
        def close(self): pass
    def dns(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
    def host():
        return RuntimeReplyEventHost(owner, ExecutiveReplyCipher('fixture-key', b'k' * 32), auth.policies,
            clock=lambda: auth.now[0], enabled=True, resolver=dns, connector=lambda *args: HTTPS())
    def frame(operation, request):
        principal = dataclasses.asdict(auth.principal)
        principal['scopes'] = list(auth.principal.scopes)
        return {'schema': PRIVATE_SCHEMA, 'operation': operation, 'principal': principal,
            'arguments': dataclasses.asdict(request),
            'source_policy_sha256': policy_fingerprint(auth.policies.select(auth.principal))}
    return SimpleNamespace(runtime=runtime, source=source, owner=owner, auth=auth,
        binding=binding, sent=sent, make_host=host, host=host(), frame=frame)


def subscribe(case):
    request = EventSubscribeRequest(case.binding['request_ref'], URL, SECRET, 600000)
    value = asyncio.run(case.host.handle_frame(case.frame('subscribe', request)))
    assert value['ok'] is True, value
    assert value['data']['callback_verified'] is True
    assert value['data']['persisted'] is True
    assert value['data']['original_request_current'] is True
    return value['data']


def test_real_subscription_challenge_restart_native_return_and_retained_delivery(t3_host):
    case = t3_host
    receipt = subscribe(case)
    assert len(case.sent) == 1 and case.sent[0][0]['type'] == 'verification'
    # Lose the HTTP invocation and all its ephemeral client objects. The new
    # host must recover sealed authorization, not borrow a subscription fixture.
    case.host = case.make_host()
    result = asyncio.run(case.host.observe_t3_reply(case.auth.principal, case.binding['request_ref']))
    assert result['reply_committed'] is True and result['parent_consumed'] is False
    assert result['deliveries'][0]['state'] == 'TRANSPORT_ACCEPTED_PARENT_UNPROVEN'
    assert len(case.sent) == 2
    event = case.sent[1][0]
    assert event['data']['read_ref'] == case.binding['read_ref']
    assert event['data']['in_reply_to'] == case.binding['request_ref']
    assert event['data']['parent_consumed'] is False
    again = asyncio.run(case.host.observe_t3_reply(case.auth.principal, case.binding['request_ref']))
    assert again['deliveries'][0]['fresh_send'] is False and len(case.sent) == 2
    record = asyncio.run(case.host.store.read(receipt['subscription_id']))
    assert record.request_ref == case.binding['request_ref']
    retained = repr(case.runtime.store.list_events())
    assert SECRET not in retained and URL not in retained and case.auth.token not in retained


def test_current_policy_revocation_tombstones_t3_subscription_without_callback(t3_host):
    case = t3_host
    receipt = subscribe(case)
    prior = case.auth.policies._variants
    pair = prior[0]
    case.auth.policies._variants = (AppPolicies(
        read=dataclasses.replace(pair.read, allowed_subject_digests=('f' * 64,)),
        submit=dataclasses.replace(pair.submit, allowed_subject_digests=('f' * 64,))),)
    value = asyncio.run(case.host.observe_t3_reply(case.auth.principal, case.binding['request_ref']))
    assert value['deliveries'][0]['state'] == 'NOT_SENT'
    assert len(case.sent) == 1
    assert asyncio.run(case.host.store.read(receipt['subscription_id'])) is None
    case.auth.policies._variants = prior
    value = asyncio.run(case.host.observe_t3_reply(case.auth.principal, case.binding['request_ref']))
    assert value['deliveries'] == () and len(case.sent) == 1


def test_private_unsubscribe_preserves_native_result_but_stops_t3_delivery(t3_host):
    case = t3_host
    subscribe(case)
    request = EventUnsubscribeRequest(case.binding['request_ref'], URL)
    value = asyncio.run(case.host.handle_frame(case.frame('unsubscribe', request)))
    assert value['ok'] is True and value['data']['stopped'] is True
    result = asyncio.run(case.host.observe_t3_reply(case.auth.principal, case.binding['request_ref']))
    assert result['reply_committed'] is True and result['deliveries'] == ()
    assert len(case.sent) == 1
    reply = asyncio.run(case.source.read(case.auth.principal, {'read_ref': case.binding['read_ref']}))
    assert reply['answer'] == 'done' and reply['parent_consumed'] is False
