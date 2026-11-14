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
from tests.test_t3_native_client import Native, SCHEMAS, SCOPE, THREAD, schema
from tests.test_session_bridge_reply_event_host_integration import authenticated_receiver, URL, SECRET


@pytest.fixture
def t3_host(tmp_path, authenticated_receiver):
    auth = authenticated_receiver
    runtime = Runtime.at(tmp_path)
    native = Native()
    native_schemas = dict(SCHEMAS, t3_pending_request=schema('environmentId', 'threadId', 'action', 'requestId', 'answers'))
    client = T3NativeClient(SCOPE, native, native_schemas)
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
    return SimpleNamespace(runtime=runtime, source=source, owner=owner, auth=auth, native=native, client=client,
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


def pending_question(case):
    case.native.detail['thread'].update(status='running', activeRunId='run-1', pendingRequestCount=1)
    case.native.responses['t3_thread_wait'] = {'structuredContent': {
        'threadId': THREAD.thread_id, 'runId': 'run-1', 'status': 'running', 'timedOut': True}}
    question = {'threadId': THREAD.thread_id, 'runId': 'run-1', 'kind': 'user_input',
                'status': 'pending', 'requestId': 'pending-1',
                'questions': [{'id': 'dataset', 'header': 'Dataset', 'question': 'Which dataset?',
                               'options': [], 'required': True}]}
    case.native.responses['t3_pending_request'] = lambda args: {'structuredContent': question}
    return question


def test_pending_question_signed_event_exact_public_read_and_duplicate(t3_host):
    from integrations.session_bridge.native_read import NativeReplyReader
    from integrations.session_bridge.return_tools import NativeReplyReadTool
    from tests import test_session_bridge_installed as installed_fixture
    case = t3_host
    pending_question(case)
    subscribe(case)
    # Restart the event-host composition; authorization and subscription remain
    # owned by the existing Runtime rather than by this test's request object.
    case.host = case.make_host()
    value = asyncio.run(case.host.observe_t3_question(
        case.auth.principal, case.binding['request_ref'], 'pending-1'))
    assert value['run_complete'] is False and value['parent_consumed'] is False
    assert value['deliveries'][0]['state'] == 'TRANSPORT_ACCEPTED_PARENT_UNPROVEN'
    assert len(case.sent) == 2
    event, headers = case.sent[1]
    assert event['data']['message_key'] == value['message_key']
    assert event['data']['read_ref'] == case.binding['read_ref']
    assert 'not a completed task' in event['data']['summary']
    assert 'Which dataset?' not in json.dumps(event)
    assert any('signature' in key.lower() for key in headers)
    reader = NativeReplyReader(case.owner, socket_path=case.owner.socket_path,
        clock=lambda: case.auth.now[0], t3_replies=case.source)
    public = asyncio.run(NativeReplyReadTool(reader).handle(installed_fixture.PRINCIPAL,
        'session_reply_read', {'read_ref': value['read_ref'], 'message_key': value['message_key']}))
    assert public['ok'] is True, public
    assert public['data']['questions'][0]['question'] == 'Which dataset?'
    assert public['data']['status'] == 'question_pending'
    assert public['data']['run_id'] == 'run-1'
    assert public['data']['run_complete'] is False
    again = asyncio.run(case.host.observe_t3_question(
        case.auth.principal, case.binding['request_ref'], 'pending-1'))
    assert again['deliveries'][0]['fresh_send'] is False
    assert len(case.sent) == 2


def test_question_answered_before_delivery_is_not_sent_or_unknown(t3_host):
    case = t3_host
    question = pending_question(case)
    subscribe(case)
    receipt = asyncio.run(case.source.observe_question(case.auth.principal,
        case.binding['request_ref'], 'pending-1'))
    observed = asyncio.run(case.source.read(case.auth.principal,
        {'read_ref': receipt['read_ref'], 'message_key': receipt['message_key']}))
    question['status'] = 'resolved'
    delivered = asyncio.run(case.host.handle_committed(read_ref=receipt['read_ref'],
        message_key=receipt['message_key'], fingerprint=observed['question_sha256']))
    assert delivered[0]['state'] == 'UNAVAILABLE'
    assert len(case.sent) == 1  # Verification only; no callback was attempted.


def test_pending_question_then_final_response_use_same_subscription_distinct_events(t3_host):
    case = t3_host
    question = pending_question(case)
    subscription = subscribe(case)
    pending = asyncio.run(case.host.observe_t3_question(
        case.auth.principal, case.binding['request_ref'], 'pending-1'))
    assert pending['run_complete'] is False
    question['status'] = 'resolved'
    case.native.detail['thread'].update(status='completed', activeRunId=None, pendingRequestCount=0)
    case.native.responses['t3_thread_wait']['structuredContent'].update(status='completed', timedOut=False)
    final = asyncio.run(case.host.observe_t3_reply(case.auth.principal, case.binding['request_ref']))
    assert final['deliveries'][0]['state'] == 'TRANSPORT_ACCEPTED_PARENT_UNPROVEN'
    assert len(case.sent) == 3
    first, last = case.sent[1][0], case.sent[2][0]
    assert first['eventId'] != last['eventId']
    assert first['data']['message_key'].startswith('t3-native-question-')
    assert last['data']['message_key'].startswith('t3-native-reply-')
    assert first['data']['read_ref'] == last['data']['read_ref'] == case.binding['read_ref']
    retained = asyncio.run(case.host.store.read(subscription['subscription_id']))
    assert retained.request_ref == case.binding['request_ref']
    assert all(packet['data']['parent_consumed'] is False for packet in (first, last))


def test_foreign_run_question_cannot_reach_original_subscriber(t3_host):
    from integrations.session_bridge.t3_native_client import Conflict
    case = t3_host
    question = pending_question(case)
    subscribe(case)
    question['runId'] = 'different-run'
    with pytest.raises(Conflict):
        asyncio.run(case.host.observe_t3_question(case.auth.principal,
            case.binding['request_ref'], 'pending-1'))
    assert len(case.sent) == 1
    assert all(event.event_type != 'T3_ORIGINAL_QUESTION_OBSERVED'
               for event in case.runtime.store.list_events())
